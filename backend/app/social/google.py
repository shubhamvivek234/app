import httpx
import os
from fastapi import HTTPException
import logging
from datetime import datetime, timedelta, timezone

class GoogleAuth:
    """Helper class for Google/YouTube OAuth"""
    
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"
    
    def __init__(self):
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
        
    def get_auth_url(self, state: str) -> str:
        """Generate Google OAuth URL for YouTube"""
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Google credentials not configured")
            
        # Scopes for YouTube upload and channel management
        scope = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
        
        return (
            f"{self.AUTH_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&state={state}"
            f"&access_type=offline" # Important for refresh token
            f"&prompt=consent" # Force consent to get refresh token
        )
        
    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token"""
        # MOCK IMPLEMENTATION
        if os.environ.get('MOCK_GOOGLE_AUTH') == 'true':
            logging.info("Using MOCK Google Auth Exchange")
            return {
                "access_token": "mock_access_token_" + code,
                "expires_in": 3599,
                "scope": "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/userinfo.profile",
                "token_type": "Bearer",
                "id_token": "mock_id_token"
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri
                }
            )
            
            if response.status_code != 200:
                logging.error(f"Google Token Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
                
            return response.json()
            
    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh expired access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to refresh token")
                
            return response.json()

    async def get_channel_info(self, access_token: str) -> dict:
        """Get YouTube channel info"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.YOUTUBE_URL}/channels",
                params={
                    "part": "snippet,contentDetails",
                    "mine": "true"
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                logging.error(f"YouTube API Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch channel info")
                
            data = response.json()
            items = data.get('items', [])
            if not items:
                raise HTTPException(status_code=404, detail="No YouTube channel found")
                
            return items[0]

    async def upload_video(self, access_token: str, file_path: str, title: str, description: str, privacy_status: str = "public") -> str:
        """
        Upload video to YouTube
        Note: Simple upload for now. Resumable upload is better for large files.
        """
        import os
        
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
            
        file_size = os.path.getsize(file_path)
        
        # 1. Prepare Metadata
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["SocialEntangler", "AutoPosted"],
                "categoryId": "22" # People & Blogs
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }
        
        # 2. Upload (using multipart/related for smaller files or resumable for larger)
        # Using simple multipart here for MVP
        
        # We need to use valid multipart construction
        # Just using httpx's files parameter which handles multipart
        
        upload_url = "https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status"
        
        import json
        
        # httpx files handling:
        # files = {'file': open(file_path, 'rb'), 'json': (None, json.dumps(metadata), 'application/json')}
        # Specifically for Google API, the metadata part needs to be first and named 'resource' usually check docs?
        # Actually Google recommends Resumable Uploads for most things.
        # Let's try the simple upload endpoint first.
        
        async with httpx.AsyncClient() as client:
            # For YouTube 'multipart' upload, the metadata must be the first part with name 'snippet' (or no name but application/json type)
            # and video second. This is tricky with high-level libraries sometimes.
            # Let's use the resumable protocol as it's more robust.
            
            # RESUMABLE UPLOAD
            init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4" # Assume mp4 for now
            }
            
            # Step 1: Initiate
            init_response = await client.post(init_url, headers=headers, json=metadata)
            
            if init_response.status_code != 200:
                logging.error(f"YouTube Upload Init Failed: {init_response.text}")
                raise Exception(f"YouTube Upload Init Failed: {init_response.text}")
                
            upload_url = init_response.headers.get("Location")
            
            if not upload_url:
                raise Exception("No upload URL returned from YouTube")
                
            # Step 2: Upload File
            with open(file_path, "rb") as f:
                file_data = f.read()
                
            # PUT the file
            put_headers = {
                "Content-Length": str(file_size),
                "Content-Type": "video/mp4"
            }
            
            upload_response = await client.put(upload_url, headers=put_headers, content=file_data)
            
            if upload_response.status_code not in [200, 201]:
                logging.error(f"YouTube File Upload Failed: {upload_response.text}")
                raise Exception(f"YouTube File Upload Failed: {upload_response.text}")
                
            return upload_response.json().get("id")

    def get_login_url(self, state: str) -> str:
        """Generate Google OAuth URL for Login"""
        # MOCK IMPLEMENTATION
        if os.environ.get('MOCK_GOOGLE_AUTH') == 'true':
            logging.info("Using MOCK Google Login URL")
            # Redirect directly to our callback with a mock code
            # Note: server.py callback expects 'code' and 'state'
            return f"http://localhost:8001/api/auth/google/callback?code=mock_code_123&state={state}"

        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Google credentials not configured")
            
        # Scopes for Login
        scope = "openid email profile"
        
        return (
            f"{self.AUTH_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&state={state}"
            f"&access_type=offline"
            f"&prompt=select_account"
        )

    async def get_user_info(self, access_token: str) -> dict:
        """Get User Info for Login"""
        # MOCK IMPLEMENTATION
        if os.environ.get('MOCK_GOOGLE_AUTH') == 'true':
            logging.info("Using MOCK Google User Info")
            return {
                "sub": "mock_google_id_12345",
                "name": "Shubham Kumar",
                "given_name": "Shubham",
                "family_name": "Kumar",
                "picture": "https://lh3.googleusercontent.com/a/ACg8ocIY...",
                "email": "findshubhamkumar@gmail.com",
                "email_verified": True,
                "locale": "en"
            }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                logging.error(f"Google User Info Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch user info")
                
            return response.json()
