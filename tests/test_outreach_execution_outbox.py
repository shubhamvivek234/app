"""Crash/replay tests for the atomic embedded physical-attempt protocol."""
from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.execution_outbox import ExecutionOutbox
from tests.outreach_memory import Database

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


async def intent(db):
    return await ExecutionOutbox(db).ensure(
        workspace_id="w", campaign_id="c", lead_id="l", sender_id="a",
        node_id="n", action_kind="send_message", sequence_version=1,
        authorization_revision=2, credential_generation="g", legacy_operation_id="l:n",
        now=NOW,
    )


@pytest.mark.asyncio
async def test_duplicate_publication_claims_only_one_owner():
    db = Database()
    outbox = ExecutionOutbox(db)
    first = await intent(db)
    second = await intent(db)
    assert first["_id"] == second["_id"]
    assert await outbox.claim("w", first["_id"], "owner1", now=NOW)
    assert not await outbox.claim("w", first["_id"], "owner2", now=NOW)


@pytest.mark.asyncio
async def test_expired_pre_submission_owner_is_fenced_and_reclaimable():
    db = Database()
    outbox = ExecutionOutbox(db)
    doc = await intent(db)
    assert await outbox.claim("w", doc["_id"], "old", now=NOW)
    later = NOW + timedelta(minutes=10)
    assert await outbox.claim("w", doc["_id"], "new", now=later)
    assert not await outbox.begin_submission("w", doc["_id"], "old", now=later)
    assert await outbox.begin_submission("w", doc["_id"], "new", now=later)


@pytest.mark.asyncio
async def test_crash_after_possible_submission_never_becomes_sendable():
    db = Database()
    outbox = ExecutionOutbox(db)
    doc = await intent(db)
    assert await outbox.claim("w", doc["_id"], "owner", now=NOW)
    assert await outbox.begin_submission("w", doc["_id"], "owner", now=NOW)
    assert not await outbox.claim("w", doc["_id"], "redelivery", now=NOW + timedelta(days=1))
    assert await outbox.quarantine_expired("w", doc["_id"], now=NOW + timedelta(days=1))
    assert not await outbox.claim("w", doc["_id"], "retry", now=NOW + timedelta(days=2))


@pytest.mark.asyncio
async def test_known_not_submitted_can_defer_without_consuming_attempt():
    db = Database()
    outbox = ExecutionOutbox(db)
    doc = await intent(db)
    await outbox.claim("w", doc["_id"], "first", now=NOW)
    assert await outbox.defer("w", doc["_id"], "first", "inbox_stale", now=NOW)
    stored = await db.outreach_intents.find_one({"_id": doc["_id"]})
    assert not stored.get("attempt")
    assert not await outbox.claim("w", doc["_id"], "second", now=NOW)
    assert await outbox.claim("w", doc["_id"], "second", now=NOW + timedelta(minutes=6))


@pytest.mark.asyncio
async def test_provider_acceptance_has_distinct_evidence_and_cannot_repeat():
    db = Database()
    outbox = ExecutionOutbox(db)
    doc = await intent(db)
    await outbox.claim("w", doc["_id"], "owner", now=NOW)
    await outbox.begin_submission("w", doc["_id"], "owner", now=NOW)
    assert await outbox.finish("w", doc["_id"], "owner", "provider_accepted", provider_message_id="urn:m", now=NOW)
    stored = await db.outreach_intents.find_one({"_id": doc["_id"]})
    assert stored["attempt"]["outcome"] == "provider_accepted"
    assert stored["status"] == "executed"
    assert not await outbox.claim("w", doc["_id"], "redelivery", now=NOW + timedelta(days=1))


@pytest.mark.asyncio
async def test_database_failure_after_submission_preserves_non_retryable_boundary(monkeypatch):
    db = Database()
    outbox = ExecutionOutbox(db)
    doc = await intent(db)
    await outbox.claim("w", doc["_id"], "owner", now=NOW)
    await outbox.begin_submission("w", doc["_id"], "owner", now=NOW)
    original = db.outreach_intents.update_one

    async def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db.outreach_intents, "update_one", fail)
    with pytest.raises(RuntimeError):
        await outbox.finish("w", doc["_id"], "owner", "provider_accepted", now=NOW)
    monkeypatch.setattr(db.outreach_intents, "update_one", original)
    assert not await outbox.claim("w", doc["_id"], "retry", now=NOW + timedelta(days=1))


@pytest.mark.asyncio
async def test_legacy_uncertain_operation_is_never_newly_sendable():
    db = Database(outreach_tasks=[{"id": "l:n", "workspace_id": "w", "status": "uncertain"}])
    doc = await intent(db)
    assert doc["status"] == "unknown_outcome"
    assert not await ExecutionOutbox(db).claim("w", doc["_id"], "owner", now=NOW)
    assert not await ExecutionOutbox(db).claim("other", doc["_id"], "owner", now=NOW)


