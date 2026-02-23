import httpx
import os
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
import logging

class FacebookAuth:
    """Helper class for Facebook/Instagram OAuth and Graph API"""
    
    BASE_URL = "https://graph.facebook.com/v19.0"
    
    def __init__(self):
        self.app_id = os.environ.get('FACEBOOK_APP_ID')
        self.app_secret = os.environ.get('FACEBOOK_APP_SECRET')
        self.redirect_uri = os.environ.get('FACEBOOK_REDIRECT_URI')
        
    def get_auth_url(self, state: str) -> str:
        """Generate Facebook Login URL"""
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Facebook credentials not configured")
            
        scope = "email,public_profile,pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights,business_management"
        
        return (
            f"https://www.facebook.com/v19.0/dialog/oauth"
            f"?client_id={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&state={state}"
            f"&scope={scope}"
            f"&response_type=code"
        )
        
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
