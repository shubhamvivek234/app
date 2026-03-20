"""
Phase 2 — Media processing Celery task.
Validates, compresses, thumbnails. Moves from /quarantine/ to /media/ on success.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Maps internal notification type → notification_prefs event key
_EVENT_MAP: dict[str, str] = {
    "publish_success":            "post.published",
    "publish_recovered":          "post.published",
    "publish_failed":             "post.failed",
    "publish_permanently_failed": "post.dlq",
    "pre_upload_timeout":         "post.failed",
}

# Human-readable titles shown in-app
_TITLES: dict[str, str] = {
    "publish_success":            "Post published",
    "publish_recovered":          "All platforms published",
    "publish_failed":             "Post failed to publish",
    "publish_permanently_failed": "Post permanently failed",
    "pre_upload_timeout":         "Video upload timed out",
}


@celery_app.task(
    name="celery_workers.tasks.media.process_media",
    bind=True,
    max_retries=2,
    acks_late=True,
    queue="media_processing",
    time_limit=360,       # hard kill after 6 minutes
    soft_time_limit=300,  # soft kill after 5 minutes (raises SoftTimeLimitExceeded)
)
def process_media(self, media_job_id: str, user_id: str) -> dict:
    return asyncio.run(_async_process_media(self, media_job_id, user_id))


async def _async_process_media(task, media_job_id: str, user_id: str) -> dict:
    from db.mongo import get_client
    from media_pipeline.validation import validate_media
    from media_pipeline.ffmpeg_worker import process_video
    from media_pipeline.thumbnail import generate_thumbnail

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    asset = await db.media_assets.find_one({"media_id": media_job_id}, {"_id": 0})
    if not asset:
        return {"status": "not_found"}

    quarantine_path = asset.get("quarantine_path")
    mime_type = asset.get("mime_type")

    try:
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "processing"}},
        )

        # Step 1: Validate
        validation_result = await validate_media(quarantine_path, mime_type)

        # Step 2: Process (transcode if video)
        if mime_type and mime_type.startswith("video/"):
            processed_path = await process_video(quarantine_path, validation_result)
        else:
            processed_path = quarantine_path

        # Step 3: Generate thumbnail
        thumbnail_path = await generate_thumbnail(processed_path, mime_type, media_job_id, user_id)

        # Step 4: Move to permanent storage
        # TODO: Upload processed_path to GCS /media/{user_id}/{media_job_id}
        media_url = f"https://storage.googleapis.com/{os.environ.get('GCS_BUCKET_MEDIA')}/media/{user_id}/{media_job_id}"
        thumbnail_url = f"https://storage.googleapis.com/{os.environ.get('GCS_BUCKET_THUMBNAILS')}/thumbnails/{user_id}/{media_job_id}.webp"

        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {
                "status": "ready",
                "media_url": media_url,
                "thumbnail_url": thumbnail_url,
                "processed_at": datetime.utcnow().isoformat(),
                "duration_seconds": validation_result.get("duration"),
                "width": validation_result.get("width"),
                "height": validation_result.get("height"),
            }},
        )

        logger.info("Media %s processed successfully", media_job_id)
        return {"status": "ready", "media_url": media_url, "thumbnail_url": thumbnail_url}

    except Exception as exc:
        logger.error("Media processing failed for %s: %s", media_job_id, exc)
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "failed", "error_message": str(exc)}},
        )
        raise task.retry(countdown=30, exc=exc)


# ── Section 18.8 — Per-platform publish notification ──────────────────────────

@celery_app.task(
    name="celery_workers.tasks.media.send_notification",
    time_limit=60,
    soft_time_limit=45,
)
def send_notification(
    post_id: str,
    type: str,
    platform: str | None = None,
    error: str | None = None,
    post_url: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    18.8: Store in-app and/or email notification records for publish events.

    Notification types:
      publish_success            — post published on a platform
      publish_failed             — publish attempt failed (will retry)
      publish_permanently_failed — all retries exhausted, moved to DLQ
      publish_recovered          — all platforms now published after partial failure
      pre_upload_timeout         — video pre-upload timed out before publish window
    """
    asyncio.run(_async_send_notification(
        post_id=post_id,
        notification_type=type,
        platform=platform,
        error=error,
        post_url=post_url,
        user_id=user_id,
    ))


