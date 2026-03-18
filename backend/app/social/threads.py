"""
Threads OAuth — Meta's Threads API (released June 2024).
Docs: https://developers.facebook.com/docs/threads
Auth URL: https://threads.net/oauth/authorize
Token URL: https://graph.threads.net/oauth/access_token
API Base: https://graph.threads.net/v1.0
"""
import httpx
import os
import logging
import urllib.parse
from fastapi import HTTPException


class ThreadsAuth:
    """Threads API OAuth 2.0"""

    AUTH_URL  = "https://threads.net/oauth/authorize"
    TOKEN_URL = "https://graph.threads.net/oauth/access_token"
    BASE_URL  = "https://graph.threads.net/v1.0"

    SCOPES = "threads_basic,threads_content_publish,threads_manage_insights,threads_manage_replies"

    def __init__(self):
        self.app_id     = os.environ.get("THREADS_APP_ID") or os.environ.get("FACEBOOK_APP_ID")
        self.app_secret = os.environ.get("THREADS_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET")
        raw_uri         = os.environ.get("THREADS_REDIRECT_URI", "http://localhost:8001/api/oauth/threads/callback")

        # Wrap local HTTP redirect with Meta-compatible HTTPS proxy
        if raw_uri.startswith("http://"):
            self.redirect_uri = f"https://redirectmeto.com/{raw_uri}"
        else:
            self.redirect_uri = raw_uri

    def get_auth_url(self, state: str) -> str:
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Threads credentials not configured")

        params = {
            "client_id":     self.app_id,
            "redirect_uri":  self.redirect_uri,
            "scope":         self.SCOPES,
            "response_type": "code",
            "state":         state,
        }
        url = f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Threads] Auth URL generated: {url}")
        return url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for short-lived access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id":     self.app_id,
                    "client_secret": self.app_secret,
                    "grant_type":    "authorization_code",
                    "redirect_uri":  self.redirect_uri,
                    "code":          code,
                },
            )
            logging.info(f"[Threads] Token exchange status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Threads] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Threads code: {response.text}")
            return response.json()

    async def get_long_lived_token(self, short_lived_token: str) -> dict:
        """Exchange short-lived token for long-lived token (60 days)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/access_token",
                params={
                    "grant_type":    "th_exchange_token",
                    "client_secret": self.app_secret,
                    "access_token":  short_lived_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Threads] Long-lived token failed: {response.text}, using short-lived")
                return {"access_token": short_lived_token}
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Threads user profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/me",
                params={
                    "fields":       "id,name,username,threads_profile_picture_url,threads_biography",
                    "access_token": access_token,
                },
            )
            logging.info(f"[Threads] /me status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Threads] /me failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch Threads profile: {response.text}")
            return response.json()

    async def publish_post(self, access_token: str, user_id: str, text: str, media_url: str = None, media_type: str = "TEXT") -> str:
        """
        Publish a Threads post.
        1. Create media container
        2. Publish container
        """
        async with httpx.AsyncClient() as client:
            container_params = {
                "media_type":   media_type,
                "text":         text,
                "access_token": access_token,
            }
            if media_url and media_type == "IMAGE":
                container_params["image_url"] = media_url
            elif media_url and media_type == "VIDEO":
                container_params["video_url"] = media_url

            # Step 1: Create container
            container_resp = await client.post(
                f"{self.BASE_URL}/{user_id}/threads",
                params=container_params,
            )
            if container_resp.status_code != 200:
                raise Exception(f"[Threads] Container create failed: {container_resp.text}")

            container_id = container_resp.json().get("id")

            # Step 2: Publish container
            publish_resp = await client.post(
                f"{self.BASE_URL}/{user_id}/threads_publish",
                params={"creation_id": container_id, "access_token": access_token},
            )
            if publish_resp.status_code != 200:
                raise Exception(f"[Threads] Publish failed: {publish_resp.text}")

            return publish_resp.json().get("id")

    async def fetch_posts(self, access_token: str, user_id: str = "me", limit: int = 20) -> list:
        """Fetch user's Threads posts with metrics"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{user_id}/threads",
                params={
                    "fields":       "id,text,media_type,media_url,thumbnail_url,timestamp,permalink,views,likes,replies,reposts,quotes",
                    "limit":        limit,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Threads] fetch_posts status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Threads] fetch_posts failed: {response.text}")
                return []

            posts = response.json().get("data", [])
            normalized = []
            for post in posts:
                media_type = post.get("media_type", "TEXT")
                if media_type == "VIDEO":
                    display_url = post.get("thumbnail_url") or post.get("media_url")
                    video_url = post.get("media_url")
                else:
                    display_url = post.get("media_url") or post.get("thumbnail_url")
                    video_url = None

                normalized.append({
                    "platform_post_id": post.get("id"),
                    "content":          post.get("text", ""),
                    "media_url":        display_url,
                    "video_url":        video_url,
                    "media_type":       media_type,
                    "post_url":         post.get("permalink"),
                    "metrics": {
                        "views":    post.get("views", 0),
                        "likes":    post.get("likes", 0),
                        "comments": post.get("replies", 0),
                        "shares":   post.get("reposts", 0),
                    },
                    "published_at": post.get("timestamp"),
                })
            return normalized

    async def fetch_replies(self, access_token: str, media_id: str, limit: int = 50) -> list:
        """Fetch replies to a Threads post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{media_id}/replies",
                params={
                    "fields": "id,text,username,timestamp,media_type",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Threads] fetch_replies status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Threads] fetch_replies failed: {response.text}")
                return []

            replies = response.json().get("data", [])
            return [
                {
                    "id": r.get("id"),
                    "author_name": r.get("username", "Unknown"),
                    "author_avatar": None,
                    "content": r.get("text", ""),
                    "timestamp": r.get("timestamp"),
                    "likes": 0,
                    "can_reply": True,
                    "platform": "threads",
                }
                for r in replies
            ]

    async def reply_to_thread(self, access_token: str, user_id: str, reply_to_id: str, text: str) -> str:
        """Reply to a Threads post (creates a reply thread)"""
        async with httpx.AsyncClient() as client:
            # Step 1: Create reply container
            response = await client.post(
                f"{self.BASE_URL}/{user_id}/threads",
                params={
                    "media_type": "TEXT",
                    "text": text,
                    "reply_to_id": reply_to_id,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Threads] reply_to_thread container status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Threads] reply_to_thread container failed: {response.text}")
                raise Exception(f"Failed to create Threads reply: {response.text}")

            container_id = response.json().get("id")

            # Step 2: Publish the reply
            publish_response = await client.post(
                f"{self.BASE_URL}/{user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Threads] reply_to_thread publish status: {publish_response.status_code}")
            if publish_response.status_code != 200:
                logging.error(f"[Threads] reply_to_thread publish failed: {publish_response.text}")
                raise Exception(f"Failed to publish Threads reply: {publish_response.text}")

            return publish_response.json().get("id")
