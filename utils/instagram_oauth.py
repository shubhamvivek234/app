"""
Instagram Business Login OAuth helper.
Handles auth URL generation, short→long-lived token exchange, and profile fetch.
Uses Instagram API with Instagram Login (no Facebook Page required).
Ref: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""
import logging
import os
import urllib.parse

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v21.0")
_OAUTH_URL = "https://api.instagram.com/oauth/authorize"
_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
_GRAPH_URL = f"https://graph.instagram.com/{_API_VERSION}"

_SCOPES = (
    "instagram_business_basic,"
    "instagram_business_content_publish,"
    "instagram_business_manage_comments,"
    "instagram_business_manage_insights"
)


def _get_credentials() -> tuple[str, str, str]:
    """Return (app_id, app_secret, redirect_uri). Raises 500 if unconfigured."""
    app_id = os.environ.get("INSTAGRAM_APP_ID") or os.environ.get("FACEBOOK_APP_ID", "")
    app_secret = os.environ.get("INSTAGRAM_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET", "")

    raw_uri = (
        os.environ.get("INSTAGRAM_REDIRECT_URI")
        or os.environ.get("FACEBOOK_REDIRECT_URI", "").replace(
            "/oauth/facebook/callback", "/oauth/instagram/callback"
        )
    )

    # Meta requires HTTPS redirect URIs; wrap plain-HTTP dev URLs in redirectmeto proxy
    if raw_uri.startswith("http://"):
        redirect_uri = f"https://redirectmeto.com/{raw_uri}"
    else:
        redirect_uri = raw_uri

    if not app_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="Instagram credentials not configured")

    return app_id, app_secret, redirect_uri


def get_auth_url(state: str) -> str:
    """Build the Instagram OAuth authorization URL with required business scopes."""
    app_id, _, redirect_uri = _get_credentials()
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": _SCOPES,
        "response_type": "code",
        "state": state,
    }
    url = f"{_OAUTH_URL}?{urllib.parse.urlencode(params)}"
    logger.info("Instagram auth URL generated for state=%s", state)
    return url


async def exchange_code_for_token(code: str) -> dict:
    """POST to /oauth/access_token — returns short-lived token dict."""
    _, app_secret, redirect_uri = _get_credentials()
    app_id, _, _ = _get_credentials()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

    logger.info("Instagram token exchange: status=%s", resp.status_code)
    if resp.status_code != 200:
        logger.error("Instagram token exchange failed: %s", resp.text)
        raise HTTPException(
            status_code=400,
            detail=f"Instagram token exchange failed: {resp.text[:200]}",
        )
    return resp.json()


async def get_long_lived_token(short_lived_token: str) -> dict:
    """Exchange short-lived token for long-lived token (~60 days)."""
    _, app_secret, _ = _get_credentials()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_GRAPH_URL}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": app_secret,
                "access_token": short_lived_token,
            },
        )

    if resp.status_code != 200:
        logger.warning("Long-lived token exchange failed (%s) — using short-lived", resp.text[:100])
        return {"access_token": short_lived_token}
    return resp.json()


async def get_user_profile(access_token: str) -> dict:
    """Fetch Instagram user profile: id, username, name."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_GRAPH_URL}/me",
            params={
                "fields": "id,name,username,profile_picture_url",
                "access_token": access_token,
            },
        )

    if resp.status_code != 200:
        logger.error("Instagram /me failed: %s", resp.text)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch Instagram profile: {resp.text[:200]}",
        )
    return resp.json()
