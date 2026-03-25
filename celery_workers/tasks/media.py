"""
Phase 2 — Media processing Celery task.
Validates, compresses, thumbnails. Moves from /quarantine/ to permanent storage on success.

Section 18.8 — per-platform publish notifications (success, failure, DLQ, recovery).
"""
import asyncio
import logging
import os
import pathlib
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── Notification type → notification_prefs event key ─────────────────────────
_EVENT_MAP: dict[str, str] = {
    "publish_success":            "post.published",
    "publish_failed":             "post.failed",
    "publish_permanently_failed": "post.dlq",
    "publish_partial_recovery":   "post.published",
}

_TITLES: dict[str, str] = {
    "publish_success":            "Post Published ✓",
    "publish_failed":             "Post Failed",
    "publish_permanently_failed": "Post Permanently Failed",
    "publish_partial_recovery":   "Post Recovered ✓",
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
    time_limit=360,
    soft_time_limit=300,
)
def process_media(self, media_job_id: str, user_id: str) -> dict:
    return asyncio.run(_async_process_media(self, media_job_id, user_id))


async def _async_process_media(task, media_job_id: str, user_id: str) -> dict:
    from db.mongo import get_client
    from media_pipeline.validation import validate_media
    from media_pipeline.ffmpeg_worker import process_video
    from media_pipeline.thumbnail import generate_thumbnail
    from utils.storage import upload_file_async

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    asset = await db.media_assets.find_one({"media_id": media_job_id}, {"_id": 0})
    if not asset:
        return {"status": "not_found"}

    quarantine_path = asset.get("quarantine_path")
    mime_type = asset.get("mime_type", "application/octet-stream")

    try:
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "processing"}},
        )

        # Step 1: Validate
        validation_result = await validate_media(quarantine_path, mime_type)

        # Step 2: Transcode if video
        if mime_type and mime_type.startswith("video/"):
            processed_path = await process_video(quarantine_path, validation_result)
        else:
            processed_path = quarantine_path

        # Step 3: Thumbnail
        thumbnail_path = await generate_thumbnail(processed_path, mime_type, media_job_id, user_id)

        # Step 4: Upload media to permanent storage (R2 or Firebase)
        ext = pathlib.Path(processed_path).suffix or ""
        loop = asyncio.get_event_loop()
        def _read_file(path: str) -> bytes:
            with open(path, "rb") as f:
                return f.read()
        media_bytes = await loop.run_in_executor(None, _read_file, processed_path)
        media_url = await upload_file_async(
            media_bytes,
            f"{media_job_id}{ext}",
            mime_type,
            folder=f"media/{user_id}",
        )
        logger.info("Media uploaded: media_id=%s url=%s", media_job_id, media_url)

        # Step 5: Upload thumbnail
        thumbnail_url = None
        if thumbnail_path and os.path.exists(thumbnail_path):
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

        # Step 6: Persist real URLs to DB
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {
                "status": "ready",
                "media_url": media_url,
                "thumbnail_url": thumbnail_url,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": validation_result.get("duration"),
                "width": validation_result.get("width"),
                "height": validation_result.get("height"),
            }},
        )

        logger.info("Media %s processed and uploaded successfully", media_job_id)
        return {"status": "ready", "media_url": media_url, "thumbnail_url": thumbnail_url}

    except Exception as exc:
        logger.error("Media processing failed for %s: %s", media_job_id, exc)
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "failed", "error_message": str(exc)}},
        )
        raise task.retry(countdown=30, exc=exc)


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
    asyncio.run(_async_send_notification(
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
    from utils.notification_prefs import should_notify

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

    now = datetime.now(timezone.utc).isoformat()
    notification_doc = {
        "user_id": user_id,
        "type": notification_type,
        "post_id": post_id,
        "platform": platform,
        "title": title,
        "message": message,
        "read": False,
        "created_at": now,
    }

    # ── In-app (stored in DB, read by frontend /api/inbox) ────────────────────
    try:
        in_app_ok = await should_notify(db, user_id, event_key, "in_app")
    except Exception:
        in_app_ok = True  # fail-open — never silently drop in-app

    if in_app_ok:
        await db.notifications.insert_one({**notification_doc, "channel": "in_app"})
        logger.info(
            "18.8 in_app stored: user=%s type=%s post=%s platform=%s",
            user_id, notification_type, post_id, platform,
        )

    # ── Email (Resend API) ────────────────────────────────────────────────────
    try:
        email_ok = await should_notify(db, user_id, event_key, "email")
    except Exception:
        email_ok = False  # fail-closed for email — avoid spam on pref lookup error

    if email_ok and RESEND_API_KEY:
        user_doc = await db.users.find_one({"user_id": user_id}, {"email": 1, "name": 1})
        recipient_email = (user_doc or {}).get("email")
        recipient_name = (user_doc or {}).get("name", "there")

        if recipient_email:
            import resend  # noqa: PLC0415 — lazy import
            resend.api_key = RESEND_API_KEY
            try:
                resend.Emails.send({
                    "from": SENDER_EMAIL,
                    "to": recipient_email,
                    "subject": f"SocialEntangler — {title}",
                    "html": _build_email_html(recipient_name, title, message, post_url),
                })
                logger.info(
                    "18.8 email sent: user=%s type=%s post=%s platform=%s",
                    user_id, notification_type, post_id, platform,
                )
            except Exception as email_exc:
                logger.warning("18.8 email send failed (non-fatal): %s", email_exc)

        # Always record email attempt in DB for audit
        await db.notifications.insert_one({**notification_doc, "channel": "email"})


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
        <a href="https://app.socialentangler.com/settings">Settings → Notifications</a>.
      </p>
    </div>
    """
