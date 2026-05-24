"""
Phase 0.5 — Two separate Redis pools.
redis-queue  → noeviction policy  (Celery broker, NEVER lose jobs)
redis-cache  → allkeys-lru policy (rate limits, sessions, safe to evict)
"""
import os
import logging
from redis.asyncio import Redis, ConnectionPool

logger = logging.getLogger(__name__)

_queue_pool: ConnectionPool | None = None
_cache_pool: ConnectionPool | None = None
_queue_pool_pid: int | None = None
_cache_pool_pid: int | None = None


def _make_pool(url: str) -> ConnectionPool:
    return ConnectionPool.from_url(
        url,
        max_connections=50,   # raised from 20 — supports 5 pods × 8 workers with headroom
        socket_connect_timeout=5,
        socket_timeout=10,
        retry_on_timeout=True,
        decode_responses=True,
    )


def get_queue_pool() -> ConnectionPool:
    """Broker pool — noeviction Redis. Used by Celery + job tracking."""
    global _queue_pool, _queue_pool_pid
    current_pid = os.getpid()
    if _queue_pool is None or _queue_pool_pid != current_pid:
        _queue_pool = _make_pool(os.environ["REDIS_QUEUE_URL"])
        _queue_pool_pid = current_pid
    return _queue_pool


def get_cache_pool() -> ConnectionPool:
    """Cache pool — allkeys-lru Redis. Used for rate limits, sessions, idempotency."""
    global _cache_pool, _cache_pool_pid
    current_pid = os.getpid()
    if _cache_pool is None or _cache_pool_pid != current_pid:
        _cache_pool = _make_pool(os.environ["REDIS_CACHE_URL"])
        _cache_pool_pid = current_pid
    return _cache_pool


def get_queue_redis() -> Redis:
    return Redis(connection_pool=get_queue_pool())


def get_cache_redis() -> Redis:
    return Redis(connection_pool=get_cache_pool())


async def close_pools() -> None:
    global _queue_pool, _cache_pool, _queue_pool_pid, _cache_pool_pid
    if _queue_pool:
        await _queue_pool.aclose()
        _queue_pool = None
        _queue_pool_pid = None
    if _cache_pool:
        await _cache_pool.aclose()
        _cache_pool = None
        _cache_pool_pid = None
    logger.info("Redis connection pools closed")
