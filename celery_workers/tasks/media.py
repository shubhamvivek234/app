"""
Phase 2 — Media processing Celery task.
Validates, compresses, thumbnails. Moves from /quarantine/ to permanent storage on success.

Section 18.8 — per-platform publish notifications (success, failure, DLQ, recovery).
"""
import asyncio
import logging
import os
import pathlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

# ── Notification type → notification_prefs event key ─────────────────────────
_EVENT_MAP: dict[str, str] = {
    "publish_success":            "post.published",
    "publish_failed":             "post.failed",
    "publish_permanently_failed": "post.dlq",
    "publish_partial_recovery":   "post.published",
    "publish_recovered":          "post.published",
    "pre_upload_timeout":         "post.dlq",
}

_TITLES: dict[str, str] = {
    "publish_success":            "Post Published ✓",
    "publish_failed":             "Post Failed",
    "publish_permanently_failed": "Post Permanently Failed",
    "publish_partial_recovery":   "Post Recovered ✓",
    "publish_recovered":          "Post Recovered ✓",
    "pre_upload_timeout":         "Post Permanently Failed",
}

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


# ── Media Processing ──────────────────────────────────────────────────────────

@celery_app.task(
    name="celery_workers.tasks.media.process_media",
    bind=True,
    max_retries=2,
    acks_late=True,
    queue="media_processing",
    time_limit=7500,       # 2h5m — allows 2h FFmpeg transcode + upload for 10GB files
    soft_time_limit=7200,  # 2h — soft limit triggers graceful abort
)
def process_media(self, media_job_id: str, user_id: str) -> dict:
    return run_async(_async_process_media(self, media_job_id, user_id))


async def _get_db():
    client = await get_client()
    return client, client[os.environ["DB_NAME"]]


async def _mark_media_failed(media_job_id: str, error_message: str) -> None:
    try:
        _client, db = await _get_db()
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "failed", "error_message": error_message, "source_stage": "failed"}},
        )
    except Exception as mark_exc:
        logger.error("Failed to mark media %s as failed: %s", media_job_id, mark_exc)


@celery_app.task(
    name="celery_workers.tasks.media.import_remote_media",
    bind=True,
    max_retries=1,
    acks_late=True,
    queue="media_processing",
    time_limit=1800,
    soft_time_limit=1500,
)
def import_remote_media(self, media_job_id: str, user_id: str) -> dict:
    return run_async(_async_import_remote_media(self, media_job_id, user_id))


@celery_app.task(
    name="celery_workers.tasks.media.render_video_audio_mix",
    bind=True,
    max_retries=1,
    acks_late=True,
    queue="media_processing",
    time_limit=7500,
    soft_time_limit=7200,
)
def render_video_audio_mix(
    self,
    render_job_id: str,
    rendered_media_id: str,
    video_media_id: str,
    audio_media_id: str,
    user_id: str,
    mix: dict,
) -> dict:
    return run_async(_async_render_video_audio_mix(
        self,
        render_job_id,
        rendered_media_id,
        video_media_id,
        audio_media_id,
        user_id,
        mix,
    ))


