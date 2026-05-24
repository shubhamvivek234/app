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
import io
from datetime import datetime, timedelta, timezone

from redis.exceptions import RedisError
from platform_adapters.base import PlatformError, PlatformHTTPError
from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_queue_redis, get_cache_redis
from utils.circuit_breaker import can_attempt, record_success, record_failure
from utils.feature_flags import is_enabled
from utils.observability import capture_degraded_event, event_log, rate_limited_event_log, shorten_provider_error
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
_PUBLISH_VIDEO_FALLBACK_DELAY_SECONDS = int(os.getenv("PUBLISH_VIDEO_FALLBACK_DELAY_SECONDS", "60"))
_PUBLISH_LOCK_TTL_SECONDS = int(os.getenv("PUBLISH_LOCK_TTL_SECONDS", "14400"))
_PUBLISH_LOCK_STALE_SECONDS = int(os.getenv("PUBLISH_LOCK_STALE_SECONDS", "90"))
_PRE_UPLOAD_LOCK_TTL_SECONDS = int(os.getenv("PRE_UPLOAD_LOCK_TTL_SECONDS", "14400"))
_PUBLISHED_CARD_THUMB_SIZE = (160, 160)
_PUBLISHED_CARD_THUMB_QUALITY = int(os.getenv("PUBLISHED_CARD_THUMB_QUALITY", "65"))

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
    "threads":   10,
}
_PLATFORM_SLOT_TTL = 60  # safety TTL in seconds — clears leaked slots on worker crash


def _is_video_like(post_type: str | None) -> bool:
    normalized = str(post_type or "").lower()
    return normalized in {"video", "reel", "story"} or "video" in normalized


def _is_scope_insufficient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "access_token_scope_insufficient" in text
        or "insufficient authentication scopes" in text
        or "insufficientpermissions" in text
    )


def _is_platform_suspension_error(platform: str, exc: Exception) -> bool:
    text = str(exc).lower()
    patterns = {
        "youtube": ("account suspended", "channel has been terminated", "suspended account"),
        "twitter": ("account suspended", "user is suspended", "account locked"),
        "linkedin": ("account restricted", "account suspended", "member account is suspended"),
        "tiktok": ("account banned", "account suspended", "account has been suspended"),
        "default": (
            "account suspended",
            "account banned",
            "account disabled",
            "account blocked",
            "account terminated",
        ),
    }
    return any(token in text for token in patterns.get(platform, patterns["default"]))


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


def _fallback_publish_queue_for(queue_name: str) -> str | None:
    if queue_name == PUBLISH_VIDEO_QUEUE:
        return "default"
    return None


def _result_target_key(platform: str, account_id: str | None = None) -> str:
    return account_id or platform


def _publish_lock_key(post_id: str, target_key: str) -> str:
    return f"publish_lock:{post_id}:{target_key}"


def _pre_upload_lock_key(post_id: str, target_key: str) -> str:
    return f"pre_upload_lock:{post_id}:{target_key}"


def _get_publish_targets(post: dict) -> list[dict]:
    targets = []
    for target in (post.get("publish_targets") or []):
        platform = str(target.get("platform") or "").strip().lower()
        account_id = str(target.get("account_id") or "").strip() or None
        if not platform:
            continue
        targets.append({
            "platform": platform,
            "account_id": account_id,
            "target_key": _result_target_key(platform, account_id),
        })

    if targets:
        return targets

    return [
        {
            "platform": platform,
            "account_id": None,
            "target_key": _result_target_key(platform, None),
        }
        for platform in (post.get("platforms") or [])
    ]


async def _acquire_publish_lock(redis, post_id: str, target_key: str, owner_token: str) -> bool:
    key = _publish_lock_key(post_id, target_key)
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


async def _acquire_pre_upload_lock(redis, post_id: str, target_key: str, owner_token: str) -> bool:
    key = _pre_upload_lock_key(post_id, target_key)
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


async def _release_publish_lock(redis, post_id: str, target_key: str, owner_token: str) -> None:
    key = _publish_lock_key(post_id, target_key)
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


async def _release_pre_upload_lock(redis, post_id: str, target_key: str, owner_token: str) -> None:
    key = _pre_upload_lock_key(post_id, target_key)
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
    return run_async(coro)


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


def _aggregate_platform_results(post: dict) -> dict:
    account_results = post.get("account_results") or {}
    if not account_results:
        return post.get("platform_results") or {}

    grouped: dict[str, dict] = {}
    for target in _get_publish_targets(post):
        platform = target["platform"]
        target_key = target["target_key"]
        grouped.setdefault(platform, {})[target_key] = account_results.get(target_key) or {"status": "pending"}

    aggregated: dict[str, dict] = {}
    for platform, results in grouped.items():
        published_at_values = [
            result.get("published_at")
            for result in results.values()
            if result.get("published_at")
        ]
        next_retry_values = [
            result.get("next_retry_at")
            for result in results.values()
            if result.get("next_retry_at")
        ]
        aggregated[platform] = {
            "status": recompute_aggregate_status(results),
            "error": next((result.get("error") for result in results.values() if result.get("error")), None),
            "retry_count": max((result.get("retry_count", 0) for result in results.values()), default=0),
            "last_attempt_at": next((result.get("last_attempt_at") for result in results.values() if result.get("last_attempt_at")), None),
            "next_retry_at": min(next_retry_values) if next_retry_values else None,
            "post_url": next((result.get("post_url") for result in results.values() if result.get("post_url")), None),
            "platform_post_id": next((result.get("platform_post_id") for result in results.values() if result.get("platform_post_id")), None),
            "published_at": max(published_at_values) if published_at_values else None,
        }
    return aggregated


def _terminal_results(post: dict) -> dict:
    account_results = post.get("account_results") or {}
    if account_results:
        return account_results
    return post.get("platform_results") or {}


# ── Media cleanup gate (Phase 2.6.1 / Section 18.9) ──────────────────────────
def should_cleanup_media(platform_results: dict) -> bool:
    """Only delete source media when ALL platforms are in terminal state."""
    terminal = {"published", "failed", "permanently_failed", "cancelled"}
    return all(v.get("status") in terminal for v in platform_results.values())


