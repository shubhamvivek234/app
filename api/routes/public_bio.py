import re
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, status

from api.deps import DB
from api.models.bio import (
    BioFeedbackRequest,
    BioLeadSubscribeRequest,
    BioPollVoteRequest,
    BioTrackRequest,
    PublicBioResponse,
    SeoConfig,
    ThemeConfig,
)
from api.routes.automations import dispatch_automation_event

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

    # A/B Testing: Split traffic if variants are configured and enabled
    active_variant_id = None
    ab_testing_enabled = bool(page.get("ab_testing_enabled", False))
    variants = page.get("variants", [])
    active_variants = [v for v in variants if v.get("is_active", True)]

    chosen_theme = page.get("theme") or {}
    if ab_testing_enabled and active_variants:
        import random
        # Split between control and variant
        roll = random.random() * 100
        first_variant = active_variants[0]
        weight = first_variant.get("weight", 50)
        if roll < weight:
            active_variant_id = first_variant.get("id")
            variant_blocks = first_variant.get("blocks", [])
            if variant_blocks:
                active_blocks = [b for b in variant_blocks if _is_block_active(b, now)]
            if first_variant.get("theme"):
                chosen_theme = first_variant.get("theme")
            # Increment variant view counter
            await db.bio_pages.update_one(
                {"_id": page["_id"], "variants.id": active_variant_id},
                {"$inc": {"variants.$.views": 1}}
            )

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

    sanitized_pages = []
    for pg in page.get("pages", []):
        pg_data = dict(pg)
        pg_blocks = pg_data.get("blocks", [])
        pg_data["blocks"] = [b for b in pg_blocks if _is_block_active(b, now)]
        sanitized_pages.append(pg_data)

    return PublicBioResponse(
        handle=page["handle"],
        title=page.get("title", ""),
        bio=page.get("bio", ""),
        avatar_url=page.get("avatar_url", ""),
        verified_badge=page.get("verified_badge", False),
        theme=ThemeConfig(**chosen_theme),
        social_links=page.get("social_links", []),
        blocks=active_blocks,
        pages=sanitized_pages,
        active_page_id=page.get("active_page_id", "home"),
        feed_posts=feed_posts,
        seo=SeoConfig(**(page.get("seo") or {})),
        active_variant_id=active_variant_id,
        ab_testing_enabled=ab_testing_enabled,
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

        if body.variant_id:
            await db.bio_pages.update_one(
                {"_id": page["_id"], "variants.id": body.variant_id},
                {"$inc": {"variants.$.clicks": 1}}
            )

    elif body.event_type == "conversion":
        if body.variant_id:
            await db.bio_pages.update_one(
                {"_id": page["_id"], "variants.id": body.variant_id},
                {"$inc": {"variants.$.conversions": 1}}
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
        "variant_id": body.variant_id,
        "device": device,
        "timestamp": now,
    })

    return {"success": True}


@router.post("/{handle}/poll/{block_id}")
async def vote_bio_poll(
    handle: str,
    block_id: str,
    body: BioPollVoteRequest,
    db: DB,
):
    """Cast a vote in a Quick Poll block on the bio page and return updated live tally."""
    cleaned_handle = handle.strip().lstrip("@").lower()
    page = await db.bio_pages.find_one({"handle": cleaned_handle})
    if not page:
        raise HTTPException(status_code=404, detail="Bio page not found")

    blocks = page.get("blocks", [])
    target_block = next((b for b in blocks if b.get("id") == block_id and b.get("type") == "poll"), None)
    if not target_block:
        raise HTTPException(status_code=404, detail="Poll block not found on this bio page")

    poll_options = target_block.get("poll_options", [])
    valid_option = any(opt.get("id") == body.option_id for opt in poll_options)
    if not valid_option:
        raise HTTPException(status_code=400, detail="Invalid poll option ID")

    # Increment votes
    updated_options = []
    total_votes = 0
    for opt in poll_options:
        votes = opt.get("votes", 0)
        if opt.get("id") == body.option_id:
            votes += 1
        total_votes += votes
        updated_options.append({
            "id": opt.get("id"),
            "text": opt.get("text", ""),
            "votes": votes,
        })

    for opt in updated_options:
        opt["percentage"] = round((opt["votes"] / total_votes * 100), 1) if total_votes > 0 else 0

    await db.bio_pages.update_one(
        {"_id": page["_id"], "blocks.id": block_id},
        {"$set": {"blocks.$.poll_options": updated_options}}
    )

    now = datetime.now(timezone.utc)
    await db.bio_analytics.insert_one({
        "_id": ObjectId(),
        "page_id": page["_id"],
        "workspace_id": page["workspace_id"],
        "event_type": "poll_vote",
        "block_id": block_id,
        "option_id": body.option_id,
        "variant_id": body.variant_id,
        "timestamp": now,
    })

    if body.variant_id:
        await db.bio_pages.update_one(
            {"_id": page["_id"], "variants.id": body.variant_id},
            {"$inc": {"variants.$.conversions": 1}}
        )

    return {
        "success": True,
        "total_votes": total_votes,
        "options": updated_options,
    }


