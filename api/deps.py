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
from utils.observability import event_log, shorten_provider_error
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
        event_log(
            logger,
            "info",
            "auth.firebase.initialized",
            credential_path=cred_path,
            outcome="initialized",
        )
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
    email_verified = bool(decoded.get("email_verified", False))
    avatar_url = decoded.get("picture")

    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
    if user is not None:
        updates = {}
        if user.get("email_verified") != email_verified:
            updates["email_verified"] = email_verified
        if display_name and user.get("display_name") != display_name:
            updates["display_name"] = display_name
        if avatar_url and user.get("avatar_url") != avatar_url:
            updates["avatar_url"] = avatar_url
        if updates:
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
            user.update(updates)
        return user

    if email:
        user = await db.users.find_one({"email": email}, {"_id": 0})
        if user is not None:
            updates = {}
            if uid and not user.get("firebase_uid"):
                updates["firebase_uid"] = uid
            if display_name and user.get("display_name") != display_name:
                updates["display_name"] = display_name
            if user.get("email_verified") != email_verified:
                updates["email_verified"] = email_verified
            if avatar_url and user.get("avatar_url") != avatar_url:
                updates["avatar_url"] = avatar_url
            if updates:
                await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
                user.update(updates)
                event_log(
                    logger,
                    "info",
                    "auth.user.backfilled",
                    user_id=user["user_id"],
                    firebase_uid=uid,
                    outcome="backfilled",
                )
            return user

    now = datetime.now(timezone.utc)
    user_doc = {
        "user_id": f"usr_{secrets.token_hex(12)}",
        "firebase_uid": uid,
        "email": email,
        "email_verified": email_verified,
        "display_name": display_name,
        "avatar_url": avatar_url,
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
        event_log(
            logger,
            "info",
            "auth.user.auto_created",
            user_id=user_doc["user_id"],
            firebase_uid=uid,
            outcome="created",
        )

        try:
            from celery_workers.tasks.notifications import send_notification_email_task  # noqa: PLC0415

            send_notification_email_task.delay(
                user_id=user_doc["user_id"],
                event="user.welcome",
                title="Welcome to Unravler! Let's get started",
                message=(
                    "Welcome to Unravler! Your all-in-one command center for scheduling, "
                    "multi-platform publishing, and analytics. Connect your social channels "
                    "in Settings to start scheduling and publishing your content."
                ),
                target_path="/dashboard",
            )
        except Exception as welcome_exc:
            logger.warning("auth.user.welcome_email.enqueue_failed: %s; falling back to direct send", welcome_exc)
            if email:
                try:
                    import asyncio
                    from utils.notification_emails import send_notification_email_async  # noqa: PLC0415

                    asyncio.create_task(
                        send_notification_email_async(
                            email=email,
                            event="user.welcome",
                            title="Welcome to Unravler! Let's get started",
                            message=(
                                "Welcome to Unravler! Your all-in-one command center for scheduling, "
                                "multi-platform publishing, and analytics. Connect your social channels "
                                "in Settings to start scheduling and publishing your content."
                            ),
                            target_path="/dashboard",
                            display_name=display_name,
                        )
                    )
                except Exception as fallback_exc:
                    logger.error("auth.user.welcome_email.fallback_failed: %s", fallback_exc)

        return user_doc
    except DuplicateKeyError:
        # Another request likely created the user concurrently. Re-read to keep
        # sign-in stable instead of failing the request.
        event_log(
            logger,
            "info",
            "auth.user.bootstrap_race",
            firebase_uid=uid,
            email=email,
            outcome="race_recovered",
        )
        if uid:
            user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
            if user is not None:
                return user
        if email:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if user is not None:
                return user
        raise


async def _create_personal_workspace(
    db: AsyncIOMotorDatabase,
    user_id: str,
    display_name: str | None,
) -> str:
    existing = await db.workspaces.find_one(
        {"owner_id": user_id, "workspace_type": "personal"},
        {"_id": 0, "workspace_id": 1},
    )
    if existing:
        return existing["workspace_id"]

    now = datetime.now(timezone.utc)
    workspace_name = f"{display_name or 'My'} Personal Workspace"
    ws_id = f"ws_{secrets.token_hex(12)}"

    await db.workspaces.insert_one(
        {
            "workspace_id": ws_id,
            "name": workspace_name,
            "owner_id": user_id,
            "workspace_type": "personal",
            "members": [{"user_id": user_id, "role": "owner", "joined_at": now}],
            "created_at": now,
        }
    )
    await db.workspace_members.insert_one(
        {
            "workspace_id": ws_id,
            "user_id": user_id,
            "role": "owner",
            "joined_at": now,
        }
    )
    event_log(
        logger,
        "info",
        "auth.workspace.created",
        route="/auth/me",
        user_id=user_id,
        workspace_id=ws_id,
        outcome="created",
    )
    return ws_id


async def ensure_active_workspace(
    db: AsyncIOMotorDatabase,
    user: dict,
    *,
    create_if_missing: bool = True,
) -> dict:
    hydrated_user = dict(user)
    user_id = hydrated_user["user_id"]
    workspace_ids = [ws_id for ws_id in (hydrated_user.get("workspace_ids") or []) if ws_id]
    default_workspace_id = hydrated_user.get("default_workspace_id")

    async def _has_access(workspace_id: str | None) -> bool:
        if not workspace_id:
            return False
        membership = await db.workspace_members.find_one(
            {"workspace_id": workspace_id, "user_id": user_id},
            {"_id": 0, "role": 1},
        )
        if membership:
            return True
        workspace = await db.workspaces.find_one(
            {"workspace_id": workspace_id, "owner_id": user_id},
            {"_id": 0, "workspace_id": 1},
        )
        return workspace is not None

    resolved_workspace_id = default_workspace_id if await _has_access(default_workspace_id) else None

    if resolved_workspace_id is None:
        for workspace_id in workspace_ids:
            if await _has_access(workspace_id):
                resolved_workspace_id = workspace_id
                break

    if resolved_workspace_id is None:
        owned_personal_workspace = await db.workspaces.find_one(
            {"owner_id": user_id, "workspace_type": "personal"},
            {"_id": 0, "workspace_id": 1},
        )
        if owned_personal_workspace:
            resolved_workspace_id = owned_personal_workspace["workspace_id"]

    if resolved_workspace_id is None:
        owned_workspace = await db.workspaces.find_one(
            {"owner_id": user_id},
            {"_id": 0, "workspace_id": 1},
        )
        if owned_workspace:
            resolved_workspace_id = owned_workspace["workspace_id"]

    if resolved_workspace_id is None:
        membership = await db.workspace_members.find_one(
            {"user_id": user_id},
            {"_id": 0, "workspace_id": 1},
        )
        if membership:
            resolved_workspace_id = membership["workspace_id"]

    if resolved_workspace_id is None and create_if_missing:
        resolved_workspace_id = await _create_personal_workspace(
            db,
            user_id,
            hydrated_user.get("display_name"),
        )

    if resolved_workspace_id and (
        resolved_workspace_id != default_workspace_id or resolved_workspace_id not in workspace_ids
    ):
        await db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {"default_workspace_id": resolved_workspace_id},
                "$addToSet": {"workspace_ids": resolved_workspace_id},
            },
        )

    if resolved_workspace_id:
        hydrated_user["default_workspace_id"] = resolved_workspace_id
        if resolved_workspace_id not in workspace_ids:
            hydrated_user["workspace_ids"] = [*workspace_ids, resolved_workspace_id]
        else:
            hydrated_user["workspace_ids"] = workspace_ids
    elif "workspace_ids" not in hydrated_user:
        hydrated_user["workspace_ids"] = workspace_ids

    return hydrated_user


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
    decoded = None
    cookie_error: HTTPException | None = None

    get_firebase_app()
    if request.cookies.get("session"):
        try:
            decoded = await verify_session_cookie(request)
            request.state.jti = decoded.get("jti") or decoded.get("sub")
        except HTTPException as exc:
            cookie_error = exc

    if decoded is None and credentials is not None:
        try:
            decoded = firebase_auth.verify_id_token(credentials.credentials)
            request.state.jti = decoded.get("jti") or decoded.get("sub")
        except Exception as exc:
            event_log(
                logger,
                "warning",
                "auth.token.verification_failed",
                route="/auth/me",
                failure_type=type(exc).__name__,
                provider_error=shorten_provider_error(exc),
                outcome="invalid_token",
            )
            if cookie_error is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if decoded is None:
        if cookie_error is not None:
            raise cookie_error
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        user = await _bootstrap_user_from_claims(db, decoded)
        user = await ensure_active_workspace(db, user)
    except DuplicateKeyError as exc:
        event_log(
            logger,
            "error",
            "auth.user.bootstrap_failed",
            exc_info=exc,
            route="/auth/me",
            firebase_uid=decoded.get("uid"),
            failure_type="duplicate_key_recovery_failed",
            outcome="error",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile is still being prepared. Please try again.",
        )

    if user.get("status") in {"deletion_pending", "deleted"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been submitted for permanent deletion and is no longer accessible.",
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
        user = await ensure_active_workspace(db, user)
    except DuplicateKeyError as exc:
        event_log(
            logger,
            "error",
            "auth.session.bootstrap_failed",
            exc_info=exc,
            route="/auth/me",
            firebase_uid=claims.get("uid"),
            failure_type="duplicate_key_recovery_failed",
            outcome="error",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile is still being prepared. Please try again.",
        )

    if user.get("status") in {"deletion_pending", "deleted"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been submitted for permanent deletion and is no longer accessible.",
        )

    request.state.user_id = user["user_id"]
    return user


# ── Convenience type aliases ─────────────────────────────────────────────────
CurrentUser = Annotated[dict, Depends(get_current_user)]
CookieUser = Annotated[dict, Depends(get_current_user_from_cookie)]
DB = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
CacheRedis = Annotated[Redis, Depends(get_cache_redis)]
QueueRedis = Annotated[Redis, Depends(get_queue_redis)]


async def require_verified_email(current_user: CurrentUser) -> dict:
    if not current_user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required before connecting accounts, publishing, or inviting teammates.",
        )
    return current_user


VerifiedUser = Annotated[dict, Depends(require_verified_email)]


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
        current_user = await ensure_active_workspace(db, current_user)
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
