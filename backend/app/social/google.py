import httpx
import os
from fastapi import HTTPException
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

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
        frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        self.youtube_redirect_uri = os.environ.get('YOUTUBE_REDIRECT_URI', f'{frontend_url}/oauth/callback')
        
        if not self.client_id:
             logging.error(f"DEBUG: GOOGLE_CLIENT_ID NOT FOUND. ENV VARS KEYS: {[k for k in os.environ.keys() if 'GOOGLE' in k]}")
             # Check if .env file exists
             from pathlib import Path
             env_path = Path(__file__).parent.parent.parent / '.env'
             logging.info(f"DEBUG: Checking .env at {env_path}, exists={env_path.exists()}")
             if env_path.exists():
                 logging.info(f"DEBUG: .env content (partial): {open(env_path).read()[:50]}")
        
    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        """Generate Google OAuth URL for YouTube"""
        oauth_redirect_uri = redirect_uri or self.youtube_redirect_uri
        if not self.client_id or not oauth_redirect_uri:
            raise HTTPException(status_code=500, detail="Google/YouTube credentials not configured")
            
        # Scopes for YouTube upload and channel management
        scope = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly"
        
        return (
            f"{self.AUTH_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={oauth_redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&state={state}"
            f"&access_type=offline" # Important for refresh token
            f"&prompt=consent" # Force consent to get refresh token
        )
        
    async def exchange_code_for_token(self, code: str, redirect_uri: str = None) -> dict:
        """Exchange authorization code for access token"""
        # Use provided redirect_uri or default to self.redirect_uri (login)
        use_redirect_uri = redirect_uri if redirect_uri else self.redirect_uri
        
        # MOCK IMPLEMENTATION
        if os.environ.get('MOCK_GOOGLE_AUTH') == 'true':
            logging.info("Using MOCK Google Auth Exchange")
            return {
                "access_token": "mock_access_token_" + code,
                "expires_in": 3599,
                "scope": "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/userinfo.profile",
                "token_type": "Bearer",
                "id_token": "mock_id_token",
                "refresh_token": "mock_refresh_token"
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": use_redirect_uri
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
                logging.error("Google refresh token error: %s", response.text)
                detail = "Failed to refresh token"
                try:
                    payload = response.json()
                    if payload.get("error") == "invalid_grant":
                        detail = "YouTube access was revoked or expired. Reconnect the account."
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail=detail)
                
            return response.json()

    async def get_channel_info(self, access_token: str) -> dict:
        """Get YouTube channel info"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.YOUTUBE_URL}/channels",
                params={
                    "part": "snippet,contentDetails,statistics",
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

            item = items[0]
            stats = item.get("statistics", {}) or {}
            item["subscribers"] = int(stats.get("subscriberCount", 0) or 0)
            item["total_views"] = int(stats.get("viewCount", 0) or 0)
            item["video_count"] = int(stats.get("videoCount", 0) or 0)
            return item

    async def upload_video(self, access_token: str, file_path: str, title: str, description: str, privacy_status: str = "public", cover_image_path: str = None) -> str:
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
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            # For YouTube 'multipart' upload, the metadata must be the first part with name 'snippet' (or no name but application/json type)
            # and video second. This is tricky with high-level libraries sometimes.
            # Let's use the resumable protocol as it's more robust.
            
            # RESUMABLE UPLOAD
            init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
            
            # YouTube API requires specific JSON structure
            # { "snippet": {...}, "status": {...} }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4" # Assume mp4 for now
            }
            
            # Step 1: Initiate
            init_response = await client.post(init_url, headers=headers, json=metadata)
            
            if init_response.status_code != 200:
                error_body = init_response.text
                logging.error(f"YouTube Upload Init Failed: {error_body}")
                if init_response.status_code == 401:
                    raise ValueError(f"AuthError: {error_body}")
                raise Exception(f"YouTube Upload Init Failed: {error_body}")
                
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
            
            # Reading file content
            # For large files we should stream, but for MVP this is okay up to ~1GB depending on RAM
            content = open(file_path, "rb").read()
            
            upload_response = await client.put(upload_url, headers=put_headers, content=content)
            
            if upload_response.status_code not in [200, 201]:
                logging.error(f"YouTube File Upload Failed: {upload_response.text}")
                raise Exception(f"YouTube File Upload Failed: {upload_response.text}")
                
            video_id = upload_response.json().get("id")
            
            # Step 3: Upload Custom Thumbnail if provided
            if video_id and cover_image_path and os.path.exists(cover_image_path):
                logging.info(f"Uploading custom thumbnail for video {video_id}")
                try:
                    thumbnail_url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}"
                    
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(cover_image_path)
                    if not mime_type:
                        mime_type = "image/jpeg"
                        
                    with open(cover_image_path, "rb") as img_f:
                        img_data = img_f.read()
                        
                    thumb_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": mime_type
                    }
                    
                    thumb_resp = await client.post(thumbnail_url, headers=thumb_headers, content=img_data)
                    if thumb_resp.status_code not in [200, 201]:
                        logging.warning(f"Failed to set custom thumbnail: {thumb_resp.text}")
                    else:
                        logging.info("Custom thumbnail set successfully.")
                except Exception as e:
                    logging.warning(f"Error setting custom thumbnail: {e}")
                    
            return video_id

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

    async def fetch_youtube_feed(self, access_token: str, channel_id: str, limit: int = 25) -> list:
        """Fetch recent videos from YouTube channel"""
        async with httpx.AsyncClient() as client:
            # Get uploads playlist
            ch_resp = await client.get(
                f"{self.YOUTUBE_URL}/channels",
                params={"part": "contentDetails", "id": channel_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if ch_resp.status_code != 200:
                return []
            items = ch_resp.json().get("items", [])
            if not items:
                return []
            uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not uploads_id:
                return []

            # Get playlist items
            pl_resp = await client.get(
                f"{self.YOUTUBE_URL}/playlistItems",
                params={"part": "snippet,contentDetails", "playlistId": uploads_id, "maxResults": limit},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if pl_resp.status_code != 200:
                return []

            video_ids = [item["contentDetails"]["videoId"] for item in pl_resp.json().get("items", [])]
            if not video_ids:
                return []

            # Get video stats
            stats_resp = await client.get(
                f"{self.YOUTUBE_URL}/videos",
                params={"part": "snippet,statistics", "id": ",".join(video_ids)},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if stats_resp.status_code != 200:
                return []

            posts = []
            for v in stats_resp.json().get("items", []):
                snippet = v.get("snippet", {})
                stats = v.get("statistics", {})
                posts.append({
                    "id": v["id"],
                    "content": snippet.get("title", ""),
                    "media_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                    "media_type": "VIDEO",
                    "timestamp": snippet.get("publishedAt"),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments_count": int(stats.get("commentCount", 0)),
                    "views": int(stats.get("viewCount", 0)),
                    "permalink": f"https://youtube.com/watch?v={v['id']}",
                    "platform": "youtube",
                })
            return posts

    async def fetch_youtube_engagement(self, access_token: str, channel_id: str, days: int | None = None) -> dict:
        """Fetch YouTube channel engagement metrics"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.YOUTUBE_URL}/channels",
                params={"part": "statistics,snippet", "id": channel_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                return {}
            items = response.json().get("items", [])
            if not items:
                return {}
            stats = items[0].get("statistics", {})
            range_days = max(int(days or 30), 1)
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=range_days - 1)
            growth_metrics = {}
            analytics_error = None
            try:
                rows = await self.query_analytics_report(
                    access_token,
                    metrics=["views", "likes", "comments", "shares", "subscribersGained", "subscribersLost"],
                    start_date=start_date,
                    end_date=end_date,
                )
                for row in rows:
                    for column in {"views", "likes", "comments", "shares", "subscribersGained", "subscribersLost"}:
                        growth_metrics[column] = growth_metrics.get(column, 0) + self._safe_number(row.get(column))
            except HTTPException as exc:
                analytics_error = str(exc.detail)
            except Exception as exc:
                logging.warning(f"[YouTube] Analytics metrics fetch failed: {exc}")
                analytics_error = "Unable to fetch YouTube Analytics API metrics for this account right now."

            subscribers_gained = growth_metrics.get("subscribersGained")
            subscribers_lost = growth_metrics.get("subscribersLost")
            return {
                "subscribers": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "subscribers_gained": int(subscribers_gained or 0) if subscribers_gained is not None else None,
                "subscribers_lost": int(subscribers_lost or 0) if subscribers_lost is not None else None,
                "followers_growth": (
                    int(subscribers_gained or 0) - int(subscribers_lost or 0)
                    if subscribers_gained is not None or subscribers_lost is not None
                    else None
                ),
                "period_views": growth_metrics.get("views"),
                "period_minutes_watched": growth_metrics.get("estimatedMinutesWatched"),
                "period_likes": growth_metrics.get("likes"),
                "period_comments": growth_metrics.get("comments"),
                "period_shares": growth_metrics.get("shares"),
                "error": analytics_error,
                "platform": "youtube",
            }

    @staticmethod
    def _safe_number(value: Any) -> int | float:
        if value is None or value == "":
            return 0
        try:
            num = float(value)
        except Exception:
            return 0
        return int(num) if num.is_integer() else num

    @staticmethod
    def _analytics_error_detail(response: httpx.Response) -> str:
        body = response.text or ""
        if response.status_code == 403 and (
            "youtubeanalytics.googleapis.com" in body or "SERVICE_DISABLED" in body or "accessNotConfigured" in body
        ):
            return (
                "YouTube Analytics API is disabled for this Google project. "
                "Subscriber growth and period engagement are unavailable until it is enabled."
            )
        if response.status_code == 401:
            return "YouTube access was revoked or expired. Reconnect the account to restore analytics."
        return "Unable to fetch YouTube Analytics API metrics for this account right now."

    async def query_analytics_report(
        self,
        access_token: str,
        metrics: list[str],
        start_date,
        end_date,
        dimensions: list[str] | None = None,
        filters: dict[str, str] | None = None,
        sort: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "ids": "channel==MINE",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "metrics": ",".join(metrics),
        }
        if dimensions:
            params["dimensions"] = ",".join(dimensions)
        if filters:
            params["filters"] = ";".join(f"{key}=={value}" for key, value in filters.items())
        if sort:
            params["sort"] = ",".join(sort)
        if max_results:
            params["maxResults"] = str(max_results)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://youtubeanalytics.googleapis.com/v2/reports",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code != 200:
            logging.warning(
                "[YouTube] Analytics query failed metrics=%s dimensions=%s filters=%s sort=%s max_results=%s status=%s body=%s",
                ",".join(metrics),
                ",".join(dimensions or []),
                filters or {},
                ",".join(sort or []),
                max_results,
                response.status_code,
                (response.text or "")[:400],
            )
            raise HTTPException(status_code=response.status_code, detail=self._analytics_error_detail(response))

        payload = response.json()
        columns = [column.get("name") for column in payload.get("columnHeaders", [])]
        rows = payload.get("rows", []) or []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append(
                {
                    columns[idx]: self._safe_number(value) if isinstance(value, (int, float, str)) else value
                    for idx, value in enumerate(row)
                    if idx < len(columns)
                }
            )
        return normalized

    async def fetch_video_details(self, access_token: str, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not video_ids:
            return {}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.YOUTUBE_URL}/videos",
                params={"part": "snippet,statistics", "id": ",".join(video_ids)},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code != 200:
            logging.warning("[YouTube] Video details fetch failed: %s", response.text)
            return {}

        details: dict[str, dict[str, Any]] = {}
        for item in response.json().get("items", []):
            details[item.get("id")] = item
        return details

    async def fetch_youtube_comments(self, access_token: str, video_id: str, limit: int = 50) -> list:
        """Fetch comments on a YouTube video (read-only)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.YOUTUBE_URL}/commentThreads",
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": min(limit, 100),
                    "order": "time",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                logging.warning(f"[YouTube] Comments fetch failed: {response.text}")
                return []
            comments = []
            for item in response.json().get("items", []):
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                comments.append({
                    "id": item.get("id"),
                    "author_name": snippet.get("authorDisplayName", "Unknown"),
                    "author_avatar": snippet.get("authorProfileImageUrl"),
                    "content": snippet.get("textDisplay", ""),
                    "timestamp": snippet.get("publishedAt"),
                    "likes": snippet.get("likeCount", 0),
                    "can_reply": False,
                    "platform": "youtube",
                })
            return comments
