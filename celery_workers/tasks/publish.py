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
from datetime import datetime, timedelta, timezone

from celery import group
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_queue_redis, get_cache_redis
from utils.circuit_breaker import can_attempt, record_success, record_failure
from utils.feature_flags import is_enabled

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
            "processing_started_at": datetime.now(timezone.utc).isoformat(),
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


# 17.4B: max seconds to wait for pre_upload to become ready at publish time
_PRE_UPLOAD_POLL_INTERVAL = 5   # seconds between status checks
_PRE_UPLOAD_MAX_WAIT = 600      # 10 minutes maximum


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

    # 20.14: Feature flag kill-switch — bail out immediately if platform disabled
    try:
        from utils.feature_flags import is_enabled
        flag_name = f"{platform}_publishing"
        if not is_enabled(flag_name):
            logger.warning("20.14: Feature flag %s is OFF — skipping publish for post %s", flag_name, post_id)
            await _update_platform_result(db, post_id, platform, {
                "status": "paused",
                "error": f"Platform {platform} is currently disabled via feature flag",
            })
            return {"status": "feature_disabled", "platform": platform}
    except ImportError:
        pass

    # 20.5: Per-platform poison pill guard — each platform has its own delivery counter
    r_queue = get_queue_redis()
    pp_key = f"delivery_count:{task.request.id}:{platform}"
    pp_count = await r_queue.incr(pp_key)
    await r_queue.expire(pp_key, 86400)
    if int(pp_count) > MAX_DELIVERY_COUNT:
        logger.error("20.5: Poison pill on %s/%s (delivered %d times) — moving to DLQ", post_id, platform, pp_count)
        await _move_to_dlq(post_id, "poison_pill_exceeded", platform=platform)
        return {"status": "dlq", "reason": "poison_pill", "platform": platform}

    # 20.1: Circuit breaker — fail fast if platform is known-down
    try:
        from utils.circuit_breaker import can_attempt
        if not await can_attempt(r_cache, platform):
            logger.warning("20.1: Circuit OPEN for %s — requeuing post %s (5-min backoff)", platform, post_id)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "error": f"Platform {platform} circuit breaker OPEN — requeued",
                "next_retry_at": datetime.utcnow() + timedelta(seconds=300),
            })
            raise task.retry(countdown=300, exc=Exception(f"Circuit OPEN for {platform}"))
    except ImportError:
        pass

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

    # 17.4 Scenario B: pre_upload still running at scheduled publish time.
    # Poll every 5s for up to 10 minutes before giving up.
    if platform in ("instagram", "youtube") and post.get("post_type") in ("video", "reel", "story"):
        pre_status = post.get("pre_upload_status", "")
        if pre_status == "failed":
            err = post.get("pre_upload_error", "Pre-upload failed before publish time")
            logger.error("17.4C: pre_upload failed for %s/%s — %s", post_id, platform, err)
            await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err})
            await _send_failure_notification(db, post_id, platform, err)
            return {"status": "failed", "reason": "pre_upload_failed"}

        if pre_status not in ("ready", "", None):
            # Still uploading — poll every 5s for up to 10 minutes (17.4B)
            waited = 0
            logger.info(
                "17.4B: pre_upload still %r at publish time for %s/%s — polling up to %ds",
                pre_status, post_id, platform, _PRE_UPLOAD_MAX_WAIT,
            )
            while waited < _PRE_UPLOAD_MAX_WAIT:
                await asyncio.sleep(_PRE_UPLOAD_POLL_INTERVAL)
                waited += _PRE_UPLOAD_POLL_INTERVAL
                refreshed = await db.posts.find_one(
                    {"id": post_id}, {"pre_upload_status": 1, "pre_upload_error": 1}
                )
                current_status = (refreshed or {}).get("pre_upload_status", "")
                if current_status == "ready":
                    logger.info(
                        "17.4B: pre_upload ready after %ds for %s/%s",
                        waited, post_id, platform,
                    )
                    # Reload full post with updated container IDs
                    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                    break
                if current_status == "failed":
                    err = (refreshed or {}).get("pre_upload_error", "Pre-upload failed")
                    logger.error("17.4B: pre_upload failed while polling %s/%s — %s", post_id, platform, err)
                    await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err})
                    await _send_failure_notification(db, post_id, platform, err)
                    return {"status": "failed", "reason": "pre_upload_failed"}
            else:
                # 10-minute timeout expired
                msg = (
                    f"Timed out waiting for pre_upload on {platform} "
                    f"(waited {_PRE_UPLOAD_MAX_WAIT}s). "
                    f"Post published {waited}s late."
                )
                logger.error("17.4B: %s for post %s", msg, post_id)
                await _update_platform_result(db, post_id, platform, {"status": "failed", "error": msg})
                await _send_failure_notification(db, post_id, platform, msg)
                return {"status": "failed", "reason": "pre_upload_wait_timeout"}

    try:
        # ── Circuit breaker check (Section 20.1) ───────────────────────────────
        cb_open = await can_attempt(r_cache, platform)
        if not cb_open:
            logger.warning("Circuit OPEN for %s — skipping platform call for post %s", platform, post_id)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "error": f"Circuit breaker OPEN for {platform} — will retry when circuit closes",
                "next_retry_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            })
            raise task.retry(countdown=300, exc=Exception(f"Circuit OPEN: {platform}"))

        # Gap 2.7: Inject decrypted access token so adapter can authenticate
        try:
            from utils.encryption import decrypt
            account_doc = await db.social_accounts.find_one({
                "user_id": post.get("user_id"),
                "platform": platform,
                "is_active": True,
            })
            if account_doc and account_doc.get("access_token"):
                post = {**post, "access_token": decrypt(account_doc["access_token"]), "account": account_doc}
        except Exception as _token_err:
            logger.warning("Could not inject access token for %s/%s: %s", post_id, platform, _token_err)

        adapter = get_adapter(platform)
        result = await adapter.publish(post)

        # 20.1: Record success — close circuit if it was half-open
        try:
            from utils.circuit_breaker import record_success
            await record_success(r_cache, platform)
        except ImportError:
            pass

        post_url = result.get("post_url")
        platform_post_id = result.get("platform_post_id")

        # EC17 Phase 2.6.3: Write confirmation to Redis FIRST
        import json
        confirmation_payload = {
            "post_url": post_url,
            "platform_post_id": platform_post_id,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        await r_cache.setex(confirm_key, 86400, json.dumps(confirmation_payload))

        # ── Circuit breaker: record success (Section 20.1) ────────────────────
        await record_success(r_cache, platform)

        # Then update MongoDB
        await _update_platform_result(db, post_id, platform, {
            "status": "published",
            "post_url": post_url,
            "platform_post_id": platform_post_id,
            "published_at": datetime.now(timezone.utc),
        })

        # Recompute aggregate status
        updated_post = await db.posts.find_one({"id": post_id}, {"platform_results": 1, "status": 1, "user_id": 1})
        prev_agg_status = updated_post.get("status") if updated_post else None
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

            # 18.8: Per-platform success notification
            user_id = updated_post.get("user_id", "")
            await _send_success_notification(db, post_id, platform, post_url or "", user_id)

            # 18.8: Partial-recovery notification — fires when last failed platform publishes
            if agg_status == "published" and prev_agg_status == "partial":
                await _send_recovery_notification(db, post_id, user_id)

        return {"status": "published", "platform": platform}

    except Exception as exc:
        from platform_adapters.base import classify_error, ErrorClass, PlatformHTTPError

        # 20.1: Record failure — may trip circuit breaker if threshold exceeded
        try:
            from utils.circuit_breaker import record_failure
            await record_failure(r_cache, platform)
        except ImportError:
            pass

        error_class = classify_error(exc)

        if error_class == ErrorClass.PERMANENT:
            logger.error("Permanent error publishing %s/%s: %s", post_id, platform, exc)
            await _update_platform_result(db, post_id, platform, {
                "status": "failed",
                "error": str(exc),
                "retry_count": attempt,
                "last_attempt_at": datetime.now(timezone.utc),
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

            # ── Circuit breaker: record failure (Section 20.1) ────────────────
            await record_failure(r_cache, platform)

            await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
            return {"status": "permanent_failure"}

        elif error_class == ErrorClass.RATE_LIMITED:
            # Do NOT count as retry failure
            retry_after = getattr(exc, "retry_after", 3600)
            logger.warning("Rate limited on %s/%s — re-queuing after %ds", post_id, platform, retry_after)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=retry_after),
            })
            raise task.retry(countdown=retry_after, exc=exc)

        else:
            # Transient — exponential backoff
            countdown_map = {0: 60, 1: 300, 2: 900}
            jitter = random.randint(0, [30, 60, 120][min(attempt, 2)])
            countdown = countdown_map.get(attempt, 900) + jitter

            if attempt >= MAX_RETRIES:
                logger.error("Max retries exceeded for %s/%s — DLQ", post_id, platform)
                await record_failure(r_cache, platform)  # Section 20.1
                await _move_to_dlq(post_id, str(exc), platform=platform)
                await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
                return {"status": "dlq"}

            logger.warning("Retry %d for %s/%s in %ds: %s", attempt + 1, post_id, platform, countdown, exc)
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "retry_count": attempt + 1,
                "last_attempt_at": datetime.now(timezone.utc),
                "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=countdown),
                "error": str(exc),
            })
            raise task.retry(countdown=countdown, exc=exc, kwargs={
                "post_id": post_id, "platform": platform, "attempt": attempt + 1
            })


