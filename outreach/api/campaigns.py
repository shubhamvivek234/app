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
from outreach.models import (
    CampaignStatus,
    DailyLimits,
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


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    sender_account_ids: list[str] | None = None
    schedule: WorkingSchedule | None = None
    limits: DailyLimits | None = None


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
        db.outreach_campaigns.find({"user_id": user_id}).sort("created_at", -1),
        length=100,
    )
    for c in campaigns:
        c.pop("_id", None)
    return campaigns


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

    await db.outreach_campaigns.update_one({"id": campaign_id}, {"$set": updates})
    updated_doc = await db.outreach_campaigns.find_one({"id": campaign_id})
    updated_doc.pop("_id", None)
    return updated_doc


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
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

    senders = campaign.get("sender_account_ids", [])
    if not senders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot launch campaign without at least one assigned LinkedIn sender account.",
        )

    # 1. Distribute unassigned leads across sender pool (Round-Robin Pooling)
    unassigned_leads = await _fetch_cursor_docs(
        db.outreach_leads.find({"campaign_id": campaign_id, "assigned_account_id": None}),
        length=10000,
    )

    for i, lead in enumerate(unassigned_leads):
        assigned_sender = senders[i % len(senders)]
        await db.outreach_leads.update_one(
            {"id": lead["id"]},
            {"$set": {"assigned_account_id": assigned_sender}}
        )

    # 2. Mark Campaign as ACTIVE
    await db.outreach_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": CampaignStatus.ACTIVE, "updated_at": datetime.now(timezone.utc)}}
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
