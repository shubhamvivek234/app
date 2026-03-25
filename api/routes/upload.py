"""
Media upload — quarantine, MIME validation, Celery processing.
Hard file-size check via Content-Length before buffering.
Queue depth guard: 503 with Retry-After if media_processing backlog > 200.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import magic
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from api.deps import CurrentUser, DB, CacheRedis, QueueRedis, require_permission
from api.limiter import limiter
from api.models.media import MediaAssetResponse, MediaStatus, MediaUploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_FILE_BYTES: dict[str, int] = {
    "starter": 100 * 1024 * 1024,   # 100 MB
    "pro":     500 * 1024 * 1024,   # 500 MB
    "agency":  2 * 1024 * 1024 * 1024,  # 2 GB
}
_DEFAULT_MAX_BYTES = _MAX_FILE_BYTES["starter"]

_CONCURRENT_LIMIT: dict[str, int] = {"starter": 2, "pro": 5, "agency": 10}

_ALLOWED_MIME_PREFIXES = ("image/", "video/")
_QUEUE_DEPTH_LIMIT = 200
_QUARANTINE_BASE = os.environ.get("QUARANTINE_PATH", "/tmp/quarantine")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_queue_depth(queue_redis: QueueRedis) -> None:
    """Raise 503 if media_processing queue is overloaded."""
    depth = await queue_redis.llen("media_processing")
    if depth > _QUEUE_DEPTH_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media processing queue is at capacity. Please retry later.",
            headers={"Retry-After": "120"},
        )


async def _check_concurrent_uploads(cache_redis: CacheRedis, user_id: str, plan: str) -> None:
    """Enforce per-user concurrent upload limit (atomic incr-then-check, LB-3)."""
    limit = _CONCURRENT_LIMIT.get(plan, 2)
    key = f"upload:concurrent:{user_id}"
    # Atomic increment first, then check — avoids GET/INCR race condition
    current = await cache_redis.incr(key)
    await cache_redis.expire(key, 300)  # auto-expire after 5 min
    if current > limit:
        # Roll back the increment before raising
        await cache_redis.decr(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Concurrent upload limit reached ({limit} for {plan} plan)",
            headers={"Retry-After": "60"},
        )


async def _release_concurrent_slot(cache_redis: CacheRedis, user_id: str) -> None:
    key = f"upload:concurrent:{user_id}"
    val = await cache_redis.get(key)
    if val and int(val) > 0:
        await cache_redis.decr(key)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=MediaUploadResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[require_permission("media:upload")])
@limiter.limit("30/hour")
async def upload_media(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
    queue_redis: QueueRedis,
) -> MediaUploadResponse:
    user_id = current_user["user_id"]
    plan = current_user.get("plan", "starter")

    # 1. Queue depth guard — before any I/O
    await _check_queue_depth(queue_redis)

    # 2. Hard file size check via Content-Length header
    content_length = request.headers.get("content-length")
    max_bytes = _MAX_FILE_BYTES.get(plan, _DEFAULT_MAX_BYTES)
    if content_length:
        declared_size = int(content_length)
        if declared_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size ({max_bytes // (1024*1024)} MB for {plan} plan)",
            )

    # 3. Concurrent upload gate
    await _check_concurrent_uploads(cache_redis, user_id, plan)

    try:
        # 4. Read first 2048 bytes for MIME detection without buffering entire file
        header_bytes = await file.read(2048)
        mime_type = magic.from_buffer(header_bytes, mime=True)

        if not any(mime_type.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: {mime_type}",
            )

        # 5. Generate UUID filename — discard original to prevent path traversal
        ext = _mime_to_ext(mime_type)
        media_job_id = str(uuid.uuid4())
        safe_filename = f"{media_job_id}{ext}"

        # 6. Write to quarantine path
        quarantine_dir = Path(_QUARANTINE_BASE) / user_id
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine_path = str(quarantine_dir / safe_filename)

        # Read the rest of the file and enforce size limit
        remaining = await file.read()
        total_bytes = len(header_bytes) + len(remaining)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size ({max_bytes // (1024*1024)} MB for {plan} plan)",
            )

        with open(quarantine_path, "wb") as fh:
            fh.write(header_bytes)
            fh.write(remaining)

        # 7. Persist media_asset record
        now = datetime.now(timezone.utc)
        asset_doc = {
            "media_id": media_job_id,
            "user_id": user_id,
            "status": MediaStatus.QUARANTINE,
            "mime_type": mime_type,
            "file_size_bytes": total_bytes,
            "quarantine_path": quarantine_path,
            "original_filename_discarded": True,
            "created_at": now,
            "processed_at": None,
            "error_message": None,
        }
        await db.media_assets.insert_one(asset_doc)

        # 8. Enqueue Celery task
        from celery_workers.tasks.media import process_media
        process_media.apply_async(
            args=[media_job_id, user_id],
            queue="media_processing",
        )

        logger.info("Media upload queued: %s user=%s mime=%s size=%d", media_job_id, user_id, mime_type, total_bytes)
        return MediaUploadResponse(media_job_id=media_job_id, status=MediaStatus.QUARANTINE)

    finally:
        await _release_concurrent_slot(cache_redis, user_id)


@router.get("/upload/{media_job_id}", response_model=MediaAssetResponse)
async def get_upload_status(
    media_job_id: str,
    current_user: CurrentUser,
    db: DB,
) -> MediaAssetResponse:
    user_id = current_user["user_id"]

    doc = await db.media_assets.find_one(
        {"media_id": media_job_id, "user_id": user_id},
        {"_id": 0},
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media job not found")

    return MediaAssetResponse(**doc)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _mime_to_ext(mime_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/webm": ".webm",
    }
    return mapping.get(mime_type, ".bin")
