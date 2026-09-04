"""
Short Links & UTM Tracking API Router.
Provides URL shortening, automated UTM parameter generation, click tracking,
and redirection endpoints for Unravler.
"""
import hashlib
import logging
import random
import re
import string
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB
from utils.ssrf_guard import assert_safe_url, is_safe_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["short-links"])

_SLUG_CHARS = string.ascii_letters + string.digits


def _generate_slug(length: int = 6) -> str:
    return "".join(random.choices(_SLUG_CHARS, k=length))


def _append_utm_params(url: str, utm_params: dict[str, str]) -> str:
    """Safely merge UTM parameters into an existing URL without duplicating query keys."""
    if not utm_params:
        return url
    parsed = urlparse(url)
    existing_queries = parse_qs(parsed.query, keep_blank_values=True)
    # Merge UTM parameters (flattening lists)
    merged_queries = {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in existing_queries.items()}
    for k, v in utm_params.items():
        if v and str(v).strip():
            merged_queries[k] = str(v).strip()
    
    new_query = urlencode(merged_queries)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class UTMPreset(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=100)
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None


class ShortLinkCreate(BaseModel):
    original_url: str = Field(..., min_length=3)
    custom_slug: str | None = Field(None, max_length=30)
    title: str | None = Field(None, max_length=200)
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None
    campaign_id: str | None = None


class ShortLinkItem(BaseModel):
    id: str
    code: str
    short_url: str
    original_url: str
    final_url: str
    title: str | None = None
    utm_params: dict[str, str] = {}
    clicks_count: int = 0
    created_at: str
    campaign_id: str | None = None


# ── REST API Endpoints ────────────────────────────────────────────────────────

