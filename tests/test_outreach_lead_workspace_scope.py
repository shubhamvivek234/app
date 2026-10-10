"""Lead tenant boundaries through real routes and permission dependencies.

Only authentication and database transport are replaced. Query matching and
workspace/role resolution run against synthetic rows; no provider is contacted.
"""
from copy import deepcopy

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException

from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.leads import _lead_query, router
from outreach.api.router import _open_workspace
from outreach.core.suppression import guard_scope
from outreach.core.workspace_scope import workspace_scope
from tests.outreach_memory import Collection, Cursor, Database, matches


pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER_ID = "member"
WORKSPACE = "personal-a"
FOREIGN = "former-team-b"
USER = {"user_id": USER_ID, "default_workspace_id": WORKSPACE, "workspace_ids": [WORKSPACE]}


class StreamingCursor(Cursor):
    def __aiter__(self):
        self.remaining = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return deepcopy(next(self.remaining))
        except StopIteration:
            raise StopAsyncIteration from None


class StreamingCollection(Collection):
    def find(self, query=None, projection=None):
        return StreamingCursor([row for row in self.docs if matches(row, query or {})])

    async def insert_many(self, rows):
        for row in rows:
            await self.insert_one(row)


def tenant_db(*, role="editor", lead_scope=None, campaign_scope=None):
    lead = {
        "id": "target", "workspace_id": WORKSPACE, "user_id": USER_ID,
        "first_name": "Private", "email": "private@example.invalid",
        "execution_state": "paused", "pipeline_stage": "unassigned",
    }
    if lead_scope is not None:
        lead.update(lead_scope)
        if lead_scope.get("missing_workspace"):
            lead.pop("workspace_id")
            lead.pop("missing_workspace")
    campaign = {
        "id": "campaign", "workspace_id": WORKSPACE, "user_id": USER_ID,
        "name": "Private campaign", "status": "draft", "leads_count": 1,
    }
    if campaign_scope is not None:
        campaign.update(campaign_scope)
        if campaign_scope.get("missing_workspace"):
            campaign.pop("workspace_id")
            campaign.pop("missing_workspace")
    db = Database(
        workspace_members=[{"workspace_id": WORKSPACE, "user_id": USER_ID, "role": role}],
        workspaces=[{"workspace_id": WORKSPACE, "owner_id": "another-owner"}],
        outreach_campaigns=[campaign],
        outreach_import_jobs=[],
        outreach_accounts=[],
    )
    db.collections["outreach_leads"] = StreamingCollection([lead])
    return db


def client_for(db, user=None, *, mounted=False):
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(_open_workspace)] if mounted else [])
    identity = deepcopy(USER if user is None else user)
    app.dependency_overrides[get_current_user] = lambda: identity
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


UNPROVEN_SCOPES = [
    pytest.param({"workspace_id": FOREIGN}, id="former-team"),
    pytest.param({"workspace_id": USER_ID}, id="implicit-uid-workspace"),
    pytest.param({"workspace_id": None}, id="null-scope"),
    pytest.param({"missing_workspace": True}, id="missing-scope"),
    pytest.param({"workspace_id": [WORKSPACE, FOREIGN]}, id="ambiguous-array-scope"),
]


@pytest.mark.parametrize("scope", UNPROVEN_SCOPES)
async def test_list_and_export_exclude_foreign_and_unproven_creator_rows(scope):
    db = tenant_db(lead_scope=scope)
    await db.outreach_leads.insert_one({
        "id": "current", "workspace_id": WORKSPACE, "user_id": "other-creator",
        "first_name": "Current", "email": "current@example.invalid",
    })
    async with client_for(db) as client:
        listed = await client.get("/leads")
        exported = await client.get("/leads/export")
    assert listed.status_code == exported.status_code == 200
    assert listed.json()["total"] == 1
    assert [row["id"] for row in listed.json()["leads"]] == ["current"]
    assert "current@example.invalid" in exported.text
    assert "private@example.invalid" not in exported.text


@pytest.mark.parametrize("scope", UNPROVEN_SCOPES)
@pytest.mark.parametrize("method,path,body", [
    ("GET", "/leads/target/activity", None),
    ("PATCH", "/leads/target/stage", {"pipeline_stage": "replied"}),
    ("POST", "/leads/target/notes", {"note": "foreign note"}),
    ("POST", "/leads/target/pause", {}),
    ("POST", "/leads/target/resume", None),
    ("DELETE", "/leads/target", None),
])
async def test_foreign_and_unproven_lead_ids_cannot_be_read_or_mutated(scope, method, path, body):
    db = tenant_db(lead_scope=scope)
    before = deepcopy(db.outreach_leads.docs)
    async with client_for(db) as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 404
    assert db.outreach_leads.docs == before
    assert db.outreach_lead_notes.docs == []
    assert db.outreach_tasks.docs == []


