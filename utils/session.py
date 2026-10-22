"""
Phase 6.5.3 — Firebase token HttpOnly cookie + JTI blocklist.
Migrates from localStorage to HttpOnly Secure SameSite=Strict cookie.
"""
import logging
import os
import time
from datetime import timedelta

import firebase_admin.auth as fb_auth
from fastapi import HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_COOKIE_NAME = "session"
_DEFAULT_EXPIRES_IN = 3600 * 24 * 5  # 5 days


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        httponly=True,
        secure=os.getenv("ENV", "development") == "production",
        samesite="strict",
        path="/",
    )


async def create_session_cookie(
    response: Response,
    id_token: str,
    expires_in: int = _DEFAULT_EXPIRES_IN,
) -> str:
    """
    Create a Firebase session cookie from an ID token.
    Sets HttpOnly, Secure, SameSite=Strict cookie on response.
    Returns the session cookie string.
    """
    try:
        session_cookie = fb_auth.create_session_cookie(
            id_token,
            expires_in=timedelta(seconds=expires_in),
        )
    except Exception as exc:
        logger.error("Failed to create session cookie: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to create session",
        )

    response.set_cookie(
        key=_COOKIE_NAME,
        value=session_cookie,
        max_age=expires_in,
        httponly=True,
        secure=os.getenv("ENV", "development") == "production",
        samesite="strict",
        path="/",
    )
    return session_cookie


def compute_session_jti(claims: dict) -> str | None:
    """Derive a distinct session identifier so single-session logout does not collide with user sub when iat is present."""
    if claims.get("jti"):
        return str(claims["jti"])
    uid = claims.get("uid") or claims.get("sub")
    iat = claims.get("iat")
    if uid and iat:
        return f"{uid}:{iat}"
    return str(uid) if uid else None


async def verify_claims_not_revoked(claims: dict) -> None:
    """Check both single-session JTI blocklist and user-level revoke_all_sessions blocklist in Redis."""
    from db.redis_client import get_cache_redis

    jti = compute_session_jti(claims)
    sub = claims.get("sub")
    uid = claims.get("uid", sub)

    try:
        cache_redis = get_cache_redis()
    except Exception:
        return

    try:
        for candidate_key in filter(None, {jti, sub}):
            blocked = await cache_redis.get(f"jti_blocklist:{candidate_key}")
            if blocked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked",
                )
        if uid:
            user_blocked = await cache_redis.get(f"jti_blocklist:uid:{uid}")
            if user_blocked:
                revoked_at = float(user_blocked)
                issued_at = claims.get("iat", 0)
                if issued_at <= revoked_at:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="All sessions have been revoked",
                    )
    except HTTPException:
        raise
    except RedisError as exc:
        logger.warning("Skipping session blocklist check because cache Redis is unavailable: %s", exc)
    except Exception as exc:
        logger.debug("Skipping session blocklist check: %s", exc)


async def verify_session_cookie(request: Request) -> dict:
    """
    Read session cookie from request and verify with Firebase.
    Check JTI against Redis blocklist.
    Returns decoded session claims dict.
    """
    session_cookie = request.cookies.get(_COOKIE_NAME)
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie",
        )

    try:
        claims = fb_auth.verify_session_cookie(session_cookie, check_revoked=True)
    except fb_auth.RevokedSessionCookieError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )
    except Exception as exc:
        logger.warning("Session cookie verification failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    await verify_claims_not_revoked(claims)
    return claims


async def revoke_session(cache_redis: Redis, session_claims: dict) -> None:
    """
    Add JTI to Redis blocklist with TTL matching remaining session lifetime.
    Key: jti_blocklist:{jti}
    """
    jti = compute_session_jti(session_claims)
    if not jti:
        return

    # Calculate remaining TTL from expiry
    exp = session_claims.get("exp", 0)
    remaining_ttl = max(int(exp - time.time()), 1)

    try:
        await cache_redis.setex(f"jti_blocklist:{jti}", remaining_ttl, "1")
        logger.info(
            "Session revoked: jti=%s uid=%s ttl=%d",
            jti, session_claims.get("uid", "unknown"), remaining_ttl,
        )
    except RedisError as exc:
        logger.warning("Failed to persist revoked-session blocklist entry: %s", exc)


async def revoke_all_sessions(cache_redis: Redis, uid: str) -> None:
    """
    Revoke all sessions for a user via Firebase and store uid in Redis blocklist.
    """
    try:
        fb_auth.revoke_refresh_tokens(uid)
    except Exception as exc:
        logger.error("Failed to revoke refresh tokens for uid=%s: %s", uid, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke sessions",
        )

    # Store revocation timestamp — sessions issued before this time are invalid.
    # TTL matches max session cookie lifetime (5 days).
    try:
        await cache_redis.setex(
            f"jti_blocklist:uid:{uid}",
            _DEFAULT_EXPIRES_IN,
            str(time.time()),
        )
        logger.info("All sessions revoked for uid=%s", uid)
    except RedisError as exc:
        logger.warning("Failed to persist revoke-all-sessions marker for uid=%s: %s", uid, exc)
