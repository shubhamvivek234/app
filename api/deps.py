"""
Shared FastAPI dependencies — db, redis, current user, permission checks.
"""
import os
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from db.mongo import get_db
from db.redis_client import get_cache_redis, get_queue_redis
from utils.roles import has_permission
from utils.session import verify_session_cookie

logger = logging.getLogger(__name__)

# ── Firebase Admin SDK initialisation ──────────────────────────────────────
_firebase_app: firebase_admin.App | None = None


def get_firebase_credential_path() -> str:
    cred_path = os.environ.get("FIREBASE_ADMIN_SDK_JSON", "/app/serviceAccountKey.json")
    if not Path(cred_path).is_file():
        raise RuntimeError(
            "Firebase Admin SDK credential file not found. "
            f"Expected FIREBASE_ADMIN_SDK_JSON at '{cred_path}'."
        )
    return cred_path


def get_firebase_app() -> firebase_admin.App:
    global _firebase_app
    if _firebase_app is None:
        cred_path = get_firebase_credential_path()
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized from %s", cred_path)
    return _firebase_app


async def _bootstrap_user_from_claims(
    db: AsyncIOMotorDatabase,
    decoded: dict,
) -> dict:
    """
    Resolve a MongoDB user from verified Firebase claims, auto-creating a record
    on first login when needed.

    We also recover gracefully from older records that exist by email but do not
    yet have firebase_uid populated.
    """
    uid = decoded.get("uid")
    email = decoded.get("email", uid)
    display_name = decoded.get("name")

    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
    if user is not None:
        return user

    if email:
        user = await db.users.find_one({"email": email}, {"_id": 0})
        if user is not None:
            updates = {}
            if uid and not user.get("firebase_uid"):
                updates["firebase_uid"] = uid
            if display_name and not user.get("display_name"):
                updates["display_name"] = display_name
            if updates:
                await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
                user.update(updates)
                logger.info("Backfilled Firebase identity for existing user %s", user["user_id"])
            return user

    now = datetime.now(timezone.utc)
    user_doc = {
        "user_id": f"usr_{secrets.token_hex(12)}",
        "firebase_uid": uid,
        "email": email,
        "display_name": display_name,
        "avatar_url": decoded.get("picture"),
        "plan": "starter",
        "subscription_status": "free",
        "subscription_end_date": None,
        "subscription_grace_period_end": None,
        "timezone": "UTC",
        "mfa_enabled": False,
        "role": "user",
        "onboarding_completed": False,
        "workspace_ids": [],
        "default_workspace_id": None,
        "created_at": now,
    }
    try:
        await db.users.insert_one(user_doc)
        logger.info("Auto-created user from Firebase login: %s", user_doc["user_id"])
        return user_doc
    except DuplicateKeyError:
        # Another request likely created the user concurrently. Re-read to keep
        # sign-in stable instead of failing the request.
        logger.info("User bootstrap raced with another request for email=%s uid=%s", email, uid)
        if uid:
            user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
            if user is not None:
                return user
        if email:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if user is not None:
                return user
        raise


# ── Security scheme ─────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> dict:
    """
    Verify Firebase JWT. Returns the MongoDB user document.
    Raises 401 if token is missing/invalid.
    Sets request.state.user_id so the rate limiter can key by user.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        get_firebase_app()
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user = await _bootstrap_user_from_claims(db, decoded)
    except DuplicateKeyError:
        logger.exception("User bootstrap failed after duplicate-key recovery")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile is still being prepared. Please try again.",
        )

    request.state.user_id = user["user_id"]
    return user


async def get_current_user_from_cookie(
    request: Request,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> dict:
    """
    Alternative auth dependency using HttpOnly session cookie instead of
    Authorization header. Verifies the Firebase session cookie and checks
    the JTI against the Redis blocklist.
    Sets request.state.user_id so the rate limiter can key by user.
    """
    get_firebase_app()
    claims = await verify_session_cookie(request)

    try:
        user = await _bootstrap_user_from_claims(db, claims)
    except DuplicateKeyError:
        logger.exception("Cookie user bootstrap failed after duplicate-key recovery")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile is still being prepared. Please try again.",
        )

    request.state.user_id = user["user_id"]
    return user


# ── Convenience type aliases ─────────────────────────────────────────────────
CurrentUser = Annotated[dict, Depends(get_current_user)]
CookieUser = Annotated[dict, Depends(get_current_user_from_cookie)]
DB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
CacheRedis = Annotated[Redis, Depends(get_cache_redis)]
QueueRedis = Annotated[Redis, Depends(get_queue_redis)]


# ── Permission dependency factory ────────────────────────────────────────────

def require_permission(permission: str):
    """
    Returns a FastAPI dependency that verifies the current user has the
    required workspace-level permission.  Looks up the user's role from
    the workspace_members collection and checks it against the role hierarchy
    defined in utils/roles.py.

    Usage in a route:
        @router.post("/posts", dependencies=[require_permission("post:create")])
    """
    async def _check(
        current_user: CurrentUser,
        db: DB,
    ) -> dict:
        user_id = current_user["user_id"]
        workspace_id = current_user.get("default_workspace_id")

        if not workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No workspace context — cannot check permissions",
            )

        membership = await db.workspace_members.find_one(
            {"workspace_id": workspace_id, "user_id": user_id},
            {"_id": 0, "role": 1},
        )

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this workspace",
            )

        user_role = membership["role"]

        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' lacks permission '{permission}'",
            )

        return current_user

    return Depends(_check)