async def _finalize_post_status(db, post_id: str) -> tuple[str | None, str | None, str]:
    from celery_workers.tasks.cleanup import schedule_media_cleanup

    updated_post = await db.posts.find_one(
        {"id": post_id},
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "workspace_id": 1,
            "status": 1,
            "post_type": 1,
            "platform_results": 1,
            "account_results": 1,
            "publish_targets": 1,
            "media_ids": 1,
            "media_urls": 1,
            "media_url": 1,
            "thumbnail_urls": 1,
            "media_types": 1,
            "published_card_thumbnail_url": 1,
        },
    )
    if not updated_post:
        return None, None, "scheduled"

    prev_agg_status = updated_post.get("status")
    aggregated_platform_results = _aggregate_platform_results(updated_post)
    result_entries = updated_post.get("account_results") or aggregated_platform_results
    agg_status = recompute_aggregate_status(result_entries)
    now = datetime.now(timezone.utc)

    set_updates = {
        "status": agg_status,
        "platform_results": aggregated_platform_results,
    }
    if agg_status != "failed":
        set_updates["dlq_reason"] = None
    if agg_status == "published" and prev_agg_status != "published":
        set_updates["published_at"] = now
        hydrated_post = await _hydrate_post_media(db, updated_post)
        set_updates["published_media_kind"] = _derive_published_media_kind(hydrated_post)
        if not hydrated_post.get("published_card_thumbnail_url"):
            try:
                set_updates.update(await _generate_published_card_thumbnail(hydrated_post))
            except Exception as exc:
                logger.warning("Published card thumbnail generation failed for post %s: %s", post_id, exc)

    await db.posts.update_one({"id": post_id}, {"$set": set_updates})

    if should_cleanup_media(result_entries):
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
    if post.get("deleted_at") or post.get("status") == "cancelled":
        logger.info("Post %s cancelled before parent dispatch — aborting cleanly", post_id)
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

    processing_started_at = datetime.now(timezone.utc)

    # Update post with jitter info + processing status
    await db.posts.update_one(
        {"id": post_id},
        {
            "$set": {
                "status": "processing",
                "jitter_seconds": jitter,
                "processing_started_at": processing_started_at.isoformat(),
                "updated_at": processing_started_at,
            },
            "$push": {
                "status_history": {
                    "status": "processing",
                    "timestamp": processing_started_at,
                    "actor": "celery_publish_parent",
                }
            },
        },
    )

    # Spawn per-platform tasks explicitly instead of relying on a Celery group.
    # This gives us child task IDs for observability and avoids silent handoff
    # gaps where the parent ran but no platform task ever left a trace.
    targets = _get_publish_targets(post)
    dispatch_updates: dict[str, object] = {}
    dispatched_children: list[dict[str, str | None]] = []
    for target in targets:
        queue_name = _publish_queue_for(target["platform"], post)
        async_result = publish_to_platform.apply_async(
            kwargs={
                "post_id": post_id,
                "platform": target["platform"],
                "account_id": target["account_id"],
                "attempt": 0,
                "dispatch_source": "primary",
            },
            countdown=jitter,
            queue=queue_name,
        )
        event_log(
            logger,
            "info",
            "publish.platform.dispatched",
            task_name="publish_post",
            post_id=post_id,
            platform=target["platform"],
            account_id=target["account_id"],
            queue_name=queue_name,
            child_task_id=async_result.id,
            dispatch_source="primary",
            outcome="enqueued",
        )
        dispatch_updates[f"account_results.{target['target_key']}.dispatch_task_id"] = async_result.id
        dispatch_updates[f"account_results.{target['target_key']}.dispatch_enqueued_at"] = processing_started_at
        dispatch_updates[f"platform_results.{target['platform']}.dispatch_task_id"] = async_result.id
        dispatch_updates[f"platform_results.{target['platform']}.dispatch_enqueued_at"] = processing_started_at
        dispatched_children.append(
            {
                "target_key": target["target_key"],
                "platform": target["platform"],
                "account_id": target["account_id"],
                "queue": queue_name,
                "task_id": async_result.id,
            }
        )

        fallback_queue = _fallback_publish_queue_for(queue_name)
        if fallback_queue:
            fallback_countdown = jitter + _PUBLISH_VIDEO_FALLBACK_DELAY_SECONDS
            fallback_result = publish_to_platform.apply_async(
                kwargs={
                    "post_id": post_id,
                    "platform": target["platform"],
                    "account_id": target["account_id"],
                    "attempt": 0,
                    "dispatch_source": "fallback",
                },
                countdown=fallback_countdown,
                queue=fallback_queue,
            )
            event_log(
                logger,
                "info",
                "publish.platform.dispatched",
                task_name="publish_post",
                post_id=post_id,
                platform=target["platform"],
                account_id=target["account_id"],
                queue_name=fallback_queue,
                child_task_id=fallback_result.id,
                dispatch_source="fallback",
                outcome="enqueued",
            )
            dispatch_updates[f"account_results.{target['target_key']}.fallback_dispatch_task_id"] = fallback_result.id
            dispatch_updates[f"account_results.{target['target_key']}.fallback_dispatch_enqueued_at"] = processing_started_at
            dispatch_updates[f"account_results.{target['target_key']}.fallback_dispatch_countdown"] = fallback_countdown
            dispatch_updates[f"platform_results.{target['platform']}.fallback_dispatch_task_id"] = fallback_result.id
            dispatch_updates[f"platform_results.{target['platform']}.fallback_dispatch_enqueued_at"] = processing_started_at
            dispatch_updates[f"platform_results.{target['platform']}.fallback_dispatch_countdown"] = fallback_countdown

    if dispatch_updates:
        dispatch_updates["updated_at"] = processing_started_at
        await db.posts.update_one({"id": post_id}, {"$set": dispatch_updates})

    return {
        "status": "dispatched",
        "platforms": post.get("platforms", []),
        "targets": [target["target_key"] for target in targets],
        "jitter_seconds": jitter,
        "child_tasks": dispatched_children,
    }


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
        {"_id": 0, "media_id": 1, "media_url": 1, "thumbnail_url": 1, "file_size_bytes": 1, "mime_type": 1},
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
    media_types = [
        "video" if str(doc.get("mime_type") or "").startswith("video/") else "image"
        for doc in ordered
        if doc.get("media_url") or doc.get("thumbnail_url")
    ]
    video_size_mb = post.get("video_size_mb")
    if file_size_bytes and not video_size_mb:
        video_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    return {
        **post,
        "media_urls": post.get("media_urls") or media_urls,
        "media_url": post.get("media_url") or (media_urls[0] if media_urls else None),
        "thumbnail_urls": post.get("thumbnail_urls") or thumbnail_urls,
        "media_types": post.get("media_types") or media_types,
        "video_size_mb": video_size_mb,
    }


def _derive_published_media_kind(post: dict) -> str:
    media_types = [
        str(media_type).strip().lower()
        for media_type in (post.get("media_types") or [])
        if str(media_type).strip()
    ]
    if media_types:
        has_image = any(media_type == "image" for media_type in media_types)
        has_video = any(media_type == "video" for media_type in media_types)
        if has_image and has_video:
            return "mixed"
        if has_video:
            return "video"
        if has_image:
            return "image"

    post_type = str(post.get("post_type") or "").strip().lower()
    if "mixed" in post_type:
        return "mixed"
    if post_type in {"video", "reel", "story"} or "video" in post_type:
        return "video"
    if (post.get("thumbnail_urls") or []) or (post.get("media_urls") or []) or post.get("media_url"):
        return "image"
    return "text"


def _published_card_thumbnail_ref(post: dict) -> str | None:
    thumbnail_urls = post.get("thumbnail_urls") or []
    media_urls = post.get("media_urls") or []
    if thumbnail_urls:
        return thumbnail_urls[0]
    if media_urls:
        return media_urls[0]
    return post.get("media_url")


