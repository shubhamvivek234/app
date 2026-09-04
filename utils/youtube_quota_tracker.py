"""
YouTube Data API v3 Daily Quota Tracker & Pacing Utility.

Google resets YouTube Data API project quotas daily at midnight Pacific Time
(00:00 PST / PDT). This tracker maintains atomic Redis counters per Pacific date,
preventing unexpected 403 quotaExceeded errors and coordinating rate pacing.

Default Standard Tier: 10,000 units/day (approx 6 video uploads at 1,600 units/upload)
Verified Enterprise Tier: 1,000,000+ units/day (supports 600+ uploads/day)
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_DAILY_QUOTA = int(os.environ.get("YOUTUBE_DAILY_QUOTA_LIMIT", "10000"))

# YouTube Data API v3 operation costs
COST_VIDEO_INSERT = 1600  # Initializing/completing a video upload
COST_VIDEO_UPDATE = 50    # Updating privacy/status or metadata
COST_THUMBNAIL_SET = 50   # Setting custom thumbnail
COST_LIST = 1             # Reading channel/video details


def get_pacific_now() -> datetime:
    """Current time in Pacific Time (PST/PDT)."""
    return datetime.now(PACIFIC_TZ)


def get_pacific_date_and_reset_seconds() -> tuple[str, int]:
    """
    Returns (pacific_date_str "YYYY-MM-DD", seconds_until_midnight_pt).
    Used for Redis key suffix and Retry-After HTTP headers.
    """
    now_pt = get_pacific_now()
    date_str = now_pt.strftime("%Y-%m-%d")
    tomorrow_pt = (now_pt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    seconds_until_midnight = max(int((tomorrow_pt - now_pt).total_seconds()), 60)
    return date_str, seconds_until_midnight


def quota_redis_key(date_str: str | None = None) -> str:
    """Redis key for daily quota counter."""
    if not date_str:
        date_str, _ = get_pacific_date_and_reset_seconds()
    return f"yt:quota:usage:{date_str}"


async def get_quota_status(redis: Any) -> dict[str, Any]:
    """
    Inspect the current Pacific day's YouTube API quota consumption.
    Returns {used, limit, remaining, percent_used, resets_in_seconds, pacific_date}.
    """
    date_str, resets_in = get_pacific_date_and_reset_seconds()
    key = quota_redis_key(date_str)

    used = 0
    if redis:
        try:
            raw = await redis.get(key)
            if raw is not None:
                used = int(raw if isinstance(raw, str) else raw.decode())
        except Exception as exc:
            logger.warning("Could not read YouTube quota from Redis: %s", exc)

    limit = DEFAULT_DAILY_QUOTA
    remaining = max(0, limit - used)
    percent = round((used / limit) * 100, 1) if limit > 0 else 100.0

    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "percent_used": percent,
        "resets_in_seconds": resets_in,
        "pacific_date": date_str,
        "is_exhausted": remaining < COST_VIDEO_UPDATE,
    }


async def check_quota_available(redis: Any, cost: int = COST_VIDEO_INSERT) -> tuple[bool, dict[str, Any]]:
    """
    Check if enough quota units remain for the requested operation.
    Returns (is_available: bool, status_dict).
    """
    status = await get_quota_status(redis)
    is_available = status["remaining"] >= cost
    return is_available, status


async def record_quota_consumption(redis: Any, cost: int = COST_VIDEO_INSERT) -> dict[str, Any]:
    """
    Atomically record quota usage in Redis and set 48h TTL on key creation.
    Returns updated quota status dict.
    """
    date_str, resets_in = get_pacific_date_and_reset_seconds()
    key = quota_redis_key(date_str)

    used = cost
    if redis:
        try:
            used = await redis.incrby(key, cost)
            # Ensure TTL of 48 hours for audit history
            await redis.expire(key, 172800)
        except Exception as exc:
            logger.warning("Could not record YouTube quota consumption in Redis: %s", exc)

    limit = DEFAULT_DAILY_QUOTA
    remaining = max(0, limit - used)
    percent = round((used / limit) * 100, 1) if limit > 0 else 100.0

    status = {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "percent_used": percent,
        "resets_in_seconds": resets_in,
        "pacific_date": date_str,
        "is_exhausted": remaining < COST_VIDEO_UPDATE,
    }

    if percent >= 90.0:
        logger.warning(
            "YouTube API quota at %.1f%% (%d/%d units used). Resets in %d seconds.",
            percent,
            used,
            limit,
            resets_in,
        )

    return status
