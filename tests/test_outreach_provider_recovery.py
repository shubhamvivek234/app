"""Full sequence handoff -> provider receipt -> local repair, without HTTP replay."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from outreach.core.execution_recovery import recover_intent
from outreach.core.sender_execution import SenderExecution
from outreach.tasks.sequence_dispatch import prepare_due, execute_job
from tests.test_outreach_mailboxes import _provider_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["email_send", "email_find"])
async def test_sequence_provider_receipt_repairs_unknown_logical_projection_and_keeps_pause(monkeypatch, source):
    from outreach.tasks import sequence_executor, sequence_dispatch
    response = httpx.Response(200, json={"id": "m"}) if source == "email_send" else httpx.Response(200, json={"data": {
        "email": "found@example.com", "source_type": "found", "verification": {"status": "valid"}}})
    db, binding, transport = await _provider_fixture(monkeypatch, response, source=source)
    await SenderExecution(db).release("w", "a", "owner")
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    monkeypatch.setattr(sequence_dispatch, "sequence_dispatch_enabled", lambda: True)
    monkeypatch.setattr(sequence_executor, "get_active_entitlement", AsyncMock(return_value={"status": "active"}))
    monkeypatch.setattr(sequence_executor.OutboundRateLimiter, "is_within_working_hours", lambda *args: True)
    monkeypatch.setattr("outreach.core.mailbox_connection.get_ready_mailbox", AsyncMock(side_effect=lambda *args: db.outreach_mailboxes.docs[0]))
    collection = db.outreach_email_operations if source == "email_send" else db.outreach_email_discoveries
    write = collection.update_one
    async def lost_confirmation(query, update, **kwargs):
        if update.get("$set", {}).get("status") in {"accepted", "found"} and not update["$set"].get("repaired_from_physical_receipt"):
            raise RuntimeError("fake provider operation acknowledgement failure")
        return await write(query, update, **kwargs)
    monkeypatch.setattr(collection, "update_one", lost_confirmation)
    await prepare_due(db)
    result = await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"])
    assert result["status"] == "action_uncertain"
    assert db.outreach_campaigns.docs[0]["status"] == "paused"
    assert db.outreach_intents.docs[0]["status"] == "unknown_outcome"
    receipt = db.outreach_physical_requests.docs[0]
    assert receipt["status"] == "response_received"
    # Simulate cleanup lost after receipt: recovery must clear only this token.
    sender = db.outreach_sender_execution.docs[0]
    sender.update(status="in_flight", owner_token=receipt["owner_token"], physical_request_token=receipt["_id"])
    assert await recover_intent(db, db.outreach_intents.docs[0]) == "repaired"
    assert db.outreach_intents.docs[0]["status"] == "executed"
    assert db.outreach_tasks.docs[0]["status"] == ("accepted" if source == "email_send" else "completed")
    assert db.outreach_campaigns.docs[0]["status"] == "paused"
    assert "physical_request_token" not in sender and sender["status"] == "idle"
    if source == "email_send":
        assert collection.docs[0]["accepted_at"] == receipt["completed_at"]
        from outreach.core.mailbox_sync import _apply_inbound
        received_at = receipt["completed_at"] + timedelta(microseconds=1)
        inbound = {"id": "reply", "in_reply_to": collection.docs[0]["message_id"]}
        # The repaired acceptance time precedes inbound even when repair occurs later.
        reply = await _apply_inbound(db, db.outreach_mailboxes.docs[0], "reply", "lead@example.com", received_at, inbound, kind="reply")
        assert reply["status"] != "ignored"
    else:
        assert db.outreach_leads.docs[0]["email"] == "found@example.com"
    assert transport.post.await_count + transport.get.await_count == 1


@pytest.mark.asyncio
async def test_unknown_physical_token_cannot_release_or_reassign_sender():
    from tests.outreach_memory import Database
    db = Database()
    guard = SenderExecution(db)
    await guard.acquire("w", "a", "owner")
    await guard.begin("w", "a", "owner")
    await db.outreach_sender_execution.update_one(guard.scope("w", "a"), {"$set": {"physical_request_token": "unknown"}})
    assert not await guard.release("w", "a", "owner")
    assert not await guard.acquire("w", "a", "replacement", now=datetime.now(timezone.utc) + timedelta(days=1))


@pytest.mark.asyncio
async def test_committed_physical_receipt_survives_lost_acknowledgement(monkeypatch):
    from outreach.core.request_guard import request_parent
    from tests.test_outreach_mailboxes import _send_fixture
    db, binding, transport = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": "m"}))
    write = db.outreach_physical_requests.update_one
    async def commit_then_raise(query, update, **kwargs):
        result = await write(query, update, **kwargs)
        if update.get("$set", {}).get("status") == "response_received":
            raise RuntimeError("fake acknowledgement lost after commit")
        return result
    monkeypatch.setattr(db.outreach_physical_requests, "update_one", commit_then_raise)
    assert (await _send_fixture(db, binding))["status"] == "uncertain"
    assert db.outreach_physical_requests.docs[0]["status"] == "response_received"
    assert (await _send_fixture(db, binding))["status"] == "accepted"
    transport.post.assert_awaited_once()
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]


@pytest.mark.asyncio
async def test_recovery_cleanup_failure_remains_eligible_for_next_pass(monkeypatch):
    from tests.test_outreach_execution_recovery import interrupted_db
    from outreach.core.execution_outbox import ExecutionOutbox
    from tests.test_outreach_execution_outbox import NOW
    db, key = await interrupted_db()
    await ExecutionOutbox(db).finish("w", key, "owner", "provider_accepted", now=NOW)
    await SenderExecution(db).acquire("w", "a", "owner")
    await SenderExecution(db).begin("w", "a", "owner")
    release = SenderExecution.release
    monkeypatch.setattr(SenderExecution, "release", AsyncMock(side_effect=RuntimeError("fake cleanup outage")))
    with pytest.raises(RuntimeError):
        await recover_intent(db, await db.outreach_intents.find_one({"_id": key}))
    assert not db.outreach_intents.docs[0].get("projection_reconciled")
    monkeypatch.setattr(SenderExecution, "release", release)
    assert await recover_intent(db, await db.outreach_intents.find_one({"_id": key})) == "repaired"
