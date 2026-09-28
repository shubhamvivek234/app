"""Human review of ambiguous provider outcomes never retries an action."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
USER = {"user_id": "admin-1", "default_workspace_id": "ws-1"}


def _db(task_type="send_email", *, op_status="uncertain"):
    task = {
        "id": "lead-1:node-1", "workspace_id": "ws-1", "campaign_id": "campaign-1",
        "lead_id": "lead-1", "account_id": "sender-1", "task_type": task_type,
        "status": "uncertain", "reason": "secret provider text", "created_at": NOW,
        "updated_at": NOW,
    }
    db = MagicMock()
    db.outreach_tasks.find_one = AsyncMock(return_value=task)
    db.outreach_tasks.find_one_and_update = AsyncMock(return_value={
        **task, "status": "resolving", "resolution": {"decision": "confirmed_sent"},
    })
    db.outreach_tasks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead-1", "workspace_id": "ws-1", "campaign_id": "campaign-1",
        "assigned_account_id": "sender-1", "execution_state": "waiting_trigger",
        "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
    })
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign-1", "workspace_id": "ws-1", "name": "Pilot",
        "status": "paused", "pause_reason": "An action outcome needs manual reconciliation before resuming.",
    })
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "sender-1", "workspace_id": "ws-1", "full_name": "Sam Sender",
    })
    db.outreach_email_operations.find_one = AsyncMock(return_value={
        "_id": "email:ws-1:lead-1:node-1", "workspace_id": "ws-1",
        "lead_id": "lead-1", "campaign_id": "campaign-1",
        "sender_account_id": "sender-1", "status": op_status,
        "created_at": NOW, "message_id": "<id@mail.unravler.com>",
    })
    db.outreach_email_operations.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return db


@pytest.mark.asyncio
async def test_confirmation_requires_evidence_and_never_restarts_campaign():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db()
    result = await resolve_uncertain_action(
        "lead-1:node-1",
        ResolutionRequest(decision="confirmed_sent", evidence_note="Verified message in Gmail Sent folder", acknowledged=True),
        current_user=USER, db=db,
    )

    assert result["status"] == "accepted"
    assert result["campaign_status"] == "paused"
    assert db.outreach_campaigns.update_one.await_count == 0
    assert db.outreach_tasks.find_one_and_update.await_args.args[0] == {
        "id": "lead-1:node-1", "workspace_id": "ws-1", "status": "uncertain",
    }
    task_update = db.outreach_tasks.update_one.await_args.args[1]
    assert task_update["$set"]["status"] == "accepted"
    assert task_update["$set"]["resolution"]["source"] == "human_assertion"
    assert task_update["$set"]["resolution"]["evidence_note"] == "Verified message in Gmail Sent folder"
    email_update = db.outreach_email_operations.update_one.await_args.args[1]
    assert email_update["$set"]["status"] == "accepted"
    assert email_update["$set"]["acceptance_source"] == "human_assertion"
    lead_update = db.outreach_leads.update_one.await_args.args[1]
    assert lead_update["$set"]["execution_state"] == "queued"


@pytest.mark.asyncio
async def test_not_sent_stops_lead_without_requeue_or_campaign_resume():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db()
    result = await resolve_uncertain_action(
        "lead-1:node-1",
        ResolutionRequest(decision="not_sent_stop", evidence_note="Checked Sent folder and no message exists", acknowledged=True),
        current_user=USER, db=db,
    )
    assert result["status"] == "not_sent_stopped"
    assert db.outreach_campaigns.update_one.await_count == 0
    lead_update = db.outreach_leads.update_one.await_args.args[1]
    assert lead_update["$set"]["execution_state"] == "failed"
    assert lead_update["$set"]["next_action_due_at"] is None
    email_update = db.outreach_email_operations.update_one.await_args.args[1]
    assert email_update["$set"]["status"] == "not_sent_stopped"


@pytest.mark.asyncio
async def test_cross_workspace_action_is_not_resolved():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db()
    db.outreach_tasks.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await resolve_uncertain_action(
            "lead-1:node-1", ResolutionRequest(decision="not_sent_stop", evidence_note="No message exists in Sent folder", acknowledged=True),
            current_user={"user_id": "other", "default_workspace_id": "ws-2"}, db=db,
        )
    assert exc.value.status_code == 404
    assert db.outreach_tasks.find_one.await_args.args[0]["workspace_id"] == "ws-2"
    assert db.outreach_tasks.find_one_and_update.await_count == 0


@pytest.mark.asyncio
async def test_confirmation_rejects_missing_email_operation_record():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db()
    db.outreach_email_operations.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await resolve_uncertain_action(
            "lead-1:node-1", ResolutionRequest(decision="confirmed_sent", evidence_note="Verified provider Sent folder", acknowledged=True),
            current_user=USER, db=db,
        )
    assert exc.value.status_code == 409
    assert db.outreach_tasks.find_one_and_update.await_count == 0


@pytest.mark.asyncio
async def test_conflicting_or_duplicate_resolution_does_not_overwrite_audit():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db()
    db.outreach_tasks.find_one.return_value = {
        **await db.outreach_tasks.find_one(), "status": "accepted",
        "resolution": {"decision": "confirmed_sent", "source": "human_assertion", "evidence_note": "Existing evidence"},
    }
    same = await resolve_uncertain_action(
        "lead-1:node-1", ResolutionRequest(decision="confirmed_sent", evidence_note="Another evidence note", acknowledged=True),
        current_user=USER, db=db,
    )
    assert same["status"] == "accepted"
    assert db.outreach_tasks.find_one_and_update.await_count == 0
    with pytest.raises(HTTPException) as exc:
        await resolve_uncertain_action(
            "lead-1:node-1", ResolutionRequest(decision="not_sent_stop", evidence_note="Different decision evidence", acknowledged=True),
            current_user=USER, db=db,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_retries_partial_confirmation_after_lead_requeued_without_resending():
    from outreach.api.action_reconciliation import ResolutionRequest, resolve_uncertain_action

    db = _db(op_status="accepted")
    task = await db.outreach_tasks.find_one()
    db.outreach_tasks.find_one.return_value = {
        **task, "status": "resolving", "resolution": {
            "decision": "confirmed_sent", "source": "human_assertion",
            "actor_id": "admin-1", "evidence_note": "Checked provider Sent folder", "recorded_at": NOW,
        },
    }
    db.outreach_leads.find_one.return_value["execution_state"] = "queued"
    result = await resolve_uncertain_action(
        "lead-1:node-1", ResolutionRequest(
            decision="confirmed_sent", evidence_note="Checked provider Sent folder", acknowledged=True,
        ), current_user=USER, db=db,
    )
    assert result["status"] == "accepted"
    db.outreach_leads.update_one.assert_not_awaited()
    db.outreach_email_operations.update_one.assert_not_awaited()
    assert db.outreach_tasks.update_one.await_args.args[1]["$set"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_list_redacts_provider_error_and_scopes_all_lookups():
    from outreach.api.action_reconciliation import list_action_reviews

    db = _db()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[await db.outreach_tasks.find_one()])
    db.outreach_tasks.find.return_value = cursor
    db.outreach_tasks.count_documents = AsyncMock(return_value=1)
    result = await list_action_reviews(view="pending", skip=0, limit=25, current_user=USER, db=db)
    assert result["total"] == 1
    assert result["items"][0]["campaign_name"] == "Pilot"
    assert "secret provider text" not in str(result)
    assert db.outreach_tasks.find.call_args.args[0]["workspace_id"] == "ws-1"
    assert db.outreach_campaigns.find_one.await_args.args[0]["workspace_id"] == "ws-1"
    assert db.outreach_leads.find_one.await_args.args[0]["workspace_id"] == "ws-1"


def test_confirmation_cannot_submit_without_explicit_acknowledgement_or_note():
    from pydantic import ValidationError
    from outreach.api.action_reconciliation import ResolutionRequest

    with pytest.raises(ValidationError):
        ResolutionRequest(decision="confirmed_sent", evidence_note="", acknowledged=True)
    with pytest.raises(ValidationError):
        ResolutionRequest(decision="confirmed_sent", evidence_note="Verified Sent folder", acknowledged=False)


def test_action_review_routes_are_registered_under_outreach():
    from outreach.api.router import router

    paths = {route.path for route in router.routes}
    assert "/outreach/action-reviews" in paths
    assert "/outreach/action-reviews/{task_id}/resolve" in paths
