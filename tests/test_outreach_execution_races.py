"""Races at inbox suppression, human review, recovery, and scheduler boundaries."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action
from outreach.core.execution_recovery import recover_intent
from tests.test_outreach_execution_outbox import execution_db, stub_transport
from tests.test_outreach_execution_recovery import interrupted_db
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_inbox_suppresses_all_same_sender_enrollments_and_preserves_other_sender(monkeypatch):
    from outreach.engine import inbox_sync
    db = execution_db()
    for lead in db.outreach_leads.docs:
        lead["linkedin_urn"] = "urn:recipient"
    await db.outreach_leads.insert_one({"id": "second", "workspace_id": "w", "campaign_id": "second-campaign",
                                       "assigned_account_id": "a", "linkedin_urn": "urn:recipient", "execution_state": "queued"})
    await db.outreach_leads.insert_one({"id": "other-sender", "workspace_id": "w", "campaign_id": "third-campaign",
                                       "assigned_account_id": "b", "linkedin_urn": "urn:recipient", "execution_state": "queued"})
    page = [{"lead_urn": "urn:recipient", "thread_urn": "urn:conversation", "lead_name": "Prospect",
             "messages": [{"sender_type": "lead", "body": "Thanks"}]}]
    transport = type("Transport", (), {"fetch_conversations": AsyncMock(return_value=page)})()
    monkeypatch.setattr(inbox_sync, "VoyagerClient", lambda **kwargs: transport)
    monkeypatch.setattr(inbox_sync, "sender_is_ready", AsyncMock(return_value=True))
    result = await inbox_sync.InboxSynchronizer(db, "w").sync_account_inbox("a")
    assert result["coverage_complete"]
    assert (await db.outreach_leads.find_one({"id": "l"}))["has_replied"]
    assert (await db.outreach_leads.find_one({"id": "second"}))["has_replied"]
    assert not (await db.outreach_leads.find_one({"id": "other-sender"})).get("has_replied")
    assert (await db.outreach_inbox_threads.find_one({"account_id": "a"}))["has_lead_reply"]


@pytest.mark.asyncio
async def test_existing_sender_recipient_reply_blocks_later_import(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    db.outreach_leads.docs[0]["linkedin_urn"] = "urn:recipient"
    await db.outreach_inbox_threads.insert_one({"workspace_id": "w", "account_id": "a", "lead_urn": "urn:recipient", "has_lead_reply": True})
    assert (await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w"))["status"] == "lead_suppressed"
    client.send_direct_message.assert_not_awaited()
    assert not db.outreach_intents.docs


async def review_db(outcome="unknown_outcome"):
    db, key = await interrupted_db()
    await db.outreach_campaigns.update_one({"id": "c"}, {"$set": {"status": "paused", "authorization_revision": 3}})
    await db.outreach_leads.update_one({"id": "l"}, {"$set": {"execution_state": "waiting_trigger"}})
    await db.outreach_tasks.update_one({"id": "l:n"}, {"$set": {"status": "uncertain", "account_id": "a", "task_type": "send_message"}})
    await db.outreach_intents.update_one({"_id": key}, {"$set": {
        "status": "executed" if outcome == "provider_accepted" else "unknown_outcome", "attempt.outcome": outcome}})
    return db, key


USER = {"user_id": "admin", "default_workspace_id": "w"}


def decision(value):
    return ResolutionRequest(decision=value, evidence_note="Verified the provider conversation and saved the evidence", acknowledged=True)


@pytest.mark.asyncio
async def test_rejected_stop_does_not_latch_review_decision():
    db, key = await review_db("provider_accepted")
    with pytest.raises(HTTPException) as exc:
        await resolve_uncertain_action("l:n", decision("not_sent_stop"), current_user=USER, db=db)
    assert exc.value.status_code == 409
    assert (await db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "uncertain"
    assert (await resolve_uncertain_action("l:n", decision("confirmed_sent"), current_user=USER, db=db))["status"] == "completed"
    assert (await db.outreach_intents.find_one({"_id": key}))["attempt"]["outcome"] == "provider_accepted"


@pytest.mark.asyncio
async def test_late_provider_evidence_refuses_stop_and_allows_correct_review(monkeypatch):
    db, key = await review_db()
    claim = db.outreach_tasks.find_one_and_update

    async def claim_then_accept(*args, **kwargs):
        result = await claim(*args, **kwargs)
        await db.outreach_intents.update_one({"_id": key}, {"$set": {"status": "executed", "attempt.outcome": "provider_accepted"}})
        return result

    monkeypatch.setattr(db.outreach_tasks, "find_one_and_update", claim_then_accept)
    with pytest.raises(HTTPException):
        await resolve_uncertain_action("l:n", decision("not_sent_stop"), current_user=USER, db=db)
    task = await db.outreach_tasks.find_one({"id": "l:n"})
    assert task["status"] == "uncertain" and not task.get("resolution")
    assert task["refused_resolutions"][0]["decision"] == "not_sent_stop"
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "waiting_trigger"
    monkeypatch.setattr(db.outreach_tasks, "find_one_and_update", claim)
    assert (await resolve_uncertain_action("l:n", decision("confirmed_sent"), current_user=USER, db=db))["status"] == "completed"


@pytest.mark.asyncio
async def test_old_recovery_snapshot_cannot_undo_human_resolution_or_resume():
    db, key = await review_db()
    old = await db.outreach_intents.find_one({"_id": key})
    await resolve_uncertain_action("l:n", decision("confirmed_sent"), current_user=USER, db=db)
    assert (await db.outreach_leads.find_one({"id": "l"}))["authorized_revision"] == 3
    await db.outreach_campaigns.update_one({"id": "c"}, {"$set": {"status": "active", "authorization_revision": 4}})
    await db.outreach_leads.update_one({"id": "l"}, {"$set": {"authorized_revision": 4}})
    assert await recover_intent(db, old) == "unchanged"
    assert (await db.outreach_campaigns.find_one({"id": "c"}))["status"] == "active"
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "queued"


@pytest.mark.asyncio
async def test_scheduler_cannot_undo_manual_pause_during_request_deferral(monkeypatch):
    from celery_workers.tasks import outreach as worker
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    monkeypatch.setenv("DB_NAME", "isolated")
    monkeypatch.setattr(worker, "get_client", AsyncMock(return_value={"isolated": db}))
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)

    async def request_denial_then_pause(*args, **kwargs):
        await db.outreach_leads.update_one({"id": "l"}, {"$set": {"execution_state": "waiting_trigger", "next_action_due_at": None}})
        return {"status": "physical_action_cap", "not_submitted": True}

    monkeypatch.setattr(executor, "_dispatch_action", request_denial_then_pause)
    from outreach.tasks.sequence_dispatch import execute_job
    assert (await worker._run_due_steps())["prepared"] == 1
    result = await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"])
    assert result["not_submitted"]
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "waiting_trigger"
    client.send_direct_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("paused_state", ["paused", "waiting_trigger"])
async def test_paused_condition_branch_cannot_requeue_lead(monkeypatch, paused_state):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    db.outreach_leads.docs[0].update({"execution_state": paused_state, "waiting_for_connection_at": datetime.now(timezone.utc)})
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"].update({"type": "if_connected", "branches": {"positive": "end"}})
    assert (await executor.SequenceExecutor.execute_lead_step("l", db))["status"] == "terminal_state"
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == paused_state


@pytest.mark.asyncio
async def test_older_sync_cannot_clear_newer_reply_authority_or_messages(monkeypatch):
    from outreach.engine import inbox_sync
    db = execution_db()
    await db.outreach_inbox_threads.insert_one({"id": "t", "workspace_id": "w", "account_id": "a",
                                               "lead_urn": "urn:recipient", "has_lead_reply": False,
                                               "thread_revision": 1, "messages": [{"sender_type": "user", "body": "old"}]})
    read = db.outreach_inbox_threads.find_one

    async def read_then_newer_reply(query, *args):
        old = await read(query, *args)
        await db.outreach_inbox_threads.update_one({"id": "t"}, {
            "$set": {"has_lead_reply": True, "messages": [{"sender_type": "lead", "body": "new reply"}]},
            "$inc": {"thread_revision": 1}})
        return old

    monkeypatch.setattr(db.outreach_inbox_threads, "find_one", read_then_newer_reply)
    page = [{"lead_urn": "urn:recipient", "thread_urn": "urn:conversation",
             "messages": [{"sender_type": "user", "body": "old"}]}]
    transport = type("Transport", (), {"fetch_conversations": AsyncMock(return_value=page)})()
    monkeypatch.setattr(inbox_sync, "VoyagerClient", lambda **kwargs: transport)
    monkeypatch.setattr(inbox_sync, "sender_is_ready", AsyncMock(return_value=True))
    result = await inbox_sync.InboxSynchronizer(db, "w").sync_account_inbox("a")
    assert not result["coverage_complete"]
    stored = await read({"id": "t"})
    assert stored["has_lead_reply"] and stored["messages"][0]["body"] == "new reply"
