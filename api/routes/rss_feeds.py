"""
RSS Feeds & Automations API.
Allows users to connect RSS/Atom feeds, configure auto-scheduling rules,
browse discovered articles, and share articles to social media.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, VerifiedUser
from utils.rss_parser import fetch_feed
from utils.timeslots import DEFAULT_TIMESLOT_CATEGORY, normalize_timeslot_category, resolve_next_timeslot_for_account

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rss-feeds"])

DEFAULT_POST_TEMPLATE = "{title}\n\n{link}\n\n#updates"


# ── Pydantic Models ───────────────────────────────────────────────────────────

class ValidateFeedRequest(BaseModel):
    feed_url: str


class FeedItemPreview(BaseModel):
    guid: str
    url: str
    title: str
    summary: str
    author: str | None = None
    media_urls: list[str] = []
    pub_date: datetime


class ValidateFeedResponse(BaseModel):
    valid: bool
    title: str
    description: str
    site_url: str
    feed_url: str
    icon_url: str | None = None
    items_count: int
    sample_items: list[FeedItemPreview]


class CreateFeedRequest(BaseModel):
    feed_url: str
    title: str | None = None
    target_account_ids: list[str] = Field(default_factory=list)
    target_platforms: list[str] = Field(default_factory=list)
    auto_publish: bool = True
    post_status: str = "scheduled"  # "scheduled" | "draft" | "pending_approval"
    post_template: str = DEFAULT_POST_TEMPLATE
    use_ai_enhancement: bool = False
    ai_tone: str = "engaging"
    use_timeslot: bool = True
    timeslot_category: str = DEFAULT_TIMESLOT_CATEGORY
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    max_posts_per_day: int = 5


class UpdateFeedRequest(BaseModel):
    title: str | None = None
    target_account_ids: list[str] | None = None
    target_platforms: list[str] | None = None
    auto_publish: bool | None = None
    post_status: str | None = None
    post_template: str | None = None
    use_ai_enhancement: bool | None = None
    ai_tone: str | None = None
    use_timeslot: bool | None = None
    timeslot_category: str | None = None
    include_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    max_posts_per_day: int | None = None
    status: str | None = None  # "active" | "paused"


class ShareItemRequest(BaseModel):
    target_account_ids: list[str] | None = None
    custom_content: str | None = None
    scheduled_time: datetime | None = None
    use_timeslot: bool = True
    timeslot_category: str = DEFAULT_TIMESLOT_CATEGORY
    as_draft: bool = False


# ── Helper Functions ──────────────────────────────────────────────────────────

def _format_post_content(template: str, item: dict) -> str:
    """Replace placeholder tags in post template."""
    text = template or DEFAULT_POST_TEMPLATE
    text = text.replace("{title}", item.get("title") or "")
    text = text.replace("{link}", item.get("url") or "")
    text = text.replace("{summary}", (item.get("summary") or "")[:200])
    text = text.replace("{author}", item.get("author") or "")
    return text.strip()


async def _sync_feed_items(db, feed: dict, user_id: str, workspace_id: str) -> dict[str, int]:
    """Fetch feed and process new items according to automation rules."""
    feed_id = feed["id"]
    feed_url = feed["feed_url"]

    try:
        feed_meta, items, new_etag, new_last_mod, not_mod = await fetch_feed(
            feed_url,
            etag=feed.get("etag"),
            last_modified=feed.get("last_modified"),
        )
    except Exception as exc:
        logger.warning("Error fetching RSS feed %s: %s", feed_id, exc)
        await db.rss_feeds.update_one(
            {"id": feed_id},
            {"$set": {"last_error": str(exc), "last_polled_at": datetime.now(timezone.utc)}},
        )
        return {"discovered": 0, "scheduled": 0, "errors": 1}

    now = datetime.now(timezone.utc)
    if not_mod or items is None:
        await db.rss_feeds.update_one(
            {"id": feed_id},
            {"$set": {"last_polled_at": now, "last_error": None}},
        )
        return {"discovered": 0, "scheduled": 0, "errors": 0}

    # Update feed headers
    await db.rss_feeds.update_one(
        {"id": feed_id},
        {
            "$set": {
                "last_polled_at": now,
                "etag": new_etag,
                "last_modified": new_last_mod,
                "last_error": None,
                "title": feed_meta.get("title") or feed.get("title"),
            }
        },
    )

    discovered_count = 0
    scheduled_count = 0

    # Fetch accounts map
    target_acc_ids = feed.get("target_account_ids") or []
    accounts_cursor = db.social_accounts.find(
        {"workspace_id": workspace_id, "id": {"$in": target_acc_ids}, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "platform": 1},
    )
    target_accounts = await accounts_cursor.to_list(None)
    platforms = list(set(a["platform"] for a in target_accounts))

    for item in reversed(items[:20]):  # process oldest to newest
        guid = item.get("guid") or item.get("url")
        if not guid:
            continue

        existing = await db.rss_feed_items.find_one({"feed_id": feed_id, "guid": guid})
        if existing:
            continue

        discovered_count += 1
        item_id = str(uuid.uuid4())
        item_doc = {
            "id": item_id,
            "feed_id": feed_id,
            "workspace_id": workspace_id,
            "guid": guid,
            "url": item.get("url"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "author": item.get("author"),
            "media_urls": item.get("media_urls", []),
            "pub_date": item.get("pub_date", now),
            "status": "discovered",
            "post_id": None,
            "created_at": now,
        }

        # Check keyword filters
        title_lower = (item.get("title") or "").lower()
        summary_lower = (item.get("summary") or "").lower()
        full_text = f"{title_lower} {summary_lower}"

        include_kws = [k.lower().strip() for k in feed.get("include_keywords") or [] if k.strip()]
        exclude_kws = [k.lower().strip() for k in feed.get("exclude_keywords") or [] if k.strip()]

        if include_kws and not any(kw in full_text for kw in include_kws):
            item_doc["status"] = "skipped_keyword"
            await db.rss_feed_items.insert_one(item_doc)
            continue

        if exclude_kws and any(kw in full_text for kw in exclude_kws):
            item_doc["status"] = "skipped_keyword"
            await db.rss_feed_items.insert_one(item_doc)
            continue

        # Auto-publish if enabled
        if feed.get("auto_publish") and target_accounts:
            content = _format_post_content(feed.get("post_template", DEFAULT_POST_TEMPLATE), item)
            post_status = feed.get("post_status", "scheduled")

            scheduled_time = None
            timeslot_cat = feed.get("timeslot_category", DEFAULT_TIMESLOT_CATEGORY)

            if post_status == "scheduled" and feed.get("use_timeslot", True) and len(target_accounts) == 1:
                try:
                    category = normalize_timeslot_category(timeslot_cat)
                    slot, _, _ = await resolve_next_timeslot_for_account(
                        db, workspace_id, target_accounts[0]["id"], category, now=now
                    )
                    scheduled_time = slot or now
                except Exception:
                    scheduled_time = now
            elif post_status == "scheduled" and not scheduled_time:
                scheduled_time = now
            post_id = str(uuid.uuid4())
            media_list = item.get("media_urls") or []
            primary_media = media_list[0] if media_list else None
            inferred_type = "image" if primary_media else "text"

            post_doc = {
                "id": post_id,
                "post_id": post_id,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "content": content,
                "title": item.get("title"),
                "platforms": platforms,
                "account_ids": [a["id"] for a in target_accounts],
                "social_account_ids": [a["id"] for a in target_accounts],
                "media_urls": item.get("media_urls", []),
                "media_url": primary_media,
                "video_url": None,
                "thumbnail_urls": [],
                "post_type": inferred_type,
                "timezone": "UTC",
                "timeslot_category": timeslot_cat if post_status == "scheduled" else None,
                "scheduled_time": scheduled_time,
                "tags": [],
                "status": post_status,
                "platform_results": {p: {"status": "pending"} for p in platforms},
                "account_results": {
                    a["id"]: {"status": "pending", "platform": a["platform"], "account_id": a["id"]}
                    for a in target_accounts
                },
                "platform_post_urls": {},
                "status_history": [
                    {"status": post_status, "timestamp": now, "actor": f"rss_feed:{feed_id}"}
                ],
                "version": 1,
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                "source": "rss_automation",
                "created_at": now,
                "updated_at": now,
            }

            await db.posts.insert_one(post_doc)
            item_doc["status"] = post_status
            item_doc["post_id"] = post_id
            scheduled_count += 1

        await db.rss_feed_items.insert_one(item_doc)

    return {"discovered": discovered_count, "scheduled": scheduled_count, "errors": 0}


# ── Route Handlers ────────────────────────────────────────────────────────────

@router.post("/rss/validate", response_model=ValidateFeedResponse)
async def validate_rss_feed(
    request: ValidateFeedRequest,
    current_user: CurrentUser,
):
    """Validate a feed URL and return metadata with sample articles."""
    try:
        feed_meta, items, _, _, _ = await fetch_feed(request.feed_url.strip())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse RSS feed: {str(exc)}",
        )

    sample_items = [
        FeedItemPreview(
            guid=item.get("guid") or item.get("url") or "",
            url=item.get("url") or "",
            title=item.get("title") or "Untitled",
            summary=item.get("summary") or "",
            author=item.get("author"),
            media_urls=item.get("media_urls") or [],
            pub_date=item.get("pub_date") or datetime.now(timezone.utc),
        )
        for item in (items or [])[:5]
    ]

    return ValidateFeedResponse(
        valid=True,
        title=feed_meta.get("title") or "Untitled Feed",
        description=feed_meta.get("description") or "",
        site_url=feed_meta.get("site_url") or request.feed_url,
        feed_url=request.feed_url,
        icon_url=feed_meta.get("icon_url"),
        items_count=len(items or []),
        sample_items=sample_items,
    )


@router.get("/rss/feeds")
async def list_rss_feeds(
    current_user: CurrentUser,
    db: DB,
):
    """List all connected RSS feeds for the active workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.rss_feeds.find(
        {"workspace_id": workspace_id},
        {"_id": 0},
    ).sort("created_at", -1)
    feeds = await cursor.to_list(None)

    # Attach stats for each feed
    for f in feeds:
        total_items = await db.rss_feed_items.count_documents({"feed_id": f["id"]})
        scheduled_items = await db.rss_feed_items.count_documents(
            {"feed_id": f["id"], "status": {"$in": ["scheduled", "published"]}}
        )
        f["total_items"] = total_items
        f["scheduled_items"] = scheduled_items

    return {"feeds": feeds}


