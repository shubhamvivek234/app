"""
Best-effort Redis helpers.

These helpers are only for cache/state Redis paths where graceful degradation is
acceptable. They are not intended for Celery broker semantics.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_local_locks: dict[str, asyncio.Lock] = {}


def _log(feature: str, key: str | None, exc: Exception) -> None:
    scope = f" key={key}" if key else ""
    logger.warning("%s degraded because Redis is unavailable%s: %s", feature, scope, exc)


async def safe_get(redis, key: str, *, default=None, feature: str = "Redis GET"):
    try:
        return await redis.get(key)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_set(redis, key: str, value, *, ex: int | None = None, nx: bool = False,
                   default=None, feature: str = "Redis SET"):
    try:
        return await redis.set(key, value, ex=ex, nx=nx)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_setex(redis, key: str, ttl: int, value, *, default=None,
                     feature: str = "Redis SETEX"):
    try:
        return await redis.setex(key, ttl, value)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_delete(redis, key: str, *, default=0, feature: str = "Redis DEL"):
    try:
        return await redis.delete(key)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_incr(redis, key: str, *, default=None, feature: str = "Redis INCR"):
    try:
        return await redis.incr(key)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_decr(redis, key: str, *, default=None, feature: str = "Redis DECR"):
    try:
        return await redis.decr(key)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_expire(redis, key: str, ttl: int, *, default=False, feature: str = "Redis EXPIRE"):
    try:
        return await redis.expire(key, ttl)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


async def safe_ttl(redis, key: str, *, default=-1, feature: str = "Redis TTL"):
    try:
        return await redis.ttl(key)
    except RedisError as exc:
        _log(feature, key, exc)
        return default


@asynccontextmanager
async def best_effort_lock(redis, key: str, *, timeout: int = 30, blocking_timeout: int = 25,
                           feature: str = "Redis lock") -> AsyncIterator[None]:
    """
    Use Redis distributed lock when available.
    Falls back to a process-local asyncio.Lock when Redis is unavailable.
    """
    try:
        async with redis.lock(key, timeout=timeout, blocking_timeout=blocking_timeout):
            yield
            return
    except RedisError as exc:
        _log(feature, key, exc)

    lock = _local_locks.setdefault(key, asyncio.Lock())
    async with lock:
        yield
