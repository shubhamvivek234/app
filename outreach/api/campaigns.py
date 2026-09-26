"""
Phase 5: Campaigns API router for LinkedIn Outbound Engine.
Supports campaign CRUD, sender pooling allocation, working schedule updates, and launch/pause.
"""
import logging
import os
from typing import Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.dag_compiler import DAGCompiler, contains_ai_prompt_token
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.crypto import decrypt_secret
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


async def _lead_metrics(db: AsyncIOMotorDatabase, campaign_ids: list[str], workspace_id: str) -> dict[str, dict[str, int]]:
    if not campaign_ids:
        return {}
    docs = await _fetch_cursor_docs(db.outreach_leads.aggregate([
        {"$match": {"workspace_id": workspace_id, "campaign_id": {"$in": campaign_ids}}},
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
    query = {
        "id": campaign_id,
        "workspace_id": _workspace_id(current_user),
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
    next_step_label: str | None = "Next: configure sequence"
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


class ArmWarmupRequest(BaseModel):
    engage_list_id: str
    warmup_hours: int = Field(default=24, ge=24, le=48)


def conditional_auto_launch_enabled() -> bool:
    """Deliberate release gate; enabling requires a separate product/legal decision."""
    return os.getenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "false").lower() == "true"


def _canonical_profile(raw_url: str) -> str:
    return normalize_linkedin_url(raw_url).replace("https://www.linkedin.com/", "https://linkedin.com/")


async def _evaluate_warmup(
    campaign_id: str, workspace_id: str, db: AsyncIOMotorDatabase,
    now: datetime | None = None, required_list_id: str | None = None,
) -> dict[str, Any]:
    """Count only recent, timestamped confirmed actions against every current lead."""
    now = now or datetime.now(timezone.utc)
    linked_lists = await _fetch_cursor_docs(db.outreach_engage_lists.find({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
    }), length=100)
    if required_list_id:
        linked_lists = [item for item in linked_lists if item.get("id") == required_list_id]
    action_due_by_url: dict[str, datetime] = {}
    for engage_list in linked_lists:
        list_id = engage_list["id"]
        contacts = await _fetch_cursor_docs(db.outreach_engage_contacts.find({
            "list_id": list_id, "workspace_id": workspace_id,
        }), length=10000)
        contact_urls = {contact.get("id"): _canonical_profile(contact.get("profile_url", "")) for contact in contacts}
        posts = await _fetch_cursor_docs(db.outreach_engage_posts.find({
            "list_id": list_id, "workspace_id": workspace_id,
            "status": {"$in": ["liked", "commented"]},
        }), length=10000)
        for post in posts:
            profile_url = contact_urls.get(post.get("contact_id"))
            if not profile_url:
                continue
            action_times = [value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                            for field in ("liked_at", "commented_at")
                            if isinstance((value := post.get(field)), datetime)]
            if not action_times:
                continue
            last_action = max(action_times)
            if last_action < now - timedelta(days=7) or last_action > now + timedelta(minutes=5):
                continue
            due = last_action + timedelta(hours=int(engage_list.get("warmup_hours", 24)))
            action_due_by_url[profile_url] = max(action_due_by_url.get(profile_url, due), due)
    leads = await _fetch_cursor_docs(db.outreach_leads.find({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
    }), length=10000)
    lead_urls = [_canonical_profile(lead.get("linkedin_url", "")) for lead in leads]
    missing_count = sum(not profile or profile not in action_due_by_url for profile in lead_urls)
    if hasattr(db.outreach_leads, "count_documents"):
        total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id, "workspace_id": workspace_id})
        missing_count += max(0, total_leads - len(leads))
    cohort_due = [action_due_by_url[url] for url in lead_urls if url in action_due_by_url]
    ready_at = max(cohort_due) if cohort_due else None
    return {
        "linked_lists_count": len(linked_lists), "leads_count": len(leads),
        "missing_count": missing_count, "ready_at": ready_at,
        "ready": bool(linked_lists and leads and missing_count == 0 and ready_at and ready_at <= now),
    }


@router.get("/features/conditional-launch")
async def get_conditional_launch_feature(current_user: dict = Depends(get_current_user)):
    return {"enabled": conditional_auto_launch_enabled()}


@router.post("/{campaign_id}/arm-warmup")
async def arm_warmup_campaign(
    campaign_id: str,
    req: ArmWarmupRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not conditional_auto_launch_enabled():
        raise HTTPException(status_code=403, detail="Conditional auto-launch is not enabled for this deployment")
    workspace_id = _workspace_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.get("status") != CampaignStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft campaigns can be armed for warm-up")
    engage_list = await db.outreach_engage_lists.find_one({
        "id": req.engage_list_id, "workspace_id": workspace_id,
    })
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")
    if engage_list.get("campaign_id") not in (None, campaign_id):
        raise HTTPException(status_code=409, detail="Engagement list is already linked to another campaign")
    leads = await _fetch_cursor_docs(db.outreach_leads.find({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
    }), length=10000)
    if not leads or not campaign.get("sender_account_ids"):
        raise HTTPException(status_code=400, detail="Add leads and select a sender before arming auto-launch")
    sequence = await db.outreach_sequences.find_one({
        "campaign_id": campaign_id, "workspace_id": workspace_id, "is_deleted": {"$ne": True},
    })
    if not sequence or not sequence.get("nodes"):
        raise HTTPException(status_code=400, detail="Save a sequence before arming auto-launch")
    now = datetime.now(timezone.utc)
    result = await db.outreach_campaigns.update_one(
        {**campaign_filter, "status": CampaignStatus.DRAFT},
        {"$set": {
            "status": CampaignStatus.WARMING_UP.value, "auto_launch_enabled": False,
            "auto_launch_list_id": req.engage_list_id,
            "auto_launch_lead_ids": sorted(str(lead["id"]) for lead in leads),
            "auto_launch_sequence_updated_at": sequence.get("updated_at"),
            "auto_launch_armed_at": now, "auto_launch_error": "", "updated_at": now,
        }},
    )
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="Campaign changed while arming auto-launch")
    armed_filter = {**campaign_filter, "status": CampaignStatus.WARMING_UP.value,
                    "auto_launch_armed_at": now, "auto_launch_enabled": False}
    try:
        linked = await db.outreach_engage_lists.update_one(
            {"id": req.engage_list_id, "workspace_id": workspace_id,
             "campaign_id": {"$in": [None, campaign_id]}},
            {"$set": {"campaign_id": campaign_id, "warmup_hours": req.warmup_hours, "updated_at": now}},
        )
        if not (getattr(linked, "matched_count", 0) or getattr(linked, "modified_count", 0)):
            raise HTTPException(status_code=409, detail="Engagement list changed while linking it to this campaign")
        enabled = await db.outreach_campaigns.update_one(
            armed_filter, {"$set": {"auto_launch_enabled": True, "updated_at": datetime.now(timezone.utc)}},
        )
        if not enabled.modified_count:
            raise HTTPException(status_code=409, detail="Campaign changed before auto-launch could be armed")
    except Exception:
        # The worker only scans enabled campaigns. Roll back a partially linked attempt.
        await db.outreach_campaigns.update_one(armed_filter, {"$set": {
            "status": CampaignStatus.DRAFT.value, "auto_launch_enabled": False,
            "auto_launch_error": "Could not link the selected Engage list",
        }})
        raise
    return {"status": CampaignStatus.WARMING_UP.value, "campaign_id": campaign_id,
            "message": "Campaign is waiting for confirmed engagement from every lead and the full cooldown."}


@router.get("")
async def list_campaigns(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of campaigns with outbound KPI metrics matching Part 1, Image 2.
    """
    workspace_id = _workspace_id(current_user)
    campaigns = await _fetch_cursor_docs(
        db.outreach_campaigns.find({
            "workspace_id": workspace_id,
            "is_deleted": {"$ne": True},
        }).sort([("updated_at", -1), ("created_at", -1)]),
        length=100,
    )
    metrics_by_campaign = await _lead_metrics(db, [c.get("id") for c in campaigns if c.get("id")], workspace_id)
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
            if existing.get("status") in {CampaignStatus.ACTIVE, CampaignStatus.WARMING_UP}:
                raise HTTPException(status_code=409, detail="Pause the campaign before editing its draft settings")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Assign sequential default name if not provided
    count = await db.outreach_campaigns.count_documents({"workspace_id": workspace_id, "is_deleted": {"$ne": True}})
    default_name = req.name or f"Campaign {count + 1}"

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
        "next_step_label": req.next_step_label or "Next: configure sequence",
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
    workspace_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.pop("_id", None)

    # Lead counts
    total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id, "workspace_id": workspace_id})
    contacted_leads = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
        "$or": [
            {"last_action_at": {"$ne": None}},
            {"execution_state": {"$in": ["invited", "connected", "messaged", "completed", "accepted", "replied"]}},
        ],
    })
    acceptances = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
        "$or": [{"is_connected": True}, {"execution_state": {"$in": ["connected", "accepted"]}}],
    })
    replies = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id, "workspace_id": workspace_id,
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
                "workspace_id": workspace_id,
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
    sequence = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "workspace_id": workspace_id})
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
    if campaign.get("status") == CampaignStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Campaign is already active")
    if campaign.get("status") not in {CampaignStatus.DRAFT, CampaignStatus.PAUSED}:
        raise HTTPException(status_code=409, detail="Only draft or paused campaigns can be edited")

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
    deletion_updates = {"is_deleted": True, "auto_launch_enabled": False, "updated_at": now}
    if campaign.get("status") in {CampaignStatus.ACTIVE, CampaignStatus.WARMING_UP}:
        deletion_updates["status"] = CampaignStatus.PAUSED.value
    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": deletion_updates}
    )

    # 2. Cascade cancel all pending/queued/scheduled tasks to prevent unwanted execution
    await db.outreach_tasks.update_many(
        {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "status": {"$in": ["queued", "pending", "scheduled"]}},
        {"$set": {
            "status": "cancelled",
            "cancelled_due_to_campaign_delete": True,
            "updated_at": now,
        }}
    )

    # 3. Soft-unassign leads enrolled in this campaign
    await db.outreach_leads.update_many(
        {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)},
        {"$set": {
            "pipeline_stage": "unassigned",
            "campaign_id": None,
            "previous_campaign_id": campaign_id,
            "updated_at": now,
        }}
    )

    # 4. Soft-delete associated sequence if any
    await db.outreach_sequences.update_one(
        {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)},
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
    restore_updates = {"is_deleted": False, "auto_launch_enabled": False, "updated_at": now}
    if campaign.get("status") in {CampaignStatus.ACTIVE, CampaignStatus.WARMING_UP}:
        restore_updates["status"] = CampaignStatus.PAUSED.value
    await db.outreach_campaigns.update_one(
        campaign_filter,
        {"$set": restore_updates}
    )

    # 2. Restore cancelled tasks that were halted by the deletion
    await db.outreach_tasks.update_many(
        {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "cancelled_due_to_campaign_delete": True},
        {
            "$set": {"status": "queued", "updated_at": now},
            "$unset": {"cancelled_due_to_campaign_delete": ""}
        }
    )

    # 3. Re-enroll unassigned leads back into the campaign
    await db.outreach_leads.update_many(
        {"previous_campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "campaign_id": None},
        {
            "$set": {"campaign_id": campaign_id, "pipeline_stage": "enrolled", "updated_at": now},
            "$unset": {"previous_campaign_id": ""}
        }
    )

    # 4. Restore sequence
    await db.outreach_sequences.update_one(
        {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)},
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
        "draft_step": 1,
        "draft_progress": 20,
        "next_step_label": "Next: configure sequence",
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
    seq = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "is_deleted": {"$ne": True}})
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
    return await _launch_campaign_impl(campaign_id, req, current_user, db)


async def _launch_campaign_impl(
    campaign_id: str,
    req: LaunchCampaignRequest | None,
    current_user: dict,
    db: AsyncIOMotorDatabase,
    *,
    auto_launch_claim_id: str | None = None,
):
    """
    Activates campaign and pools/distributes enrolled leads across assigned senders.
    """
    user_id = _user_id(current_user)
    campaign_filter = _campaign_filter(campaign_id, current_user)
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.get("status") == CampaignStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Campaign is already active")
    allowed_statuses = {CampaignStatus.DRAFT, CampaignStatus.PAUSED}
    if auto_launch_claim_id:
        allowed_statuses.add(CampaignStatus.WARMING_UP)
    if campaign.get("status") not in allowed_statuses:
        raise HTTPException(status_code=409, detail="Only draft or paused campaigns can be launched")
    if campaign.get("status") == CampaignStatus.WARMING_UP and (
        not auto_launch_claim_id or not campaign.get("auto_launch_enabled")
        or campaign.get("auto_launch_claim_id") != auto_launch_claim_id
    ):
        raise HTTPException(status_code=409, detail="Warm-up activation was canceled or superseded")

    # Apply any runtime parameters passed during launch
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if req:
        if req.name:
            updates["name"] = req.name
            campaign["name"] = req.name
        if req.sender_account_ids is not None:
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
        "workspace_id": _workspace_id(current_user),
    }), length=100)
    mock_mode = os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}
    active_sender_ids = set()
    for account in active_senders:
        encrypted_cookie = account.get("session_cookie_enc") or account.get("encrypted_session_cookie")
        proxy_host = (account.get("proxy") or account.get("proxy_config") or {}).get("host")
        if not encrypted_cookie or (not mock_mode and (not account.get("jsession_id") or not proxy_host or proxy_host in {"127.0.0.1", "localhost"})):
            continue
        try:
            cookie = decrypt_secret(encrypted_cookie).removeprefix("li_at=")
        except Exception:
            continue
        if not cookie or (not mock_mode and cookie.startswith(("mock_", "test_"))):
            continue
        active_sender_ids.add(account.get("id"))
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
    seq = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "is_deleted": {"$ne": True}})
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
            {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)},
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
                    {"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)},
                    {"$set": {
                        "campaign_id": campaign_id,
                        "workspace_id": _workspace_id(current_user),
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
    total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user)})
    if total_leads == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Add at least one lead before launching this campaign.")
    if not root_node_id:
        raise HTTPException(status_code=400, detail="Save a valid sequence before launching this campaign.")

    # The same strict all-leads gate serves manual launch and conditional launch.
    workspace_id = _workspace_id(current_user)
    warmup = await _evaluate_warmup(
        campaign_id, workspace_id, db,
        required_list_id=campaign.get("auto_launch_list_id") if auto_launch_claim_id else None,
    )
    warmup_until = warmup["ready_at"]
    if auto_launch_claim_id and not warmup["linked_lists_count"]:
        raise HTTPException(status_code=409, detail="Conditional launch requires a linked Engage list")
    if warmup["linked_lists_count"] and warmup["missing_count"]:
        raise HTTPException(status_code=409, detail=(
            f"{warmup['missing_count']} campaign lead(s) have no confirmed engagement in the past seven days in the linked list(s). "
            "Warm them first or unlink the list before launch."
        ))
    if auto_launch_claim_id and not warmup["ready"]:
        raise HTTPException(status_code=409, detail="The full Engage warm-up cooldown has not elapsed")

    unassigned_leads = await _fetch_cursor_docs(
        db.outreach_leads.find({"campaign_id": campaign_id, "workspace_id": workspace_id, "assigned_account_id": None}),
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
            {"id": lead["id"], "workspace_id": workspace_id},
            {"$set": lead_updates}
        )

    # 3. Mark Campaign as ACTIVE
    updates["status"] = CampaignStatus.ACTIVE
    updates["auto_launch_enabled"] = False
    updates["auto_launch_claim_id"] = None
    if warmup_until:
        updates["warmup_until"] = warmup_until
        if warmup_until > datetime.now(timezone.utc):
            await db.outreach_leads.update_many(
                {"campaign_id": campaign_id, "workspace_id": workspace_id, "execution_state": LeadExecutionState.QUEUED,
                 "$or": [{"next_action_due_at": None}, {"next_action_due_at": {"$lt": warmup_until}}]},
                {"$set": {"next_action_due_at": warmup_until}},
            )
    final_filter = {**campaign_filter, "status": campaign["status"]}
    if auto_launch_claim_id:
        final_filter["auto_launch_claim_id"] = auto_launch_claim_id
        final_filter["auto_launch_enabled"] = True
    activated = await db.outreach_campaigns.update_one(final_filter, {"$set": updates})
    if not activated.modified_count:
        raise HTTPException(status_code=409, detail="Campaign changed before activation; no outreach will run")

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
        {"$set": {"status": CampaignStatus.PAUSED, "auto_launch_enabled": False,
                  "auto_launch_claim_id": None, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"status": "paused", "campaign_id": campaign_id}
