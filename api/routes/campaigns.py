"""
Campaigns API & Multi-Channel ROI Analytics.
Allows workspaces to organize, schedule, and measure multi-platform marketing initiatives.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, VerifiedUser
from utils.free_llm_router import FreeLLMRouter

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


class BlueprintPost(BaseModel):
    stage: str
    day_offset: int
    hook: str
    content: str
    suggested_platforms: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    call_to_action: str


class BlueprintRequest(BaseModel):
    themes: list[str] = Field(default_factory=list)
    custom_prompt: str | None = None


class BlueprintResponse(BaseModel):
    campaign_id: str
    campaign_name: str
    posts: list[BlueprintPost]
    provider: str
    model: str


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
    published_count: int = 0
    scheduled_count: int = 0
    draft_count: int = 0
    total_clicks: int = 0
    total_impressions: int = 0
    total_engagements: int = 0
    cpc: float = 0.0
    cpe: float = 0.0
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
        # Aggregate posts and statuses
        posts_cursor = db.posts.find(
            {"workspace_id": workspace_id, "campaign_id": cmp_id},
            {"_id": 0, "status": 1, "metrics": 1, "platform_results": 1},
        )
        posts = await posts_cursor.to_list(None)
        post_count = len(posts)
        published_count = sum(1 for p in posts if p.get("status") == "published")
        scheduled_count = sum(1 for p in posts if p.get("status") == "scheduled")
        draft_count = sum(1 for p in posts if p.get("status") in ("draft", "template"))

        # Aggregate clicks from short links tagged with this campaign
        links_cursor = db.short_links.find(
            {"workspace_id": workspace_id, "$or": [{"campaign_id": cmp_id}, {"utm_campaign": c["name"]}]},
            {"_id": 0, "clicks": 1, "click_count": 1, "clicks_count": 1},
        )
        links = await links_cursor.to_list(None)
        total_clicks = sum(l.get("clicks_count") or l.get("clicks") or l.get("click_count") or 0 for l in links)

        # Approximate engagements & impressions from posts
        total_impressions = 0
        total_engagements = 0
        for p in posts:
            m = p.get("metrics") or {}
            total_impressions += m.get("impressions", 0) or m.get("views", 0)
            total_engagements += m.get("engagements", 0) or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("retweets", 0))

        budget = c.get("budget")
        cpc = round(budget / total_clicks, 2) if (budget and total_clicks > 0) else 0.0
        cpe = round(budget / total_engagements, 2) if (budget and total_engagements > 0) else 0.0

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
            budget=budget,
            status=c.get("status", "active"),
            post_count=post_count,
            published_count=published_count,
            scheduled_count=scheduled_count,
            draft_count=draft_count,
            total_clicks=total_clicks,
            total_impressions=total_impressions,
            total_engagements=total_engagements,
            cpc=cpc,
            cpe=cpe,
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
        published_count=0,
        scheduled_count=0,
        draft_count=0,
        total_clicks=0,
        total_impressions=0,
        total_engagements=0,
        cpc=0.0,
        cpe=0.0,
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
        {"_id": 0, "id": 1, "content": 1, "platforms": 1, "status": 1, "scheduled_time": 1, "created_at": 1, "metrics": 1, "platform_results": 1},
    ).sort("created_at", -1).limit(100)
    posts = await posts_cursor.to_list(None)

    published_count = sum(1 for p in posts if p.get("status") == "published")
    scheduled_count = sum(1 for p in posts if p.get("status") == "scheduled")
    draft_count = sum(1 for p in posts if p.get("status") in ("draft", "template"))
    failed_count = sum(1 for p in posts if p.get("status") == "failed")
    status_breakdown = {
        "published": published_count,
        "scheduled": scheduled_count,
        "draft": draft_count,
        "failed": failed_count,
    }

    platform_breakdown: dict[str, int] = {}
    total_impressions = 0
    total_engagements = 0
    for p in posts:
        for plt in (p.get("platforms") or []):
            plt_key = str(plt).lower()
            platform_breakdown[plt_key] = platform_breakdown.get(plt_key, 0) + 1
        m = p.get("metrics") or {}
        total_impressions += m.get("impressions", 0) or m.get("views", 0)
        total_engagements += m.get("engagements", 0) or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("retweets", 0))

    # Short links linked to this campaign
    links_cursor = db.short_links.find(
        {"workspace_id": workspace_id, "$or": [{"campaign_id": campaign_id}, {"utm_campaign": campaign.get("name")}]},
        {"_id": 0},
    ).sort("created_at", -1).limit(50)
    short_links = await links_cursor.to_list(None)
    total_clicks = sum(l.get("clicks_count") or l.get("clicks") or l.get("click_count") or 0 for l in short_links)

    budget = campaign.get("budget")
    cpc = round(budget / total_clicks, 2) if (budget and total_clicks > 0) else 0.0
    cpe = round(budget / total_engagements, 2) if (budget and total_engagements > 0) else 0.0
    engagement_rate = round((total_engagements / total_impressions) * 100, 2) if total_impressions > 0 else 0.0

    return {
        "campaign": campaign,
        "posts": posts,
        "post_count": len(posts),
        "status_breakdown": status_breakdown,
        "platform_breakdown": platform_breakdown,
        "short_links": short_links,
        "metrics": {
            "total_impressions": total_impressions,
            "total_engagements": total_engagements,
            "total_clicks": total_clicks,
            "cpc": cpc,
            "cpe": cpe,
            "engagement_rate": engagement_rate,
        },
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

    posts_cursor = db.posts.find(
        {"workspace_id": workspace_id, "campaign_id": campaign_id},
        {"_id": 0, "status": 1},
    )
    posts = await posts_cursor.to_list(None)
    post_count = len(posts)
    published_count = sum(1 for p in posts if p.get("status") == "published")
    scheduled_count = sum(1 for p in posts if p.get("status") == "scheduled")
    draft_count = sum(1 for p in posts if p.get("status") in ("draft", "template"))

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
        published_count=published_count,
        scheduled_count=scheduled_count,
        draft_count=draft_count,
        total_clicks=0,
        total_impressions=0,
        total_engagements=0,
        cpc=0.0,
        cpe=0.0,
        created_at=updated.get("created_at", datetime.now(timezone.utc)),
        updated_at=updated.get("updated_at", datetime.now(timezone.utc)),
    )


def _generate_deterministic_blueprint(campaign: dict[str, Any]) -> list[BlueprintPost]:
    name = campaign.get("name", "New Campaign")
    desc = campaign.get("description") or f"Exciting new release and updates for {name}."
    platforms = campaign.get("target_platforms") or ["twitter", "linkedin"]
    tags = [t.strip("#") for t in (campaign.get("tags") or ["Growth", "Innovation", "Launch"])]
    hashtags = [f"#{t}" for t in tags[:4]]

    return [
        BlueprintPost(
            stage="Stage 1: Teaser & Problem",
            day_offset=1,
            hook=f"Something big is coming for {name}. Are you ready?",
            content=f"Most teams struggle with the very problem {name} was designed to solve.\n\nOver the last few months, we've been crafting something game-changing:\n→ {desc[:140]}\n\nDrop a comment if you want early access before public release! 👇\n\n{' '.join(hashtags)}",
            suggested_platforms=platforms,
            hashtags=hashtags,
            call_to_action="Reply or comment below for early beta VIP access",
        ),
        BlueprintPost(
            stage="Stage 2: Big Reveal & Launch",
            day_offset=3,
            hook=f"🚀 It's officially here: Introducing {name}!",
            content=f"Today, we are thrilled to officially launch {name}!\n\n{desc}\n\nKey highlights:\n✨ Built for performance & seamless workflow\n⚡ Cut repetitive friction by 50%\n🎯 Direct ROI and clear results\n\nCheck out the full release and get started today via the link in bio!\n\n{' '.join(hashtags)}",
            suggested_platforms=platforms,
            hashtags=hashtags,
            call_to_action="Click the link in bio to explore the launch today",
        ),
        BlueprintPost(
            stage="Stage 3: Deep Dive & Value",
            day_offset=5,
            hook=f"How does {name} actually work? Here's the inside breakdown:",
            content=f"A lot of you asked how {name} differs from traditional solutions.\n\nHere is a 3-step breakdown:\n1️⃣ Step 1: Instant setup with zero learning curve\n2️⃣ Step 2: Intelligent automation saves you hours every week\n3️⃣ Step 3: Actionable analytics prove your ROI\n\nWhich of these would make the biggest difference in your daily workflow?\n\n{' '.join(hashtags)}",
            suggested_platforms=platforms,
            hashtags=hashtags,
            call_to_action="Comment your favorite feature below",
        ),
        BlueprintPost(
            stage="Stage 4: Social Proof & Transformation",
            day_offset=7,
            hook=f"The early feedback on {name} is blowing us away:",
            content=f"\"Since adopting {name}, our efficiency increased by over 40% and our team saved 10+ hours in the first week alone.\"\n\nSeeing results like this is why we built {name}. Whether you are an agency, creator, or growing brand, {desc[:100]} is ready for you.\n\nTry it free today!\n\n{' '.join(hashtags)}",
            suggested_platforms=platforms,
            hashtags=hashtags,
            call_to_action="Start your free trial today and experience the difference",
        ),
        BlueprintPost(
            stage="Stage 5: Urgency & Final Call",
            day_offset=10,
            hook=f"⏳ Final call: Don't miss out on {name} launch perks!",
            content=f"Our launch special for {name} wraps up soon.\n\nIf you've been waiting for the right moment to upgrade your strategy, this is your sign:\n\n🔥 Full access to all premium features\n🔥 Priority onboarding & VIP support\n🔥 Locked-in founding member terms\n\nClaim your spot before the offer closes tonight!\n\n{' '.join(hashtags)}",
            suggested_platforms=platforms,
            hashtags=hashtags,
            call_to_action="Claim launch perks before midnight",
        ),
    ]


@router.post("/{campaign_id}/blueprint", response_model=BlueprintResponse)
async def generate_campaign_blueprint(
    campaign_id: str,
    body: BlueprintRequest,
    current_user: VerifiedUser,
    db: DB,
) -> BlueprintResponse:
    """
    Generates a structured 5-stage campaign social media blueprint using the Free LLM waterfall,
    with an immediate deterministic heuristic fallback.
    """
    workspace_id = _workspace_id(current_user)
    campaign = await db.campaigns.find_one({"id": campaign_id, "workspace_id": workspace_id})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    router_llm = FreeLLMRouter()
    system_prompt = (
        "You are an elite CMO and viral social media campaign strategist. "
        "Create a comprehensive 5-stage sequential social media content blueprint for marketing campaigns. "
        "You must output STRICT JSON format with a 'posts' array containing 5 objects. "
        "Each object must have keys: 'stage' (string), 'day_offset' (integer), 'hook' (string), "
        "'content' (full formatted post copy with spacing, emojis, line breaks), "
        "'suggested_platforms' (array of strings), 'hashtags' (array of strings starting with #), "
        "and 'call_to_action' (string)."
    )

    platforms_str = ", ".join(campaign.get("target_platforms") or ["Twitter/X", "LinkedIn"])
    tags_str = ", ".join(campaign.get("tags") or ["General"])
    user_prompt = f"""Generate a 5-stage high-converting social media campaign blueprint for:
