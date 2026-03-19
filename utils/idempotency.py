"""
Phase 2.5.1 (EC1) — Idempotency key management.
Prevents duplicate posts when a worker retries after network failures.
Key = SHA256(post_id + platform + attempt_number), stored in Redis 24h.
"""
import hashlib
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

KEY_TTL = 86400  # 24 hours
CONFIRMATION_TTL = 86400 * 3  # EC29: 72 hours for Instagram error 9007


def make_idempotency_key(post_id: str, platform: str, attempt: int) -> str:
    """SHA256(post_id + platform + attempt) — deterministic, never guessable."""
    raw = f"{post_id}:{platform}:{attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def check_idempotency(redis, post_id: str, platform: str, attempt: int) -> dict | None:
    """
    Check if this (post_id, platform, attempt) was already successfully executed.
    Returns the stored result dict if found, None if this is a fresh attempt.
    """
    key = f"idempotency:{make_idempotency_key(post_id, platform, attempt)}"
    raw = await redis.get(key)
    if raw:
        logger.info("Idempotency hit for %s/%s attempt %d", post_id, platform, attempt)
        return json.loads(raw)
    return None


async def mark_idempotency(
    redis,
    post_id: str,
    platform: str,
    attempt: int,
    result: dict,
    ttl: int = KEY_TTL,
) -> None:
    """Store the result so future retries can short-circuit."""
    key = f"idempotency:{make_idempotency_key(post_id, platform, attempt)}"
    await redis.setex(key, ttl, json.dumps(result))
    logger.debug("Stored idempotency key for %s/%s attempt %d", post_id, platform, attempt)


async def get_container_id(redis, post_id: str, platform: str) -> str | None:
    """Retrieve pre-uploaded container ID stored during pre_upload_task."""
    key = f"idempotency:{make_idempotency_key(post_id, platform, 0)}"
    raw = await redis.get(key)
    if raw:
        data = json.loads(raw)
        return data.get("container_id")
    return None