async def _async_import_remote_media(task, media_job_id: str, user_id: str) -> dict:
    temp_path: str | None = None
    cache_redis = None
    auth_ref = None
    try:
        import json

        from api.routes.upload import _mime_to_ext, _release_concurrent_slot
        from api.task_queue import enqueue_task
        from db.redis_client import get_cache_redis
        from utils.media_source_imports import (
            build_download_url_for_google_photos,
            stream_remote_file_to_path,
        )
        from utils.redis_resilience import safe_get
        from utils.storage import upload_file_from_path_async

        cache_redis = get_cache_redis()
        _client, db = await _get_db()
        asset = await db.media_assets.find_one({"media_id": media_job_id, "user_id": user_id}, {"_id": 0})
        if not asset:
            return {"status": "not_found"}

        provider = asset.get("source_provider")
        download_url = asset.get("source_download_url")
        auth_ref = asset.get("source_auth_ref")
        if provider == "google_photos":
            download_url = build_download_url_for_google_photos(download_url, asset.get("mime_type"))
        if not provider or not download_url:
            raise ValueError("Remote media import is missing provider or download URL")

        headers = {}
        if auth_ref and cache_redis is not None:
            raw_auth = await safe_get(cache_redis, auth_ref, default=None, feature="Media source auth read")
            if raw_auth:
                auth_payload = raw_auth if isinstance(raw_auth, dict) else json.loads(raw_auth)
                if auth_payload.get("type") == "bearer" and auth_payload.get("token"):
                    headers["Authorization"] = f"Bearer {auth_payload['token']}"

        filename_hint = asset.get("original_filename") or f"{media_job_id}{_mime_to_ext(asset.get('mime_type') or '')}"
        suffix = Path(filename_hint).suffix or _mime_to_ext(asset.get("mime_type") or "application/octet-stream")
        fd, temp_path = tempfile.mkstemp(prefix=f"media-import-{media_job_id}-", suffix=suffix or ".bin")
        os.close(fd)

        fetch_result = await stream_remote_file_to_path(
            provider=provider,
            url=download_url,
            destination_path=temp_path,
            headers=headers,
            max_bytes=int(asset.get("max_file_size_bytes") or 500 * 1024 * 1024),
        )

        mime_type = fetch_result["mime_type"]
        source_storage_key = asset["source_storage_key"]
        source_folder = str(Path(source_storage_key).parent)
        source_filename = Path(source_storage_key).name
        await upload_file_from_path_async(temp_path, source_filename, mime_type, folder=source_folder)

        await db.media_assets.update_one(
            {"media_id": media_job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "processing",
                    "source_stage": "processing",
                    "mime_type": mime_type,
                    "file_size_bytes": fetch_result["file_size_bytes"],
                    "remote_fetched_at": datetime.now(timezone.utc),
                }
            },
        )
        enqueue_task(
            "celery_workers.tasks.media.process_media",
            args=[media_job_id, user_id],
            queue="media_processing",
        )
        return {"status": "processing"}
    except Exception as exc:
        logger.error("Remote media import failed for %s: %s", media_job_id, exc)
        current_retries = getattr(task.request, "retries", 0)
        max_retries = getattr(task, "max_retries", 0)
        if current_retries >= max_retries:
            await _mark_media_failed(media_job_id, str(exc))
            try:
                _client, db = await _get_db()
                await db.media_assets.update_one(
                    {"media_id": media_job_id, "user_id": user_id},
                    {"$set": {"source_stage": "failed"}},
                )
            except Exception as mark_exc:
                logger.error("Failed to mark remote media import %s as failed: %s", media_job_id, mark_exc)
            raise
        raise task.retry(countdown=15, exc=exc)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as cleanup_exc:
                logger.warning("Could not delete remote import temp file %s: %s", temp_path, cleanup_exc)
        try:
            from api.routes.upload import _release_concurrent_slot
            if cache_redis is None:
                from db.redis_client import get_cache_redis
                cache_redis = get_cache_redis()
            await _release_concurrent_slot(cache_redis, user_id)
        except Exception as exc:
            logger.warning("Could not release media import slot for %s: %s", user_id, exc)
        if auth_ref and cache_redis is not None:
            try:
                from utils.redis_resilience import safe_delete
                await safe_delete(cache_redis, auth_ref, default=0, feature="Media source auth cleanup")
            except Exception as exc:
                logger.warning("Could not cleanup media import auth %s: %s", auth_ref, exc)


def _asset_kind_for_doc(doc: dict | None) -> str:
    if not doc:
        return ""
    if doc.get("asset_kind"):
        return str(doc["asset_kind"])
    mime_type = str(doc.get("mime_type") or doc.get("content_type") or "")
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "image"


def _storage_ref(doc: dict) -> str | None:
    return doc.get("storage_key") or doc.get("media_url") or doc.get("url")


