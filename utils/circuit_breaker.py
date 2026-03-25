"""
Phase 7.1 — Per-account circuit breaker stored in Redis.
States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (probing) → CLOSED.

Keyed by account_id (not platform) so one user's bad token does not block
all other users' posts to the same platform. Falls back to platform-level
key when account_id is not available (e.g. during reconciliation).

Do NOT count OPEN-circuit requeues as retry failures.
"""
import logging
from enum import Enum

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD = 5          # failures in window before tripping
FAILURE_WINDOW_SECONDS = 60
OPEN_COOLDOWN_SECONDS = 300    # 5 minutes before HALF_OPEN probe


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


def _key(platform: str, account_id: str | None) -> str:
    """Per-account key when available, platform-wide fallback otherwise."""
    if account_id:
        return f"circuit:{platform}:{account_id}"
    return f"circuit:{platform}"


async def get_circuit_state(redis, platform: str, account_id: str | None = None) -> CircuitState:
    state_raw = await redis.get(f"{_key(platform, account_id)}:state")
    if state_raw is None:
        return CircuitState.CLOSED
    return CircuitState(state_raw)


async def record_success(redis, platform: str, account_id: str | None = None) -> None:
    """Called after a successful platform API call. Closes the circuit."""
    base = _key(platform, account_id)
    state = await get_circuit_state(redis, platform, account_id)
    if state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
        await redis.set(f"{base}:state", CircuitState.CLOSED)
        await redis.delete(f"{base}:failures")
        logger.info("Circuit CLOSED for %s (recovered)", base)


async def record_failure(redis, platform: str, account_id: str | None = None) -> CircuitState:
    """
    Called after a failed platform API call.
    Returns the new circuit state so callers can decide how to handle it.
    """
    base = _key(platform, account_id)
    failure_key = f"{base}:failures"
    count = await redis.incr(failure_key)
    await redis.expire(failure_key, FAILURE_WINDOW_SECONDS)

    if count >= FAILURE_THRESHOLD:
        await redis.setex(
            f"{base}:state",
            OPEN_COOLDOWN_SECONDS,
            CircuitState.OPEN,
        )
        logger.warning(
            "Circuit OPEN for %s (%d failures in %ds) — requeuing with 5min backoff",
            base, count, FAILURE_WINDOW_SECONDS,
        )
        return CircuitState.OPEN

    return CircuitState.CLOSED


async def can_attempt(redis, platform: str, account_id: str | None = None) -> bool:
    """
    Returns True if a call to this platform/account is allowed.
    CLOSED → always allowed.
    OPEN → not allowed. Requeue the job.
    HALF_OPEN → one probe call allowed (TTL on state key handles transition).
    """
    base = _key(platform, account_id)
    state = await get_circuit_state(redis, platform, account_id)

    if state == CircuitState.CLOSED:
        return True

    if state == CircuitState.OPEN:
        # Check if cooldown has passed (TTL expired → key gone → CLOSED)
        ttl = await redis.ttl(f"{base}:state")
        if ttl <= 0:
            # Transition to HALF_OPEN for probe
            await redis.setex(f"{base}:state", OPEN_COOLDOWN_SECONDS, CircuitState.HALF_OPEN)
            logger.info("Circuit HALF_OPEN for %s — probe call allowed", base)
            return True
        return False

    # HALF_OPEN — allow exactly one probe call
    return True
