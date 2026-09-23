"""
Phase 5: Campaigns API router for LinkedIn Outbound Engine.
Supports campaign CRUD, sender pooling allocation, working schedule updates, and launch/pause.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.dag_compiler import DAGCompiler
from outreach.models import (
    CampaignStatus,
    DailyLimits,
    LeadExecutionState,
    OutreachCampaign,
    WorkingSchedule,
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
    schedule: WorkingSchedule | None = None
    limits: DailyLimits | None = None


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
    user_id = current_user.get("user_id")
    campaigns = await _fetch_cursor_docs(
        db.outreach_campaigns.find({
            "user_id": user_id,
            "is_deleted": {"$ne": True},
        }).sort("created_at", -1),
        length=100,
    )
    for c in campaigns:
        c.pop("_id", None)
        # Dynamic lead count if not cached
        if not c.get("leads_count"):
            cnt = await db.outreach_leads.count_documents({"campaign_id": c.get("id")})
            c["leads_count"] = cnt
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
    user_id = current_user.get("user_id")
    workspace_id = current_user.get("default_workspace_id") or "default_ws"

    if req.campaign_id:
        existing = await db.outreach_campaigns.find_one({"id": req.campaign_id, "user_id": user_id})
        if existing:
            updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
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
                updates["schedule"] = req.schedule.model_dump()
            if req.limits is not None:
                updates["limits"] = req.limits.model_dump()

            await db.outreach_campaigns.update_one({"id": req.campaign_id}, {"$set": updates})
            doc = await db.outreach_campaigns.find_one({"id": req.campaign_id})
            doc.pop("_id", None)
            return doc

    # Assign sequential default name if not provided
    count = await db.outreach_campaigns.count_documents({"user_id": user_id})
    default_name = req.name or f"test{count + 1}"

    campaign_doc = OutreachCampaign(
        workspace_id=workspace_id,
        user_id=user_id,
        name=default_name,
        status=CampaignStatus.DRAFT,
        sender_account_ids=req.sender_account_ids or [],
        schedule=req.schedule or WorkingSchedule(),
        limits=req.limits or DailyLimits(),
        draft_step=req.draft_step or 1,
        draft_progress=req.draft_progress or 20,
        next_step_label=req.next_step_label or "Next: add your leads",
    ).model_dump()

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
    user_id = current_user.get("user_id")
    workspace_id = current_user.get("default_workspace_id") or "default_ws"

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
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.pop("_id", None)

    # Lead counts
    total_leads = await db.outreach_leads.count_documents({"campaign_id": campaign_id})
    contacted_leads = await db.outreach_leads.count_documents({
        "campaign_id": campaign_id,
        "execution_state": {"$in": ["invited", "connected", "messaged", "completed"]},
    })
    campaign["leads_count"] = total_leads
    campaign["leads_contacted"] = contacted_leads

    # Senders summary
    sender_ids = campaign.get("sender_account_ids", [])
    senders = []
    if sender_ids:
        acc_docs = await _fetch_cursor_docs(
            db.outreach_accounts.find({"id": {"$in": sender_ids}}),
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
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
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

    await db.outreach_campaigns.update_one({"id": campaign_id}, {"$set": updates})
    updated_doc = await db.outreach_campaigns.find_one({"id": campaign_id})
    updated_doc.pop("_id", None)
    return updated_doc


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Soft-deletes a campaign allowing reversible undo."""
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    await db.outreach_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"status": "deleted", "id": campaign_id, "name": campaign["name"]}


@router.post("/{campaign_id}/restore")
async def restore_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Restores a soft-deleted campaign (Undo action)."""
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    await db.outreach_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"is_deleted": False, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"status": "restored", "id": campaign_id, "name": campaign["name"]}


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
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
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
        if req.schedule:
            updates["schedule"] = req.schedule.model_dump() if hasattr(req.schedule, "model_dump") else req.schedule
            campaign["schedule"] = updates["schedule"]
        if req.daily_limits:
            updates["limits"] = req.daily_limits.model_dump() if hasattr(req.daily_limits, "model_dump") else req.daily_limits
            campaign["limits"] = updates["limits"]

    senders = campaign.get("sender_account_ids", [])
    if not senders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot launch campaign without at least one assigned LinkedIn sender account.",
        )

    # 1. Ensure Sequence DAG is compiled for this campaign
    seq = await db.outreach_sequences.find_one({"campaign_id": campaign_id})
    root_node_id = None
    if seq and isinstance(seq, dict) and seq.get("compiled_dag"):
        root_nodes = seq["compiled_dag"].get("root_node_ids", [])
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
        if root_node_id and not lead.get("current_node_id"):
            lead_updates["current_node_id"] = root_node_id
        await db.outreach_leads.update_one(
            {"id": lead["id"]},
            {"$set": lead_updates}
        )

    # 3. Mark Campaign as ACTIVE
    updates["status"] = CampaignStatus.ACTIVE
    await db.outreach_campaigns.update_one(
        {"id": campaign_id},
        {"$set": updates}
    )

    logger.info("Campaign %s launched with %s senders and %s leads pooled.", campaign_id, len(senders), len(unassigned_leads))
    return {
        "status": "launched",
        "campaign_id": campaign_id,
        "pooled_senders_count": len(senders),
        "allocated_leads_count": len(unassigned_leads),
    }


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Pauses sequence execution for the campaign."""
    user_id = current_user.get("user_id")
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    await db.outreach_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": CampaignStatus.PAUSED, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"status": "paused", "campaign_id": campaign_id}
