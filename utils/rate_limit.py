"""
Phase 3.1 — Token bucket rate limiting per social_account_id + platform.
Keys are per social_account (not per user) — all users sharing an account share a bucket.
Never count rate-limit hits as retry failures.
"""
import logging

from utils.redis_resilience import safe_decr, safe_get, safe_setex, safe_ttl

logger = logging.getLogger(__name__)

# Platform token limits (publish-operation tokens per window unless noted)
PLATFORM_LIMITS: dict[str, dict] = {
    "instagram": {"tokens_per_window": 25,  "window_seconds": 3600},
    "facebook":  {"tokens_per_window": 200, "window_seconds": 3600},
    # YouTube video publish is a multi-step flow (pre-upload + publish) and may
    # need recovery retries. Keep the local guard conservative but not so strict
    # that one healthy post flow exhausts the account for the whole day.
    "youtube":   {"tokens_per_window": 24,  "window_seconds": 86400},  # per day
    "twitter":   {"tokens_per_window": 300, "window_seconds": 10800},  # per 3h
    "linkedin":  {"tokens_per_window": 150, "window_seconds": 86400},  # per day
    "tiktok":    {"tokens_per_window": 5,   "window_seconds": 86400},  # per day (conservative)
}

_RATE_LIMIT_SCHEMA_VERSION = "v2"


def _bucket_key(platform: str, social_account_id: str, limits: dict) -> str:
    return (
        f"ratelimit:{_RATE_LIMIT_SCHEMA_VERSION}:{platform}:{social_account_id}:"
        f"{limits['tokens_per_window']}:{limits['window_seconds']}:tokens"
    )


async def check_rate_limit(redis, platform: str, social_account_id: str) -> bool:
    """
    Returns True if the request is allowed (tokens available).
    Returns False if rate limited — caller must re-queue, NOT retry.
    """
    limits = PLATFORM_LIMITS.get(platform)
    if limits is None:
        logger.warning("No rate limit config for platform %s — allowing", platform)
        return True

    key = _bucket_key(platform, social_account_id, limits)
    window = limits["window_seconds"]
    max_tokens = limits["tokens_per_window"]

    # Atomic: SETNX (set if not exists) to initialise bucket, then DECR
    current = await safe_get(redis, key, default=None, feature="Platform rate-limit read")
    if current is None:
        # Initialise bucket with max tokens - 1 (consuming one now)
        await safe_setex(redis, key, window, max_tokens - 1, default=True, feature="Platform rate-limit init")
        return True

    current_int = int(current)
    if current_int <= 0:
        logger.warning("Rate limit exceeded: %s/%s (%d tokens)", platform, social_account_id, current_int)
        return False

    await safe_decr(redis, key, default=current_int - 1, feature="Platform rate-limit consume")
    return True


async def pause_account(redis, platform: str, social_account_id: str, pause_seconds: int) -> None:
    """
    Called on HTTP 429 from platform. Pauses all requests for this account.
    Sets tokens to 0 for the specified duration (Retry-After).
    """
    limits = PLATFORM_LIMITS.get(platform)
    if limits is None:
        return
    key = _bucket_key(platform, social_account_id, limits)
    await safe_setex(redis, key, pause_seconds, 0, default=True, feature="Platform rate-limit pause")
    logger.info("Account %s/%s paused for %ds after 429", platform, social_account_id, pause_seconds)


async def get_remaining_tokens(redis, platform: str, social_account_id: str) -> int:
    limits = PLATFORM_LIMITS.get(platform, {})
    if not limits:
        return 0
    key = _bucket_key(platform, social_account_id, limits)
    val = await safe_get(redis, key, default=None, feature="Platform rate-limit remaining")
    if val is None:
        return limits.get("tokens_per_window", 0)
    return max(0, int(val))


async def get_retry_after_seconds(redis, platform: str, social_account_id: str) -> int:
    limits = PLATFORM_LIMITS.get(platform)
    if limits is None:
        return 3600
    key = _bucket_key(platform, social_account_id, limits)
    ttl = await safe_ttl(redis, key, default=-1, feature="Platform rate-limit TTL")
    if ttl is None or int(ttl) <= 0:
        return int(limits["window_seconds"])
    return int(ttl)
