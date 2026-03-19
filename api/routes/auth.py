"""
Auth routes — /me, /logout (JTI blocklist), /workspace (get-or-create).
Auto-creates MongoDB user + personal workspace on first Firebase login.
"""
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from api.deps import CurrentUser, DB, CacheRedis
from api.models.user import Plan, SubscriptionStatus, UserResponse, WorkspaceResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

_DEFAULT_WORKSPACE_NAME = "Personal Workspace"


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> UserResponse:
    """
    Return authenticated user. Auto-creates user + personal workspace on first login.
    get_current_user dep verifies the Firebase JWT and fetches from MongoDB.
    If user doesn't exist yet (new Firebase signup), create it here.
    """
    # deps.get_current_user already guarantees user exists; but handle bootstrap
    # for deployments where user creation is deferred to this endpoint.
    user = current_user

    if not user.get("workspace_ids"):
        ws_id = await _ensure_personal_workspace(db, user["user_id"], user.get("display_name"))
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {
                "$set": {"default_workspace_id": ws_id},
                "$addToSet": {"workspace_ids": ws_id},
            },
        )
        user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})

    return UserResponse(**user)


# ── /logout ───────────────────────────────────────────────────────────────────

@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> None:
    """
    Add the Firebase token JTI to Redis blocklist so it cannot be reused.
    get_current_user already verified the token; extract JTI from request state
    or re-examine the Authorization header.
    """
    # JTI is set on request state by the bearer dep if available;
    # fall back to extracting it directly from the decoded token.
    jti: str | None = getattr(request.state, "jti", None)

    if not jti:
        # Re-decode to get jti (already verified — safe to use .get without re-verify)
        auth_header = request.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            try:
                import firebase_admin.auth as fb_auth
                decoded = fb_auth.verify_id_token(token, check_revoked=False)
                jti = decoded.get("jti") or decoded.get("sub")
            except Exception:
                pass  # Token already verified by dep — proceed without jti

    if jti:
        # Block JTI for the remainder of its TTL (Firebase tokens last 1 hour = 3600s)
        block_key = f"jti_blocklist:{jti}"
        await cache_redis.setex(block_key, 3600, "1")
        logger.info("JTI blocklisted on logout: user=%s", current_user["user_id"])


# ── /workspace ────────────────────────────────────────────────────────────────

@router.get("/auth/workspace", response_model=WorkspaceResponse)
async def get_or_create_workspace(
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceResponse:
    user_id = current_user["user_id"]
    default_ws_id = current_user.get("default_workspace_id")

    if default_ws_id:
        ws = await db.workspaces.find_one(
            {"workspace_id": default_ws_id, "owner_id": user_id},
            {"_id": 0},
        )
        if ws:
            return WorkspaceResponse(**ws)

    # Create personal workspace if missing
    ws_id = await _ensure_personal_workspace(db, user_id, current_user.get("display_name"))
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"default_workspace_id": ws_id}, "$addToSet": {"workspace_ids": ws_id}},
    )

    ws = await db.workspaces.find_one({"workspace_id": ws_id}, {"_id": 0})
    return WorkspaceResponse(**ws)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _ensure_personal_workspace(db, user_id: str, display_name: str | None) -> str:
    """Get or create the personal workspace for a user. Returns workspace_id."""
    existing = await db.workspaces.find_one(
        {"owner_id": user_id, "workspace_type": "personal"},
        {"workspace_id": 1},
    )
    if existing:
        return existing["workspace_id"]

    now = datetime.now(timezone.utc)
    workspace_name = f"{display_name or 'My'} {_DEFAULT_WORKSPACE_NAME}"
    ws_id = f"ws_{secrets.token_hex(12)}"

    ws_doc = {
        "workspace_id": ws_id,
        "name": workspace_name,
        "owner_id": user_id,
        "workspace_type": "personal",
        "members": [
            {"user_id": user_id, "role": "owner", "joined_at": now}
        ],
        "created_at": now,
    }
    await db.workspaces.insert_one(ws_doc)
    logger.info("Personal workspace created: %s user=%s", ws_id, user_id)
    return ws_id


async def _auto_create_user(db, firebase_uid: str, email: str, display_name: str | None) -> dict:
    """Bootstrap user record on first Firebase login."""
    now = datetime.now(timezone.utc)
    user_id = f"usr_{secrets.token_hex(12)}"

    user_doc = {
        "user_id": user_id,
        "firebase_uid": firebase_uid,
        "email": email,
        "display_name": display_name,
        "avatar_url": None,
        "plan": Plan.STARTER,
        "subscription_status": SubscriptionStatus.FREE,
        "subscription_end_date": None,
        "subscription_grace_period_end": None,
        "timezone": "UTC",
        "mfa_enabled": False,
        "workspace_ids": [],
        "default_workspace_id": None,
        "created_at": now,
    }
    await db.users.insert_one(user_doc)
    user_doc.pop("_id", None)
    logger.info("User auto-created: %s firebase_uid=%s", user_id, firebase_uid)
    return user_doc
