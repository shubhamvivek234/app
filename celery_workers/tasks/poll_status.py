"""
Phase 5 — Polling fallback for posts stuck in PROCESSING status.
Runs every 5 minutes via Beat. Queries each platform's API directly
when a webhook confirmation has not arrived within the expected window.

Why needed: Platforms don't guarantee webhook delivery (Instagram drops ~2%,
YouTube delays up to 10 min). Without polling, stuck posts would never
transition to published/failed.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from celery import shared_task

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

# Posts stuck in PROCESSING for longer than this are eligible for polling
_POLLING_THRESHOLD_MINUTES = 10
# Processing posts with no platform post id and no publish attempt after this
# window are treated as orphaned child tasks and re-queued.
_ORPHAN_CHILD_THRESHOLD_MINUTES = 3
# Maximum staleness before we mark as failed (platform gives up)
_STALE_THRESHOLD_HOURS = 2


def _coerce_utc_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


# ── Beat schedule registration ────────────────────────────────────────────────

celery_app.conf.beat_schedule["poll-processing-posts"] = {
    "task": "celery_workers.tasks.poll_status.poll_processing_posts",
    "schedule": 300,  # every 5 minutes
    "options": {"queue": "default"},
}


# ── Task entrypoint ───────────────────────────────────────────────────────────

@celery_app.task(name="celery_workers.tasks.poll_status.poll_processing_posts")
def poll_processing_posts() -> dict:
    """Find PROCESSING posts with no recent update and check platform status."""
    return run_async(_async_poll())


async def _async_poll() -> dict:
    from celery_workers.tasks.publish import (
        _get_publish_targets,
        _publish_queue_for,
        _resolve_post_account,
        _update_platform_result,
        _finalize_post_status,
        publish_to_platform,
    )
    from platform_adapters import get_adapter
    from utils.circuit_breaker import can_attempt
    from db.redis_client import get_cache_redis
    from utils.encryption import decrypt

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    cache_redis = get_cache_redis()

    now = datetime.now(timezone.utc)
    polling_cutoff = now - timedelta(minutes=_POLLING_THRESHOLD_MINUTES)
    orphan_cutoff = now - timedelta(minutes=_ORPHAN_CHILD_THRESHOLD_MINUTES)
    stale_cutoff = now - timedelta(hours=_STALE_THRESHOLD_HOURS)

    # Find posts that are still PROCESSING and old enough for either:
    # - orphaned child-task recovery (3 min), or
    # - normal provider polling (10 min).
    candidate_cutoff = orphan_cutoff
    cursor = db.posts.find(
        {
            "status": "processing",
            "updated_at": {"$lt": candidate_cutoff},
        },
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "platforms": 1,
            "platform_results": 1,
            "account_results": 1,
            "publish_targets": 1,
            "post_type": 1,
            "pre_upload_status": 1,
            "updated_at": 1,
            "workspace_id": 1,
        },
        limit=100,  # safety cap per cycle
    )

    polled = 0
    resolved = 0
    requeued = 0

    async for post in cursor:
        post_id = post["id"]
        platform_results = post.get("platform_results", {})
        account_results = post.get("account_results", {})
        post_updated_at = _coerce_utc_datetime(post.get("updated_at")) or now
        is_stale = post_updated_at < stale_cutoff
        is_orphaned = post_updated_at < orphan_cutoff

        for target in _get_publish_targets(post):
            platform = target["platform"]
            target_key = target["target_key"]
            result = account_results.get(target_key) or platform_results.get(platform) or {}
            if result.get("status") not in ("processing", "pending", "retrying"):
                continue

            platform_post_id = result.get("platform_post_id")
            last_attempt_at = _coerce_utc_datetime(result.get("last_attempt_at"))

            if (
                not platform_post_id
                and (
                    not last_attempt_at
                    or (
                        isinstance(last_attempt_at, datetime)
                        and last_attempt_at < orphan_cutoff
                    )
                )
                and is_orphaned
                and post.get("pre_upload_status") not in {"uploading", "pending"}
            ):
                publish_queue = _publish_queue_for(platform, post)
                recovery_queue = "default" if publish_queue == "publish_video" else publish_queue
                publish_to_platform.apply_async(
                    kwargs={
                        "post_id": post_id,
                        "platform": platform,
                        "account_id": target.get("account_id"),
                        "attempt": 0,
                        "dispatch_source": "recovery",
                    },
                    queue=recovery_queue,
                )
                await db.posts.update_one(
                    {"id": post_id},
                    {
                        "$set": {
                            f"account_results.{target_key}.status": "retrying",
                            f"account_results.{target_key}.last_attempt_at": now,
                            f"account_results.{target_key}.error": (
                                "Recovered orphaned publish task"
                                if recovery_queue == publish_queue
                                else "Recovered orphaned publish task via default fallback"
                            ),
                            f"platform_results.{platform}.status": "retrying",
                            f"platform_results.{platform}.last_attempt_at": now,
                            f"platform_results.{platform}.error": (
                                "Recovered orphaned publish task"
                                if recovery_queue == publish_queue
                                else "Recovered orphaned publish task via default fallback"
                            ),
                            "updated_at": now,
                        }
                    },
                )
                logger.warning(
                    "poll_status: requeued orphaned publish task for %s/%s (%s)",
                    post_id,
                    platform,
                    target_key,
                )
                requeued += 1
                continue

            if not platform_post_id:
                continue

            if post_updated_at >= polling_cutoff:
                continue

            if not await can_attempt(cache_redis, platform):
                logger.info(
                    "poll_status: circuit breaker OPEN for %s — skipping post %s",
                    platform, post_id,
                )
                continue

            # If the post is older than stale threshold, mark failed without polling
            if is_stale:
                await _mark_platform_failed(
                    db, post_id, platform, "Exceeded polling timeout — no confirmation received"
                )
                resolved += 1
                continue

            # Query platform API for publish status
            try:
                adapter = get_adapter(platform)
                account_doc = await _resolve_post_account(
                    db,
                    {**post, "user_id": post.get("user_id")},
                    platform,
                    account_id=target.get("account_id"),
                )
                access_token = ""
                if account_doc and account_doc.get("access_token"):
                    try:
                        access_token = decrypt(account_doc["access_token"])
                    except Exception:
                        logger.warning(
                            "poll_status: could not decrypt token for %s/%s",
                            platform,
                            post_id,
                        )
                status = await adapter.check_status(
                    platform_post_id,
                    access_token=access_token,
                    account=account_doc,
                    post=post,
                )
                polled += 1

                if status == "published":
                    await _mark_platform_published(
                        db,
                        post_id,
                        platform,
                        platform_post_id,
                        account_id=target.get("account_id"),
                    )
                    resolved += 1
                elif status == "failed":
                    await _mark_platform_failed(
                        db,
                        post_id,
                        platform,
                        "Platform reported failure",
                        account_id=target.get("account_id"),
                    )
                    resolved += 1
                else:
                    logger.debug(
                        "poll_status: post %s on %s still %s", post_id, platform, status
                    )
            except NotImplementedError:
                # Platform adapter doesn't support check_status — rely on webhooks only
                logger.debug("poll_status: %s does not support check_status", platform)
            except Exception as exc:
                logger.warning(
                    "poll_status: failed to check %s/%s: %s", platform, post_id, exc
                )

    logger.info(
        "poll_status: scanned processing posts, polled=%s resolved=%s requeued=%s",
        polled, resolved,
        requeued,
    )
    return {"polled": polled, "resolved": resolved, "requeued": requeued}


# ── Status update helpers ─────────────────────────────────────────────────────

async def _mark_platform_published(
    db,
    post_id: str,
    platform: str,
    platform_post_id: str,
    *,
    account_id: str | None = None,
) -> None:
    from celery_workers.tasks.publish import _update_platform_result, _finalize_post_status

    now = datetime.now(timezone.utc)
    await _update_platform_result(
        db,
        post_id,
        platform,
        {
            "status": "published",
            "platform_post_id": platform_post_id,
            "confirmed_at": now,
            "published_at": now,
            "error": None,
        },
        account_id=account_id,
    )
    await _finalize_post_status(db, post_id)
    logger.info("poll_status: confirmed %s published on %s", post_id, platform)


async def _mark_platform_failed(
    db,
    post_id: str,
    platform: str,
    reason: str,
    *,
    account_id: str | None = None,
) -> None:
    from celery_workers.tasks.publish import _update_platform_result, _finalize_post_status

    now = datetime.now(timezone.utc)
    await _update_platform_result(
        db,
        post_id,
        platform,
        {
            "status": "failed",
            "error": reason,
            "failed_at": now,
        },
        account_id=account_id,
    )
    await _finalize_post_status(db, post_id)
    logger.warning("poll_status: marked %s failed on %s — %s", post_id, platform, reason)