async def _generate_published_card_thumbnail(post: dict) -> dict:
    source_ref = _published_card_thumbnail_ref(post)
    if not source_ref:
        return {}

    from PIL import Image  # noqa: PLC0415
    import httpx  # noqa: PLC0415
    from utils.storage import build_storage_key, upload_file_async  # noqa: PLC0415

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(source_ref)
        response.raise_for_status()
        source_bytes = response.content

    loop = asyncio.get_running_loop()

    def _render_card_thumbnail() -> bytes:
        with Image.open(io.BytesIO(source_bytes)) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.getchannel("A"))
                img = background
            else:
                img = img.convert("RGB")

            width, height = img.size
            side = min(width, height)
            left = max(0, (width - side) // 2)
            top = max(0, (height - side) // 2)
            cropped = img.crop((left, top, left + side, top + side))
            resized = cropped.resize(_PUBLISHED_CARD_THUMB_SIZE, Image.LANCZOS)

            output = io.BytesIO()
            resized.save(
                output,
                format="WEBP",
                quality=_PUBLISHED_CARD_THUMB_QUALITY,
                optimize=True,
                method=6,
            )
            return output.getvalue()

    thumb_bytes = await loop.run_in_executor(None, _render_card_thumbnail)

    user_id = post.get("user_id") or "unknown"
    post_id = post.get("id") or "unknown"
    filename = f"{post_id}.webp"
    folder = f"published-card-thumbnails/{user_id}"
    storage_key = build_storage_key(folder, filename)
    thumbnail_url = await upload_file_async(
        thumb_bytes,
        filename,
        "image/webp",
        folder=folder,
    )
    return {
        "published_card_thumbnail_key": storage_key,
        "published_card_thumbnail_url": thumbnail_url,
        "published_card_thumbnail_created_at": datetime.now(timezone.utc),
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


def _pre_upload_result_path(target_key: str, field: str) -> str:
    return f"pre_upload_results.{target_key}.{field}"


def _get_platform_pre_upload_state(post: dict, target_key: str) -> dict:
    return ((post.get("pre_upload_results") or {}).get(target_key) or {})


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


def _get_platform_pre_upload_status(post: dict, target_key: str) -> str | None:
    state = _get_platform_pre_upload_state(post, target_key)
    return state.get("status") or post.get("pre_upload_status")


def _get_platform_pre_upload_error(post: dict, target_key: str) -> str | None:
    state = _get_platform_pre_upload_state(post, target_key)
    return state.get("error") or post.get("pre_upload_error")


def _get_platform_pre_upload_started_at(post: dict, target_key: str):
    state = _get_platform_pre_upload_state(post, target_key)
    return _coerce_utc_datetime(state.get("started_at") or post.get("pre_upload_started_at"))


def _get_platform_pre_upload_completed_at(post: dict, target_key: str):
    state = _get_platform_pre_upload_state(post, target_key)
    return _coerce_utc_datetime(state.get("completed_at") or post.get("pre_upload_completed_at"))


def _get_platform_pre_upload_next_retry_at(post: dict, target_key: str):
    state = _get_platform_pre_upload_state(post, target_key)
    return _coerce_utc_datetime(state.get("next_retry_at"))


def _seconds_until_retry(next_retry_at, fallback: int) -> int:
    if not isinstance(next_retry_at, datetime):
        return fallback
    remaining = int((next_retry_at - datetime.now(timezone.utc)).total_seconds())
    return max(fallback, remaining if remaining > 0 else 0)


async def _handle_pre_upload_permanent_error(
    *,
    db,
    task,
    post: dict,
    post_id: str,
    platform: str,
    account_id: str | None,
    target_key: str,
    publish_queue: str,
    attempt: int,
    dispatch_source: str,
    exc: PlatformError,
) -> dict:
    error_code = getattr(exc, "code", None)
    subcode = getattr(exc, "subcode", None)
    is_scope_error = _is_scope_insufficient_error(exc)
    is_suspension_error = _is_platform_suspension_error(platform, exc)
    is_auth_error = (
        (isinstance(exc, PlatformHTTPError) and getattr(exc, "status_code", 0) in (401, 403))
        or subcode in {458, 460}
        or error_code in (190, 261, 326)
    )
    resolved_account_id = account_id or target_key

    if is_auth_error and resolved_account_id and attempt == 0:
        try:
            from celery_workers.tasks.tokens import _refresh_with_lock

            logger.info(
                "Auth error during pre-upload on %s/%s — attempting on-demand token refresh for account %s",
                post_id,
                platform,
                resolved_account_id,
            )
            await _refresh_with_lock(db, resolved_account_id, platform)
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$unset": {
                        _pre_upload_result_path(target_key, "status"): "",
                        f"platform_container_ids.{target_key}": "",
                        f"container_expiry_at.{target_key}": "",
                        _pre_upload_result_path(target_key, "error"): "",
                        _pre_upload_result_path(target_key, "started_at"): "",
                        _pre_upload_result_path(target_key, "completed_at"): "",
                        _pre_upload_result_path(target_key, "actual_duration_secs"): "",
                        _pre_upload_result_path(target_key, "next_retry_at"): "",
                    },
                    "$set": {
                        "updated_at": datetime.now(timezone.utc),
                    },
                },
            )
            await _sync_pre_upload_aggregate(db, post_id)
            publish_to_platform.apply_async(
                kwargs={
                    "post_id": post_id,
                    "platform": platform,
                    "account_id": resolved_account_id,
                    "attempt": attempt + 1,
                    "dispatch_source": dispatch_source,
                },
                countdown=5,
                queue=publish_queue,
            )
            return {"status": "token_refreshed_requeued", "platform": platform, "account_id": resolved_account_id}
        except Exception as refresh_err:
            logger.warning("On-demand pre-upload token refresh failed for %s: %s", post_id, refresh_err)

    await _update_platform_result(
        db,
        post_id,
        platform,
        {
            "status": "failed",
            "error": str(exc),
            "retry_count": attempt,
            "last_attempt_at": datetime.now(timezone.utc),
        },
        account_id=resolved_account_id,
    )

    if is_auth_error and resolved_account_id:
        try:
            if is_scope_error:
                from utils.ghost_cascade import handle_account_reconnect_required

                await handle_account_reconnect_required(
                    db,
                    resolved_account_id,
                    reconnect_reason=(
                        "Missing required YouTube publish permissions. Reconnect the account and grant upload/edit access."
                        if platform == "youtube"
                        else str(exc)
                    ),
                    error_code=str(error_code or "insufficient_scopes"),
                )
            elif is_suspension_error:
                from utils.ghost_cascade import handle_ghost_account

                await handle_ghost_account(
                    db,
                    resolved_account_id,
                    error_code,
                    suspension_reason=str(exc),
                )
            else:
                from utils.ghost_cascade import handle_account_reconnect_required

                await handle_account_reconnect_required(
                    db,
                    resolved_account_id,
                    reconnect_reason=str(exc),
                    error_code=str(error_code or ""),
                )
        except ImportError:
            pass

    await _finalize_post_status(db, post_id)
    await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
    return {"status": "permanent_failure", "platform": platform, "account_id": resolved_account_id}


def _get_target_publish_state(post: dict, platform: str, target_key: str) -> dict:
    account_results = post.get("account_results") or {}
    if target_key in account_results:
        return account_results.get(target_key) or {}
    return (post.get("platform_results") or {}).get(platform) or {}


