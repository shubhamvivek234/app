"""
Phase 5.8 — Public REST API under /api/v1/public/.
Authenticated via API key (X-API-Key header) instead of Firebase JWT.
Scoped to user — never cross-user access.
"""
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Header, Request, status
from pydantic import BaseModel

from api.deps import DB
from api.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public-api"])


# ── API key auth ──────────────────────────────────────────────────────────────

async def _resolve_user_id(x_api_key: str | None, db) -> str:
    """
    Resolve user_id from an API key.
    Hashes the key, looks it up in api_keys collection, returns user_id.
    Updates last_used_at as a side effect.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    doc = await db.api_keys.find_one({"key_hash": key_hash, "revoked": {"$ne": True}})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )
    try:
        await db.api_keys.update_one(
            {"_id": doc["_id"]},
            {"$set": {"last_used_at": datetime.now(timezone.utc)}},
        )
    except Exception:
        pass
    return doc["user_id"]


async def _resolve_workspace(x_api_key: str | None, db) -> dict:
    """
    Look up workspace by hashed API key. Returns workspace doc.

    Checks two systems in order:
    1. api_keys collection (supports multiple keys, scopes, revocation)
    2. workspaces.api_key_hash (legacy single-key per workspace)
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    # Primary: check api_keys collection (multi-key, revocable)
    api_key_doc = await db.api_keys.find_one({
        "key_hash": key_hash,
        "revoked": {"$ne": True},
    })
    if api_key_doc:
        workspace_id = api_key_doc.get("workspace_id")
        workspace = await db.workspaces.find_one({"_id": workspace_id}) or \
                    await db.workspaces.find_one({"workspace_id": workspace_id})
        if workspace:
            # Update last_used_at (best-effort, non-blocking)
            try:
                await db.api_keys.update_one(
                    {"_id": api_key_doc["_id"]},
                    {"$set": {"last_used_at": datetime.now(timezone.utc)}},
                )
            except Exception:
                pass
            return workspace

    # Fallback: legacy single workspace api_key_hash
    workspace = await db.workspaces.find_one({"api_key_hash": key_hash, "active": True})
    if workspace:
        return workspace

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked API key",
    )


# ── Response models ───────────────────────────────────────────────────────────

class PublicPostSummary(BaseModel):
    id: str
    status: str
    platforms: list[str]
    scheduled_time: datetime
    created_at: datetime
    platform_results: dict = {}


class PublicPostListResponse(BaseModel):
    data: list[PublicPostSummary]
    total: int
    page: int
    limit: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/posts", response_model=PublicPostListResponse)
