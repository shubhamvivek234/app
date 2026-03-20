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
    from utils.storage import delete_file_async

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    warned = 0
    paused_users = 0
    cleanup_users = 0
    cleanup_posts = 0
    media_deleted = 0

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
        {"_id": 0, "id": 1, "user_id": 1, "subscription_expires_at": 1, "subscription_cleanup_date": 1},
    )
    async for user in expired_cursor:
        user_id = user.get("user_id") or user.get("id")

        # Initialize cleanup date if not already set
        subscription_expires_at = user.get("subscription_expires_at")
        if subscription_expires_at and not user.get("subscription_cleanup_date"):
            cleanup_date = subscription_expires_at + timedelta(days=20)
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"subscription_cleanup_date": cleanup_date}},
            )

        result = await db.posts.update_many(
            {
                "user_id": user_id,
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
                "user_id": user_id,
                "type": "posts_paused",
                "message": f"{result.modified_count} posts paused due to expired subscription.",
                "created_at": now,
                "is_read": False,
            })

    # 3. CLEANUP PHASE: Delete paused posts 20+ days after subscription end date
    cleanup_cursor = db.users.find(
        {
            "subscription_cleanup_date": {"$lte": now},
            "subscription_status": "expired",
        },
        {"_id": 0, "id": 1, "user_id": 1},
    )
    async for user in cleanup_cursor:
        user_id = user.get("user_id") or user.get("id")

        # Find all paused posts that are scheduled for the future
        paused_posts = await db.posts.find({
            "user_id": user_id,
            "status": "paused",
            "paused_reason": "subscription_expired",
            "scheduled_time": {"$gt": now},
        }).to_list(None)

        # Delete each paused post and its media
        for post in paused_posts:
            # Delete media from Cloudflare
            media_ids = post.get("media_ids", [])
            for media_id in media_ids:
                media = await db.media_assets.find_one({"_id": media_id})
                if media and media.get("url"):
                    try:
                        await delete_file_async(media["url"])
                        media_deleted += 1
                    except Exception as exc:
                        logger.error("Failed to delete media: media_id=%s error=%s", media_id, exc)

            # Cancel the post
            await db.posts.update_one(
                {"_id": post["_id"]},
                {"$set": {
                    "status": "cancelled",
                    "cancellation_reason": "cleanup_after_20day_grace",
                    "paused_reason": None,
                    "updated_at": now,
                }},
            )
            cleanup_posts += 1

        if paused_posts:
            cleanup_users += 1
            # Clear subscription_cleanup_date to prevent re-notification on next daily run
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"subscription_cleanup_date": None}},
            )
            await db.notifications.insert_one({
                "user_id": user_id,
                "type": "subscription.posts_deleted",
                "channel": "email",
                "message": (
                    f"Your {len(paused_posts)} scheduled posts have been permanently deleted "
                    f"to free up storage. Resubscribe to schedule new posts."
                ),
                "metadata": {
                    "posts_deleted": len(paused_posts),
                    "media_deleted": media_deleted,
                },
                "created_at": now,
            })

            logger.info(
                "Cleanup complete: user=%s posts_deleted=%d media_deleted=%d",
                user_id, len(paused_posts), media_deleted
            )

    logger.info(
        "subscription_check: warned=%d paused_users=%d cleanup_users=%d cleanup_posts=%d media_deleted=%d",
        warned, paused_users, cleanup_users, cleanup_posts, media_deleted
    )
    return {
        "warned": warned,
        "paused_users": paused_users,
        "cleanup_users": cleanup_users,
        "cleanup_posts": cleanup_posts,
        "media_deleted": media_deleted,
    }
