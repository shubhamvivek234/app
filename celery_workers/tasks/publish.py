"""
Phase 1.4 + 1.5 + 1.6 — Core publishing task.
- Exponential backoff retry (1m → 5m → 15m → DLQ)
- Poison pill guard (Phase 7.3)
- Version conflict check (EC3)
- Two-phase publish: pre_upload_task + publish_task
- Per-platform independent execution with platform_results (Phase 1.6)
- Two-phase Redis+MongoDB write confirmation (EC17)
"""
import logging
import os
import random
import asyncio
from datetime import datetime, timedelta

from celery import group
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_queue_redis, get_cache_redis

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
MAX_DELIVERY_COUNT = 5  # Poison pill threshold


# ── Poison pill guard (Phase 7.3) ────────────────────────────────────────────
async def _check_poison_pill(task_id: str) -> bool:
    """Returns True if this task has been delivered too many times → DLQ."""
    r = get_queue_redis()
    key = f"delivery_count:{task_id}"
    count = await r.incr(key)
    await r.expire(key, 86400)  # 24-hour TTL
    return int(count) > MAX_DELIVERY_COUNT


# ── Jitter helper (Phase 1.6) ─────────────────────────────────────────────────
def _jitter_seconds(post_type: str) -> int:
    if "video" in post_type:
        return random.randint(0, 300)
    elif post_type == "text":
        return random.randint(0, 30)
    return random.randint(0, 60)


# ── Aggregate status logic (Phase 1.6.3) ─────────────────────────────────────
def recompute_aggregate_status(platform_results: dict) -> str:
    statuses = {v.get("status") for v in platform_results.values()}
    if not statuses:
        return "scheduled"
    if statuses == {"published"}:
        return "published"
    if statuses == {"failed"}:
        return "failed"
    if statuses == {"cancelled"}:
        return "cancelled"
    terminal = {"published", "failed", "cancelled"}
    if statuses & {"processing", "retrying", "queued"}:
        return "processing"
    if statuses.issubset(terminal) and "published" in statuses:
        return "partial"
    return "processing"


# ── Media cleanup gate (Phase 2.6.1 / Section 18.9) ──────────────────────────
def should_cleanup_media(platform_results: dict) -> bool:
    """Only delete source media when ALL platforms are in terminal state."""
    terminal = {"published", "failed", "cancelled"}
    return all(v.get("status") in terminal for v in platform_results.values())


