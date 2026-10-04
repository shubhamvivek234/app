"""Drained operator assertions never become transport evidence or new sends."""
from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.manual_actions import ManualActions
from outreach.core.manual_resolution import ManualResolution
from outreach.core.sender_execution import SenderExecution
from tests.test_outreach_manual_actions import database


async def unknown(source="engage", action="comment", auto_like=False):
    db = database()
    service = ManualActions(db)
    target = "p" if source == "engage" else "t"
    content = {"body": "Reviewed copy", "auto_like": auto_like}
    await service.queue("j", "w", "a", target, source, action, content, "human")
    job = db.outreach_manual_actions.docs[0]
    job.update(status="unknown_outcome", owner="old", claim_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    if auto_like:
        job["stages"]["like"] = {"status": "provider_accepted", "provenance": "adapter_response", "accepted_at": datetime.now(timezone.utc)}
    request_id = service.physical_id(job, action)
    job["stages"][action] = {"status": "possible_submission", "request_id": request_id, "owner_token": "old"}
    await db.outreach_physical_requests.insert_one({"_id": request_id, "workspace_id": "w", "sender_id": "a", "owner_token": "old",
        "status": "unknown_outcome", "mutation": True, "source": source, "credential_generation": "g",
        "action": "message" if action == "reply" else action, "logical_operation_id": "engage:p" if source == "engage" else "j"})
    guard = SenderExecution(db)
    await guard.acquire("w", "a", "old")
    await guard.begin("w", "a", "old")
    await db.outreach_sender_execution.update_one(guard.scope("w", "a"), {"$set": {"physical_request_token": request_id}})
    return db, job


async def resolve(service, decisions, *, drained=True, digest=None):
    view = await service.inspect("w", "j")
    return await service.resolve("w", "j", decisions, "operator", "Independently inspected the original action after draining workers.",
        workers_drained=drained, expected_digest=digest or view["review_digest"])


@pytest.mark.asyncio
async def test_manual_assertion_preserves_original_unknown_evidence_and_excludes_engagement_gate():
    db, job = await unknown()
    service = ManualResolution(db)
    result = await resolve(service, {"comment": "confirmed_sent"})
    assert result["status"] == "resolved"
    assert job["stages"]["comment"]["status"] == "human_confirmed"
    assert job["review"]["provenance"] == "human_assertion"
    post = db.outreach_engage_posts.docs[0]
    assert not post.get("commented_at") and not post.get("comments_count")
    assert post["manual_review"]["decision"] == "confirmed_sent"
    assert "action_id" not in post
    physical = db.outreach_physical_requests.docs[0]
    assert physical["original_status"] == "unknown_outcome" and physical["status"] == "resolved"
    sender = db.outreach_sender_execution.docs[0]
    assert sender["permission"]["latched"] and sender["status"] == "idle"
    assert "physical_request_token" not in sender


@pytest.mark.asyncio
async def test_partial_provider_like_remains_observed_but_human_comment_is_separate():
    db, _ = await unknown(auto_like=True)
    await resolve(ManualResolution(db), {"comment": "not_sent_stop"})
    post = db.outreach_engage_posts.docs[0]
    assert post["reactions_count"] == 1 and post["liked_at"]
    assert not post.get("commented_at") and not post.get("comments_count")
    assert (await ManualActions(db).run("w", "j"))["status"] in {"disabled", "already_claimed"}


@pytest.mark.asyncio
async def test_inbox_assertion_does_not_invent_a_provider_message():
    db, _ = await unknown("inbox_reply", "reply")
    await resolve(ManualResolution(db), {"reply": "confirmed_sent"})
    thread = db.outreach_inbox_threads.docs[0]
    assert not thread["messages"]
    assert thread["manual_review"]["provenance"] == "human_assertion"
    assert "manual_action_id" not in thread


@pytest.mark.asyncio
async def test_draining_and_exact_review_snapshot_are_required():
    db, _ = await unknown()
    service = ManualResolution(db)
    with pytest.raises(ValueError):
        await resolve(service, {"comment": "confirmed_sent"}, drained=False)
    view = await service.inspect("w", "j")
    db.outreach_physical_requests.docs[0]["owner_token"] = "replacement"
    with pytest.raises(ValueError):
        await resolve(service, {"comment": "confirmed_sent"}, digest=view["review_digest"])
    assert db.outreach_manual_actions.docs[0]["status"] == "unknown_outcome"


@pytest.mark.asyncio
async def test_resolution_retry_after_physical_write_retains_original_actor_and_decision(monkeypatch):
    db, job = await unknown()
    service = ManualResolution(db)
    write = db.outreach_manual_actions.update_one
    async def fail_once(query, update, **kwargs):
        if update.get("$set", {}).get("stages.comment.status") == "human_confirmed":
            raise RuntimeError("fake stage write outage")
        return await write(query, update, **kwargs)
    monkeypatch.setattr(db.outreach_manual_actions, "update_one", fail_once)
    with pytest.raises(RuntimeError):
        await resolve(service, {"comment": "confirmed_sent"})
    assert job["status"] == "resolving" and db.outreach_sender_execution.docs[0]["permission"]["latched"]
    monkeypatch.setattr(db.outreach_manual_actions, "update_one", write)
    assert (await resolve(service, {"comment": "confirmed_sent"}))["status"] == "resolved"
    with pytest.raises(ValueError):
        await resolve(service, {"comment": "not_sent_stop"})
    assert job["review"]["operator"] == "operator"


@pytest.mark.asyncio
async def test_received_acceptance_uses_original_transport_time_and_counts_once():
    db, job = await unknown()
    accepted_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    db.outreach_physical_requests.docs[0].update(status="response_received", http_status=201, completed_at=accepted_at)
    service = ManualResolution(db)
    with pytest.raises(ValueError):
        await resolve(service, {"comment": "not_sent_stop"})
    await resolve(service, {"comment": "use_receipt"})
    await service.finish("w", "j")
    assert job["stages"]["comment"]["accepted_at"] == accepted_at
    assert db.outreach_engage_posts.docs[0]["comments_count"] == 1
    assert db.outreach_physical_requests.docs[0]["status"] == "response_received"


@pytest.mark.asyncio
async def test_pending_remainder_is_cancelled_without_automatic_continuation():
    db, job = await unknown(action="like")
    job["stages"]["comment"] = {"status": "pending"}
    await resolve(ManualResolution(db), {"like": "not_sent_stop"})
    assert job["stages"]["comment"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_missing_physical_receipt_can_be_asserted_but_never_invented():
    db, _ = await unknown()
    db.outreach_physical_requests.docs.clear()
    await resolve(ManualResolution(db), {"comment": "confirmed_sent"})
    assert not db.outreach_physical_requests.docs
    assert not db.outreach_engage_posts.docs[0].get("commented_at")


@pytest.mark.asyncio
async def test_drained_preparing_physical_request_can_stop_without_inventing_a_send():
    db, job = await unknown()
    db.outreach_physical_requests.docs[0]["status"] = "preparing"
    await resolve(ManualResolution(db), {"comment": "not_sent_stop"})
    physical = db.outreach_physical_requests.docs[0]
    assert physical["status"] == "resolved" and physical["original_status"] == "preparing"
    assert job["stages"]["comment"]["status"] == "not_sent_stopped"
    assert db.outreach_sender_execution.docs[0]["status"] == "idle"
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]
    assert not db.outreach_engage_posts.docs[0].get("commented_at")


@pytest.mark.asyncio
async def test_preparing_receipt_cannot_be_asserted_sent():
    db, _ = await unknown()
    db.outreach_physical_requests.docs[0]["status"] = "preparing"
    with pytest.raises(ValueError):
        await resolve(ManualResolution(db), {"comment": "confirmed_sent"})
    assert db.outreach_physical_requests.docs[0]["status"] == "preparing"


@pytest.mark.asyncio
async def test_preparing_stop_preserves_replacement_owner_and_request_token():
    db, _ = await unknown()
    db.outreach_physical_requests.docs[0]["status"] = "preparing"
    sender = db.outreach_sender_execution.docs[0]
    sender.update(owner_token="replacement", physical_request_token="replacement-request")
    await resolve(ManualResolution(db), {"comment": "not_sent_stop"})
    assert sender["owner_token"] == "replacement"
    assert sender["physical_request_token"] == "replacement-request"
    assert sender["status"] == "in_flight" and sender["permission"]["latched"]


@pytest.mark.asyncio
async def test_preparing_read_requires_interrupted_read_review():
    from outreach.core.execution_permission import ExecutionPermission
    db, _ = await unknown()
    record = db.outreach_physical_requests.docs[0]
    record.update(status="preparing", mutation=False, source="verify", action="read")
    service = ExecutionPermission(db)
    with pytest.raises(ValueError):
        await service.resolve_request("w", "a", record["_id"], "operator", "not_sent_stop",
            "Drained and inspected the original verification read.", workers_drained=True)
    await service.resolve_request("w", "a", record["_id"], "operator", "read_interrupted",
        "Drained and inspected the original verification read.", workers_drained=True)
    assert record["original_status"] == "preparing"
    assert record["resolution"]["provenance"] == "human_assertion"
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["request_id", "generation", "source", "action", "operation", "decision"])
async def test_changed_request_binding_and_incomplete_decisions_fail_closed(change):
    db, job = await unknown()
    if change == "request_id":
        job["stages"]["comment"]["request_id"] = "another-request"
    elif change == "decision":
        with pytest.raises(ValueError):
            await resolve(ManualResolution(db), {})
        return
    else:
        field = {"generation": "credential_generation", "operation": "logical_operation_id"}.get(change, change)
        db.outreach_physical_requests.docs[0][field] = "replacement"
    with pytest.raises(ValueError):
        await resolve(ManualResolution(db), {"comment": "confirmed_sent"})
    assert job["status"] == "unknown_outcome"


