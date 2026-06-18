"""Composer audio rendering routes."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DB, require_permission
from api.models.media import (
    AudioRenderRequest,
    AudioRenderResponse,
    MediaAssetResponse,
    MediaStatus,
    TemporaryAudioCleanupRequest,
)
from api.task_queue import enqueue_task
from utils.observability import event_log
from utils.temp_audio_cleanup import cleanup_temporary_audio_assets

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audio-render"])


def _asset_kind_for_doc(doc: dict | None) -> str:
    if not doc:
        return ""
    kind = doc.get("asset_kind")
    if kind:
        return str(kind)
    mime_type = doc.get("mime_type") or doc.get("content_type") or ""
    if str(mime_type).startswith("video/"):
        return "video"
    if str(mime_type).startswith("audio/"):
        return "audio"
    return "image"


def _storage_ref(doc: dict) -> str | None:
    return doc.get("storage_key") or doc.get("media_url") or doc.get("url")


@router.post(
    "/media/{video_media_id}/audio/render",
    response_model=AudioRenderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[require_permission("media:upload")],
)
async def render_video_audio(
    video_media_id: str,
    payload: AudioRenderRequest,
    current_user: CurrentUser,
    db: DB,
) -> AudioRenderResponse:
    user_id = current_user["user_id"]
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in {"active", "free", "grace"}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to render media",
        )

    mix = payload.mix.model_dump()
    if mix.get("trim_end_ms") is not None and mix["trim_end_ms"] <= mix.get("trim_start_ms", 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Audio trim end must be after trim start",
        )

    video_doc = await db.media_assets.find_one(
        {"media_id": video_media_id, "user_id": user_id},
        {"_id": 0},
    )
    if not video_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video media not found")
    if video_doc.get("status") != MediaStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Video media is not ready")
    if _asset_kind_for_doc(video_doc) != "video":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Audio can only be added to videos")
    if not _storage_ref(video_doc):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Video storage reference is missing")

    audio_doc = await db.media_assets.find_one(
        {"media_id": mix["audio_media_id"], "user_id": user_id},
        {"_id": 0},
    )
    if not audio_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio media not found")
    if audio_doc.get("status") != MediaStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audio media is not ready")
    if _asset_kind_for_doc(audio_doc) != "audio":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected media is not an audio asset")
    if not _storage_ref(audio_doc):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audio storage reference is missing")

    render_job_id = str(uuid.uuid4())
    rendered_media_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    source_label = audio_doc.get("source_label") or audio_doc.get("original_filename") or audio_doc.get("filename") or "Custom audio"
    asset_doc = {
        "media_id": rendered_media_id,
        "user_id": user_id,
        "workspace_id": current_user.get("default_workspace_id") or user_id,
        "status": MediaStatus.PROCESSING,
        "asset_kind": "video",
        "mime_type": "video/mp4",
        "parent_media_id": video_media_id,
        "render_job_id": render_job_id,
        "audio_mix": {
            **mix,
            "source_label": source_label,
        },
        "source_provider": "audio_render",
        "source_item_id": mix["audio_media_id"],
        "source_label": f"{video_doc.get('source_label') or video_doc.get('original_filename') or 'Video'} + {source_label}",
        "thumbnail_url": video_doc.get("thumbnail_url"),
        "duration_seconds": video_doc.get("duration_seconds"),
        "width": video_doc.get("width"),
        "height": video_doc.get("height"),
        "has_audio": True,
        "created_at": now,
        "processed_at": None,
        "error_message": None,
    }
    await db.media_assets.insert_one(asset_doc)

    enqueue_task(
        "celery_workers.tasks.media.render_video_audio_mix",
        args=[render_job_id, rendered_media_id, video_media_id, mix["audio_media_id"], user_id, mix],
        queue="media_processing",
    )
    event_log(
        logger,
        "info",
        "audio.render.queued",
        route="/media/{video_media_id}/audio/render",
        user_id=user_id,
        media_job_id=rendered_media_id,
        video_media_id=video_media_id,
        audio_media_id=mix["audio_media_id"],
        render_job_id=render_job_id,
        outcome="queued",
    )
    return AudioRenderResponse(
        render_job_id=render_job_id,
        media_job_id=rendered_media_id,
        status=MediaStatus.PROCESSING,
    )


@router.get(
    "/media/audio-renders/{render_job_id}",
    response_model=MediaAssetResponse,
    dependencies=[require_permission("media:read")],
)
async def get_audio_render_status(
    render_job_id: str,
    current_user: CurrentUser,
    db: DB,
) -> MediaAssetResponse:
    doc = await db.media_assets.find_one(
        {"render_job_id": render_job_id, "user_id": current_user["user_id"]},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio render not found")
    return MediaAssetResponse(**doc)


@router.post(
    "/media/audio/temp/cleanup",
    dependencies=[require_permission("media:upload")],
)
async def cleanup_temporary_audio(
    payload: TemporaryAudioCleanupRequest,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    if not payload.media_ids and not payload.composer_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide media_ids or composer_session_id",
        )
    return await cleanup_temporary_audio_assets(
        db,
        user_id=current_user["user_id"],
        workspace_id=current_user.get("default_workspace_id") or current_user["user_id"],
        media_ids=payload.media_ids,
        composer_session_id=payload.composer_session_id,
        reason=payload.reason,
    )
