"""
Shared slowapi limiter instance.
Extracted from api/main.py to break circular import:
  api/main.py → api/routes/* → api/main.py (limiter)

Key function priority:
  1. request.state.user_id  — set by get_current_user dep on authenticated routes
  2. X-Forwarded-For header  — real client IP when behind Cloudflare/Nginx
  3. request.client.host    — direct connection fallback
"""
import ipaddress
import os
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

_TRUSTED_PROXIES = {
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
}


def _is_trusted_proxy(client_host: str | None) -> bool:
    if not client_host:
        return False
    try:
        ip = ipaddress.ip_address(client_host)
        return any(ip in net for net in _TRUSTED_PROXIES)
    except ValueError:
        return False


def _rate_limit_key(request: Request) -> str:
    """Use authenticated user_id when available, real client IP otherwise."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    client_host = request.client.host if request.client else None
    # Only trust X-Forwarded-For when connection originates from a trusted reverse proxy
    if _is_trusted_proxy(client_host):
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
