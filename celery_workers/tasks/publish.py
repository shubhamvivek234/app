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
from redis.exceptions import RedisError
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_queue_redis, get_cache_redis
from utils.circuit_breaker import can_attempt, record_success, record_failure
from utils.feature_flags import is_enabled
from utils.redis_resilience import (
    safe_delete,
    safe_expire,
    safe_get,
    safe_incr,
    safe_set,
    safe_setex,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
MAX_DELIVERY_COUNT = 5  # Poison pill threshold
PUBLISH_LIGHT_QUEUE = "publish_light"
PUBLISH_VIDEO_QUEUE = "publish_video"
_PUBLISH_LOCK_TTL_SECONDS = int(os.getenv("PUBLISH_LOCK_TTL_SECONDS", "14400"))
_PRE_UPLOAD_LOCK_TTL_SECONDS = int(os.getenv("PRE_UPLOAD_LOCK_TTL_SECONDS", "14400"))

# ── Per-platform concurrent API call limits (cross-process via Redis) ─────────
# Prevents app-level quota exhaustion when 1000 posts hit a platform simultaneously.
# Each value = max number of concurrent HTTP calls to that platform API at any time.
_PLATFORM_CONCURRENCY: dict[str, int] = {
    "instagram": 10,
    "tiktok":    10,
    "youtube":    5,   # stricter — YouTube upload API is more sensitive
    "twitter":   20,
    "facebook":  15,
    "linkedin":  10,
    "pinterest": 10,
}
_PLATFORM_SLOT_TTL = 60  # safety TTL in seconds — clears leaked slots on worker crash


def _is_video_like(post_type: str | None) -> bool:
    normalized = str(post_type or "").lower()
    return normalized in {"video", "reel", "story"} or "video" in normalized


def _publish_queue_for(platform: str, post: dict) -> str:
    """
    Route heavy media publishes away from light text/image work so one burst of
    large uploads does not starve every other platform publish.
    """
    if platform == "tiktok":
        return PUBLISH_VIDEO_QUEUE
    if platform == "youtube":
        return PUBLISH_VIDEO_QUEUE
    if _is_video_like(post.get("post_type")):
        return PUBLISH_VIDEO_QUEUE
    return PUBLISH_LIGHT_QUEUE


def _publish_lock_key(post_id: str, platform: str) -> str:
    return f"publish_lock:{post_id}:{platform}"


def _pre_upload_lock_key(post_id: str, platform: str) -> str:
    return f"pre_upload_lock:{post_id}:{platform}"


async def _acquire_publish_lock(redis, post_id: str, platform: str, owner_token: str) -> bool:
    key = _publish_lock_key(post_id, platform)
    acquired = await safe_set(
        redis,
        key,
        owner_token,
        ex=_PUBLISH_LOCK_TTL_SECONDS,
        nx=True,
        default=None,
        feature="Publish in-flight lock acquisition",
    )
    return bool(acquired)


async def _acquire_pre_upload_lock(redis, post_id: str, platform: str, owner_token: str) -> bool:
    key = _pre_upload_lock_key(post_id, platform)
    acquired = await safe_set(
        redis,
        key,
        owner_token,
        ex=_PRE_UPLOAD_LOCK_TTL_SECONDS,
        nx=True,
        default=None,
        feature="Pre-upload in-flight lock acquisition",
    )
    return bool(acquired)


async def _release_publish_lock(redis, post_id: str, platform: str, owner_token: str) -> None:
    key = _publish_lock_key(post_id, platform)
    current = await safe_get(
        redis,
        key,
        default=None,
        feature="Publish in-flight lock read",
    )
    if current == owner_token:
        await safe_delete(
            redis,
            key,
            default=0,
            feature="Publish in-flight lock release",
        )


async def _release_pre_upload_lock(redis, post_id: str, platform: str, owner_token: str) -> None:
    key = _pre_upload_lock_key(post_id, platform)
    current = await safe_get(
        redis,
        key,
        default=None,
        feature="Pre-upload in-flight lock read",
    )
    if current == owner_token:
        await safe_delete(
            redis,
            key,
            default=0,
            feature="Pre-upload in-flight lock release",
        )


def _run_async(coro):
    """
    Run async publishing code from Celery's prefork worker process.

    Python 3.11 no longer creates a default event loop automatically for
    synchronous worker tasks. Keep one loop per worker process so async clients
    such as Motor are not rebound to a new loop on every task.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


async def _acquire_platform_slot(redis, platform: str) -> bool:
    """
    Atomically increment the per-platform concurrent call counter in Redis.
    Returns True if a slot was acquired, False if the platform is at capacity.
    Uses MULTI/EXEC pipeline (transaction=True) so INCR and EXPIRE are atomic —
    if Redis crashes between them the key will not exist without a TTL.
    """
    limit = _PLATFORM_CONCURRENCY.get(platform, 15)
    key = f"pub_slots:{platform}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            await pipe.incr(key)
            await pipe.expire(key, _PLATFORM_SLOT_TTL)
            results = await pipe.execute()
        current = int(results[0])
        if current > limit:
            await redis.decr(key)
            return False
        return True
    except RedisError as exc:
        logger.warning(
            "Platform slot control degraded for %s because cache Redis is unavailable: %s",
            platform,
            exc,
        )
        return True


async def _release_platform_slot(redis, platform: str) -> None:
    """Release a previously acquired platform slot."""
    key = f"pub_slots:{platform}"
    try:
        val = await redis.decr(key)
        if val < 0:
            await redis.set(key, 0)  # guard against going negative on restart
    except RedisError as exc:
        logger.warning("Platform slot release degraded for %s: %s", platform, exc)


# ── Poison pill guard (Phase 7.3) ────────────────────────────────────────────
async def _check_poison_pill(task_id: str) -> bool:
    """Returns True if this task has been delivered too many times → DLQ."""
    r = get_queue_redis()
    key = f"delivery_count:{task_id}"
    count = await safe_incr(r, key, default=1, feature="Publish poison-pill counter")
    await safe_expire(r, key, 86400, default=True, feature="Publish poison-pill TTL")  # 24-hour TTL
    return int(count) > MAX_DELIVERY_COUNT


# ── Jitter helper (Phase 1.6) ─────────────────────────────────────────────────
# Jitter spreads platform API calls to avoid thundering herd, but must stay
# small so the gap between scheduled time and actual publish time is minimal.
def _jitter_seconds(post_type: str) -> int:
    if "video" in post_type:
        return random.randint(0, 30)   # was 300 — 5 min delay unacceptable for users
    elif post_type == "text":
        return random.randint(0, 10)   # was 30
    return random.randint(0, 15)       # was 60


# ── Aggregate status logic (Phase 1.6.3) ─────────────────────────────────────
def recompute_aggregate_status(platform_results: dict) -> str:
    statuses = {v.get("status") for v in platform_results.values()}
    if not statuses:
        return "scheduled"
    normalized = {
        "failed" if status in {"failed", "permanently_failed", "paused"} else status
        for status in statuses
    }
    if normalized == {"cancelled"}:
        return "cancelled"
    if normalized == {"published"}:
        return "published"
    if normalized == {"failed"}:
        return "failed"
    if normalized & {"processing", "retrying", "queued", "pending"}:
        return "processing"
    terminal = {"published", "failed", "cancelled"}
    if normalized.issubset(terminal) and "published" in normalized:
        return "partial"
    if normalized.issubset(terminal):
        return "failed"
    return "processing"


# ── Media cleanup gate (Phase 2.6.1 / Section 18.9) ──────────────────────────
def should_cleanup_media(platform_results: dict) -> bool:
    """Only delete source media when ALL platforms are in terminal state."""
    terminal = {"published", "failed", "permanently_failed", "cancelled"}
    return all(v.get("status") in terminal for v in platform_results.values())


async def _finalize_post_status(db, post_id: str) -> tuple[str | None, str | None, str]:
    from celery_workers.tasks.cleanup import prune_recent_published_posts, schedule_media_cleanup

    updated_post = await db.posts.find_one(
        {"id": post_id},
        {"platform_results": 1, "status": 1, "user_id": 1, "workspace_id": 1},
    )
    if not updated_post:
        return None, None, "scheduled"

    prev_agg_status = updated_post.get("status")
    agg_status = recompute_aggregate_status(updated_post.get("platform_results", {}))
    now = datetime.now(timezone.utc)

    set_updates = {"status": agg_status}
    if agg_status != "failed":
        set_updates["dlq_reason"] = None
    if agg_status == "published" and prev_agg_status != "published":
        set_updates["published_at"] = now

    await db.posts.update_one({"id": post_id}, {"$set": set_updates})

    if agg_status == "published" and prev_agg_status != "published":
        await prune_recent_published_posts(
            db,
            user_id=updated_post.get("user_id"),
            workspace_id=updated_post.get("workspace_id"),
            keep=25,
        )

    if should_cleanup_media(updated_post.get("platform_results", {})):
        schedule_media_cleanup.apply_async(
            kwargs={"post_id": post_id},
            countdown=300,
            queue="default",
        )

    return updated_post.get("user_id"), prev_agg_status, agg_status


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
    return _run_async(_async_publish_post(self, post_id, version))


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

    # Apply jitter — use Celery countdown instead of blocking time.sleep (LB-2)
    post_type = post.get("post_type", "image")
    jitter = _jitter_seconds(post_type)

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
    # countdown=jitter delays children without blocking the worker thread
    platforms = post.get("platforms", [])
    platform_tasks = group(
        publish_to_platform.s(post_id=post_id, platform=p, attempt=0).set(
            queue=_publish_queue_for(p, post)
        )
        for p in platforms
    )
    platform_tasks.apply_async(countdown=jitter)

    return {"status": "dispatched", "platforms": platforms, "jitter_seconds": jitter}


# 17.4B: max seconds to wait for pre_upload to become ready at publish time
_PRE_UPLOAD_POLL_INTERVAL = 5   # seconds between status checks
_PRE_UPLOAD_MAX_WAIT = 600      # 10 minutes maximum


async def _hydrate_post_media(db, post: dict) -> dict:
    media_ids = post.get("media_ids") or []
    if not media_ids:
        return post

    if post.get("media_url") and post.get("media_urls"):
        return post

    docs = await db.media_assets.find(
        {"media_id": {"$in": media_ids}},
        {"_id": 0, "media_id": 1, "media_url": 1, "thumbnail_url": 1, "file_size_bytes": 1},
    ).to_list(len(media_ids))
    by_id = {doc.get("media_id"): doc for doc in docs}
    ordered = [by_id[media_id] for media_id in media_ids if media_id in by_id]

    media_urls = [doc.get("media_url") for doc in ordered if doc.get("media_url")]
    thumbnail_urls = [
        doc.get("thumbnail_url") or doc.get("media_url")
        for doc in ordered
        if doc.get("thumbnail_url") or doc.get("media_url")
    ]
    file_size_bytes = next(
        (doc.get("file_size_bytes") for doc in ordered if doc.get("file_size_bytes")),
        None,
    )
    video_size_mb = post.get("video_size_mb")
    if file_size_bytes and not video_size_mb:
        video_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    return {
        **post,
        "media_urls": post.get("media_urls") or media_urls,
        "media_url": post.get("media_url") or (media_urls[0] if media_urls else None),
        "thumbnail_urls": post.get("thumbnail_urls") or thumbnail_urls,
        "video_size_mb": video_size_mb,
    }


def _normalize_account_doc(account_doc: dict | None) -> dict | None:
    if not account_doc:
        return None
    if account_doc.get("id"):
        return account_doc
    return {
        **account_doc,
        "id": account_doc.get("account_id") or account_doc.get("id"),
    }


def _requires_pre_upload(platform: str, post: dict) -> bool:
    post_type = str(post.get("post_type") or "").lower()
    has_media = bool(post.get("media_url") or post.get("media_urls"))

    if platform == "instagram":
        return has_media and post_type != "text"

    if platform == "youtube":
        return post_type in {"video", "reel", "story"} or "video" in post_type

    return False


def _pre_upload_result_path(platform: str, field: str) -> str:
    return f"pre_upload_results.{platform}.{field}"


def _get_platform_pre_upload_state(post: dict, platform: str) -> dict:
    return ((post.get("pre_upload_results") or {}).get(platform) or {})


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


def _get_platform_pre_upload_status(post: dict, platform: str) -> str | None:
    state = _get_platform_pre_upload_state(post, platform)
    return state.get("status") or post.get("pre_upload_status")


def _get_platform_pre_upload_error(post: dict, platform: str) -> str | None:
    state = _get_platform_pre_upload_state(post, platform)
    return state.get("error") or post.get("pre_upload_error")


def _get_platform_pre_upload_started_at(post: dict, platform: str):
    state = _get_platform_pre_upload_state(post, platform)
    return _coerce_utc_datetime(state.get("started_at") or post.get("pre_upload_started_at"))


def _get_platform_pre_upload_completed_at(post: dict, platform: str):
    state = _get_platform_pre_upload_state(post, platform)
    return _coerce_utc_datetime(state.get("completed_at") or post.get("pre_upload_completed_at"))


def _pre_upload_platforms_for(post: dict) -> list[str]:
    selected = post.get("platforms") or []
    required = [platform for platform in selected if _requires_pre_upload(platform, post)]
    result_keys = list((post.get("pre_upload_results") or {}).keys())
    return list(dict.fromkeys(required + result_keys))


async def _sync_pre_upload_aggregate(db, post_id: str) -> None:
    post = await db.posts.find_one(
        {"id": post_id},
        {
            "_id": 0,
            "platforms": 1,
            "post_type": 1,
            "pre_upload_results": 1,
        },
    )
    if not post:
        return

    platforms = _pre_upload_platforms_for(post)
    results = post.get("pre_upload_results") or {}

    statuses: list[str] = []
    errors: list[str] = []
    start_times = []
    started_ats = []
    completed_ats = []
    estimated_durations = []
    actual_durations = []

    for platform in platforms:
        state = results.get(platform) or {}
        status = state.get("status")
        if status:
            statuses.append(status)
        error = state.get("error")
        if error:
            errors.append(f"{platform}: {error}")
        if state.get("start_time"):
            start_times.append(state["start_time"])
        if state.get("started_at"):
            started_ats.append(state["started_at"])
        if state.get("completed_at"):
            completed_ats.append(state["completed_at"])
        if state.get("estimated_duration_secs") is not None:
            estimated_durations.append(state["estimated_duration_secs"])
        if state.get("actual_duration_secs") is not None:
            actual_durations.append(state["actual_duration_secs"])

    aggregate_status = None
    if "failed" in statuses:
        aggregate_status = "failed"
    elif "timeout" in statuses:
        aggregate_status = "timeout"
    elif "uploading" in statuses:
        aggregate_status = "uploading"
    elif "pending" in statuses:
        aggregate_status = "pending"
    elif statuses and all(status == "ready" for status in statuses):
        aggregate_status = "ready"

    set_updates: dict[str, object] = {}
    unset_updates: dict[str, str] = {}

    if aggregate_status:
        set_updates["pre_upload_status"] = aggregate_status
    else:
        unset_updates["pre_upload_status"] = ""

    if errors and aggregate_status in {"failed", "timeout"}:
        set_updates["pre_upload_error"] = " | ".join(errors)
    else:
        unset_updates["pre_upload_error"] = ""

    if start_times:
        set_updates["pre_upload_start_time"] = min(start_times)
    else:
        unset_updates["pre_upload_start_time"] = ""

    if started_ats:
        set_updates["pre_upload_started_at"] = min(started_ats)
    else:
        unset_updates["pre_upload_started_at"] = ""

    if completed_ats:
        set_updates["pre_upload_completed_at"] = max(completed_ats)
    else:
        unset_updates["pre_upload_completed_at"] = ""

    if estimated_durations:
        set_updates["estimated_upload_duration"] = max(estimated_durations)
    else:
        unset_updates["estimated_upload_duration"] = ""

    if actual_durations:
        set_updates["actual_upload_duration"] = max(actual_durations)
    else:
        unset_updates["actual_upload_duration"] = ""

    update_doc: dict[str, dict] = {}
    if set_updates:
        update_doc["$set"] = set_updates
    if unset_updates:
        update_doc["$unset"] = unset_updates

    if update_doc:
        await db.posts.update_one({"id": post_id}, update_doc)


async def _resolve_post_account(db, post: dict, platform: str) -> dict | None:
    selected_ids = post.get("social_account_ids") or post.get("account_ids") or []
    if selected_ids:
        account_doc = await db.social_accounts.find_one({
            "user_id": post.get("user_id"),
            "platform": platform,
            "is_active": True,
            "$or": [
                {"account_id": {"$in": selected_ids}},
                {"id": {"$in": selected_ids}},
            ],
        })
        if not account_doc:
            logger.warning(
                "Selected account resolution failed for post %s platform %s with ids=%s",
                post.get("id"),
                platform,
                selected_ids,
            )
            return None
        return _normalize_account_doc(account_doc)

    account_doc = await db.social_accounts.find_one({
            "user_id": post.get("user_id"),
            "platform": platform,
            "is_active": True,
        })
    return _normalize_account_doc(account_doc)


# ── Per-platform task ─────────────────────────────────────────────────────────
@celery_app.task(
    name="celery_workers.tasks.publish.publish_to_platform",
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def publish_to_platform(self, post_id: str, platform: str, attempt: int = 0) -> dict:
    return _run_async(_async_publish_to_platform(self, post_id, platform, attempt))


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
            await _finalize_post_status(db, post_id)
            return {"status": "feature_disabled", "platform": platform}
    except ImportError:
        pass

    # 20.5: Per-platform poison pill guard — each platform has its own delivery counter
    r_queue = get_queue_redis()
    pp_key = f"delivery_count:{task.request.id}:{platform}"
    pp_count = await safe_incr(r_queue, pp_key, default=1, feature="Per-platform poison-pill counter")
    await safe_expire(r_queue, pp_key, 86400, default=True, feature="Per-platform poison-pill TTL")
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
    cached = await safe_get(r_cache, confirm_key, default=None, feature="Publish confirmation cache read")
    if cached:
        logger.info("Platform %s/%s already confirmed in Redis — skipping API call", post_id, platform)
        return {"status": "already_confirmed"}

    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if post is None:
        return {"status": "post_deleted"}
    post = await _hydrate_post_media(db, post)

    publish_queue = _publish_queue_for(platform, post)
    lock_owner = task.request.id or f"{post_id}:{platform}:{attempt}"
    lock_acquired = await _acquire_publish_lock(r_cache, post_id, platform, lock_owner)
    if not lock_acquired:
        logger.info(
            "Publish already in-flight for %s/%s — re-enqueuing after short backoff",
            post_id,
            platform,
        )
        publish_to_platform.apply_async(
            kwargs={"post_id": post_id, "platform": platform, "attempt": attempt},
            countdown=random.randint(20, 40),
            queue=publish_queue,
        )
        return {"status": "already_inflight_requeued", "platform": platform}

    try:
        # Bootstrap pre-upload for platforms that require a prepared container/video_id
        # before publish. This is critical for immediate "post now" flows because they do
        # not always pass through the scheduled pre-upload window first.
        if _requires_pre_upload(platform, post):
            container_ids = post.get("platform_container_ids") or {}
            pre_status = _get_platform_pre_upload_status(post, platform) or ""
            has_container = bool(container_ids.get(platform))

            if not has_container or pre_status in ("", None):
                logger.info(
                    "Bootstrapping pre-upload for %s/%s (post_type=%s, has_container=%s, pre_status=%r)",
                    post_id,
                    platform,
                    post.get("post_type"),
                    has_container,
                    pre_status,
                )
                pre_result = await _async_pre_upload(task, post_id, platform)
                if pre_result.get("status") == "polling":
                    await _update_platform_result(db, post_id, platform, {
                        "status": "retrying",
                        "error": f"{platform} media container is still processing",
                        "last_attempt_at": datetime.now(timezone.utc),
                    })
                    raise task.retry(
                        countdown=_PRE_UPLOAD_POLL_INTERVAL,
                        exc=Exception(f"{platform} pre_upload still processing"),
                        kwargs={"post_id": post_id, "platform": platform, "attempt": attempt},
                    )

                post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                if post is None:
                    return {"status": "post_deleted"}
                post = await _hydrate_post_media(db, post)

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
                await _finalize_post_status(db, post_id)
                return {"status": "subscription_expired"}
        except ImportError:
            pass

        # 17.4 Scenario B: pre_upload still running at scheduled publish time.
        # Poll every 5s for up to 10 minutes before giving up.
        if _requires_pre_upload(platform, post):
            pre_status = _get_platform_pre_upload_status(post, platform) or ""
            if pre_status == "failed":
                err = _get_platform_pre_upload_error(post, platform) or "Pre-upload failed before publish time"
                logger.error("17.4C: pre_upload failed for %s/%s — %s", post_id, platform, err)
                await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err})
                await _finalize_post_status(db, post_id)
                await _send_failure_notification(db, post_id, platform, err)
                return {"status": "failed", "reason": "pre_upload_failed"}

            if pre_status not in ("ready", "", None):
                waited = 0
                logger.info(
                    "17.4B: pre_upload still %r at publish time for %s/%s — polling up to %ds",
                    pre_status, post_id, platform, _PRE_UPLOAD_MAX_WAIT,
                )
                while waited < _PRE_UPLOAD_MAX_WAIT:
                    await asyncio.sleep(_PRE_UPLOAD_POLL_INTERVAL)
                    waited += _PRE_UPLOAD_POLL_INTERVAL
                    await safe_expire(
                        r_cache,
                        _publish_lock_key(post_id, platform),
                        _PUBLISH_LOCK_TTL_SECONDS,
                        default=True,
                        feature="Publish in-flight lock heartbeat",
                    )
                    refreshed = await db.posts.find_one(
                        {"id": post_id},
                        {
                            "_id": 0,
                            "pre_upload_status": 1,
                            "pre_upload_error": 1,
                            f"pre_upload_results.{platform}": 1,
                        },
                    )
                    current_status = _get_platform_pre_upload_status(refreshed or {}, platform) or ""
                    if current_status == "ready":
                        logger.info(
                            "17.4B: pre_upload ready after %ds for %s/%s",
                            waited, post_id, platform,
                        )
                        post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                        break
                    if current_status == "failed":
                        err = _get_platform_pre_upload_error(refreshed or {}, platform) or "Pre-upload failed"
                        logger.error("17.4B: pre_upload failed while polling %s/%s — %s", post_id, platform, err)
                        await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err})
                        await _finalize_post_status(db, post_id)
                        await _send_failure_notification(db, post_id, platform, err)
                        return {"status": "failed", "reason": "pre_upload_failed"}
                else:
                    msg = (
                        f"Timed out waiting for pre_upload on {platform} "
                        f"(waited {_PRE_UPLOAD_MAX_WAIT}s). "
                        f"Post published {waited}s late."
                    )
                    logger.error("17.4B: %s for post %s", msg, post_id)
                    await _update_platform_result(db, post_id, platform, {"status": "failed", "error": msg})
                    await _finalize_post_status(db, post_id)
                    await _send_failure_notification(db, post_id, platform, msg)
                    return {"status": "failed", "reason": "pre_upload_wait_timeout"}
                post = await _hydrate_post_media(db, post)

        account_id: str | None = None
        try:
            from utils.encryption import decrypt
            account_doc = await _resolve_post_account(db, post, platform)
            if account_doc and account_doc.get("access_token"):
                account_id = account_doc.get("account_id") or account_doc.get("id")
                post = {**post, "access_token": decrypt(account_doc["access_token"]), "account": account_doc}
        except Exception as _token_err:
            logger.warning("Could not inject access token for %s/%s: %s", post_id, platform, _token_err)

        try:
            cb_open = await can_attempt(r_cache, platform, account_id)
            if not cb_open:
                logger.warning("Circuit OPEN for %s/%s — skipping platform call for post %s", platform, account_id, post_id)
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "error": f"Circuit breaker OPEN for {platform} — will retry when circuit closes",
                    "next_retry_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                })
                raise task.retry(countdown=300, exc=Exception(f"Circuit OPEN: {platform}"))

            _override = (post.get("platform_overrides") or {}).get(platform) or {}
            _use_media_override = _override.get("use_media_override")
            if _use_media_override is True:
                _override_media_ids = _override.get("media_ids") or []
                _override_media_urls = _override.get("media_urls") or []
                _override_media_url = _override.get("media_url")
                _override_thumbnails = _override.get("thumbnail_urls") or []
            else:
                _override_media_ids = post.get("media_ids") or []
                _override_media_urls = post.get("media_urls") or []
                _override_media_url = post.get("media_url")
                _override_thumbnails = post.get("thumbnail_urls") or []
            post = {
                **post,
                "effective_content": _override.get("content") or post.get("content", ""),
                "effective_title": _override.get("title") or post.get("title", ""),
                "media_ids": _override_media_ids,
                "media_urls": _override_media_urls,
                "media_url": _override_media_url or (_override_media_urls[0] if _override_media_urls else None),
                "thumbnail_urls": _override_thumbnails,
            }

            adapter = get_adapter(platform)

            _slot_acquired = await _acquire_platform_slot(r_cache, platform)
            if not _slot_acquired:
                _backoff = random.randint(8, 15)
                logger.info(
                    "Platform %s at capacity — re-enqueuing post %s after %ds backoff",
                    platform, post_id, _backoff,
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "error": f"Platform {platform} throttled — too many concurrent calls",
                    "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=_backoff),
                })
                publish_to_platform.apply_async(
                    kwargs={"post_id": post_id, "platform": platform, "attempt": attempt},
                    countdown=_backoff,
                    queue=publish_queue,
                )
                return {"status": "throttled_requeued", "platform": platform}

            try:
                result = await adapter.publish(post, redis=r_cache)
            finally:
                await _release_platform_slot(r_cache, platform)

            try:
                from utils.circuit_breaker import record_success
                await record_success(r_cache, platform)
            except ImportError:
                pass

            post_url = result.get("post_url")
            platform_post_id = result.get("platform_post_id")

            import json
            confirmation_payload = {
                "post_url": post_url,
                "platform_post_id": platform_post_id,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
            await safe_setex(
                r_cache,
                confirm_key,
                86400,
                json.dumps(confirmation_payload),
                default=True,
                feature="Publish confirmation cache write",
            )

            await record_success(r_cache, platform, account_id)

            await _update_platform_result(db, post_id, platform, {
                "status": "published",
                "post_url": post_url,
                "platform_post_id": platform_post_id,
                "published_at": datetime.now(timezone.utc),
            })
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$unset": {
                        f"platform_results.{platform}.error": "",
                        f"platform_results.{platform}.next_retry_at": "",
                        f"platform_results.{platform}.dlq_reason": "",
                    }
                },
            )

            user_id, prev_agg_status, agg_status = await _finalize_post_status(db, post_id)
            await _send_success_notification(db, post_id, platform, post_url or "", user_id or "")
            if agg_status == "published" and prev_agg_status == "partial":
                await _send_recovery_notification(db, post_id, user_id or "")

            return {"status": "published", "platform": platform}

        except Exception as exc:
            from platform_adapters.base import classify_error, ErrorClass, PlatformHTTPError

            if "container expired" in str(exc).lower() and platform == "instagram":
                logger.warning("Instagram container expired for %s — clearing and re-queuing pre_upload", post_id)
                await db.posts.update_one(
                    {"id": post_id},
                    {
                        "$unset": {
                            f"platform_container_ids.{platform}": "",
                            f"container_expiry_at.{platform}": "",
                            _pre_upload_result_path(platform, "error"): "",
                            _pre_upload_result_path(platform, "completed_at"): "",
                            _pre_upload_result_path(platform, "actual_duration_secs"): "",
                        },
                        "$set": {
                            _pre_upload_result_path(platform, "status"): "pending",
                            _pre_upload_result_path(platform, "started_at"): None,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    },
                )
                await _sync_pre_upload_aggregate(db, post_id)
                pre_upload_task.apply_async(
                    kwargs={"post_id": post_id, "platform": platform},
                    queue="media_processing",
                    countdown=5,
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "error": "Container expired — re-uploading media",
                    "last_attempt_at": datetime.now(timezone.utc),
                })
                return {"status": "container_expired_requeued"}

            error_class = classify_error(exc)

            if error_class == ErrorClass.PERMANENT:
                logger.error("Permanent error publishing %s/%s: %s", post_id, platform, exc)
                await _update_platform_result(db, post_id, platform, {
                    "status": "failed",
                    "error": str(exc),
                    "retry_count": attempt,
                    "last_attempt_at": datetime.now(timezone.utc),
                })

                error_code = getattr(exc, "code", None)
                subcode = getattr(exc, "subcode", None)
                is_auth_error = (
                    (isinstance(exc, PlatformHTTPError) and getattr(exc, "status_code", 0) in (401, 403))
                    or subcode in {458, 460}
                    or error_code in (190, 261, 326)
                )
                if is_auth_error:
                    try:
                        from celery_workers.tasks.tokens import _refresh_with_lock
                        _acct = post.get("account", {})
                        _acct_id = _acct.get("account_id", _acct.get("id", ""))
                        if _acct_id and attempt == 0:
                            logger.info(
                                "Auth error on %s/%s — attempting on-demand token refresh for account %s",
                                post_id, platform, _acct_id,
                            )
                            await _refresh_with_lock(db, _acct_id, platform)
                            logger.info("Token refreshed for %s — re-enqueuing post %s", _acct_id, post_id)
                            publish_to_platform.apply_async(
                                kwargs={"post_id": post_id, "platform": platform, "attempt": attempt + 1},
                                countdown=5,
                                queue=publish_queue,
                            )
                            return {"status": "token_refreshed_requeued"}
                    except Exception as _refresh_err:
                        logger.warning("On-demand token refresh failed for %s: %s", post_id, _refresh_err)

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

                await record_failure(r_cache, platform, account_id)
                await _finalize_post_status(db, post_id)
                await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
                return {"status": "permanent_failure"}

            if error_class == ErrorClass.RATE_LIMITED:
                retry_after = getattr(exc, "retry_after", 3600)
                logger.warning("Rate limited on %s/%s — re-queuing after %ds", post_id, platform, retry_after)
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=retry_after),
                })
                raise task.retry(countdown=retry_after, exc=exc)

            countdown_map = {0: 60, 1: 300, 2: 900}
            jitter = random.randint(0, [30, 60, 120][min(attempt, 2)])
            countdown = countdown_map.get(attempt, 900) + jitter

            if attempt >= MAX_RETRIES:
                logger.error("Max retries exceeded for %s/%s — DLQ", post_id, platform)
                await record_failure(r_cache, platform, account_id)
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
    finally:
        await _release_publish_lock(r_cache, post_id, platform, lock_owner)


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
_DEFAULT_PRE_UPLOAD_SECS = 1800  # 30-minute fallback when file_size unknown


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
    return _run_async(_async_pre_upload(self, post_id, platform))


async def _async_pre_upload(task, post_id: str, platform: str) -> dict:
    from platform_adapters import get_adapter

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    r_cache = get_cache_redis()

    started_at = datetime.now(timezone.utc)
    lock_owner = task.request.id or f"{post_id}:{platform}:preupload"
    lock_acquired = await _acquire_pre_upload_lock(r_cache, post_id, platform, lock_owner)
    if not lock_acquired:
        logger.info("Pre-upload already in-flight for %s/%s — skipping duplicate dispatch", post_id, platform)
        return {"status": "already_inflight", "platform": platform}

    await db.posts.update_one(
        {"id": post_id},
        {
            "$set": {
                _pre_upload_result_path(platform, "status"): "uploading",
                _pre_upload_result_path(platform, "started_at"): started_at,
                "updated_at": started_at,
            },
            "$unset": {
                _pre_upload_result_path(platform, "error"): "",
                _pre_upload_result_path(platform, "completed_at"): "",
                _pre_upload_result_path(platform, "actual_duration_secs"): "",
            },
        },
    )
    await _sync_pre_upload_aggregate(db, post_id)

    try:
        adapter = get_adapter(platform)
        post = await db.posts.find_one({"id": post_id}, {"_id": 0})
        if not post:
            return {"status": "post_deleted"}
        post = await _hydrate_post_media(db, post)
        account_doc = await _resolve_post_account(db, post, platform)
        if account_doc:
            post = {**post, "account": account_doc}
        # EC-1: Post deleted or cancelled before pre_upload executed — abort cleanly
        if not post or post.get("status") in {"deleted", "cancelled"}:
            logger.info("pre_upload EC-1: post %s deleted/cancelled before pre_upload — aborting", post_id)
            return {"status": "post_deleted"}
        # Inject per-platform text overrides for pre_upload (YouTube uses title/content in metadata)
        _override = (post.get("platform_overrides") or {}).get(platform) or {}
        _use_media_override = _override.get("use_media_override")
        if _use_media_override is True:
            _override_media_ids = _override.get("media_ids") or []
            _override_media_urls = _override.get("media_urls") or []
            _override_media_url = _override.get("media_url")
            _override_thumbnails = _override.get("thumbnail_urls") or []
        else:
            _override_media_ids = post.get("media_ids") or []
            _override_media_urls = post.get("media_urls") or []
            _override_media_url = post.get("media_url")
            _override_thumbnails = post.get("thumbnail_urls") or []
        post = {
            **post,
            "effective_content": _override.get("content") or post.get("content", ""),
            "effective_title": _override.get("title") or post.get("title", ""),
            "media_ids": _override_media_ids,
            "media_urls": _override_media_urls,
            "media_url": _override_media_url or (_override_media_urls[0] if _override_media_urls else None),
            "thumbnail_urls": _override_thumbnails,
        }
        container_result = await adapter.pre_upload(post, redis=r_cache)

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
                queue="media_processing",
            )
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$set": {
                        _pre_upload_result_path(platform, "status"): "uploading",
                        _pre_upload_result_path(platform, "started_at"): started_at,
                        f"platform_container_ids.{platform}": container_id,
                        "updated_at": datetime.now(timezone.utc),
                    }
                }
            )
            await _sync_pre_upload_aggregate(db, post_id)
            return {"status": "polling", "platform": platform, "container_id": container_id}

        completed_at = datetime.now(timezone.utc)
        actual_duration = int((completed_at - started_at).total_seconds())
        expiry = completed_at + timedelta(hours=23)
        container_id = container_result.get("container_id") or container_result.get("video_id")
        await db.posts.update_one(
            {"id": post_id},
            {
                "$set": {
                    _pre_upload_result_path(platform, "status"): "ready",
                    _pre_upload_result_path(platform, "started_at"): started_at,
                    _pre_upload_result_path(platform, "completed_at"): completed_at,
                    _pre_upload_result_path(platform, "actual_duration_secs"): actual_duration,
                    f"platform_container_ids.{platform}": container_id,
                    f"container_expiry_at.{platform}": expiry.isoformat(),
                    "updated_at": completed_at,
                },
                "$unset": {
                    _pre_upload_result_path(platform, "error"): "",
                },
            }
        )
        await _sync_pre_upload_aggregate(db, post_id)
        logger.info(
            "17.3: pre_upload ready for %s/%s — actual_duration=%ds container=%s",
            post_id, platform, actual_duration, container_id,
        )
        return {"status": "ready", "platform": platform, "actual_duration_secs": actual_duration}

    except Exception as exc:
        logger.error("pre_upload_task failed for %s/%s: %s", post_id, platform, exc)
        await db.posts.update_one(
            {"id": post_id},
            {
                "$set": {
                    _pre_upload_result_path(platform, "status"): "failed",
                    _pre_upload_result_path(platform, "error"): str(exc),
                    _pre_upload_result_path(platform, "completed_at"): datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            }
        )
        await _sync_pre_upload_aggregate(db, post_id)
        raise task.retry(countdown=60, exc=exc)
    finally:
        await _release_pre_upload_lock(r_cache, post_id, platform, lock_owner)


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
    update: dict = {"dlq_reason": reason}
    if platform:
        update[f"platform_results.{platform}.status"] = "permanently_failed"
        update[f"platform_results.{platform}.error"] = reason
        update[f"platform_results.{platform}.dlq_reason"] = reason
    else:
        update["status"] = "failed"
    post = await db.posts.find_one_and_update(
        {"id": post_id},
        {"$set": update},
        return_document=True,
        projection={"user_id": 1},
    )

    # Write to dead_letter_queue so admin GET /admin/dlq can surface these items
    import uuid
    dlq_doc: dict = {
        "task_id": str(uuid.uuid4()),
        "post_id": post_id,
        "user_id": post.get("user_id", "") if post else "",
        "reason": reason,
        "platform": platform,
        "failed_at": datetime.now(timezone.utc),
        "retry_count": 0,
        "payload": {"task_name": "celery_workers.tasks.publish.publish_post", "args": [post_id]},
    }
    try:
        await db.dead_letter_queue.insert_one(dlq_doc)
    except Exception as dlq_err:
        logger.error("Failed to write DLQ record for post %s: %s", post_id, dlq_err)

    if platform:
        try:
            await _finalize_post_status(db, post_id)
        except Exception as finalize_err:
            logger.warning("DLQ: failed to finalize aggregate status for %s: %s", post_id, finalize_err)

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