# ── Parent publish task ───────────────────────────────────────────────────────
@celery_app.task(
    name="celery_workers.tasks.publish.publish_post",
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_post(self, post_id: str, version: int) -> dict:
    """
    Parent task: reads post, applies jitter, spawns one child per platform.
    Phase 1.6.2 — platforms execute in parallel via celery.group().
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_publish_post(self, post_id, version)
    )


async def _async_publish_post(task, post_id: str, version: int) -> dict:
    from celery_workers.shutdown_handler import is_shutting_down
    from celery_workers.tasks.cleanup import schedule_media_cleanup

    # Poison pill guard
    if await _check_poison_pill(task.request.id):
        logger.error("Poison pill: task %s delivered >%d times — moving to DLQ", task.request.id, MAX_DELIVERY_COUNT)
        await _move_to_dlq(post_id, "poison_pill_exceeded")
        return {"status": "dlq", "reason": "poison_pill"}

    # Graceful shutdown check
    if is_shutting_down():
        logger.info("Worker shutting down — re-queuing post %s", post_id)
        raise task.retry(countdown=5)

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    post = await db.posts.find_one({"id": post_id}, {"_id": 0})

    # Post deleted mid-flight (EC3)
    if post is None:
        logger.info("Post %s deleted mid-flight — aborting cleanly", post_id)
        return {"status": "post_deleted"}

    # Version mismatch — post was edited while queued (EC3)
    if post.get("version", 1) != version:
        logger.info("Post %s version mismatch (%d vs %d) — re-enqueuing with new version",
                    post_id, post.get("version"), version)
        publish_post.apply_async(
            kwargs={"post_id": post_id, "version": post.get("version", 1)},
            queue="default",
        )
        return {"status": "version_mismatch_requeued"}

    # Apply jitter
    post_type = post.get("post_type", "image")
    jitter = _jitter_seconds(post_type)
    if jitter > 0:
        import time
        time.sleep(jitter)

    # Update post with jitter info + processing status
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {
            "status": "processing",
            "jitter_seconds": jitter,
            "processing_started_at": datetime.utcnow().isoformat(),
        }},
    )

    # Spawn per-platform tasks in parallel (Phase 1.6.2)
    platforms = post.get("platforms", [])
    platform_tasks = group(
        publish_to_platform.s(post_id=post_id, platform=p, attempt=0)
        for p in platforms
    )
    platform_tasks.apply_async(queue="default")

    return {"status": "dispatched", "platforms": platforms, "jitter_seconds": jitter}


# ── Per-platform task ─────────────────────────────────────────────────────────
@celery_app.task(
    name="celery_workers.tasks.publish.publish_to_platform",
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def publish_to_platform(self, post_id: str, platform: str, attempt: int = 0) -> dict:
    return asyncio.get_event_loop().run_until_complete(
        _async_publish_to_platform(self, post_id, platform, attempt)
    )


async def _async_publish_to_platform(task, post_id: str, platform: str, attempt: int) -> dict:
    from platform_adapters import get_adapter
    from celery_workers.tasks.publish import recompute_aggregate_status, should_cleanup_media
    from celery_workers.tasks.cleanup import schedule_media_cleanup

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    r_cache = get_cache_redis()

    # EC17: Check Redis confirmation cache first — may already be done
    confirm_key = f"confirmed:{post_id}:{platform}"
    cached = await r_cache.get(confirm_key)
    if cached:
        logger.info("Platform %s/%s already confirmed in Redis — skipping API call", post_id, platform)
        return {"status": "already_confirmed"}

    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if post is None:
        return {"status": "post_deleted"}

    # EC15: Check subscription is still active before publishing
    try:
        from utils.subscription import check_subscription_active
        user_id = post.get("user_id", "")
        is_active, reason = await check_subscription_active(db, user_id)
        if not is_active:
            logger.warning("EC15: subscription expired for user %s — pausing post %s", user_id, post_id)
            await _update_platform_result(db, post_id, platform, {
                "status": "paused",
                "error": f"Subscription expired: {reason}",
            })
            return {"status": "subscription_expired"}
    except ImportError:
        pass  # subscription module not available — skip check

    try:
        adapter = get_adapter(platform)
        result = await adapter.publish(post)

        post_url = result.get("post_url")
        platform_post_id = result.get("platform_post_id")

        # EC17 Phase 2.6.3: Write confirmation to Redis FIRST
        import json
        confirmation_payload = {
            "post_url": post_url,
            "platform_post_id": platform_post_id,
            "published_at": datetime.utcnow().isoformat(),
        }
        await r_cache.setex(confirm_key, 86400, json.dumps(confirmation_payload))

        # Then update MongoDB
        await _update_platform_result(db, post_id, platform, {
            "status": "published",
            "post_url": post_url,
            "platform_post_id": platform_post_id,
            "published_at": datetime.utcnow(),
        })

        # Recompute aggregate status
        updated_post = await db.posts.find_one({"id": post_id}, {"platform_results": 1})
        if updated_post:
            agg_status = recompute_aggregate_status(updated_post.get("platform_results", {}))
            await db.posts.update_one({"id": post_id}, {"$set": {"status": agg_status}})

            # Media cleanup gate (Phase 2.6.1)
            if should_cleanup_media(updated_post.get("platform_results", {})):
                schedule_media_cleanup.apply_async(
                    kwargs={"post_id": post_id},
                    countdown=300,  # 5-minute delay
                    queue="default",
                )

        return {"status": "published", "platform": platform}

    except Exception as exc:
        from platform_adapters.base import classify_error, ErrorClass, PlatformHTTPError

        error_class = classify_error(exc)

        if error_class == ErrorClass.PERMANENT:
            logger.error("Permanent error publishing %s/%s: %s", post_id, platform, exc)
            await _update_platform_result(db, post_id, platform, {
                "status": "failed",
                "error": str(exc),
                "retry_count": attempt,
                "last_attempt_at": datetime.utcnow(),
            })

            # EC16: Detect account suspension/revocation and trigger ghost cascade
            error_code = getattr(exc, "code", None)
            subcode = getattr(exc, "subcode", None)
            is_auth_error = (
                (isinstance(exc, PlatformHTTPError) and getattr(exc, "status_code", 0) in (401, 403))
                or subcode in {458, 460}
                or error_code in (190, 261, 326)
            )
            if is_auth_error:
                try:
                    from utils.ghost_cascade import handle_ghost_account
                    social_account_id = post.get("social_account_id") or post.get("account", {}).get("id", "")
                    if social_account_id:
                        await handle_ghost_account(
                            db, social_account_id, error_code,
                            suspension_reason=str(exc),
                        )
                except ImportError:
                    pass

            await _send_failure_notification(post_id, platform, str(exc))
            return {"status": "permanent_failure"}

        elif error_class == ErrorClass.RATE_LIMITED:
            # Do NOT count as retry failure
            retry_after = getattr(exc, "retry_after", 3600)
            logger.warning("Rate limited on %s/%s — re-queuing after %ds", post_id, platform, retry_after)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "next_retry_at": datetime.utcnow() + timedelta(seconds=retry_after),
            })
            raise task.retry(countdown=retry_after, exc=exc)

        else:
            # Transient — exponential backoff
            countdown_map = {0: 60, 1: 300, 2: 900}
            jitter = random.randint(0, [30, 60, 120][min(attempt, 2)])
            countdown = countdown_map.get(attempt, 900) + jitter

            if attempt >= MAX_RETRIES:
                logger.error("Max retries exceeded for %s/%s — DLQ", post_id, platform)
                await _move_to_dlq(post_id, str(exc), platform=platform)
                await _send_failure_notification(post_id, platform, str(exc))
                return {"status": "dlq"}

            logger.warning("Retry %d for %s/%s in %ds: %s", attempt + 1, post_id, platform, countdown, exc)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "retry_count": attempt + 1,
                "last_attempt_at": datetime.utcnow(),
                "next_retry_at": datetime.utcnow() + timedelta(seconds=countdown),
                "error": str(exc),
            })
            raise task.retry(countdown=countdown, exc=exc, kwargs={
                "post_id": post_id, "platform": platform, "attempt": attempt + 1
            })


# ── Pre-upload task (Phase 1.5.3) ─────────────────────────────────────────────
@celery_app.task(
    name="celery_workers.tasks.publish.pre_upload_task",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def pre_upload_task(self, post_id: str, platform: str) -> dict:
    """
    Fires 15+ minutes before scheduled_time.
    Uploads media container (Instagram) or private video (YouTube).
    Stores container_id/video_id for use by publish_task at scheduled_time.
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_pre_upload(self, post_id, platform)
    )