def _is_stale_publish_lock(post: dict, platform: str, target_key: str, now: datetime) -> bool:
    result = _get_target_publish_state(post, platform, target_key)
    if not result:
        return False

    if _coerce_utc_datetime(result.get("dispatch_started_at")) or _coerce_utc_datetime(result.get("last_attempt_at")):
        return False

    enqueued_candidates = [
        _coerce_utc_datetime(result.get("dispatch_enqueued_at")),
        _coerce_utc_datetime(result.get("fallback_dispatch_enqueued_at")),
    ]
    enqueued_candidates = [candidate for candidate in enqueued_candidates if isinstance(candidate, datetime)]
    if not enqueued_candidates:
        return False

    latest_enqueue = max(enqueued_candidates)
    return latest_enqueue <= now - timedelta(seconds=_PUBLISH_LOCK_STALE_SECONDS)


def _pre_upload_platforms_for(post: dict) -> list[dict]:
    required = [
        target
        for target in _get_publish_targets(post)
        if _requires_pre_upload(target["platform"], post)
    ]
    result_keys = set((post.get("pre_upload_results") or {}).keys())
    for target in _get_publish_targets(post):
        if target["target_key"] in result_keys and target not in required:
            required.append(target)
    return required


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

    targets = _pre_upload_platforms_for(post)
    results = post.get("pre_upload_results") or {}

    statuses: list[str] = []
    errors: list[str] = []
    start_times = []
    started_ats = []
    completed_ats = []
    estimated_durations = []
    actual_durations = []

    for target in targets:
        target_key = target["target_key"]
        state = results.get(target_key) or {}
        status = state.get("status")
        if status:
            statuses.append(status)
        error = state.get("error")
        if error:
            errors.append(f"{target['platform']}:{target_key}: {error}")
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
    elif "retrying" in statuses:
        aggregate_status = "retrying"
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


async def _resolve_post_account(db, post: dict, platform: str, account_id: str | None = None) -> dict | None:
    if account_id:
        account_doc = await db.social_accounts.find_one({
            "user_id": post.get("user_id"),
            "platform": platform,
            "is_active": True,
            "$or": [
                {"account_id": account_id},
                {"id": account_id},
            ],
        })
        return _normalize_account_doc(account_doc)

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
def publish_to_platform(
    self,
    post_id: str,
    platform: str,
    account_id: str | None = None,
    attempt: int = 0,
    dispatch_source: str = "primary",
) -> dict:
    return _run_async(_async_publish_to_platform(self, post_id, platform, account_id, attempt, dispatch_source))


