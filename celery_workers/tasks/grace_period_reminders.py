"""
Subscription grace period email reminders.
Sends reminders every 2 days + final urgent warning 1 day before cleanup.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from db.redis_client import get_cache_redis
from utils.notifications import emit_notification
from utils.redis_resilience import safe_set

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.grace_period_reminders.send_grace_period_reminders",
    time_limit=1800,       # hard kill after 30 min
    soft_time_limit=1680,  # SoftTimeLimitExceeded raised at 28 min for clean shutdown
)
def send_grace_period_reminders() -> dict:
    """Beat task that runs every 2 days to send grace period reminder emails."""
    return run_async(_async_send_reminders())


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
            for channel in ("email", "in_app"):
                dedup_key = f"grace_reminder:{user_id}:day_{days_since_expiry}:{channel}"
                is_new = await safe_set(
                    cache_redis,
                    dedup_key,
                    "1",
                    ex=86400 * 21,
                    nx=True,
                    default=True,
                    feature="Grace reminder dedup",
                )

                inserted = await _ensure_notification_once(
                    db,
                    event="subscription.expiring",
                    channel=channel,
                    dedup_key=dedup_key,
                    payload_builder=lambda posts_at_risk, days_until_cleanup, *, current_channel=channel, current_dedup_key=dedup_key: {
                        "user_id": user_id,
                        "type": "subscription.grace_reminder",
                        "channel": current_channel,
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
                        "dedup_key": current_dedup_key,
                    },
                    user_id=user_id,
                    now=now,
                    subscription_cleanup_date=subscription_cleanup_date,
                    days_since_expiry=days_since_expiry,
                )
                if is_new and inserted:
                    reminders_sent += 1
                    logger.info(
                        "Grace period reminder queued: user=%s channel=%s days_past_expiry=%d",
                        user_id, channel, days_since_expiry
                    )

        # FINAL WARNING: 1 day before cleanup date
        if subscription_cleanup_date:
            days_until_cleanup = (subscription_cleanup_date - now).days

            if days_until_cleanup == 1:
                for channel in ("email", "in_app"):
                    cleanup_date_str = subscription_cleanup_date.date().isoformat()
                    dedup_key = f"grace_final_warning:{user_id}:{cleanup_date_str}:{channel}"
                    is_new = await safe_set(
                        cache_redis,
                        dedup_key,
                        "1",
                        ex=86400 * 30,
                        nx=True,
                        default=True,
                        feature="Grace final-warning dedup",
                    )

                    if is_new:
                        inserted = await _ensure_notification_once(
                            db,
                            event="subscription.expiring",
                            channel=channel,
                            dedup_key=dedup_key,
                            payload_builder=lambda posts_at_risk, _days_until_cleanup, *, current_channel=channel, current_dedup_key=dedup_key: {
                                "user_id": user_id,
                                "type": "subscription.grace_final_warning",
                                "channel": current_channel,
                                "message": (
                                    f"Your scheduled posts will be permanently deleted tomorrow. "
                                    f"{posts_at_risk} posts and their media will be removed unless you renew in time."
                                ),
                                "metadata": {
                                    "posts_at_risk": posts_at_risk,
                                    "final_warning": True,
                                    "cleanup_date": subscription_cleanup_date.isoformat(),
                                },
                                "created_at": now,
                                "dedup_key": current_dedup_key,
                            },
                            user_id=user_id,
                            now=now,
                            subscription_cleanup_date=subscription_cleanup_date,
                            days_since_expiry=days_since_expiry,
                        )
                    else:
                        inserted = False

                    if inserted:
                        final_warnings_sent += 1
                        logger.warning(
                            "Final grace period warning queued: user=%s channel=%s cleanup_date=%s",
                            user_id, channel, subscription_cleanup_date
                        )

    logger.info("Grace period reminders complete: sent=%d final_warnings=%d", reminders_sent, final_warnings_sent)
    return {
        "reminders_sent": reminders_sent,
        "final_warnings_sent": final_warnings_sent,
    }


async def _ensure_notification_once(
    db,
    *,
    event: str,
    channel: str,
    dedup_key: str,
    payload_builder,
    user_id: str,
    now: datetime,
    subscription_cleanup_date,
    days_since_expiry: int,
) -> bool:
    posts_at_risk = await db.posts.count_documents({
        "user_id": user_id,
        "status": "paused",
        "paused_reason": "subscription_expired",
    })
    if subscription_cleanup_date:
        days_until_cleanup = (subscription_cleanup_date - now).days
    else:
        days_until_cleanup = 20 - days_since_expiry

    payload = payload_builder(posts_at_risk, days_until_cleanup)
    written = await emit_notification(
        db,
        user_id=user_id,
        event=event,
        channels=(channel,),
        notification_type=payload.get("type", "subscription.expiring"),
        title="Subscription needs attention",
        message=payload.get("message", "Your subscription needs attention."),
        severity="high" if payload.get("metadata", {}).get("final_warning") else "medium",
        metadata=payload.get("metadata", {}),
        target_path="/billing",
        dedup_key=dedup_key,
        created_at=now,
    )
    return bool(written)