async def _mark_render_failed(rendered_media_id: str, error_message: str) -> None:
    try:
        _client, db = await _get_db()
        await db.media_assets.update_one(
            {"media_id": rendered_media_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "processed_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception as mark_exc:
        logger.error("Failed to mark audio render %s as failed: %s", rendered_media_id, mark_exc)


async def _async_render_video_audio_mix(
    task,
    render_job_id: str,
    rendered_media_id: str,
    video_media_id: str,
    audio_media_id: str,
    user_id: str,
    mix: dict,
) -> dict:
    video_path: str | None = None
    audio_path: str | None = None
    output_path: str | None = None
    try:
        from media_pipeline.validation import validate_media
        from media_pipeline.ffmpeg_worker import render_video_with_audio
        from utils.observability import event_log, shorten_provider_error
        from utils.storage import download_file_to_path_async, upload_file_from_path_async

        _client, db = await _get_db()
        rendered_asset = await db.media_assets.find_one(
            {"media_id": rendered_media_id, "user_id": user_id},
            {"_id": 0},
        )
        if not rendered_asset:
            return {"status": "not_found"}

        video_asset = await db.media_assets.find_one(
            {"media_id": video_media_id, "user_id": user_id},
            {"_id": 0},
        )
        audio_asset = await db.media_assets.find_one(
            {"media_id": audio_media_id, "user_id": user_id},
            {"_id": 0},
        )
        if not video_asset or not audio_asset:
            raise ValueError("Source video or audio no longer exists")
        if video_asset.get("status") != "ready" or audio_asset.get("status") != "ready":
            raise ValueError("Source video and audio must be ready before rendering")
        if _asset_kind_for_doc(video_asset) != "video":
            raise ValueError("Audio render source media is not a video")
        if _asset_kind_for_doc(audio_asset) != "audio":
            raise ValueError("Selected audio media is not an audio asset")

        event_log(
            logger,
            "info",
            "audio.render.started",
            user_id=user_id,
            media_job_id=rendered_media_id,
            video_media_id=video_media_id,
            audio_media_id=audio_media_id,
            render_job_id=render_job_id,
            outcome="started",
        )

        video_suffix = pathlib.Path(video_asset.get("storage_key") or video_asset.get("media_url") or ".mp4").suffix or ".mp4"
        audio_suffix = pathlib.Path(audio_asset.get("storage_key") or audio_asset.get("media_url") or ".m4a").suffix or ".m4a"
        fd, video_path = tempfile.mkstemp(prefix=f"audio-render-video-{render_job_id}-", suffix=video_suffix)
        os.close(fd)
        fd, audio_path = tempfile.mkstemp(prefix=f"audio-render-audio-{render_job_id}-", suffix=audio_suffix)
        os.close(fd)
        output_path = os.path.join(tempfile.gettempdir(), f"audio-render-{rendered_media_id}.mp4")

        await download_file_to_path_async(_storage_ref(video_asset), video_path)
        await download_file_to_path_async(_storage_ref(audio_asset), audio_path)

        video_metadata = await validate_media(video_path, video_asset.get("mime_type") or "video/mp4")
        audio_metadata = await validate_media(audio_path, audio_asset.get("mime_type") or "audio/mp4")
        if not video_metadata.get("is_video"):
            raise ValueError("Stored source media is not a valid video")
        if not audio_metadata.get("is_audio") and not audio_metadata.get("has_audio"):
            raise ValueError("Stored selected media is not valid audio")

        await render_video_with_audio(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            video_metadata=video_metadata,
            mix=mix,
        )
        rendered_metadata = await validate_media(output_path, "video/mp4")

        media_folder = f"media/{user_id}"
        media_filename = f"{rendered_media_id}.mp4"
        media_storage_key = f"{media_folder}/{media_filename}"
        media_url = await upload_file_from_path_async(
            output_path,
            media_filename,
            "video/mp4",
            folder=media_folder,
        )

        now = datetime.now(timezone.utc)
        await db.media_assets.update_one(
            {"media_id": rendered_media_id, "user_id": user_id},
            {
                "$set": {
                    "status": "ready",
                    "media_url": media_url,
                    "storage_key": media_storage_key,
                    "mime_type": "video/mp4",
                    "asset_kind": "video",
                    "file_size_bytes": pathlib.Path(output_path).stat().st_size,
                    "duration_seconds": rendered_metadata.get("duration") or video_metadata.get("duration"),
                    "width": rendered_metadata.get("width") or video_metadata.get("width"),
                    "height": rendered_metadata.get("height") or video_metadata.get("height"),
                    "has_audio": True,
                    "processed_at": now,
                    "error_message": None,
                }
            },
        )
        event_log(
            logger,
            "info",
            "audio.render.succeeded",
            user_id=user_id,
            media_job_id=rendered_media_id,
            video_media_id=video_media_id,
            audio_media_id=audio_media_id,
            render_job_id=render_job_id,
            file_size_bytes=pathlib.Path(output_path).stat().st_size,
            outcome="ready",
        )
        return {"status": "ready", "media_job_id": rendered_media_id, "media_url": media_url}
    except Exception as exc:
        logger.error("Audio render failed for %s: %s", rendered_media_id, exc)
        current_retries = getattr(task.request, "retries", 0)
        max_retries = getattr(task, "max_retries", 0)
        if current_retries >= max_retries:
            await _mark_render_failed(rendered_media_id, str(exc))
            try:
                from utils.observability import event_log, shorten_provider_error
                event_log(
                    logger,
                    "error",
                    "audio.render.failed",
                    exc_info=exc,
                    user_id=user_id,
                    media_job_id=rendered_media_id,
                    video_media_id=video_media_id,
                    audio_media_id=audio_media_id,
                    render_job_id=render_job_id,
                    failure_type="ffmpeg_render_failed",
                    provider_error=shorten_provider_error(exc),
                    outcome="failed",
                )
            except Exception:
                logger.exception("Could not emit audio render failure event")
            raise
        raise task.retry(countdown=30, exc=exc)
    finally:
        for path in {video_path, audio_path, output_path}:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError as cleanup_exc:
                    logger.warning("Could not delete audio render temp file %s: %s", path, cleanup_exc)


async def _async_process_media(task, media_job_id: str, user_id: str) -> dict:
    quarantine_path: str | None = None
    source_storage_key: str | None = None
    source_local_path: str | None = None
    processed_path: str | None = None
    completed_successfully = False
    try:
        from media_pipeline.validation import validate_media
        from media_pipeline.ffmpeg_worker import extract_audio_waveform_peaks, process_video
        from media_pipeline.thumbnail import generate_thumbnail
        from utils.storage import (
            copy_storage_object_async,
            delete_file_async,
            download_file_to_path_async,
            upload_file_async,
            upload_file_from_path_async,
        )

        _client, db = await _get_db()
        asset = await db.media_assets.find_one({"media_id": media_job_id}, {"_id": 0})
        if not asset:
            return {"status": "not_found"}

        quarantine_path = asset.get("quarantine_path")
        source_storage_key = asset.get("source_storage_key")
        mime_type = asset.get("mime_type", "application/octet-stream")

        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "processing"}},
        )

        if source_storage_key:
            suffix = pathlib.Path(
                asset.get("original_filename")
                or source_storage_key
                or media_job_id
            ).suffix or pathlib.Path(source_storage_key).suffix or ".bin"
            fd, source_local_path = tempfile.mkstemp(
                prefix=f"media-src-{media_job_id}-",
                suffix=suffix,
            )
            os.close(fd)
            await download_file_to_path_async(source_storage_key, source_local_path)
            input_path = source_local_path
        else:
            input_path = quarantine_path

        if not input_path:
            raise ValueError("No media source path available for processing")

        # Step 1: Validate
        validation_result = await validate_media(input_path, mime_type)

        asset_kind = "video" if mime_type and mime_type.startswith("video/") else (
            "audio" if mime_type and mime_type.startswith("audio/") else "image"
        )

        # Step 2: Transcode if video
        if asset_kind == "video":
            processed_path = await process_video(input_path, validation_result)
        else:
            processed_path = input_path

        used_passthrough = processed_path == input_path
        if used_passthrough:
            logger.info(
                "Media %s passed validation without transcode (mime_type=%s, source_storage_key=%s)",
                media_job_id,
                mime_type,
                bool(source_storage_key),
            )
        else:
            logger.info(
                "Media %s required transcode before publish (mime_type=%s)",
                media_job_id,
                mime_type,
            )

        # Step 3: Thumbnail. Audio assets are library inputs for later video
        # rendering, so they intentionally do not get image thumbnails.
        thumbnail_path = None
        if asset_kind != "audio":
            thumbnail_path = await generate_thumbnail(processed_path, mime_type, media_job_id, user_id)
        waveform_peaks = None
        if asset_kind == "audio":
            try:
                waveform_peaks = await extract_audio_waveform_peaks(processed_path)
            except Exception as waveform_exc:
                logger.warning(
                    "Could not extract audio waveform peaks: media_id=%s error=%s",
                    media_job_id,
                    waveform_exc,
                )

        # Step 4: Upload media to permanent storage (R2 or Firebase)
        ext = pathlib.Path(processed_path).suffix or ""
        media_filename = f"{media_job_id}{ext}"
        media_folder = f"media/{user_id}"
        media_storage_key = f"{media_folder}/{media_filename}"
        can_promote_source_object = bool(
            source_storage_key
            and source_storage_key != media_storage_key
            and processed_path == source_local_path
        )
        if can_promote_source_object:
            media_url = await copy_storage_object_async(
                source_storage_key,
                media_storage_key,
                content_type=mime_type,
            )
            logger.info(
                "Media promoted via storage-side copy: media_id=%s source_key=%s dest_key=%s",
                media_job_id,
                source_storage_key,
                media_storage_key,
            )
        else:
            media_url = await upload_file_from_path_async(
                processed_path,
                media_filename,
                mime_type,
                folder=media_folder,
            )
        logger.info("Media uploaded: media_id=%s url=%s", media_job_id, media_url)

        # Step 5: Upload thumbnail
        thumbnail_url = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            loop = asyncio.get_running_loop()
            thumb_bytes = await loop.run_in_executor(
                None, lambda: open(thumbnail_path, "rb").read()
            )
            thumbnail_url = await upload_file_async(
                thumb_bytes,
                f"{media_job_id}.webp",
                "image/webp",
                folder=f"thumbnails/{user_id}",
            )
            logger.info("Thumbnail uploaded: media_id=%s url=%s", media_job_id, thumbnail_url)

        source_storage_deleted_at = None
        source_storage_deleted = False
        if source_storage_key and source_storage_key != media_storage_key:
            try:
                await delete_file_async(source_storage_key)
                source_storage_deleted_at = datetime.now(timezone.utc).isoformat()
                source_storage_deleted = True
                logger.info(
                    "Raw upload source deleted after processing: media_id=%s key=%s",
                    media_job_id,
                    source_storage_key,
                )
            except Exception as raw_delete_exc:
                logger.warning(
                    "Could not delete raw upload source for media_id=%s key=%s: %s",
                    media_job_id,
                    source_storage_key,
                    raw_delete_exc,
                )

        # Step 6: Persist real URLs + storage key to DB
        # storage_key is stored separately so cleanup can call delete_file(key)
        # without having to parse the public URL (which may change format)
        media_update = {
            "$set": {
                "status": "ready",
                "media_url": media_url,
                "storage_key": media_storage_key,
                "thumbnail_url": thumbnail_url,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": validation_result.get("duration"),
                "width": validation_result.get("width"),
                "height": validation_result.get("height"),
                "has_audio": validation_result.get("has_audio"),
                "asset_kind": asset_kind,
                "source_stage": "ready",
            },
        }
        if waveform_peaks:
            media_update["$set"]["waveform_peaks"] = waveform_peaks
        if source_storage_deleted:
            media_update["$set"]["source_storage_deleted_at"] = source_storage_deleted_at
            media_update["$unset"] = {"source_storage_key": ""}

        await db.media_assets.update_one(
            {"media_id": media_job_id},
            media_update,
        )

        logger.info("Media %s processed and uploaded successfully", media_job_id)
        completed_successfully = True
        return {"status": "ready", "media_url": media_url, "thumbnail_url": thumbnail_url}

    except Exception as exc:
        logger.error("Media processing failed for %s: %s", media_job_id, exc)
        current_retries = getattr(task.request, "retries", 0)
        max_retries = getattr(task, "max_retries", 0)
        if current_retries >= max_retries:
            await _mark_media_failed(media_job_id, str(exc))
            raise
        raise task.retry(countdown=30, exc=exc)

    finally:
        transient_paths = {source_local_path}
        if processed_path and processed_path not in {quarantine_path, source_local_path}:
            transient_paths.add(processed_path)
        for path in transient_paths:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError as _e:
                    logger.warning("Could not delete temp file %s: %s", path, _e)
        if completed_successfully:
            # EC-14: Remove local quarantine/temp files only after successful processing.
            # Retried jobs still need the original quarantine file.
            for path in {quarantine_path, processed_path}:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError as _e:
                        logger.warning("Could not delete temp file %s: %s", path, _e)


