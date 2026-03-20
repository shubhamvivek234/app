"""
Subscription grace period email reminders.
Sends reminders every 2 days + final urgent warning 1 day before cleanup.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_cache_redis

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.grace_period_reminders.send_grace_period_reminders",
    time_limit=1800,       # hard kill after 30 min
    soft_time_limit=1680,  # SoftTimeLimitExceeded raised at 28 min for clean shutdown
)
def send_grace_period_reminders() -> dict:
    """Beat task that runs every 2 days to send grace period reminder emails."""
    return asyncio.run(_async_send_reminders())


async def _async_send_reminders() -> dict:
    """Async implementation of grace period reminders."""
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    cache_redis = get_cache_redis()
    return await _send_grace_period_reminders(db, cache_redis)


async def _send_grace_period_reminders(db, cache_redis) -> dict:
    """
    Send reminders to users in subscription grace period.

    - Days 1, 3, 5, 7, 9, 11, 13, 15, 17, 19+ of grace period: reminder email
    - 1 day before cleanup (subscription_cleanup_date - 1 day): urgent final warning
    """
    now = datetime.now(timezone.utc)
    reminders_sent = 0
    final_warnings_sent = 0

    # Stream users one at a time — never load all expired users into memory at once
    cursor = db.users.find({
        "subscription_status": "expired",
        "subscription_expires_at": {"$exists": True},
    })

    async for user in cursor:
        user_id = user.get("user_id")
        if not user_id:
            continue

        subscription_expires_at = user.get("subscription_expires_at")
        subscription_cleanup_date = user.get("subscription_cleanup_date")

        if not subscription_expires_at:
            continue

        # Calculate days since expiry
        days_since_expiry = (now - subscription_expires_at).days

        # REMINDER LOGIC: Send on odd-numbered days (1, 3, 5, 7, 9, 11, 13, 15, 17, 19...)
        if days_since_expiry > 0 and days_since_expiry % 2 == 1:
            dedup_key = f"grace_reminder:{user_id}:day_{days_since_expiry}"
            is_new = await cache_redis.set(dedup_key, "1", ex=86400 * 21, nx=True)

            if is_new:
                # Use count_documents instead of fetching all posts — no memory allocation
                posts_at_risk = await db.posts.count_documents({
                    "user_id": user_id,
                    "status": "paused",
                    "paused_reason": "subscription_expired",
                })

                # Calculate days remaining until cleanup (should be set by subscription_check.py)
                if subscription_cleanup_date:
                    days_until_cleanup = (subscription_cleanup_date - now).days
                else:
                    # Fallback: assume 20 days from subscription expiry if cleanup_date not set
                    # This shouldn't happen in normal operation
                    days_until_cleanup = 20 - days_since_expiry

                # Insert notification record (email service will pick this up)
                await db.notifications.insert_one({
                    "user_id": user_id,
                    "type": "subscription.grace_reminder",
                    "channel": "email",
                    "message": (
                        f"Your subscription has expired. Your scheduled posts are paused. "
                        f"Please renew your subscription to resume publishing. "
                        f"Your posts will be permanently deleted in {days_until_cleanup} days."
                    ),
                    "metadata": {
                        "days_past_expiry": days_since_expiry,
                        "posts_at_risk": posts_at_risk,
                        "days_until_cleanup": days_until_cleanup,
                    },
                    "created_at": now,
                })

                reminders_sent += 1
                logger.info(
                    "Grace period reminder sent: user=%s days_past_expiry=%d posts_at_risk=%d",
                    user_id, days_since_expiry, posts_at_risk
                )

        # FINAL WARNING: 1 day before cleanup date
        if subscription_cleanup_date:
            days_until_cleanup = (subscription_cleanup_date - now).days

            if days_until_cleanup == 1:
                # Anchor dedup key to cleanup date to ensure it fires only once, even if redis fails
                cleanup_date_str = subscription_cleanup_date.date().isoformat()
                dedup_key = f"grace_final_warning:{user_id}:{cleanup_date_str}"
                is_new = await cache_redis.set(dedup_key, "1", ex=86400 * 30, nx=True)

                if is_new:
                    # Count future posts at risk — no need to fetch full documents
                    posts_at_risk = await db.posts.count_documents({
                        "user_id": user_id,
                        "status": "paused",
                        "paused_reason": "subscription_expired",
                        "scheduled_time": {"$gt": now},
                    })

                    # Insert final warning notification
                    await db.notifications.insert_one({
                        "user_id": user_id,
                        "type": "subscription.grace_final_warning",
                        "channel": "email",
                        "message": (
                            f"⚠️ URGENT: Your scheduled posts will be PERMANENTLY DELETED tomorrow. "
                            f"{posts_at_risk} posts and their media will be removed to free up storage. "
                            f"Purchase now to save your posts and resume publishing."
                        ),
                        "metadata": {
                            "posts_at_risk": posts_at_risk,
                            "final_warning": True,
                            "cleanup_date": subscription_cleanup_date.isoformat(),
                        },
                        "created_at": now,
                    })

                    final_warnings_sent += 1
                    logger.warning(
                        "Final grace period warning sent: user=%s posts_at_risk=%d cleanup_date=%s",
                        user_id, posts_at_risk, subscription_cleanup_date
                    )

    logger.info("Grace period reminders complete: sent=%d final_warnings=%d", reminders_sent, final_warnings_sent)
    return {
        "reminders_sent": reminders_sent,
        "final_warnings_sent": final_warnings_sent,
    }