# ── 17.3 Pre-upload timing formula ────────────────────────────────────────────

# Upload speed estimates in seconds-per-MB (tuned from real metrics over time)
_UPLOAD_RATE_SECS_PER_MB: dict[str, float] = {
    "instagram": 0.8,
    "youtube": 0.5,
}
# Platform video processing time estimates in seconds
_PROCESSING_SECS: dict[str, int] = {
    "instagram": 180,
    "youtube": 300,
}
_SAFETY_BUFFER_SECS = 300  # 5-minute safety margin
_DEFAULT_PRE_UPLOAD_SECS = 900  # 15-minute fallback when file_size unknown


def calculate_pre_upload_start(
    scheduled_time: datetime,
    file_size_mb: float,
    platforms: list,
) -> tuple:
    """
    17.3 — Calculate dynamic pre_upload_start_time based on file size + platforms.

    Returns (pre_upload_start_time: datetime, estimated_duration_secs: int).

    The upload should FINISH at scheduled_time, not START.  This calculates
    when uploading must BEGIN so that processing completes before the deadline.

    Over time: collect actual_upload_duration from each job and replace
    _UPLOAD_RATE_SECS_PER_MB with per-user averages from slow connections.
    """
    relevant = [p for p in platforms if p in _UPLOAD_RATE_SECS_PER_MB]
    if not relevant or file_size_mb <= 0:
        estimated = _DEFAULT_PRE_UPLOAD_SECS
    else:
        estimated = int(max(
            (file_size_mb * _UPLOAD_RATE_SECS_PER_MB[p]) + _PROCESSING_SECS.get(p, 180)
            for p in relevant
        )) + _SAFETY_BUFFER_SECS

    return scheduled_time - timedelta(seconds=estimated), estimated


