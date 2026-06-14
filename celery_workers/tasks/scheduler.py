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

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)


def _coerce_utc_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return value


def _schedule_scan_interval_secs() -> float:
    return float(os.environ.get("SCHEDULE_SCAN_INTERVAL_SECS", "15"))


def _schedule_lookahead_secs() -> int:
    return int(os.environ.get("SCHEDULE_LOOKAHEAD_SECS", "45"))


def _schedule_scan_batch_size() -> int:
    return max(1, int(os.environ.get("SCHEDULE_SCAN_BATCH_SIZE", "500")))


def _schedule_scan_max_batches() -> int:
    return max(1, int(os.environ.get("SCHEDULE_SCAN_MAX_BATCHES", "5")))


def _scheduler_claim_recovery_secs() -> int:
    return max(30, int(os.environ.get("SCHEDULER_CLAIM_RECOVERY_SECS", "300")))


_SCHEDULE_SCAN_INTERVAL_SECS = _schedule_scan_interval_secs()

# ── Beat schedule registration ───────────────────────────────────────────────
celery_app.conf.beat_schedule.update({
    "scan-scheduled-posts": {
        "task": "celery_workers.tasks.scheduler.scan_and_enqueue",
        "schedule": _SCHEDULE_SCAN_INTERVAL_SECS,
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
    "stale-direct-upload-scan": {
        "task": "celery_workers.tasks.cleanup.scan_stale_direct_uploads",
        "schedule": 300,  # every 5 minutes
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
    "cleanup-expired-published-card-thumbnails": {
        "task": "celery_workers.tasks.cleanup.cleanup_expired_published_card_thumbnails",
        "schedule": 86400,  # daily
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
    return run_async(_async_scan_and_enqueue())


async def _async_scan_and_enqueue() -> dict:
    from celery_workers.tasks.publish import (
        _get_publish_targets,
        _get_platform_pre_upload_started_at,
        _get_platform_pre_upload_status,
        _pre_upload_result_path,
        _requires_pre_upload,
        _sync_pre_upload_aggregate,
        calculate_pre_upload_start,
        publish_post,
    )

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    lookahead_secs = _schedule_lookahead_secs()
    batch_size = _schedule_scan_batch_size()
    max_batches = _schedule_scan_max_batches()
    enqueue_horizon = now + timedelta(seconds=lookahead_secs)

    enqueued = 0
    batches_processed = 0
    recovered = 0
    high_priority_threshold = now + timedelta(minutes=5)
    claim_recovery_threshold = now - timedelta(seconds=_scheduler_claim_recovery_secs())

    recovery_cursor = db.posts.find(
        {
            "status": "queued",
            "deleted_at": {"$exists": False},
            "processing_started_at": {"$exists": False},
            "queue_job_id": None,
            "scheduler_claimed_at": {"$lte": claim_recovery_threshold},
        },
        {"_id": 0, "id": 1},
        limit=batch_size,
    )
    async for post in recovery_cursor:
        reset = await db.posts.find_one_and_update(
            {
                "id": post["id"],
                "status": "queued",
                "processing_started_at": {"$exists": False},
                "queue_job_id": None,
            },
            {
                "$set": {
                    "status": "scheduled",
                    "updated_at": now,
                    "scheduler_recovered_at": now,
                },
                "$unset": {
                    "scheduler_claimed_at": "",
                },
                "$push": {
                    "status_history": {
                        "status": "scheduled",
                        "timestamp": now.isoformat(),
                        "actor": "beat_scheduler_recovery",
                        "message": "Recovered queued post after parent task was never enqueued",
                    }
                },
            },
            return_document=True,
        )
        if reset is not None:
            recovered += 1

    while batches_processed < max_batches:
        cursor = db.posts.find(
            {"status": "scheduled", "scheduled_time": {"$lte": enqueue_horizon}},
            {"_id": 0, "id": 1, "scheduled_time": 1, "platforms": 1, "version": 1},
            limit=batch_size,
        )
        batch_posts = [post async for post in cursor]
        if not batch_posts:
            break
        batches_processed += 1

        for post in batch_posts:
            post_id = post["id"]
            scheduled = _coerce_utc_datetime(post.get("scheduled_time"))
            queue = (
                "high_priority"
                if isinstance(scheduled, datetime) and scheduled <= high_priority_threshold
                else "default"
            )
            countdown = (
                max(0.0, (scheduled - now).total_seconds())
                if isinstance(scheduled, datetime)
                else 0.0
            )

            # Atomic claim — prevents double-enqueue from concurrent Beat instances (EC2)
            result = await db.posts.find_one_and_update(
                {"id": post_id, "status": "scheduled"},
                {
                    "$set": {
                        "status": "queued",
                        "scheduler_claimed_at": now,
                    },
                    "$push": {"status_history": {
                        "status": "queued",
                        "timestamp": now.isoformat(),
                        "actor": "beat_scheduler",
                    }},
                },
                return_document=True,
            )

            if result is None:
                logger.debug("Post %s already claimed — skipping", post_id)
                continue

            try:
                async_result = publish_post.apply_async(
                    kwargs={
                        "post_id": post_id,
                        "version": post.get("version", 1),
                    },
                    countdown=countdown,
                    queue=queue,
                )
            except Exception:
                rollback_time = datetime.now(timezone.utc)
                await db.posts.update_one(
                    {
                        "id": post_id,
                        "status": "queued",
                        "processing_started_at": {"$exists": False},
                    },
                    {
                        "$set": {
                            "status": "scheduled",
                            "queue_job_id": None,
                            "updated_at": rollback_time,
                        },
                        "$unset": {
                            "scheduler_claimed_at": "",
                        },
                        "$push": {
                            "status_history": {
                                "status": "scheduled",
                                "timestamp": rollback_time.isoformat(),
                                "actor": "beat_scheduler",
                                "message": "Parent publish enqueue failed; reverted to scheduled for retry",
                            }
                        },
                    },
                )
                logger.exception("Failed to enqueue scheduled post %s; reverted to scheduled", post_id)
                continue

            queue_job_id = getattr(async_result, "id", None)
            if isinstance(queue_job_id, str) and queue_job_id:
                await db.posts.update_one(
                    {"id": post_id, "status": "queued"},
                    {"$set": {"queue_job_id": queue_job_id, "updated_at": now}},
                )
            enqueued += 1
            logger.info(
                "Enqueued post %s to %s queue with countdown=%ss (scheduled_lag_target)",
                post_id,
                queue,
                f"{countdown:.2f}",
            )

    # 17.3 + Phase 1.5.3: Trigger pre-upload for video posts whose dynamic window has opened.
    # Use a wide scan horizon (60 min) and filter per-post using calculate_pre_upload_start.
    pre_upload_scan_horizon = now + timedelta(minutes=60)
    pre_upload_cursor = db.posts.find(
        {
            "status": "scheduled",
            "scheduled_time": {"$lte": pre_upload_scan_horizon, "$gt": enqueue_horizon},
            "post_type": {"$in": ["video", "reel", "story"]},
        },
        {
            "_id": 0,
            "id": 1,
            "platforms": 1,
            "publish_targets": 1,
            "scheduled_time": 1,
            "video_size_mb": 1,
            "post_type": 1,
            "pre_upload_results": 1,
        },
        limit=200,  # raised from 50 — handles burst of video posts at popular time slots
    )
    pre_uploads_triggered = 0
    async for post in pre_upload_cursor:
        # 17.3: Only trigger if we've reached the calculated pre_upload start time
        pre_upload_start = _get_pre_upload_start(post, now)
        if now < pre_upload_start:
            continue  # Not yet time to start pre-upload for this post

        from celery_workers.tasks.publish import pre_upload_task
        publish_targets = [
            target
            for target in _get_publish_targets(post)
            if _requires_pre_upload(target["platform"], post)
        ]
        if not publish_targets:
            continue

        # 17.5: Record pre_upload_start_time + estimated_upload_duration on the post
        file_size_mb = post.get("video_size_mb", 0) or 0
        estimated_secs = None
        if file_size_mb > 0 and post.get("scheduled_time"):
            _, estimated_secs = calculate_pre_upload_start(
                post["scheduled_time"], file_size_mb, [target["platform"] for target in publish_targets]
            )

        for target in publish_targets:
            target_key = target["target_key"]
            current_status = _get_platform_pre_upload_status(post, target_key)
            if current_status in {"uploading", "ready"}:
                continue

            update_doc = {
                "$set": {
                    _pre_upload_result_path(target_key, "start_time"): now,
                    "updated_at": now,
                },
            }
            if estimated_secs is not None:
                update_doc["$set"][_pre_upload_result_path(target_key, "estimated_duration_secs")] = estimated_secs

            claim = await db.posts.update_one(
                {
                    "id": post["id"],
                    "$or": [
                        {_pre_upload_result_path(target_key, "status"): {"$exists": False}},
                        {_pre_upload_result_path(target_key, "status"): {"$in": ["pending", "failed", "timeout"]}},
                    ],
                },
                update_doc,
            )
            if claim.modified_count == 0:
                continue

            if estimated_secs is not None:
                await _sync_pre_upload_aggregate(db, post["id"])

            if target["platform"] in ("instagram", "youtube"):
                pre_upload_task.apply_async(
                    kwargs={"post_id": post["id"], "platform": target["platform"], "account_id": target["account_id"]},
                    queue="media_processing",
                )
                pre_uploads_triggered += 1

    if batches_processed >= max_batches:
        logger.warning(
            "Scheduled scan hit batch cap: recovered=%s enqueued=%s batches=%s batch_size=%s lookahead=%ss",
            str(recovered),
            str(enqueued),
            str(batches_processed),
            str(batch_size),
            str(lookahead_secs),
        )
    else:
        logger.info(
            "Scheduled scan complete: recovered=%s enqueued=%s pre_uploads=%s batches=%s batch_size=%s lookahead=%ss",
            str(recovered),
            str(enqueued),
            str(pre_uploads_triggered),
            str(batches_processed),
            str(batch_size),
            str(lookahead_secs),
        )

    return {
        "recovered": recovered,
        "enqueued": enqueued,
        "pre_uploads": pre_uploads_triggered,
        "batches_processed": batches_processed,
        "scan_time": now.isoformat(),
        "lookahead_seconds": lookahead_secs,
    }


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
    return run_async(_async_scan_pre_upload_timeouts())


async def _async_scan_pre_upload_timeouts() -> dict:
    from celery_workers.tasks.publish import (
        _get_publish_targets,
        _get_platform_pre_upload_started_at,
        _get_platform_pre_upload_status,
        _move_to_dlq,
        _pre_upload_result_path,
        _sync_pre_upload_aggregate,
    )

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    timeout_threshold = now - timedelta(minutes=120)  # 2h — 10GB files need longer upload windows

    cursor = db.posts.find(
        {"pre_upload_results": {"$exists": True, "$ne": {}}},
        {"_id": 0, "id": 1, "user_id": 1, "platforms": 1, "scheduled_time": 1, "pre_upload_results": 1, "publish_targets": 1},
        limit=50,
    )

    timed_out = 0
    async for post in cursor:
        post_id = post["id"]
        for target in _get_publish_targets(post):
            if target["platform"] not in {"instagram", "youtube"}:
                continue
            target_key = target["target_key"]
            started_at = _get_platform_pre_upload_started_at(post, target_key)
            status = _get_platform_pre_upload_status(post, target_key)
            if status != "uploading" or not started_at or started_at > timeout_threshold:
                continue

            result = await db.posts.find_one_and_update(
                {
                    "id": post_id,
                    _pre_upload_result_path(target_key, "status"): "uploading",
                },
                {
                    "$set": {
                        _pre_upload_result_path(target_key, "status"): "timeout",
                        _pre_upload_result_path(target_key, "error"): "Pre-upload timed out after 2 hours — moved to DLQ",
                        _pre_upload_result_path(target_key, "timed_out_at"): now,
                        "updated_at": now,
                    },
                },
                projection={"_id": 0, _pre_upload_result_path(target_key, "started_at"): 1},
            )
            if result is None:
                continue

            await _sync_pre_upload_aggregate(db, post_id)

            logger.error(
                "17.4D: pre_upload timeout for post %s platform %s (started_at=%s) — moving to DLQ",
                post_id, target["platform"], _get_platform_pre_upload_started_at(result, target_key),
            )

            try:
                await _move_to_dlq(post_id, "pre_upload_timeout", platform=target["platform"], account_id=target["account_id"])
            except Exception as dlq_exc:
                logger.error("17.4D: Failed to move %s/%s to DLQ: %s", post_id, target["platform"], dlq_exc)

            timed_out += 1

    if timed_out:
        logger.warning("17.4D: Timed out %d stuck pre_upload tasks", timed_out)

    return {"status": "complete", "timed_out": timed_out, "scan_time": now.isoformat()}
