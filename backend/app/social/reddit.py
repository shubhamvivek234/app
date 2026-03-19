"""
Reddit OAuth 2.0
Docs: https://www.reddit.com/dev/api/oauth
Auth URL: https://www.reddit.com/api/v1/authorize
Token URL: https://www.reddit.com/api/v1/access_token
API Base: https://oauth.reddit.com
"""
import httpx
import os
import logging
import base64
import urllib.parse
from datetime import datetime, timezone
from fastapi import HTTPException


class RedditAuth:
    """Reddit OAuth 2.0"""

    AUTH_URL  = "https://www.reddit.com/api/v1/authorize"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    BASE_URL  = "https://oauth.reddit.com"

    SCOPES = "identity submit read history mysubreddits"
    USER_AGENT = "SocialEntangler/1.0"

    def __init__(self):
        self.client_id     = os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        self.redirect_uri  = os.environ.get("REDDIT_REDIRECT_URI", "http://localhost:8001/api/oauth/reddit/callback")

    def _basic_auth_header(self) -> str:
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_auth_url(self, state: str) -> str:
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Reddit credentials not configured")

        params = {
            "client_id":     self.client_id,
            "response_type": "code",
            "state":         state,
            "redirect_uri":  self.redirect_uri,
            "duration":      "permanent",   # get a refresh token
            "scope":         self.SCOPES,
        }
        url = f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Reddit] Auth URL generated")
        return url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access + refresh token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "User-Agent":    self.USER_AGENT,
                },
                data={
                    "grant_type":   "authorization_code",
                    "code":         code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            logging.info(f"[Reddit] Token exchange status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Reddit] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Reddit code: {response.text}")
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an expired Reddit access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "User-Agent":    self.USER_AGENT,
                },
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            if response.status_code != 200:
                logging.error(f"[Reddit] Token refresh failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to refresh Reddit token")
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Reddit user profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/v1/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent":    self.USER_AGENT,
                },
            )
            logging.info(f"[Reddit] /api/v1/me status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Reddit] /api/v1/me failed: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Reddit profile")
            return response.json()

    async def get_user_subreddits(self, access_token: str, limit: int = 50) -> list:
        """Get subreddits the user subscribes to / moderates"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/subreddits/mine/subscriber",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent":    self.USER_AGENT,
                },
                params={"limit": limit},
            )
            if response.status_code != 200:
                return []
            return [
                {"name": s["data"]["display_name"], "title": s["data"]["title"]}
                for s in response.json().get("data", {}).get("children", [])
            ]

    async def submit_post(
        self,
        access_token: str,
        subreddit: str,
        title: str,
        text: str = "",
        url: str = "",
        post_type: str = "self",
        nsfw: bool = False,
        spoiler: bool = False,
    ) -> str:
        """Submit a post to a subreddit. post_type: 'self' (text) | 'link' | 'image' | 'video'"""
        async with httpx.AsyncClient() as client:
            payload = {
                "sr":       subreddit,
                "title":    title,
                "kind":     post_type,
                "nsfw":     nsfw,
                "spoiler":  spoiler,
                "resubmit": True,
            }
            if post_type == "self":
                payload["text"] = text
            elif post_type in ("link", "image", "video"):
                payload["url"] = url

            response = await client.post(
                f"{self.BASE_URL}/api/submit",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent":    self.USER_AGENT,
                },
                data=payload,
            )
            if response.status_code not in [200, 201]:
                logging.error(f"[Reddit] Submit failed: {response.text}")
                raise Exception(f"Failed to submit Reddit post: {response.text}")

            data = response.json()
            return data.get("json", {}).get("data", {}).get("id", "")

    async def fetch_user_posts(self, access_token: str, username: str, limit: int = 20) -> list:
        """Fetch user's submitted posts"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/user/{username}/submitted",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent":    self.USER_AGENT,
                },
                params={"limit": limit, "sort": "new"},
            )
            logging.info(f"[Reddit] fetch_user_posts status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Reddit] fetch_user_posts failed: {response.text}")
                return []

            children = response.json().get("data", {}).get("children", [])
            normalized = []
            for child in children:
                p = child.get("data", {})
                import datetime
                pub = datetime.datetime.utcfromtimestamp(p.get("created_utc", 0)).isoformat() + "Z"
                normalized.append({
                    "platform_post_id": p.get("id"),
                    "content":  p.get("title", ""),
                    "media_url": p.get("thumbnail") if p.get("thumbnail", "").startswith("http") else None,
                    "media_type": "IMAGE" if p.get("post_hint") == "image" else "TEXT",
                    "post_url": f"https://www.reddit.com{p.get('permalink', '')}",
                    "metrics": {
                        "likes":    p.get("score", 0),
                        "comments": p.get("num_comments", 0),
                        "views":    p.get("view_count") or 0,
                    },
                    "published_at": pub,
                })
            return normalized

    async def fetch_comments(self, access_token: str, post_id: str, limit: int = 50) -> list:
        """Fetch comments on a Reddit post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/comments/{post_id}",
                params={"sort": "new", "limit": limit, "raw_json": 1},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": self.USER_AGENT,
                },
            )
            logging.info(f"[Reddit] fetch_comments status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Reddit] fetch_comments failed: {response.text}")
                return []

            # Reddit returns [post_listing, comments_listing]
            data = response.json()
            if not isinstance(data, list) or len(data) < 2:
                return []

            comments_data = data[1].get("data", {}).get("children", [])
            comments = []
            for child in comments_data:
                if child.get("kind") != "t1":
                    continue
                c = child.get("data", {})
                comments.append({
                    "id": c.get("name", ""),  # fullname like t1_xxx
                    "author_name": c.get("author", "[deleted]"),
                    "author_avatar": None,
                    "content": c.get("body", ""),
                    "timestamp": (
                        datetime.fromtimestamp(c["created_utc"], tz=timezone.utc).isoformat()
                        if c.get("created_utc") else None
                    ),
                    "likes": c.get("score", 0),
                    "can_reply": True,
                    "platform": "reddit",
                })
            return comments

    async def reply_to_comment(self, access_token: str, thing_id: str, text: str) -> dict:
        """Reply to a Reddit comment (thing_id is the fullname like t1_xxx)"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/api/comment",
                data={"thing_id": thing_id, "text": text, "api_type": "json"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": self.USER_AGENT,
                },
            )
            logging.info(f"[Reddit] reply_to_comment status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Reddit] reply_to_comment failed: {response.text}")
                raise Exception(f"Failed to reply to Reddit comment: {response.text}")

            result = response.json()
            errors = result.get("json", {}).get("errors", [])
            if errors:
                raise Exception(f"Reddit comment error: {errors}")
            return result
