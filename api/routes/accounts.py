"""
Social account management — list, disconnect, OAuth flow.
EC7: safe disconnect with future-post guard.
Tokens are NEVER returned to frontend (response_model excludes them).
"""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from api.deps import CurrentUser, DB, CacheRedis, require_permission
from utils.encryption import encrypt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["accounts"])

_SUPPORTED_PLATFORMS = {"instagram", "facebook", "youtube", "twitter", "linkedin", "tiktok"}

# ── Response models (access_token / refresh_token intentionally absent) ───────

class SocialAccountResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    user_id: str
    platform: str
    platform_user_id: str | None = None
    platform_username: str | None = None
    is_active: bool
    scopes: list[str] = []
    connected_at: datetime
    expires_at: datetime | None = None
    token_error: str | None = None


class DisconnectConflictResponse(BaseModel):
    conflict: bool = True
    future_posts_count: int
    message: str
    options: list[str]


class OAuthUrlResponse(BaseModel):
    platform: str
    authorization_url: str
    state: str


class OAuthCallbackResponse(BaseModel):
    account_id: str
    platform: str
    platform_username: str | None = None
    connected: bool = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[SocialAccountResponse],
            dependencies=[require_permission("account:read")])
async def list_accounts(
    current_user: CurrentUser,
    db: DB,
) -> list[SocialAccountResponse]:
    user_id = current_user["user_id"]
    cursor = db.social_accounts.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "access_token": 0, "refresh_token": 0},
    )
    docs = await cursor.to_list(length=50)
    return [SocialAccountResponse(**d) for d in docs]


@router.delete("/accounts/{account_id}", status_code=status.HTTP_200_OK,
               dependencies=[require_permission("account:disconnect")])
async def disconnect_account(
    account_id: str,
    current_user: CurrentUser,
    db: DB,
    force: Annotated[bool, Query()] = False,
) -> dict:
    user_id = current_user["user_id"]

    account = await db.social_accounts.find_one(
        {"account_id": account_id, "user_id": user_id, "is_active": True},
        {"_id": 0, "platform": 1, "platform_username": 1},
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    now = datetime.now(timezone.utc)

    # EC7: count future posts referencing this account
    future_count = await db.posts.count_documents({
        "user_id": user_id,
        "social_account_ids": account_id,
        "scheduled_time": {"$gt": now},
        "status": {"$in": ["draft", "scheduled"]},
        "deleted_at": {"$exists": False},
    })

    if future_count > 0 and not force:
        return DisconnectConflictResponse(
            future_posts_count=future_count,
            message=f"This account has {future_count} future scheduled post(s).",
            options=["proceed", "cancel"],
        ).model_dump()

    # Proceed: cancel future posts, notify, deactivate
    if future_count > 0:
        await db.posts.update_many(
            {
                "user_id": user_id,
                "social_account_ids": account_id,
                "scheduled_time": {"$gt": now},
                "status": {"$in": ["draft", "scheduled"]},
                "deleted_at": {"$exists": False},
            },
            {"$set": {"status": "cancelled", "updated_at": now}},
        )
        logger.info(
            "Cancelled %d future posts for account %s (force disconnect)",
            future_count, account_id,
        )
        # TODO: enqueue notification task
        try:
            from celery_workers.tasks.media import send_notification
            send_notification.delay(account_id, "account_disconnected")
        except Exception as exc:
            logger.warning("Failed to send disconnect notification: %s", exc)

    # Soft-deactivate; hard-delete deferred 24h
    await db.social_accounts.update_one(
        {"account_id": account_id, "user_id": user_id},
        {"$set": {"is_active": False, "deactivated_at": now, "schedule_hard_delete_at": now}},
    )

    return {"disconnected": True, "future_posts_cancelled": future_count}


@router.get("/oauth/{platform}/url", response_model=OAuthUrlResponse,
            dependencies=[require_permission("account:connect")])
async def get_oauth_url(
    platform: str,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> OAuthUrlResponse:
    if platform not in _SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {platform}",
        )

    user_id = current_user["user_id"]
    state = secrets.token_urlsafe(32)

    # Store state → user_id mapping in Redis (10-minute TTL)
    await cache_redis.setex(f"oauth_state:{state}", 600, user_id)

    auth_url = _build_oauth_url(platform, state)
    return OAuthUrlResponse(platform=platform, authorization_url=auth_url, state=state)


@router.get("/oauth/{platform}/callback", response_model=OAuthCallbackResponse,
            dependencies=[require_permission("account:connect")])
async def oauth_callback(
    platform: str,
    code: str,
    state: str,
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
) -> OAuthCallbackResponse:
    if platform not in _SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {platform}",
        )

    # Validate CSRF state
    stored_user = await cache_redis.get(f"oauth_state:{state}")
    if stored_user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    await cache_redis.delete(f"oauth_state:{state}")

    user_id = current_user["user_id"]
    token_data = await _exchange_code_for_tokens(platform, code)

    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange authorization code for tokens",
        )

    now = datetime.now(timezone.utc)
    account_id = f"{platform}_{user_id}_{secrets.token_hex(8)}"

    await db.social_accounts.update_one(
        {"user_id": user_id, "platform": platform, "platform_user_id": token_data.get("platform_user_id")},
        {
            "$set": {
                "account_id": account_id,
                "user_id": user_id,
                "platform": platform,
                "platform_user_id": token_data.get("platform_user_id"),
                "platform_username": token_data.get("username"),
                "access_token": encrypt(token_data["access_token"]),
                "refresh_token": encrypt(token_data.get("refresh_token", "")),
                "scopes": token_data.get("scopes", []),
                "expires_at": token_data.get("expires_at"),
                "is_active": True,
                "connected_at": now,
            }
        },
        upsert=True,
    )

    logger.info("OAuth connected: %s user=%s platform=%s", account_id, user_id, platform)
    return OAuthCallbackResponse(
        account_id=account_id,
        platform=platform,
        platform_username=token_data.get("username"),
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_oauth_url(platform: str, state: str) -> str:
    """Build platform-specific OAuth authorization URL."""
    base_urls = {
        "facebook": "https://www.facebook.com/v18.0/dialog/oauth",
        "instagram": "https://api.instagram.com/oauth/authorize",
        "youtube": "https://accounts.google.com/o/oauth2/v2/auth",
        "twitter": "https://twitter.com/i/oauth2/authorize",
        "linkedin": "https://www.linkedin.com/oauth/v2/authorization",
        "tiktok": "https://www.tiktok.com/auth/authorize/",
    }
    # YouTube uses Google OAuth — env var is GOOGLE_CLIENT_ID not YOUTUBE_CLIENT_ID (CFG-3)
    client_id_env = "GOOGLE_CLIENT_ID" if platform == "youtube" else f"{platform.upper()}_CLIENT_ID"
    client_id = os.environ.get(client_id_env, "")
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8001/api/v1/oauth/callback")
    base = base_urls.get(platform, "")
    # URL-encode all params to handle special characters (LB-4)
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    })
    return f"{base}?{params}"


async def _exchange_code_for_tokens(platform: str, code: str) -> dict | None:
    """Exchange authorization code for access/refresh tokens. Platform-specific logic."""
    # TODO: implement per-platform token exchange using httpx
    logger.info("Token exchange stub called for platform=%s", platform)
    return None
