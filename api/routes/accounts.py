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
    return_to: str | None = None


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str | None = None
    code_verifier: str | None = None


# ── Bluesky connect model ─────────────────────────────────────────────────────

class BlueskyConnectRequest(BaseModel):
    handle: str
    app_password: str


class DiscordWebhookRequest(BaseModel):
    webhook_url: str
    channel_name: str | None = None  # optional user-supplied label


# ── LinkedIn org models ───────────────────────────────────────────────────────

class LinkedInOrgRequest(BaseModel):
    org_ids: list[str]


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
        cancelled_cursor = db.posts.find(
            {
                "user_id": user_id,
                "social_account_ids": account_id,
                "scheduled_time": {"$gt": now},
                "status": {"$in": ["draft", "scheduled"]},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0, "id": 1},
        )
        cancelled_post_ids = [p["id"] async for p in cancelled_cursor]

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

        # Schedule media cleanup for each cancelled post
        try:
            from celery_workers.tasks.cleanup import schedule_media_cleanup
            for pid in cancelled_post_ids:
                schedule_media_cleanup.apply_async(args=[pid], countdown=300)
        except Exception as exc:
            logger.warning("Failed to schedule media cleanup after disconnect for account %s: %s", account_id, exc)

        # Notify user about the disconnection directly (9.5: send_notification is post-only)
        try:
            await db.notifications.insert_one({
                "user_id": user_id,
                "type": "account.disconnected",
                "message": f"Social account disconnected and {future_count} future posts cancelled.",
                "metadata": {"account_id": account_id, "cancelled_posts": future_count},
                "is_read": False,
                "created_at": now,
            })
        except Exception as exc:
            logger.warning("Failed to insert disconnect notification: %s", exc)

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

    try:
        auth_url = _build_oauth_url(platform, state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return OAuthUrlResponse(platform=platform, authorization_url=auth_url, state=state)


@router.post("/oauth/{platform}/callback", response_model=OAuthCallbackResponse,
            dependencies=[require_permission("account:connect")])
async def oauth_callback(
    platform: str,
    payload: OAuthCallbackRequest,
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
) -> OAuthCallbackResponse:
    if platform not in _SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {platform}",
        )

    # Validate CSRF state (only if state is provided, e.g. not for some platforms)
    if payload.state:
        stored_user = await cache_redis.get(f"oauth_state:{payload.state}")
        if stored_user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")
        await cache_redis.delete(f"oauth_state:{payload.state}")

    user_id = current_user["user_id"]
    token_data = await _exchange_code_for_tokens(platform, payload.code, payload.code_verifier)

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


# ── Frontend URL aliases (/social-accounts mirrors /accounts) ─────────────────

@router.get("/social-accounts", response_model=list[SocialAccountResponse],
            dependencies=[require_permission("account:read")])
async def list_social_accounts(current_user: CurrentUser, db: DB):
    return await list_accounts(current_user, db)


@router.delete("/social-accounts/{account_id}", status_code=status.HTTP_200_OK,
               dependencies=[require_permission("account:disconnect")])
async def disconnect_social_account(
    account_id: str,
    current_user: CurrentUser,
    db: DB,
    force: bool = False,
):
    return await disconnect_account(account_id, current_user, db, force)


# ── Bluesky (credential-based, no OAuth) ─────────────────────────────────────

