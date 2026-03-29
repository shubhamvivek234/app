"""
Phase 1.3 — Celery Beat scheduler task.
Runs every 30 seconds. Uses atomic findOneAndUpdate to prevent double-enqueue (EC2).
Phase 2.4.4 — NTP skew check on startup.
"""
import logging
import ntplib
import os
from datetime import datetime, timedelta, timezone

from celery import shared_task
from celery.signals import beat_init
from motor.motor_asyncio import AsyncIOMotorClient

from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

# ── Beat schedule registration ───────────────────────────────────────────────
celery_app.conf.beat_schedule.update({
    "scan-scheduled-posts": {
        "task": "celery_workers.tasks.scheduler.scan_and_enqueue",
        "schedule": 30.0,  # every 30 seconds
        "options": {"queue": "default"},
    },
    "token-refresh": {
        "task": "celery_workers.tasks.tokens.refresh_expiring_tokens",
        "schedule": 6 * 3600,  # every 6 hours
        "options": {"queue": "default"},
    },
    "reconcile-redis-mongo": {
        "task": "celery_workers.tasks.reconcile.reconcile_confirmations",
        "schedule": 300,  # every 5 minutes
        "options": {"queue": "default"},
    },
    "orphan-file-scan": {
        "task": "celery_workers.tasks.cleanup.scan_orphaned_files",
        "schedule": 7 * 24 * 3600,  # weekly
        "options": {"queue": "default"},
    },
    "check-subscription-expiry": {
        "task": "celery_workers.tasks.subscription_check.check_expiring_subscriptions",
        "schedule": 86400,  # daily
        "options": {"queue": "default"},
    },
    "send-grace-period-reminders": {
        "task": "celery_workers.tasks.grace_period_reminders.send_grace_period_reminders",
        "schedule": 172800,  # every 2 days
        "options": {"queue": "default"},
    },
    "api-version-monitor": {
        "task": "celery_workers.tasks.api_version_monitor.check_platform_api_versions",
        "schedule": 86400,  # daily
        "options": {"queue": "default"},
    },
    # 22: Re-apply GCS lifecycle rules weekly — ensures rules survive bucket ops
    # and are applied to any new buckets created during deployment.
    "apply-gcs-lifecycle-rules": {
        "task": "celery_workers.tasks.cleanup.apply_gcs_lifecycle_rules",
        "schedule": 7 * 24 * 3600,  # weekly
        "options": {"queue": "default"},
    },
    # 17.4D: Detect pre_upload tasks stuck > 30 min → DLQ + notify user
    "pre-upload-timeout-scan": {
        "task": "celery_workers.tasks.scheduler.scan_pre_upload_timeouts",
        "schedule": 60.0,  # every minute
        "options": {"queue": "default"},
    },
})


@beat_init.connect
def check_ntp_on_startup(sender=None, **kwargs):
    """Phase 2.4.4 — Refuse to start Beat if clock skew > 30 seconds."""
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request("pool.ntp.org", version=3)
        skew = abs(response.offset)
        if skew > 30:
            raise RuntimeError(
                f"NTP clock skew {skew:.1f}s exceeds 30s limit. "
                "Fix system clock before running Celery Beat."
            )
        if skew > 5:
            logger.warning("NTP clock skew %.1fs > 5s threshold", skew)
        else:
            logger.info("NTP clock skew %.3fs — OK", skew)
    except ntplib.NTPException as exc:
        logger.warning("NTP check failed (non-fatal): %s", exc)


