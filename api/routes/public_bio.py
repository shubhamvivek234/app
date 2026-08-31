import re
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, status

from api.deps import DB
from api.models.bio import (
    BioLeadSubscribeRequest,
    BioTrackRequest,
    PublicBioResponse,
    SeoConfig,
    ThemeConfig,
)

router = APIRouter(prefix="/public/bio", tags=["public-bio"])


def _is_block_active(block: dict, now: datetime) -> bool:
    if not block.get("active", True):
        return False
    schedule = block.get("schedule")
    if not schedule:
        return True

    start_at = schedule.get("start_at")
    end_at = schedule.get("end_at")

    if start_at:
        start_dt = start_at if isinstance(start_at, datetime) else datetime.fromisoformat(str(start_at).replace("Z", "+00:00"))
        if now < start_dt:
            return False

    if end_at:
        end_dt = end_at if isinstance(end_at, datetime) else datetime.fromisoformat(str(end_at).replace("Z", "+00:00"))
        if now > end_dt:
            return False

    return True


@router.get("/{handle}", response_model=PublicBioResponse)
async def get_public_bio_page(
    handle: str,
    db: DB,
) -> PublicBioResponse:
    cleaned_handle = handle.strip().lstrip("@").lower()
    page = await db.bio_pages.find_one({"handle": cleaned_handle, "published": True})

    if not page:
        # Check custom domain fallback
        page = await db.bio_pages.find_one({"custom_domain": cleaned_handle, "published": True})

    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bio page not found")

    now = datetime.now(timezone.utc)
    workspace_id = page["workspace_id"]

    # Increment view counter asynchronously
    await db.bio_pages.update_one({"_id": page["_id"]}, {"$inc": {"total_views": 1}})

    # Filter active blocks (respecting scheduling / expiration)
    raw_blocks = page.get("blocks", [])
    active_blocks = [b for b in raw_blocks if _is_block_active(b, now)]

    # If page contains feed_grid block, hydrate published posts
    has_feed_grid = any(b.get("type") == "feed_grid" for b in active_blocks)
    feed_posts = []

    if has_feed_grid:
        cursor = db.posts.find(
            {
                "workspace_id": workspace_id,
                "status": "published",
            },
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "content": 1,
                "platforms": 1,
                "media_urls": 1,
                "thumbnail_urls": 1,
                "published_at": 1,
                "platform_results": 1,
            }
        ).sort("published_at", -1).limit(12)
        raw_posts = await cursor.to_list(length=12)

        for p in raw_posts:
            # Pick first available media or thumbnail
            media_url = ""
            if p.get("thumbnail_urls") and len(p["thumbnail_urls"]) > 0:
                media_url = p["thumbnail_urls"][0]
            elif p.get("media_urls") and len(p["media_urls"]) > 0:
                media_url = p["media_urls"][0]

            # Pick target link from platform results or default
            post_link = ""
            results = p.get("platform_results") or {}
            for plat_data in results.values():
                if plat_data.get("post_url"):
                    post_link = plat_data["post_url"]
                    break

            feed_posts.append({
                "id": p.get("id"),
                "title": p.get("title") or (p.get("content") or "")[:40],
                "content": p.get("content", ""),
                "media_url": media_url,
                "post_url": post_link,
                "platforms": p.get("platforms", []),
                "published_at": p.get("published_at").isoformat() if p.get("published_at") else None,
            })

    return PublicBioResponse(
        handle=page["handle"],
        title=page.get("title", ""),
        bio=page.get("bio", ""),
        avatar_url=page.get("avatar_url", ""),
        verified_badge=page.get("verified_badge", False),
        theme=ThemeConfig(**(page.get("theme") or {})),
        social_links=page.get("social_links", []),
        blocks=active_blocks,
        feed_posts=feed_posts,
        seo=SeoConfig(**(page.get("seo") or {})),
    )


@router.post("/{handle}/track")
async def track_bio_interaction(
    handle: str,
    body: BioTrackRequest,
    request: Request,
    db: DB,
):
    cleaned_handle = handle.strip().lstrip("@").lower()
    page = await db.bio_pages.find_one({"handle": cleaned_handle})
    if not page:
        return {"success": False}

    now = datetime.now(timezone.utc)
    workspace_id = page["workspace_id"]

    if body.event_type == "click":
        # Increment total clicks
        await db.bio_pages.update_one({"_id": page["_id"]}, {"$inc": {"total_clicks": 1}})

        # Increment specific block click count if block_id provided
        if body.block_id:
            await db.bio_pages.update_one(
                {"_id": page["_id"], "blocks.id": body.block_id},
                {"$inc": {"blocks.$.click_count": 1}}
            )

    # Log granular analytics
    user_agent = request.headers.get("user-agent", "")
    device = "mobile" if "mobile" in user_agent.lower() or "iphone" in user_agent.lower() or "android" in user_agent.lower() else "desktop"

    await db.bio_analytics.insert_one({
        "_id": ObjectId(),
        "page_id": page["_id"],
        "workspace_id": workspace_id,
        "event_type": body.event_type,
        "block_id": body.block_id,
        "target_url": body.target_url,
        "referrer": body.referrer,
        "device": device,
        "timestamp": now,
    })

    return {"success": True}


@router.post("/{handle}/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_to_bio_newsletter(
    handle: str,
    body: BioLeadSubscribeRequest,
    db: DB,
):
    cleaned_handle = handle.strip().lstrip("@").lower()
    page = await db.bio_pages.find_one({"handle": cleaned_handle})
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bio page not found")

    email = body.email.strip().lower()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Valid email address is required")

    workspace_id = page["workspace_id"]
    now = datetime.now(timezone.utc)

    # Check if already subscribed
    existing = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": email})
    if not existing:
        await db.workspace_leads.insert_one({
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "page_id": page["_id"],
            "email": email,
            "source_block_id": body.source_block_id,
            "created_at": now,
        })

    return {"success": True, "message": "Subscribed successfully!"}
