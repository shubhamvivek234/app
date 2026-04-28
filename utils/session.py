"""
Phase 6.5.3 — Firebase token HttpOnly cookie + JTI blocklist.
Migrates from localStorage to HttpOnly Secure SameSite=Strict cookie.
"""
import logging
import time
from datetime import timedelta

import firebase_admin.auth as fb_auth
from fastapi import HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_COOKIE_NAME = "session"
_DEFAULT_EXPIRES_IN = 3600 * 24 * 5  # 5 days


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
        secure=True,
        samesite="strict",
        path="/",
    )
    return session_cookie


async def verify_session_cookie(request: Request) -> dict:
    """
    Read session cookie from request and verify with Firebase.
    Check JTI against Redis blocklist.
    Returns decoded session claims dict.
    """
    from db.redis_client import get_cache_redis

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

    # Check JTI blocklist in Redis
    jti = claims.get("jti") or claims.get("sub")
    uid = claims.get("uid", claims.get("sub"))

    cache_redis = get_cache_redis()
    try:
        # Check individual JTI blocklist
        if jti:
            blocked = await cache_redis.get(f"jti_blocklist:{jti}")
            if blocked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked",
                )
        # Check user-level blocklist (revoke_all_sessions)
        if uid:
            user_blocked = await cache_redis.get(f"jti_blocklist:uid:{uid}")
            if user_blocked:
                # Check if session was issued before the revocation timestamp
                revoked_at = float(user_blocked)
                issued_at = claims.get("iat", 0)
                if issued_at <= revoked_at:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="All sessions have been revoked",
                    )
    except RedisError as exc:
        logger.warning("Skipping session blocklist check because cache Redis is unavailable: %s", exc)

    return claims


async def revoke_session(cache_redis: Redis, session_claims: dict) -> None:
    """
    Add JTI to Redis blocklist with TTL matching remaining session lifetime.
    Key: jti_blocklist:{jti}
    """
    jti = session_claims.get("jti") or session_claims.get("sub")
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
