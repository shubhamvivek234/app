"""
Phase 5: Campaigns API router for LinkedIn Outbound Engine.
Supports campaign CRUD, sender pooling allocation, working schedule updates, and launch/pause.
"""
from outreach.core.workspace_scope import workspace_scope
import logging
import os
from typing import Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core.dag_compiler import DAGCompiler, contains_ai_prompt_token
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.crypto import decrypt_secret
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.core.sequence_capabilities import sequence_capabilities, sequence_capability_map
from outreach.core.paid_access import get_active_entitlement, sender_is_ready
from outreach.core.sequence_versions import load_sequence
from outreach.core.activation import claim_activation, release_activation, activation_lead_filter
from outreach.core.campaign_readiness import assess as assess_readiness, launch_parameters
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


@router.get("/features/sequence-capabilities")
async def get_sequence_capabilities(current_user: dict = Depends(get_outreach_user)):
    """Editor capabilities; sender-specific launch checks happen on launch."""
    return {"capabilities": sequence_capabilities()}


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
    skip_team_campaign_leads: bool = False


class AutoDraftRequest(BaseModel):
    name: str | None = None
    campaign_id: str | None = None
    draft_step: int | None = 1
    draft_progress: int | None = 20
    next_step_label: str | None = "Next: configure sequence"
    sender_account_ids: list[str] | None = None
    schedule: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None
    skip_team_campaign_leads: bool | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    sender_account_ids: list[str] | None = None
    schedule: WorkingSchedule | None = None
    limits: DailyLimits | None = None
    skip_team_campaign_leads: bool | None = None
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
        "campaign_id": campaign_id, **workspace_scope(workspace_id),
    }), length=101)
    if len(linked_lists) > 100:
        raise ValueError("Warm-up source exceeds bounded review capacity")
    if required_list_id:
        linked_lists = [item for item in linked_lists if item.get("id") == required_list_id]
    action_due_by_url: dict[str, datetime] = {}
    for engage_list in linked_lists:
        list_id = engage_list["id"]
        contacts = await _fetch_cursor_docs(db.outreach_engage_contacts.find({
            "list_id": list_id, **workspace_scope(workspace_id),
        }), length=10001)
        if len(contacts) > 10000:
            raise ValueError("Warm-up contacts exceed bounded review capacity")
        contact_urls = {contact.get("id"): _canonical_profile(contact.get("profile_url", "")) for contact in contacts}
        posts = await _fetch_cursor_docs(db.outreach_engage_posts.find({
            "list_id": list_id, **workspace_scope(workspace_id),
            "status": {"$in": ["liked", "commented"]},
        }), length=10001)
        if len(posts) > 10000:
            raise ValueError("Warm-up actions exceed bounded review capacity")
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
        "campaign_id": campaign_id, **workspace_scope(workspace_id), "execution_state": {"$ne": "staged"},
    }), length=10001)
    if len(leads) > 10000:
        raise ValueError("Warm-up leads exceed bounded review capacity")
    lead_urls = [_canonical_profile(lead.get("linkedin_url", "")) for lead in leads]
    missing_count = sum(not profile or profile not in action_due_by_url for profile in lead_urls)
    if hasattr(db.outreach_leads, "count_documents"):
        total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id, **workspace_scope(workspace_id), "execution_state": {"$ne": "staged"}})
        missing_count += max(0, total_leads - len(leads))
    cohort_due = [action_due_by_url[url] for url in lead_urls if url in action_due_by_url]
    ready_at = max(cohort_due) if cohort_due else None
    return {
        "linked_lists_count": len(linked_lists), "leads_count": len(leads),
        "missing_count": missing_count, "ready_at": ready_at,
        "ready": bool(linked_lists and leads and missing_count == 0 and ready_at and ready_at <= now),
    }


@router.get("/features/conditional-launch")
async def get_conditional_launch_feature(current_user: dict = Depends(get_outreach_user)):
    return {"enabled": conditional_auto_launch_enabled()}


