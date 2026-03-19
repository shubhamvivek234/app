"""
Circuit Breaker — Stage 7
Prevents cascading failures when a platform API is consistently failing.
States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
"""
import asyncio
import time
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal — requests flow through
    OPEN = "open"            # Failing — requests rejected immediately
    HALF_OPEN = "half_open"  # Testing — one request allowed through


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,      # Open after 5 consecutive failures
        recovery_timeout: float = 60.0,  # Try again after 60s
        success_threshold: int = 2,      # Close after 2 successes in HALF_OPEN
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def call(self, func, *args, **kwargs):
        """Execute func through the circuit breaker."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.monotonic() - (self.last_failure_time or 0) >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(f"Circuit {self.name}: OPEN → HALF_OPEN (testing recovery)")
                else:
                    remaining = self.recovery_timeout - (time.monotonic() - (self.last_failure_time or 0))
                    raise CircuitOpenError(
                        f"Circuit {self.name} is OPEN. Retry in {remaining:.0f}s."
                    )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info(f"Circuit {self.name}: HALF_OPEN → CLOSED (recovered)")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self, exc: Exception):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name}: HALF_OPEN → OPEN (still failing: {exc})")
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"Circuit {self.name}: CLOSED → OPEN after {self.failure_count} failures. "
                    f"Last error: {exc}"
                )

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
        }


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejects the call."""
    pass


# Global circuit breakers — one per platform
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(platform: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a platform."""
    if platform not in _circuit_breakers:
        _circuit_breakers[platform] = CircuitBreaker(
            name=platform,
            failure_threshold=5,
            recovery_timeout=120.0,  # 2 minutes
            success_threshold=2,
        )
    return _circuit_breakers[platform]


def get_all_circuit_breaker_status() -> list[dict]:
    return [cb.get_status() for cb in _circuit_breakers.values()]
