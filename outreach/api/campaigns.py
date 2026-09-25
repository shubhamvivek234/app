"""
Phase 5: Campaigns API router for LinkedIn Outbound Engine.
Supports campaign CRUD, sender pooling allocation, working schedule updates, and launch/pause.
"""
import logging
from typing import Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.dag_compiler import DAGCompiler, contains_ai_prompt_token
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.models import (
    CampaignStatus,
    DailyLimits,
    LeadExecutionState,
    OutreachCampaign,
    WorkingSchedule,
    generate_uuid,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["LinkedIn Outreach Campaigns"])


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 10000) -> list[dict[str, Any]]:
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


async def _lead_metrics(db: AsyncIOMotorDatabase, campaign_ids: list[str]) -> dict[str, dict[str, int]]:
    if not campaign_ids:
        return {}
    docs = await _fetch_cursor_docs(db.outreach_leads.aggregate([
        {"$match": {"campaign_id": {"$in": campaign_ids}}},
        {"$group": {
            "_id": "$campaign_id",
            "leads_count": {"$sum": 1},
            "leads_contacted": {"$sum": {"$cond": [
                {"$or": [
                    {"$ne": [{"$ifNull": ["$last_action_at", None]}, None]},
                    {"$in": ["$execution_state", ["invited", "connected", "messaged", "completed", "accepted", "replied"]]},
                ]}, 1, 0,
            ]}},
            "acceptances_count": {"$sum": {"$cond": [
                {"$or": [{"$eq": ["$is_connected", True]}, {"$in": ["$execution_state", ["connected", "accepted"]]}]}, 1, 0,
            ]}},
            "replies_count": {"$sum": {"$cond": [
                {"$or": [{"$eq": ["$has_replied", True]}, {"$eq": ["$execution_state", "replied"]}]}, 1, 0,
            ]}},
        }},
    ]), length=100)
    return {doc["_id"]: {key: doc.get(key, 0) for key in (
        "leads_count", "leads_contacted", "acceptances_count", "replies_count",
    )} for doc in docs if doc.get("_id")}


def _user_id(current_user: dict) -> str:
    return str(current_user.get("user_id") or current_user.get("id") or current_user.get("_id") or "")


def _workspace_id(current_user: dict) -> str:
    return str(
        current_user.get("default_workspace_id")
        or current_user.get("current_workspace_id")
        or current_user.get("workspace_id")
        or _user_id(current_user)
        or "default_ws"
    )


def _campaign_filter(campaign_id: str, current_user: dict, include_deleted: bool = False) -> dict[str, Any]:
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)
    query = {
        "id": campaign_id,
        "$or": [
            {"user_id": user_id},
            {"workspace_id": workspace_id},
            {"workspace_id": user_id},  # legacy personal-workspace records
        ],
    }
    if not include_deleted:
        query["is_deleted"] = {"$ne": True}
    return query


class CreateCampaignRequest(BaseModel):
    name: str = Field(..., min_length=1)
    sender_account_ids: list[str] = Field(default_factory=list)
    schedule: WorkingSchedule = Field(default_factory=WorkingSchedule)
    limits: DailyLimits = Field(default_factory=DailyLimits)


class AutoDraftRequest(BaseModel):
    name: str | None = None
    campaign_id: str | None = None
    draft_step: int | None = 1
    draft_progress: int | None = 20
    next_step_label: str | None = "Next: add your leads"
    sender_account_ids: list[str] | None = None
    schedule: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    sender_account_ids: list[str] | None = None
    schedule: WorkingSchedule | None = None
    limits: DailyLimits | None = None
    draft_step: int | None = None
    draft_progress: int | None = None
    next_step_label: str | None = None


class LaunchCampaignRequest(BaseModel):
    name: str | None = None
    sender_account_ids: list[str] | None = None
    schedule: Any | None = None
    timezone: str | None = None
    daily_limits: Any | None = None
    status: str | None = None


