"""
Phase 2.6.3 (EC17) — Redis→MongoDB reconciliation.
Runs every 5 minutes. Finds Redis confirmation keys and syncs unupdated MongoDB records.
"""
import json
import logging
import os
from datetime import datetime

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.reconcile.reconcile_confirmations",
    bind=True,
)
def reconcile_confirmations(self) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_reconcile())


async def _async_reconcile() -> dict:
    from db.mongo import get_client
    from db.redis_client import get_cache_redis

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    r = get_cache_redis()

    # Scan Redis for all confirmed:{post_id}:{platform} keys
    synced = 0
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor=cursor, match="confirmed:*:*", count=100)
        for key in keys:
            parts = key.split(":", 2)
            if len(parts) != 3:
                continue
            _, post_id, platform = parts

            try:
                raw = await r.get(key)
                if not raw:
                    continue
                payload = json.loads(raw)

                # Check if MongoDB is already synced
                post = await db.posts.find_one(
                    {"id": post_id},
                    {f"platform_results.{platform}.status": 1},
                )
                if not post:
                    continue

                current_status = (post.get("platform_results") or {}).get(platform, {}).get("status")
                if current_status != "published":
                    # Sync MongoDB from Redis confirmation
                    await db.posts.update_one(
                        {"id": post_id},
                        {"$set": {
                            f"platform_results.{platform}.status": "published",
                            f"platform_results.{platform}.post_url": payload.get("post_url"),
                            f"platform_results.{platform}.published_at": payload.get("published_at"),
                        }},
                    )
                    logger.info("Reconciled %s/%s from Redis confirmation", post_id, platform)
                    synced += 1
            except Exception as exc:
                logger.error("Reconcile error for key %s: %s", key, exc)

        if cursor == 0:
            break

    return {"synced": synced}


@celery_app.task(
    name="celery_workers.tasks.reconcile.send_notification",
)
def send_notification(post_id: str, type: str, platform: str | None = None, error: str | None = None) -> None:
    """Stub — integrate with Resend or notification service."""
    logger.info("Notification: type=%s post_id=%s platform=%s", type, post_id, platform)
