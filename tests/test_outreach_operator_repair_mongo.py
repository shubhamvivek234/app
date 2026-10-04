"""Real Mongo ordering for local operator repair; no provider traffic."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from outreach.core.connection_repair import ConnectionRepair
from outreach.core.manual_resolution import ManualResolution
from tests.test_outreach_connection_repair import database, prepared
from tests.test_outreach_execution_mongo import mongo_db  # noqa: F401
from tests.test_outreach_manual_resolution import unknown

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1",
    reason="Disposable local MongoDB test is opt-in")]


async def seed(db, memory):
    for name, collection in memory.collections.items():
        if collection.docs:
            await db[name].insert_many(collection.docs)
    await db.outreach_accounts.create_index([("workspace_id", 1), ("id", 1)], unique=True)


async def test_real_mongo_human_manual_resolution_preserves_unknown_and_idempotent_projection(mongo_db):
    memory, _ = await unknown(auto_like=True)
    await seed(mongo_db, memory)
    service = ManualResolution(mongo_db)
    view = await service.inspect("w", "j")
    await service.resolve("w", "j", {"comment": "confirmed_sent"}, "operator", "Independently inspected this action after sender workers were drained.",
        workers_drained=True, expected_digest=view["review_digest"])
    await service.finish("w", "j")
    post = await mongo_db.outreach_engage_posts.find_one({"id": "p"})
    assert post["reactions_count"] == 1 and not post.get("comments_count")
    physical = await mongo_db.outreach_physical_requests.find_one({})
    assert physical["status"] == "resolved" and physical["original_status"] == "unknown_outcome"
    assert (await mongo_db.outreach_manual_actions.find_one({"_id": "j"}))["cleanup_complete"]


async def test_real_mongo_expiry_and_install_contend_on_one_account(mongo_db):
    await seed(mongo_db, database())
    service, job = await prepared(mongo_db)
    await asyncio.gather(service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active"}),
        service.expire(job, force=True))
    account = await mongo_db.outreach_accounts.find_one({"id": "a"})
    assert account["connection_finalization"]["state"] == "closed"
    assert not account.get("session_cookie_enc")
    assert not (await mongo_db.outreach_connection_jobs.find_one({"id": "j"})).get("li_at_enc")
    assert await mongo_db.outreach_proxy_leases.count_documents({}) == 1


async def test_real_mongo_server_deadline_blocks_delayed_final_install(mongo_db):
    await seed(mongo_db, database())
    service, job = await prepared(mongo_db)
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=80)
    await mongo_db.outreach_accounts.update_one({"id": "a"}, {"$set": {"connection_finalization.custody_expires_at": deadline}})
    await mongo_db.outreach_connection_jobs.update_one({"id": "j"}, {"$set": {"custody_expires_at": deadline}})
    class DelayedAccount:
        async def find_one(self, *args, **kwargs):
            return await mongo_db.outreach_accounts.find_one(*args, **kwargs)
        async def update_one(self, *args, **kwargs):
            await asyncio.sleep(0.15)
            return await mongo_db.outreach_accounts.update_one(*args, **kwargs)
    class DelayedDatabase:
        outreach_accounts = DelayedAccount()
        def __getattr__(self, key):
            return getattr(mongo_db, key)
    assert not await ConnectionRepair(DelayedDatabase()).install(job, "owner", "g", {"session_cookie_enc": "cached-cipher", "status": "active"})
    assert not (await mongo_db.outreach_accounts.find_one({"id": "a"})).get("session_cookie_enc")


async def test_real_mongo_index_migration_holds_a_resolving_target(mongo_db, monkeypatch):
    from db.indexes import create_all_indexes
    keys = [("workspace_id", 1), ("source", 1), ("target_id", 1)]
    await mongo_db.outreach_manual_actions.create_index(keys, unique=True, partialFilterExpression={"status": {"$in": [
        "awaiting_approval", "queued", "preparing", "in_flight", "unknown_outcome", "projection_pending"]}})
    monkeypatch.setenv("DB_NAME", mongo_db.name)
    await create_all_indexes(mongo_db.client)
    voice_indexes = await mongo_db.outreach_voice_preparation_jobs.index_information()
    assert all("expireAfterSeconds" not in index for index in voice_indexes.values())
    for keys in ([("status", 1), ("next_publish_at", 1)], [("status", 1), ("claim_expires_at", 1)],
            [("next_recovery_due_at", 1), ("_id", 1)]):
        assert any(index["key"] == keys for index in voice_indexes.values())
    assert any(index["key"] == [("expires_at", 1)] and index.get("expireAfterSeconds") == 0
        for index in (await mongo_db.outreach_voice_artifacts.index_information()).values())
    erasure_indexes = await mongo_db.outreach_erasure_requests.index_information()
    assert any(index.get("unique") and index["key"] == [("workspace_id", 1)] for index in erasure_indexes.values())
    for name in ("outreach_suppression_guards", "outreach_erasure_requests", "outreach_erasure_holds"):
        assert all("expireAfterSeconds" not in index for index in (await mongo_db[name].index_information()).values())
    assert any(index["key"] == [("status", 1), ("deletion_next_publish_at", 1)]
        for index in (await mongo_db.users.index_information()).values())
    assert "manual_active_target_v2" in await mongo_db.outreach_manual_actions.index_information()
    await mongo_db.outreach_manual_actions.insert_one({"_id": "old", "workspace_id": "w", "source": "engage", "target_id": "p", "status": "resolving"})
    candidate = {"_id": "new", "workspace_id": "w", "source": "engage", "target_id": "p", "status": "queued"}
    with pytest.raises(DuplicateKeyError):
        await mongo_db.outreach_manual_actions.insert_one(candidate)
    await mongo_db.outreach_manual_actions.update_one({"_id": "old"}, {"$set": {"status": "resolved"}})
    await mongo_db.outreach_manual_actions.insert_one(candidate)
