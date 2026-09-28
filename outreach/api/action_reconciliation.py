"""Manual, tenant-scoped review for outreach actions with unknown outcomes.

This endpoint never calls a provider and never resumes a campaign. The action
ledger remains the idempotency boundary: a human assertion records provenance,
then the existing executor can advance the lead only after a separate campaign
resume. Unknown actions are never automatically resent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, field_validator

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.models import LeadExecutionState


router = APIRouter(prefix="/action-reviews", tags=["Outreach Action Review"])
_PENDING = {"$in": ["uncertain", "resolving"]}
_RESOLVED = {"$in": ["accepted", "completed", "not_sent_stopped"]}
_PUBLIC_REASON = "The provider outcome is unknown. Check the sender account before deciding."


def _workspace_id(user: dict) -> str:
    workspace_id = user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=403, detail="An active workspace is required")
    return str(workspace_id)


class ResolutionRequest(BaseModel):
    decision: Literal["confirmed_sent", "not_sent_stop"]
    evidence_note: str = Field(..., min_length=10, max_length=500)
    acknowledged: Literal[True]

    @field_validator("evidence_note")
    @classmethod
    def evidence_is_meaningful(cls, value: str) -> str:
        note = value.strip()
        if len(note) < 10:
            raise ValueError("Describe what you checked before resolving this action")
        return note


async def _email_operation(db, workspace_id: str, task: dict) -> dict | None:
    return await db.outreach_email_operations.find_one({
        "_id": f"email:{workspace_id}:{task['id']}", "workspace_id": workspace_id,
        "lead_id": task.get("lead_id"), "campaign_id": task.get("campaign_id"),
        "sender_account_id": task.get("account_id"),
    }, {"_id": 1, "status": 1, "created_at": 1, "accepted_at": 1,
        "provider_message_id": 1, "provider_thread_id": 1,
        "acceptance_source": 1, "resolution": 1})


@router.get("", dependencies=[require_permission("account:connect")])
async def list_action_reviews(
    view: Literal["pending", "resolved"] = "pending",
    skip: int = Query(0, ge=0, le=5000),
    limit: int = Query(25, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    query = {"workspace_id": workspace_id}
    if view == "pending":
        query["status"] = _PENDING
    else:
        query.update({"status": _RESOLVED, "resolution.source": "human_assertion"})
    projection = {
        "_id": 0, "id": 1, "task_type": 1, "status": 1, "campaign_id": 1,
        "lead_id": 1, "account_id": 1, "created_at": 1, "updated_at": 1,
        "resolution": 1,
    }
    cursor = db.outreach_tasks.find(query, projection).sort("updated_at", -1).skip(skip).limit(limit)
    tasks = await cursor.to_list(length=limit)
    total = await db.outreach_tasks.count_documents(query)
    items = []
    for task in tasks:
        campaign = await db.outreach_campaigns.find_one({
            "workspace_id": workspace_id, "id": task.get("campaign_id"),
        }, {"_id": 0, "name": 1, "status": 1})
        lead = await db.outreach_leads.find_one({
            "workspace_id": workspace_id, "id": task.get("lead_id"),
            "campaign_id": task.get("campaign_id"),
        }, {"_id": 0, "first_name": 1, "last_name": 1, "email": 1, "execution_state": 1})
        account = await db.outreach_accounts.find_one({
            "workspace_id": workspace_id, "id": task.get("account_id"),
        }, {"_id": 0, "full_name": 1})
        email_op = await _email_operation(db, workspace_id, task) if task.get("task_type") == "send_email" else None
        resolution = task.get("resolution") if view == "resolved" else None
        items.append({
            "id": task.get("id"), "task_type": task.get("task_type"),
            "status": task.get("status"), "campaign_id": task.get("campaign_id"),
            "campaign_name": (campaign or {}).get("name") or "Deleted campaign",
            "campaign_status": (campaign or {}).get("status"),
            "lead_id": task.get("lead_id"),
            "lead_name": " ".join(filter(None, [(lead or {}).get("first_name"), (lead or {}).get("last_name")])) or "Deleted lead",
            "lead_email": (lead or {}).get("email") if task.get("task_type") == "send_email" else None,
            "lead_status": (lead or {}).get("execution_state"),
            "sender_name": (account or {}).get("full_name") or "Sender unavailable",
            "created_at": task.get("created_at"), "updated_at": task.get("updated_at"),
            "reason": _PUBLIC_REASON if view == "pending" else None,
            "can_confirm": bool(task.get("task_type") != "send_email" or email_op),
            "resolution": {
                "decision": resolution.get("decision"), "source": resolution.get("source"),
                "actor_id": resolution.get("actor_id"), "evidence_note": resolution.get("evidence_note"),
                "recorded_at": resolution.get("recorded_at"),
            } if isinstance(resolution, dict) else None,
        })
    return {"items": items, "total": total, "skip": skip, "limit": limit, "view": view}


@router.post("/{task_id}/resolve", dependencies=[require_permission("account:connect")])
async def resolve_uncertain_action(
    task_id: str,
    request: ResolutionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    actor_id = str(current_user.get("user_id") or "")
    if not actor_id or not task_id or len(task_id) > 200:
        raise HTTPException(status_code=400, detail="A valid action and actor are required")
    scope = {"id": task_id, "workspace_id": workspace_id}
    task = await db.outreach_tasks.find_one(scope)
    if not task:
        raise HTTPException(status_code=404, detail="Action review was not found")
    final_status = "not_sent_stopped" if request.decision == "not_sent_stop" else (
        "accepted" if task.get("task_type") == "send_email" else "completed"
    )
    existing_resolution = task.get("resolution") or {}
    if task.get("status") == final_status and existing_resolution.get("decision") == request.decision:
        return {"id": task_id, "status": final_status, "campaign_status": "paused", "already_resolved": True}
    if task.get("status") not in {"uncertain", "resolving"}:
        raise HTTPException(status_code=409, detail="This action is not awaiting review")
    if task.get("status") == "resolving" and existing_resolution.get("decision") != request.decision:
        raise HTTPException(status_code=409, detail="This action is already being resolved differently")

    campaign = await db.outreach_campaigns.find_one({
        "workspace_id": workspace_id, "id": task.get("campaign_id"),
    }, {"_id": 0, "status": 1})
    if not campaign or campaign.get("status") != "paused":
        raise HTTPException(status_code=409, detail="Pause the campaign before resolving this action")
    lead = await db.outreach_leads.find_one({
        "workspace_id": workspace_id, "id": task.get("lead_id"),
        "campaign_id": task.get("campaign_id"),
    }, {"_id": 0, "execution_state": 1, "assigned_account_id": 1})
    if not lead or lead.get("assigned_account_id") != task.get("account_id"):
        raise HTTPException(status_code=409, detail="The lead assignment changed; review it manually")
    expected_retried_state = (LeadExecutionState.QUEUED if request.decision == "confirmed_sent"
                              else LeadExecutionState.FAILED)
    allowed_states = {LeadExecutionState.WAITING_TRIGGER, LeadExecutionState.REPLIED}
    if task.get("status") == "resolving":
        # A previous attempt may have updated the lead just before this
        # request failed. Let the same audited decision finish idempotently.
        allowed_states.add(expected_retried_state)
    if lead.get("execution_state") not in allowed_states:
        raise HTTPException(status_code=409, detail="The lead state changed; review it manually")
    if request.decision == "not_sent_stop" and lead.get("execution_state") == LeadExecutionState.REPLIED:
        raise HTTPException(status_code=409, detail="A replying lead cannot be marked not sent")

    email_op = await _email_operation(db, workspace_id, task) if task.get("task_type") == "send_email" else None
    if task.get("task_type") == "send_email" and request.decision == "confirmed_sent":
        if not email_op or email_op.get("status") not in {"uncertain", "dispatching", "accepted"}:
            raise HTTPException(status_code=409, detail="Email send record is missing or conflicts with confirmation")
    if email_op and request.decision == "not_sent_stop" and email_op.get("status") == "accepted":
        raise HTTPException(status_code=409, detail="Provider already accepted this email; it cannot be marked not sent")

    now = datetime.now(timezone.utc)
    resolution = existing_resolution if task.get("status") == "resolving" else {
        "decision": request.decision, "source": "human_assertion", "actor_id": actor_id,
        "evidence_note": request.evidence_note, "recorded_at": now,
    }
    if task.get("status") == "uncertain":
        claimed = await db.outreach_tasks.find_one_and_update(
            {**scope, "status": "uncertain"},
            {"$set": {"status": "resolving", "resolution": resolution, "updated_at": now}},
        )
        if not claimed:
            raise HTTPException(status_code=409, detail="Another reviewer changed this action")

    # Keep `resolving` as a visible, non-retryable state until every dependent
    # record has been updated. Retrying the same decision completes it.
    if email_op and email_op.get("status") != "accepted":
        operation_scope = {"_id": email_op["_id"], "workspace_id": workspace_id,
                           "status": {"$in": ["uncertain", "dispatching"]}}
        operation_updates = {
            "status": "accepted" if request.decision == "confirmed_sent" else "not_sent_stopped",
            "resolution": resolution, "updated_at": now,
        }
        if request.decision == "confirmed_sent":
            operation_updates["acceptance_source"] = "human_assertion"
            operation_updates["accepted_at"] = email_op.get("created_at") or now
        updated = await db.outreach_email_operations.update_one(
            operation_scope, {"$set": operation_updates},
        )
        if not getattr(updated, "matched_count", 0):
            current_op = await _email_operation(db, workspace_id, task)
            expected = operation_updates["status"]
            if not current_op or current_op.get("status") != expected or (current_op.get("resolution") or {}).get("decision") != request.decision:
                raise HTTPException(status_code=409, detail="Email operation changed during review")

    if lead.get("execution_state") == LeadExecutionState.WAITING_TRIGGER:
        if request.decision == "confirmed_sent":
            lead_changes = {"execution_state": LeadExecutionState.QUEUED,
                            "next_action_due_at": now, "updated_at": now}
        else:
            lead_changes = {"execution_state": LeadExecutionState.FAILED,
                            "failure_reason": "An admin stopped this lead after reviewing an uncertain action.",
                            "next_action_due_at": None, "updated_at": now}
        updated = await db.outreach_leads.update_one(
            {"workspace_id": workspace_id, "id": task.get("lead_id"),
             "campaign_id": task.get("campaign_id"), "execution_state": LeadExecutionState.WAITING_TRIGGER},
            {"$set": lead_changes, **({"$unset": {"failure_reason": ""}} if request.decision == "confirmed_sent" else {})},
        )
        if not getattr(updated, "matched_count", 0):
            raise HTTPException(status_code=409, detail="Lead state changed during review")

    updated = await db.outreach_tasks.update_one(
        {**scope, "status": "resolving", "resolution.decision": request.decision},
        {"$set": {"status": final_status, "resolution": resolution, "resolved_at": now, "updated_at": now}},
    )
    if not getattr(updated, "matched_count", 0):
        raise HTTPException(status_code=409, detail="Action state changed during review")
    return {"id": task_id, "status": final_status, "campaign_status": "paused", "already_resolved": False}
