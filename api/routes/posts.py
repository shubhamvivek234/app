"""
Posts CRUD — schedule, list, update (optimistic lock), soft-delete.
All queries scope by workspace_id or user_id — never post_id alone.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from api.deps import CurrentUser, DB, QueueRedis
from api.models.post import (
    CreatePostRequest,
    PostResponse,
    PostStatus,
    UpdatePostRequest,
)

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

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
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
        "created_at": now,
        "updated_at": now,
    }

    await db.posts.insert_one(doc)
    logger.info("Post created: %s user=%s workspace=%s", doc["id"], user_id, workspace_id)
    return _doc_to_response(doc)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("/posts", response_model=list[PostResponse])
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

@router.get("/posts/{post_id}", response_model=PostResponse)
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

@router.patch("/posts/{post_id}", response_model=PostResponse)
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
    return _doc_to_response(updated)


# ── Soft-delete ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
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
