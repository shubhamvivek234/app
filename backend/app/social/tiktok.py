import httpx
import os
import logging
import secrets
import hashlib
import base64
from datetime import datetime, timezone
from fastapi import HTTPException
from urllib.parse import urlencode

class TikTokAuth:
    """TikTok OAuth 2.0 (Content Posting API v2)"""

    AUTH_URL   = "https://www.tiktok.com/v2/auth/authorize/"
    TOKEN_URL  = "https://open.tiktokapis.com/v2/oauth/token/"
    USER_URL   = "https://open.tiktokapis.com/v2/user/info/"
    VIDEO_INIT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    VIDEO_STATUS = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

    SCOPES = "user.info.basic,video.publish,video.upload"

    def __init__(self):
        self.client_id     = os.environ.get("TIKTOK_CLIENT_ID")
        self.client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
        self.redirect_uri  = os.environ.get(
            "TIKTOK_REDIRECT_URI",
            "http://localhost:8001/api/oauth/tiktok/callback"
        )

    def _generate_pkce(self):
        verifier  = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        return verifier, challenge

    def get_auth_url(self, state: str) -> dict:
        """Return auth URL + PKCE verifier (store verifier in session)."""
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="TikTok credentials not configured")
        verifier, challenge = self._generate_pkce()
        params = {
            "client_key":             self.client_id,
            "response_type":          "code",
            "scope":                  self.SCOPES,
            "redirect_uri":           self.redirect_uri,
            "state":                  state,
            "code_challenge":         challenge,
            "code_challenge_method":  "S256",
        }
        return {
            "url":      f"{self.AUTH_URL}?{urlencode(params)}",
            "verifier": verifier,
        }

    async def exchange_code_for_token(self, code: str, verifier: str) -> dict:
        async with httpx.AsyncClient() as client:
            data = {
                "client_key":     self.client_id,
                "client_secret":  self.client_secret,
                "code":           code,
                "grant_type":     "authorization_code",
                "redirect_uri":   self.redirect_uri,
                "code_verifier":  verifier,
            }
            response = await client.post(self.TOKEN_URL, data=data)
            if response.status_code != 200:
                logging.error(f"[TikTok] Token exchange error: {response.text}")
                raise HTTPException(status_code=400, detail=f"TikTok token exchange failed: {response.text}")
            return response.json().get("data", response.json())

    async def get_user_profile(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "open_id,union_id,avatar_url,display_name"},
            )
            if response.status_code != 200:
                logging.error(f"[TikTok] User info error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch TikTok user profile")
            data = response.json().get("data", {}).get("user", response.json())
            return {
                "id":          data.get("open_id") or data.get("union_id", ""),
                "name":        data.get("display_name", ""),
                "picture_url": data.get("avatar_url"),
                "username":    data.get("display_name", ""),
            }

    async def publish_video(
        self,
        access_token: str,
        video_url: str,
        caption: str,
        privacy: str = "PUBLIC_TO_EVERYONE",
        allow_duet: bool = True,
        allow_stitch: bool = True,
        allow_comments: bool = True,
    ) -> dict:
        """
        Initiate a video post via TikTok Content Posting API.
        Returns publish_id for status polling.
        """
        privacy_map = {
            "public":  "PUBLIC_TO_EVERYONE",
            "friends": "MUTUAL_FOLLOW_FRIENDS",
            "private": "SELF_ONLY",
        }
        tiktok_privacy = privacy_map.get(privacy, "PUBLIC_TO_EVERYONE")

        payload = {
            "post_info": {
                "title":            caption[:2200],
                "privacy_level":    tiktok_privacy,
                "disable_duet":     not allow_duet,
                "disable_stitch":   not allow_stitch,
                "disable_comment":  not allow_comments,
            },
            "source_info": {
                "source":    "PULL_FROM_URL",
                "video_url": video_url,
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.VIDEO_INIT,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json; charset=UTF-8",
                },
            )
            if response.status_code not in [200, 201]:
                logging.error(f"[TikTok] Video publish error: {response.text}")
                raise Exception(f"Failed to publish TikTok video: {response.text}")
            data = response.json().get("data", {})
            return {"publish_id": data.get("publish_id", "")}

    async def fetch_posts(self, access_token: str, limit: int = 20) -> list:
        """
        Fetch user's TikTok videos (requires video.list scope).
        Returns empty list gracefully if scope not available.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.tiktokapis.com/v2/video/list/",
                json={"max_count": limit},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json; charset=UTF-8",
                },
            )
            logging.info(f"[TikTok] fetch_posts status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[TikTok] fetch_posts unavailable: {response.text}")
                return []

            videos = response.json().get("data", {}).get("videos", [])
            return [
                {
                    "platform_post_id": v.get("id", ""),
                    "content":          v.get("title", ""),
                    "media_url":        v.get("cover_image_url"),
                    "media_type":       "VIDEO",
                    "post_url":         v.get("share_url"),
                    "metrics": {
                        "likes":    v.get("like_count", 0),
                        "comments": v.get("comment_count", 0),
                        "shares":   v.get("share_count", 0),
                        "views":    v.get("view_count", 0),
                    },
                    "published_at": (
                        datetime.fromtimestamp(v["create_time"], tz=timezone.utc).isoformat()
                        if v.get("create_time")
                        else None
                    ),
                }
                for v in videos
            ]