@router.post("/short-links", response_model=ShortLinkItem, status_code=status.HTTP_201_CREATED)
async def create_short_link(
    payload: ShortLinkCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new shortened link with optional UTM parameters."""
    raw_url = payload.original_url.strip()
    if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
        raw_url = f"https://{raw_url}"

    try:
        assert_safe_url(raw_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Build UTM map
    utm_map = {}
    for key in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]:
        val = getattr(payload, key, None)
        if val and str(val).strip():
            utm_map[key] = str(val).strip()

    final_url = _append_utm_params(raw_url, utm_map)
    user_id = current_user.get("user_id") or current_user.get("id")

    # Handle custom slug or auto-generate
    slug = None
    if payload.custom_slug:
        cleaned_slug = re.sub(r"[^a-zA-Z0-9_-]", "", payload.custom_slug.strip())
        if len(cleaned_slug) < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom slug must be at least 3 characters")
        existing = await db.short_links.find_one({"code": cleaned_slug})
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Custom slug already taken")
        slug = cleaned_slug
    else:
        # Generate collision-free slug
        for _ in range(5):
            candidate = _generate_slug(6)
            if not await db.short_links.find_one({"code": candidate}):
                slug = candidate
                break
        if not slug:
            slug = _generate_slug(8)

    doc_id = hashlib.sha256(f"{user_id}:{slug}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:24]
    now_iso = datetime.now(timezone.utc).isoformat()

    workspace_id = current_user.get("default_workspace_id") or user_id

    doc = {
        "id": doc_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "campaign_id": payload.campaign_id,
        "code": slug,
        "original_url": raw_url,
        "final_url": final_url,
        "title": payload.title or raw_url[:60],
        "utm_params": utm_map,
        "clicks_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.short_links.insert_one(doc)

    return ShortLinkItem(
        id=doc_id,
        code=slug,
        short_url=f"https://api.unravler.com/r/{slug}",
        original_url=raw_url,
        final_url=final_url,
        title=doc["title"],
        utm_params=utm_map,
        clicks_count=0,
        created_at=now_iso,
        campaign_id=payload.campaign_id,
    )


@router.get("/short-links", response_model=list[ShortLinkItem])
async def list_short_links(
    current_user: CurrentUser,
    db: DB,
    campaign_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    """List shortened links for current user."""
    user_id = current_user.get("user_id") or current_user.get("id")
    workspace_id = current_user.get("default_workspace_id") or user_id
    query: dict[str, Any] = {"$or": [{"user_id": user_id}, {"workspace_id": workspace_id}]}
    if campaign_id:
        query["campaign_id"] = campaign_id

    limit_val = getattr(limit, "default", limit) if hasattr(limit, "default") else limit
    skip_val = getattr(skip, "default", skip) if hasattr(skip, "default") else skip
    cursor = db.short_links.find(query).sort("created_at", -1).skip(int(skip_val)).limit(int(limit_val))
    items = []
    async for doc in cursor:
        items.append(
            ShortLinkItem(
                id=doc.get("id", str(doc.get("_id"))),
                code=doc["code"],
                short_url=f"https://api.unravler.com/r/{doc['code']}",
                original_url=doc["original_url"],
                final_url=doc.get("final_url", doc["original_url"]),
                title=doc.get("title"),
                utm_params=doc.get("utm_params", {}),
                clicks_count=doc.get("clicks_count", doc.get("clicks", 0)),
                created_at=doc.get("created_at", ""),
                campaign_id=doc.get("campaign_id"),
            )
        )
    return items


@router.get("/short-links/{code}/stats")
async def get_short_link_stats(
    code: str,
    current_user: CurrentUser,
    db: DB,
):
    """Retrieve click analytics for a shortened link."""
    user_id = current_user.get("user_id") or current_user.get("id")
    doc = await db.short_links.find_one({"code": code, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")

    # Fetch last 100 click events
    clicks_cursor = db.short_link_clicks.find({"code": code}).sort("timestamp", -1).limit(100)
    clicks = []
    referrers: dict[str, int] = {}
    devices: dict[str, int] = {}

    async for c in clicks_cursor:
        clicks.append({
            "timestamp": c.get("timestamp"),
            "referrer": c.get("referrer", "direct"),
            "user_agent": c.get("user_agent", ""),
        })
        ref = c.get("referrer") or "direct"
        referrers[ref] = referrers.get(ref, 0) + 1
        ua = (c.get("user_agent") or "").lower()
        device_type = "mobile" if "mobile" in ua or "android" in ua or "iphone" in ua else "desktop"
        devices[device_type] = devices.get(device_type, 0) + 1

    return {
        "code": code,
        "original_url": doc["original_url"],
        "final_url": doc.get("final_url", doc["original_url"]),
        "total_clicks": doc.get("clicks_count", 0),
        "recent_clicks": clicks,
        "referrers": referrers,
        "devices": devices,
    }


@router.delete("/short-links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_short_link(
    code: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a shortened link."""
    user_id = current_user.get("user_id") or current_user.get("id")
    res = await db.short_links.delete_one({"code": code, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found")
    await db.short_link_clicks.delete_many({"code": code})
    return None


# ── UTM Presets ───────────────────────────────────────────────────────────────

@router.get("/utm-presets", response_model=list[UTMPreset])
async def list_utm_presets(
    current_user: CurrentUser,
    db: DB,
):
    """List saved UTM presets."""
    user_id = current_user.get("user_id") or current_user.get("id")
    cursor = db.utm_presets.find({"user_id": user_id}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        results.append(UTMPreset(
            id=doc.get("id", str(doc.get("_id"))),
            name=doc.get("name", "Default"),
            utm_source=doc.get("utm_source"),
            utm_medium=doc.get("utm_medium"),
            utm_campaign=doc.get("utm_campaign"),
            utm_term=doc.get("utm_term"),
            utm_content=doc.get("utm_content"),
        ))
    return results


@router.post("/utm-presets", response_model=UTMPreset, status_code=status.HTTP_201_CREATED)
async def save_utm_preset(
    payload: UTMPreset,
    current_user: CurrentUser,
    db: DB,
):
    """Save a new UTM preset."""
    user_id = current_user.get("user_id") or current_user.get("id")
    preset_id = hashlib.sha256(f"{user_id}:{payload.name}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
    doc = {
        "id": preset_id,
        "user_id": user_id,
        "name": payload.name.strip(),
        "utm_source": payload.utm_source,
        "utm_medium": payload.utm_medium,
        "utm_campaign": payload.utm_campaign,
        "utm_term": payload.utm_term,
        "utm_content": payload.utm_content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.utm_presets.insert_one(doc)
    return UTMPreset(
        id=preset_id,
        name=doc["name"],
        utm_source=doc.get("utm_source"),
        utm_medium=doc.get("utm_medium"),
        utm_campaign=doc.get("utm_campaign"),
        utm_term=doc.get("utm_term"),
        utm_content=doc.get("utm_content"),
    )


@router.delete("/utm-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_utm_preset(
    preset_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a UTM preset."""
    user_id = current_user.get("user_id") or current_user.get("id")
    res = await db.utm_presets.delete_one({"id": preset_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    return None


# ── Public Redirection Endpoint ──────────────────────────────────────────────

@router.get("/r/{code}")
async def redirect_short_link(
    code: str,
    request: Request,
    db: DB,
):
    """Public 302 redirect for shortened links with anonymous click tracking."""
    doc = await db.short_links.find_one({"code": code})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    target_url = doc.get("final_url") or doc.get("original_url")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Increment click count on link doc
    await db.short_links.update_one({"code": code}, {"$inc": {"clicks_count": 1}})

    # Record click event
    click_doc = {
        "code": code,
        "timestamp": now_iso,
        "referrer": request.headers.get("referer", "direct"),
        "user_agent": request.headers.get("user-agent", "")[:250],
    }
    await db.short_link_clicks.insert_one(click_doc)

    return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)