@router.get("")
async def list_campaigns(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of campaigns with outbound KPI metrics matching Part 1, Image 2.
    """
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)
    campaigns = await _fetch_cursor_docs(
        db.outreach_campaigns.find({
            "$or": [
                {"user_id": user_id},
                {"workspace_id": workspace_id},
                {"workspace_id": user_id},
            ],
            "is_deleted": {"$ne": True},
        }).sort([("updated_at", -1), ("created_at", -1)]),
        length=100,
    )
    metrics_by_campaign = await _lead_metrics(db, [c.get("id") for c in campaigns if c.get("id")])
    for c in campaigns:
        c.pop("_id", None)
        metrics = metrics_by_campaign.get(c.get("id"), {})
        c.update(metrics)
        c.setdefault("leads_count", 0)
        c.setdefault("leads_contacted", 0)
        c.setdefault("acceptances_count", 0)
        c.setdefault("replies_count", 0)
    return campaigns


@router.post("/auto-draft")
async def auto_draft_campaign(
    req: AutoDraftRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Auto-persists a campaign draft immediately so work is never lost if user closes browser.
    """
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)

    if req.campaign_id:
        existing = await db.outreach_campaigns.find_one(_campaign_filter(req.campaign_id, current_user))
        if existing:
            updates: dict[str, Any] = {
                "updated_at": datetime.now(timezone.utc),
            }
            if req.name:
                updates["name"] = req.name
            if req.draft_step is not None:
                updates["draft_step"] = req.draft_step
            if req.draft_progress is not None:
                updates["draft_progress"] = req.draft_progress
            if req.next_step_label is not None:
                updates["next_step_label"] = req.next_step_label
            if req.sender_account_ids is not None:
                updates["sender_account_ids"] = req.sender_account_ids
            if req.schedule is not None:
                updates["schedule"] = req.schedule if isinstance(req.schedule, dict) else req.schedule.model_dump()
            if req.limits is not None:
                updates["limits"] = req.limits if isinstance(req.limits, dict) else req.limits.model_dump()

            await db.outreach_campaigns.update_one(_campaign_filter(req.campaign_id, current_user), {"$set": updates})
            doc = await db.outreach_campaigns.find_one(_campaign_filter(req.campaign_id, current_user))
            if doc:
                doc.pop("_id", None)
                return doc
        elif await db.outreach_campaigns.find_one({"id": req.campaign_id}):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Assign sequential default name if not provided
    count = await db.outreach_campaigns.count_documents({"user_id": user_id, "is_deleted": {"$ne": True}})
    default_name = req.name or f"test{count + 1}"

    schedule_data = req.schedule if isinstance(req.schedule, dict) else (req.schedule.model_dump() if req.schedule else WorkingSchedule().model_dump())
    limits_data = req.limits if isinstance(req.limits, dict) else (req.limits.model_dump() if req.limits else DailyLimits().model_dump())

    campaign_doc = {
        "id": req.campaign_id or generate_uuid(),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "name": default_name,
        "status": CampaignStatus.DRAFT.value,
        "sender_account_ids": req.sender_account_ids or [],
        "schedule": schedule_data,
        "limits": limits_data,
        "draft_step": req.draft_step or 1,
        "draft_progress": req.draft_progress or 20,
        "next_step_label": req.next_step_label or "Next: add your leads",
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    await db.outreach_campaigns.insert_one(campaign_doc)
    campaign_doc.pop("_id", None)
    return campaign_doc


@router.post("")
async def create_campaign(
    req: CreateCampaignRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Creates a new outreach campaign draft."""
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)

    campaign_doc = OutreachCampaign(
        workspace_id=workspace_id,
        user_id=user_id,
        name=req.name,
        status=CampaignStatus.DRAFT,
        sender_account_ids=req.sender_account_ids,
        schedule=req.schedule,
        limits=req.limits,
    ).model_dump()

    await db.outreach_campaigns.insert_one(campaign_doc)
    campaign_doc.pop("_id", None)
    return campaign_doc


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Returns single campaign details, funnel metrics, and linked senders."""
    user_id = _user_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.pop("_id", None)

    # Lead counts
    total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id})
    contacted_leads = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id,
        "$or": [
            {"last_action_at": {"$ne": None}},
            {"execution_state": {"$in": ["invited", "connected", "messaged", "completed", "accepted", "replied"]}},
        ],
    })
    acceptances = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id,
        "$or": [{"is_connected": True}, {"execution_state": {"$in": ["connected", "accepted"]}}],
    })
    replies = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id,
        "$or": [{"has_replied": True}, {"execution_state": "replied"}],
    })
    interested = campaign.get("interested_count", 0)
    campaign["leads_count"] = total_leads
    campaign["leads_contacted"] = contacted_leads
    campaign["acceptances_count"] = acceptances
    campaign["replies_count"] = replies
    campaign["interested_count"] = interested

    # Senders summary
    sender_ids = campaign.get("sender_account_ids", [])
    senders = []
    if sender_ids:
        acc_docs = await _fetch_cursor_docs(
            db.outreach_accounts.find({
                "id": {"$in": sender_ids},
                "$or": [
                    {"user_id": user_id},
                    {"workspace_id": _workspace_id(current_user)},
                    {"workspace_id": user_id},
                ],
            }),
            length=100,
        )
        senders = [
            {
                "id": a["id"],
                "account_name": a.get("account_name", "LinkedIn Sender"),
                "vanity_name": a.get("vanity_name", ""),
                "avatar_url": a.get("avatar_url"),
            }
            for a in acc_docs
        ]
    campaign["senders"] = senders

    # Sequence summary
    sequence = await db.outreach_sequences.find_one({"campaign_id": campaign_id})
    if sequence:
        sequence.pop("_id", None)
        campaign["sequence"] = sequence

    return campaign


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    req: UpdateCampaignRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Updates campaign parameters, schedule, or senders."""
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if req.name is not None:
        updates["name"] = req.name
    if req.sender_account_ids is not None:
        updates["sender_account_ids"] = req.sender_account_ids
    if req.schedule is not None:
        updates["schedule"] = req.schedule.model_dump()
    if req.limits is not None:
        updates["limits"] = req.limits.model_dump()
    if req.draft_step is not None:
        updates["draft_step"] = req.draft_step
    if req.draft_progress is not None:
        updates["draft_progress"] = req.draft_progress
    if req.next_step_label is not None:
        updates["next_step_label"] = req.next_step_label

    await db.outreach_campaigns.update_one(campaign_filter, {"$set": updates})
    updated_doc = await db.outreach_campaigns.find_one(campaign_filter)
    updated_doc.pop("_id", None)
    return updated_doc


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Soft-deletes a campaign allowing reversible undo with relational cascade cleanup."""
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    now = datetime.now(timezone.utc)
    # 1. Soft-delete campaign
    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": {"is_deleted": True, "updated_at": now}}
    )

    # 2. Cascade cancel all pending/queued/scheduled tasks to prevent unwanted execution
    await db.outreach_tasks.update_many(
        {"campaign_id": campaign_id, "status": {"$in": ["queued", "pending", "scheduled"]}},
        {"$set": {
            "status": "cancelled",
            "cancelled_due_to_campaign_delete": True,
            "updated_at": now,
        }}
    )

    # 3. Soft-unassign leads enrolled in this campaign
    await db.outreach_leads.update_many(
        {"campaign_id": campaign_id, "$or": [{"user_id": user_id}, {"workspace_id": _workspace_id(current_user)}, {"workspace_id": user_id}]},
        {"$set": {
            "pipeline_stage": "unassigned",
            "campaign_id": None,
            "previous_campaign_id": campaign_id,
            "updated_at": now,
        }}
    )

    # 4. Soft-delete associated sequence if any
    await db.outreach_sequences.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"is_deleted": True, "updated_at": now}}
    )

    return {"status": "deleted", "id": campaign_id, "name": campaign["name"]}


