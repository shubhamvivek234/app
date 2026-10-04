"""Manual action durability, partial stages, and reporting repair without resend."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from tests.outreach_memory import Database
from outreach.core.manual_actions import ManualActions


def database():
    return Database(outreach_accounts=[{"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g"}],
                    outreach_engage_posts=[{"id": "p", "workspace_id": "w", "list_id": "list", "status": "pending", "post_urn": "urn:post", "action_id": "j"}],
                    outreach_inbox_threads=[{"id": "t", "workspace_id": "w", "account_id": "a", "conversation_urn": "urn:thread", "thread_revision": 1, "messages": []}])


@pytest.mark.asyncio
async def test_manual_submission_records_exact_human_content_and_durable_job():
    db = database()
    service = ManualActions(db)
    job = await service.queue("j", "w", "a", "p", "engage", "comment", {"body": "Reviewed comment", "auto_like": True}, "human")
    assert job["status"] == "queued"
    assert list(job["stages"]) == ["like", "comment"]
    assert job["binding"]["content"]["body"] == "Reviewed comment"
    assert db.outreach_content_approvals.docs[0]["reviewed_by"] == "human"
    assert not db.outreach_sender_execution.docs


@pytest.mark.asyncio
async def test_duplicate_claim_cannot_repeat_provider_call(monkeypatch):
    from outreach.core import manual_actions as module
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    transport = type("Client", (), {"like_update": AsyncMock(return_value={"status": "liked"})})()
    monkeypatch.setattr(service, "client", AsyncMock(return_value=transport))
    assert (await service.run("w", "j"))["status"] == "completed"
    await service.run("w", "j")
    transport.like_update.assert_awaited_once()
    assert db.outreach_engage_posts.docs[0]["reactions_count"] == 1


@pytest.mark.asyncio
async def test_received_outcome_repairs_reporting_without_provider_replay(monkeypatch):
    from outreach.core import manual_actions as module
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    transport = type("Client", (), {"like_update": AsyncMock(return_value={"status": "liked"})})()
    monkeypatch.setattr(service, "client", AsyncMock(return_value=transport))
    update = db.outreach_engage_posts.update_one
    async def commit_then_lose_ack(query, changes, **kwargs):
        await update(query, changes, **kwargs)
        raise RuntimeError("report acknowledgement lost")
    monkeypatch.setattr(db.outreach_engage_posts, "update_one", commit_then_lose_ack)
    assert (await service.run("w", "j"))["status"] == "projection_pending"
    assert db.outreach_manual_actions.docs[0]["stages"]["like"]["status"] == "provider_accepted"
    monkeypatch.setattr(db.outreach_engage_posts, "update_one", update)
    assert (await service.recover("w", "j"))["status"] == "completed"
    transport.like_update.assert_awaited_once()
    assert db.outreach_engage_posts.docs[0]["reactions_count"] == 1


@pytest.mark.asyncio
async def test_interrupted_possible_submission_never_becomes_queued():
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    job = db.outreach_manual_actions.docs[0]
    job.update(status="in_flight", owner="old", claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    job["stages"]["like"] = {"status": "possible_submission", "request_id": "physical"}
    assert (await service.recover("w", "j"))["status"] == "unknown_outcome"
    assert db.outreach_engage_posts.docs[0]["action_id"] == "j"


@pytest.mark.asyncio
async def test_partial_like_is_not_repeated_when_comment_defers(monkeypatch):
    from outreach.core import manual_actions as module
    from outreach.core.request_guard import RequestDenied
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "comment", {"body": "Reviewed comment", "auto_like": True}, "human")
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    transport = type("Client", (), {"like_update": AsyncMock(return_value={"status": "liked"}),
        "comment_on_update": AsyncMock(side_effect=RequestDenied("sender_busy"))})()
    monkeypatch.setattr(service, "client", AsyncMock(return_value=transport))
    assert (await service.run("w", "j"))["status"] == "queued"
    db.outreach_manual_actions.docs[0]["next_due_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    transport.comment_on_update.side_effect = None
    transport.comment_on_update.return_value = {"status": "commented"}
    assert (await service.run("w", "j"))["status"] == "completed"
    transport.like_update.assert_awaited_once()
    assert transport.comment_on_update.await_count == 2


@pytest.mark.asyncio
async def test_duplicate_queue_cannot_reapprove_revoked_content():
    from outreach.core.content_approval import ContentApproval
    db = database()
    service = ManualActions(db)
    job = await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    approval = db.outreach_content_approvals.docs[0]
    await ContentApproval(db).decide("w", approval["_id"], "human", "revoke", revision=approval["revision"])
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    assert not await ContentApproval(db).allowed(job["binding"])


@pytest.mark.asyncio
async def test_old_physical_receipt_cannot_confirm_a_new_manual_job():
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    job = db.outreach_manual_actions.docs[0]
    job.update(status="unknown_outcome", owner="new-owner")
    job["stages"]["like"] = {"status": "possible_submission", "request_id": "physical"}
    await db.outreach_physical_requests.insert_one({"_id": "physical", "workspace_id": "w", "sender_id": "a",
        "owner_token": "old-owner", "status": "response_received", "http_status": 201, "completed_at": datetime.now(timezone.utc)})
    assert (await service.recover("w", "j"))["status"] == "unknown_outcome"
    assert db.outreach_engage_posts.docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_completed_job_repairs_interrupted_post_lock_cleanup():
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    db.outreach_manual_actions.docs[0]["status"] = "completed"
    await service.recover("w", "j")
    assert "action_id" not in db.outreach_engage_posts.docs[0]


@pytest.mark.asyncio
async def test_inbox_projection_deduplicates_and_preserves_newer_inbound_message():
    db = database()
    service = ManualActions(db)
    job = await service.queue("j", "w", "a", "t", "inbox_reply", "reply", {"body": "Reviewed reply"}, "human")
    now = datetime.now(timezone.utc)
    job["stages"]["reply"] = {"status": "provider_accepted", "accepted_at": now, "provenance": "adapter_response"}
    db.outreach_inbox_threads.docs[0].update(last_message_at=now + timedelta(seconds=1), last_message_snippet="New reply")
    await service.project(job)
    await service.project(job)
    thread = db.outreach_inbox_threads.docs[0]
    assert len(thread["messages"]) == 1
    assert thread["last_message_snippet"] == "New reply"
    assert thread["thread_revision"] == 2


@pytest.mark.asyncio
async def test_inbound_revision_invalidates_queued_reply(monkeypatch):
    from outreach.core import manual_actions as module
    db = database()
    service = ManualActions(db)
    job = await service.queue("j", "w", "a", "t", "inbox_reply", "reply", {"body": "Reviewed reply"}, "human")
    db.outreach_manual_actions.docs[0].update(status="preparing", owner="owner")
    db.outreach_inbox_threads.docs[0]["thread_revision"] += 1
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    assert await service.validate(job, "owner") == "content_changed"


@pytest.mark.asyncio
async def test_cancel_pending_inbox_reply_clears_slot_without_message():
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "t", "inbox_reply", "reply", {"body": "Reviewed reply"}, "human")
    await db.outreach_inbox_jobs.insert_one({"id": "j", "workspace_id": "w", "status": "queued"})
    await service.cancel("w", "j")
    assert db.outreach_inbox_jobs.docs[0]["status"] == "cancelled"
    assert not db.outreach_inbox_threads.docs[0]["messages"]
    assert "manual_action_id" not in db.outreach_inbox_threads.docs[0]


@pytest.mark.asyncio
async def test_receipt_recovery_releases_only_original_sender_token():
    from outreach.core.sender_execution import SenderExecution
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    job = db.outreach_manual_actions.docs[0]
    job.update(status="unknown_outcome", owner="owner")
    job["stages"]["like"] = {"status": "possible_submission", "request_id": service.physical_id(job, "like"), "owner_token": "owner"}
    await db.outreach_physical_requests.insert_one({"_id": service.physical_id(job, "like"), "workspace_id": "w", "sender_id": "a",
        "owner_token": "owner", "source": "engage", "action": "like", "mutation": True, "credential_generation": "g",
        "logical_operation_id": "engage:p", "status": "response_received", "http_status": 201, "completed_at": datetime.now(timezone.utc)})
    await db.outreach_sender_execution.insert_one({**SenderExecution.scope("w", "a"), "owner_token": "owner", "status": "in_flight", "physical_request_token": service.physical_id(job, "like")})
    assert (await service.recover("w", "j"))["status"] == "completed"
    assert db.outreach_sender_execution.docs[0]["status"] == "idle"
    assert "physical_request_token" not in db.outreach_sender_execution.docs[0]
    db.outreach_sender_execution.docs[0].update(status="in_flight", owner_token="new-owner", physical_request_token="new-request")
    await service.recover("w", "j")
    assert db.outreach_sender_execution.docs[0]["owner_token"] == "new-owner"


@pytest.mark.asyncio
async def test_due_publisher_keeps_job_on_broker_failure_and_uses_only_refs(monkeypatch):
    from unittest.mock import Mock
    from outreach.tasks import manual_actions as module
    db = database()
    await ManualActions(db).queue("j", "w", "a", "t", "inbox_reply", "reply", {"body": "Private reply"}, "human")
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    publish = Mock(side_effect=RuntimeError("Broker unavailable"))
    assert (await module.publish_due(db, publish))["published"] == 0
    assert db.outreach_manual_actions.docs[0]["status"] == "queued"
    assert publish.call_args.kwargs["args"] == ["j", "w", "a", "t"]


@pytest.mark.asyncio
async def test_provider_restriction_trips_sender_circuit(monkeypatch):
    from outreach.core import manual_actions as module
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    trip = AsyncMock()
    monkeypatch.setattr(module.SafetyShield, "trip_circuit_breaker", trip)
    monkeypatch.setattr(service, "client", AsyncMock(return_value=type("Client", (), {"like_update": AsyncMock(return_value={"status": "failed", "status_code": 403})})()))
    assert (await service.run("w", "j"))["status"] == "unknown_outcome"
    trip.assert_awaited_once_with("a", "Manual LinkedIn action restricted", db, "w")


@pytest.mark.asyncio
async def test_published_job_remains_due_for_an_arriving_worker(monkeypatch):
    from unittest.mock import Mock
    from outreach.tasks import manual_actions as publisher
    from outreach.core import manual_actions as module
    db = database()
    service = ManualActions(db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    monkeypatch.setattr(publisher, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    transport = type("Client", (), {"like_update": AsyncMock(return_value={"status": "liked"})})()
    monkeypatch.setattr(service, "client", AsyncMock(return_value=transport))
    assert (await publisher.publish_due(db, Mock()))["published"] == 1
    assert (await service.run("w", "j"))["status"] == "completed"
    transport.like_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_unresolved_rows_do_not_starve_later_cleanup():
    from outreach.tasks.manual_actions import recover_due
    db = database()
    for index in range(51):
        await db.outreach_manual_actions.insert_one({"_id": str(index), "workspace_id": "w", "account_id": "a", "source": "engage", "target_id": "p",
            "status": "unknown_outcome" if index < 50 else "completed", "stages": {"like": {"status": "possible_submission", "request_id": "none"}},
            "binding": {"credential_generation": "g"}})
    await recover_due(db)
    await recover_due(db)
    assert db.outreach_manual_actions.docs[50]["cleanup_complete"]


@pytest.mark.asyncio
async def test_cleanup_cannot_release_a_new_inflight_token(monkeypatch):
    from outreach.core.sender_execution import SenderExecution
    db = database()
    job = {"_id": "j", "workspace_id": "w", "account_id": "a", "owner": "old", "stages": {}}
    await db.outreach_sender_execution.insert_one({**SenderExecution.scope("w", "a"), "owner_token": "old", "status": "in_flight"})
    update = db.outreach_sender_execution.update_one
    async def new_token_before_release(query, changes, **kwargs):
        if changes.get("$set", {}).get("status") == "idle":
            db.outreach_sender_execution.docs[0]["physical_request_token"] = "new-flight"
        return await update(query, changes, **kwargs)
    monkeypatch.setattr(db.outreach_sender_execution, "update_one", new_token_before_release)
    await ManualActions(db).release_owner(job)
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"
    assert db.outreach_sender_execution.docs[0]["owner_token"] == "old"


@pytest.mark.asyncio
async def test_recovery_rotation_at_real_beat_cadence(monkeypatch):
    from outreach.tasks import manual_actions as module
    now = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(module, "datetime", Clock)
    db = database()
    for index in range(5):
        await db.outreach_manual_actions.insert_one({"_id": str(index), "workspace_id": "w", "account_id": "a", "source": "engage", "target_id": "p",
            "status": "unknown_outcome" if index < 4 else "completed", "stages": {"like": {"status": "possible_submission", "request_id": "none"}},
            "binding": {"credential_generation": "g"}})
    for _ in range(3):
        await module.recover_due(db, limit=2)
        now += timedelta(seconds=30)
    assert db.outreach_manual_actions.docs[4]["cleanup_complete"]