@router.post("/{campaign_id}/arm-warmup")
async def arm_warmup_campaign(
    campaign_id: str,
    req: ArmWarmupRequest,
    current_user: dict = require_outreach_permission('campaign:update'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not conditional_auto_launch_enabled():
        raise HTTPException(status_code=403, detail="Conditional auto-launch is not enabled for this deployment")
    workspace_id = _workspace_id(current_user)
    from outreach.core.suppression import mutate_suppression, SuppressionUnavailable

    async def apply(current):
        db = current
        campaign_filter = {**_campaign_filter(campaign_id, current_user), **workspace_scope(workspace_id)}
        campaign = await db.outreach_campaigns.find_one(campaign_filter)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign.get("status") != CampaignStatus.DRAFT:
            raise HTTPException(status_code=409, detail="Only draft campaigns can be armed for warm-up")
        if campaign.get("launch_claim_token"):
            raise HTTPException(409, "Wait for the current campaign launch outcome before arming warm-up.")
        engage_list = await db.outreach_engage_lists.find_one({
            "id": req.engage_list_id, **workspace_scope(workspace_id),
        })
        if not engage_list:
            raise HTTPException(status_code=404, detail="Engagement list not found")
        if engage_list.get("campaign_id") not in (None, campaign_id):
            raise HTTPException(status_code=409, detail="Engagement list is already linked to another campaign")
        leads = await _fetch_cursor_docs(db.outreach_leads.find({
            "campaign_id": campaign_id, **workspace_scope(workspace_id),
            "execution_state": {"$ne": "staged"},
        }), length=10001)
        if len(leads) > 10000:
            raise HTTPException(409, "This cohort exceeds the verified warm-up limit. Split the campaign first.")
        if not leads or not campaign.get("sender_account_ids"):
            raise HTTPException(status_code=400, detail="Add leads and select a sender before arming auto-launch")
        sequence = await load_sequence(db, workspace_id, campaign_id, campaign=campaign)
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
                {"id": req.engage_list_id, **workspace_scope(workspace_id),
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
    try:
        return await mutate_suppression(db, workspace_id, apply)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm this change. Reload before retrying.") from None


@router.get("")
async def list_campaigns(
    current_user: dict = Depends(get_outreach_user),
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
    current_user: dict = require_outreach_permission('campaign:create'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Auto-persists a campaign draft immediately so work is never lost if user closes browser.
    """
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)

    if req.campaign_id:
        draft_filter = {**_campaign_filter(req.campaign_id, current_user),
                        **workspace_scope(workspace_id), 'id.0': {'$exists': False}}
        existing = await db.outreach_campaigns.find_one(draft_filter)
        if existing:
            if existing.get('status') not in {CampaignStatus.DRAFT, CampaignStatus.PAUSED}:
                raise HTTPException(status_code=409, detail="Only draft or paused campaigns can be edited")
            revision = existing.get('authorization_revision', 0)
            if type(revision) is not int or revision < 0:
                raise HTTPException(status_code=409, detail="Campaign authorization requires review before editing")
            claim_until = existing.get('launch_claim_expires_at')
            if claim_until is not None:
                if not isinstance(claim_until, datetime):
                    raise HTTPException(status_code=409, detail="Campaign activation ownership requires review before editing")
                deadline = claim_until if claim_until.tzinfo else claim_until.replace(tzinfo=timezone.utc)
                if deadline > datetime.now(timezone.utc):
                    raise HTTPException(status_code=409, detail="Wait for the current campaign launch outcome before editing")
            elif existing.get('launch_claim_token'):
                raise HTTPException(status_code=409, detail="Campaign activation ownership requires review before editing")
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
            if req.skip_team_campaign_leads is not None:
                updates["skip_team_campaign_leads"] = bool(req.skip_team_campaign_leads)

            # The UI uses auto-draft for settings too. Match the observed native
            # record and authority so a suspended save cannot edit a later active
            # campaign or race an intake/sequence change and retain its revision.
            observed = {**draft_filter, 'status': existing['status']}
            if '_id' in existing:
                observed['_id'] = existing['_id']
            for field in ('authorization_revision', 'lead_admission_revision',
                          'launch_claim_token', 'launch_claim_expires_at'):
                observed[field] = existing[field] if field in existing else {'$exists': False}
            result = await db.outreach_campaigns.update_one(
                observed, {'$set': updates, '$inc': {'authorization_revision': 1}})
            if getattr(result, 'matched_count', 0) != 1:
                raise HTTPException(status_code=409, detail="Campaign changed while editing; reload it before saving")
            doc = await db.outreach_campaigns.find_one(draft_filter)
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
        "authorization_revision": 0,
        "sender_account_ids": req.sender_account_ids or [],
        "schedule": schedule_data,
        "limits": limits_data,
        "skip_team_campaign_leads": bool(req.skip_team_campaign_leads) if req.skip_team_campaign_leads is not None else False,
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
    current_user: dict = require_outreach_permission('campaign:create'),
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
        skip_team_campaign_leads=bool(req.skip_team_campaign_leads),
    ).model_dump()

    await db.outreach_campaigns.insert_one(campaign_doc)
    campaign_doc.pop("_id", None)
    return campaign_doc


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_outreach_user),
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
    interested = int(campaign.get("interested_count", 0) or 0)
    if hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "count_documents"):
        try:
            thread_interested = await db.outreach_inbox_threads.count_documents({
                "campaign_id": campaign_id, "workspace_id": workspace_id, "intent_tag": "interested",
            })
            if isinstance(thread_interested, int):
                interested = max(interested, thread_interested)
        except Exception as exc:
            logger.debug("Campaign interested threads count skipped for campaign=%s (%s)", campaign_id, type(exc).__name__)
    campaign["leads_count"] = total_leads
    campaign["leads_contacted"] = contacted_leads
    campaign["acceptances_count"] = acceptances
    campaign["replies_count"] = replies
    campaign["interested_count"] = interested

    # Sequence summary & per-step / per-sender activity breakdown
    sequence = await load_sequence(db, workspace_id, campaign_id, campaign=campaign)
    if sequence:
        sequence.pop("_id", None)
        campaign["sequence"] = sequence

    campaign_tasks: list[dict[str, Any]] = []
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        try:
            campaign_tasks = await _fetch_cursor_docs(
                db.outreach_tasks.find({"campaign_id": campaign_id, "workspace_id": workspace_id}),
                length=10000,
            )
        except Exception as exc:
            logger.debug("Campaign tasks fetch skipped for campaign=%s (%s)", campaign_id, type(exc).__name__)
            campaign_tasks = []

    campaign_leads: list[dict[str, Any]] = []
    if hasattr(db, "outreach_leads") and hasattr(db.outreach_leads, "find"):
        try:
            campaign_leads = await _fetch_cursor_docs(
                db.outreach_leads.find({"campaign_id": campaign_id, "workspace_id": workspace_id}),
                length=10000,
            )
        except Exception as exc:
            logger.debug("Campaign leads fetch skipped for campaign=%s (%s)", campaign_id, type(exc).__name__)
            campaign_leads = []

    step_performance: dict[str, dict[str, int]] = {}
    for t in campaign_tasks:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        node_key = t.get("step_id") or t.get("node_id") or (tid.split(":", 1)[1] if ":" in tid else None)
        if not node_key:
            continue
        bucket = step_performance.setdefault(str(node_key), {"completed": 0, "queued": 0, "failed": 0})
        st = t.get("status")
        if st in ("completed", "accepted", "skipped"):
            bucket["completed"] += 1
        elif st in ("queued", "preparing", "dispatching", "running", "pending"):
            bucket["queued"] += 1
        elif st == "failed":
            bucket["failed"] += 1
    for ld in campaign_leads:
        if not isinstance(ld, dict):
            continue
        cnode = ld.get("current_node_id")
        if cnode and ld.get("execution_state") in ("queued", "in_progress", "waiting_delay"):
            bucket = step_performance.setdefault(str(cnode), {"completed": 0, "queued": 0, "failed": 0})
            bucket["queued"] += 1
    campaign["step_performance"] = step_performance

    # Dripify 5-Stage Campaign Funnel Status Breakdown (Completed, Paused, Moving in Sequence, Waiting in Queue, Uploading/Staged)
    f_completed = 0
    f_paused = 0
    f_moving = 0
    f_queued = 0
    f_staged = 0
    list_buckets: dict[str, dict[str, int]] = {}
    lead_by_id: dict[str, dict[str, Any]] = {}
    for ld in campaign_leads:
        if not isinstance(ld, dict):
            continue
        lid = str(ld.get("id") or "")
        if lid:
            lead_by_id[lid] = ld
        ex_state = str(ld.get("execution_state") or "queued").lower()
        if ex_state in ("finished", "completed", "failed", "bounced") or ld.get("do_not_contact") is True:
            f_completed += 1
        elif ex_state in ("paused", "replied", "waiting_trigger") or ld.get("has_replied") is True:
            f_paused += 1
        elif ex_state in ("in_progress", "waiting_delay", "invited", "connected", "messaged", "accepted"):
            f_moving += 1
        elif ex_state == "staged":
            f_staged += 1
        else:
            f_queued += 1

        src_meta = ld.get("source_metadata") if isinstance(ld.get("source_metadata"), dict) else {}
        cohort_name = str(ld.get("list_name") or src_meta.get("list_name") or "").strip() or "Default Cohort"
        lb = list_buckets.setdefault(cohort_name, {"leads_count": 0, "contacted": 0, "accepted": 0, "replied": 0})
        lb["leads_count"] += 1
        if ld.get("last_action_at") or ex_state in ("invited", "connected", "messaged", "completed", "accepted", "replied"):
            lb["contacted"] += 1
        if ld.get("is_connected") is True or ex_state in ("connected", "accepted"):
            lb["accepted"] += 1
        if ld.get("has_replied") is True or ex_state == "replied":
            lb["replied"] += 1

    campaign["funnel_stages"] = {
        "completed": f_completed,
        "paused": f_paused,
        "moving": f_moving,
        "queued": f_queued,
        "staged": f_staged,
        "low_queue_warning": bool(campaign.get("status") == "active" and f_queued < 20),
    }

    list_performance: list[dict[str, Any]] = []
    for cname, counts in list_buckets.items():
        denom = counts["contacted"] or counts["leads_count"]
        list_performance.append({
            "list_name": cname,
            "leads_count": counts["leads_count"],
            "contacted": counts["contacted"],
            "accepted": counts["accepted"],
            "acceptance_rate": round((counts["accepted"] / denom) * 100, 1) if denom > 0 else None,
            "replied": counts["replied"],
            "reply_rate": round((counts["replied"] / denom) * 100, 1) if denom > 0 else None,
        })
    list_performance.sort(key=lambda item: item["leads_count"], reverse=True)
    campaign["list_performance"] = list_performance

    # Campaign Recent Activity Timeline (most recent 25 tasks hydrated with lead name & LinkedIn URL)
    def _task_ts(t: dict[str, Any]) -> str:
        val = t.get("completed_at") or t.get("updated_at") or t.get("created_at") or ""
        return val.isoformat() if isinstance(val, datetime) else str(val or "")

    recent_tasks = sorted(
        [t for t in campaign_tasks if isinstance(t, dict) and t.get("status") in ("completed", "accepted", "skipped", "failed")],
        key=_task_ts,
        reverse=True,
    )[:25]
    campaign_recent_activity: list[dict[str, Any]] = []
    for t in recent_tasks:
        lid = str(t.get("lead_id") or "")
        ld = lead_by_id.get(lid, {})
        lname = f"{ld.get('first_name', '')} {ld.get('last_name', '')}".strip() or ld.get("vanity_name") or "Lead"
        campaign_recent_activity.append({
            "id": str(t.get("id") or ""),
            "action_type": str(t.get("task_type") or t.get("action_type") or "action"),
            "status": str(t.get("status") or "completed"),
            "lead_id": lid,
            "lead_name": lname,
            "lead_company": ld.get("company_name") or "",
            "lead_linkedin_url": ld.get("linkedin_url") or "",
            "timestamp": _task_ts(t),
        })
    campaign["recent_activity"] = campaign_recent_activity

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
        for a in acc_docs:
            sid = a["id"]
            s_tasks = [t for t in campaign_tasks if isinstance(t, dict) and t.get("account_id") == sid and t.get("status") in ("completed", "accepted")]
            s_leads = [l for l in campaign_leads if isinstance(l, dict) and l.get("assigned_account_id") == sid]
            s_contacted = sum(1 for l in s_leads if l.get("last_action_at") or l.get("execution_state") in ("invited", "connected", "messaged", "completed", "accepted", "replied"))
            s_accepted = sum(1 for l in s_leads if l.get("is_connected") is True or l.get("execution_state") in ("connected", "accepted"))
            s_replied = sum(1 for l in s_leads if l.get("has_replied") is True or l.get("execution_state") == "replied")
            s_req_sent = sum(1 for t in s_tasks if t.get("task_type") == "connection_request")
            s_msg_sent = sum(1 for t in s_tasks if t.get("task_type") in ("send_message", "inmail", "voice_note"))
            denom = s_contacted or (s_req_sent + s_msg_sent)
            senders.append({
                "id": sid,
                "account_name": a.get("account_name", "LinkedIn Sender"),
                "vanity_name": a.get("vanity_name", ""),
                "avatar_url": a.get("avatar_url"),
                "contacted": s_contacted,
                "requests_sent": s_req_sent,
                "messages_sent": s_msg_sent,
                "acceptances": s_accepted,
                "replies": s_replied,
                "reply_rate": round((s_replied / denom) * 100, 1) if denom > 0 else None,
            })
        senders.sort(key=lambda s: (s.get("reply_rate") is not None, s.get("reply_rate") or 0, s.get("contacted") or 0), reverse=True)
    campaign["senders"] = senders

    return campaign


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    req: UpdateCampaignRequest,
    current_user: dict = require_outreach_permission('campaign:update'),
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
    if req.skip_team_campaign_leads is not None:
        updates["skip_team_campaign_leads"] = bool(req.skip_team_campaign_leads)
    if req.draft_step is not None:
        updates["draft_step"] = req.draft_step
    if req.draft_progress is not None:
        updates["draft_progress"] = req.draft_progress
    if req.next_step_label is not None:
        updates["next_step_label"] = req.next_step_label

    result = await db.outreach_campaigns.update_one(
        {**campaign_filter, "status": campaign["status"],
         "authorization_revision": campaign.get("authorization_revision", 0) if "authorization_revision" in campaign else {"$exists": False}},
        {"$set": updates, "$inc": {"authorization_revision": 1}},
    )
    if getattr(result, "matched_count", 0) == 0:
        raise HTTPException(status_code=409, detail="Campaign changed while editing; reload it before saving")
    updated_doc = await db.outreach_campaigns.find_one(campaign_filter)
    updated_doc.pop("_id", None)
    return updated_doc


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    request_id: str | None = None,
    expected_workspace_id: str | None = None,
    current_user: dict = require_outreach_permission('campaign:delete'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Stop first, then resume bounded cleanup under the original deletion identity."""
    from outreach.core import campaign_deletion
    from outreach.core.suppression import SuppressionUnavailable
    from fastapi.responses import JSONResponse
    if expected_workspace_id is not None and expected_workspace_id != _workspace_id(current_user):
        raise HTTPException(409, "Workspace changed. Reopen the original workspace before continuing.")
    try:
        result = await campaign_deletion.delete(db, _workspace_id(current_user), campaign_id, request_id)
    except SuppressionUnavailable:
        raise HTTPException(503, "Deletion could not be confirmed. Retry the same request to finish cleanup.") from None
    return JSONResponse(result, status_code=202) if result["status"].endswith("_pending") else result


@router.post("/{campaign_id}/restore")
async def restore_campaign(
    campaign_id: str,
    request_id: str | None = None,
    expected_workspace_id: str | None = None,
    current_user: dict = require_outreach_permission('campaign:update'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Restore only the captured deletion cohort; keep all execution stopped."""
    from outreach.core import campaign_deletion
    from outreach.core.suppression import SuppressionUnavailable
    from fastapi.responses import JSONResponse
    if expected_workspace_id is not None and expected_workspace_id != _workspace_id(current_user):
        raise HTTPException(409, "Workspace changed. Reopen the original workspace before continuing.")
    try:
        result = await campaign_deletion.restore(db, _workspace_id(current_user), campaign_id, request_id)
    except SuppressionUnavailable:
        raise HTTPException(503, "Restoration could not be confirmed. Retry the same request.") from None
    return JSONResponse(result, status_code=202) if result["status"].endswith("_pending") else result


@router.post("/{campaign_id}/duplicate")
async def duplicate_campaign(
    campaign_id: str,
    current_user: dict = require_outreach_permission('campaign:create'),
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
        "workspace_id": campaign.get("workspace_id", _workspace_id(current_user)),
        "user_id": user_id,
        "name": copy_name,
        "status": CampaignStatus.DRAFT.value,
        "authorization_revision": 0,
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
    seq = await load_sequence(db, _workspace_id(current_user), campaign_id, campaign=campaign)
    if seq:
        pointer = generate_uuid()
        new_seq_doc = {
            "campaign_id": new_id,
            "id": generate_uuid(),
            "user_id": user_id,
            "workspace_id": campaign.get("workspace_id", _workspace_id(current_user)),
            "nodes": seq.get("nodes", []),
            "edges": seq.get("edges", []),
            "tree": seq.get("tree"),
            "compiled_dag": seq.get("compiled_dag"),
            "compiler_contract_version": 1,
            "version": 1,
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
        }
        seq_versions = getattr(db, "outreach_sequence_versions", None)
        if seq_versions is not None:
            await seq_versions.insert_one({**new_seq_doc, "_id": pointer})
            new_campaign_doc["sequence_version_id"] = pointer
        await db.outreach_sequences.insert_one(dict(new_seq_doc))

    await db.outreach_campaigns.insert_one(new_campaign_doc)
    new_campaign_doc.pop("_id", None)
    return new_campaign_doc


async def _read_campaign_preflight(campaign_id, request, current_user, db):
    workspace = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one({**_campaign_filter(campaign_id, current_user),
        **workspace_scope(workspace), 'id.0': {'$exists': False}})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    prospective, _ = launch_parameters(campaign, request)
    result = await assess_readiness(db, workspace, prospective, _evaluate_warmup)
    return result.report


@router.get("/{campaign_id}/preflight")
async def get_campaign_preflight(
    campaign_id: str,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Read-only stored launch prerequisites, never permission to send."""
    return await _read_campaign_preflight(campaign_id, None, current_user, db)


@router.post("/{campaign_id}/preflight")
async def preview_campaign_preflight(
    campaign_id: str,
    req: LaunchCampaignRequest,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Read-only assessment of the exact prospective launch parameters."""
    return await _read_campaign_preflight(campaign_id, req, current_user, db)


@router.get("/{campaign_id}/node-counts")
async def get_campaign_node_counts(
    campaign_id: str,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns real-time lead counts distributed across sequence nodes and execution states for a campaign.
    Uses optimized compound index [("campaign_id", 1), ("current_node_id", 1)].
    """
    workspace_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    node_pipeline = [
        {
            "$match": {
                "campaign_id": campaign_id,
                "workspace_id": workspace_id,
                "execution_state": "in_progress",
                "current_node_id": {"$ne": None},
            }
        },
        {"$group": {"_id": "$current_node_id", "count": {"$sum": 1}}},
    ]
    node_docs = await _fetch_cursor_docs(db.outreach_leads.aggregate(node_pipeline), length=1000)
    node_counts = {str(doc["_id"]): doc["count"] for doc in node_docs if doc.get("_id")}

    queued_pipeline = [
        {
            "$match": {
                "campaign_id": campaign_id,
                "workspace_id": workspace_id,
                "execution_state": "queued",
                "current_node_id": {"$ne": None},
            }
        },
        {"$group": {"_id": "$current_node_id", "count": {"$sum": 1}}},
    ]
    queued_docs = await _fetch_cursor_docs(db.outreach_leads.aggregate(queued_pipeline), length=1000)
    queued_node_counts = {str(doc["_id"]): doc["count"] for doc in queued_docs if doc.get("_id")}

    combined_node_counts = dict(node_counts)
    for node_id, q_count in queued_node_counts.items():
        combined_node_counts[node_id] = combined_node_counts.get(node_id, 0) + q_count

    state_pipeline = [
        {"$match": {"campaign_id": campaign_id, "workspace_id": workspace_id}},
        {"$group": {"_id": "$execution_state", "count": {"$sum": 1}}},
    ]
    state_docs = await _fetch_cursor_docs(db.outreach_leads.aggregate(state_pipeline), length=50)
    execution_state_counts = {str(doc["_id"]): doc["count"] for doc in state_docs if doc.get("_id")}

    total_leads = sum(execution_state_counts.values())

    return {
        "campaign_id": campaign_id,
        "node_counts": node_counts,
        "waiting_node_counts": combined_node_counts,
        "execution_state_counts": execution_state_counts,
        "total_leads": total_leads,
    }


@router.get("/{campaign_id}/sequence-step-leads")
async def get_sequence_step_leads(
    campaign_id: str,
    node_id: str = Query(..., min_length=1, max_length=200),
    status_filter: str | None = Query(None, description="Optional filter: 'queued' | 'in_progress' | 'completed' | 'failed'"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns detailed lead queue & execution history for a specific sequence node
    (queued leads, waiting condition leads, completed touches, and failed leads with failure reason + A/B variant).
    Powers click-through inspection on the Sequence Canvas.
    """
    ws_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # 1. Leads currently sitting at this node (queued / in_progress / paused / failed)
    lead_query: dict[str, Any] = {
        "campaign_id": campaign_id,
        "workspace_id": ws_id,
        "current_node_id": node_id,
    }
    if status_filter in {"queued", "in_progress", "paused", "failed"}:
        lead_query["execution_state"] = status_filter

    active_leads_docs = await _fetch_cursor_docs(
        db.outreach_leads.find(lead_query).sort("updated_at", -1), length=limit
    )

    # 2. Task execution history at this node (completed, failed, skipped, pending)
    task_docs: list[dict[str, Any]] = []
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        task_q: dict[str, Any] = {
            "campaign_id": campaign_id,
            "workspace_id": ws_id,
            "node_id": node_id,
        }
        if status_filter == "completed":
            task_q["status"] = "completed"
        elif status_filter == "failed":
            task_q["status"] = {"$in": ["failed", "skipped"]}
        task_docs = await _fetch_cursor_docs(
            db.outreach_tasks.find(task_q).sort("updated_at", -1), length=limit
        )

    # Hydrate lead info for tasks whose leads have already moved past this node
    seen_lead_ids = {str(l.get("id")) for l in active_leads_docs if l.get("id")}
    task_lead_ids = [
        str(t.get("lead_id")) for t in task_docs
        if t.get("lead_id") and str(t.get("lead_id")) not in seen_lead_ids
    ]
    extra_leads_map: dict[str, dict[str, Any]] = {}
    if task_lead_ids:
        extra_docs = await _fetch_cursor_docs(
            db.outreach_leads.find({
                "campaign_id": campaign_id,
                "workspace_id": ws_id,
                "id": {"$in": list(dict.fromkeys(task_lead_ids))[:200]},
            }),
            length=200,
        )
        extra_leads_map = {str(d.get("id")): d for d in extra_docs if d.get("id")}

    latest_task_by_lead: dict[str, dict[str, Any]] = {}
    for t in task_docs:
        lid = str(t.get("lead_id") or "")
        if lid and lid not in latest_task_by_lead:
            latest_task_by_lead[lid] = t

    items: list[dict[str, Any]] = []
    counts = {"queued": 0, "in_progress": 0, "completed": 0, "failed": 0}

    for ldoc in active_leads_docs:
        lid = str(ldoc.get("id") or "")
        state = str(ldoc.get("execution_state") or "queued")
        t_info = latest_task_by_lead.get(lid, {})
        ab_map = ldoc.get("ab_variants_assigned") if isinstance(ldoc.get("ab_variants_assigned"), dict) else {}
        variant_id = t_info.get("variant_id") or ab_map.get(node_id)
        bucket = "failed" if state == "failed" or t_info.get("status") == "failed" else (
            "in_progress" if state == "in_progress" else "queued"
        )
        counts[bucket] = counts.get(bucket, 0) + 1
        items.append({
            "lead_id": lid,
            "first_name": ldoc.get("first_name") or "",
            "last_name": ldoc.get("last_name") or "",
            "company_name": ldoc.get("company_name") or "",
            "job_title": ldoc.get("job_title") or "",
            "linkedin_url": ldoc.get("linkedin_url") or "",
            "step_status": bucket,
            "execution_state": state,
            "next_action_due_at": ldoc.get("next_action_due_at"),
            "failure_reason": t_info.get("error_reason") or t_info.get("skip_reason") or ldoc.get("pause_reason"),
            "ab_variant": variant_id,
            "updated_at": ldoc.get("updated_at") or ldoc.get("created_at"),
        })

    for t in task_docs:
        lid = str(t.get("lead_id") or "")
        if not lid or lid in seen_lead_ids:
            continue
        seen_lead_ids.add(lid)
        ldoc = extra_leads_map.get(lid, {})
        t_status = str(t.get("status") or "completed")
        bucket = "failed" if t_status in {"failed", "skipped"} else "completed"
        if status_filter and status_filter != bucket:
            continue
        counts[bucket] = counts.get(bucket, 0) + 1
        ab_map = ldoc.get("ab_variants_assigned") if isinstance(ldoc.get("ab_variants_assigned"), dict) else {}
        variant_id = t.get("variant_id") or ab_map.get(node_id)
        items.append({
            "lead_id": lid,
            "first_name": ldoc.get("first_name") or "",
            "last_name": ldoc.get("last_name") or "",
            "company_name": ldoc.get("company_name") or "",
            "job_title": ldoc.get("job_title") or "",
            "linkedin_url": ldoc.get("linkedin_url") or "",
            "step_status": bucket,
            "execution_state": ldoc.get("execution_state") or "in_progress",
            "next_action_due_at": ldoc.get("next_action_due_at"),
            "failure_reason": t.get("error_reason") or t.get("skip_reason"),
            "ab_variant": variant_id,
            "updated_at": t.get("updated_at") or t.get("executed_at") or t.get("created_at"),
        })

    return {
        "campaign_id": campaign_id,
        "node_id": node_id,
        "counts": counts,
        "leads": items[:limit],
    }


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    req: LaunchCampaignRequest | None = None,
    current_user: dict = require_outreach_permission('campaign:update'),
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
    campaign_filter = {**_campaign_filter(campaign_id, current_user), **workspace_scope(_workspace_id(current_user)),
                       "id.0": {"$exists": False}}
    campaign = await db.outreach_campaigns.find_one(campaign_filter)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    workspace_id = _workspace_id(current_user)
    original_campaign = campaign
    campaign, updates = launch_parameters(campaign, req)
    assessment = await assess_readiness(db, workspace_id, campaign, _evaluate_warmup,
                                      auto_claim=auto_launch_claim_id)
    if not assessment.report['can_launch']:
        raise HTTPException(status_code=assessment.code, detail=assessment.report['blockers'][0])
    seq = assessment.sequence
    senders = list(dict.fromkeys(campaign['sender_account_ids']))
    capability_map = sequence_capability_map()
    needs_linkedin = any(capability_map.get(node.get('type'), {}).get('channel') == 'linkedin' for node in seq['nodes'])
    # Scoped key access remains a final launch check; preflight never opens KMS.
    if needs_linkedin:
        try:
            import asyncio
            from outreach.core.session_custody import account_session
            from outreach.core.proxy_custody import prepare_proxy, policy
            captured_policy = policy()
            for account in assessment.accounts:
                await asyncio.wait_for(account_session(account), timeout=5)
                prepared = await asyncio.wait_for(prepare_proxy(account['proxy'], workspace_id), timeout=5)
                if policy() != captured_policy or not prepared.matches(account['proxy'], workspace_id):
                    raise ValueError('Credential policy changed')
        except Exception:
            raise HTTPException(status_code=400, detail="Stored session or proxy credentials are unavailable; reconnect the sender") from None
    # Reobserve after asynchronous key access. This is advisory read validation,
    # not a cross-authority activation transaction; final worker gates still apply.
    latest = await db.outreach_campaigns.find_one(campaign_filter)
    if latest != original_campaign:
        raise HTTPException(status_code=409, detail="Campaign changed during launch preparation")
    latest, _ = launch_parameters(latest, req)
    refreshed = await assess_readiness(db, workspace_id, latest, _evaluate_warmup,
                                     auto_claim=auto_launch_claim_id)
    if not refreshed.report['can_launch']:
        raise HTTPException(status_code=refreshed.code, detail=refreshed.report['blockers'][0])
    if refreshed.sequence != seq or refreshed.accounts != assessment.accounts:
        raise HTTPException(status_code=409, detail="Sequence or sender changed during launch preparation")
    campaign['limits'] = assessment.limits
    updates.update({'limits': campaign['limits'], 'updated_at': datetime.now(timezone.utc)})
    root_node_id = seq['compiled_dag']['root_node_ids'][0]
    warmup_until = refreshed.warmup['ready_at']
    from outreach.core.sequence_preview import successor_fields
    root_started_at = datetime.now(timezone.utc)
    root_base = max(root_started_at, warmup_until) if warmup_until else root_started_at
    root_due = successor_fields(seq['compiled_dag'], root_node_id, root_base)['next_action_due_at']

    # Freeze legacy/default sequence data before publishing authorization.
    pointer = campaign.get("sequence_version_id")
    if not pointer:
        pointer = generate_uuid()
        await db.outreach_sequence_versions.insert_one({
            **seq, "_id": pointer, "version": seq.get("version", 1), "is_deleted": False,
        })
    activation = await claim_activation(db, campaign, sequence_version_id=pointer)
    if not activation:
        raise HTTPException(status_code=409, detail="Campaign changed or another launch is preparing it")
    revision = activation["revision"]
    try:
        from outreach.core import sequence_continuity
        version = sequence_continuity.current_version(seq)
        if version is None:
            raise HTTPException(409, sequence_continuity.VERSION_HOLD)
        # A superseded launcher cannot overwrite a newer lead binding.
        # Retained progress cannot acquire a different version, even if its
        # public step ID survived a content/type/timing edit. Terminal history
        # keeps its original authorization and version.
        await db.outreach_leads.update_many(
            {'$and': [activation_lead_filter(workspace_id, campaign_id, revision),
                      sequence_continuity.outstanding_scope(workspace_id, campaign_id),
                      sequence_continuity.binding_candidates(version, [root_node_id], list(seq['compiled_dag']['nodes']))]},
            {"$set": {"authorized_revision": revision, "sequence_version": version}},
        )
        if await db.outreach_leads.find_one(sequence_continuity.version_conflicts(
                workspace_id, campaign_id, version, [root_node_id], list(seq['compiled_dag']['nodes']))):
            raise HTTPException(409, sequence_continuity.VERSION_HOLD)
        await db.outreach_leads.update_many(
            {"workspace_id": workspace_id, "campaign_id": campaign_id, "authorized_revision": revision,
             "current_node_id": None, "has_replied": {"$ne": True},
             "execution_state": {"$in": ["queued", "waiting_delay"]}},
            {"$set": {"current_node_id": root_node_id, "next_action_due_at": root_due}},
        )
        from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY
        unassigned_leads = await _fetch_cursor_docs(
            db.outreach_leads.find({"campaign_id": campaign_id, "workspace_id": workspace_id,
                                   "authorized_revision": revision, "assigned_account_id": None,
                                   "execution_state": {"$ne": "staged"}, "$nor": [SEARCH_PROVENANCE_QUERY]}),
            length=10000,
        )
        for i, lead in enumerate(unassigned_leads):
            lead_updates = {"assigned_account_id": senders[i % len(senders)],
                            "execution_state": LeadExecutionState.QUEUED}
            if warmup_until and warmup_until > datetime.now(timezone.utc):
                old_due = lead.get("next_action_due_at")
                if isinstance(old_due, datetime) and old_due.tzinfo is None:
                    old_due = old_due.replace(tzinfo=timezone.utc)
                lead_updates["next_action_due_at"] = max(warmup_until, old_due) if isinstance(old_due, datetime) else warmup_until
            if lead.get("current_node_id") is None:
                lead_updates["current_node_id"] = root_node_id
                lead_updates["next_action_due_at"] = root_due
            await db.outreach_leads.update_one(
                {"id": lead["id"], "workspace_id": workspace_id, "campaign_id": campaign_id,
                 "authorized_revision": revision, "assigned_account_id": None, "has_replied": {"$ne": True},
                 "execution_state": {"$nin": ["staged", "replied", "finished", "bounced", "failed"]},
                 "$nor": [SEARCH_PROVENANCE_QUERY]},
                {"$set": lead_updates},
            )
        updates.update({"authorization_revision": revision, "pause_reasons": [],
                        "status": CampaignStatus.ACTIVE, "pause_reason": None,
                        "auto_launch_enabled": False, "auto_launch_claim_id": None})
        if warmup_until:
            updates["warmup_until"] = warmup_until
            if warmup_until > datetime.now(timezone.utc):
                await db.outreach_leads.update_many(
                    {"campaign_id": campaign_id, "workspace_id": workspace_id, "authorized_revision": revision,
                     "execution_state": LeadExecutionState.QUEUED, "has_replied": {"$ne": True},
                     "$or": [{"next_action_due_at": None}, {"next_action_due_at": {"$lt": warmup_until}}]},
                    {"$set": {"next_action_due_at": warmup_until}},
                )
        final_filter = {**campaign_filter, "status": campaign["status"], "authorization_revision": revision,
                        "launch_claim_token": activation["token"], "sequence_version_id": pointer,
                        "launch_claim_expires_at": {"$gt": datetime.now(timezone.utc)}}
        if auto_launch_claim_id:
            final_filter.update({"auto_launch_claim_id": auto_launch_claim_id, "auto_launch_enabled": True})
        activated = await db.outreach_campaigns.update_one(final_filter, {"$set": updates})
        if not activated.modified_count:
            raise HTTPException(status_code=409, detail="Campaign changed before activation; no outreach will run")
    finally:
        await release_activation(db, workspace_id, campaign_id, activation["token"])

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
    current_user: dict = require_outreach_permission('campaign:update'),
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
                  "auto_launch_claim_id": None, "updated_at": datetime.now(timezone.utc)},
         "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "operator_pause"}}
    )
    return {"status": "paused", "campaign_id": campaign_id}
