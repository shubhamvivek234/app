"""
Shared slowapi limiter instance.
Extracted from api/main.py to break circular import:
  api/main.py → api/routes/* → api/main.py (limiter)

Key function priority:
  1. request.state.user_id  — set by get_current_user dep on authenticated routes
  2. X-Forwarded-For header  — real client IP when behind Cloudflare/Nginx
  3. request.client.host    — direct connection fallback
"""
import os
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    """Use authenticated user_id when available, real client IP otherwise."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    # Trust X-Forwarded-For when behind a reverse proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=_rate_limit_key,
    storage_uri=os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1"),
    # Upstash quota exhaustion or transient Redis outages should not take auth
    # and basic app navigation down. slowapi can transparently fall back to an
    # in-memory limiter for the current process when the shared backend fails.
    in_memory_fallback_enabled=True,
)
