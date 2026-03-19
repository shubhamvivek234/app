"""
Phase 3.1 — Token bucket rate limiting per social_account_id + platform.
Keys are per social_account (not per user) — all users sharing an account share a bucket.
Never count rate-limit hits as retry failures.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Platform token limits (posts per hour unless noted)
PLATFORM_LIMITS: dict[str, dict] = {
    "instagram": {"tokens_per_window": 25,  "window_seconds": 3600},
    "facebook":  {"tokens_per_window": 200, "window_seconds": 3600},
    "youtube":   {"tokens_per_window": 6,   "window_seconds": 86400},  # per day
    "twitter":   {"tokens_per_window": 300, "window_seconds": 10800},  # per 3h
    "linkedin":  {"tokens_per_window": 150, "window_seconds": 86400},  # per day
    "tiktok":    {"tokens_per_window": 5,   "window_seconds": 86400},  # per day (conservative)
}


async def check_rate_limit(redis, platform: str, social_account_id: str) -> bool:
    """
    Returns True if the request is allowed (tokens available).
    Returns False if rate limited — caller must re-queue, NOT retry.
    """
    limits = PLATFORM_LIMITS.get(platform)
    if limits is None:
        logger.warning("No rate limit config for platform %s — allowing", platform)
        return True

    key = f"ratelimit:{platform}:{social_account_id}:tokens"
    window = limits["window_seconds"]
    max_tokens = limits["tokens_per_window"]

    # Atomic: SETNX (set if not exists) to initialise bucket, then DECR
    current = await redis.get(key)
    if current is None:
        # Initialise bucket with max tokens - 1 (consuming one now)
        await redis.setex(key, window, max_tokens - 1)
        return True

    current_int = int(current)
    if current_int <= 0:
        logger.warning("Rate limit exceeded: %s/%s (%d tokens)", platform, social_account_id, current_int)
        return False

    await redis.decr(key)
    return True


async def pause_account(redis, platform: str, social_account_id: str, pause_seconds: int) -> None:
    """
    Called on HTTP 429 from platform. Pauses all requests for this account.
    Sets tokens to 0 for the specified duration (Retry-After).
    """
    key = f"ratelimit:{platform}:{social_account_id}:tokens"
    await redis.setex(key, pause_seconds, 0)
    logger.info("Account %s/%s paused for %ds after 429", platform, social_account_id, pause_seconds)


async def get_remaining_tokens(redis, platform: str, social_account_id: str) -> int:
    key = f"ratelimit:{platform}:{social_account_id}:tokens"
    val = await redis.get(key)
    if val is None:
        return PLATFORM_LIMITS.get(platform, {}).get("tokens_per_window", 0)
    return max(0, int(val))
