import httpx
import os
import logging
from fastapi import HTTPException
from urllib.parse import urlencode

class LinkedInAuth:
    """LinkedIn OAuth 2.0 and API"""

    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    USER_URL = "https://api.linkedin.com/v2/userinfo" # New OIDC userinfo
    POST_URL = "https://api.linkedin.com/v2/ugcPosts" # Or the new /rest/posts

    def __init__(self):
        self.client_id = os.environ.get('LINKEDIN_CLIENT_ID')
        self.client_secret = os.environ.get('LINKEDIN_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('LINKEDIN_REDIRECT_URI')

    def get_auth_url(self, state: str) -> str:
        """Generate LinkedIn OAuth URL"""
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="LinkedIn credentials not configured")
        
        scopes = "openid profile email w_member_social"
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": scopes
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange code for access token"""
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            }
            response = await client.post(self.TOKEN_URL, data=data)
            
            if response.status_code != 200:
                logging.error(f"LinkedIn Token Exchange Error: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange LinkedIn code: {response.text}")
                
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get LinkedIn user profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                logging.error(f"LinkedIn User Profile Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch LinkedIn user profile")
                
            return response.json()

    async def publish_post(self, access_token: str, person_urn: str, text: str, media_urls: list = None) -> str:
        """Publish a post to LinkedIn member profile"""
        async with httpx.AsyncClient() as client:
            # LinkedIn UGC Post structure
            payload = {
                "author": f"urn:li:person:{person_urn}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": text
                        },
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                }
            }
            
            if media_urls:
                # For simplicity in MVP, we just append URL if it's there
                # Proper image/video upload requires multi-step process
                payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] = f"{text}\n\n{media_urls[0]}"

            response = await client.post(
                self.POST_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0"
                },
                json=payload
            )
            
            if response.status_code not in [200, 201]:
                logging.error(f"LinkedIn Post Error: {response.text}")
                raise Exception(f"Failed to publish to LinkedIn: {response.text}")
                
            return response.headers.get('x-restli-id')