# ── Pre-upload task (Phase 1.5.3 + 17.3) ─────────────────────────────────────
@celery_app.task(
    name="celery_workers.tasks.publish.pre_upload_task",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def pre_upload_task(self, post_id: str, platform: str) -> dict:
    """
    Fires at pre_upload_start_time (dynamically calculated, min 15 min ahead).
    Uploads media container (Instagram) or private video (YouTube).
    Stores container_id/video_id for use by publish_task at scheduled_time.
    Records actual_upload_duration for future estimate calibration (17.3).
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_pre_upload(self, post_id, platform)
    )


async def _async_pre_upload(task, post_id: str, platform: str) -> dict:
    from platform_adapters import get_adapter

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    started_at = datetime.now(timezone.utc)
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"pre_upload_status": "uploading", "pre_upload_started_at": started_at}}
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

        completed_at = datetime.now(timezone.utc)
        actual_duration = int((completed_at - started_at).total_seconds())
        expiry = completed_at + timedelta(hours=23)
        container_id = container_result.get("container_id") or container_result.get("video_id")
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {
                "pre_upload_status": "ready",
                "pre_upload_completed_at": completed_at,
                "actual_upload_duration": actual_duration,  # 17.5: feeds future estimates
                f"platform_container_ids.{platform}": container_id,
                f"container_expiry_at.{platform}": expiry.isoformat(),
            }}
        )
        logger.info(
            "17.3: pre_upload ready for %s/%s — actual_duration=%ds container=%s",
            post_id, platform, actual_duration, container_id,
        )
        return {"status": "ready", "platform": platform, "actual_duration_secs": actual_duration}

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

    # 20.4: Publish SSE update so browser is notified in real-time (non-blocking)
    try:
        import json as _json
        import os as _os
        from db.redis_client import get_cache_redis
        r = get_cache_redis()
        post_doc = await db.posts.find_one({"id": post_id}, {"user_id": 1, "status": 1})
        if post_doc:
            payload = _json.dumps({
                "type": "platform_update",
                "post_id": post_id,
                "platform": platform,
                "update": {k: str(v) for k, v in update.items()},
            })
            # Publish to per-post and per-user channels
            await r.publish(f"post:{post_id}:updates", payload)
            await r.publish(f"user:{post_doc.get('user_id', '')}:updates", payload)
    except Exception as _sse_err:
        logger.debug("SSE publish failed (non-blocking): %s", _sse_err)


async def _move_to_dlq(post_id: str, reason: str, platform: str | None = None) -> None:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    update: dict = {"dlq_reason": reason, "status": "failed"}
    if platform:
        update[f"platform_results.{platform}.status"] = "permanently_failed"
    post = await db.posts.find_one_and_update(
        {"id": post_id},
        {"$set": update},
        return_document=True,
        projection={"user_id": 1},
    )
    # 18.8: DLQ notification — "permanently failed — [Reschedule]"
    if post and platform:
        user_id = post.get("user_id", "")
        try:
            from celery_workers.tasks.media import send_notification
            send_notification.apply_async(
                kwargs={
                    "post_id": post_id,
                    "type": "publish_permanently_failed",
                    "platform": platform,
                    "error": (
                        f"Your post permanently failed on {platform.capitalize()} after "
                        f"{MAX_RETRIES} attempts — please reschedule or edit the post."
                    ),
                    "user_id": user_id,
                },
                queue="default",
            )
        except Exception as notify_exc:
            logger.warning("18.8: Failed to send DLQ notification for %s/%s: %s", post_id, platform, notify_exc)


async def _send_failure_notification(db, post_id: str, platform: str, error: str, user_id: str = "") -> None:
    # Section 20.12: check user notification preferences before sending
    if user_id:
        try:
            from utils.notification_prefs import should_notify
            if not await should_notify(db, user_id, "post.failed", "email"):
                logger.debug("Notification suppressed for user %s event post.failed", user_id)
                return
        except Exception:
            pass  # never block notifications on pref lookup failure
    from celery_workers.tasks.media import send_notification
    send_notification.apply_async(
        kwargs={"post_id": post_id, "type": "publish_failed", "platform": platform, "error": error},
        queue="default",
    )


# 18.8: Per-platform success notification
async def _send_success_notification(db, post_id: str, platform: str, post_url: str, user_id: str = "") -> None:
    if user_id:
        try:
            from utils.notification_prefs import should_notify
            if not await should_notify(db, user_id, "post.published", "email"):
                logger.debug("Notification suppressed for user %s event post.published", user_id)
                return
        except Exception:
            pass
    try:
        from celery_workers.tasks.media import send_notification
        send_notification.apply_async(
            kwargs={
                "post_id": post_id,
                "type": "publish_success",
                "platform": platform,
                "post_url": post_url,
                "user_id": user_id,
            },
            queue="default",
        )
    except Exception as exc:
        logger.warning("18.8: Failed to send success notification for %s/%s: %s", post_id, platform, exc)


# 18.8: Partial-recovery notification — all platforms now published
async def _send_recovery_notification(db, post_id: str, user_id: str = "") -> None:
    if user_id:
        try:
            from utils.notification_prefs import should_notify
            if not await should_notify(db, user_id, "post.published", "email"):
                return
        except Exception:
            pass
    try:
        from celery_workers.tasks.media import send_notification
        send_notification.apply_async(
            kwargs={
                "post_id": post_id,
                "type": "publish_recovered",
                "user_id": user_id,
            },
            queue="default",
        )
    except Exception as exc:
        logger.warning("18.8: Failed to send recovery notification for %s: %s", post_id, exc)