@router.post("/{campaign_id}/restore")
async def restore_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Restores a soft-deleted campaign and cascades reversal to tasks, leads, and sequences."""
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user, include_deleted=True)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    now = datetime.now(timezone.utc)
    # 1. Restore campaign
    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": {"is_deleted": False, "updated_at": now}}
    )

    # 2. Restore cancelled tasks that were halted by the deletion
    await db.outreach_tasks.update_many(
        {"campaign_id": campaign_id, "cancelled_due_to_campaign_delete": True},
        {
            "$set": {"status": "queued", "updated_at": now},
            "$unset": {"cancelled_due_to_campaign_delete": ""}
        }
    )

    # 3. Re-enroll unassigned leads back into the campaign
    await db.outreach_leads.update_many(
        {"previous_campaign_id": campaign_id, "$or": [{"user_id": user_id}, {"workspace_id": _workspace_id(current_user)}, {"workspace_id": user_id}], "campaign_id": None},
        {
            "$set": {"campaign_id": campaign_id, "pipeline_stage": "enrolled", "updated_at": now},
            "$unset": {"previous_campaign_id": ""}
        }
    )

    # 4. Restore sequence
    await db.outreach_sequences.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"is_deleted": False, "updated_at": now}}
    )

    return {"status": "restored", "id": campaign_id, "name": campaign["name"]}


@router.post("/{campaign_id}/duplicate")
async def duplicate_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Duplicates an existing campaign, including its settings, schedule, daily limits, 
    sender assignments, and sequence DAG, resetting status to draft and metrics to 0.
    """
    user_id = _user_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    new_id = generate_uuid()
    now = datetime.now(timezone.utc)
    original_name = campaign.get("name", "Campaign")
    copy_name = f"{original_name} (Copy)"

    new_campaign_doc = {
        "id": new_id,
        "workspace_id": campaign.get("workspace_id", "default_ws"),
        "user_id": user_id,
        "name": copy_name,
        "status": CampaignStatus.DRAFT.value,
        "sender_account_ids": list(campaign.get("sender_account_ids", [])),
        "schedule": dict(campaign.get("schedule", {})),
        "limits": dict(campaign.get("limits", {})),
        "draft_step": 2,
        "draft_progress": 60,
        "next_step_label": "Next: add your leads",
        "leads_count": 0,
        "leads_contacted": 0,
        "acceptances_count": 0,
        "replies_count": 0,
        "interested_count": 0,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }

    # If original campaign has an associated sequence, clone it for the new campaign
    seq = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "is_deleted": {"$ne": True}})
    if seq:
        new_seq_doc = {
            "campaign_id": new_id,
            "id": generate_uuid(),
            "user_id": user_id,
            "workspace_id": campaign.get("workspace_id", _workspace_id(current_user)),
            "nodes": seq.get("nodes", []),
            "edges": seq.get("edges", []),
            "tree": seq.get("tree"),
            "compiled_dag": seq.get("compiled_dag"),
            "created_at": now,
            "updated_at": now,
        }
        await db.outreach_sequences.insert_one(new_seq_doc)

    await db.outreach_campaigns.insert_one(new_campaign_doc)
    new_campaign_doc.pop("_id", None)
    return new_campaign_doc


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    req: LaunchCampaignRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Activates campaign and pools/distributes enrolled leads across assigned senders.
    """
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Apply any runtime parameters passed during launch
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if req:
        if req.name:
            updates["name"] = req.name
            campaign["name"] = req.name
        if req.sender_account_ids:
            updates["sender_account_ids"] = req.sender_account_ids
            campaign["sender_account_ids"] = req.sender_account_ids
        if req.schedule is not None:
            schedule = req.schedule.model_dump() if hasattr(req.schedule, "model_dump") else req.schedule
            if isinstance(schedule, list):
                schedule = {"timezone": req.timezone or "UTC", "days": schedule}
            elif isinstance(schedule, dict) and req.timezone:
                schedule = {**schedule, "timezone": req.timezone}
            updates["schedule"] = schedule
            campaign["schedule"] = schedule
        if req.daily_limits is not None:
            limits = req.daily_limits.model_dump() if hasattr(req.daily_limits, "model_dump") else req.daily_limits
            updates["limits"] = limits
            campaign["limits"] = limits

    senders = list(dict.fromkeys(campaign.get("sender_account_ids", [])))
    if not senders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot launch campaign without at least one assigned LinkedIn sender account.",
        )

    active_senders = await _fetch_cursor_docs(db.outreach_accounts.find({
        "id": {"$in": senders},
        "status": "active",
        "$or": [
            {"user_id": user_id},
            {"workspace_id": _workspace_id(current_user)},
            {"workspace_id": user_id},
        ],
    }), length=100)
    active_sender_ids = {account.get("id") for account in active_senders}
    if active_sender_ids != set(senders):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more selected LinkedIn sender accounts are unavailable. Re-select an active sender.",
        )

    if not OutboundRateLimiter.has_valid_working_window(campaign.get("schedule")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose at least one valid working-hours window before launching.",
        )

    try:
        campaign["limits"] = DailyLimits.model_validate(campaign.get("limits") or {}).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Daily limits are invalid: {exc}") from exc
    updates["limits"] = campaign["limits"]

    # 1. Ensure Sequence DAG is compiled for this campaign
    seq = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "is_deleted": {"$ne": True}})
    root_node_id = None
    if seq and isinstance(seq, dict) and seq.get("nodes"):
        if contains_ai_prompt_token(seq.get("nodes")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI prompt tokens are preview-only and are not generated during live sending. Replace them with finished message copy before launching.",
            )
        try:
            compiled = DAGCompiler.validate_and_compile(seq.get("nodes", []), seq.get("edges", []))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Sequence is invalid: {exc}") from exc
        unsupported = sorted({
            node.get("type") for node in seq.get("nodes", [])
            if node.get("type") not in {
                "visit_profile", "connection_request", "send_message", "like_last_post",
                "voice_note", "if_connected",
            }
        })
        if unsupported:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"These sequence steps are not supported by the campaign runner yet: {', '.join(unsupported)}. Remove or replace them before launching.",
            )
        await db.outreach_sequences.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"compiled_dag": compiled, "is_deleted": False, "updated_at": datetime.now(timezone.utc)}}
        )
        root_nodes = compiled.get("root_node_ids", [])
        if root_nodes:
            root_node_id = root_nodes[0]
    else:
        # Auto-compile default sequence template if not explicitly saved yet
        templates = DAGCompiler.get_prebuilt_templates()
        if templates:
            default_tpl = templates[0]
            try:
                compiled = DAGCompiler.validate_and_compile(default_tpl["nodes"], default_tpl["edges"])
                await db.outreach_sequences.update_one(
                    {"campaign_id": campaign_id},
                    {"$set": {
                        "campaign_id": campaign_id,
                        "nodes": default_tpl["nodes"],
                        "edges": default_tpl["edges"],
                        "compiled_dag": compiled,
                        "updated_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )
                if compiled.get("root_node_ids"):
                    root_node_id = compiled["root_node_ids"][0]
            except Exception as exc:
                logger.warning("Could not auto-compile default sequence on launch: %s", exc)

    # 2. Distribute unassigned leads across sender pool (Round-Robin Pooling) & initialize state
    total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id})
    if total_leads == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Add at least one lead before launching this campaign.")

    # An opt-in Engage list delays queued outreach until its last confirmed
    # interaction has had the configured warm-up window. It never auto-engages.
    workspace_id = _workspace_id(current_user)
    linked_lists = await _fetch_cursor_docs(db.outreach_engage_lists.find({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
    }), length=100)
    warmup_until = None
    warmed_urls: set[str] = set()
    for engage_list in linked_lists:
        list_id = engage_list["id"]
        contacts = await _fetch_cursor_docs(db.outreach_engage_contacts.find({
            "list_id": list_id, "workspace_id": workspace_id,
        }), length=10000)
        contact_urls = {contact.get("id"): normalize_linkedin_url(contact.get("profile_url", "")) for contact in contacts}
        engaged_posts = await _fetch_cursor_docs(db.outreach_engage_posts.find({
            "list_id": list_id, "workspace_id": workspace_id,
            "status": {"$in": ["liked", "commented"]},
        }), length=10000)
        if not engaged_posts:
            raise HTTPException(status_code=409, detail=(
                f"Engagement list '{engage_list.get('name', list_id)}' is linked to this campaign but has no confirmed likes or comments. "
                "Engage first or unlink the list before launch."
            ))
        for post in engaged_posts:
            profile_url = contact_urls.get(post.get("contact_id"))
            if not profile_url:
                continue
            action_times = [value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                            for field in ("liked_at", "commented_at")
                            if isinstance((value := post.get(field)), datetime)]
            # Legacy status-only rows cannot prove when engagement happened.
            if not action_times:
                continue
            last_action = max(action_times)
            if last_action < datetime.now(timezone.utc) - timedelta(days=7):
                continue
            warmed_urls.add(profile_url)
            due = last_action + timedelta(hours=int(engage_list.get("warmup_hours", 24)))
            warmup_until = max(warmup_until, due) if warmup_until else due
    if linked_lists:
        lead_urls = await _fetch_cursor_docs(db.outreach_leads.find({"campaign_id": campaign_id}), length=10000)
        missing = sum(normalize_linkedin_url(lead.get("linkedin_url", "")) not in warmed_urls for lead in lead_urls)
        if missing:
            raise HTTPException(status_code=409, detail=(
                f"{missing} campaign lead(s) have no confirmed engagement in the past seven days in the linked list(s). "
                "Warm them first or unlink the list before launch."
            ))

    unassigned_leads = await _fetch_cursor_docs(
        db.outreach_leads.find({"campaign_id": campaign_id, "assigned_account_id": None}),
        length=10000,
    )

    for i, lead in enumerate(unassigned_leads):
        assigned_sender = senders[i % len(senders)]
        lead_updates = {
            "assigned_account_id": assigned_sender,
            "execution_state": LeadExecutionState.QUEUED,
        }
        if warmup_until and warmup_until > datetime.now(timezone.utc):
            lead_updates["next_action_due_at"] = warmup_until
        if root_node_id and not lead.get("current_node_id"):
            lead_updates["current_node_id"] = root_node_id
        await db.outreach_leads.update_one(
            {"id": lead["id"]},
            {"$set": lead_updates}
        )

    # 3. Mark Campaign as ACTIVE
    updates["status"] = CampaignStatus.ACTIVE
    if warmup_until:
        updates["warmup_until"] = warmup_until
        if warmup_until > datetime.now(timezone.utc):
            await db.outreach_leads.update_many(
                {"campaign_id": campaign_id, "execution_state": LeadExecutionState.QUEUED,
                 "$or": [{"next_action_due_at": None}, {"next_action_due_at": {"$lt": warmup_until}}]},
                {"$set": {"next_action_due_at": warmup_until}},
            )
    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": updates}
    )

    logger.info("Campaign %s launched with %s senders and %s leads pooled.", campaign_id, len(senders), len(unassigned_leads))
    return {
        "status": "launched",
        "campaign_id": campaign_id,
        "pooled_senders_count": len(senders),
        "allocated_leads_count": len(unassigned_leads),
        "warmup_until": warmup_until.isoformat() if warmup_until else None,
    }


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Pauses sequence execution for the campaign."""
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": {"status": CampaignStatus.PAUSED, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"status": "paused", "campaign_id": campaign_id}