async def _async_publish_to_platform(
    task,
    post_id: str,
    platform: str,
    account_id: str | None,
    attempt: int,
    dispatch_source: str = "primary",
) -> dict:
    from platform_adapters import get_adapter
    from celery_workers.tasks.publish import recompute_aggregate_status, should_cleanup_media
    from celery_workers.tasks.cleanup import schedule_media_cleanup

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    r_cache = get_cache_redis()
    target_key = _result_target_key(platform, account_id)

    # 20.14: Feature flag kill-switch — bail out immediately if platform disabled
    try:
        from utils.feature_flags import is_enabled
        flag_name = f"{platform}_publishing"
        if not is_enabled(flag_name):
            event_log(
                logger,
                "warning",
                "publish.platform.paused",
                task_name="publish_to_platform",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="feature_flag_disabled",
                outcome="paused",
            )
            await _update_platform_result(db, post_id, platform, {
                "status": "paused",
                "error": f"Platform {platform} is currently disabled via feature flag",
            }, account_id=account_id)
            await _finalize_post_status(db, post_id)
            return {"status": "feature_disabled", "platform": platform, "account_id": account_id}
    except ImportError:
        pass

    # 20.5: Per-platform poison pill guard — each platform has its own delivery counter
    r_queue = get_queue_redis()
    pp_key = f"delivery_count:{task.request.id}:{target_key}"
    pp_count = await safe_incr(r_queue, pp_key, default=1, feature="Per-platform poison-pill counter")
    await safe_expire(r_queue, pp_key, 86400, default=True, feature="Per-platform poison-pill TTL")
    if int(pp_count) > MAX_DELIVERY_COUNT:
        event_log(
            logger,
            "error",
            "publish.platform.poison_pill",
            task_name="publish_to_platform",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            failure_type="poison_pill_exceeded",
            delivery_count=int(pp_count),
            outcome="dlq",
        )
        await _move_to_dlq(post_id, "poison_pill_exceeded", platform=platform, account_id=account_id)
        return {"status": "dlq", "reason": "poison_pill", "platform": platform, "account_id": account_id}

    # 20.1: Circuit breaker — fail fast if platform is known-down
    try:
        from utils.circuit_breaker import can_attempt
        if not await can_attempt(r_cache, platform):
            rate_limited_event_log(
                logger,
                "warning",
                "publish.platform.circuit_open",
                dedupe_key=f"publish:circuit-open:{platform}:{account_id or 'none'}",
                task_name="publish_to_platform",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="circuit_open",
                outcome="retrying",
            )
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "error": f"Platform {platform} circuit breaker OPEN — requeued",
                "next_retry_at": datetime.utcnow() + timedelta(seconds=300),
            }, account_id=account_id)
            raise task.retry(
                countdown=300,
                exc=Exception(f"Circuit OPEN for {platform}"),
                kwargs={
                    "post_id": post_id,
                    "platform": platform,
                    "account_id": account_id,
                    "attempt": attempt,
                    "dispatch_source": dispatch_source,
                },
            )
    except ImportError:
        pass

    # EC17: Check Redis confirmation cache first — may already be done
    confirm_key = f"confirmed:{post_id}:{target_key}"
    cached = await safe_get(r_cache, confirm_key, default=None, feature="Publish confirmation cache read")
    if cached:
        event_log(
            logger,
            "info",
            "publish.platform.confirmed_cache_hit",
            task_name="publish_to_platform",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            outcome="already_confirmed",
        )
        return {"status": "already_confirmed", "platform": platform, "account_id": account_id}

    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if post is None:
        return {"status": "post_deleted"}
    if post.get("deleted_at") or post.get("status") == "cancelled":
        event_log(
            logger,
            "info",
            "publish.platform.cancelled_before_start",
            task_name="publish_to_platform",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            outcome="post_deleted_or_cancelled",
        )
        return {"status": "post_deleted", "platform": platform, "account_id": account_id}
    post = await _hydrate_post_media(db, post)
    event_log(
        logger,
        "info",
        "publish.platform.received",
        task_name="publish_to_platform",
        post_id=post_id,
        platform=platform,
        account_id=account_id,
        dispatch_source=dispatch_source,
        attempt=attempt,
        outcome="received",
    )

    publish_queue = _publish_queue_for(platform, post)
    lock_owner = task.request.id or f"{post_id}:{target_key}:{attempt}"
    lock_acquired = await _acquire_publish_lock(r_cache, post_id, target_key, lock_owner)
    if not lock_acquired and _is_stale_publish_lock(post, platform, target_key, datetime.now(timezone.utc)):
        await safe_delete(
            r_cache,
            _publish_lock_key(post_id, target_key),
            default=0,
            feature="Publish stale lock recovery",
        )
        event_log(
            logger,
            "warning",
            "publish.platform.stale_lock_cleared",
            task_name="publish_to_platform",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            dispatch_source=dispatch_source,
            failure_type="stale_lock",
            outcome="recovered",
        )
        lock_acquired = await _acquire_publish_lock(r_cache, post_id, target_key, lock_owner)
    if not lock_acquired:
        event_log(
            logger,
            "info",
            "publish.platform.lock_contention",
            task_name="publish_to_platform",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            outcome="requeued",
        )
        if dispatch_source == "fallback":
            return {"status": "already_inflight", "platform": platform, "account_id": account_id}
        publish_to_platform.apply_async(
            kwargs={
                "post_id": post_id,
                "platform": platform,
                "account_id": account_id,
                "attempt": attempt,
                "dispatch_source": dispatch_source,
            },
            countdown=random.randint(20, 40),
            queue=publish_queue,
        )
        return {"status": "already_inflight_requeued", "platform": platform, "account_id": account_id}

    try:
        await _update_platform_result(
            db,
            post_id,
            platform,
            {
                "status": "processing",
                "last_attempt_at": datetime.now(timezone.utc),
                "dispatch_started_at": datetime.now(timezone.utc),
                "dispatch_source": dispatch_source,
            },
            account_id=account_id,
        )

        # Bootstrap pre-upload for platforms that require a prepared container/video_id
        # before publish. This is critical for immediate "post now" flows because they do
        # not always pass through the scheduled pre-upload window first.
        if _requires_pre_upload(platform, post):
            container_ids = post.get("platform_container_ids") or {}
            pre_status = _get_platform_pre_upload_status(post, target_key) or ""
            pre_retry_at = _get_platform_pre_upload_next_retry_at(post, target_key)
            has_container = bool(container_ids.get(target_key))

            if not has_container and pre_status in {"pending", "uploading", "retrying"}:
                retry_after = _seconds_until_retry(pre_retry_at, _PRE_UPLOAD_POLL_INTERVAL)
                event_log(
                    logger,
                    "info",
                    "publish.pre_upload.awaiting_retry",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=account_id,
                    retry_after=retry_after,
                    pre_upload_status=pre_status,
                    outcome="retrying",
                )
                await _update_platform_result(
                    db,
                    post_id,
                    platform,
                    {
                        "status": "retrying",
                        "error": f"{platform} pre-upload is retrying",
                        "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=retry_after),
                    },
                    account_id=account_id,
                )
                raise task.retry(
                    countdown=retry_after,
                    exc=Exception(f"{platform} pre_upload retry scheduled"),
                    kwargs={
                        "post_id": post_id,
                        "platform": platform,
                        "account_id": account_id,
                        "attempt": attempt,
                        "dispatch_source": dispatch_source,
                    },
                )

            if pre_status in ("", None) or (pre_status == "ready" and not has_container):
                logger.info(
                    "Bootstrapping pre-upload for %s/%s (post_type=%s, has_container=%s, pre_status=%r)",
                    post_id,
                    platform,
                    post.get("post_type"),
                    has_container,
                    pre_status,
                )
                event_log(
                    logger,
                    "info",
                    "publish.pre_upload.bootstrap",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=account_id,
                    post_type=post.get("post_type"),
                    outcome="bootstrapped",
                )
                try:
                    pre_result = await _async_pre_upload(task, post_id, platform, account_id)
                except PlatformError as exc:
                    return await _handle_pre_upload_permanent_error(
                        db=db,
                        task=task,
                        post=post,
                        post_id=post_id,
                        platform=platform,
                        account_id=account_id,
                        target_key=target_key,
                        publish_queue=publish_queue,
                        attempt=attempt,
                        dispatch_source=dispatch_source,
                        exc=exc,
                    )
                if pre_result.get("status") == "polling":
                    await _update_platform_result(db, post_id, platform, {
                        "status": "retrying",
                        "error": f"{platform} media container is still processing",
                        "last_attempt_at": datetime.now(timezone.utc),
                    }, account_id=account_id)
                    raise task.retry(
                        countdown=_PRE_UPLOAD_POLL_INTERVAL,
                        exc=Exception(f"{platform} pre_upload still processing"),
                        kwargs={
                            "post_id": post_id,
                            "platform": platform,
                            "account_id": account_id,
                            "attempt": attempt,
                            "dispatch_source": dispatch_source,
                        },
                    )

                post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                if post is None:
                    return {"status": "post_deleted"}
                if post.get("deleted_at") or post.get("status") == "cancelled":
                    return {"status": "post_deleted", "platform": platform, "account_id": account_id}
                post = await _hydrate_post_media(db, post)

        # EC15: Check subscription is still active before publishing
        try:
            from utils.subscription import check_subscription_active
            user_id = post.get("user_id", "")
            is_active, reason = await check_subscription_active(db, user_id)
            if not is_active:
                event_log(
                    logger,
                    "warning",
                    "publish.subscription_blocked",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=account_id,
                    user_id=user_id,
                    failure_type="subscription_expired",
                    provider_error=reason,
                    outcome="paused",
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "paused",
                    "error": f"Subscription expired: {reason}",
                }, account_id=account_id)
                await _finalize_post_status(db, post_id)
                return {"status": "subscription_expired"}
        except ImportError:
            pass

        # 17.4 Scenario B: pre_upload still running at scheduled publish time.
        # Poll every 5s for up to 10 minutes before giving up.
        if _requires_pre_upload(platform, post):
            pre_status = _get_platform_pre_upload_status(post, target_key) or ""
            if pre_status == "failed":
                err = _get_platform_pre_upload_error(post, target_key) or "Pre-upload failed before publish time"
                logger.error("17.4C: pre_upload failed for %s/%s — %s", post_id, platform, err)
                await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err}, account_id=account_id)
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
                        _publish_lock_key(post_id, target_key),
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
                            f"pre_upload_results.{target_key}": 1,
                        },
                    )
                    current_status = _get_platform_pre_upload_status(refreshed or {}, target_key) or ""
                    if current_status == "ready":
                        logger.info(
                            "17.4B: pre_upload ready after %ds for %s/%s",
                            waited, post_id, platform,
                        )
                        post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                        break
                    if current_status == "failed":
                        err = _get_platform_pre_upload_error(refreshed or {}, target_key) or "Pre-upload failed"
                        logger.error("17.4B: pre_upload failed while polling %s/%s — %s", post_id, platform, err)
                        await _update_platform_result(db, post_id, platform, {"status": "failed", "error": err}, account_id=account_id)
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
                    await _update_platform_result(db, post_id, platform, {"status": "failed", "error": msg}, account_id=account_id)
                    await _finalize_post_status(db, post_id)
                    await _send_failure_notification(db, post_id, platform, msg)
                    return {"status": "failed", "reason": "pre_upload_wait_timeout"}
                post = await _hydrate_post_media(db, post)

        resolved_account_id = account_id
        try:
            from utils.encryption import decrypt
            account_doc = await _resolve_post_account(db, post, platform, account_id=account_id)
            if account_doc and account_doc.get("access_token"):
                resolved_account_id = account_doc.get("account_id") or account_doc.get("id")
                post = {**post, "access_token": decrypt(account_doc["access_token"]), "account": account_doc}
        except Exception as _token_err:
            event_log(
                logger,
                "warning",
                "publish.token_injection.degraded",
                exc_info=_token_err,
                task_name="publish_to_platform",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="token_injection_failed",
                provider_error=shorten_provider_error(_token_err),
                outcome="degraded",
            )

        try:
            cb_open = await can_attempt(r_cache, platform, resolved_account_id)
            if not cb_open:
                rate_limited_event_log(
                    logger,
                    "warning",
                    "publish.platform.account_circuit_open",
                    dedupe_key=f"publish:acct-circuit-open:{platform}:{resolved_account_id or 'none'}",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=resolved_account_id,
                    failure_type="circuit_open",
                    outcome="retrying",
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "error": f"Circuit breaker OPEN for {platform} — will retry when circuit closes",
                    "next_retry_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                }, account_id=resolved_account_id)
                raise task.retry(
                    countdown=300,
                    exc=Exception(f"Circuit OPEN: {platform}"),
                    kwargs={
                        "post_id": post_id,
                        "platform": platform,
                        "account_id": resolved_account_id,
                        "attempt": attempt,
                        "dispatch_source": dispatch_source,
                    },
                )

            _override = (
                (post.get("account_overrides") or {}).get(resolved_account_id or target_key)
                or (post.get("platform_overrides") or {}).get(platform)
                or {}
            )
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
                "effective_first_comment": _override.get("first_comment"),
                "effective_poll": _override.get("poll"),
                "effective_youtube_privacy": _override.get("youtube_privacy") or post.get("youtube_privacy"),
                "effective_tiktok_privacy": _override.get("tiktok_privacy") or post.get("tiktok_privacy"),
                "effective_tiktok_allow_duet": _override.get("tiktok_allow_duet", post.get("tiktok_allow_duet")),
                "effective_tiktok_allow_stitch": _override.get("tiktok_allow_stitch", post.get("tiktok_allow_stitch")),
                "effective_tiktok_allow_comment": _override.get("tiktok_allow_comment", post.get("tiktok_allow_comment")),
                "effective_linkedin_document_url": _override.get("linkedin_document_url"),
                "effective_linkedin_document_title": _override.get("linkedin_document_title"),
                "tiktok_privacy": _override.get("tiktok_privacy") or post.get("tiktok_privacy"),
                "disable_duet": not bool(_override.get("tiktok_allow_duet", post.get("tiktok_allow_duet", True))),
                "disable_stitch": not bool(_override.get("tiktok_allow_stitch", post.get("tiktok_allow_stitch", True))),
                "disable_comment": not bool(_override.get("tiktok_allow_comment", post.get("tiktok_allow_comment", True))),
                "publish_target_key": target_key,
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
                }, account_id=resolved_account_id)
                publish_to_platform.apply_async(
                    kwargs={
                        "post_id": post_id,
                        "platform": platform,
                        "account_id": resolved_account_id,
                        "attempt": attempt,
                        "dispatch_source": dispatch_source,
                    },
                    countdown=_backoff,
                    queue=publish_queue,
                )
                return {"status": "throttled_requeued", "platform": platform, "account_id": resolved_account_id}

            try:
                result = await adapter.publish(post, redis=r_cache)
            finally:
                await _release_platform_slot(r_cache, platform)

            try:
                from utils.circuit_breaker import record_success
                await record_success(r_cache, platform, resolved_account_id)
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

            await record_success(r_cache, platform, resolved_account_id)

            await _update_platform_result(db, post_id, platform, {
                "status": "published",
                "post_url": post_url,
                "platform_post_id": platform_post_id,
                "published_at": datetime.now(timezone.utc),
            }, account_id=resolved_account_id)
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$unset": {
                        f"account_results.{target_key}.error": "",
                        f"account_results.{target_key}.next_retry_at": "",
                        f"account_results.{target_key}.dlq_reason": "",
                    }
                },
            )

            user_id, prev_agg_status, agg_status = await _finalize_post_status(db, post_id)
            await _send_success_notification(db, post_id, platform, post_url or "", user_id or "")
            if agg_status == "published" and prev_agg_status == "partial":
                await _send_recovery_notification(db, post_id, user_id or "")
            event_log(
                logger,
                "info",
                "publish.platform.succeeded",
                task_name="publish_to_platform",
                post_id=post_id,
                platform=platform,
                account_id=resolved_account_id,
                platform_post_id=platform_post_id,
                outcome="published",
            )

            return {"status": "published", "platform": platform, "account_id": resolved_account_id}

        except Exception as exc:
            from platform_adapters.base import classify_error, ErrorClass, PlatformHTTPError

            if "container expired" in str(exc).lower() and platform == "instagram":
                logger.warning("Instagram container expired for %s — clearing and re-queuing pre_upload", post_id)
                await db.posts.update_one(
                    {"id": post_id},
                    {
                        "$unset": {
                            f"platform_container_ids.{target_key}": "",
                            f"container_expiry_at.{target_key}": "",
                            _pre_upload_result_path(target_key, "error"): "",
                            _pre_upload_result_path(target_key, "completed_at"): "",
                            _pre_upload_result_path(target_key, "actual_duration_secs"): "",
                        },
                        "$set": {
                            _pre_upload_result_path(target_key, "status"): "pending",
                            _pre_upload_result_path(target_key, "started_at"): None,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    },
                )
                await _sync_pre_upload_aggregate(db, post_id)
                pre_upload_task.apply_async(
                    kwargs={"post_id": post_id, "platform": platform, "account_id": resolved_account_id},
                    queue="media_processing",
                    countdown=5,
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "error": "Container expired — re-uploading media",
                    "last_attempt_at": datetime.now(timezone.utc),
                }, account_id=resolved_account_id)
                return {"status": "container_expired_requeued", "platform": platform, "account_id": resolved_account_id}

            error_class = classify_error(exc)

            if error_class == ErrorClass.PERMANENT:
                event_log(
                    logger,
                    "error",
                    "publish.platform.failed",
                    exc_info=exc,
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=resolved_account_id,
                    failure_type="permanent",
                    provider_error=shorten_provider_error(exc),
                    outcome="failed",
                )
                capture_degraded_event(
                    "Publish permanent failure",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=resolved_account_id,
                    failure_type="permanent",
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "failed",
                    "error": str(exc),
                    "retry_count": attempt,
                    "last_attempt_at": datetime.now(timezone.utc),
                }, account_id=resolved_account_id)

                error_code = getattr(exc, "code", None)
                subcode = getattr(exc, "subcode", None)
                is_scope_error = _is_scope_insufficient_error(exc)
                is_suspension_error = _is_platform_suspension_error(platform, exc)
                is_auth_error = (
                    (isinstance(exc, PlatformHTTPError) and getattr(exc, "status_code", 0) in (401, 403))
                    or subcode in {458, 460}
                    or error_code in (190, 261, 326)
                )
                if is_auth_error:
                    _acct = post.get("account", {})
                    _acct_id = _acct.get("account_id", _acct.get("id", ""))
                    if is_scope_error and _acct_id:
                        try:
                            from utils.ghost_cascade import handle_account_reconnect_required

                            await handle_account_reconnect_required(
                                db,
                                _acct_id,
                                reconnect_reason=(
                                    "Missing required YouTube publish permissions. "
                                    "Reconnect the account and grant upload/edit access."
                                    if platform == "youtube"
                                    else str(exc)
                                ),
                                error_code=str(error_code or "insufficient_scopes"),
                            )
                        except ImportError:
                            pass
                    else:
                        try:
                            from celery_workers.tasks.tokens import _refresh_with_lock
                            if _acct_id and attempt == 0:
                                logger.info(
                                    "Auth error on %s/%s — attempting on-demand token refresh for account %s",
                                    post_id, platform, _acct_id,
                                )
                                await _refresh_with_lock(db, _acct_id, platform)
                                logger.info("Token refreshed for %s — re-enqueuing post %s", _acct_id, post_id)
                                publish_to_platform.apply_async(
                                    kwargs={
                                        "post_id": post_id,
                                        "platform": platform,
                                        "account_id": _acct_id,
                                        "attempt": attempt + 1,
                                        "dispatch_source": dispatch_source,
                                    },
                                    countdown=5,
                                    queue=publish_queue,
                                )
                                return {"status": "token_refreshed_requeued"}
                        except Exception as _refresh_err:
                            logger.warning("On-demand token refresh failed for %s: %s", post_id, _refresh_err)

                        try:
                            if _acct_id:
                                if is_suspension_error:
                                    from utils.ghost_cascade import handle_ghost_account

                                    await handle_ghost_account(
                                        db, _acct_id, error_code,
                                        suspension_reason=str(exc),
                                    )
                                else:
                                    from utils.ghost_cascade import handle_account_reconnect_required

                                    await handle_account_reconnect_required(
                                        db,
                                        _acct_id,
                                        reconnect_reason=str(exc),
                                        error_code=str(error_code or ""),
                                    )
                        except ImportError:
                            pass

                await record_failure(r_cache, platform, resolved_account_id)
                await _finalize_post_status(db, post_id)
                await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
                return {"status": "permanent_failure"}

            if error_class == ErrorClass.RATE_LIMITED:
                retry_after = getattr(exc, "retry_after", 3600)
                rate_limited_event_log(
                    logger,
                    "warning",
                    "publish.platform.rate_limited",
                    dedupe_key=f"publish:rate-limited:{platform}:{resolved_account_id or 'none'}",
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=resolved_account_id,
                    failure_type="rate_limited",
                    retry_after=retry_after,
                    outcome="retrying",
                )
                await _update_platform_result(db, post_id, platform, {
                    "status": "retrying",
                    "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=retry_after),
                }, account_id=resolved_account_id)
                raise task.retry(
                    countdown=retry_after,
                    exc=exc,
                    kwargs={
                        "post_id": post_id,
                        "platform": platform,
                        "account_id": resolved_account_id,
                        "attempt": attempt,
                        "dispatch_source": dispatch_source,
                    },
                )

            countdown_map = {0: 60, 1: 300, 2: 900}
            jitter = random.randint(0, [30, 60, 120][min(attempt, 2)])
            countdown = countdown_map.get(attempt, 900) + jitter

            if attempt >= MAX_RETRIES:
                event_log(
                    logger,
                    "error",
                    "publish.platform.max_retries_exceeded",
                    exc_info=exc,
                    task_name="publish_to_platform",
                    post_id=post_id,
                    platform=platform,
                    account_id=resolved_account_id,
                    failure_type="max_retries_exceeded",
                    provider_error=shorten_provider_error(exc),
                    outcome="dlq",
                )
                await record_failure(r_cache, platform, resolved_account_id)
                await _move_to_dlq(post_id, str(exc), platform=platform, account_id=resolved_account_id)
                await _send_failure_notification(db, post_id, platform, str(exc), post.get("user_id", ""))
                return {"status": "dlq"}

            event_log(
                logger,
                "warning",
                "publish.platform.retry_scheduled",
                exc_info=exc,
                task_name="publish_to_platform",
                post_id=post_id,
                platform=platform,
                account_id=resolved_account_id,
                retry_count=attempt + 1,
                retry_after=countdown,
                failure_type="transient",
                provider_error=shorten_provider_error(exc),
                outcome="retrying",
            )
            await _update_platform_result(db, post_id, platform, {
                "status": "retrying",
                "retry_count": attempt + 1,
                "last_attempt_at": datetime.now(timezone.utc),
                "next_retry_at": datetime.now(timezone.utc) + timedelta(seconds=countdown),
                "error": str(exc),
            }, account_id=resolved_account_id)
            raise task.retry(countdown=countdown, exc=exc, kwargs={
                "post_id": post_id,
                "platform": platform,
                "account_id": resolved_account_id,
                "attempt": attempt + 1,
                "dispatch_source": dispatch_source,
            })
    finally:
        await _release_publish_lock(r_cache, post_id, target_key, lock_owner)


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
def pre_upload_task(self, post_id: str, platform: str, account_id: str | None = None) -> dict:
    """
    Fires at pre_upload_start_time (dynamically calculated, min 15 min ahead).
    Uploads media container (Instagram) or private video (YouTube).
    Stores container_id/video_id for use by publish_task at scheduled_time.
    Records actual_upload_duration for future estimate calibration (17.3).
    """
    return _run_async(_async_pre_upload(self, post_id, platform, account_id))


