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
    "api-version-monitor": {
        "task": "celery_workers.tasks.api_version_monitor.check_platform_api_versions",
        "schedule": 86400,  # daily
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

    # Cursor over posts due in window — each iteration atomically claims one
    cursor = db.posts.find(
        {"status": "scheduled", "scheduled_time": {"$lte": enqueue_horizon}},
        {"_id": 0, "id": 1, "scheduled_time": 1, "platforms": 1, "version": 1},
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

    # Phase 1.5.3: Trigger pre-upload for posts with video that are due within 20 minutes
    pre_upload_horizon = now + timedelta(minutes=20)
    pre_upload_cursor = db.posts.find(
        {
            "status": "scheduled",
            "scheduled_time": {"$lte": pre_upload_horizon, "$gt": enqueue_horizon},
            "post_type": {"$in": ["video", "reel", "story"]},
            "pre_upload_status": {"$in": [None, "pending"]},
        },
        {"_id": 0, "id": 1, "platforms": 1},
        limit=50,
    )
    pre_uploads_triggered = 0
    async for post in pre_upload_cursor:
        from celery_workers.tasks.publish import pre_upload_task
        platforms = post.get("platforms", [])
        for p in platforms:
            if p in ("instagram", "youtube"):
                pre_upload_task.apply_async(
                    kwargs={"post_id": post["id"], "platform": p},
                    queue="media_processing",
                )
                pre_uploads_triggered += 1

    return {"enqueued": enqueued, "pre_uploads": pre_uploads_triggered, "scan_time": now.isoformat()}