# ── Section 18.8 — Per-platform Publish Notifications ────────────────────────

@celery_app.task(
    name="celery_workers.tasks.media.send_notification",
    acks_late=True,
    queue="default",
    max_retries=3,
)
def send_notification(
    post_id: str,
    type: str,
    platform: str | None = None,
    error: str | None = None,
    post_url: str | None = None,
) -> None:
    """
    18.8: Store in-app and email notification records for publish events.

    Notification types:
      publish_success            — platform posted successfully
      publish_failed             — platform failed (retrying)
      publish_permanently_failed — all retries exhausted, moved to DLQ
      publish_partial_recovery   — last previously-failed platform now succeeded
    """
    run_async(_async_send_notification(
        post_id=post_id,
        notification_type=type,
        platform=platform,
        error=error,
        post_url=post_url,
    ))


async def _async_send_notification(
    post_id: str,
    notification_type: str,
    platform: str | None,
    error: str | None,
    post_url: str | None,
) -> None:
    from db.mongo import get_client
    from utils.notifications import emit_notification

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    # Resolve user_id from post
    post_doc = await db.posts.find_one({"id": post_id}, {"user_id": 1})
    user_id = (post_doc or {}).get("user_id", "")

    if not user_id:
        logger.warning("send_notification: cannot resolve user_id for post=%s type=%s", post_id, notification_type)
        return

    event_key = _EVENT_MAP.get(notification_type, "post.failed")
    platform_label = platform.capitalize() if platform else "platform"
    message = _build_message(notification_type, platform_label, error, post_url)
    title = _TITLES.get(notification_type, "Notification")
    severity = "low" if event_key == "post.published" else "high"
    await emit_notification(
        db,
        user_id=user_id,
        event=event_key,
        notification_type=notification_type,
        title=title.replace(" ✓", ""),
        message=message,
        severity=severity,
        metadata={
            "post_id": post_id,
            "platform": platform,
            "post_url": post_url,
            "legacy_publish_notification": True,
        },
        target_path="/content-library?status=published" if event_key == "post.published" else "/content-library?status=failed",
        dedup_key=f"post:{post_id}:legacy:{event_key}:{platform or 'all'}",
        created_at=datetime.now(timezone.utc),
    )