@router.post("/rss/feeds")
async def create_rss_feed(
    request: CreateFeedRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """Connect a new RSS feed and perform initial sync."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    # Check for existing feed URL in workspace
    existing = await db.rss_feeds.find_one({"workspace_id": workspace_id, "feed_url": request.feed_url.strip()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This feed URL is already connected to your workspace.",
        )

    # Validate feed
    try:
        feed_meta, _, etag, last_mod, _ = await fetch_feed(request.feed_url.strip())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not connect to feed: {str(exc)}",
        )

    now = datetime.now(timezone.utc)
    feed_id = str(uuid.uuid4())

    feed_doc = {
        "id": feed_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "feed_url": request.feed_url.strip(),
        "title": request.title or feed_meta.get("title") or "Untitled Feed",
        "description": feed_meta.get("description") or "",
        "site_url": feed_meta.get("site_url") or request.feed_url.strip(),
        "icon_url": feed_meta.get("icon_url"),
        "status": "active",
        "last_polled_at": now,
        "poll_interval_minutes": 30,
        "etag": etag,
        "last_modified": last_mod,
        "last_error": None,
        "target_account_ids": request.target_account_ids,
        "target_platforms": request.target_platforms,
        "auto_publish": request.auto_publish,
        "post_status": request.post_status,
        "post_template": request.post_template or DEFAULT_POST_TEMPLATE,
        "use_ai_enhancement": request.use_ai_enhancement,
        "ai_tone": request.ai_tone,
        "use_timeslot": request.use_timeslot,
        "timeslot_category": request.timeslot_category,
        "include_keywords": request.include_keywords,
        "exclude_keywords": request.exclude_keywords,
        "max_posts_per_day": request.max_posts_per_day,
        "created_at": now,
        "updated_at": now,
    }

    await db.rss_feeds.insert_one(feed_doc)

    # Run initial sync
    sync_stats = await _sync_feed_items(db, feed_doc, user_id, workspace_id)

    feed_doc.pop("_id", None)
    return {"feed": feed_doc, "sync_stats": sync_stats}


@router.get("/rss/feeds/{feed_id}")
async def get_rss_feed(
    feed_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get single feed details."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    feed = await db.rss_feeds.find_one({"id": feed_id, "workspace_id": workspace_id}, {"_id": 0})
    if not feed:
        raise HTTPException(status_code=404, detail="RSS Feed not found")
    return feed


@router.patch("/rss/feeds/{feed_id}")
async def update_rss_feed(
    feed_id: str,
    request: UpdateFeedRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """Update feed configuration and automation rules."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.rss_feeds.find_one_and_update(
        {"id": feed_id, "workspace_id": workspace_id},
        {"$set": update_data},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="RSS Feed not found")
    return res