Campaign Name: {campaign.get('name')}
Campaign Description / Goals: {campaign.get('description') or 'Multi-channel brand awareness and conversion'}
Target Platforms: {platforms_str}
Tags / Themes: {tags_str}
Additional Focus: {body.custom_prompt or 'Drive awareness, engagement, and conversions'}

Provide exactly 5 narrative stages:
1. Stage 1: Teaser & Problem (Day 1)
2. Stage 2: Big Reveal & Launch (Day 3)
3. Stage 3: Deep Dive & Value (Day 5)
4. Stage 4: Social Proof & Transformation (Day 7)
5. Stage 5: Urgency & Final Call (Day 10)

Respond strictly with JSON:
{{"posts": [...]}}"""

    provider = "fallback_heuristic"
    model = "deterministic_v1"
    parsed_posts: list[BlueprintPost] = []

    try:
        raw_text, prov, mdl = await router_llm.generate_text(
            system_message=system_prompt,
            user_prompt=user_prompt,
            response_json=True,
        )
        provider = prov
        model = mdl

        # Parse JSON
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        data = json.loads(cleaned)
        posts_raw = data.get("posts") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for idx, item in enumerate(posts_raw):
            if isinstance(item, dict) and "content" in item:
                parsed_posts.append(BlueprintPost(
                    stage=str(item.get("stage", f"Stage {idx + 1}")),
                    day_offset=int(item.get("day_offset", idx * 2 + 1)),
                    hook=str(item.get("hook", item["content"][:60])),
                    content=str(item.get("content")),
                    suggested_platforms=item.get("suggested_platforms") or campaign.get("target_platforms") or ["twitter", "linkedin"],
                    hashtags=item.get("hashtags") or [f"#{t}" for t in campaign.get("tags") or ["Growth"]],
                    call_to_action=str(item.get("call_to_action", "Learn more via link in bio")),
                ))
    except Exception as exc:
        logger.warning("Free LLM failed or produced non-JSON for campaign blueprint: %s", exc)

    if not parsed_posts or len(parsed_posts) < 3:
        parsed_posts = _generate_deterministic_blueprint(campaign)
        provider = "fallback_heuristic"
        model = "deterministic_v1"

    return BlueprintResponse(
        campaign_id=campaign_id,
        campaign_name=campaign["name"],
        posts=parsed_posts,
        provider=provider,
        model=model,
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