def execution_db():
    now = datetime.now(timezone.utc)
    return Database(
        outreach_leads=[{"id": "l", "workspace_id": "w", "campaign_id": "c", "assigned_account_id": "a",
                         "authorized_revision": 2, "sequence_version": 1, "current_node_id": "n",
                         "execution_state": "queued", "linkedin_url": "https://www.linkedin.com/in/person"}],
        outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "active", "authorization_revision": 2,
                             "pause_reasons": [], "sender_account_ids": ["a"]}],
        outreach_accounts=[{"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g",
                            "session_cookie_enc": "ciphertext", "inbox_sync": {"status": "complete", "parser_version": 1,
                            "credential_generation": "g", "coverage_started_at": now - timedelta(seconds=1), "completed_at": now}}],
        outreach_sequences=[{"campaign_id": "c", "workspace_id": "w", "version": 1,
                             "compiled_dag": {"root_node_ids": ["n"], "nodes": {"n": {
                             "id": "n", "type": "send_message", "config": {"body": "Hello"}}}}}],
    )


def stub_transport(monkeypatch, *, review_content=False):
    from unittest.mock import AsyncMock
    from outreach.tasks import sequence_executor as executor
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setattr(executor, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(executor.OutboundRateLimiter, "is_within_working_hours", lambda *args: True)
    monkeypatch.setattr(executor.OutboundRateLimiter, "check_and_increment_daily_limit", AsyncMock(return_value=True))
    client = type("Transport", (), {"send_direct_message": AsyncMock(return_value={"status": "message_sent"})})()
    monkeypatch.setattr(executor, "VoyagerClient", lambda **kwargs: client)
    monkeypatch.setattr(executor, "account_session", AsyncMock(return_value={"li_at": "local-test-cookie", "jsession_id": "ajax:local", "li_a": ""}))
    if not review_content:
        monkeypatch.setattr(executor, "_approved_content", AsyncMock(return_value=None))
    return executor, client


@pytest.mark.asyncio
async def test_reply_during_operation_claim_blocks_transport_and_defers(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    claim = executor._claim_operation

    async def claim_and_reply(*args, **kwargs):
        result = await claim(*args, **kwargs)
        await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
        return result

    monkeypatch.setattr(executor, "_claim_operation", claim_and_reply)
    result = await executor.SequenceExecutor.execute_lead_step("l", db)
    assert result["status"] == "lead_suppressed"
    client.send_direct_message.assert_not_awaited()
    operation = await db.outreach_tasks.find_one({"id": "l:n"})
    assert operation["status"] == "not_submitted"
    assert not db.outreach_intents.docs[0].get("attempt")


@pytest.mark.asyncio
async def test_reply_during_transport_is_preserved_and_broker_replay_does_not_resend(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()

    async def send(*args):
        await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
        return {"status": "message_sent"}

    client.send_direct_message.side_effect = send
    assert (await executor.SequenceExecutor.execute_lead_step("l", db))["status"] == "lead_changed"
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "replied"
    await executor.SequenceExecutor.execute_lead_step("l", db)
    assert client.send_direct_message.await_count == 1
    assert db.outreach_intents.docs[0]["attempt"]["outcome"] == "provider_accepted"


@pytest.mark.asyncio
async def test_reply_during_evidence_promotion_blocks_call_and_keeps_non_submission_evidence(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    update = db.outreach_tasks.update_one

    async def promote_then_reply(query, changes, **kwargs):
        result = await update(query, changes, **kwargs)
        if changes.get("$set", {}).get("status") == "dispatching":
            await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
        return result

    monkeypatch.setattr(db.outreach_tasks, "update_one", promote_then_reply)
    assert (await executor.SequenceExecutor.execute_lead_step("l", db))["status"] == "lead_suppressed"
    client.send_direct_message.assert_not_awaited()
    stored = db.outreach_intents.docs[0]
    assert stored["attempt"] is None
    assert stored["attempt_history"][0]["outcome"] == "not_submitted"
    assert (await db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "not_submitted"


@pytest.mark.asyncio
async def test_missing_prepared_voice_never_generates_or_consumes_step_or_attempt(monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.core.voice_cloner import VoiceCloner
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["type"] = "voice_note"
    synthesis = AsyncMock(side_effect=AssertionError("Sending must never synthesize"))
    monkeypatch.setattr(VoiceCloner, "synthesize_voice_note", synthesis)
    assert (await executor.SequenceExecutor.execute_lead_step("l", db))["status"] == "voice_preparation_required"
    synthesis.assert_not_awaited()
    assert (await db.outreach_leads.find_one({"id": "l"}))["current_node_id"] == "n"
    assert db.outreach_intents.docs[0]["attempt"] is None
    assert (await db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "not_submitted"


@pytest.mark.asyncio
async def test_pending_intent_can_refresh_authorization_but_submitted_intent_cannot():
    db = Database()
    doc = await intent(db)
    kwargs = dict(workspace_id="w", campaign_id="c", lead_id="l", sender_id="a", node_id="n",
                  action_kind="send_message", sequence_version=1, authorization_revision=3,
                  credential_generation="new-generation", legacy_operation_id="l:n", now=NOW)
    assert (await ExecutionOutbox(db).ensure(**kwargs))["authorization_revision"] == 3
    await ExecutionOutbox(db).claim("w", doc["_id"], "owner", now=NOW)
    assert not await ExecutionOutbox(db).begin_submission("w", doc["_id"], "owner", now=NOW,
                                                        expected={"revision": 2, "credential_generation": "g", "sender_id": "a"})
    assert await ExecutionOutbox(db).begin_submission("w", doc["_id"], "owner", now=NOW)
    kwargs["authorization_revision"] = 4
    assert (await ExecutionOutbox(db).ensure(**kwargs))["authorization_revision"] == 3