@router.delete("/rss/feeds/{feed_id}")
async def delete_rss_feed(
    feed_id: str,
    current_user: VerifiedUser,
    db: DB,
):
    """Delete feed and its historical item logs."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.rss_feeds.delete_one({"id": feed_id, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="RSS Feed not found")

    await db.rss_feed_items.delete_many({"feed_id": feed_id})
    return {"deleted": True, "feed_id": feed_id}


@router.post("/rss/feeds/{feed_id}/sync")
async def sync_rss_feed_now(
    feed_id: str,
    current_user: VerifiedUser,
    db: DB,
):
    """Trigger on-demand sync for a feed."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    user_id = current_user["user_id"]
    feed = await db.rss_feeds.find_one({"id": feed_id, "workspace_id": workspace_id})
    if not feed:
        raise HTTPException(status_code=404, detail="RSS Feed not found")

    sync_stats = await _sync_feed_items(db, feed, user_id, workspace_id)
    return {"synced": True, "feed_id": feed_id, "stats": sync_stats}


@router.get("/rss/items")
async def list_rss_items(
    current_user: CurrentUser,
    db: DB,
    feed_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List discovered article stream across all feeds."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    query: dict[str, Any] = {"workspace_id": workspace_id}
    if feed_id:
        query["feed_id"] = feed_id
    if status:
        query["status"] = status

    cursor = db.rss_feed_items.find(query, {"_id": 0}).sort("pub_date", -1).skip(offset).limit(limit)
    items = await cursor.to_list(None)
    total = await db.rss_feed_items.count_documents(query)

    # Attach feed title for convenience
    feeds = await db.rss_feeds.find({"workspace_id": workspace_id}, {"_id": 0, "id": 1, "title": 1}).to_list(None)
    feed_map = {f["id"]: f["title"] for f in feeds}
    for item in items:
        item["feed_title"] = feed_map.get(item["feed_id"], "Unknown Feed")

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/rss/items/{item_id}/share")
async def share_rss_item_to_social(
    item_id: str,
    request: ShareItemRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """Share a discovered article to social media immediately or in timeslots."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    item = await db.rss_feed_items.find_one({"id": item_id, "workspace_id": workspace_id})
    if not item:
        raise HTTPException(status_code=404, detail="Article item not found")

    feed = await db.rss_feeds.find_one({"id": item["feed_id"]}) or {}

    target_acc_ids = request.target_account_ids or feed.get("target_account_ids") or []
    if not target_acc_ids:
        # Fallback to user's first active account
        first_acc = await db.social_accounts.find_one(
            {"workspace_id": workspace_id, "status": {"$ne": "deleted"}},
            {"_id": 0, "id": 1, "platform": 1},
        )
        if first_acc:
            target_acc_ids = [first_acc["id"]]

    accounts_cursor = db.social_accounts.find(
        {"workspace_id": workspace_id, "id": {"$in": target_acc_ids}, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "platform": 1},
    )
    target_accounts = await accounts_cursor.to_list(None)
    if not target_accounts:
        raise HTTPException(status_code=400, detail="No active social accounts selected to share this article.")

    platforms = list(set(a["platform"] for a in target_accounts))
    content = request.custom_content or _format_post_content(feed.get("post_template", DEFAULT_POST_TEMPLATE), item)

    now = datetime.now(timezone.utc)
    post_status = "draft" if request.as_draft else "scheduled"
    scheduled_time = request.scheduled_time

    if post_status == "scheduled" and not scheduled_time and request.use_timeslot and len(target_accounts) == 1:
        try:
            category = normalize_timeslot_category(request.timeslot_category)
            slot, _, _ = await resolve_next_timeslot_for_account(
                db, workspace_id, target_accounts[0]["id"], category, now=now
            )
            scheduled_time = slot or now
        except Exception:
            scheduled_time = now
    elif post_status == "scheduled" and not scheduled_time:
        scheduled_time = now

    post_id = str(uuid.uuid4())
    media_list = item.get("media_urls") or []
    primary_media = media_list[0] if media_list else None
    inferred_type = "image" if primary_media else "text"

    post_doc = {
        "id": post_id,
        "post_id": post_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "content": content,
        "title": item.get("title"),
        "platforms": platforms,
        "account_ids": [a["id"] for a in target_accounts],
        "social_account_ids": [a["id"] for a in target_accounts],
        "media_urls": item.get("media_urls", []),
        "media_url": primary_media,
        "video_url": None,
        "thumbnail_urls": [],
        "post_type": inferred_type,
        "timezone": "UTC",
        "timeslot_category": request.timeslot_category if post_status == "scheduled" else None,
        "scheduled_time": scheduled_time,
        "tags": [],
        "status": post_status,
        "platform_results": {p: {"status": "pending"} for p in platforms},
        "account_results": {
            a["id"]: {"status": "pending", "platform": a["platform"], "account_id": a["id"]}
            for a in target_accounts
        },
        "platform_post_urls": {},
        "status_history": [
            {"status": post_status, "timestamp": now, "actor": user_id}
        ],
        "version": 1,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "source": "rss_manual_share",
        "created_at": now,
        "updated_at": now,
    }

    await db.posts.insert_one(post_doc)
    await db.rss_feed_items.update_one(
        {"id": item_id},
        {"$set": {"status": post_status, "post_id": post_id}},
    )

    post_doc.pop("_id", None)
    return {"shared": True, "post": post_doc}
