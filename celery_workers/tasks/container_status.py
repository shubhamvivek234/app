"""
EC12 — Non-blocking Instagram container status checks.
Instead of synchronous polling loops, this is a standalone Celery task
that checks once, releases the worker, and retries via Celery countdown.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.encryption import decrypt

logger = logging.getLogger(__name__)

GRAPH_BASE = f"https://graph.facebook.com/{os.environ.get('FACEBOOK_API_VERSION', 'v21.0')}"
_CONTAINER_EXPIRY_HOURS = 24
_MAX_POLL_RETRIES = 30         # 30 × 10s = 5 minutes max polling time
_POLL_COUNTDOWN_SECONDS = 10


@celery_app.task(
    name="celery_workers.tasks.container_status.check_instagram_container_status",
    bind=True,
    max_retries=_MAX_POLL_RETRIES,
    default_retry_delay=_POLL_COUNTDOWN_SECONDS,
)
def check_instagram_container_status(
    self,
    post_id: str,
    container_id: str,
    access_token_encrypted: str,
    poll_attempt: int = 0,
) -> dict:
    """
    EC12: Single-shot container status check. If IN_PROGRESS, raises
    self.retry() with countdown — releases the worker immediately instead
    of blocking in a polling loop.
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_check(self, post_id, container_id, access_token_encrypted, poll_attempt)
    )


async def _async_check(task, post_id, container_id, access_token_encrypted, poll_attempt):
    access_token = decrypt(access_token_encrypted)
    client_db = await get_client()
    db = client_db[os.environ["DB_NAME"]]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
        )

    if resp.status_code != 200:
        logger.warning("EC12: container status check failed HTTP %d for post %s", resp.status_code, post_id)
        raise task.retry(countdown=_POLL_COUNTDOWN_SECONDS, exc=Exception(f"HTTP {resp.status_code}"))

    status_code = resp.json().get("status_code", "")

    if status_code == "FINISHED":
        # Container ready — update post and trigger publish
        now = datetime.now(timezone.utc)
        container_expiry = now + timedelta(hours=_CONTAINER_EXPIRY_HOURS)
        await db.posts.update_one(
            {"id": post_id},
            {
                "$set": {
                    "pre_upload_status": "ready",
                    f"platform_container_ids.instagram": container_id,
                    f"container_expiry_at.instagram": container_expiry,
                    "updated_at": now,
                }
            },
        )
        logger.info("EC12: container %s FINISHED for post %s", container_id, post_id)
        return {"status": "ready", "container_id": container_id}

    if status_code == "ERROR":
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {"pre_upload_status": "failed", "updated_at": datetime.now(timezone.utc)}},
        )
        logger.error("EC12: container %s FAILED for post %s", container_id, post_id)
        return {"status": "failed", "container_id": container_id}

    # IN_PROGRESS — retry (releases worker immediately)
    logger.debug("EC12: container %s still IN_PROGRESS (attempt %d)", container_id, poll_attempt)
    raise task.retry(
        countdown=_POLL_COUNTDOWN_SECONDS,
        kwargs={
            "post_id": post_id,
            "container_id": container_id,
            "access_token_encrypted": access_token_encrypted,
            "poll_attempt": poll_attempt + 1,
        },
    )
