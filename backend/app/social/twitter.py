import httpx
import os
import logging
import base64
import hashlib
import secrets
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

class TwitterAuth:
    """Twitter API v2 OAuth 2.0 with PKCE"""

    AUTH_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    USER_URL = "https://api.twitter.com/2/users/me"
    TWEET_URL = "https://api.twitter.com/2/tweets"

    def __init__(self):
        self.client_id = os.environ.get('TWITTER_CLIENT_ID')
        self.client_secret = os.environ.get('TWITTER_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('TWITTER_REDIRECT_URI') or os.environ.get('OAUTH_REDIRECT_URI')
        
        # Fallback for local development if env is not loading correctly
        if not self.redirect_uri or 'localhost' in self.redirect_uri:
             # Check if we should prefer 127.0.0.1 based on user settings
             self.redirect_uri = "http://127.0.0.1:8001/api/oauth/twitter/callback"
             logging.info(f"[TwitterAuth] Using fallback redirect_uri: {self.redirect_uri}")

    def generate_pkce(self):
        """Generate verifier and challenge for PKCE"""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return verifier, challenge

    def get_auth_url(self, state: str, code_challenge: str) -> str:
        """Generate Twitter OAuth 2.0 URL"""
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Twitter credentials not configured")
        
        scopes = "tweet.read tweet.write users.read offline.access"
        return (
            f"{self.AUTH_URL}"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

    async def exchange_code_for_token(self, code: str, code_verifier: str) -> dict:
        """Exchange code for access token using code_verifier"""
        async with httpx.AsyncClient() as client:
            data = {
                "code": code,
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            }
            # Twitter requires Basic Auth with client_id:client_secret for confidential clients
            auth = (self.client_id, self.client_secret)
            response = await client.post(self.TOKEN_URL, data=data, auth=auth)
            
            if response.status_code != 200:
                logging.error(f"Twitter Token Exchange Error: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Twitter code: {response.text}")
                
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh expired access token"""
        async with httpx.AsyncClient() as client:
            data = {
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "client_id": self.client_id,
            }
            auth = (self.client_id, self.client_secret)
            response = await client.post(self.TOKEN_URL, data=data, auth=auth)
            
            if response.status_code != 200:
                logging.error(f"Twitter Token Refresh Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to refresh Twitter token")
                
            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Twitter user profile"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"user.fields": "id,name,username,profile_image_url"}
            )
            
            if response.status_code != 200:
                logging.error(f"Twitter User Profile Error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Twitter user profile")
                
            return response.json().get('data', {})

    async def publish_tweet(self, access_token: str, text: str, media_urls: list = None) -> str:
        """Publish a tweet (v2 API)"""
        async with httpx.AsyncClient() as client:
            # Note: Media upload in v2 is still complex and often requires v1.1
            # For now, we'll implement simple text posting.
            # If media_urls are provided, we'd need to upload them first.
            
            payload = {"text": text}
            
            # TODO: Implement media upload if needed
            # For now, just include the URL in the text if it's there
            if media_urls:
                payload["text"] = f"{text}\n\n{media_urls[0]}"

            response = await client.post(
                self.TWEET_URL,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=payload
            )
            
            if response.status_code not in [200, 201]:
                logging.error(f"Twitter Post Error: {response.text}")
                raise Exception(f"Failed to publish tweet: {response.text}")
                
            return response.json().get('data', {}).get('id')
