"""
EC15 — Daily subscription expiry check.
Sends warnings, pauses posts after grace period.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

_GRACE_PERIOD_DAYS = 7
_WARNING_DAYS_BEFORE = 7


@celery_app.task(name="celery_workers.tasks.subscription_check.check_expiring_subscriptions")
def check_expiring_subscriptions() -> dict:
    """Daily Beat task: warn users about expiring subscriptions, pause expired posts."""
    return asyncio.get_event_loop().run_until_complete(_async_check())


async def _async_check() -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    warned = 0
    paused_users = 0

    # 1. Warn users whose subscription expires within 7 days
    warning_cutoff = now + timedelta(days=_WARNING_DAYS_BEFORE)
    cursor = db.users.find(
        {
            "subscription_expires_at": {"$lte": warning_cutoff, "$gt": now},
            "subscription_status": "active",
            "expiry_warning_sent": {"$ne": True},
        },
        {"_id": 0, "id": 1, "email": 1, "subscription_expires_at": 1},
    )
    async for user in cursor:
        # Count affected posts
        post_count = await db.posts.count_documents({
            "user_id": user["id"],
            "status": "scheduled",
            "scheduled_time": {"$gt": user.get("subscription_expires_at", now)},
        })
        # Send warning notification
        await db.notifications.insert_one({
            "user_id": user["id"],
            "type": "subscription_expiring",
            "message": f"Your subscription expires soon. {post_count} scheduled posts may be affected.",
            "post_count": post_count,
            "created_at": now,
            "is_read": False,
        })
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"expiry_warning_sent": True}},
        )
        warned += 1

    # 2. Pause posts for users past grace period
    grace_cutoff = now - timedelta(days=_GRACE_PERIOD_DAYS)
    expired_cursor = db.users.find(
        {
            "subscription_expires_at": {"$lte": grace_cutoff},
            "subscription_status": {"$in": ["expired", "past_due"]},
        },
        {"_id": 0, "id": 1},
    )
    async for user in expired_cursor:
        result = await db.posts.update_many(
            {
                "user_id": user["id"],
                "status": "scheduled",
            },
            {"$set": {
                "status": "paused",
                "paused_reason": "subscription_expired",
                "paused_at": now,
            }},
        )
        if result.modified_count > 0:
            paused_users += 1
            await db.notifications.insert_one({
                "user_id": user["id"],
                "type": "posts_paused",
                "message": f"{result.modified_count} posts paused due to expired subscription.",
                "created_at": now,
                "is_read": False,
            })

    logger.info("subscription_check: warned=%d, paused_users=%d", warned, paused_users)
    return {"warned": warned, "paused_users": paused_users}