@pytest.mark.parametrize("scope", UNPROVEN_SCOPES)
async def test_campaign_creator_does_not_authorize_filter_or_intake(scope):
    db = tenant_db(campaign_scope=scope)
    async with client_for(db) as client:
        listed = await client.get("/leads?campaign_id=campaign")
        exported = await client.get("/leads/export?campaign_id=campaign")
        preview = await client.post("/leads/preview", json={
            "campaign_id": "campaign", "raw_text": "LinkedIn URL\nhttps://linkedin.com/in/person",
        })
    assert listed.status_code == exported.status_code == preview.status_code == 404


@pytest.mark.parametrize("path", ["/leads", "/leads/export", "/leads/target/activity", "/leads/do-not-contact"])
async def test_reads_resolve_revoked_membership_before_access(path):
    db = tenant_db()
    db.workspace_members.docs.clear()
    # The standard permission dependency creates a personal workspace for this
    # authenticated user; it must not retain access to the revoked workspace.
    async with client_for(db) as client:
        response = await client.get(path)
    assert response.status_code == (404 if "activity" in path else 200)
    assert "private@example.invalid" not in response.text


@pytest.mark.parametrize("path", ["/leads", "/leads/export", "/leads/target/activity", "/leads/do-not-contact"])
async def test_read_dependency_resolves_stale_foreign_workspace_before_resource_scope(path):
    db = tenant_db(lead_scope={"workspace_id": FOREIGN})
    stale = {"user_id": USER_ID, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    await db.outreach_do_not_contact.insert_one({"workspace_id": FOREIGN, "email": "private@example.invalid"})
    async with client_for(db, stale) as client:
        response = await client.get(path)
    assert response.status_code == (404 if "activity" in path else 200)
    assert "private@example.invalid" not in response.text


async def test_mutation_consumes_same_resolved_workspace_as_permission_check():
    db = tenant_db(lead_scope={"workspace_id": FOREIGN})
    stale = {"user_id": USER_ID, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    before = deepcopy(db.outreach_leads.docs)
    async with client_for(db, stale) as client:
        response = await client.patch("/leads/target/stage", json={"pipeline_stage": "replied"})
    assert response.status_code == 404
    assert db.outreach_leads.docs == before


async def test_viewer_can_read_current_rows_but_not_change_them():
    db = tenant_db(role="viewer")
    async with client_for(db) as client:
        listed = await client.get("/leads")
        changed = await client.patch("/leads/target/stage", json={"pipeline_stage": "replied"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert changed.status_code == 403


@pytest.mark.parametrize("method,path,body", [
    ("PATCH", "/leads/target/stage", {"pipeline_stage": "replied"}),
    ("POST", "/leads/target/notes", {"note": "Current workspace note"}),
    ("POST", "/leads/target/pause", {}),
    ("POST", "/leads/target/resume", None),
    ("DELETE", "/leads/target", None),
])
async def test_current_editor_mutations_preserve_foreign_rows_with_the_same_id(method, path, body):
    db = tenant_db()
    foreign_row = {"id": "target", "workspace_id": FOREIGN, "user_id": USER_ID, "execution_state": "paused"}
    db.outreach_leads.docs.insert(0, deepcopy(foreign_row))
    async with client_for(db) as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 200
    assert await db.outreach_leads.find_one({"id": "target", "workspace_id": FOREIGN}) == foreign_row
    if "notes" in path:
        assert db.outreach_lead_notes.docs[0]["workspace_id"] == WORKSPACE


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/leads", None),
    ("PATCH", "/leads/target/stage", {"pipeline_stage": "replied"}),
])
async def test_resolved_workspace_erasure_hold_is_checked_after_permission(method, path, body):
    db = tenant_db()
    await db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), "erasure_state": "stopped"})
    stale = {"user_id": USER_ID, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    before = deepcopy(db.outreach_leads.docs)
    async with client_for(db, stale, mounted=True) as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 409
    assert db.outreach_leads.docs == before


async def test_explicit_uid_workspace_is_supported_when_it_is_actually_active():
    db = tenant_db(lead_scope={"workspace_id": USER_ID})
    await db.workspace_members.insert_one({"workspace_id": USER_ID, "user_id": USER_ID, "role": "editor"})
    async with client_for(db, {"user_id": USER_ID, "default_workspace_id": USER_ID}) as client:
        response = await client.patch("/leads/target/stage", json={"pipeline_stage": "replied"})
    assert response.status_code == 200
    assert db.outreach_leads.docs[0]["pipeline_stage"] == "replied"


async def test_activity_never_opens_foreign_sender_or_campaign_references():
    db = tenant_db(campaign_scope={"workspace_id": FOREIGN})
    await db.outreach_leads.update_one({"id": "target"}, {"$set": {
        "campaign_id": "campaign", "assigned_account_id": "sender",
    }})
    await db.outreach_accounts.insert_one({"id": "sender", "workspace_id": FOREIGN, "account_name": "Private sender"})
    async with client_for(db) as client:
        response = await client.get("/leads/target/activity")
    assert response.status_code == 200
    assert response.json()["lead"]["campaign_name"] is None
    assert response.json()["lead"]["assigned_sender_name"] is None


async def test_cancel_and_staged_commit_do_not_write_id_collisions_in_another_workspace():
    db = tenant_db()
    await db.outreach_import_jobs.insert_one({
        "id": "job", "workspace_id": FOREIGN, "campaign_id": "campaign", "status": "queued",
    })
    await db.outreach_import_jobs.insert_one({
        "id": "job", "workspace_id": WORKSPACE, "campaign_id": "campaign", "status": "queued",
    })
    await db.outreach_campaigns.insert_one({
        "id": "campaign", "workspace_id": FOREIGN, "leads_count": 10,
    })
    for scope in (FOREIGN, WORKSPACE):
        await db.outreach_leads.insert_one({
            "id": "staged", "workspace_id": scope, "import_job_id": "job",
            "execution_state": "staged", "first_name": "Original",
        })
    async with client_for(db) as client:
        cancelled = await client.post("/leads/import-jobs/job/cancel")
        committed = await client.post("/leads/import-jobs/job/commit", json={"name_overrides": {"staged": "Edited"}})
    assert cancelled.status_code == committed.status_code == 200
    foreign_job = await db.outreach_import_jobs.find_one({"id": "job", "workspace_id": FOREIGN})
    foreign_lead = await db.outreach_leads.find_one({"id": "staged", "workspace_id": FOREIGN})
    foreign_campaign = await db.outreach_campaigns.find_one({"id": "campaign", "workspace_id": FOREIGN})
    assert foreign_job["status"] == "queued"
    assert foreign_lead["first_name"] == "Original"
    assert foreign_lead["execution_state"] == "staged"
    assert foreign_campaign["leads_count"] == 10
    current_lead = await db.outreach_leads.find_one({"id": "staged", "workspace_id": WORKSPACE})
    assert current_lead["first_name"] == "Edited"
    assert current_lead["execution_state"] == "queued"


async def test_staged_commit_requires_current_workspace_campaign_before_any_write():
    db = tenant_db(campaign_scope={"workspace_id": FOREIGN})
    await db.outreach_import_jobs.insert_one({"id": "job", "workspace_id": WORKSPACE, "campaign_id": "campaign"})
    await db.outreach_leads.insert_one({
        "id": "staged", "workspace_id": WORKSPACE, "import_job_id": "job",
        "execution_state": "staged", "first_name": "Original",
    })
    before = deepcopy(db.outreach_leads.docs)
    async with client_for(db) as client:
        response = await client.post("/leads/import-jobs/job/commit", json={"name_overrides": {"staged": "Edited"}})
    assert response.status_code == 404
    assert db.outreach_leads.docs == before


@pytest.mark.parametrize("path,payload", [
    ("/leads/import-urls", {"urls_text": "https://linkedin.com/in/alice, Alice"}),
    ("/leads/import-csv", {"csv_text": "LinkedIn URL,First Name\nhttps://linkedin.com/in/alice,Alice"}),
])
async def test_common_importer_updates_only_the_authorized_campaign_count(path, payload):
    db = tenant_db()
    db.outreach_campaigns.docs.insert(0, {"id": "campaign", "workspace_id": FOREIGN, "leads_count": 10})
    async with client_for(db) as client:
        response = await client.post(path, json={"campaign_id": "campaign", **payload})
    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    assert (await db.outreach_campaigns.find_one({"id": "campaign", "workspace_id": FOREIGN}))["leads_count"] == 10
    assert (await db.outreach_campaigns.find_one({"id": "campaign", "workspace_id": WORKSPACE}))["leads_count"] == 2


async def test_import_job_with_ambiguous_workspace_scope_is_inaccessible():
    db = tenant_db()
    await db.outreach_import_jobs.insert_one({
        "id": "job", "workspace_id": [WORKSPACE, FOREIGN], "campaign_id": "campaign", "status": "queued",
    })
    async with client_for(db) as client:
        read = await client.get("/leads/import-jobs/job")
        cancel = await client.post("/leads/import-jobs/job/cancel")
        commit = await client.post("/leads/import-jobs/job/commit")
    assert read.status_code == cancel.status_code == commit.status_code == 404
    assert db.outreach_import_jobs.docs[0]["status"] == "queued"


@pytest.mark.parametrize("context", [
    {}, {"default_workspace_id": ""}, {"default_workspace_id": "   "},
    {"default_workspace_id": 123}, {"default_workspace_id": [WORKSPACE, FOREIGN]},
])
async def test_direct_query_without_workspace_context_denies_instead_of_guessing_ownership(context):
    with pytest.raises(HTTPException) as exc:
        await _lead_query(None, None, None, None, None, {"user_id": USER_ID, **context}, tenant_db())
    assert exc.value.status_code == 403


@pytest.mark.parametrize("identity", [None, "", "   ", 123, [WORKSPACE, FOREIGN]])
async def test_shared_scope_rejects_invalid_caller_identity(identity):
    with pytest.raises(ValueError):
        workspace_scope(identity)