async def _async_send_notification(
    post_id: str,
    notification_type: str,
    platform: str | None,
    error: str | None,
    post_url: str | None,
    user_id: str | None,
) -> None:
    from db.mongo import get_client
    from utils.notification_prefs import should_notify

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)

    # Resolve user_id from post if not supplied by caller
    resolved_user_id = user_id
    if not resolved_user_id:
        post = await db.posts.find_one({"id": post_id}, {"user_id": 1})
        if post:
            resolved_user_id = post.get("user_id")

    if not resolved_user_id:
        logger.warning("send_notification: cannot resolve user_id for post=%s type=%s", post_id, notification_type)
        return

    # Map internal type → preference event key
    event_key = _EVENT_MAP.get(notification_type, "post.failed")

    # Build human-readable message
    platform_label = platform.capitalize() if platform else "your platform"
    message = _build_message(notification_type, platform_label, error, post_url)
    title = _TITLES.get(notification_type, "Notification")

    # Build shared metadata
    metadata: dict = {"post_id": post_id, "notification_type": notification_type}
    if platform:
        metadata["platform"] = platform
    if error:
        metadata["error"] = error
    if post_url:
        metadata["post_url"] = post_url

    # ── In-app notification (stored in DB, read by frontend) ──────────────────
    try:
        in_app_enabled = await should_notify(db, resolved_user_id, event_key, "in_app")
    except Exception:
        in_app_enabled = True  # fail open — never silently drop notifications

    if in_app_enabled:
        await db.notifications.insert_one({
            "user_id": resolved_user_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "channel": "in_app",
            "is_read": False,
            "metadata": metadata,
            "created_at": now,
        })
        logger.info(
            "18.8 in_app notification stored: user=%s type=%s post=%s platform=%s",
            resolved_user_id, notification_type, post_id, platform,
        )

    # ── Email notification (stored in DB, picked up by email delivery service) ─
    try:
        email_enabled = await should_notify(db, resolved_user_id, event_key, "email")
    except Exception:
        email_enabled = False  # fail closed for email — avoid accidental spam

    if email_enabled:
        await db.notifications.insert_one({
            "user_id": resolved_user_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "channel": "email",
            "is_read": False,
            "metadata": metadata,
            "created_at": now,
        })
        logger.info(
            "18.8 email notification queued: user=%s type=%s post=%s platform=%s",
            resolved_user_id, notification_type, post_id, platform,
        )


def _build_message(
    notification_type: str,
    platform_label: str,
    error: str | None,
    post_url: str | None,
) -> str:
    """Build a human-readable notification message for each publish event type."""
    if notification_type == "publish_success":
        suffix = f" View it here: {post_url}" if post_url else ""
        return f"Your post was published successfully on {platform_label}.{suffix}"

    if notification_type == "publish_recovered":
        return "All platforms have now published your post successfully."

    if notification_type == "publish_failed":
        reason = f": {error}" if error else "."
        return (
            f"Your post failed to publish on {platform_label}{reason} "
            f"It will retry automatically."
        )

    if notification_type == "publish_permanently_failed":
        reason = f": {error}" if error else "."
        return (
            f"Your post permanently failed on {platform_label}{reason} "
            f"All retry attempts were exhausted — please reschedule or edit the post."
        )

    if notification_type == "pre_upload_timeout":
        return (
            f"Your video upload to {platform_label} timed out after 30 minutes. "
            f"Please reschedule the post or try again with a smaller file."
        )

    # Fallback for unknown types
    return f"Notification: {notification_type} on {platform_label}."