async def _async_pre_upload(task, post_id: str, platform: str, account_id: str | None = None) -> dict:
    from platform_adapters import get_adapter

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    r_cache = get_cache_redis()
    target_key = _result_target_key(platform, account_id)

    started_at = datetime.now(timezone.utc)
    lock_owner = task.request.id or f"{post_id}:{target_key}:preupload"
    lock_acquired = await _acquire_pre_upload_lock(r_cache, post_id, target_key, lock_owner)
    if not lock_acquired:
        event_log(
            logger,
            "info",
            "publish.pre_upload.lock_contention",
            task_name="pre_upload_task",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            outcome="already_inflight",
        )
        return {"status": "already_inflight", "platform": platform, "account_id": account_id}

    await db.posts.update_one(
        {"id": post_id},
        {
            "$set": {
                _pre_upload_result_path(target_key, "status"): "uploading",
                _pre_upload_result_path(target_key, "started_at"): started_at,
                "updated_at": started_at,
            },
            "$unset": {
                _pre_upload_result_path(target_key, "error"): "",
                _pre_upload_result_path(target_key, "completed_at"): "",
                _pre_upload_result_path(target_key, "actual_duration_secs"): "",
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
        account_doc = await _resolve_post_account(db, post, platform, account_id=account_id)
        if account_doc:
            post = {**post, "account": account_doc}
        # EC-1: Post deleted or cancelled before pre_upload executed — abort cleanly
        if not post or post.get("status") in {"deleted", "cancelled"}:
            event_log(
                logger,
                "info",
                "publish.pre_upload.skipped",
                task_name="pre_upload_task",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                outcome="post_deleted_or_cancelled",
            )
            return {"status": "post_deleted"}
        # Inject per-platform text overrides for pre_upload (YouTube uses title/content in metadata)
        _override = (
            (post.get("account_overrides") or {}).get(account_id or target_key)
            or (post.get("platform_overrides") or {}).get(platform)
            or {}
        )
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
            "effective_poll": _override.get("poll"),
            "publish_target_key": target_key,
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
                    "target_key": target_key,
                    "poll_attempt": 0,
                },
                queue="media_processing",
            )
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$set": {
                        _pre_upload_result_path(target_key, "status"): "uploading",
                        _pre_upload_result_path(target_key, "started_at"): started_at,
                        f"platform_container_ids.{target_key}": container_id,
                        "updated_at": datetime.now(timezone.utc),
                    }
                }
            )
            await _sync_pre_upload_aggregate(db, post_id)
            return {"status": "polling", "platform": platform, "account_id": account_id, "container_id": container_id}

        completed_at = datetime.now(timezone.utc)
        actual_duration = int((completed_at - started_at).total_seconds())
        expiry = completed_at + timedelta(hours=23)
        container_id = container_result.get("container_id") or container_result.get("video_id")
        await db.posts.update_one(
            {"id": post_id},
            {
                "$set": {
                    _pre_upload_result_path(target_key, "status"): "ready",
                    _pre_upload_result_path(target_key, "started_at"): started_at,
                    _pre_upload_result_path(target_key, "completed_at"): completed_at,
                    _pre_upload_result_path(target_key, "actual_duration_secs"): actual_duration,
                    f"platform_container_ids.{target_key}": container_id,
                    f"container_expiry_at.{target_key}": expiry.isoformat(),
                    "updated_at": completed_at,
                },
                "$unset": {
                    _pre_upload_result_path(target_key, "error"): "",
                },
            }
        )
        await _sync_pre_upload_aggregate(db, post_id)
        event_log(
            logger,
            "info",
            "publish.pre_upload.ready",
            task_name="pre_upload_task",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            actual_duration_secs=actual_duration,
            container_id=container_id,
            outcome="ready",
        )
        return {"status": "ready", "platform": platform, "account_id": account_id, "actual_duration_secs": actual_duration}

    except Exception as exc:
        from platform_adapters.base import ErrorClass, classify_error

        error_class = classify_error(exc, platform)
        retry_after = int(getattr(exc, "retry_after", 60) or 60)
        now = datetime.now(timezone.utc)

        if error_class == ErrorClass.PERMANENT:
            event_log(
                logger,
                "error",
                "publish.pre_upload.failed",
                exc_info=exc,
                task_name="pre_upload_task",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="pre_upload_failed",
                provider_error=shorten_provider_error(exc),
                outcome="failed",
            )
            await db.posts.update_one(
                {"id": post_id},
                {
                    "$set": {
                        _pre_upload_result_path(target_key, "status"): "failed",
                        _pre_upload_result_path(target_key, "error"): str(exc),
                        _pre_upload_result_path(target_key, "completed_at"): now,
                        "updated_at": now,
                    }
                }
            )
            await _sync_pre_upload_aggregate(db, post_id)
            raise

        event_log(
            logger,
            "warning",
            "publish.pre_upload.retry_scheduled",
            exc_info=exc,
            task_name="pre_upload_task",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            failure_type="pre_upload_retry",
            provider_error=shorten_provider_error(exc),
            retry_after=retry_after,
            outcome="retrying",
        )
        await db.posts.update_one(
            {"id": post_id},
            {
                "$set": {
                    _pre_upload_result_path(target_key, "status"): "retrying",
                    _pre_upload_result_path(target_key, "error"): str(exc),
                    _pre_upload_result_path(target_key, "next_retry_at"): now + timedelta(seconds=retry_after),
                    "updated_at": now,
                },
                "$unset": {
                    _pre_upload_result_path(target_key, "completed_at"): "",
                    _pre_upload_result_path(target_key, "actual_duration_secs"): "",
                },
            }
        )
        await _sync_pre_upload_aggregate(db, post_id)
        raise task.retry(countdown=retry_after, exc=exc)
    finally:
        await _release_pre_upload_lock(r_cache, post_id, target_key, lock_owner)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _update_platform_result(
    db,
    post_id: str,
    platform: str,
    update: dict,
    account_id: str | None = None,
) -> None:
    target_key = _result_target_key(platform, account_id)
    update_fields = {
        f"account_results.{target_key}.{k}": v
        for k, v in {
            **update,
            "platform": platform,
            "account_id": account_id or target_key,
        }.items()
    }
    await db.posts.update_one(
        {"id": post_id},
        {"$set": update_fields}
    )

    post_doc = await db.posts.find_one(
        {"id": post_id},
        {"_id": 0, "account_results": 1, "platform_results": 1, "publish_targets": 1, "user_id": 1, "status": 1},
    )
    if post_doc and post_doc.get("account_results"):
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {"platform_results": _aggregate_platform_results(post_doc)}},
        )

    # 20.4: Publish SSE update so browser is notified in real-time (non-blocking)
    try:
        import json as _json
        from db.redis_client import get_cache_redis
        r = get_cache_redis()
        if post_doc:
            payload = _json.dumps({
                "type": "platform_update",
                "post_id": post_id,
                "platform": platform,
                "account_id": account_id,
                "update": {k: str(v) for k, v in update.items()},
            })
            # Publish to per-post and per-user channels
            await r.publish(f"post:{post_id}:updates", payload)
            await r.publish(f"user:{post_doc.get('user_id', '')}:updates", payload)
    except Exception as _sse_err:
        logger.debug("SSE publish failed (non-blocking): %s", _sse_err)