@router.post("/{handle}/feedback")
async def submit_bio_feedback(
    handle: str,
    body: BioFeedbackRequest,
    db: DB,
):
    """Submit an NPS or star rating feedback on the bio page."""
    cleaned_handle = handle.strip().lstrip("@").lower()
    page = await db.bio_pages.find_one({"handle": cleaned_handle})
    if not page:
        raise HTTPException(status_code=404, detail="Bio page not found")

    if body.score < 1 or body.score > 10:
        raise HTTPException(status_code=400, detail="Score must be between 1 and 10")

    now = datetime.now(timezone.utc)
    workspace_id = page["workspace_id"]

    await db.bio_analytics.insert_one({
        "_id": ObjectId(),
        "page_id": page["_id"],
        "workspace_id": workspace_id,
        "event_type": "nps_rating",
        "score": body.score,
        "feedback": (body.feedback or "").strip()[:500],
        "block_id": body.block_id,
        "variant_id": body.variant_id,
        "timestamp": now,
    })

    if body.variant_id:
        await db.bio_pages.update_one(
            {"_id": page["_id"], "variants.id": body.variant_id},
            {"$inc": {"variants.$.conversions": 1}}
        )

    # Reactive trigger for Automations Engine
    try:
        await dispatch_automation_event(
            "feedback.received",
            workspace_id,
            {
                "score": body.score,
                "feedback": body.feedback,
                "handle": handle,
            },
            db,
        )
    except Exception as exc:
        pass

    return {
        "success": True,
        "message": "Thank you for your rating and feedback!",
    }


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
    name = (body.name or "").strip()
    phone = (body.phone or "").strip()
    tag = body.tag or "subscriber"

    # Check if already subscribed
    existing = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": email})
    if not existing:
        lead_doc = {
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "page_id": page["_id"],
            "email": email,
            "name": name,
            "phone": phone,
            "tag": tag,
            "source": "bio",
            "source_block_id": body.source_block_id,
            "created_at": now,
            "updated_at": now,
        }
        await db.workspace_leads.insert_one(lead_doc)
    else:
        update_set: dict = {"updated_at": now}
        if name and not existing.get("name"):
            update_set["name"] = name
        if phone and not existing.get("phone"):
            update_set["phone"] = phone
        await db.workspace_leads.update_one({"_id": existing["_id"]}, {"$set": update_set})

    if body.variant_id:
        await db.bio_pages.update_one(
            {"_id": page["_id"], "variants.id": body.variant_id},
            {"$inc": {"variants.$.conversions": 1}}
        )

    # Reactive trigger for Automations Engine (Cluster D)
    try:
        await dispatch_automation_event(
            "lead.created",
            workspace_id,
            {
                "email": email,
                "name": name,
                "phone": phone,
                "tag": tag,
                "source": "bio",
                "handle": handle,
            },
            db,
        )
    except Exception as exc:
        pass

    return {"success": True, "message": "Subscribed successfully!"}
