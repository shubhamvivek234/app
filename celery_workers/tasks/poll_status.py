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

from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

# Posts stuck in PROCESSING for longer than this are eligible for polling
_POLLING_THRESHOLD_MINUTES = 10
# Maximum staleness before we mark as failed (platform gives up)
_STALE_THRESHOLD_HOURS = 2


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
    return asyncio.get_event_loop().run_until_complete(_async_poll())


async def _async_poll() -> dict:
    from platform_adapters import get_adapter
    from utils.circuit_breaker import can_attempt
    from db.redis_client import get_cache_redis

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    cache_redis = get_cache_redis()

    now = datetime.now(timezone.utc)
    polling_cutoff = now - timedelta(minutes=_POLLING_THRESHOLD_MINUTES)
    stale_cutoff = now - timedelta(hours=_STALE_THRESHOLD_HOURS)

    # Find posts that are still PROCESSING and haven't been updated recently
    cursor = db.posts.find(
        {
            "status": "processing",
            "updated_at": {"$lt": polling_cutoff},
        },
        {
            "_id": 0,
            "id": 1,
            "platform_results": 1,
            "updated_at": 1,
            "workspace_id": 1,
        },
        limit=100,  # safety cap per cycle
    )

    polled = 0
    resolved = 0

    async for post in cursor:
        post_id = post["id"]
        platform_results = post.get("platform_results", {})
        is_stale = post.get("updated_at", now) < stale_cutoff

        for platform, result in platform_results.items():
            if result.get("status") not in ("processing", "pending"):
                continue

            platform_post_id = result.get("platform_post_id")
            if not platform_post_id:
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
                status = await adapter.check_status(platform_post_id)
                polled += 1

                if status == "published":
                    await _mark_platform_published(db, post_id, platform, platform_post_id)
                    resolved += 1
                elif status == "failed":
                    await _mark_platform_failed(db, post_id, platform, "Platform reported failure")
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
        "poll_status: scanned processing posts, polled=%d resolved=%d",
        polled, resolved,
    )
    return {"polled": polled, "resolved": resolved}


# ── Status update helpers ─────────────────────────────────────────────────────

async def _mark_platform_published(db, post_id: str, platform: str, platform_post_id: str) -> None:
    now = datetime.now(timezone.utc)
    await db.posts.update_one(
        {"id": post_id},
        {
            "$set": {
                f"platform_results.{platform}.status": "published",
                f"platform_results.{platform}.confirmed_at": now,
                "updated_at": now,
            }
        },
    )
    logger.info("poll_status: confirmed %s published on %s", post_id, platform)


async def _mark_platform_failed(db, post_id: str, platform: str, reason: str) -> None:
    now = datetime.now(timezone.utc)
    await db.posts.update_one(
        {"id": post_id},
        {
            "$set": {
                f"platform_results.{platform}.status": "failed",
                f"platform_results.{platform}.error": reason,
                f"platform_results.{platform}.failed_at": now,
                "updated_at": now,
            }
        },
    )
    logger.warning("poll_status: marked %s failed on %s — %s", post_id, platform, reason)