@pytest.mark.asyncio
async def test_inbox_review_write_outage_is_recovered_by_saved_database_review(monkeypatch):
    from outreach.tasks.manual_actions import recover_due
    db, job = await unknown("inbox_reply", "reply")
    original = db.outreach_inbox_jobs.update_one
    async def unavailable(*args, **kwargs):
        raise RuntimeError("fake inbox review outage")
    monkeypatch.setattr(db.outreach_inbox_jobs, "update_one", unavailable)
    with pytest.raises(RuntimeError):
        await resolve(ManualResolution(db), {"reply": "not_sent_stop"})
    assert job["status"] == "resolved" and not job.get("cleanup_complete")
    monkeypatch.setattr(db.outreach_inbox_jobs, "update_one", original)
    assert (await recover_due(db))["resolved"] == 1
    assert job["cleanup_complete"]


@pytest.mark.asyncio
async def test_permission_cannot_be_unlatched_mid_repair_after_physical_resolution(monkeypatch):
    from outreach.core.execution_permission import ExecutionPermission
    db, job = await unknown()
    original = db.outreach_manual_actions.update_one
    async def fail_stage(query, update, **kwargs):
        if update.get("$set", {}).get("stages.comment.status"):
            raise RuntimeError("stage database outage")
        return await original(query, update, **kwargs)
    monkeypatch.setattr(db.outreach_manual_actions, "update_one", fail_stage)
    with pytest.raises(RuntimeError):
        await resolve(ManualResolution(db), {"comment": "confirmed_sent"})
    assert db.outreach_physical_requests.docs[0]["status"] == "resolved"
    with pytest.raises(ValueError, match="manual"):
        await ExecutionPermission(db).grant("w", "a", "g", ["engage"], "operator", clear_latch=True)