async def _async_pre_upload(task, post_id: str, platform: str) -> dict:
    from platform_adapters import get_adapter

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"pre_upload_status": "uploading", "pre_upload_started_at": datetime.utcnow()}}
    )

    try:
        adapter = get_adapter(platform)
        post = await db.posts.find_one({"id": post_id}, {"_id": 0})
        container_result = await adapter.pre_upload(post)

        # EC12: If Instagram container is still pending, dispatch non-blocking poller
        if container_result.get("pre_upload_status") == "pending" and platform == "instagram":
            from celery_workers.tasks.container_status import check_instagram_container_status
            container_id = container_result.get("container_id", "")
            account = post.get("account", {})
            check_instagram_container_status.apply_async(
                kwargs={
                    "post_id": post_id,
                    "container_id": container_id,
                    "access_token_encrypted": account.get("access_token", ""),
                    "poll_attempt": 0,
                },
                queue="default",
            )
            await db.posts.update_one(
                {"id": post_id},
                {"$set": {
                    "pre_upload_status": "uploading",
                    f"platform_container_ids.{platform}": container_id,
                }}
            )
            return {"status": "polling", "platform": platform, "container_id": container_id}

        expiry = datetime.utcnow() + timedelta(hours=23)
        container_id = container_result.get("container_id") or container_result.get("video_id")
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {
                "pre_upload_status": "ready",
                "pre_upload_completed_at": datetime.utcnow(),
                f"platform_container_ids.{platform}": container_id,
                f"container_expiry_at.{platform}": expiry.isoformat(),
            }}
        )
        return {"status": "ready", "platform": platform}

    except Exception as exc:
        logger.error("pre_upload_task failed for %s/%s: %s", post_id, platform, exc)
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {"pre_upload_status": "failed", "pre_upload_error": str(exc)}}
        )
        raise task.retry(countdown=60, exc=exc)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _update_platform_result(db, post_id: str, platform: str, update: dict) -> None:
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {f"platform_results.{platform}.{k}": v for k, v in update.items()}}
    )


async def _move_to_dlq(post_id: str, reason: str, platform: str | None = None) -> None:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    update: dict = {"dlq_reason": reason, "status": "failed"}
    if platform:
        update[f"platform_results.{platform}.status"] = "failed"
    await db.posts.update_one({"id": post_id}, {"$set": update})


async def _send_failure_notification(post_id: str, platform: str, error: str) -> None:
    from celery_workers.tasks.media import send_notification
    send_notification.apply_async(
        kwargs={"post_id": post_id, "type": "publish_failed", "platform": platform, "error": error},
        queue="default",
    )