@router.post("/social-accounts/bluesky/connect")
async def connect_bluesky(
    body: BlueskyConnectRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Connect a Bluesky account using handle + app password (AT Protocol)."""
    import httpx
    user_id = current_user["user_id"]
    handle = body.handle.lstrip("@")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                json={"identifier": handle, "password": body.app_password},
            )
            r.raise_for_status()
            session = r.json()
    except Exception as exc:
        logger.error("Bluesky connect failed for handle=%s: %s", handle, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Failed to authenticate with Bluesky")

    now = datetime.now(timezone.utc)
    account_id = f"bluesky_{user_id}_{secrets.token_hex(8)}"
    did = session.get("did", handle)

    await db.social_accounts.update_one(
        {"user_id": user_id, "platform": "bluesky", "platform_user_id": did},
        {"$set": {
            "account_id": account_id,
            "user_id": user_id,
            "platform": "bluesky",
            "platform_user_id": did,
            "platform_username": handle,
            "access_token": encrypt(session.get("accessJwt", "")),
            "refresh_token": encrypt(session.get("refreshJwt", "")),
            "scopes": ["write"],
            "is_active": True,
            "connected_at": now,
            "expires_at": None,
        }},
        upsert=True,
    )
    logger.info("Bluesky connected: user=%s handle=%s", user_id, handle)
    return {"connected": True, "platform": "bluesky", "handle": handle}


# ── Discord (webhook-based, no OAuth) ─────────────────────────────────────────

@router.post("/social-accounts/discord/connect")
async def connect_discord(
    body: DiscordWebhookRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Connect a Discord channel via incoming webhook URL."""
    from backend.app.social.discord import DiscordWebhook

    user_id = current_user["user_id"]
    webhook_url = body.webhook_url.strip()

    try:
        meta = await DiscordWebhook.validate(webhook_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Discord webhook validation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Failed to reach Discord. Please check the webhook URL.")

    now = datetime.now(timezone.utc)
    webhook_id = meta["webhook_id"]
    account_id = f"discord_{user_id}_{secrets.token_hex(8)}"
    channel_label = body.channel_name or meta.get("channel_name") or f"Channel {meta.get('channel_id', '')}"

    await db.social_accounts.update_one(
        {"user_id": user_id, "platform": "discord", "platform_user_id": webhook_id},
        {"$set": {
            "account_id": account_id,
            "user_id": user_id,
            "platform": "discord",
            "platform_user_id": webhook_id,
            "platform_username": channel_label,
            "access_token": encrypt(webhook_url),   # webhook URL is the "token"
            "refresh_token": None,
            "scopes": ["webhook"],
            "is_active": True,
            "connected_at": now,
            "expires_at": None,
            "metadata": {
                "guild_id": meta.get("guild_id"),
                "channel_id": meta.get("channel_id"),
            },
        }},
        upsert=True,
    )
    logger.info("Discord webhook connected: user=%s webhook_id=%s channel=%s", user_id, webhook_id, channel_label)
    return {"connected": True, "platform": "discord", "channel": channel_label}


# ── LinkedIn org selection ────────────────────────────────────────────────────

@router.get("/social-accounts/linkedin/pending-orgs")
async def get_linkedin_pending_orgs(current_user: CurrentUser, db: DB):
    """Return LinkedIn orgs pending page selection for the connected account."""
    user_id = current_user["user_id"]
    account = await db.social_accounts.find_one(
        {"user_id": user_id, "platform": "linkedin", "is_active": True},
        {"_id": 0, "pending_orgs": 1},
    )
    if not account:
        raise HTTPException(status_code=404, detail="No active LinkedIn account found")
    return {"orgs": account.get("pending_orgs", [])}


@router.post("/social-accounts/linkedin/save-orgs")
async def save_linkedin_orgs(body: LinkedInOrgRequest, current_user: CurrentUser, db: DB):
    """Save selected LinkedIn org pages to the account."""
    user_id = current_user["user_id"]
    await db.social_accounts.update_one(
        {"user_id": user_id, "platform": "linkedin", "is_active": True},
        {"$set": {"selected_org_ids": body.org_ids, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"saved": True, "org_count": len(body.org_ids)}


@router.post("/social-accounts/linkedin/manual")
async def add_linkedin_page_manually(body: dict, current_user: CurrentUser, db: DB):
    """Add a LinkedIn page ID manually (fallback)."""
    page_id = body.get("page_id") or body.get("org_id")
    if not page_id:
        raise HTTPException(status_code=422, detail="page_id required")
    user_id = current_user["user_id"]
    await db.social_accounts.update_one(
        {"user_id": user_id, "platform": "linkedin", "is_active": True},
        {"$addToSet": {"selected_org_ids": page_id}},
    )
    return {"added": True, "page_id": page_id}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_oauth_url(platform: str, state: str) -> str:
    """Build platform-specific OAuth authorization URL with required scopes."""
    if platform == "instagram":
        from utils.instagram_oauth import get_auth_url as _ig_get_auth_url
        return _ig_get_auth_url(state)

    base_urls = {
        "facebook": "https://www.facebook.com/v18.0/dialog/oauth",
        "youtube": "https://accounts.google.com/o/oauth2/v2/auth",
        "twitter": "https://twitter.com/i/oauth2/authorize",
        "linkedin": "https://www.linkedin.com/oauth/v2/authorization",
        "tiktok": "https://www.tiktok.com/v2/auth/authorize/",
    }
    
    scopes = {
        "facebook": "pages_show_list,pages_read_engagement,pages_manage_posts",
        "youtube": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/userinfo.profile",
        "twitter": "tweet.read tweet.write users.read offline.access",
        "linkedin": "w_member_social r_liteprofile",
        "tiktok": "video.upload,user.info.basic",
    }
    # Some providers use APP_ID naming instead of CLIENT_ID.
    if platform == "youtube":
        client_id_env = "GOOGLE_CLIENT_ID"
    elif platform == "facebook":
        client_id_env = "FACEBOOK_APP_ID"
    else:
        client_id_env = f"{platform.upper()}_CLIENT_ID"
    client_id = os.environ.get(client_id_env, "")
    # 9.9: Fail fast if OAuth client_id not configured — prevents silent malformed URLs
    if not client_id:
        raise ValueError(f"OAuth not configured for platform '{platform}': {client_id_env} env var is missing")

    redirect_uri_env_map = {
        "facebook": "FACEBOOK_REDIRECT_URI",
        "youtube": "YOUTUBE_REDIRECT_URI",
        "twitter": "TWITTER_REDIRECT_URI",
        "linkedin": "LINKEDIN_REDIRECT_URI",
        "tiktok": "TIKTOK_REDIRECT_URI",
    }
    redirect_uri = os.environ.get(
        redirect_uri_env_map.get(platform, "OAUTH_REDIRECT_URI"),
        os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8001/api/v1/oauth/callback"),
    )
    base = base_urls.get(platform, "")
    scope = scopes.get(platform, "")
    # URL-encode all params to handle special characters in redirect_uri/state (LB-4)
    params: dict = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    }
    if scope:
        params["scope"] = scope
    return f"{base}?{urlencode(params)}"


async def _exchange_code_for_tokens(platform: str, code: str, code_verifier: str | None = None) -> dict | None:
    """Exchange authorization code for access/refresh tokens. Platform-specific logic."""
    if platform == "instagram":
        return await _exchange_instagram_code(code)
    if platform == "facebook":
        return await _exchange_facebook_code(code)
    if platform == "youtube":
        return await _exchange_youtube_code(code)
    if platform == "twitter":
        return await _exchange_twitter_code(code, code_verifier or "")
    if platform == "linkedin":
        return await _exchange_linkedin_code(code)
    if platform == "tiktok":
        return await _exchange_tiktok_code(code)
    logger.warning("Token exchange not implemented for platform=%s", platform)
    return None


async def _exchange_facebook_code(code: str) -> dict | None:
    """Facebook OAuth: exchange code → short-lived → long-lived (60 days)."""
    import urllib.parse
    import httpx
    from datetime import timedelta

    app_id = os.environ.get("FACEBOOK_APP_ID", "")
    app_secret = os.environ.get("FACEBOOK_APP_SECRET", "")
    redirect_uri = os.environ.get("FACEBOOK_REDIRECT_URI",
                                  os.environ.get("OAUTH_REDIRECT_URI", ""))
    if not app_id or not app_secret:
        logger.error("Facebook OAuth: FACEBOOK_APP_ID / FACEBOOK_APP_SECRET not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1 — short-lived user access token
            r = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={"client_id": app_id, "redirect_uri": redirect_uri,
                        "client_secret": app_secret, "code": code},
            )
            r.raise_for_status()
            short = r.json()
            short_token = short.get("access_token")
            if not short_token:
                logger.error("Facebook short token missing: %s", short)
                return None

            # Step 2 — long-lived token (60 days)
            r2 = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={"grant_type": "fb_exchange_token", "client_id": app_id,
                        "client_secret": app_secret, "fb_exchange_token": short_token},
            )
            r2.raise_for_status()
            long = r2.json()
            access_token = long.get("access_token", short_token)
            expires_in = long.get("expires_in")
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                          if expires_in else None)

            # Step 3 — profile
            r3 = await client.get(
                "https://graph.facebook.com/v18.0/me",
                params={"fields": "id,name", "access_token": access_token},
            )
            r3.raise_for_status()
            profile = r3.json()

        return {
            "access_token": access_token,
            "refresh_token": None,
            "platform_user_id": str(profile.get("id", "")),
            "username": profile.get("name", ""),
            "scopes": ["pages_show_list", "pages_manage_posts"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("Facebook token exchange failed: %s", exc)
        return None


async def _exchange_youtube_code(code: str) -> dict | None:
    """YouTube/Google OAuth: exchange authorization code for tokens."""
    import httpx
    from datetime import timedelta

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI",
                                  os.environ.get("OAUTH_REDIRECT_URI", ""))
    if not client_id or not client_secret:
        logger.error("YouTube OAuth: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={"code": code, "client_id": client_id, "client_secret": client_secret,
                      "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
            )
            r.raise_for_status()
            tokens = r.json()
            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("YouTube token missing: %s", tokens)
                return None

            expires_in = tokens.get("expires_in")
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                          if expires_in else None)

            # Get user profile
            r2 = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r2.raise_for_status()
            profile = r2.json()

        return {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "platform_user_id": str(profile.get("id", "")),
            "username": profile.get("name", profile.get("email", "")),
            "scopes": ["youtube.upload"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("YouTube token exchange failed: %s", exc)
        return None


async def _exchange_twitter_code(code: str, code_verifier: str) -> dict | None:
    """Twitter OAuth 2.0 PKCE: exchange authorization code for tokens."""
    import httpx
    from datetime import timedelta

    client_id = os.environ.get("TWITTER_CLIENT_ID", "")
    client_secret = os.environ.get("TWITTER_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("TWITTER_REDIRECT_URI",
                                  os.environ.get("OAUTH_REDIRECT_URI", ""))
    if not client_id:
        logger.error("Twitter OAuth: TWITTER_CLIENT_ID not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.twitter.com/2/oauth2/token",
                data={"code": code, "grant_type": "authorization_code",
                      "client_id": client_id, "redirect_uri": redirect_uri,
                      "code_verifier": code_verifier or "challenge"},
                auth=(client_id, client_secret) if client_secret else None,
            )
            r.raise_for_status()
            tokens = r.json()
            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("Twitter token missing: %s", tokens)
                return None

            # Get user profile
            r2 = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r2.raise_for_status()
            user_data = r2.json().get("data", {})

        expires_in = tokens.get("expires_in")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                      if expires_in else None)

        return {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "platform_user_id": str(user_data.get("id", "")),
            "username": user_data.get("username", user_data.get("name", "")),
            "scopes": ["tweet.read", "tweet.write"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("Twitter token exchange failed: %s", exc)
        return None


async def _exchange_linkedin_code(code: str) -> dict | None:
    """LinkedIn OAuth: exchange authorization code for tokens."""
    import httpx
    from datetime import timedelta

    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("LINKEDIN_REDIRECT_URI",
                                  os.environ.get("OAUTH_REDIRECT_URI", ""))
    if not client_id or not client_secret:
        logger.error("LinkedIn OAuth: LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={"grant_type": "authorization_code", "code": code,
                      "redirect_uri": redirect_uri, "client_id": client_id,
                      "client_secret": client_secret},
            )
            r.raise_for_status()
            tokens = r.json()
            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("LinkedIn token missing: %s", tokens)
                return None

            expires_in = tokens.get("expires_in")
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                          if expires_in else None)

            # Get profile
            r2 = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r2.raise_for_status()
            profile = r2.json()

        return {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "platform_user_id": str(profile.get("sub", "")),
            "username": profile.get("name", profile.get("email", "")),
            "scopes": ["w_member_social"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("LinkedIn token exchange failed: %s", exc)
        return None


async def _exchange_tiktok_code(code: str) -> dict | None:
    """TikTok OAuth v2: exchange authorization code for tokens."""
    import httpx
    from datetime import timedelta

    client_key = os.environ.get("TIKTOK_CLIENT_ID", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("TIKTOK_REDIRECT_URI",
                                  os.environ.get("OAUTH_REDIRECT_URI", ""))
    if not client_key or not client_secret:
        logger.error("TikTok OAuth: TIKTOK_CLIENT_ID / TIKTOK_CLIENT_SECRET not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={"client_key": client_key, "client_secret": client_secret,
                      "code": code, "grant_type": "authorization_code",
                      "redirect_uri": redirect_uri},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r.raise_for_status()
            data = r.json()
            token_data = data.get("data", data)
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("TikTok token missing: %s", data)
                return None

            expires_in = token_data.get("expires_in")
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                          if expires_in else None)

            open_id = token_data.get("open_id", "")

        return {
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token"),
            "platform_user_id": str(open_id),
            "username": open_id,
            "scopes": ["video.upload", "user.info.basic"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("TikTok token exchange failed: %s", exc)
        return None


async def _exchange_instagram_code(code: str) -> dict | None:
    """
    Full Instagram Business Login token exchange:
    1. Short-lived token via POST /oauth/access_token
    2. Long-lived token (60 days) via GET /access_token?grant_type=ig_exchange_token
    3. Fetch user profile (id, username) via GET /me
    """
    from datetime import timedelta

    try:
        from utils.instagram_oauth import (
            exchange_code_for_token as _ig_exchange,
            get_long_lived_token as _ig_long_token,
            get_user_profile as _ig_profile,
        )

        # Step 1 — short-lived token
        short_data = await _ig_exchange(code)
        short_token = short_data.get("access_token")
        if not short_token:
            logger.error("Instagram token exchange: no access_token in response %s", short_data)
            return None

        # Step 2 — long-lived token (60 days)
        long_data = await _ig_long_token(short_token)
        access_token = long_data.get("access_token", short_token)
        expires_in_seconds = long_data.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_seconds))
            if expires_in_seconds
            else None
        )

        # Step 3 — user profile
        profile = await _ig_profile(access_token)
        platform_user_id = str(profile.get("id", short_data.get("user_id", "")))
        username = profile.get("username") or profile.get("name") or platform_user_id

        logger.info("Instagram OAuth connected: user_id=%s username=%s", platform_user_id, username)
        return {
            "access_token": access_token,
            "refresh_token": None,
            "platform_user_id": platform_user_id,
            "username": username,
            "scopes": ["instagram_business_basic", "instagram_business_content_publish"],
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.error("Instagram token exchange failed: %s", exc)
        return None
