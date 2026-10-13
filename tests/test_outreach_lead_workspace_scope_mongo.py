"""Lead isolation against an owned, loopback-only disposable Mongo process.

Opt in with OUTREACH_TEST_LOCAL_MONGO=1. This suite checks real query and route
behavior; it does not exercise transactions, providers or production data.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from outreach.core.suppression import guard_scope
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope import (
    FOREIGN, USER_ID, WORKSPACE, client_for, tenant_db,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable local Mongo is opt-in",
)]


@pytest.fixture(scope="module")
def mongo_server():
    executable = shutil.which("mongod")
    assert executable, "Native scope checks require mongod"
    with tempfile.TemporaryDirectory(prefix="unravler-lead-scope-") as directory:
        storage = Path(directory) / "data"
        storage.mkdir(mode=0o700)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        uri = f"mongodb://127.0.0.1:{port}/?directConnection=true"
        process = subprocess.Popen([
            executable, "--dbpath", str(storage), "--bind_ip", "127.0.0.1",
            "--port", str(port), "--nounixsocket", "--logpath", str(Path(directory) / "mongo.log"),
            "--setParameter", "diagnosticDataCollectionEnabled=false",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = MongoClient(uri, serverSelectionTimeoutMS=200, connectTimeoutMS=200)
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, "Owned Mongo failed to start"
                try:
                    client.admin.command("ping")
                    break
                except PyMongoError:
                    if time.monotonic() >= deadline:
                        raise AssertionError("Owned Mongo did not become ready") from None
                    time.sleep(0.05)
            yield uri
            assert not [name for name in client.list_database_names() if name.startswith("test_lead_scope_")]
        finally:
            client.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@pytest_asyncio.fixture
async def real_db(mongo_server):
    client = AsyncIOMotorClient(mongo_server, tz_aware=True, serverSelectionTimeoutMS=2000)
    name = "test_lead_scope_" + uuid.uuid4().hex
    db = client[name]
    try:
        assert name not in await client.list_database_names()
        source = tenant_db(lead_scope={"workspace_id": FOREIGN})
        for collection, rows in source.collections.items():
            if rows.docs:
                await db[collection].insert_many(rows.docs)
        yield db
    finally:
        await client.drop_database(name)
        client.close()


@pytest_asyncio.fixture
async def admission_db(replica_db):
    source = tenant_db(lead_scope={"workspace_id": FOREIGN})
    for collection, rows in source.collections.items():
        if rows.docs:
            await replica_db[collection].insert_many(rows.docs)
    return replica_db


async def test_actual_list_and_export_exclude_creator_tagged_legacy_scopes(real_db):
    await real_db.outreach_leads.insert_many([
        {"id": "null", "workspace_id": None, "user_id": USER_ID, "email": "private-null@example.invalid"},
        {"id": "missing", "user_id": USER_ID, "email": "private-missing@example.invalid"},
        {"id": "uid", "workspace_id": USER_ID, "user_id": USER_ID, "email": "private-uid@example.invalid"},
        {"id": "array", "workspace_id": [WORKSPACE, FOREIGN], "user_id": USER_ID, "email": "private-array@example.invalid"},
        {"id": "current", "workspace_id": WORKSPACE, "user_id": "someone-else", "email": "current@example.invalid"},
    ])
    async with client_for(real_db) as client:
        listed = await client.get("/leads")
        exported = await client.get("/leads/export")
        changed_array = await client.patch("/leads/array/stage", json={"pipeline_stage": "replied"})
    assert listed.status_code == exported.status_code == 200
    assert listed.json()["total"] == 1
    assert [row["id"] for row in listed.json()["leads"]] == ["current"]
    assert "current@example.invalid" in exported.text
    assert "private" not in exported.text
    assert changed_array.status_code == 404


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/leads/target/activity", None),
    ("PATCH", "/leads/target/stage", {"pipeline_stage": "replied"}),
    ("POST", "/leads/target/notes", {"note": "foreign note"}),
    ("POST", "/leads/target/pause", {}),
    ("POST", "/leads/target/resume", None),
    ("DELETE", "/leads/target", None),
])
async def test_actual_foreign_resource_routes_deny_without_writes(real_db, method, path, body):
    before = await real_db.outreach_leads.find_one({"id": "target"})
    async with client_for(real_db) as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 404
    assert await real_db.outreach_leads.find_one({"id": "target"}) == before
    assert await real_db.outreach_lead_notes.count_documents({}) == 0


@pytest.mark.parametrize("scope", [FOREIGN, [WORKSPACE, FOREIGN]])
async def test_actual_campaign_scope_blocks_creator_intake(real_db, scope):
    await real_db.outreach_campaigns.update_one({"id": "campaign"}, {"$set": {"workspace_id": scope}})
    async with client_for(real_db) as client:
        listed = await client.get("/leads?campaign_id=campaign")
        preview = await client.post("/leads/preview", json={"campaign_id": "campaign", "raw_text": "LinkedIn URL"})
    assert listed.status_code == preview.status_code == 404


async def test_actual_stale_context_checks_resolved_workspace_erasure_hold(real_db):
    await real_db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), "erasure_state": "stopped"})
    stale = {"user_id": USER_ID, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    async with client_for(real_db, stale, mounted=True) as client:
        response = await client.get("/leads")
    assert response.status_code == 409


async def test_actual_import_updates_only_current_workspace_children(admission_db):
    real_db = admission_db
    for workspace in (FOREIGN, WORKSPACE):
        await real_db.outreach_import_jobs.insert_one({
            "id": "job", "workspace_id": workspace, "campaign_id": "campaign", "status": "queued",
        })
        await real_db.outreach_leads.insert_one({
            "id": "staged", "workspace_id": workspace, "import_job_id": "job",
            "campaign_id": "campaign", "linkedin_url": "https://linkedin.com/in/staged",
            "first_name": "Original", "execution_state": "staged",
        })
    await real_db.outreach_campaigns.insert_one({"id": "campaign", "workspace_id": FOREIGN, "leads_count": 10})
    async with client_for(real_db) as client:
        cancelled = await client.post("/leads/import-jobs/job/cancel")
        committed = await client.post("/leads/import-jobs/job/commit", json={"name_overrides": {"staged": "Edited"}})
    assert cancelled.status_code == committed.status_code == 200
    assert (await real_db.outreach_import_jobs.find_one({"id": "job", "workspace_id": FOREIGN}))["status"] == "queued"
    foreign = await real_db.outreach_leads.find_one({"id": "staged", "workspace_id": FOREIGN})
    current = await real_db.outreach_leads.find_one({"id": "staged", "workspace_id": WORKSPACE})
    assert foreign["first_name"] == "Original" and foreign["execution_state"] == "staged"
    assert current["first_name"] == "Edited" and current["execution_state"] == "queued"
    assert (await real_db.outreach_campaigns.find_one({"id": "campaign", "workspace_id": FOREIGN}))["leads_count"] == 10


@pytest.mark.parametrize("path,payload", [
    ("/leads/import-urls", {"urls_text": "https://linkedin.com/in/alice, Alice"}),
    ("/leads/import-csv", {"csv_text": "LinkedIn URL,First Name\nhttps://linkedin.com/in/alice,Alice"}),
])
async def test_actual_common_import_counter_ignores_foreign_and_array_campaigns(admission_db, path, payload):
    real_db = admission_db
    await real_db.outreach_campaigns.delete_many({})
    await real_db.outreach_campaigns.insert_many([
        {"id": "campaign", "workspace_id": FOREIGN, "leads_count": 10},
        {"id": "campaign", "workspace_id": [WORKSPACE, FOREIGN], "leads_count": 20},
        {"id": "campaign", "workspace_id": WORKSPACE, "status": "draft", "leads_count": 1},
    ])
    async with client_for(real_db) as client:
        response = await client.post(path, json={"campaign_id": "campaign", **payload})
    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    rows = await real_db.outreach_campaigns.find({}).to_list(length=10)
    assert [row["leads_count"] for row in rows] == [10, 20, 2]


async def test_actual_array_job_scope_never_authorizes_read_or_write(real_db):
    await real_db.outreach_import_jobs.insert_one({
        "id": "job", "workspace_id": [WORKSPACE, FOREIGN], "campaign_id": "campaign", "status": "queued",
    })
    async with client_for(real_db) as client:
        read = await client.get("/leads/import-jobs/job")
        cancel = await client.post("/leads/import-jobs/job/cancel")
        commit = await client.post("/leads/import-jobs/job/commit")
    assert read.status_code == cancel.status_code == commit.status_code == 404
    assert (await real_db.outreach_import_jobs.find_one({"id": "job"}))["status"] == "queued"
