"""
Unravler Smart Bio (Link-in-Bio & Dynamic Social Feed Builder) API Router.
Provides public customizable landing pages (unravler.com/@handle),
rich block architecture (links, social feed grid, video/music embeds, lead capture),
link click tracking, scheduled/expiring links, and agency theme styling.
"""
import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bio-pages"])

_RESERVED_HANDLES = {
    "admin", "api", "app", "auth", "billing", "blog", "calendar", "dashboard",
    "developers", "docs", "help", "inbox", "login", "pricing", "privacy",
    "review", "rss-feeds", "settings", "signup", "terms", "unravler", "public",
}


# ── Pydantic Models ──────────────────────────────────────────────────────────

class BlockSchedule(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None


class BioBlockItem(BaseModel):
    id: str
    type: Literal["link", "feed_grid", "embed", "lead_capture", "text_block", "media_card", "folder", "tab_group"] = "link"
    title: str = ""
    subtitle: str = ""
    url: str = ""
    icon: str = "globe"
    badge: str = ""
    is_featured: bool = False
    provider: str = ""
    embed_url: str = ""
    media_url: str = ""
    media_type: str = "image"
    layout: str = "card_left_image"
    animation: str = "none"
    tag: str = ""
    text_align: str = "left"
    size: str = "large"
    custom_styles: dict = Field(default_factory=dict)
    headline: str = ""
    subheadline: str = ""
    button_label: str = "Subscribe"
    content: str = ""
    limit: int = 6
    show_caption: bool = True
    active: bool = True
    schedule: BlockSchedule | None = None
    click_count: int = 0
    folder_items: list[dict] = Field(default_factory=list)
    is_expanded: bool = False


class BioTheme(BaseModel):
    preset: str = "editorial_cream"
    background_type: str = "gradient"
    background_color: str = "#FDFBF7"
    background_gradient: str = "linear-gradient(135deg, #fdfbf7 0%, #f4ede2 100%)"
    background_effect: str = "none"
    header_layout: str = "classic"
    banner_url: str = ""
    text_color: str = "#18181B"
    card_style: str = "glass_double_bezel"
    card_bg: str = "rgba(255, 255, 255, 0.85)"
    card_border: str = "rgba(0, 0, 0, 0.07)"
    card_text_color: str = "#18181B"
    card_shadow: str = ""
    button_radius: str = "rounded-2xl"
    font_family: str = "Plus Jakarta Sans"
    accent_color: str = "#4F46E5"
    card_corner_radius: int = 20
    card_border_width: int = 0
    card_shadow_depth: int = 100
    card_shadow_type: str = "soft"
    card_spacing: int = 33
    profile_picture_size: int = 50
    profile_picture_shadow: int = 0
    profile_picture_border: int = 0
    collapse_long_bio: bool = False
    social_icon_size: int = 0
    announcement_banner: str = ""
    announcement_url: str = ""
    announcement_active: bool = False
    navigation_style: str = "pills"


class SeoConfig(BaseModel):
    meta_title: str = ""
    meta_description: str = ""
    meta_image_url: str = ""


class BioSubPage(BaseModel):
    id: str
    slug: str
    title: str
    description: str = ""
    blocks: list[BioBlockItem] = Field(default_factory=list)
    seo: SeoConfig | None = None


class BioPageConfig(BaseModel):
    handle: str = Field(..., min_length=2, max_length=40)
    title: str = Field(..., min_length=1, max_length=100)
    bio: str = Field(default="", max_length=500)
    avatar_url: str | None = None
    verified_badge: bool = False
    theme: BioTheme = Field(default_factory=BioTheme)
    blocks: list[BioBlockItem] = Field(default_factory=list)
    pages: list[BioSubPage] = Field(default_factory=list)
    active_page_id: str = "home"
    navigation_style: str = "pills"
    social_links: dict[str, str] = Field(default_factory=dict)
    custom_domain: str = ""
    seo: SeoConfig = Field(default_factory=SeoConfig)
    auto_sync_instagram_grid: bool = True
    is_published: bool = True


class BioLeadSubscribeRequest(BaseModel):
    email: str
    source_block_id: str | None = None


class BioTrackRequest(BaseModel):
    event_type: Literal["impression", "click"] = "click"
    block_id: str | None = None
    target_url: str | None = None
    referrer: str | None = None


# ── Helper Functions ──────────────────────────────────────────────────────────

def _is_block_active(block: dict, now: datetime) -> bool:
    if not block.get("active", True):
        return False
    schedule = block.get("schedule")
    if not schedule:
        return True

    start_at = schedule.get("start_at")
    end_at = schedule.get("end_at")

    if start_at:
        try:
            start_dt = start_at if isinstance(start_at, datetime) else datetime.fromisoformat(str(start_at).replace("Z", "+00:00"))
            if now < start_dt:
                return False
        except Exception:
            pass

    if end_at:
        try:
            end_dt = end_at if isinstance(end_at, datetime) else datetime.fromisoformat(str(end_at).replace("Z", "+00:00"))
            if now > end_dt:
                return False
        except Exception:
            pass

    return True


# ── REST API Endpoints ────────────────────────────────────────────────────────

@router.get("/bio-pages/mine")
async def get_my_bio_page(
    current_user: CurrentUser,
    db: DB,
):
    """Retrieve the bio page configuration for the current workspace."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)

    doc = await db.bio_pages.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})
    if not doc:
        user_doc = await db.users.find_one({"user_id": user_id}) or {}
        default_handle = re.sub(r"[^a-zA-Z0-9_]", "", (user_doc.get("name") or "creator").lower())[:20] or "creator"
        
        # Uniqueness check
        existing = await db.bio_pages.find_one({"handle": default_handle})
        if existing:
            default_handle = f"{default_handle}_{int(now.timestamp()) % 10000}"

        display_name = user_doc.get("name") or "My Bio"
        avatar_url = user_doc.get("picture") or user_doc.get("avatar_url") or ""

        default_blocks = [
            {
                "id": "blk_feed",
                "type": "feed_grid",
                "title": "Recent Social Highlights",
                "limit": 6,
                "show_caption": True,
                "active": True,
                "click_count": 0,
            },
            {
                "id": "blk_welcome",
                "type": "link",
                "title": "Visit Official Website 🌐",
                "subtitle": "Portfolio, case studies, and services",
                "url": "https://unravler.com",
                "icon": "globe",
                "badge": "Featured",
                "active": True,
                "click_count": 0,
            },
            {
                "id": "blk_newsletter",
                "type": "lead_capture",
                "headline": "Join My VIP Newsletter 💌",
                "subheadline": "Weekly curation, insights, and free drops directly to your inbox.",
                "button_label": "Subscribe",
                "active": True,
                "click_count": 0,
            }
        ]

        default_doc = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "handle": default_handle,
            "title": display_name,
            "bio": "Welcome to my official links & social feed ✨",
            "avatar_url": avatar_url,
            "verified_badge": False,
            "theme": BioTheme().model_dump(),
            "blocks": default_blocks,
            "social_links": {},
            "custom_domain": "",
            "seo": {
                "meta_title": f"{display_name} | Smart Bio",
                "meta_description": f"Explore links, latest social posts, and updates from {display_name}.",
                "meta_image_url": "",
            },
            "auto_sync_instagram_grid": True,
            "is_published": True,
            "total_views": 0,
            "total_clicks": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.bio_pages.insert_one(default_doc)
        doc = default_doc

    # Transform legacy custom_links to blocks if needed
    blocks = doc.get("blocks")
    if blocks is None:
        blocks = []
        for cl in doc.get("custom_links", []):
            blocks.append({
                "id": cl.get("id", str(ObjectId())),
                "type": "link",
                "title": cl.get("title", "Link"),
                "subtitle": "",
                "url": cl.get("url", ""),
                "icon": cl.get("icon", "globe"),
                "badge": "",
                "active": cl.get("is_active", True),
                "click_count": cl.get("clicks", 0),
            })
        if doc.get("auto_sync_instagram_grid", True):
            blocks.insert(0, {
                "id": "blk_feed",
                "type": "feed_grid",
                "title": "Recent Highlights",
                "limit": 6,
                "show_caption": True,
                "active": True,
            })

    return {
        "handle": doc["handle"],
        "title": doc.get("title", ""),
        "bio": doc.get("bio", ""),
        "avatar_url": doc.get("avatar_url"),
        "verified_badge": doc.get("verified_badge", False),
        "theme": doc.get("theme", BioTheme().model_dump()),
        "blocks": blocks,
        "pages": doc.get("pages", []),
        "active_page_id": doc.get("active_page_id", "home"),
        "navigation_style": doc.get("navigation_style", "pills"),
        "social_links": doc.get("social_links", {}),
        "custom_domain": doc.get("custom_domain", ""),
        "seo": doc.get("seo", {}),
        "auto_sync_instagram_grid": doc.get("auto_sync_instagram_grid", True),
        "is_published": doc.get("is_published", True),
        "total_views": doc.get("total_views", 0),
        "total_clicks": doc.get("total_clicks", 0),
        "page_url": f"https://www.unravler.com/@{doc['handle']}",
    }


@router.put("/bio-pages/mine")
async def save_my_bio_page(
    payload: BioPageConfig,
    current_user: CurrentUser,
    db: DB,
):
    """Save/update the workspace's Link-in-Bio configuration."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    # Clean handle
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", payload.handle.lower().strip())
    if len(clean_handle) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Handle must be at least 2 characters")
    if clean_handle in _RESERVED_HANDLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"The handle '{clean_handle}' is reserved")

    # Check handle uniqueness
    existing = await db.bio_pages.find_one({"handle": clean_handle, "workspace_id": {"$ne": workspace_id}})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Handle '@{clean_handle}' is already taken by another creator")

    # Validate links in blocks
    for b in payload.blocks:
        if b.type == "link" and b.url:
            raw_url = b.url.strip()
            if not (raw_url.startswith("http://") or raw_url.startswith("https://") or raw_url.startswith("mailto:") or raw_url.startswith("tel:")):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid URL format: {raw_url}")
            if "127.0.0.1" in raw_url or "localhost" in raw_url or "169.254.169.254" in raw_url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Internal URLs are not allowed")

    now = datetime.now(timezone.utc)
    doc_data = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "handle": clean_handle,
        "title": payload.title.strip(),
        "bio": payload.bio.strip(),
        "avatar_url": payload.avatar_url,
        "verified_badge": payload.verified_badge,
        "theme": payload.theme.model_dump(),
        "blocks": [b.model_dump() for b in payload.blocks],
        "pages": [p.model_dump() for p in payload.pages],
        "active_page_id": payload.active_page_id,
        "navigation_style": payload.navigation_style,
        "social_links": payload.social_links,
        "custom_domain": payload.custom_domain.strip().lower(),
        "seo": payload.seo.model_dump(),
        "auto_sync_instagram_grid": payload.auto_sync_instagram_grid,
        "is_published": payload.is_published,
        "updated_at": now,
    }

    await db.bio_pages.update_one(
        {"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]},
        {"$set": doc_data, "$setOnInsert": {"_id": ObjectId(), "created_at": now, "total_views": 0, "total_clicks": 0}},
        upsert=True,
    )

    return {
        "ok": True,
        "handle": clean_handle,
        "page_url": f"https://www.unravler.com/@{clean_handle}",
    }


@router.get("/bio-pages/analytics")
async def get_bio_analytics(
    current_user: CurrentUser,
    db: DB,
):
    """Fetch high-level and per-block performance analytics for the workspace's Bio page."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    page = await db.bio_pages.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})
    if not page:
        return {"views": 0, "clicks": 0, "ctr": 0, "referrers": [], "top_blocks": []}

    total_views = page.get("total_views", 0)
    total_clicks = page.get("total_clicks", 0)
    ctr = round((total_clicks / total_views * 100), 1) if total_views > 0 else 0

    # Top referrers aggregation
    pipeline = [
        {"$match": {"workspace_id": workspace_id, "event_type": "click"}},
        {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    raw_referrers = await db.bio_analytics.aggregate(pipeline).to_list(length=5)
    referrers = [
        {"source": r["_id"] or "Direct / Social Bio", "clicks": r["count"]}
        for r in raw_referrers
    ]

    blocks = page.get("blocks", [])
    top_blocks = []
    for b in blocks:
        clicks = b.get("click_count", 0) or b.get("clicks", 0)
        title = b.get("title") or b.get("headline") or "Block"
        top_blocks.append({
            "id": b.get("id"),
            "title": title,
            "type": b.get("type", "link"),
            "url": b.get("url", ""),
            "clicks": clicks,
        })
    top_blocks.sort(key=lambda x: x["clicks"], reverse=True)

    return {
        "views": total_views,
        "clicks": total_clicks,
        "ctr": ctr,
        "referrers": referrers,
        "top_blocks": top_blocks,
    }


@router.get("/bio-pages/leads")
async def get_bio_leads(
    current_user: CurrentUser,
    db: DB,
):
    """List emails captured from the Smart Bio lead form."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    cursor = db.workspace_leads.find({"workspace_id": workspace_id}).sort("created_at", -1).limit(200)
    leads = await cursor.to_list(length=200)
    return [
        {
            "id": str(lead["_id"]),
            "email": lead["email"],
            "created_at": lead["created_at"].isoformat() if hasattr(lead["created_at"], "isoformat") else str(lead["created_at"]),
        }
        for lead in leads
    ]


@router.get("/bio-pages/leads/export")
async def export_bio_leads_csv(
    current_user: CurrentUser,
    db: DB,
):
    """Download a CSV of all emails collected via the Smart Bio lead capture block."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    cursor = db.workspace_leads.find({"workspace_id": workspace_id}).sort("created_at", -1)
    leads = await cursor.to_list(length=5000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Subscribed At", "Source"])
    for lead in leads:
        ts = lead["created_at"].isoformat() if hasattr(lead["created_at"], "isoformat") else str(lead["created_at"])
        writer.writerow([lead["email"], ts, "Unravler Smart Bio"])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bio_leads_{int(datetime.now().timestamp())}.csv"},
    )


@router.get("/bio-pages/public/{handle}")
async def get_public_bio_page(
    handle: str,
    db: DB,
):
    """Public read endpoint for rendering a creator's Link-in-Bio page."""
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", handle.lower().strip())
    doc = await db.bio_pages.find_one({"handle": clean_handle})
    if not doc:
        # Check custom domain fallback
        doc = await db.bio_pages.find_one({"custom_domain": clean_handle})

    if not doc or not doc.get("is_published", True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator page not found")

    now = datetime.now(timezone.utc)
    workspace_id = doc.get("workspace_id")

    # Increment view counter asynchronously
    doc_id = doc.get("_id")
    page_query = {"_id": doc_id} if doc_id else {"handle": clean_handle}
    await db.bio_pages.update_one(page_query, {"$inc": {"total_views": 1}})

    # Process blocks & filter active schedule
    raw_blocks = doc.get("blocks")
    if raw_blocks is None:
        raw_blocks = []
        for cl in doc.get("custom_links", []):
            raw_blocks.append({
                "id": cl.get("id", str(ObjectId())),
                "type": "link",
                "title": cl.get("title", "Link"),
                "subtitle": "",
                "url": cl.get("url", ""),
                "icon": cl.get("icon", "globe"),
                "badge": "",
                "active": cl.get("is_active", True),
                "click_count": cl.get("clicks", 0),
            })
        if doc.get("auto_sync_instagram_grid", True):
            raw_blocks.insert(0, {
                "id": "blk_feed",
                "type": "feed_grid",
                "title": "Recent Highlights",
                "limit": 6,
                "show_caption": True,
                "active": True,
            })

    active_blocks = [b for b in raw_blocks if _is_block_active(b, now)]

    # Fetch recent published media items for feed_grid
    recent_grid_posts = []
    has_feed_grid = any(b.get("type") == "feed_grid" for b in active_blocks) or doc.get("auto_sync_instagram_grid", True)

    if has_feed_grid and workspace_id:
        cursor = db.posts.find({
            "$or": [{"workspace_id": workspace_id}, {"user_id": workspace_id}],
            "status": "published",
            "media_urls": {"$exists": True, "$ne": []},
            "deleted_at": {"$exists": False},
        }).sort("published_at", -1).limit(12)

        async for p in cursor:
            media_url = (p.get("media_urls") or [None])[0]
            # Try to grab published platform url
            post_link = ""
            results = p.get("platform_results") or {}
            for plat_data in results.values():
                if plat_data.get("post_url"):
                    post_link = plat_data["post_url"]
                    break

            if media_url:
                recent_grid_posts.append({
                    "id": p.get("id"),
                    "title": p.get("title") or (p.get("content") or "")[:50],
                    "media_url": media_url,
                    "post_url": post_link,
                    "platforms": p.get("platforms", []),
                    "published_at": p.get("published_at").isoformat() if isinstance(p.get("published_at"), datetime) else p.get("published_at"),
                })

    return {
        "handle": doc["handle"],
        "title": doc.get("title", ""),
        "bio": doc.get("bio", ""),
        "avatar_url": doc.get("avatar_url"),
        "verified_badge": doc.get("verified_badge", False),
        "theme": doc.get("theme", BioTheme().model_dump()),
        "blocks": active_blocks,
        "pages": doc.get("pages", []),
        "active_page_id": doc.get("active_page_id", "home"),
        "navigation_style": doc.get("navigation_style", "pills"),
        "social_links": doc.get("social_links", {}),
        "grid_posts": recent_grid_posts,
        "seo": doc.get("seo", {}),
    }


@router.post("/bio-pages/public/{handle}/click/{link_id}")
@router.post("/bio-pages/public/{handle}/track")
async def track_bio_link_click(
    handle: str,
    request: Request,
    db: DB,
    link_id: str | None = None,
    body: BioTrackRequest | None = None,
):
    """Track an interaction or click on a Link-in-Bio custom block or button."""
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", handle.lower().strip())
    doc = await db.bio_pages.find_one({"handle": clean_handle})
    if not doc:
        # Check custom domain fallback
        doc = await db.bio_pages.find_one({"custom_domain": clean_handle})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator page not found")

    target_block_id = link_id or (body.block_id if body else None)
    target_url = body.target_url if body else None
    referrer = body.referrer if body else request.headers.get("referer")
    user_agent = request.headers.get("user-agent", "")
    device = "mobile" if "mobile" in user_agent.lower() or "iphone" in user_agent.lower() or "android" in user_agent.lower() else "desktop"
    now = datetime.now(timezone.utc)
    workspace_id = doc.get("workspace_id")

    doc_id = doc.get("_id")
    page_query = {"_id": doc_id} if doc_id else {"handle": clean_handle}

    # Increment total clicks
    await db.bio_pages.update_one(page_query, {"$inc": {"total_clicks": 1}})

    # Increment specific block if found
    if target_block_id:
        if doc_id:
            await db.bio_pages.update_one(
                {"_id": doc_id, "blocks.id": target_block_id},
                {"$inc": {"blocks.$.click_count": 1}}
            )
            await db.bio_pages.update_one(
                {"_id": doc_id, "custom_links.id": target_block_id},
                {"$inc": {"custom_links.$.clicks": 1}}
            )
        else:
            await db.bio_pages.update_one(
                {"handle": clean_handle, "blocks.id": target_block_id},
                {"$inc": {"blocks.$.click_count": 1}}
            )

    # Log granular event
    await db.bio_analytics.insert_one({
        "_id": ObjectId(),
        "page_id": doc_id or clean_handle,
        "workspace_id": workspace_id,
        "event_type": "click",
        "block_id": target_block_id,
        "target_url": target_url,
        "referrer": referrer,
        "device": device,
        "timestamp": now,
    })

    return {"ok": True}


@router.post("/bio-pages/public/{handle}/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_to_bio_newsletter(
    handle: str,
    body: BioLeadSubscribeRequest,
    db: DB,
):
    """Subscribe a visitor to the creator's audience newsletter from the Smart Bio page."""
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", handle.lower().strip())
    doc = await db.bio_pages.find_one({"handle": clean_handle})
    if not doc:
        # Check custom domain fallback
        doc = await db.bio_pages.find_one({"custom_domain": clean_handle})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator page not found")

    email = body.email.strip().lower()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please provide a valid email address.")

    workspace_id = doc.get("workspace_id")
    now = datetime.now(timezone.utc)

    existing = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": email})
    if not existing:
        await db.workspace_leads.insert_one({
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "page_id": doc.get("_id"),
            "email": email,
            "source_block_id": body.source_block_id,
            "created_at": now,
        })

    return {"ok": True, "message": "Successfully subscribed!"}
