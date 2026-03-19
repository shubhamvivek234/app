"""
EC15 — Subscription expiry grace period.
7-day grace period after subscription expiry.
Posts continue publishing during grace period.
After grace period, posts are paused (not cancelled).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_GRACE_PERIOD_DAYS = 7
_WARNING_DAYS_BEFORE_EXPIRY = 7


async def check_subscription_active(db, user_id: str) -> tuple[bool, str]:
    """
    Check whether the user's subscription is active, accounting for grace period.
    Returns (is_active, reason):
        (True,  "active")       — subscription is current
        (True,  "grace_period") — expired but within 7-day grace window
        (False, "expired")      — grace period has also elapsed
        (False, "not_found")    — no user record
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return (False, "not_found")

    now = datetime.now(timezone.utc)

    # If explicit grace period end is set, use that as the source of truth
    grace_end = user.get("subscription_grace_period_end")
    if grace_end is not None:
        if isinstance(grace_end, str):
            grace_end = datetime.fromisoformat(grace_end)
        if grace_end.tzinfo is None:
            grace_end = grace_end.replace(tzinfo=timezone.utc)

        sub_status = user.get("subscription_status", "")
        if sub_status == "active":
            return (True, "active")
        if now <= grace_end:
            return (True, "grace_period")
        return (False, "expired")

    # Fallback: derive from subscription_status alone
    sub_status = user.get("subscription_status", "")
    if sub_status == "active":
        return (True, "active")

    return (False, "expired")


async def pause_expired_user_posts(db, user_id: str) -> int:
    """
    Pause all future scheduled posts for user whose subscription has expired.
    Sets status='paused' and paused_reason='subscription_expired'.
    Returns count of posts paused.
    """
    now = datetime.now(timezone.utc)
    result = await db.posts.update_many(
        {
            "user_id": user_id,
            "status": "scheduled",
            "scheduled_time": {"$gt": now},
        },
        {
            "$set": {
                "status": "paused",
                "paused_reason": "subscription_expired",
                "updated_at": now,
            },
        },
    )
    count = result.modified_count
    if count:
        logger.info("Paused %d posts for expired user %s", count, user_id)
    return count


async def resume_user_posts(db, user_id: str) -> int:
    """
    Resume posts that were paused due to subscription expiry.
    Sets status back to 'scheduled' and clears paused_reason.
    Returns count of resumed posts.
    """
    now = datetime.now(timezone.utc)
    result = await db.posts.update_many(
        {
            "user_id": user_id,
            "status": "paused",
            "paused_reason": "subscription_expired",
        },
        {
            "$set": {"status": "scheduled", "updated_at": now},
            "$unset": {"paused_reason": ""},
        },
    )
    count = result.modified_count
    if count:
        logger.info("Resumed %d posts for user %s", count, user_id)
    return count


async def send_expiry_warnings(db, cache_redis) -> None:
    """
    Celery-callable: scan users approaching or past subscription expiry.
    Sends email warnings at two milestones:
      1. 7 days before expiry
      2. On the day of expiry (includes count of affected posts)
    Uses Redis dedup to send each warning only once.
    """
    now = datetime.now(timezone.utc)
    seven_days_from_now = now + timedelta(days=_WARNING_DAYS_BEFORE_EXPIRY)

    # Users whose subscription expires within 7 days (but not yet expired)
    pre_expiry_cursor = db.users.find({
        "subscription_status": "active",
        "subscription_expires_at": {"$lte": seven_days_from_now, "$gt": now},
    })

    async for user in pre_expiry_cursor:
        user_id = user.get("user_id", "")
        dedup_key = f"expiry_warning:pre:{user_id}"
        already_sent = await cache_redis.set(dedup_key, "1", ex=86400 * 8, nx=True)
        if not already_sent:
            continue
        logger.info(
            "Sending pre-expiry warning to user %s (expires %s)",
            user_id,
            user.get("subscription_expires_at"),
        )
        # Actual email dispatch delegated to notification system
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "subscription.expiring",
            "channel": "email",
            "message": (
                "Your subscription expires in 7 days. "
                "After expiry, you'll have a 7-day grace period before posts are paused."
            ),
            "created_at": now,
            "read": False,
        })

    # Users whose subscription just expired (on expiry day)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    expired_cursor = db.users.find({
        "subscription_status": {"$ne": "active"},
        "subscription_expires_at": {"$gte": day_start, "$lt": day_end},
    })

    async for user in expired_cursor:
        user_id = user.get("user_id", "")
        dedup_key = f"expiry_warning:expired:{user_id}"
        already_sent = await cache_redis.set(dedup_key, "1", ex=86400 * 8, nx=True)
        if not already_sent:
            continue

        # Count affected scheduled posts
        affected_count = await db.posts.count_documents({
            "user_id": user_id,
            "status": "scheduled",
            "scheduled_time": {"$gt": now},
        })

        logger.info(
            "Sending expiry notification to user %s (%d posts affected)",
            user_id,
            affected_count,
        )
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "subscription.expired",
            "channel": "email",
            "message": (
                f"Your subscription has expired. You have a 7-day grace period. "
                f"{affected_count} scheduled post(s) will be paused after the grace period."
            ),
            "created_at": now,
            "read": False,
        })