@pytest.mark.asyncio
async def test_proven_non_call_cannot_be_human_confirmed_sent():
    db, _ = await unknown()
    db.outreach_physical_requests.docs[0]["status"] = "not_submitted"
    with pytest.raises(ValueError):
        await resolve(ManualResolution(db), {"comment": "confirmed_sent"})
    await resolve(ManualResolution(db), {"comment": "not_sent_stop"})


@pytest.mark.asyncio
async def test_inbox_job_readback_keeps_human_confirmation_separate_from_sent_message():
    from outreach.api.inbox import get_inbox_job
    db, _ = await unknown("inbox_reply", "reply")
    await resolve(ManualResolution(db), {"reply": "confirmed_sent"})
    result = await get_inbox_job("j", current_user={"user_id": "human", "default_workspace_id": "w"}, db=db)
    assert result["status"] == "resolved" and result["review_provenance"] == "human_assertion"
    assert not result.get("result", {}).get("message")


@pytest.mark.asyncio
async def test_inbox_received_transport_review_returns_original_sent_message():
    from outreach.api.inbox import get_inbox_job
    db, _ = await unknown("inbox_reply", "reply")
    await db.outreach_inbox_jobs.insert_one({"id": "j", "workspace_id": "w", "kind": "reply", "status": "queued"})
    db.outreach_physical_requests.docs[0].update(status="response_received", http_status=201, completed_at=datetime.now(timezone.utc))
    await resolve(ManualResolution(db), {"reply": "use_receipt"})
    result = await get_inbox_job("j", current_user={"user_id": "human", "default_workspace_id": "w"}, db=db)
    assert result["status"] == "completed"
    assert result["result"]["message"]["evidence_source"] == "transport_response_recovery"
