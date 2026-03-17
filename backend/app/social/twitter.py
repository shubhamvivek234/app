import httpx
import os
import logging
import base64
import hashlib
import secrets
import urllib.parse
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
        raw_uri = os.environ.get('TWITTER_REDIRECT_URI') or os.environ.get('OAUTH_REDIRECT_URI')
        
        # Reverting bypass for Twitter because X portal rejects the redirectmeto.com format.
        # X allows http://127.0.0.1 and http://localhost directly for development.
        if raw_uri and 'localhost' in raw_uri:
            # Force replace localhost with 127.0.0.1 if that's what's working in the portal
            self.redirect_uri = raw_uri.replace('localhost', '127.0.0.1')
            logging.info(f"[TwitterAuth] Local development detected. Using direct IP: {self.redirect_uri}")
        else:
            self.redirect_uri = raw_uri
            
        logging.info(f"[TwitterAuth] Using redirect_uri: {self.redirect_uri}")

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
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        auth_url = f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[TwitterAuth] Generated Auth URL: {auth_url}")
        return auth_url

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
            logging.info(f"[TwitterAuth] Exchanging code for token... redirect_uri={self.redirect_uri}")
            response = await client.post(self.TOKEN_URL, data=data, auth=auth)
            
            logging.info(f"[TwitterAuth] Token exchange status: {response.status_code}")
            logging.info(f"[TwitterAuth] Token exchange response: {response.text[:500]}")
            
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

    async def fetch_tweets(self, access_token: str, user_id: str, limit: int = 25) -> list:
        """Fetch recent tweets"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.twitter.com/2/users/{}/tweets".format(user_id),
                params={
                    "max_results": min(limit, 100),
                    "tweet.fields": "created_at,public_metrics,entities",
                    "expansions": "attachments.media_keys",
                    "media.fields": "url,preview_image_url,type",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                logging.warning(f"[Twitter] Feed fetch failed: {response.text}")
                return []

            media_map = {}
            for m in response.json().get("includes", {}).get("media", []):
                media_map[m.get("media_key")] = m.get("url") or m.get("preview_image_url")

            posts = []
            for t in response.json().get("data", []):
                metrics = t.get("public_metrics", {})
                media_keys = t.get("attachments", {}).get("media_keys", [])
                media_url = media_map.get(media_keys[0]) if media_keys else None
                posts.append({
                    "id": t.get("id"),
                    "content": t.get("text", ""),
                    "media_url": media_url,
                    "media_type": "IMAGE",
                    "timestamp": t.get("created_at"),
                    "likes": metrics.get("like_count", 0),
                    "comments_count": metrics.get("reply_count", 0),
                    "retweets": metrics.get("retweet_count", 0),
                    "permalink": f"https://twitter.com/i/status/{t['id']}",
                    "platform": "twitter",
                })
            return posts

    async def fetch_engagement(self, access_token: str, user_id: str) -> dict:
        """Fetch Twitter user engagement metrics"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.twitter.com/2/users/{user_id}",
                params={"user.fields": "public_metrics"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                return {}
            data = response.json().get("data", {})
            metrics = data.get("public_metrics", {})
            return {
                "followers": metrics.get("followers_count", 0),
                "following": metrics.get("following_count", 0),
                "tweet_count": metrics.get("tweet_count", 0),
                "platform": "twitter",
            }
