"""
Phase 8.4/8.5 — Plan upgrade/downgrade + failed payment grace period.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ── Plan limits ──────────────────────────────────────────────────────────────

PLAN_LIMITS: dict[str, dict] = {
    "free": {
        "monthly_post_count": 10,
        "max_media_size_mb": 25,
        "connected_accounts": 2,
        "platforms": ["instagram", "facebook"],
        "analytics_retention_days": 7,
        "team_members": 1,
        "ai_captions": False,
    },
    "starter": {
        "monthly_post_count": 50,
        "max_media_size_mb": 100,
        "connected_accounts": 5,
        "platforms": ["instagram", "facebook", "twitter", "linkedin"],
        "analytics_retention_days": 30,
        "team_members": 3,
        "ai_captions": True,
    },
    "professional": {
        "monthly_post_count": 200,
        "max_media_size_mb": 500,
        "connected_accounts": 15,
        "platforms": ["instagram", "facebook", "twitter", "linkedin", "tiktok", "youtube"],
        "analytics_retention_days": 90,
        "team_members": 10,
        "ai_captions": True,
    },
    "enterprise": {
        "monthly_post_count": -1,  # unlimited
        "max_media_size_mb": 2048,
        "connected_accounts": -1,  # unlimited
        "platforms": ["instagram", "facebook", "twitter", "linkedin", "tiktok", "youtube"],
        "analytics_retention_days": 365,
        "team_members": -1,  # unlimited
        "ai_captions": True,
    },
}

# Ordered tiers for upgrade/downgrade detection
_PLAN_ORDER = ["free", "starter", "professional", "enterprise"]

# Retry schedule for failed payments (days after first failure)
_RETRY_SCHEDULE_DAYS = [1, 3, 7]


def _is_upgrade(old_plan: str, new_plan: str) -> bool:
    old_idx = _PLAN_ORDER.index(old_plan) if old_plan in _PLAN_ORDER else 0
    new_idx = _PLAN_ORDER.index(new_plan) if new_plan in _PLAN_ORDER else 0
    return new_idx > old_idx


async def handle_plan_change(
    db,
    user_id: str,
    old_plan: str,
    new_plan: str,
) -> dict:
    """
    Handle plan upgrade or downgrade.

    Downgrade: posts scheduled before the downgrade date continue publishing
    under the old plan limits. New limits apply only to newly created posts.

    Upgrade: new limits apply immediately.

    Stores plan_effective_from on user record.
    Returns change details dict.
    """
    now = datetime.now(timezone.utc)
    is_up = _is_upgrade(old_plan, new_plan)
    old_limits = PLAN_LIMITS.get(old_plan, PLAN_LIMITS["free"])
    new_limits = PLAN_LIMITS.get(new_plan, PLAN_LIMITS["free"])

    update_fields: dict = {
        "plan": new_plan,
        "plan_effective_from": now,
        "previous_plan": old_plan,
        "plan_changed_at": now,
        "updated_at": now,
    }

    if is_up:
        # Upgrade: new limits apply immediately
        update_fields["active_plan_limits"] = new_limits
    else:
        # Downgrade: keep old limits for existing scheduled posts
        update_fields["active_plan_limits"] = new_limits
        update_fields["grandfathered_plan_limits"] = old_limits
        update_fields["grandfathered_until"] = now  # posts created before this use old limits

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": update_fields},
    )

    change_type = "upgrade" if is_up else "downgrade"
    logger.info(
        "Plan %s for user %s: %s -> %s",
        change_type, user_id, old_plan, new_plan,
    )

    return {
        "user_id": user_id,
        "change_type": change_type,
        "old_plan": old_plan,
        "new_plan": new_plan,
        "old_limits": old_limits,
        "new_limits": new_limits,
        "effective_from": now.isoformat(),
    }


async def handle_payment_failure(
    db,
    user_id: str,
    attempt: int,
) -> dict:
    """
    Handle a failed payment attempt.

    Retry schedule: 1 day, 3 days, 7 days after initial failure.
    During retry window: posts continue publishing (don't fail them).
    After 7 days (attempt >= 3): pause (not cancel) all scheduled posts.
    Sends consolidated notification.

    Returns dict with failure state and action taken.
    """
    now = datetime.now(timezone.utc)

    # Determine next retry date
    retry_index = min(attempt - 1, len(_RETRY_SCHEDULE_DAYS) - 1)
    next_retry_days = _RETRY_SCHEDULE_DAYS[retry_index] if attempt <= len(_RETRY_SCHEDULE_DAYS) else None
    next_retry_at = now + timedelta(days=next_retry_days) if next_retry_days else None

    update_fields: dict = {
        "payment_failure_count": attempt,
        "last_payment_failure_at": now,
        "updated_at": now,
    }
    if next_retry_at:
        update_fields["next_payment_retry_at"] = next_retry_at

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": update_fields},
    )

    action = "retry_scheduled"
    paused_count = 0

    # After exhausting retries (7 days), pause posts
    if attempt > len(_RETRY_SCHEDULE_DAYS):
        action = "posts_paused"
        result = await db.posts.update_many(
            {
                "user_id": user_id,
                "status": "scheduled",
                "scheduled_time": {"$gt": now},
            },
            {
                "$set": {
                    "status": "paused",
                    "paused_reason": "payment_failed",
                    "updated_at": now,
                },
            },
        )
        paused_count = result.modified_count

        # Send consolidated notification
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "billing.payment_failed_final",
            "channel": "email",
            "message": (
                f"Payment failed after {attempt} attempts. "
                f"{paused_count} scheduled post(s) have been paused. "
                "Please update your payment method to resume posting."
            ),
            "created_at": now,
            "read": False,
        })
        logger.warning("Payment exhausted for user %s — paused %d posts", user_id, paused_count)
    else:
        # Send retry notification
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "billing.payment_failed",
            "channel": "email",
            "message": (
                f"Payment attempt {attempt} failed. "
                f"We'll retry in {next_retry_days} day(s). "
                "Your scheduled posts will continue publishing during this time."
            ),
            "created_at": now,
            "read": False,
        })
        logger.info("Payment attempt %d failed for user %s, retry in %d days", attempt, user_id, next_retry_days)

    return {
        "user_id": user_id,
        "attempt": attempt,
        "action": action,
        "paused_count": paused_count,
        "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
    }


async def handle_payment_success(db, user_id: str) -> dict:
    """
    Handle successful payment after previous failures.

    Resumes all paused posts and clears payment failure state.
    Returns dict with resume details.
    """
    now = datetime.now(timezone.utc)

    # Clear payment failure state
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "subscription_status": "active",
                "payment_failure_count": 0,
                "updated_at": now,
            },
            "$unset": {
                "last_payment_failure_at": "",
                "next_payment_retry_at": "",
            },
        },
    )

    # Resume posts paused due to payment failure
    result = await db.posts.update_many(
        {
            "user_id": user_id,
            "status": "paused",
            "paused_reason": "payment_failed",
        },
        {
            "$set": {"status": "scheduled", "updated_at": now},
            "$unset": {"paused_reason": ""},
        },
    )
    resumed_count = result.modified_count

    if resumed_count:
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "billing.payment_succeeded",
            "channel": "in_app",
            "message": (
                f"Payment successful! {resumed_count} paused post(s) have been resumed."
            ),
            "created_at": now,
            "read": False,
        })
        logger.info("Payment succeeded for user %s — resumed %d posts", user_id, resumed_count)

    return {
        "user_id": user_id,
        "resumed_count": resumed_count,
        "subscription_status": "active",
    }
