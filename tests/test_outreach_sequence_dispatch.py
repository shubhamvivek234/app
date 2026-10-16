"""Selection and broker publication must not perform provider work."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from tests.test_outreach_execution_outbox import execution_db
from outreach.tasks.sequence_dispatch import prepare_due, publish_due, execute_job


@pytest.mark.asyncio
async def test_selector_persists_intent_before_reference_only_publication(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    assert (await prepare_due(db))["prepared"] == 1
    assert db.outreach_intents.docs
    publish = Mock()
    assert (await publish_due(db, publish))["published"] == 1
    job = db.outreach_sequence_jobs.docs[0]
    assert publish.call_args.kwargs["args"] == ["w", job["_id"]]
    assert job["intent_id"] == db.outreach_intents.docs[0]["_id"]


@pytest.mark.asyncio
async def test_broker_failure_retains_unsubmitted_intent_and_job(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await prepare_due(db)
    assert (await publish_due(db, Mock(side_effect=RuntimeError("broker down"))))["published"] == 0
    assert db.outreach_sequence_jobs.docs[0]["status"] == "queued"
    assert not db.outreach_intents.docs[0].get("attempt")


@pytest.mark.asyncio
async def test_published_job_is_due_and_duplicate_workers_do_not_execute_twice(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await prepare_due(db)
    await publish_due(db, Mock())
    executor = AsyncMock(return_value={"status": "success"})
    job = db.outreach_sequence_jobs.docs[0]
    assert (await execute_job(db, "w", job["_id"], executor=executor))["status"] == "success"
    await execute_job(db, "w", job["_id"], executor=executor)
    executor.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["enrollment_id", "current_node_id", "authorized_revision", "sequence_version", "assigned_account_id"])
async def test_stale_job_never_executes_a_different_current_step(monkeypatch, field):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await prepare_due(db)
    db.outreach_leads.docs[0][field] = "changed"
    executor = AsyncMock()
    result = await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"], executor=executor)
    assert result["status"] == "stale_job"
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_deferral_cannot_overwrite_a_reply(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await prepare_due(db)
    async def reply_while_waiting(*args, **kwargs):
        db.outreach_leads.docs[0].update(has_replied=True, execution_state="replied", next_action_due_at=None)
        return {"status": "request_deferred", "not_submitted": True}
    await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"], executor=reply_while_waiting)
    assert db.outreach_leads.docs[0]["execution_state"] == "replied"
    assert db.outreach_leads.docs[0]["next_action_due_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('current',[None,'',0,[],{},False])
async def test_selector_does_not_initialize_unproven_current_steps_or_bypass_root_delay(monkeypatch,current):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    db.outreach_leads.docs[0]["current_node_id"] = current
    db.outreach_sequences.docs[0]['compiled_dag']['nodes']['n']['delay_hours']=24
    assert (await prepare_due(db))["prepared"]==0
    assert db.outreach_leads.docs[0]["current_node_id"]==current
    assert not db.outreach_intents.docs and not db.outreach_sequence_jobs.docs


@pytest.mark.asyncio
async def test_changed_intent_authority_denies_job(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await prepare_due(db)
    db.outreach_intents.docs[0]["sender_id"] = "other"
    executor = AsyncMock()
    assert (await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"], executor=executor))["status"] == "stale_job"
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_mailbox_defers_worker_instead_of_hot_looping(monkeypatch):
    from outreach.tasks import sequence_dispatch
    from tests.test_outreach_execution_outbox import execution_db
    monkeypatch.setattr(sequence_dispatch, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    await sequence_dispatch.prepare_due(db)
    result = await sequence_dispatch.execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"],
        executor=AsyncMock(return_value={"status": "mailbox_unavailable"}))
    assert result["status"] == "mailbox_unavailable"
    assert db.outreach_leads.docs[0]["next_action_due_at"] > datetime.now(timezone.utc)
    assert db.outreach_sequence_jobs.docs[0]["status"] == "deferred"


@pytest.mark.asyncio
async def test_same_condition_is_selected_again_at_its_next_due_occurrence(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["type"] = "if_connected"
    await prepare_due(db)
    next_due = datetime.now(timezone.utc) + timedelta(hours=1)
    async def poll(*args, **kwargs):
        db.outreach_leads.docs[0].update(next_action_due_at=next_due)
        return {"status": "waiting_for_condition"}
    await execute_job(db, "w", db.outreach_sequence_jobs.docs[0]["_id"], executor=poll)
    assert (await prepare_due(db, now=next_due))["prepared"] == 1
    assert len(db.outreach_sequence_jobs.docs) == 2


@pytest.mark.asyncio
async def test_invalid_candidates_rotate_so_later_eligible_leads_are_selected(monkeypatch):
    from outreach.tasks import sequence_dispatch as module
    monkeypatch.setattr(module, "sequence_dispatch_enabled", lambda: True)
    db = execution_db()
    original = db.outreach_leads.docs[0]
    db.outreach_leads.docs[:] = [{**original, "id": str(n), "assigned_account_id": "missing"} for n in range(3)] + [original]
    for _ in range(3):
        await prepare_due(db, limit=2)
    assert db.outreach_sequence_jobs.docs
