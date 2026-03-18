import httpx
import os
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
import logging
import urllib.parse

class FacebookAuth:
    """Helper class for Facebook/Instagram OAuth and Graph API"""
    
    BASE_URL = "https://graph.facebook.com/v19.0"
    
    def __init__(self):
        self.app_id = os.environ.get('FACEBOOK_APP_ID')
        self.app_secret = os.environ.get('FACEBOOK_APP_SECRET')
        
        raw_uri = os.environ.get('FACEBOOK_REDIRECT_URI', 'http://localhost:8001/api/oauth/facebook/callback')
        # Postiz Bypass: If running on local HTTP, wrap the URI in the redirectmeto.com HTTPS proxy
        if raw_uri.startswith('http://'):
            self.redirect_uri = f"https://redirectmeto.com/{raw_uri}"
        else:
            self.redirect_uri = raw_uri
        
    def get_auth_url(self, state: str) -> str:
        """Generate Facebook Login URL"""
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Facebook credentials not configured")
            
        scope = "email,public_profile,pages_show_list,pages_read_engagement,pages_manage_posts,pages_messaging,instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights,business_management"
        
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": scope,
            "response_type": "code"
        }
        
        auth_url = f"https://www.facebook.com/v19.0/dialog/oauth?{urllib.parse.urlencode(params)}"
        logging.info(f"[Facebook] Generated Auth URL: {auth_url}")
        return auth_url
        
    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "client_id": self.app_id,
                    "redirect_uri": self.redirect_uri,
                    "client_secret": self.app_secret,
                    "code": code
                }
            )
            
            logging.info(f"[Facebook] Token exchange status: {response.status_code}")
            logging.info(f"[Facebook] Token exchange response: {response.text[:500]}")
            
            if response.status_code != 200:
                logging.error(f"Facebook Token Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
                
            return response.json()
            
    async def get_long_lived_token(self, short_lived_token: str) -> dict:
        """Exchange short-lived token for long-lived token (60 days)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": short_lived_token
                }
            )
            
            if response.status_code != 200:
                # If fail, just return the short lived one, but log it
                logging.warning(f"Failed to get long-lived token: {response.text}")
                return {"access_token": short_lived_token, "expires_in": 3600}
                
            return response.json()
            
    async def get_user_profile(self, access_token: str) -> dict:
        """Get Facebook user profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/me",
                params={
                    "fields": "id,name,email,picture",
                    "access_token": access_token
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch user profile")
                
            return response.json()
            
    async def get_accounts(self, access_token: str) -> list:
        """Get connected Pages and Instagram Business Accounts"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/me/accounts",
                params={
                    "fields": "id,name,access_token,picture{url},instagram_business_account{id,username,profile_picture_url}",
                    "access_token": access_token
                }
            )
            
            logging.info(f"[Facebook] /me/accounts status: {response.status_code}")
            logging.info(f"[Facebook] /me/accounts response: {response.text[:2000]}")
            
            if response.status_code != 200:
                logging.error(f"[Facebook] /me/accounts failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch pages: {response.text}")
                
            data = response.json()
            pages = data.get('data', [])
            logging.info(f"[Facebook] Found {len(pages)} page(s): {[p.get('name') for p in pages]}")
            return pages

    async def publish_to_instagram(self, access_token: str, ig_user_id: str, media_url: str, caption: str = "", media_type: str = "IMAGE") -> str:
        """
        Publish media to Instagram
        1. Create Media Container
        2. Publish Media Container
        """
        async with httpx.AsyncClient() as client:
            # 1. Create Media Container
            container_url = f"{self.BASE_URL}/{ig_user_id}/media"
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
                logging.error(f"IG Container Create Error: {error_msg}")
                raise Exception(f"Failed to create IG media container: {error_msg}")
                
            container_id = response.json().get("id")
            
            # 2. If VIDEO, wait for status to be FINISHED
            if media_type == "VIDEO":
                import asyncio
                status_url = f"{self.BASE_URL}/{container_id}"
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
                            raise Exception("Instagram video processing failed")
                    
                    await asyncio.sleep(5) # Wait 5 seconds
            
            # 3. Publish Container
            publish_url = f"{self.BASE_URL}/{ig_user_id}/media_publish"
            publish_params = {
                "access_token": access_token,
                "creation_id": container_id
            }
            
            publish_response = await client.post(publish_url, params=publish_params)
            
            if publish_response.status_code != 200:
                error_msg = publish_response.text
                logging.error(f"IG Publish Error: {error_msg}")
                raise Exception(f"Failed to publish to IG: {error_msg}")
                
            return publish_response.json().get("id")

    async def publish_to_facebook(self, access_token: str, page_id: str, media_url: str, message: str = "", media_type: str = "IMAGE") -> str:
        """
        Publish to Facebook Page
        """
        async with httpx.AsyncClient() as client:
            if media_type == "VIDEO":
                # POST /page_id/videos
                url = f"{self.BASE_URL}/{page_id}/videos"
                params = {
                    "access_token": access_token,
                    "description": message,
                    "file_url": media_url
                }
            else:
                # POST /page_id/photos
                url = f"{self.BASE_URL}/{page_id}/photos"
                params = {
                    "access_token": access_token,
                    "message": message,
                    "url": media_url
                }
                
            response = await client.post(url, params=params)
            
            if response.status_code != 200:
                logging.error(f"FB Publish Error: {response.text}")
                raise Exception(f"Failed to publish to FB: {response.text}")
                
            return response.json().get("id")

    async def fetch_page_posts(self, access_token: str, page_id: str, limit: int = 20) -> list:
        """Fetch Facebook Page posts with engagement metrics"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{page_id}/posts",
                params={
                    "fields": "id,message,story,full_picture,created_time,permalink_url,shares,reactions.summary(true),comments.summary(true)",
                    "limit": limit,
                    "access_token": access_token,
                },
            )

            logging.info(f"[Facebook] fetch_page_posts status: {response.status_code}")

            if response.status_code != 200:
                logging.error(f"[Facebook] fetch_page_posts failed: {response.text}")
                return []

            data = response.json()
            posts = data.get("data", [])

            normalized = []
            for post in posts:
                reactions = post.get("reactions", {}).get("summary", {}).get("total_count", 0)
                comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                shares = post.get("shares", {}).get("count", 0)
                normalized.append({
                    "platform_post_id": post.get("id"),
                    "content": post.get("message") or post.get("story", ""),
                    "media_url": post.get("full_picture"),
                    "media_type": "IMAGE" if post.get("full_picture") else "TEXT",
                    "post_url": post.get("permalink_url"),
                    "metrics": {
                        "likes": reactions,
                        "comments": comments,
                        "shares": shares,
                    },
                    "published_at": post.get("created_time"),
                })

            return normalized

    async def fetch_page_demographics(self, access_token: str, page_id: str) -> dict:
        """Fetch Facebook Page fan demographics"""
        result = {"age": [], "gender": [], "cities": [], "countries": [], "supported": True}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{page_id}/insights",
                params={
                    "metric": "page_fans_city,page_fans_country,page_fans_gender_age",
                    "period": "lifetime",
                    "access_token": access_token,
                },
            )
            logging.info(f"[Facebook] fetch_page_demographics status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Facebook] fetch_page_demographics failed: {response.text}")
                result["supported"] = False
                result["error"] = "Demographics not available for this page"
                return result

            data = response.json().get("data", [])
            for metric in data:
                name = metric.get("name", "")
                values = metric.get("values", [{}])
                val_data = values[-1].get("value", {}) if values else {}

                if name == "page_fans_gender_age":
                    # Keys like "F.18-24", "M.25-34", etc.
                    gender_totals = {}
                    age_totals = {}
                    for key, count in val_data.items():
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            g, a = parts
                            gender_label = {"F": "Female", "M": "Male", "U": "Other"}.get(g, g)
                            gender_totals[gender_label] = gender_totals.get(gender_label, 0) + count
                            age_totals[a] = age_totals.get(a, 0) + count
                    result["gender"] = [{"label": k, "count": v} for k, v in gender_totals.items()]
                    result["age"] = [{"range": k, "count": v} for k, v in age_totals.items()]

                elif name == "page_fans_city":
                    result["cities"] = [{"name": k, "count": v} for k, v in val_data.items()]

                elif name == "page_fans_country":
                    result["countries"] = [{"name": k, "count": v} for k, v in val_data.items()]

            for key in ["age", "gender", "cities", "countries"]:
                result[key].sort(key=lambda x: x.get("count", 0), reverse=True)

            return result

    async def fetch_comments(self, access_token: str, post_id: str, limit: int = 50) -> list:
        """Fetch comments on a Facebook Page post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{post_id}/comments",
                params={
                    "fields": "id,message,from,created_time,like_count",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Facebook] fetch_comments status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Facebook] fetch_comments failed: {response.text}")
                return []

            comments = response.json().get("data", [])
            return [
                {
                    "id": c.get("id"),
                    "author_name": c.get("from", {}).get("name", "Unknown"),
                    "author_avatar": None,
                    "content": c.get("message", ""),
                    "timestamp": c.get("created_time"),
                    "likes": c.get("like_count", 0),
                    "can_reply": True,
                    "platform": "facebook",
                }
                for c in comments
            ]

    async def reply_to_comment(self, access_token: str, comment_id: str, text: str) -> dict:
        """Reply to a comment on a Facebook Page post"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{comment_id}/comments",
                params={
                    "message": text,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Facebook] reply_to_comment status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Facebook] reply_to_comment failed: {response.text}")
                raise Exception(f"Failed to reply to Facebook comment: {response.text}")
            return response.json()

    async def fetch_page_conversations(self, access_token: str, page_id: str, limit: int = 20) -> list:
        """Fetch Facebook Page DM conversations"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/{page_id}/conversations",
                params={
                    "fields": "id,participants,messages{id,message,from,created_time}",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            logging.info(f"[Facebook] fetch_page_conversations status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Facebook] fetch_page_conversations failed: {response.text}")
                return []

            conversations = response.json().get("data", [])
            normalized = []
            for conv in conversations:
                participants = conv.get("participants", {}).get("data", [])
                messages = conv.get("messages", {}).get("data", [])
                normalized.append({
                    "id": conv.get("id"),
                    "participants": [p.get("name", "Unknown") for p in participants],
                    "messages": [
                        {
                            "id": m.get("id"),
                            "content": m.get("message", ""),
                            "from": m.get("from", {}).get("name", "Unknown"),
                            "timestamp": m.get("created_time"),
                        }
                        for m in messages
                    ],
                })
            return normalized

    async def send_page_message(self, access_token: str, page_id: str, recipient_id: str, text: str) -> dict:
        """Send a message from a Facebook Page"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{page_id}/messages",
                params={"access_token": access_token},
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": text},
                    "messaging_type": "RESPONSE",
                },
            )
            logging.info(f"[Facebook] send_page_message status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Facebook] send_page_message failed: {response.text}")
                raise Exception(f"Failed to send Facebook message: {response.text}")
            return response.json()
