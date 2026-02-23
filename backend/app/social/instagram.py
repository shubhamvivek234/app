"""
Instagram Business Login (Standalone)
Uses Instagram API with Instagram Login — does NOT require a Facebook Page.
Official docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""
import httpx
import os
import logging
from fastapi import HTTPException


class InstagramAuth:
    """Instagram Business Login standalone (no Facebook Page required)"""

    OAUTH_URL = "https://api.instagram.com/oauth/authorize"
    TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    GRAPH_URL = "https://graph.instagram.com/v19.0"

    def __init__(self):
        self.app_id = os.environ.get("INSTAGRAM_APP_ID") or os.environ.get("FACEBOOK_APP_ID")
        self.app_secret = os.environ.get("INSTAGRAM_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET")
        self.redirect_uri = os.environ.get("INSTAGRAM_REDIRECT_URI") or os.environ.get("FACEBOOK_REDIRECT_URI", "").replace(
            "/oauth/facebook/callback", "/oauth/instagram/callback"
        )

    def get_auth_url(self, state: str) -> str:
        """Generate Instagram Business Login authorization URL"""
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Instagram credentials not configured")

        scope = "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_comments,instagram_business_manage_insights"

        return (
            f"{self.OAUTH_URL}"
            f"?client_id={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope}"
            f"&response_type=code"
            f"&state={state}"
        )

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for short-lived access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )

            logging.info(f"[Instagram] Token exchange status: {response.status_code}")
            logging.info(f"[Instagram] Token exchange response: {response.text[:500]}")

            if response.status_code != 200:
                logging.error(f"[Instagram] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Instagram code: {response.text}")

            return response.json()

    async def get_long_lived_token(self, short_lived_token: str) -> dict:
        """Exchange short-lived token for long-lived token (60 days)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self.app_secret,
                    "access_token": short_lived_token,
                },
            )

            logging.info(f"[Instagram] Long-lived token status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Instagram] Long-lived token failed: {response.text}, using short-lived")
                return {"access_token": short_lived_token}

            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Instagram user profile using the new Business Login API"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/me",
                params={
                    "fields": "id,name,username,profile_picture_url,followers_count,media_count",
                    "access_token": access_token,
                },
            )

            logging.info(f"[Instagram] /me status: {response.status_code}")
            logging.info(f"[Instagram] /me response: {response.text[:500]}")

            if response.status_code != 200:
                logging.error(f"[Instagram] /me failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch Instagram profile: {response.text}")

            return response.json()
