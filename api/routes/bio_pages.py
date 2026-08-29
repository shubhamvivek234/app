"""
Link-in-Bio / "Start Page" Builder API Router.
Provides public customizable landing pages (unravler.com/@handle),
link click tracking, Instagram post grid synchronization, and theme styling.
"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB
from utils.ssrf_guard import assert_safe_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bio-pages"])

_RESERVED_HANDLES = {
    "admin", "api", "app", "auth", "billing", "blog", "calendar", "dashboard",
    "developers", "docs", "help", "inbox", "login", "pricing", "privacy",
    "review", "rss-feeds", "settings", "signup", "terms", "unravler",
}


# ── Pydantic Models ──────────────────────────────────────────────────────────

class BioCustomLink(BaseModel):
    id: str
    title: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=3, max_length=2000)
    icon: str | None = Field(default="globe", max_length=50)
    clicks: int = 0
    is_active: bool = True


class BioTheme(BaseModel):
    background_type: str = Field(default="solid")  # "solid" | "gradient" | "dark"
    background_color: str = Field(default="#0f172a", max_length=50)
    card_background: str = Field(default="#1e293b", max_length=50)
    text_color: str = Field(default="#ffffff", max_length=50)
    accent_color: str = Field(default="#6366f1", max_length=50)
    button_style: str = Field(default="rounded-2xl")  # "rounded-md" | "rounded-2xl" | "rounded-full"


class BioPageConfig(BaseModel):
    handle: str = Field(..., min_length=2, max_length=40)
    title: str = Field(..., min_length=1, max_length=100)
    bio: str = Field(default="", max_length=500)
    avatar_url: str | None = None
    theme: BioTheme = Field(default_factory=BioTheme)
    custom_links: list[BioCustomLink] = Field(default_factory=list)
    social_links: dict[str, str] = Field(default_factory=dict)
    auto_sync_instagram_grid: bool = True
    is_published: bool = True


# ── REST API Endpoints ────────────────────────────────────────────────────────

@router.get("/bio-pages/mine")
async def get_my_bio_page(
    current_user: CurrentUser,
    db: DB,
):
    """Retrieve the bio page configuration for the current workspace."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    doc = await db.bio_pages.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})
    if not doc:
        user_doc = await db.users.find_one({"user_id": user_id}) or {}
        default_handle = re.sub(r"[^a-zA-Z0-9_]", "", (user_doc.get("name") or "user").lower())[:20] or "mybrand"
        return {
            "handle": default_handle,
            "title": user_doc.get("name") or "My Link in Bio",
            "bio": "Welcome to my official links & social feed!",
            "avatar_url": user_doc.get("picture") or user_doc.get("avatar_url"),
            "theme": BioTheme().model_dump(),
            "custom_links": [
                {"id": "link_1", "title": "Visit Website", "url": "https://unravler.com", "icon": "globe", "clicks": 0, "is_active": True},
            ],
            "social_links": {},
            "auto_sync_instagram_grid": True,
            "is_published": True,
            "page_url": f"https://www.unravler.com/@{default_handle}",
        }

    return {
        "handle": doc["handle"],
        "title": doc.get("title", ""),
        "bio": doc.get("bio", ""),
        "avatar_url": doc.get("avatar_url"),
        "theme": doc.get("theme", BioTheme().model_dump()),
        "custom_links": doc.get("custom_links", []),
        "social_links": doc.get("social_links", {}),
        "auto_sync_instagram_grid": doc.get("auto_sync_instagram_grid", True),
        "is_published": doc.get("is_published", True),
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

    # Validate custom links
    for link in payload.custom_links:
        raw_url = link.url.strip()
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Link URL must start with http:// or https://: {raw_url}")
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
        "theme": payload.theme.model_dump(),
        "custom_links": [link.model_dump() for link in payload.custom_links],
        "social_links": payload.social_links,
        "auto_sync_instagram_grid": payload.auto_sync_instagram_grid,
        "is_published": payload.is_published,
        "updated_at": now,
    }

    await db.bio_pages.update_one(
        {"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]},
        {"$set": doc_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "ok": True,
        "handle": clean_handle,
        "page_url": f"https://www.unravler.com/@{clean_handle}",
    }


@router.get("/bio-pages/public/{handle}")
async def get_public_bio_page(
    handle: str,
    db: DB,
):
    """Public read endpoint for rendering a creator's Link-in-Bio page."""
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", handle.lower().strip())
    doc = await db.bio_pages.find_one({"handle": clean_handle})
    if not doc or not doc.get("is_published", True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator page not found")

    workspace_id = doc.get("workspace_id")

    # Fetch recent published media items if auto_sync_instagram_grid is True
    recent_grid_posts = []
    if doc.get("auto_sync_instagram_grid", True):
        cursor = db.posts.find({
            "$or": [{"workspace_id": workspace_id}, {"user_id": workspace_id}],
            "status": "published",
            "media_urls": {"$exists": True, "$ne": []},
            "deleted_at": {"$exists": False},
        }).sort("published_at", -1).limit(12)

        async for p in cursor:
            media_url = (p.get("media_urls") or [None])[0]
            if media_url:
                recent_grid_posts.append({
                    "id": p.get("id"),
                    "title": p.get("title") or p.get("content", "")[:50],
                    "media_url": media_url,
                    "published_at": p.get("published_at").isoformat() if isinstance(p.get("published_at"), datetime) else p.get("published_at"),
                })

    return {
        "handle": doc["handle"],
        "title": doc.get("title", ""),
        "bio": doc.get("bio", ""),
        "avatar_url": doc.get("avatar_url"),
        "theme": doc.get("theme", BioTheme().model_dump()),
        "custom_links": [link for link in (doc.get("custom_links") or []) if link.get("is_active", True)],
        "social_links": doc.get("social_links", {}),
        "grid_posts": recent_grid_posts,
    }


@router.post("/bio-pages/public/{handle}/click/{link_id}")
async def track_bio_link_click(
    handle: str,
    link_id: str,
    request: Request,
    db: DB,
):
    """Track a click on a Link-in-Bio custom button."""
    clean_handle = re.sub(r"[^a-zA-Z0-9_-]", "", handle.lower().strip())
    res = await db.bio_pages.update_one(
        {"handle": clean_handle, "custom_links.id": link_id},
        {"$inc": {"custom_links.$.clicks": 1}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link item not found")

    return {"ok": True}
