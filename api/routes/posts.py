"""
Posts CRUD — schedule, list, update (optimistic lock), soft-delete.
All queries scope by workspace_id or user_id — never post_id alone.
Phase 5.5:  EC8 content policy + EC23 platform×content-type validation on create.
Phase 7.5:  Pre-publish content intelligence (7.5.3) + audit event logging.
Phase 10.1: Schedule density warning on post save.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request, status

from api.deps import CurrentUser, DB, QueueRedis, require_permission
from api.limiter import limiter
from api.models.post import (
    CreatePostRequest,
    PostResponse,
    PostStatus,
    UpdatePostRequest,
)
from utils.audit import log_audit_event
from utils.content_policy import check_content_policy, validate_platform_content_type
from utils.schedule_density import check_schedule_density

logger = logging.getLogger(__name__)
router = APIRouter(tags=["posts"])

_BLOCKED_STATUSES = {PostStatus.QUEUED, PostStatus.PROCESSING}
_SUBSCRIPTION_ALLOWED = {"active", "grace"}


def _plan_post_limit(plan: str) -> int:
    return {"starter": 30, "pro": 200, "agency": 2000}.get(plan, 30)


def _doc_to_response(doc: dict) -> PostResponse:
    doc.setdefault("id", str(doc.get("_id", "")))
    doc.pop("_id", None)
    doc.pop("deleted_at", None)
    return PostResponse(**doc)


# ── Create ───────────────────────────────────────────────────────────────────

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("post:create")])
@limiter.limit("100/hour")
async def create_post(
    request: Request,
    body: CreatePostRequest,
    current_user: CurrentUser,
    db: DB,
    queue_redis: QueueRedis,
) -> PostResponse:
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in _SUBSCRIPTION_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to schedule posts",
        )

    workspace_id = body.workspace_id or current_user.get("default_workspace_id")
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)

    # EC23 — Validate platform × content-type compatibility
    for platform in body.platforms:
        try:
            validate_platform_content_type(platform, body.post_type)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # EC8 — Content policy check (local, fast)
    policy_warnings: list[str] = []
    for platform in body.platforms:
        result = check_content_policy(body.content or "", platform)
        if not result.approved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Content policy violation",
                    "platform": platform,
                    "violations": result.violations,
                },
            )
        policy_warnings.extend(result.warnings)

    # Phase 7.5.3 — Pre-publish content intelligence (non-blocking warnings)
    intelligence_warnings: list[str] = []

    # Duplicate detection: SHA256 of content vs last 30 published posts
    if body.content:
        content_hash = hashlib.sha256(body.content.encode()).hexdigest()
        recent = await db.posts.count_documents({
            "user_id": user_id,
            "content_hash": content_hash,
            "status": "published",
        })
        if recent > 0:
            intelligence_warnings.append("Duplicate content detected — this post has been published before")

    # Platform character count enforcement
    _CHAR_LIMITS = {"twitter": 280, "linkedin": 3000, "instagram": 2200, "facebook": 63206, "tiktok": 2200, "youtube": 5000}
    for platform in body.platforms:
        limit = _CHAR_LIMITS.get(platform.lower())
        if limit and body.content and len(body.content) > limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{platform} character limit is {limit} (got {len(body.content)})",
            )

    # Hashtag limit warnings (platform best practices)
    _HASHTAG_LIMITS = {"instagram": 30, "twitter": 2, "linkedin": 5, "tiktok": 10}
    if body.content:
        import re as _re
        hashtag_count = len(_re.findall(r"#\w+", body.content))
        for platform in body.platforms:
            rec = _HASHTAG_LIMITS.get(platform.lower())
            if rec and hashtag_count > rec:
                intelligence_warnings.append(
                    f"{platform}: {hashtag_count} hashtags detected — recommended max is {rec}"
                )

    all_warnings = policy_warnings + intelligence_warnings
    if all_warnings:
        logger.info("Post pre-publish warnings user=%s: %s", user_id, all_warnings)

    # Phase 10.1 — Schedule density warning (non-blocking)
    density_ws = body.workspace_id or current_user.get("default_workspace_id")
    density_warnings = await check_schedule_density(
        db, density_ws, body.platforms, body.scheduled_time
    )
    for dw in density_warnings:
        logger.warning("Schedule density warning: %s", dw.message)
        all_warnings.append(dw.message)

    doc: dict = {
        "id": str(ObjectId()),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "content": body.content,
        "platforms": body.platforms,
        "media_ids": body.media_ids,
        "post_type": body.post_type,
        "timezone": body.timezone,
        "scheduled_time": body.scheduled_time,
        "status": PostStatus.SCHEDULED,
        "platform_results": {},
        "platform_post_urls": {},
        "status_history": [
            {"status": PostStatus.SCHEDULED, "timestamp": now, "actor": user_id}
        ],
        "thumbnail_urls": [],
        "pre_upload_status": None,
        "queue_job_id": None,
        "jitter_seconds": None,
        "version": 1,
        "dlq_reason": None,
        "content_hash": hashlib.sha256((body.content or "").encode()).hexdigest(),
        "schedule_warnings": all_warnings,
        "created_at": now,
        "updated_at": now,
    }

    await db.posts.insert_one(doc)

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.created",
        actor_id=user_id,
        resource_type="post",
        resource_id=doc["id"],
        metadata={"platforms": body.platforms, "scheduled_time": body.scheduled_time.isoformat()},
    )

    logger.info("Post created: %s user=%s workspace=%s", doc["id"], user_id, workspace_id)
    return _doc_to_response(doc)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("/posts", response_model=list[PostResponse],
            dependencies=[require_permission("post:read")])
async def list_posts(
    current_user: CurrentUser,
    db: DB,
    workspace_id: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PostResponse]:
    user_id = current_user["user_id"]
    ws_id = workspace_id or current_user.get("default_workspace_id")

    query: dict = {
        "workspace_id": ws_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    if status_filter:
        query["status"] = status_filter

    skip = (page - 1) * limit
    cursor = db.posts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_response(d) for d in docs]


# ── Get single ───────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostResponse,
            dependencies=[require_permission("post:read")])
async def get_post(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    user_id = current_user["user_id"]
    ws_id = current_user.get("default_workspace_id")

    doc = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0},
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Verify via workspace_id when present
    if doc.get("workspace_id") and doc["workspace_id"] != ws_id:
        member = await db.workspace_members.find_one(
            {"workspace_id": doc["workspace_id"], "user_id": user_id}
        )
        if not member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _doc_to_response(doc)


# ── Update (optimistic lock EC25) ────────────────────────────────────────────

@router.patch("/posts/{post_id}", response_model=PostResponse,
              dependencies=[require_permission("post:update")])
async def update_post(
    post_id: str,
    body: UpdatePostRequest,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    user_id = current_user["user_id"]

    existing = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0, "status": 1, "workspace_id": 1},
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if existing.get("status") in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post is currently being published",
        )

    now = datetime.now(timezone.utc)
    updates: dict = {"updated_at": now}
    if body.content is not None:
        updates["content"] = body.content
    if body.scheduled_time is not None:
        updates["scheduled_time"] = body.scheduled_time
    if body.platforms is not None:
        updates["platforms"] = body.platforms

    result = await db.posts.update_one(
        {
            "id": post_id,
            "user_id": user_id,
            "version": body.version,
            "deleted_at": {"$exists": False},
        },
        {"$set": updates, "$inc": {"version": 1}},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version conflict — fetch the latest version and retry",
        )

    updated = await db.posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.updated",
        actor_id=user_id,
        resource_type="post",
        resource_id=post_id,
        metadata={"fields_changed": list(updates.keys())},
    )

    return _doc_to_response(updated)


# ── Soft-delete ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("post:delete")])
async def delete_post(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    user_id = current_user["user_id"]

    existing = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0, "status": 1, "queue_job_id": 1, "media_ids": 1},
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if existing.get("status") in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post is currently being published",
        )

    now = datetime.now(timezone.utc)
    await db.posts.update_one(
        {"id": post_id, "user_id": user_id},
        {"$set": {"deleted_at": now, "updated_at": now, "status": PostStatus.CANCELLED}},
    )

    # Revoke Celery task if queued
    queue_job_id = existing.get("queue_job_id")
    if queue_job_id:
        try:
            from celery_workers.celery_app import celery_app
            celery_app.control.revoke(queue_job_id, terminate=False)
        except Exception as exc:
            logger.warning("Failed to revoke Celery task %s: %s", queue_job_id, exc)

    # Schedule media cleanup with 5-minute delay
    try:
        from celery_workers.tasks.cleanup import schedule_media_cleanup
        schedule_media_cleanup.apply_async(args=[post_id], countdown=300)
    except Exception as exc:
        logger.warning("Failed to schedule media cleanup for %s: %s", post_id, exc)

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.deleted",
        actor_id=user_id,
        resource_type="post",
        resource_id=post_id,
        metadata={},
    )
