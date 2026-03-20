"""
Instagram Business Login (Standalone)
Uses Instagram API with Instagram Login — does NOT require a Facebook Page.
Official docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""
import httpx
import os
import logging
from fastapi import HTTPException
import urllib.parse


class InstagramAuth:
    """Instagram Business Login standalone (no Facebook Page required)"""

    OAUTH_URL = "https://api.instagram.com/oauth/authorize"
    TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    GRAPH_URL = "https://graph.instagram.com/v19.0"

    def __init__(self):
        self.app_id = os.environ.get("INSTAGRAM_APP_ID") or os.environ.get("FACEBOOK_APP_ID")
        self.app_secret = os.environ.get("INSTAGRAM_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET")
        
        raw_uri = os.environ.get("INSTAGRAM_REDIRECT_URI") or os.environ.get("FACEBOOK_REDIRECT_URI", "").replace(
            "/oauth/facebook/callback", "/oauth/instagram/callback"
        )
        
        # Postiz Bypass: Wrap local HTTP URLs in the redirectmeto HTTPS proxy for Meta API
        if raw_uri.startswith('http://'):
            self.redirect_uri = f"https://redirectmeto.com/{raw_uri}"
        else:
            self.redirect_uri = raw_uri

    def get_auth_url(self, state: str) -> str:
        """Generate Instagram Business Login authorization URL"""
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Instagram credentials not configured")

        scope = "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_comments,instagram_business_manage_insights,instagram_business_manage_messages"

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "response_type": "code",
            "state": state
        }
        
        auth_url = f"{self.OAUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Instagram] Generated Auth URL: {auth_url}")
        return auth_url

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

    async def publish_to_instagram(self, access_token: str, ig_user_id: str, media_url: str, caption: str = "", media_type: str = "IMAGE") -> str:
        """
        Publish media to Instagram using the Standalone API
        1. Create Media Container
        2. Check Status (if video)
        3. Publish Media Container
        """
        async with httpx.AsyncClient() as client:
            # 1. Create Media Container
            container_url = f"{self.GRAPH_URL}/{ig_user_id}/media"
            params = {
                "access_token": access_token,
                "caption": caption
            }
            
            if media_type == "VIDEO":
                params["media_type"] = "REELS" 
                params["video_url"] = media_url
            else:
                params["image_url"] = media_url
            
            response = await client.post(container_url, params=params)
            
            if response.status_code != 200:
                error_msg = response.text
                logging.error(f"[Standalone IG] Container Create Error: {error_msg}")
                raise Exception(f"Failed to create standalone IG media container: {error_msg}")
                
            container_id = response.json().get("id")
            
            # 2. If VIDEO, wait for status to be FINISHED
            if media_type == "VIDEO":
                import asyncio
                status_url = f"{self.GRAPH_URL}/{container_id}"
                status_params = {
                    "fields": "status_code",
                    "access_token": access_token
                }
                
                max_retries = 30 # 30 * 5s = 2.5 minutes timeout
                for _ in range(max_retries):
                    status_response = await client.get(status_url, params=status_params)
                    if status_response.status_code == 200:
                        status_code = status_response.json().get("status_code")
                        if status_code == "FINISHED":
                            break
                        elif status_code == "ERROR":
                            raise Exception("Standalone IG video processing failed")
                    
                    await asyncio.sleep(5)
            
            # 3. Publish Container
            publish_url = f"{self.GRAPH_URL}/{ig_user_id}/media_publish"
            publish_params = {
                "access_token": access_token,
                "creation_id": container_id
            }
            
            publish_response = await client.post(publish_url, params=publish_params)
            
            if publish_response.status_code != 200:
                error_msg = publish_response.text
                logging.error(f"[Standalone IG] Publish Error: {error_msg}")
                raise Exception(f"Failed to publish to standalone IG: {error_msg}")
                
            return publish_response.json().get("id")

    async def fetch_feed(self, access_token: str, user_id: str, limit: int = 25) -> list:
        """Fetch recent media from Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}/media",
                params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,permalink",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] Feed fetch failed: {response.text}")
                return []
            posts = response.json().get("data", [])
            result = []
            for post in posts:
                media_type = post.get("media_type", "IMAGE")
                if media_type in ("VIDEO", "REELS"):
                    display_url = post.get("thumbnail_url") or post.get("media_url")
                    video_url = post.get("media_url")
                else:
                    display_url = post.get("media_url") or post.get("thumbnail_url")
                    video_url = None
                result.append({
                    "id": post.get("id"),
                    "content": post.get("caption", ""),
                    "media_url": display_url,
                    "video_url": video_url,
                    "media_type": media_type,
                    "timestamp": post.get("timestamp"),
                    "likes": post.get("like_count", 0),
                    "comments_count": post.get("comments_count", 0),
                    "permalink": post.get("permalink"),
                    "platform": "instagram",
                })
            return result

    async def fetch_engagement(self, access_token: str, user_id: str) -> dict:
        """Fetch Instagram account engagement metrics"""
        async with httpx.AsyncClient() as client:
            # Get user profile stats
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}",
                params={
                    "fields": "id,username,followers_count,follows_count,media_count",
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                return {}
            profile = response.json()

            # Get insights
            insights = {}
            try:
                insights_resp = await client.get(
                    f"{self.GRAPH_URL}/{user_id}/insights",
                    params={
                        "metric": "impressions,reach,profile_views",
                        "period": "day",
                        "metric_type": "total_value",
                        "access_token": access_token,
                    },
                )
                if insights_resp.status_code == 200:
                    for item in insights_resp.json().get("data", []):
                        name = item.get("name")
                        val = item.get("total_value", {}).get("value", 0)
                        insights[name] = val
            except Exception as e:
                logging.warning(f"[Instagram] Insights fetch failed: {e}")

            return {
                "followers": profile.get("followers_count", 0),
                "following": profile.get("follows_count", 0),
                "posts_count": profile.get("media_count", 0),
                "impressions": insights.get("impressions", 0),
                "reach": insights.get("reach", 0),
                "profile_views": insights.get("profile_views", 0),
                "platform": "instagram",
            }

    async def fetch_demographics(self, access_token: str, user_id: str) -> dict:
        """Fetch follower demographics (requires 100+ followers)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}/insights",
                params={
                    "metric": "follower_demographics",
                    "period": "lifetime",
                    "metric_type": "total_value",
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] Demographics fetch failed: {response.text}")
                return {"supported": False, "error": "Could not fetch demographics"}

            data = response.json().get("data", [])
            result = {"age": [], "gender": [], "cities": [], "countries": [], "supported": True}

            for metric in data:
                breakdowns = metric.get("total_value", {}).get("breakdowns", [])
                for breakdown in breakdowns:
                    dimension = breakdown.get("dimension_keys", [""])[0]
                    results = breakdown.get("results", [])

                    if dimension == "age":
                        for r in results:
                            result["age"].append({"range": r.get("dimension_values", [""])[0], "count": r.get("value", 0)})
                    elif dimension == "city":
                        for r in sorted(results, key=lambda x: x.get("value", 0), reverse=True)[:10]:
                            result["cities"].append({"name": r.get("dimension_values", [""])[0], "count": r.get("value", 0)})
                    elif dimension == "country":
                        for r in sorted(results, key=lambda x: x.get("value", 0), reverse=True)[:10]:
                            result["countries"].append({"name": r.get("dimension_values", [""])[0], "count": r.get("value", 0)})
                    elif dimension == "gender":
                        for r in results:
                            result["gender"].append({"label": r.get("dimension_values", [""])[0], "count": r.get("value", 0)})

            return result

    async def fetch_comments(self, access_token: str, media_id: str, limit: int = 50) -> list:
        """Fetch comments on a media post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{media_id}/comments",
                params={
                    "fields": "id,text,username,timestamp,like_count",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] Comments fetch failed: {response.text}")
                return []
            comments = []
            for c in response.json().get("data", []):
                comments.append({
                    "id": c.get("id"),
                    "author_name": c.get("username", "Unknown"),
                    "author_avatar": None,
                    "content": c.get("text", ""),
                    "timestamp": c.get("timestamp"),
                    "likes": c.get("like_count", 0),
                    "can_reply": True,
                    "platform": "instagram",
                })
            return comments

    async def reply_to_comment(self, access_token: str, comment_id: str, text: str) -> dict:
        """Reply to a comment on Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/{comment_id}/replies",
                params={
                    "message": text,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.error(f"[Instagram] Reply failed: {response.text}")
                raise Exception(f"Failed to reply: {response.text}")
            return response.json()

    async def fetch_conversations(self, access_token: str, user_id: str, limit: int = 20) -> list:
        """Fetch Instagram DM conversations"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}/conversations",
                params={
                    "fields": "id,participants,messages{id,message,from,created_time}",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] DM fetch failed: {response.text}")
                return []
            conversations = []
            for conv in response.json().get("data", []):
                messages = conv.get("messages", {}).get("data", [])
                latest = messages[0] if messages else {}
                conversations.append({
                    "id": conv.get("id"),
                    "participants": [p.get("name", "Unknown") for p in conv.get("participants", {}).get("data", [])],
                    "last_message": latest.get("message", ""),
                    "last_message_time": latest.get("created_time"),
                    "platform": "instagram",
                })
            return conversations

    async def send_message(self, access_token: str, recipient_id: str, text: str) -> dict:
        """Send a DM on Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/me/messages",
                params={"access_token": access_token},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
            )
            if response.status_code != 200:
                logging.error(f"[Instagram] DM send failed: {response.text}")
                raise Exception(f"Failed to send message: {response.text}")
            return response.json()
