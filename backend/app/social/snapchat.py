"""
Snapchat Snap Kit Login & Spotlight OAuth
Docs: https://developers.snap.com/docs/snap-kit/login-kit/
Auth URL: https://accounts.snapchat.com/login/oauth2/authorize
Token URL: https://accounts.snapchat.com/login/oauth2/access_token
Profile URL: https://kit.snapchat.com/v1/me

NOTE: Snapchat's public API is very limited.
- Organic Snap posting is NOT available via API (only through deep-links).
- Profile info (display name, bitmoji avatar) is available via Login Kit.
- Spotlight analytics are available only via the Ads/Creator API (limited access).
- This integration provides: Login, Profile display, and UI placeholder for Spotlight.
"""
import httpx
import os
import logging
import urllib.parse
from fastapi import HTTPException


class SnapchatAuth:
    """Snapchat Snap Kit OAuth 2.0"""

    AUTH_URL    = "https://accounts.snapchat.com/login/oauth2/authorize"
    TOKEN_URL   = "https://accounts.snapchat.com/login/oauth2/access_token"
    PROFILE_URL = "https://kit.snapchat.com/v1/me"

    SCOPES = "https://auth.snapchat.com/oauth2/api/user.profile.bitmoji https://auth.snapchat.com/oauth2/api/user.profile"

    def __init__(self):
        self.client_id     = os.environ.get("SNAPCHAT_CLIENT_ID")
        self.client_secret = os.environ.get("SNAPCHAT_CLIENT_SECRET")
        self.redirect_uri  = os.environ.get("SNAPCHAT_REDIRECT_URI", "http://localhost:8001/api/oauth/snapchat/callback")

    def get_auth_url(self, state: str) -> str:
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Snapchat credentials not configured")

        params = {
            "client_id":     self.client_id,
            "redirect_uri":  self.redirect_uri,
            "response_type": "code",
            "scope":         self.SCOPES,
            "state":         state,
        }
        url = f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Snapchat] Auth URL generated")
        return url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "code":          code,
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type":    "authorization_code",
                    "redirect_uri":  self.redirect_uri,
                },
            )
            logging.info(f"[Snapchat] Token exchange status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Snapchat] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Snapchat code: {response.text}")
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an expired Snapchat access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type":    "refresh_token",
                },
            )
            if response.status_code != 200:
                logging.error(f"[Snapchat] Token refresh failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to refresh Snapchat token")
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Snapchat user profile (Login Kit)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logging.info(f"[Snapchat] /v1/me status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Snapchat] /v1/me failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Snapchat profile")

            data = response.json()
            # Snap Kit returns { data: { me: { externalId, displayName, bitmoji: { avatar } } } }
            me = data.get("data", {}).get("me", {})
            return {
                "id":          me.get("externalId", ""),
                "name":        me.get("displayName", ""),
                "username":    me.get("displayName", ""),
                "picture_url": me.get("bitmoji", {}).get("avatar"),
            }

    async def fetch_posts(self, access_token: str, limit: int = 20) -> list:
        """
        Snapchat does not expose organic post fetching via a public API.
        Returns empty list — this is a known platform limitation.
        """
        logging.info("[Snapchat] fetch_posts: Snapchat does not support post fetching via public API")
        return []