async def _move_to_dlq(post_id: str, reason: str, platform: str | None = None, account_id: str | None = None) -> None:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    update: dict = {"dlq_reason": reason}
    if platform:
        target_key = _result_target_key(platform, account_id)
        update[f"account_results.{target_key}.status"] = "permanently_failed"
        update[f"account_results.{target_key}.error"] = reason
        update[f"account_results.{target_key}.dlq_reason"] = reason
        update[f"account_results.{target_key}.platform"] = platform
        update[f"account_results.{target_key}.account_id"] = account_id or target_key
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
        "account_id": account_id,
        "failed_at": datetime.now(timezone.utc),
        "retry_count": 0,
        "payload": {"task_name": "celery_workers.tasks.publish.publish_post", "args": [post_id]},
    }
    try:
        await db.dead_letter_queue.insert_one(dlq_doc)
    except Exception as dlq_err:
        event_log(
            logger,
            "error",
            "publish.dlq.write_failed",
            exc_info=dlq_err,
            task_name="_move_to_dlq",
            post_id=post_id,
            platform=platform,
            account_id=account_id,
            failure_type="dlq_write_failed",
            provider_error=shorten_provider_error(dlq_err),
            outcome="failed",
        )

    if platform:
        try:
            await _finalize_post_status(db, post_id)
        except Exception as finalize_err:
            event_log(
                logger,
                "warning",
                "publish.dlq.finalize_degraded",
                exc_info=finalize_err,
                task_name="_move_to_dlq",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="finalize_status_failed",
                provider_error=shorten_provider_error(finalize_err),
                outcome="degraded",
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
            event_log(
                logger,
                "warning",
                "publish.dlq.notification_degraded",
                exc_info=notify_exc,
                task_name="_move_to_dlq",
                post_id=post_id,
                platform=platform,
                account_id=account_id,
                failure_type="notification_failed",
                provider_error=shorten_provider_error(notify_exc),
                outcome="degraded",
            )


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
        event_log(
            logger,
            "warning",
            "publish.success_notification.degraded",
            exc_info=exc,
            task_name="_send_success_notification",
            post_id=post_id,
            platform=platform,
            user_id=user_id,
            failure_type="notification_failed",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )


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
        event_log(
            logger,
            "warning",
            "publish.recovery_notification.degraded",
            exc_info=exc,
            task_name="_send_recovery_notification",
            post_id=post_id,
            user_id=user_id,
            failure_type="notification_failed",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )
