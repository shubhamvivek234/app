"""
Phase 7.1 — Per-platform circuit breaker stored in Redis.
States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (probing) → CLOSED.
Do NOT count OPEN-circuit requeues as retry failures.
"""
import logging
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD = 5          # failures in window before tripping
FAILURE_WINDOW_SECONDS = 60
OPEN_COOLDOWN_SECONDS = 300    # 5 minutes before HALF_OPEN probe


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


async def get_circuit_state(redis, platform: str) -> CircuitState:
    state_raw = await redis.get(f"circuit:{platform}:state")
    if state_raw is None:
        return CircuitState.CLOSED
    return CircuitState(state_raw)


async def record_success(redis, platform: str) -> None:
    """Called after a successful platform API call. Closes the circuit."""
    state = await get_circuit_state(redis, platform)
    if state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
        await redis.set(f"circuit:{platform}:state", CircuitState.CLOSED)
        await redis.delete(f"circuit:{platform}:failures")
        logger.info("Circuit CLOSED for platform %s (recovered)", platform)


async def record_failure(redis, platform: str) -> CircuitState:
    """
    Called after a failed platform API call.
    Returns the new circuit state so callers can decide how to handle it.
    """
    failure_key = f"circuit:{platform}:failures"
    count = await redis.incr(failure_key)
    await redis.expire(failure_key, FAILURE_WINDOW_SECONDS)

    if count >= FAILURE_THRESHOLD:
        await redis.setex(
            f"circuit:{platform}:state",
            OPEN_COOLDOWN_SECONDS,
            CircuitState.OPEN,
        )
        logger.warning(
            "Circuit OPEN for platform %s (%d failures in %ds) — requeuing with 5min backoff",
            platform, count, FAILURE_WINDOW_SECONDS,
        )
        return CircuitState.OPEN

    return CircuitState.CLOSED


async def can_attempt(redis, platform: str) -> bool:
    """
    Returns True if a call to this platform is allowed.
    CLOSED → always allowed.
    OPEN → not allowed. Requeue the job.
    HALF_OPEN → one probe call allowed (TTL on state key handles transition).
    """
    state = await get_circuit_state(redis, platform)

    if state == CircuitState.CLOSED:
        return True

    if state == CircuitState.OPEN:
        # Check if cooldown has passed (TTL expired → key gone → CLOSED)
        ttl = await redis.ttl(f"circuit:{platform}:state")
        if ttl <= 0:
            # Transition to HALF_OPEN for probe
            await redis.setex(f"circuit:{platform}:state", OPEN_COOLDOWN_SECONDS, CircuitState.HALF_OPEN)
            logger.info("Circuit HALF_OPEN for platform %s — probe call allowed", platform)
            return True
        return False

    # HALF_OPEN — allow exactly one probe call
    return True
