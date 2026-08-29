"""
RSS Feed Polling Background Task.
Periodically fetches active RSS feeds, deduplicates incoming items,
and auto-schedules social media posts into user timeslots.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from api.routes.rss_feeds import _sync_feed_items

logger = logging.getLogger(__name__)

# Register beat schedule for automatic feed polling
celery_app.conf.beat_schedule["poll-rss-feeds"] = {
    "task": "celery_workers.tasks.rss_poller.poll_all_active_rss_feeds",
    "schedule": 1800,  # every 30 minutes
    "options": {"queue": "default"},
}


@celery_app.task(
    name="celery_workers.tasks.rss_poller.poll_all_active_rss_feeds",
    time_limit=300,
)
def poll_all_active_rss_feeds() -> dict:
    """Poll all active RSS feeds across all workspaces."""
    return run_async(_async_poll_all_feeds())


async def _async_poll_all_feeds() -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    cursor = db.rss_feeds.find({"status": "active"})
    active_feeds = await cursor.to_list(None)

    total_feeds = len(active_feeds)
    total_discovered = 0
    total_scheduled = 0
    errors = 0

    for feed in active_feeds:
        try:
            workspace_id = feed.get("workspace_id")
            user_id = feed.get("user_id")
            stats = await _sync_feed_items(db, feed, user_id=user_id, workspace_id=workspace_id)
            total_discovered += stats.get("discovered", 0)
            total_scheduled += stats.get("scheduled", 0)
            if stats.get("errors", 0) > 0:
                errors += 1
        except Exception as exc:
            logger.error("Failed to poll RSS feed %s: %s", feed.get("id"), exc)
            errors += 1

    logger.info(
        "RSS Feeds Polling Complete: feeds=%d discovered=%d scheduled=%d errors=%d",
        total_feeds,
        total_discovered,
        total_scheduled,
        errors,
    )

    return {
        "status": "success",
        "total_feeds": total_feeds,
        "total_discovered": total_discovered,
        "total_scheduled": total_scheduled,
        "errors": errors,
    }
