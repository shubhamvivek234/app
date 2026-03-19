"""
EC16 — Ghost account cascade.
When a platform bans/suspends a user's account, cascade-cancel all future posts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def handle_ghost_account(
    db,
    social_account_id: str,
    error_code,
    suspension_reason: str,
) -> dict:
    """
    Handle a platform ban/suspension for a social account.

    1. Deactivate the social account and record the suspension reason.
    2. Pause (not delete) all future scheduled posts for this account.
    3. Send one consolidated notification to the user.

    Returns {"paused_count": int, "account_id": str}.
    """
    now = datetime.now(timezone.utc)

    # 1. Mark the social account as inactive
    account = await db.social_accounts.find_one_and_update(
        {"account_id": social_account_id},
        {
            "$set": {
                "is_active": False,
                "suspension_reason": error_code,
                "suspended_at": now,
                "updated_at": now,
            },
        },
        return_document=True,
    )

    if not account:
        logger.warning("Social account %s not found for ghost cascade", social_account_id)
        return {"paused_count": 0, "account_id": social_account_id}

    user_id = account.get("user_id", "")
    platform = account.get("platform", "unknown")

    # 2. Pause all future scheduled posts targeting this social account
    result = await db.posts.update_many(
        {
            "social_account_id": social_account_id,
            "status": "scheduled",
            "scheduled_time": {"$gt": now},
        },
        {
            "$set": {
                "status": "paused",
                "paused_reason": "account_suspended",
                "updated_at": now,
            },
        },
    )
    paused_count = result.modified_count

    # Also check posts that reference this account in a platforms list
    result_multi = await db.posts.update_many(
        {
            "platform_account_ids": social_account_id,
            "status": "scheduled",
            "scheduled_time": {"$gt": now},
        },
        {
            "$set": {
                "status": "paused",
                "paused_reason": "account_suspended",
                "updated_at": now,
            },
        },
    )
    paused_count += result_multi.modified_count

    # 3. Send ONE consolidated notification
    account_name = account.get("account_name", account.get("username", social_account_id))
    await db.notifications.insert_one({
        "user_id": user_id,
        "type": "account.suspended",
        "channel": "email",
        "message": (
            f"Your {platform} account '{account_name}' has been suspended by the platform. "
            f"Reason: {suspension_reason}. "
            f"{paused_count} scheduled post(s) have been paused. "
            "Reconnect the account after resolving the issue to resume posting."
        ),
        "metadata": {
            "social_account_id": social_account_id,
            "platform": platform,
            "error_code": str(error_code),
            "paused_count": paused_count,
        },
        "created_at": now,
        "read": False,
    })

    logger.info(
        "Ghost cascade complete: account=%s platform=%s paused=%d reason=%s",
        social_account_id,
        platform,
        paused_count,
        suspension_reason,
    )

    return {"paused_count": paused_count, "account_id": social_account_id}
