"""
Shared FastAPI dependencies — db, redis, current user.
"""
import os
import logging
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from db.mongo import get_db
from db.redis_client import get_cache_redis, get_queue_redis

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


# ── Convenience type aliases ─────────────────────────────────────────────────
CurrentUser = Annotated[dict, Depends(get_current_user)]
DB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
CacheRedis = Annotated[Redis, Depends(get_cache_redis)]
QueueRedis = Annotated[Redis, Depends(get_queue_redis)]