@limiter.limit("60/minute")
async def public_list_posts(
    request: Request,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    page: int = 1,
    limit: int = 20,
) -> PublicPostListResponse:
    """List posts for the workspace associated with the API key."""
    workspace = await _resolve_workspace(x_api_key, db)
    workspace_id = str(workspace["_id"])

    if limit > 100:
        limit = 100

    query = {"workspace_id": workspace_id, "deleted_at": {"$exists": False}}
    total = await db.posts.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.posts.find(
        query,
        {"_id": 0, "id": 1, "status": 1, "platforms": 1,
         "scheduled_time": 1, "created_at": 1, "platform_results": 1},
    ).sort("scheduled_time", -1).skip(skip).limit(limit)

    docs = await cursor.to_list(length=limit)
    return PublicPostListResponse(
        data=[PublicPostSummary(**d) for d in docs],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/posts/{post_id}", response_model=PublicPostSummary)
@limiter.limit("60/minute")
async def public_get_post(
    request: Request,
    post_id: str,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> PublicPostSummary:
    workspace = await _resolve_workspace(x_api_key, db)
    workspace_id = str(workspace["_id"])

    doc = await db.posts.find_one(
        {"id": post_id, "workspace_id": workspace_id, "deleted_at": {"$exists": False}},
        {"_id": 0, "id": 1, "status": 1, "platforms": 1,
         "scheduled_time": 1, "created_at": 1, "platform_results": 1},
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return PublicPostSummary(**doc)


# ── Accounts ──────────────────────────────────────────────────────────────────

class PublicAccount(BaseModel):
    id: str
    platform: str
    username: Optional[str] = None
    name: Optional[str] = None
    status: str = "active"


@router.get("/accounts")
@limiter.limit("60/minute")
async def public_list_accounts(
    request: Request,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """List all active connected social accounts for this API key's user."""
    user_id = await _resolve_user_id(x_api_key, db)
    cursor = db.social_accounts.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "account_id": 1, "platform": 1, "username": 1, "name": 1},
    )
    accounts = await cursor.to_list(length=200)
    return {
        "accounts": [
            {
                "id": a.get("account_id", ""),
                "platform": a.get("platform", ""),
                "username": a.get("username") or a.get("name"),
                "status": "active",
            }
            for a in accounts
        ],
        "total": len(accounts),
    }


# ── Create post ───────────────────────────────────────────────────────────────

class PublicCreatePostRequest(BaseModel):
    content: str
    account_ids: list[str]
    scheduled_at: Optional[datetime] = None
    publish_now: bool = False
    media_urls: list[str] = []


@router.post("/posts", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def public_create_post(
    request: Request,
    body: PublicCreatePostRequest,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Create a post — draft, scheduled, or publish now."""
    user_id = await _resolve_user_id(x_api_key, db)

    if not body.content.strip():
        raise HTTPException(status_code=422, detail="Content cannot be empty")
    if not body.account_ids:
        raise HTTPException(status_code=422, detail="account_ids cannot be empty")

    # Validate that all accounts belong to this user
    accounts = await db.social_accounts.find(
        {"account_id": {"$in": body.account_ids}, "user_id": user_id, "is_active": True},
        {"account_id": 1, "platform": 1},
    ).to_list(length=100)

    found_ids = {a["account_id"] for a in accounts}
    invalid = [aid for aid in body.account_ids if aid not in found_ids]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown or inactive account IDs: {invalid}")

    platforms = list({a["platform"] for a in accounts})
    now = datetime.now(timezone.utc)

    if body.publish_now:
        post_status = "publishing"
        scheduled_time = now
    elif body.scheduled_at:
        post_status = "scheduled"
        scheduled_time = body.scheduled_at
    else:
        post_status = "draft"
        scheduled_time = now

    post_id = str(ObjectId())
    doc = {
        "id": post_id,
        "user_id": user_id,
        "content": body.content,
        "platforms": platforms,
        "account_ids": body.account_ids,
        "media_urls": body.media_urls,
        "scheduled_time": scheduled_time,
        "status": post_status,
        "created_at": now,
        "updated_at": now,
        "history": [{"status": post_status, "timestamp": now, "actor": f"api_key:{user_id}"}],
        "platform_results": {},
    }
    await db.posts.insert_one(doc)

    return {
        "id": post_id,
        "status": post_status,
        "scheduled_at": scheduled_time.isoformat(),
        "message": (
            "Post is being published now." if body.publish_now
            else f"Post scheduled for {scheduled_time.isoformat()}." if body.scheduled_at
            else "Post saved as draft."
        ),
    }


# ── Delete post ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def public_delete_post(
    request: Request,
    post_id: str,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Delete a post owned by this API key's user."""
    user_id = await _resolve_user_id(x_api_key, db)
    result = await db.posts.update_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"$set": {"deleted_at": datetime.now(timezone.utc), "status": "deleted"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")


# ── Retry failed post ─────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/retry")
@limiter.limit("20/minute")
async def public_retry_post(
    request: Request,
    post_id: str,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Retry a failed post."""
    user_id = await _resolve_user_id(x_api_key, db)
    now = datetime.now(timezone.utc)
    result = await db.posts.update_one(
        {"id": post_id, "user_id": user_id, "status": {"$in": ["failed", "partial"]}},
        {
            "$set": {"status": "scheduled", "updated_at": now},
            "$push": {"history": {"status": "scheduled", "timestamp": now, "actor": f"api_key_retry:{user_id}"}},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Failed post not found or not retryable")
    return {"post_id": post_id, "status": "scheduled", "message": "Post queued for retry."}


# ── AI content generation ─────────────────────────────────────────────────────

_PLATFORM_HINTS: dict[str, str] = {
    "twitter":   " Keep it under 280 characters.",
    "linkedin":  " Make it professional and insight-driven.",
    "instagram": " Make it engaging with 3–5 relevant hashtags.",
    "facebook":  " Write in a conversational tone.",
    "tiktok":    " Write a short, punchy caption with trending language.",
    "youtube":   " Write a concise, keyword-rich description.",
}

_SYSTEM_MESSAGE_BASE = (
    "You are a social media content expert. "
    "Generate engaging, brand-safe social media posts. "
    "Return only the post text — no explanations or meta-commentary."
)


class PublicAIRequest(BaseModel):
    topic: str
    platform: Optional[str] = None
    tone: Optional[str] = None
    count: int = 1
    additional_context: Optional[str] = None


@router.post("/ai/generate")
@limiter.limit("20/minute")
async def public_generate_content(
    request: Request,
    body: PublicAIRequest,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Generate platform-optimized social media content via AI."""
    user_id = await _resolve_user_id(x_api_key, db)

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service is not configured")

    if not body.topic.strip():
        raise HTTPException(status_code=422, detail="Topic cannot be empty")

    platform_hint = _PLATFORM_HINTS.get(body.platform or "", "")
    tone_hint = f" Use a {body.tone} tone." if body.tone else ""
    context_hint = f" Additional context: {body.additional_context}" if body.additional_context else ""
    system_message = f"{_SYSTEM_MESSAGE_BASE}{platform_hint}{tone_hint}"

    prompt = f"Write a social media post about: {body.topic}.{context_hint}"

    count = max(1, min(body.count, 5))
    results = []

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        for i in range(count):
            session_id = f"mcp-content-gen-{user_id}-{uuid.uuid4()}"
            chat = (
                LlmChat(api_key=api_key, session_id=session_id, system_message=system_message)
                .with_model("openai", "gpt-4o-mini")
            )
            response = await chat.send_message(UserMessage(text=prompt))
            results.append(response)
    except Exception as exc:
        logger.error("Public AI generation error user=%s: %s", user_id, exc)
        raise HTTPException(status_code=502, detail="AI content generation failed. Please try again.")

    return {
        "variations": results,
        "platform": body.platform,
        "count": len(results),
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
@limiter.limit("60/minute")
async def public_get_stats(
    request: Request,
    db: DB,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Dashboard statistics for the API key's user."""
    user_id = await _resolve_user_id(x_api_key, db)

    total_posts, scheduled, published, failed, accounts = await __import__("asyncio").gather(
        db.posts.count_documents({"user_id": user_id, "deleted_at": {"$exists": False}}),
        db.posts.count_documents({"user_id": user_id, "status": "scheduled", "deleted_at": {"$exists": False}}),
        db.posts.count_documents({"user_id": user_id, "status": "published", "deleted_at": {"$exists": False}}),
        db.posts.count_documents({"user_id": user_id, "status": {"$in": ["failed", "partial"]}, "deleted_at": {"$exists": False}}),
        db.social_accounts.count_documents({"user_id": user_id, "is_active": True}),
    )

    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled,
        "published_posts": published,
        "failed_posts": failed,
        "connected_accounts": accounts,
    }
