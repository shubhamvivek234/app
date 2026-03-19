"""
Pinterest OAuth 2.0 — Pinterest API v5
Docs: https://developers.pinterest.com/docs/getting-started/authentication/
Auth URL: https://www.pinterest.com/oauth/
Token URL: https://api.pinterest.com/v5/oauth/token
API Base: https://api.pinterest.com/v5
"""
import httpx
import os
import logging
import base64
import urllib.parse
from fastapi import HTTPException


class PinterestAuth:
    """Pinterest API v5 OAuth 2.0"""

    AUTH_URL  = "https://www.pinterest.com/oauth/"
    TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
    BASE_URL  = "https://api.pinterest.com/v5"

    SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"

    def __init__(self):
        self.app_id     = os.environ.get("PINTEREST_APP_ID")
        self.app_secret = os.environ.get("PINTEREST_APP_SECRET")
        self.redirect_uri = os.environ.get("PINTEREST_REDIRECT_URI", "http://localhost:8001/api/oauth/pinterest/callback")

    def _basic_auth_header(self) -> str:
        credentials = f"{self.app_id}:{self.app_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_auth_url(self, state: str) -> str:
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Pinterest credentials not configured")

        params = {
            "client_id":     self.app_id,
            "redirect_uri":  self.redirect_uri,
            "response_type": "code",
            "scope":         self.SCOPES,
            "state":         state,
        }
        url = f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Pinterest] Auth URL generated")
        return url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type":   "authorization_code",
                    "code":         code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            logging.info(f"[Pinterest] Token exchange status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Pinterest] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Pinterest code: {response.text}")
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an expired Pinterest access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": refresh_token,
                    "scope":         self.SCOPES,
                },
            )
            if response.status_code != 200:
                logging.error(f"[Pinterest] Token refresh failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to refresh Pinterest token")
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Pinterest user account info"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/user_account",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logging.info(f"[Pinterest] /user_account status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Pinterest] /user_account failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Pinterest profile")
            return response.json()

    async def get_boards(self, access_token: str, limit: int = 50) -> list:
        """Get user's Pinterest boards"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/boards",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"page_size": limit},
            )
            if response.status_code != 200:
                return []
            return response.json().get("items", [])

    async def create_pin(
        self,
        access_token: str,
        board_id: str,
        title: str,
        description: str,
        link: str = "",
        image_url: str = "",
        alt_text: str = "",
    ) -> str:
        """Create a Pin on a board"""
        async with httpx.AsyncClient() as client:
            payload = {
                "board_id":    board_id,
                "title":       title,
                "description": description,
            }
            if link:
                payload["link"] = link
            if image_url:
                payload["media_source"] = {
                    "source_type": "image_url",
                    "url":         image_url,
                }
                if alt_text:
                    payload["alt_text"] = alt_text

            response = await client.post(
                f"{self.BASE_URL}/pins",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
            if response.status_code not in [200, 201]:
                logging.error(f"[Pinterest] Create pin failed: {response.text}")
                raise Exception(f"Failed to create Pinterest pin: {response.text}")
            return response.json().get("id", "")

    async def fetch_pins(self, access_token: str, limit: int = 20) -> list:
        """Fetch user's Pins"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/pins",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"page_size": limit},
            )
            logging.info(f"[Pinterest] fetch_pins status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Pinterest] fetch_pins failed: {response.text}")
                return []

            pins = response.json().get("items", [])
            normalized = []
            for pin in pins:
                media = pin.get("media", {})
                images = media.get("images", {})
                thumb = (images.get("400x300") or images.get("150x150") or {}).get("url")

                normalized.append({
                    "platform_post_id": pin.get("id"),
                    "content":          pin.get("title") or pin.get("description", ""),
                    "media_url":        thumb,
                    "media_type":       "IMAGE",
                    "post_url":         pin.get("link") or f"https://www.pinterest.com/pin/{pin.get('id')}/",
                    "metrics": {
                        "likes":    pin.get("save_count", 0),
                        "views":    pin.get("impression_count", 0),
                        "comments": pin.get("comment_count", 0),
                    },
                    "published_at": pin.get("created_at"),
                })
            return normalized
