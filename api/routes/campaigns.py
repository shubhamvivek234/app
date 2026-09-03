"""
Campaigns API & Multi-Channel ROI Analytics.
Allows workspaces to organize, schedule, and measure multi-platform marketing initiatives.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, VerifiedUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _workspace_id(current_user: dict) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(None, max_length=1000)
    color: str = Field("#6366f1", max_length=20)
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_platforms: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    budget: float | None = None
    status: str = Field("active")  # "active" | "draft" | "completed" | "archived"


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    color: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_platforms: list[str] | None = None
    tags: list[str] | None = None
    budget: float | None = None
    status: str | None = None


class CampaignResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    name: str
    description: str | None = None
    color: str = "#6366f1"
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_platforms: list[str] = []
    tags: list[str] = []
    budget: float | None = None
    status: str = "active"
    post_count: int = 0
    total_clicks: int = 0
    total_impressions: int = 0
    total_engagements: int = 0
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    current_user: CurrentUser,
    db: DB,
    status: str | None = None,
) -> list[CampaignResponse]:
    workspace_id = _workspace_id(current_user)
    query: dict[str, Any] = {"workspace_id": workspace_id}
    if status:
        query["status"] = status

    cursor = db.campaigns.find(query, {"_id": 0}).sort("created_at", -1)
    campaigns = await cursor.to_list(None)

    results: list[CampaignResponse] = []
    for c in campaigns:
        cmp_id = c["id"]
        # Count associated posts
        post_count = await db.posts.count_documents({"workspace_id": workspace_id, "campaign_id": cmp_id})
        
        # Aggregate clicks from short links tagged with this campaign
        links_cursor = db.short_links.find(
            {"workspace_id": workspace_id, "$or": [{"campaign_id": cmp_id}, {"utm_campaign": c["name"]}]},
            {"_id": 0, "clicks": 1, "click_count": 1},
        )
        links = await links_cursor.to_list(None)
        total_clicks = sum(l.get("clicks") or l.get("click_count") or 0 for l in links)

        # Approximate engagements & impressions from posts platform_results
        posts_cursor = db.posts.find(
            {"workspace_id": workspace_id, "campaign_id": cmp_id},
            {"_id": 0, "metrics": 1, "platform_results": 1},
        )
        posts = await posts_cursor.to_list(None)
        total_impressions = 0
        total_engagements = 0
        for p in posts:
            m = p.get("metrics") or {}
            total_impressions += m.get("impressions", 0) or m.get("views", 0)
            total_engagements += m.get("engagements", 0) or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0))

        results.append(CampaignResponse(
            id=cmp_id,
            workspace_id=workspace_id,
            user_id=c.get("user_id", current_user["user_id"]),
            name=c["name"],
            description=c.get("description"),
            color=c.get("color", "#6366f1"),
            start_date=c.get("start_date"),
            end_date=c.get("end_date"),
            target_platforms=c.get("target_platforms") or [],
            tags=c.get("tags") or [],
            budget=c.get("budget"),
            status=c.get("status", "active"),
            post_count=post_count,
            total_clicks=total_clicks,
            total_impressions=total_impressions,
            total_engagements=total_engagements,
            created_at=c.get("created_at", datetime.now(timezone.utc)),
            updated_at=c.get("updated_at", datetime.now(timezone.utc)),
        ))

    return results


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: VerifiedUser,
    db: DB,
) -> CampaignResponse:
    workspace_id = _workspace_id(current_user)
    user_id = current_user["user_id"]
    cmp_id = f"cmp_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "id": cmp_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "name": body.name.strip(),
        "description": body.description.strip() if body.description else None,
        "color": body.color or "#6366f1",
        "start_date": body.start_date,
        "end_date": body.end_date,
        "target_platforms": body.target_platforms,
        "tags": body.tags,
        "budget": body.budget,
        "status": body.status or "active",
        "created_at": now,
        "updated_at": now,
    }

    await db.campaigns.insert_one(doc)

    return CampaignResponse(
        id=cmp_id,
        workspace_id=workspace_id,
        user_id=user_id,
        name=doc["name"],
        description=doc["description"],
        color=doc["color"],
        start_date=doc["start_date"],
        end_date=doc["end_date"],
        target_platforms=doc["target_platforms"],
        tags=doc["tags"],
        budget=doc["budget"],
        status=doc["status"],
        post_count=0,
        total_clicks=0,
        total_impressions=0,
        total_engagements=0,
        created_at=now,
        updated_at=now,
    )


@router.get("/{campaign_id}")
async def get_campaign_detail(
    campaign_id: str,
    current_user: CurrentUser,
    db: DB,
):
    workspace_id = _workspace_id(current_user)
    campaign = await db.campaigns.find_one({"id": campaign_id, "workspace_id": workspace_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Fetch linked posts
    posts_cursor = db.posts.find(
        {"workspace_id": workspace_id, "campaign_id": campaign_id},
        {"_id": 0, "id": 1, "content": 1, "platforms": 1, "status": 1, "scheduled_time": 1, "created_at": 1},
    ).sort("created_at", -1).limit(50)
    posts = await posts_cursor.to_list(None)

    return {
        "campaign": campaign,
        "posts": posts,
        "post_count": len(posts),
    }


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    current_user: VerifiedUser,
    db: DB,
) -> CampaignResponse:
    workspace_id = _workspace_id(current_user)
    existing = await db.campaigns.find_one({"id": campaign_id, "workspace_id": workspace_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        update_payload["name"] = body.name.strip()
    if body.description is not None:
        update_payload["description"] = body.description.strip()
    if body.color is not None:
        update_payload["color"] = body.color
    if body.start_date is not None:
        update_payload["start_date"] = body.start_date
    if body.end_date is not None:
        update_payload["end_date"] = body.end_date
    if body.target_platforms is not None:
        update_payload["target_platforms"] = body.target_platforms
    if body.tags is not None:
        update_payload["tags"] = body.tags
    if body.budget is not None:
        update_payload["budget"] = body.budget
    if body.status is not None:
        update_payload["status"] = body.status

    await db.campaigns.update_one({"id": campaign_id, "workspace_id": workspace_id}, {"$set": update_payload})
    updated = await db.campaigns.find_one({"id": campaign_id, "workspace_id": workspace_id}, {"_id": 0})

    post_count = await db.posts.count_documents({"workspace_id": workspace_id, "campaign_id": campaign_id})

    return CampaignResponse(
        id=campaign_id,
        workspace_id=workspace_id,
        user_id=updated.get("user_id", current_user["user_id"]),
        name=updated["name"],
        description=updated.get("description"),
        color=updated.get("color", "#6366f1"),
        start_date=updated.get("start_date"),
        end_date=updated.get("end_date"),
        target_platforms=updated.get("target_platforms") or [],
        tags=updated.get("tags") or [],
        budget=updated.get("budget"),
        status=updated.get("status", "active"),
        post_count=post_count,
        total_clicks=0,
        total_impressions=0,
        total_engagements=0,
        created_at=updated.get("created_at", datetime.now(timezone.utc)),
        updated_at=updated.get("updated_at", datetime.now(timezone.utc)),
    )


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    current_user: VerifiedUser,
    db: DB,
):
    workspace_id = _workspace_id(current_user)
    res = await db.campaigns.delete_one({"id": campaign_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Unlink posts
    await db.posts.update_many(
        {"workspace_id": workspace_id, "campaign_id": campaign_id},
        {"$set": {"campaign_id": None}},
    )
    return None
