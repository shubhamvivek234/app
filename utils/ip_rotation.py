"""
Phase 10 -- Outbound IP Pool Rotation.

Round-robin IP selection per platform, backed by Redis for state persistence.
IPs loaded from OUTBOUND_IP_POOL env var (comma-separated).
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Redis key prefix for IP rotation state
_REDIS_PREFIX = "ip_rotation"

# Default pool from environment
_DEFAULT_POOL: tuple[str, ...] = ()


def _load_pool_from_env() -> tuple[str, ...]:
    """Load IP pool from OUTBOUND_IP_POOL env var. Cached at module level."""
    global _DEFAULT_POOL
    if _DEFAULT_POOL:
        return _DEFAULT_POOL
    raw = os.environ.get("OUTBOUND_IP_POOL", "")
    if not raw.strip():
        return ()
    pool = tuple(ip.strip() for ip in raw.split(",") if ip.strip())
    _DEFAULT_POOL = pool
    return pool


async def _get_platform_pool(redis, platform: str) -> list[str]:
    """
    Get the active IP pool for a platform from Redis.

    Falls back to the default env-based pool if no platform-specific
    pool is stored.
    """
    pool_key = f"{_REDIS_PREFIX}:{platform}:pool"
    stored = await redis.lrange(pool_key, 0, -1)
    if stored:
        return [ip.decode() if isinstance(ip, bytes) else ip for ip in stored]

    # Initialize from env
    default = _load_pool_from_env()
    if not default:
        return []

    pool = list(default)
    await redis.delete(pool_key)
    for ip in pool:
        await redis.rpush(pool_key, ip)
    return pool


async def get_outbound_ip(redis, platform: str) -> str:
    """
    Select the next outbound IP for a platform using round-robin.

    Raises ValueError if the IP pool is empty or depleted.
    """
    pool = await _get_platform_pool(redis, platform)
    if not pool:
        raise ValueError(
            f"No outbound IPs available for platform '{platform}'. "
            "Set OUTBOUND_IP_POOL env var or replenish the pool."
        )

    index_key = f"{_REDIS_PREFIX}:{platform}:index"
    current_index = await redis.get(index_key)

    if current_index is None:
        idx = 0
    else:
        idx = int(current_index) % len(pool)

    selected_ip = pool[idx]

    # Advance index for next call
    next_idx = (idx + 1) % len(pool)
    await redis.set(index_key, next_idx)

    logger.debug(
        "Selected outbound IP for %s: %s (index %d/%d)",
        platform, selected_ip, idx, len(pool),
    )
    return selected_ip


async def rotate_ip_pool(redis, platform: str) -> str:
    """
    Mark the current IP as used and advance to the next one.

    Returns the newly selected IP.
    """
    pool = await _get_platform_pool(redis, platform)
    if not pool:
        raise ValueError(f"No outbound IPs available for platform '{platform}'")

    index_key = f"{_REDIS_PREFIX}:{platform}:index"
    current_index = await redis.get(index_key)
    idx = int(current_index) if current_index is not None else 0

    # Move to next
    next_idx = (idx + 1) % len(pool)
    await redis.set(index_key, next_idx)

    new_ip = pool[next_idx]
    logger.info(
        "Rotated IP pool for %s: %s -> %s (index %d -> %d)",
        platform, pool[idx % len(pool)], new_ip, idx, next_idx,
    )
    return new_ip


async def report_ip_blocked(redis, platform: str, ip: str) -> dict[str, Any]:
    """
    Remove a blocked IP from the platform's pool and alert if pool is depleted.

    Returns a summary dict with pool status.
    """
    pool_key = f"{_REDIS_PREFIX}:{platform}:pool"
    blocked_key = f"{_REDIS_PREFIX}:{platform}:blocked"

    # Record the blocked IP
    await redis.sadd(blocked_key, ip)

    # Remove from active pool
    removed_count = await redis.lrem(pool_key, 0, ip)

    # Get remaining pool
    remaining = await redis.lrange(pool_key, 0, -1)
    remaining_ips = [
        r.decode() if isinstance(r, bytes) else r for r in remaining
    ]

    # Reset index if needed
    if remaining_ips:
        index_key = f"{_REDIS_PREFIX}:{platform}:index"
        current_index = await redis.get(index_key)
        if current_index is not None:
            idx = int(current_index)
            if idx >= len(remaining_ips):
                await redis.set(index_key, 0)

    pool_depleted = len(remaining_ips) == 0

    if pool_depleted:
        logger.critical(
            "IP POOL DEPLETED for platform %s! All IPs blocked. "
            "Immediate action required.",
            platform,
        )
    else:
        logger.warning(
            "IP %s blocked for platform %s. %d IPs remaining in pool.",
            ip, platform, len(remaining_ips),
        )

    return {
        "platform": platform,
        "blocked_ip": ip,
        "removed": removed_count > 0,
        "remaining_count": len(remaining_ips),
        "remaining_ips": remaining_ips,
        "pool_depleted": pool_depleted,
    }


async def get_pool_status(redis, platform: str) -> dict[str, Any]:
    """Return the current state of the IP pool for a platform."""
    pool = await _get_platform_pool(redis, platform)
    index_key = f"{_REDIS_PREFIX}:{platform}:index"
    blocked_key = f"{_REDIS_PREFIX}:{platform}:blocked"

    current_index = await redis.get(index_key)
    idx = int(current_index) if current_index is not None else 0

    blocked = await redis.smembers(blocked_key)
    blocked_ips = [b.decode() if isinstance(b, bytes) else b for b in blocked]

    return {
        "platform": platform,
        "pool_size": len(pool),
        "active_ips": pool,
        "current_index": idx,
        "current_ip": pool[idx % len(pool)] if pool else None,
        "blocked_ips": blocked_ips,
    }
