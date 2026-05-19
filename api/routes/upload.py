"""
Media upload — direct-to-cloud session flow plus legacy server-stream fallback.
Queue depth guard: 503 with Retry-After if media_processing backlog > 200.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import magic
from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile, status
from redis.exceptions import RedisError

from api.deps import CurrentUser, DB, CacheRedis, QueueRedis, require_permission
from api.limiter import limiter
from api.models.media import (
    MediaAssetResponse,
    MediaStatus,
    MediaUploadAbortRequest,
    MediaUploadCompleteRequest,
    MediaUploadResponse,
    MediaUploadSessionRequest,
    MediaUploadSessionResponse,
)
from api.task_queue import enqueue_task
from utils.observability import capture_degraded_event, event_log, shorten_provider_error

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_FILE_BYTES: dict[str, int] = {
    "starter": 500 * 1024 * 1024,       # 500 MB
    "pro":     2 * 1024 * 1024 * 1024,   # 2 GB
    "agency":  10 * 1024 * 1024 * 1024,  # 10 GB
}
_DEFAULT_MAX_BYTES = _MAX_FILE_BYTES["starter"]

_CONCURRENT_LIMIT: dict[str, int] = {"starter": 2, "pro": 5, "agency": 10}
_PENDING_UPLOAD_LIMIT: dict[str, int] = {"starter": 10, "pro": 30, "agency": 75}

_ALLOWED_MIME_PREFIXES = ("image/", "video/")
_QUEUE_DEPTH_LIMIT = 200
_QUARANTINE_BASE = os.environ.get("QUARANTINE_PATH", "/tmp/quarantine")
_UPLOAD_SESSION_EXPIRES_IN = int(os.environ.get("UPLOAD_SESSION_EXPIRES_IN_SECONDS", "14400"))


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_queue_depth(queue_redis: QueueRedis) -> None:
    """Raise 503 if media_processing queue is overloaded."""
    try:
        depth = await queue_redis.llen("media_processing")
    except RedisError as exc:
        event_log(
            logger,
            "warning",
            "upload.queue_depth.degraded",
            exc_info=exc,
            route="/upload/session",
            failure_type="redis_unavailable",
            provider_error=shorten_provider_error(exc),
            outcome="skipped",
        )
        return

    if depth > _QUEUE_DEPTH_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media processing queue is at capacity. Please retry later.",
            headers={"Retry-After": "120"},
        )


async def _reserve_concurrent_upload_slot(
    cache_redis: CacheRedis,
    user_id: str,
    plan: str,
    *,
    ttl_seconds: int = _UPLOAD_SESSION_EXPIRES_IN,
) -> None:
    """Enforce per-user concurrent upload limit (atomic incr-then-check, LB-3)."""
    limit = _CONCURRENT_LIMIT.get(plan, 2)
    key = f"upload:concurrent:{user_id}"
    try:
        current = await cache_redis.incr(key)
        await cache_redis.expire(key, ttl_seconds)
    except RedisError as exc:
        event_log(
            logger,
            "warning",
            "upload.concurrent_limit.degraded",
            exc_info=exc,
            route="/upload/session",
            user_id=user_id,
            failure_type="redis_unavailable",
            provider_error=shorten_provider_error(exc),
            outcome="skipped",
        )
        return

    if current > limit:
        try:
            # Roll back the increment before raising
            await cache_redis.decr(key)
        except RedisError as exc:
            event_log(
                logger,
                "warning",
                "upload.concurrent_limit_rollback.degraded",
                exc_info=exc,
                route="/upload/session",
                user_id=user_id,
                failure_type="redis_unavailable",
                provider_error=shorten_provider_error(exc),
                outcome="degraded",
            )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Concurrent upload limit reached ({limit} for {plan} plan)",
            headers={"Retry-After": "60"},
        )


async def _check_user_upload_backlog(db, user_id: str, plan: str) -> None:
    """Prevent a single user from monopolizing the shared media queue."""
    limit = _PENDING_UPLOAD_LIMIT.get(plan, _PENDING_UPLOAD_LIMIT["starter"])
    pending_count = await db.media_assets.count_documents(
        {
            "user_id": user_id,
            "status": {"$in": [MediaStatus.PENDING_UPLOAD, MediaStatus.PROCESSING, MediaStatus.QUARANTINE]},
        }
    )
    if pending_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many in-flight uploads ({limit} for {plan} plan). Please wait for current uploads to finish.",
            headers={"Retry-After": "120"},
        )


async def _release_concurrent_slot(cache_redis: CacheRedis, user_id: str) -> None:
    key = f"upload:concurrent:{user_id}"
    try:
        val = await cache_redis.get(key)
        if val and int(val) > 0:
            await cache_redis.decr(key)
    except RedisError as exc:
        event_log(
            logger,
            "warning",
            "upload.concurrent_slot_release.degraded",
            exc_info=exc,
            user_id=user_id,
            failure_type="redis_unavailable",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )


def _ensure_allowed_mime(content_type: str) -> None:
    if not any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}",
        )


def _max_bytes_for_plan(plan: str) -> int:
    return _MAX_FILE_BYTES.get(plan, _DEFAULT_MAX_BYTES)


def _safe_filename(name: str) -> str:
    return Path(name or "").name or "upload.bin"


def _raw_storage_key(user_id: str, media_job_id: str, ext: str) -> str:
    filename = f"{media_job_id}{ext}"
    return f"raw/{user_id}/{filename}"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload/session",
    response_model=MediaUploadSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("media:upload")],
)
@limiter.limit("60/hour")
async def create_upload_session(
    request: Request,
    payload: Annotated[MediaUploadSessionRequest, Body(...)],
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
    queue_redis: QueueRedis,
) -> MediaUploadSessionResponse:
    from utils.storage import create_direct_upload_session

    user_id = current_user["user_id"]
    plan = current_user.get("plan", "starter")
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in {"active", "free", "grace"}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to upload media",
        )

    await _check_queue_depth(queue_redis)

    max_bytes = _max_bytes_for_plan(plan)
    if payload.file_size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size ({max_bytes // (1024 * 1024)} MB for {plan} plan)",
        )

    _ensure_allowed_mime(payload.content_type)
    await _check_user_upload_backlog(db, user_id, plan)
    await _reserve_concurrent_upload_slot(cache_redis, user_id, plan)

    media_job_id = str(uuid.uuid4())
    safe_name = _safe_filename(payload.filename)
    ext = Path(safe_name).suffix.lower() or _mime_to_ext(payload.content_type)
    source_storage_key = _raw_storage_key(user_id, media_job_id, ext)
    now = datetime.now(timezone.utc)

    try:
        event_log(
            logger,
            "info",
            "upload.session.started",
            route="/upload/session",
            user_id=user_id,
            mime_type=payload.content_type,
            file_size_bytes=payload.file_size_bytes,
            plan=plan,
            outcome="started",
        )
        upload = create_direct_upload_session(
            key=source_storage_key,
            content_type=payload.content_type,
            file_size_bytes=payload.file_size_bytes,
            expires_in=_UPLOAD_SESSION_EXPIRES_IN,
        )
    except RuntimeError as exc:
        await _release_concurrent_slot(cache_redis, user_id)
        event_log(
            logger,
            "warning",
            "upload.session.rejected",
            route="/upload/session",
            user_id=user_id,
            media_job_id=media_job_id,
            failure_type="storage_not_configured",
            provider_error=shorten_provider_error(exc),
            outcome="rejected",
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await _release_concurrent_slot(cache_redis, user_id)
        event_log(
            logger,
            "error",
            "upload.session.failed",
            exc_info=exc,
            route="/upload/session",
            user_id=user_id,
            media_job_id=media_job_id,
            failure_type="session_create_failed",
            provider_error=shorten_provider_error(exc),
            outcome="failed",
        )
        raise

    asset_doc = {
        "media_id": media_job_id,
        "user_id": user_id,
        "status": MediaStatus.PENDING_UPLOAD,
        "mime_type": payload.content_type,
        "file_size_bytes": payload.file_size_bytes,
        "original_filename": safe_name,
        "source_storage_key": source_storage_key,
        "upload_mode": upload["mode"],
        "upload_session_id": upload.get("upload_id"),
        "upload_expires_at": now.timestamp() + _UPLOAD_SESSION_EXPIRES_IN,
        "created_at": now,
        "processed_at": None,
        "error_message": None,
    }
    await db.media_assets.insert_one(asset_doc)
    event_log(
        logger,
        "info",
        "upload.session.created",
        route="/upload/session",
        user_id=user_id,
        media_job_id=media_job_id,
        mode=upload["mode"],
        source_storage_key=source_storage_key,
        file_size_bytes=payload.file_size_bytes,
        outcome="created",
    )
    return MediaUploadSessionResponse(
        media_job_id=media_job_id,
        status=MediaStatus.PENDING_UPLOAD,
        upload=upload,
    )


@router.post(
    "/upload/complete",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[require_permission("media:upload")],
)
async def complete_upload(
    payload: Annotated[MediaUploadCompleteRequest, Body(...)],
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
) -> MediaUploadResponse:
    from utils.storage import complete_direct_upload_session, head_storage_object_async

    user_id = current_user["user_id"]
    asset = await db.media_assets.find_one(
        {"media_id": payload.media_job_id, "user_id": user_id},
        {"_id": 0},
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media job not found")

    current_status = asset.get("status")
    if current_status in {MediaStatus.PROCESSING, MediaStatus.READY, MediaStatus.ARCHIVED}:
        return MediaUploadResponse(
            media_job_id=payload.media_job_id,
            status=current_status,
            message="Upload already completed",
        )
    if current_status == MediaStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload already failed")

    source_storage_key = asset.get("source_storage_key")
    upload_mode = asset.get("upload_mode")
    upload_session_id = asset.get("upload_session_id")

    try:
        if upload_mode == "multipart":
            if not upload_session_id or payload.upload_id != upload_session_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid multipart upload id")
            if not payload.parts:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multipart upload parts are required")
            complete_direct_upload_session(
                key=source_storage_key,
                upload_id=upload_session_id,
                parts=[{"PartNumber": part.part_number, "ETag": part.etag} for part in payload.parts],
            )

        head = await head_storage_object_async(source_storage_key)
        actual_size = int(head.get("file_size_bytes") or 0)
        if actual_size <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded object is empty")
    except HTTPException:
        raise
    except Exception as exc:
        event_log(
            logger,
            "error",
            "upload.complete.failed",
            exc_info=exc,
            route="/upload/complete",
            user_id=user_id,
            media_job_id=payload.media_job_id,
            failure_type="cloud_finalize_failed",
            provider_error=shorten_provider_error(exc),
            outcome="failed",
        )
        capture_degraded_event(
            "Upload completion failed",
            route="/upload/complete",
            user_id=user_id,
            media_job_id=payload.media_job_id,
            failure_type="cloud_finalize_failed",
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to finalize cloud upload") from exc

    await db.media_assets.update_one(
        {"media_id": payload.media_job_id, "user_id": user_id},
        {
            "$set": {
                "status": MediaStatus.PROCESSING,
                "file_size_bytes": actual_size,
                "upload_completed_at": datetime.now(timezone.utc),
            },
            "$unset": {"upload_session_id": "", "upload_expires_at": ""},
        },
    )
    enqueue_task(
        "celery_workers.tasks.media.process_media",
        args=[payload.media_job_id, user_id],
        queue="media_processing",
    )
    await _release_concurrent_slot(cache_redis, user_id)
    event_log(
        logger,
        "info",
        "upload.complete.queued",
        route="/upload/complete",
        user_id=user_id,
        media_job_id=payload.media_job_id,
        outcome="queued_for_processing",
    )
    return MediaUploadResponse(
        media_job_id=payload.media_job_id,
        status=MediaStatus.PROCESSING,
        message="Upload completed, processing started",
    )


@router.post(
    "/upload/{media_job_id}/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("media:upload")],
)
async def abort_upload(
    media_job_id: str,
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
    payload: Annotated[MediaUploadAbortRequest, Body()] = MediaUploadAbortRequest(),
) -> None:
    from utils.storage import abort_direct_upload_session

    user_id = current_user["user_id"]
    asset = await db.media_assets.find_one(
        {"media_id": media_job_id, "user_id": user_id},
        {"_id": 0},
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media job not found")

    if asset.get("upload_mode") == "multipart" and asset.get("upload_session_id"):
        try:
            abort_direct_upload_session(
                key=asset.get("source_storage_key"),
                upload_id=asset["upload_session_id"],
            )
        except Exception as exc:
            event_log(
                logger,
                "warning",
                "upload.abort.degraded",
                exc_info=exc,
                route="/upload/{media_job_id}/abort",
                user_id=user_id,
                media_job_id=media_job_id,
                failure_type="multipart_abort_failed",
                provider_error=shorten_provider_error(exc),
                outcome="degraded",
            )

    await db.media_assets.update_one(
        {"media_id": media_job_id, "user_id": user_id},
        {
            "$set": {
                "status": MediaStatus.FAILED,
                "error_message": payload.reason or "Upload aborted",
                "aborted_at": datetime.now(timezone.utc),
            },
            "$unset": {"upload_session_id": "", "upload_expires_at": ""},
        },
    )
    await _release_concurrent_slot(cache_redis, user_id)


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

    # EC-5: Block uploads for expired subscriptions (not just at publish time)
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in {"active", "free", "grace"}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to upload media",
        )

    # 1. Queue depth guard — before any I/O
    await _check_queue_depth(queue_redis)

    # 2. Hard file size check via Content-Length header
    content_length = request.headers.get("content-length")
    max_bytes = _max_bytes_for_plan(plan)
    if content_length:
        declared_size = int(content_length)
        if declared_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size ({max_bytes // (1024*1024)} MB for {plan} plan)",
            )

    # 3. Concurrent upload gate
    await _check_user_upload_backlog(db, user_id, plan)
    await _reserve_concurrent_upload_slot(cache_redis, user_id, plan, ttl_seconds=300)

    try:
        # 4. Read first 2048 bytes for MIME detection without buffering entire file
        header_bytes = await file.read(2048)
        mime_type = magic.from_buffer(header_bytes, mime=True)

        _ensure_allowed_mime(mime_type)

        # 5. Generate UUID filename — discard original to prevent path traversal
        ext = _mime_to_ext(mime_type)
        media_job_id = str(uuid.uuid4())
        safe_filename = f"{media_job_id}{ext}"

        # 6. Stream to quarantine path in chunks (never load entire file into RAM)
        quarantine_dir = Path(_QUARANTINE_BASE) / user_id
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine_path = str(quarantine_dir / safe_filename)

        _STREAM_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
        total_bytes = len(header_bytes)

        try:
            with open(quarantine_path, "wb") as fh:
                fh.write(header_bytes)
                while True:
                    chunk = await file.read(_STREAM_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds maximum size ({max_bytes // (1024*1024)} MB for {plan} plan)",
                        )
                    fh.write(chunk)
        except HTTPException:
            # Clean up partial file on size limit violation
            if os.path.exists(quarantine_path):
                os.unlink(quarantine_path)
            raise

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

        # 8. Enqueue media processing task without importing worker modules into API
        enqueue_task(
            "celery_workers.tasks.media.process_media",
            args=[media_job_id, user_id],
            queue="media_processing",
        )

        # 9. Purge any stale CDN cache entries for this media path (best-effort)
        await _purge_media_cdn_cache(user_id, safe_filename)

        event_log(
            logger,
            "info",
            "upload.legacy.queued",
            route="/upload",
            user_id=user_id,
            media_job_id=media_job_id,
            mime_type=mime_type,
            file_size_bytes=total_bytes,
            outcome="queued",
        )
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


# ── CDN purge helper ──────────────────────────────────────────────────────────

async def _purge_media_cdn_cache(user_id: str, filename: str) -> None:
    """
    Best-effort Cloudflare cache purge for a newly uploaded media file.
    Failures are logged but do not propagate — upload success is not affected.
    """
    try:
        from config.cdn import purge_by_urls  # noqa: PLC0415
        cf_public_base = os.environ.get("CF_R2_PUBLIC_URL", "")
        if not cf_public_base:
            return
        url = f"{cf_public_base}/uploads/{filename}"
        await purge_by_urls([url])
        event_log(logger, "info", "upload.cdn_purge.requested", url=url, outcome="requested")
    except Exception as exc:
        event_log(
            logger,
            "warning",
            "upload.cdn_purge.degraded",
            exc_info=exc,
            failure_type="cdn_purge_failed",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )


async def purge_media_cache(urls: list[str]) -> None:
    """
    Public helper: purge a list of Cloudflare-cached media URLs.
    Wraps config.cdn.purge_by_urls with error suppression so callers
    don't need to handle CDN failures.
    """
    if not urls:
        return
    try:
        from config.cdn import purge_by_urls  # noqa: PLC0415
        await purge_by_urls(urls)
    except Exception as exc:
        event_log(
            logger,
            "warning",
            "upload.cdn_purge_bulk.degraded",
            exc_info=exc,
            failure_type="cdn_purge_failed",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )


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