def _build_message(notification_type: str, platform: str, error: str | None, post_url: str | None) -> str:
    if notification_type == "publish_success":
        url_part = f" — {post_url}" if post_url else ""
        return f"Your post was successfully published on {platform}{url_part}."
    if notification_type == "publish_failed":
        reason = f": {error}" if error else ""
        return f"Publishing to {platform} failed{reason}. We'll retry automatically."
    if notification_type == "publish_permanently_failed":
        reason = f": {error}" if error else ""
        return (
            f"Your post permanently failed on {platform}{reason} after all retries "
            f"were exhausted. Please check your connected account and reschedule."
        )
    if notification_type == "publish_partial_recovery":
        return f"Your post has now been published on {platform} after a previous failure."
    return f"An event ({notification_type}) occurred for your post on {platform}."


def _build_email_html(name: str, title: str, message: str, post_url: str | None) -> str:
    url_block = ""
    if post_url:
        url_block = f'<p><a href="{post_url}" style="color:#6366f1">View post →</a></p>'
    return f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
      <h2 style="color:#1e293b">{title}</h2>
      <p style="color:#475569">Hi {name},</p>
      <p style="color:#475569">{message}</p>
      {url_block}
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0"/>
      <p style="font-size:12px;color:#94a3b8">
        You can manage your email preferences in
        <a href="https://app.unravler.com/settings">Settings → Notifications</a>.
      </p>
    </div>
    """