@celery_app.task(name="celery_workers.tasks.scheduler.scan_and_enqueue")
def scan_and_enqueue() -> dict:
    """
    Runs every 30 seconds. Atomically claims posts that are due to be published.
    Passes only post_id in Celery payload — never the full document.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_scan_and_enqueue())


async def _async_scan_and_enqueue() -> dict:
    from celery_workers.tasks.publish import publish_post

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    # 10-second buffer compensates for minor clock drift (Phase 2.4.4)
    window_end = now + timedelta(seconds=10)
    # 35-second look-ahead for 30s beat interval with buffer
    enqueue_horizon = now + timedelta(seconds=35)

    enqueued = 0
    high_priority_threshold = now + timedelta(minutes=5)

    # Cursor over posts due in window — each iteration atomically claims one.
    # Capped at 500 per scan: prevents Beat task from running past its 30s window
    # on popular time slots (e.g. 9AM Monday with thousands of posts due).
    # Unclaimed posts are picked up by the next scan cycle 30s later.
    cursor = db.posts.find(
        {"status": "scheduled", "scheduled_time": {"$lte": enqueue_horizon}},
        {"_id": 0, "id": 1, "scheduled_time": 1, "platforms": 1, "version": 1},
        limit=500,
    )

    async for post in cursor:
        post_id = post["id"]

        # Atomic claim — prevents double-enqueue from concurrent Beat instances (EC2)
        result = await db.posts.find_one_and_update(
            {"id": post_id, "status": "scheduled"},
            {
                "$set": {"status": "queued"},
                "$push": {"status_history": {
                    "status": "queued",
                    "timestamp": now.isoformat(),
                    "actor": "beat_scheduler",
                }},
            },
            return_document=True,
        )

        if result is None:
            # Another Beat instance (or concurrent request) already claimed this post
            logger.debug("Post %s already claimed — skipping", post_id)
            continue

        # Determine queue priority
        scheduled = post.get("scheduled_time", now)
        queue = "high_priority" if scheduled <= high_priority_threshold else "default"

        # Enqueue with post_id + version only (EC3: version for edit-conflict detection)
        publish_post.apply_async(
            kwargs={
                "post_id": post_id,
                "version": post.get("version", 1),
            },
            queue=queue,
        )
        enqueued += 1
        logger.info("Enqueued post %s to %s queue", post_id, queue)

    # 17.3 + Phase 1.5.3: Trigger pre-upload for video posts whose dynamic window has opened.
    # Use a wide scan horizon (60 min) and filter per-post using calculate_pre_upload_start.
    pre_upload_scan_horizon = now + timedelta(minutes=60)
    pre_upload_cursor = db.posts.find(
        {
            "status": "scheduled",
            "scheduled_time": {"$lte": pre_upload_scan_horizon, "$gt": enqueue_horizon},
            "post_type": {"$in": ["video", "reel", "story"]},
            "pre_upload_status": {"$in": [None, "pending", "failed"]},  # retry failed pre-uploads
        },
        {"_id": 0, "id": 1, "platforms": 1, "scheduled_time": 1, "video_size_mb": 1},
        limit=200,  # raised from 50 — handles burst of video posts at popular time slots
    )
    pre_uploads_triggered = 0
    async for post in pre_upload_cursor:
        # 17.3: Only trigger if we've reached the calculated pre_upload start time
        pre_upload_start = _get_pre_upload_start(post, now)
        if now < pre_upload_start:
            continue  # Not yet time to start pre-upload for this post

        from celery_workers.tasks.publish import pre_upload_task, calculate_pre_upload_start
        platforms = post.get("platforms", [])

        # 17.5: Record pre_upload_start_time + estimated_upload_duration on the post
        file_size_mb = post.get("video_size_mb", 0) or 0
        if file_size_mb > 0 and post.get("scheduled_time"):
            _, estimated_secs = calculate_pre_upload_start(
                post["scheduled_time"], file_size_mb, platforms
            )
            await db.posts.update_one(
                {"id": post["id"], "pre_upload_status": {"$in": [None, "pending"]}},
                {"$set": {
                    "pre_upload_start_time": now,
                    "estimated_upload_duration": estimated_secs,
                }},
            )

        for p in platforms:
            if p in ("instagram", "youtube"):
                pre_upload_task.apply_async(
                    kwargs={"post_id": post["id"], "platform": p},
                    queue="media_processing",
                )
                pre_uploads_triggered += 1

    return {"enqueued": enqueued, "pre_uploads": pre_uploads_triggered, "scan_time": now.isoformat()}


# ── 17.4D: Dynamic pre_upload window using timing formula ─────────────────────
def _get_pre_upload_start(post: dict, now: datetime) -> datetime:
    """
    Use calculate_pre_upload_start() if video_size_mb is known,
    otherwise fall back to 20-minute fixed window.
    """
    from celery_workers.tasks.publish import calculate_pre_upload_start
    scheduled_time = post.get("scheduled_time")
    file_size_mb = post.get("video_size_mb", 0) or 0
    platforms = post.get("platforms", [])
    if file_size_mb > 0 and scheduled_time:
        start_time, _ = calculate_pre_upload_start(scheduled_time, file_size_mb, platforms)
        return start_time
    # Fallback: 20-minute window
    return (scheduled_time or now) - timedelta(minutes=20)


# ── 17.4D: Timeout scanner — runs every minute via Beat ───────────────────────
@celery_app.task(name="celery_workers.tasks.scheduler.scan_pre_upload_timeouts")
def scan_pre_upload_timeouts() -> dict:
    """
    17.4 Scenario D — Detect pre_upload tasks stuck > 30 min.
    Moves timed-out posts to DLQ and notifies the user with a reschedule option.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_scan_pre_upload_timeouts())


async def _async_scan_pre_upload_timeouts() -> dict:
    from celery_workers.tasks.publish import _move_to_dlq

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.utcnow()
    timeout_threshold = now - timedelta(minutes=120)  # 2h — 10GB files need longer upload windows

    # Find posts stuck in "uploading" for more than 30 minutes
    cursor = db.posts.find(
        {
            "pre_upload_status": "uploading",
            "pre_upload_started_at": {"$lte": timeout_threshold},
        },
        {"_id": 0, "id": 1, "user_id": 1, "platforms": 1, "scheduled_time": 1},
        limit=50,
    )

    timed_out = 0
    async for post in cursor:
        post_id = post["id"]
        # Atomically claim — prevent concurrent scanners processing same post
        result = await db.posts.find_one_and_update(
            {"id": post_id, "pre_upload_status": "uploading"},
            {"$set": {
                "pre_upload_status": "timeout",
                "pre_upload_error": "Pre-upload timed out after 2 hours — moved to DLQ",
                "pre_upload_timed_out_at": now,
            }},
        )
        if result is None:
            continue  # Already claimed by another scanner instance

        logger.error(
            "17.4D: pre_upload timeout for post %s (started_at=%s) — moving to DLQ",
            post_id, result.get("pre_upload_started_at"),
        )

        # Move to DLQ
        try:
            await _move_to_dlq(post_id, "pre_upload_timeout")
        except Exception as dlq_exc:
            logger.error("17.4D: Failed to move %s to DLQ: %s", post_id, dlq_exc)

        # Notify user with reschedule option
        try:
            from celery_workers.tasks.media import send_notification
            send_notification.apply_async(
                kwargs={
                    "post_id": post_id,
                    "type": "pre_upload_timeout",
                    "platform": ",".join(post.get("platforms", [])),
                    "error": (
                        "Your video upload timed out after 2 hours. "
                        "Please reschedule the post or try again with a smaller file."
                    ),
                },
                queue="default",
            )
        except Exception as notify_exc:
            logger.warning("17.4D: Failed to notify user for post %s: %s", post_id, notify_exc)

        timed_out += 1

    if timed_out:
        logger.warning("17.4D: Timed out %d stuck pre_upload tasks", timed_out)

    return {"status": "complete", "timed_out": timed_out, "scan_time": now.isoformat()}
