"""
Shared FastAPI dependencies — db, redis, current user, permission checks.
"""
import os
import logging
from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
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

def get_firebase_app() -> firebase_admin.App:
    global _firebase_app
    if _firebase_app is None:
        cred = credentials.Certificate(os.environ["FIREBASE_ADMIN_SDK_JSON"])
        _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


# ── Security scheme ─────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> dict:
    """
    Verify Firebase JWT. Returns the MongoDB user document.
    Raises 401 if token is missing/invalid.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        get_firebase_app()
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    uid = decoded.get("uid")
    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_current_user_from_cookie(
    request: Request,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> dict:
    """
    Alternative auth dependency using HttpOnly session cookie instead of
    Authorization header. Verifies the Firebase session cookie and checks
    the JTI against the Redis blocklist.
    """
    get_firebase_app()
    claims = await verify_session_cookie(request)

    uid = claims.get("uid") or claims.get("sub")
    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

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
