"""Real-database closure of unverified search collection/promotion paths."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from outreach.api import leads
from outreach.core.lead_importer import LeadImporter
from outreach.core.lead_selection import selection_preview, create_selection_draft
from outreach.models import OutreachLead
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo is opt-in")]
USER = {"user_id": "actor", "default_workspace_id": "w"}
URL = "https://www.linkedin.com/search/results/people/?keywords=CEO"


async def seed(db, *, state="staged", marker="job"):
    await db.outreach_campaigns.insert_one({"id": "campaign", "workspace_id": "w", "status": "draft", "leads_count": 0})
    await db.outreach_import_jobs.insert_one({"id": "job", "workspace_id": "w", "campaign_id": "campaign",
        "sender_account_id": "sender", "search_url": URL, "status": "queued", "cursor": 0,
        "lease_token": "lease", "page_owner_token": None})
    record = OutreachLead(workspace_id="w", campaign_id="campaign", linkedin_url="https://linkedin.com/in/person").model_dump()
    record.update(id="lead", execution_state=state, import_job_id=marker)
    await db.outreach_leads.insert_one(record)


@pytest.mark.parametrize("live,mock", [("false", "false"), ("true", "false"), ("true", "true")])
async def test_http_collection_denies_with_flags_and_preserves_state(replica_db, monkeypatch, live, mock):
    from fastapi import FastAPI
    import httpx
    from api.deps import get_current_user
    from db.mongo import get_db
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", live)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", mock)
    await seed(replica_db)
    await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": "editor"})
    app = FastAPI(); app.include_router(leads.router)
    app.dependency_overrides[get_current_user] = lambda: dict(USER)
    app.dependency_overrides[get_db] = lambda: replica_db
    paid = AsyncMock(side_effect=AssertionError("No paid/provider setup on unavailable source"))
    monkeypatch.setattr(leads, "get_active_entitlement", paid)
    before = await replica_db.outreach_import_jobs.find({}).to_list(10)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        catalog = await client.get("/leads/import-sources")
        assert catalog.status_code == 200
        assert all(not row["collection_available"] for row in catalog.json()["sources"])
        response = await client.post("/leads/import-search", json={"campaign_id": "campaign", "search_url": URL, "sender_account_id": "sender"})
        assert response.status_code == 501
    paid.assert_not_awaited()
    assert await replica_db.outreach_import_jobs.find({}).to_list(10) == before


async def test_worker_stops_only_owned_job_before_opening_credentials(replica_db, monkeypatch):
    from celery_workers.tasks import outreach as worker
    await seed(replica_db)
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    material = AsyncMock(side_effect=AssertionError("Credential opening must not occur"))
    monkeypatch.setattr(worker, "account_session", material)
    before = await replica_db.outreach_leads.find({}).to_list(10)
    result = await worker._crawl_page("job", 0, "lease", db=replica_db)
    assert result["reason"] == "search_source_review_required" and result["status"] == "stopped"
    job = await replica_db.outreach_import_jobs.find_one({"id": "job"})
    assert job["stop_reason"] == "search_source_review_required"
    assert await replica_db.outreach_leads.find({}).to_list(10) == before
    material.assert_not_awaited()


async def test_stale_worker_cannot_stop_replacement_owner(replica_db, monkeypatch):
    from celery_workers.tasks import outreach as worker
    await seed(replica_db)
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    await replica_db.outreach_import_jobs.update_one({"id": "job"}, {"$set": {"lease_token": "replacement"}})
    before = await replica_db.outreach_import_jobs.find_one({"id": "job"})
    assert (await worker._crawl_page("job", 0, "lease", db=replica_db))["status"] == "job_not_found_or_cancelled"
    assert await replica_db.outreach_import_jobs.find_one({"id": "job"}) == before


async def test_search_commit_preserves_unverified_staged_records(replica_db):
    await seed(replica_db)
    before = await replica_db.outreach_leads.find({}).to_list(10)
    with pytest.raises(HTTPException) as failure:
        await leads.commit_staged_leads("job", None, current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find({}).to_list(10) == before


@pytest.mark.parametrize("payload", ["markers", "known_id", "renamed_state"])
async def test_generic_intake_cannot_strip_known_search_provenance(replica_db, payload):
    await seed(replica_db, state="paused" if payload == "renamed_state" else "staged")
    row = {"linkedin_url": "https://linkedin.com/in/person", "first_name": "Person"}
    if payload == "markers": row["import_job_id"] = "job"
    else: row["id"] = "lead"
    before = await replica_db.outreach_leads.find({}).to_list(10)
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([row], "campaign", "w", replica_db, source="staged_preview")
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find({}).to_list(10) == before


async def test_duplicate_ordinary_ids_do_not_hide_known_search_source(replica_db):
    await seed(replica_db)
    ordinary = OutreachLead(workspace_id="w", campaign_id="campaign", linkedin_url="https://linkedin.com/in/manual").model_dump()
    ordinary["id"] = "lead"
    await replica_db.outreach_leads.insert_many([deepcopy(ordinary) for _ in range(5)])
    with pytest.raises(HTTPException):
        await LeadImporter.ingest_leads([{"id": "lead", "linkedin_url": "https://linkedin.com/in/new"}], "campaign", "w", replica_db)


@pytest.mark.parametrize("state", ["staged", "paused", "queued"])
async def test_reviewed_draft_and_resume_preserve_search_hold(replica_db, state):
    await seed(replica_db, state=state)
    preview = await selection_preview(replica_db, "w", ["lead"], True)
    assert preview["valid_count"] == 0 and preview["rows"][0]["rejection_code"] == "search_source_unverified"
    with pytest.raises(HTTPException):
        await create_selection_draft(replica_db, "w", "actor", ["lead"], True, "Next", "request", preview["review_digest"])
    with pytest.raises(HTTPException) as failure:
        await leads.resume_lead("lead", current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_campaigns.count_documents({}) == 1


async def test_manual_csv_and_modeled_null_markers_remain_usable(replica_db):
    await seed(replica_db, state="queued", marker=None)
    preview = await selection_preview(replica_db, "w", ["lead"], False)
    assert preview["valid_count"] == 1
    result = await LeadImporter.ingest_leads([{"linkedin_url": "https://linkedin.com/in/manual", "first_name": "Manual"}], "campaign", "w", replica_db)
    assert result["imported_count"] == 1


@pytest.mark.parametrize("change", [{"source": ["csv", "linkedin_search"]},
    {"source_metadata": ["linkedin_search"]}, {"source_metadata": {"source_type": ["csv", "linkedin_search"]}},
    {"execution_state": ["queued"]}, {"import_job_id": False}, {"staged_at": []}])
async def test_malformed_source_markers_cannot_be_normalized_into_enrollment(replica_db, change):
    await seed(replica_db, state="queued", marker=None)
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([{"linkedin_url": "https://linkedin.com/in/new", **change}], "campaign", "w", replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.count_documents({}) == 1
    await replica_db.outreach_leads.update_one({"id": "lead"}, {"$set": change})
    with pytest.raises(HTTPException) as known:
        await LeadImporter.ingest_leads([{"id": "lead", "linkedin_url": "https://linkedin.com/in/new"}], "campaign", "w", replica_db)
    assert known.value.status_code == 409


async def test_readiness_and_dispatch_reject_known_search_sources(replica_db, monkeypatch):
    from tests.test_outreach_campaign_readiness_mongo import seed as ready_seed, preflight
    from outreach.core.authorization import dispatch_block_reason
    await ready_seed(replica_db)
    await replica_db.outreach_leads.update_one({"id": "lead"}, {"$set": {"import_job_id": "old-search", "execution_state": "queued"}})
    report = await preflight(replica_db)
    source = next(check for check in report["checklist"] if check["id"] == "lead_sources")
    assert not source["passed"] and not report["can_launch"]
    expected = {"workspace_id": "workspace", "campaign_id": "campaign"}
    assert dispatch_block_reason({"workspace_id": "workspace", "import_job_id": "old-search"},
        {"workspace_id": "workspace"}, {"workspace_id": "workspace"}, {"workspace_id": "workspace"}, expected) == "search_source_review_required"


@pytest.mark.parametrize("state", ["staged", ["queued"], ["staged"], {"state": "queued"}, False])
async def test_pause_cannot_erase_only_unverified_state_marker(replica_db, state):
    await seed(replica_db, state=state, marker=None)
    original = await replica_db.outreach_leads.find_one({"id": "lead"})
    with pytest.raises(HTTPException) as failure:
        await leads.pause_lead("lead", leads.PauseLeadRequest(), current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    with pytest.raises(HTTPException):
        await leads.resume_lead("lead", current_user=USER, db=replica_db)
    assert await replica_db.outreach_leads.find_one({"id": "lead"}) == original


@pytest.mark.parametrize("operation", ["pause", "resume"])
async def test_concurrent_state_marker_is_not_normalized_away(replica_db, operation):
    await seed(replica_db, state="queued" if operation == "pause" else "paused", marker=None)
    collection = replica_db.outreach_leads
    class ChangedAfterRead:
        async def find_one(self, query):
            captured = await collection.find_one(query)
            await collection.update_one({"id": "lead"}, {"$set": {"execution_state": ["queued"]}})
            return captured
        async def update_one(self, query, update):
            return await collection.update_one(query, update)
    wrapper = SimpleNamespace(outreach_leads=ChangedAfterRead())
    with pytest.raises(HTTPException) as failure:
        if operation == "pause":
            await leads.pause_lead("lead", leads.PauseLeadRequest(), current_user=USER, db=wrapper)
        else:
            await leads.resume_lead("lead", current_user=USER, db=wrapper)
    assert failure.value.status_code == 409
    assert (await collection.find_one({"id": "lead"}))["execution_state"] == ["queued"]


@pytest.mark.parametrize("change", [{"execution_state": ["queued"]}, {"import_job_id": "old-job"},
    {"source_metadata": {"source_type": "linkedin_search"}}])
async def test_nonphysical_sequence_steps_preserve_source_hold(replica_db, monkeypatch, change):
    from outreach.tasks import sequence_executor as executor
    await seed(replica_db, state="queued", marker=None)
    await replica_db.outreach_leads.update_one({"id": "lead"}, {"$set": change})
    monkeypatch.setattr(executor, "validate_dispatch_context", AsyncMock(return_value=None))
    opening = AsyncMock(side_effect=AssertionError("Source review must precede credential preparation"))
    monkeypatch.setattr(executor, "account_session", opening)
    original = await replica_db.outreach_leads.find_one({"id": "lead"})
    result = await executor.SequenceExecutor._execute_lead_step("lead", replica_db, workspace_id="w")
    assert result == {"status": "search_source_review_required", "not_submitted": True}
    assert not await executor._advance_lead(replica_db, original, {"execution_state": "queued"})
    assert await replica_db.outreach_leads.find_one({"id": "lead"}) == original
    opening.assert_not_awaited()


async def test_sequence_advancement_cas_rejects_new_source_marker(replica_db, monkeypatch):
    from outreach.tasks import sequence_executor as executor
    await seed(replica_db, state="queued", marker=None)
    captured = await replica_db.outreach_leads.find_one({"id": "lead"})
    await replica_db.outreach_leads.update_one({"id": "lead"}, {"$set": {"execution_state": ["queued"]}})
    monkeypatch.setattr(executor, "validate_dispatch_context", AsyncMock(return_value=None))
    assert not await executor._advance_lead(replica_db, captured, {"execution_state": "finished"})
    assert (await replica_db.outreach_leads.find_one({"id": "lead"}))["execution_state"] == ["queued"]


@pytest.mark.parametrize("state", [["queued"], "staged"])
async def test_public_pause_cannot_remove_source_review(replica_db, state):
    from outreach.api.integrations import public_pause_lead
    await seed(replica_db, state=state, marker=None)
    original = await replica_db.outreach_leads.find_one({"id": "lead"})
    with pytest.raises(HTTPException) as failure:
        await public_pause_lead("lead", auth={"workspace_id": "w"}, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find_one({"id": "lead"}) == original


async def reply_seed(db):
    await seed(db, state=["queued"], marker=None)
    await db.outreach_leads.update_one({"id": "lead"}, {"$set": {"assigned_account_id": "sender"}})
    for identity, workspace, profile in [("other", "w", "person"), ("foreign", "foreign", "person"),
                                         ("unrelated", "w", "unrelated")]:
        await db.outreach_leads.insert_one({"id": identity, "workspace_id": workspace,
            "campaign_id": "campaign", "assigned_account_id": "sender", "execution_state": ["queued"],
            "linkedin_url": "https://linkedin.com/in/" + profile})


async def test_linkedin_reply_keeps_source_hold_and_actual_reply_evidence(replica_db):
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.search_sources import unverified_search_lead
    await reply_seed(replica_db)
    result = await InboxSynchronizer(replica_db, "w").persist_conversation("sender", {
        "lead_urn": "urn:li:member:person", "thread_urn": "urn:thread:source-review",
        "lead_profile_url": "https://www.linkedin.com/in/person",
        "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    assert result["new_replies_detected"] == 1
    for identity in ("lead", "other"):
        row = await replica_db.outreach_leads.find_one({"id": identity})
        assert row["has_replied"] and row["execution_state"] == "replied"
        assert row["search_source_review_required"] is True and unverified_search_lead(row)
    for identity in ("foreign", "unrelated"):
        row = await replica_db.outreach_leads.find_one({"id": identity})
        assert row["execution_state"] == ["queued"] and "search_source_review_required" not in row
    assert (await replica_db.outreach_campaigns.find_one({"id": "campaign"}))["replies_count"] == 1


@pytest.mark.parametrize("kind", ["reply", "possible", "bounce"])
async def test_email_stop_projection_retains_source_review(replica_db, kind):
    from outreach.core.mailbox_sync import _apply_inbound
    from outreach.core.search_sources import unverified_search_lead
    await reply_seed(replica_db)
    now = datetime.now(timezone.utc)
    await replica_db.outreach_email_operations.insert_one({"workspace_id": "w", "sender_account_id": "sender",
        "lead_id": "lead", "campaign_id": "campaign", "status": "accepted", "recipient": "person@example.com",
        "message_id": "<original@unravler>", "accepted_at": now - timedelta(minutes=1)})
    mailbox = {"workspace_id": "w", "sender_account_id": "sender", "email": "sender@example.com"}
    message = {"in_reply_to": "<original@unravler>"} if kind == "reply" else {}
    result = await _apply_inbound(replica_db, mailbox, "event", "person@example.com", now, message,
        kind="bounce" if kind == "bounce" else "reply")
    row = await replica_db.outreach_leads.find_one({"id": "lead"})
    assert result["status"] == {"reply": "reply", "possible": "possible_reply", "bounce": "bounce"}[kind]
    assert row["execution_state"] == {"reply": "replied", "possible": "waiting_trigger", "bounce": "bounced"}[kind]
    assert row["search_source_review_required"] is True and unverified_search_lead(row)
    assert await replica_db.outreach_email_suppressions.count_documents({"workspace_id": "w"}) == 1


async def test_reply_failure_rolls_back_source_latch_with_evidence(replica_db, monkeypatch):
    from outreach.core.suppression import SuppressionCollection
    from outreach.engine.inbox_sync import InboxSynchronizer
    await reply_seed(replica_db)
    update = SuppressionCollection.update_one
    async def fail_lead(self, query, changes, **kwargs):
        if self.collection.name == "outreach_leads":
            raise RuntimeError("Synthetic reply projection failure")
        return await update(self, query, changes, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", fail_lead)
    with pytest.raises(RuntimeError):
        await InboxSynchronizer(replica_db, "w").persist_conversation("sender", {
            "lead_urn": "urn:li:member:person", "thread_urn": "urn:thread:source-review",
            "lead_profile_url": "https://www.linkedin.com/in/person",
            "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    assert await replica_db.outreach_inbox_threads.count_documents({}) == 0
    for identity in ("lead", "other"):
        row = await replica_db.outreach_leads.find_one({"id": identity})
        assert row["execution_state"] == ["queued"] and "search_source_review_required" not in row


async def test_received_receipt_repairs_reporting_without_erasing_source_hold(replica_db):
    from outreach.core.execution_recovery import recover_intent
    await seed(replica_db, state=["waiting_trigger"], marker=None)
    await replica_db.outreach_leads.update_one({"id": "lead"}, {"$set": {"current_node_id": "node", "authorized_revision": 1}})
    intent = {"_id": "intent", "workspace_id": "w", "status": "executed", "action_kind": "send_email",
        "legacy_operation_id": "operation", "lead_id": "lead", "campaign_id": "campaign", "node_id": "node",
        "authorization_revision": 1, "sender_id": "sender", "claim_token": "owner", "attempt": {"outcome": "provider_accepted"}}
    await replica_db.outreach_intents.insert_one(intent)
    await replica_db.outreach_tasks.insert_one({"id": "operation", "workspace_id": "w", "intent_id": "intent", "status": "accepted"})
    assert await recover_intent(replica_db, intent) == "repaired"
    assert (await replica_db.outreach_leads.find_one({"id": "lead"}))["execution_state"] == ["waiting_trigger"]
    assert (await replica_db.outreach_intents.find_one({"_id": "intent"}))["projection_reconciled"] is True
