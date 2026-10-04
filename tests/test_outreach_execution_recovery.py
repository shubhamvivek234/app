from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from outreach.core.execution_outbox import ExecutionOutbox
from outreach.core.execution_recovery import recover_intent
from tests.test_outreach_execution_outbox import intent, NOW
from tests.outreach_memory import Database


async def interrupted_db():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "active", "authorization_revision": 2}],
                  outreach_leads=[{"id": "l", "workspace_id": "w", "campaign_id": "c", "execution_state": "queued",
                                   "authorized_revision": 2, "current_node_id": "n", "assigned_account_id": "a"}])
    doc = await intent(db)
    await ExecutionOutbox(db).claim("w", doc["_id"], "owner", now=NOW)
    await db.outreach_tasks.insert_one({"id": "l:n", "workspace_id": "w", "campaign_id": "c", "lead_id": "l",
                                       "intent_id": doc["_id"], "owner_token": "owner", "status": "preparing"})
    await ExecutionOutbox(db).begin_submission("w", doc["_id"], "owner", now=NOW)
    return db, doc["_id"]


@pytest.mark.asyncio
async def test_crash_between_attempt_marker_and_ledger_promotion_is_visible_for_review():
    db, key = await interrupted_db()
    stored = await db.outreach_intents.find_one({"_id": key})
    assert await recover_intent(db, stored, now=NOW + timedelta(minutes=3)) == "quarantined"
    assert (await db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "uncertain"
    assert (await db.outreach_campaigns.find_one({"id": "c"}))["pause_reasons"] == ["unknown_outcome"]
    assert not await ExecutionOutbox(db).claim("w", key, "retry", now=NOW + timedelta(days=1))


@pytest.mark.asyncio
async def test_saved_acceptance_repairs_legacy_projection_without_new_submission():
    db, key = await interrupted_db()
    await ExecutionOutbox(db).finish("w", key, "owner", "provider_accepted", provider_message_id="m", now=NOW)
    assert await recover_intent(db, await db.outreach_intents.find_one({"_id": key})) == "repaired"
    task = await db.outreach_tasks.find_one({"id": "l:n"})
    assert task["status"] == "completed" and task["provider_message_id"] == "m"
    assert await recover_intent(db, await db.outreach_intents.find_one({"_id": key})) == "repaired"


@pytest.mark.asyncio
async def test_recovery_preserves_reply_and_human_resolution_provenance():
    db, key = await interrupted_db()
    await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
    assert await recover_intent(db, await db.outreach_intents.find_one({"_id": key}), now=NOW + timedelta(minutes=3)) == "quarantined"
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "replied"
    await db.outreach_intents.update_one({"_id": key}, {"$set": {"status": "executed", "resolution": {"source": "human_assertion"}}})
    assert await recover_intent(db, await db.outreach_intents.find_one({"_id": key})) == "human_review"


@pytest.mark.asyncio
async def test_recovery_beat_rotates_missing_prefix_and_reaches_later_known_receipt(monkeypatch):
    from celery_workers.tasks import outreach as worker
    db, key = await interrupted_db()
    await ExecutionOutbox(db).finish("w", key, "owner", "provider_accepted", now=NOW)
    prefix = [{"_id": f"!a-{n:03}", "workspace_id": "w", "status": "executed", "legacy_operation_id": f"missing-{n}",
        "claim_token": f"owner-{n}", "attempt": {"outcome": "provider_accepted"}} for n in range(200)]
    db.outreach_intents.docs[:] = prefix + db.outreach_intents.docs
    monkeypatch.setenv("DB_NAME", "test_isolated")
    monkeypatch.setattr(worker, "get_client", AsyncMock(return_value={"test_isolated": db}))
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    assert (await worker._recover_execution_intents())["checked"] == 200
    assert (await worker._recover_execution_intents())["repaired"] == 1
    assert (await db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "completed"
