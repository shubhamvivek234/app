"""
Phase 5.8 — Public REST API under /api/v1/public/.
Authenticated via API key (X-API-Key header) instead of Firebase JWT.
Scoped to workspace — never cross-workspace access.
"""
import hashlib
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Request, status
from pydantic import BaseModel

from api.deps import DB
from api.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public-api"])


# ── API key auth ──────────────────────────────────────────────────────────────

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
