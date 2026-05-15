import httpx
import os
import logging
from fastapi import HTTPException
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone

class LinkedInAuth:
    """LinkedIn OAuth 2.0 and API"""

    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    USER_URL = "https://api.linkedin.com/v2/userinfo" # New OIDC userinfo
    POST_URL = "https://api.linkedin.com/v2/ugcPosts" # Or the new /rest/posts
    REST_URL = "https://api.linkedin.com/rest"

    def __init__(self):
        self.client_id = os.environ.get('LINKEDIN_CLIENT_ID')
        self.client_secret = os.environ.get('LINKEDIN_CLIENT_SECRET')
        raw_uri = os.environ.get('LINKEDIN_REDIRECT_URI')
        # User requested exact localhost URL. Removing redirectmeto.com proxy
        self.redirect_uri = raw_uri
        self.api_version = os.environ.get('LINKEDIN_API_VERSION', '202603')

    def _rest_headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Linkedin-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _organization_urn(value: str | None) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.startswith("urn:li:organization:"):
            return raw
        return f"urn:li:organization:{raw}"

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

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh an expired LinkedIn access token."""
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
            response = await client.post(self.TOKEN_URL, data=data)
            if response.status_code != 200:
                logging.error("LinkedIn refresh token error: %s", response.text)
                raise HTTPException(status_code=400, detail="LinkedIn access expired. Reconnect the account.")
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

    async def get_member_follower_total(self, access_token: str) -> int | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/memberFollowersCount",
                params={"q": "me"},
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn member follower total unavailable: %s", response.text)
                return None
            elements = response.json().get("elements", [])
            if not elements:
                return None
            try:
                return int(elements[0].get("memberFollowersCount", 0))
            except Exception:
                return None

    async def get_member_follower_growth(self, access_token: str, days: int | None = None) -> int | None:
        range_days = max(int(days or 30), 1)
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=range_days)
        range_param = (
            f"(start:(year:{start.year},month:{start.month},day:{start.day}),"
            f"end:(year:{today.year},month:{today.month},day:{today.day}))"
        )
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/memberFollowersCount",
                params={"q": "dateRange", "dateRange": range_param},
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn member follower growth unavailable: %s", response.text)
                return None
            try:
                return sum(int(item.get("memberFollowersCount", 0) or 0) for item in response.json().get("elements", []))
            except Exception:
                return None

    async def get_admin_organizations(self, access_token: str) -> list[str]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/organizationAcls",
                params={
                    "q": "roleAssignee",
                    "role": "ADMINISTRATOR",
                    "state": "APPROVED",
                    "count": 100,
                    "start": 0,
                },
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn organization ACL lookup unavailable: %s", response.text)
                return []

            orgs: list[str] = []
            for item in response.json().get("elements", []):
                org_urn = self._organization_urn(item.get("organizationTarget") or item.get("organization"))
                if org_urn and org_urn not in orgs:
                    orgs.append(org_urn)
            return orgs

    async def get_organization_follower_total(self, access_token: str, organization_urn: str) -> int | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/networkSizes/{organization_urn}",
                params={"edgeType": "COMPANY_FOLLOWED_BY_MEMBER"},
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn organization follower total unavailable for %s: %s", organization_urn, response.text)
                return None
            try:
                return int(response.json().get("firstDegreeSize", 0))
            except Exception:
                return None

    async def get_organization_follower_growth(self, access_token: str, organization_urn: str, days: int | None = None) -> int | None:
        range_days = max(int(days or 30), 1)
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=range_days)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/organizationalEntityFollowerStatistics",
                params={
                    "q": "organizationalEntity",
                    "organizationalEntity": organization_urn,
                    "timeIntervals.timeGranularityType": "DAY",
                    "timeIntervals.timeRange.start": int(start_dt.timestamp() * 1000),
                    "timeIntervals.timeRange.end": int(end_dt.timestamp() * 1000),
                },
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn organization follower growth unavailable for %s: %s", organization_urn, response.text)
                return None

            total_growth = 0
            saw_value = False
            for item in response.json().get("elements", []):
                counts = item.get("followerCounts") or item.get("totalFollowerCounts") or {}
                if counts:
                    total_growth += int(counts.get("organicFollowerCount", 0) or 0)
                    total_growth += int(counts.get("paidFollowerCount", 0) or 0)
                    saw_value = True
            return total_growth if saw_value else None

    async def get_organization_share_stats(self, access_token: str, organization_urn: str, days: int | None = None) -> dict:
        range_days = max(int(days or 30), 1)
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=range_days)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.REST_URL}/organizationalEntityShareStatistics",
                params={
                    "q": "organizationalEntity",
                    "organizationalEntity": organization_urn,
                    "timeIntervals.timeGranularityType": "DAY",
                    "timeIntervals.timeRange.start": int(start_dt.timestamp() * 1000),
                    "timeIntervals.timeRange.end": int(end_dt.timestamp() * 1000),
                },
                headers=self._rest_headers(access_token),
            )
            if response.status_code != 200:
                logging.warning("LinkedIn organization share stats unavailable for %s: %s", organization_urn, response.text)
                return {}

            metrics = {
                "impressions": 0,
                "reach": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
            }
            saw_value = False
            for item in response.json().get("elements", []):
                stats = item.get("totalShareStatistics") or {}
                if not stats:
                    continue
                metrics["impressions"] += int(stats.get("impressionCount", 0) or 0)
                metrics["reach"] += int(stats.get("uniqueImpressionsCount", 0) or 0)
                metrics["likes"] += int(stats.get("likeCount", 0) or 0)
                metrics["comments"] += int(stats.get("commentCount", 0) or 0)
                metrics["shares"] += int(stats.get("shareCount", 0) or 0)
                saw_value = True
            return metrics if saw_value else {}

    async def fetch_audience_analytics(self, access_token: str, account: dict, days: int | None = None) -> dict:
        """Fetch LinkedIn audience metrics for member and organization analytics."""
        result: dict[str, int | str | None] = {
            "platform": "linkedin",
            "followers": None,
            "followers_growth": None,
            "impressions": None,
            "reach": None,
            "error": None,
        }

        member_total = await self.get_member_follower_total(access_token)
        member_growth = await self.get_member_follower_growth(access_token, days=days)
        if member_total is not None:
            result["followers"] = member_total
        if member_growth is not None:
            result["followers_growth"] = member_growth

        explicit_orgs = [self._organization_urn(org_id) for org_id in (account.get("selected_org_ids") or [])]
        organization_urns = [org for org in explicit_orgs if org] or await self.get_admin_organizations(access_token)

        if organization_urns:
            org_followers_total = 0
            org_followers_growth = 0
            org_impressions = 0
            org_reach = 0
            saw_org_total = False
            saw_org_growth = False
            saw_org_share_stats = False

            for organization_urn in organization_urns:
                total = await self.get_organization_follower_total(access_token, organization_urn)
                growth = await self.get_organization_follower_growth(access_token, organization_urn, days=days)
                share_stats = await self.get_organization_share_stats(access_token, organization_urn, days=days)

                if total is not None:
                    org_followers_total += total
                    saw_org_total = True
                if growth is not None:
                    org_followers_growth += growth
                    saw_org_growth = True
                if share_stats:
                    org_impressions += int(share_stats.get("impressions", 0) or 0)
                    org_reach += int(share_stats.get("reach", 0) or 0)
                    saw_org_share_stats = True

            if saw_org_total:
                result["followers"] = org_followers_total
            if saw_org_growth:
                result["followers_growth"] = org_followers_growth
            if saw_org_share_stats:
                result["impressions"] = org_impressions
                result["reach"] = org_reach

        if all(result.get(metric) is None for metric in ("followers", "followers_growth", "impressions", "reach")):
            result["error"] = "LinkedIn analytics are not enabled for this application or this LinkedIn connection does not have the required analytics access."

        return result

    async def publish_post(self, access_token: str, person_urn: str, text: str, media_urls: list = None, local_file_path: str = None) -> str:
        """Publish a post to LinkedIn member profile"""
        async with httpx.AsyncClient() as client:
            asset_urn = None
            
            # Step 1 & 2: Register upload and PUT binary if we have a local file
            if local_file_path and os.path.exists(local_file_path):
                # Standardize on feedshare-image for MVP
                recipe = "urn:li:digitalmediaRecipe:feedshare-image"
                if local_file_path.lower().endswith(('.mp4', '.mov')):
                    recipe = "urn:li:digitalmediaRecipe:feedshare-video"

                register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
                register_payload = {
                    "registerUploadRequest": {
                        "recipes": [recipe],
                        "owner": f"urn:li:person:{person_urn}",
                        "serviceRelationships": [
                            {
                                "relationshipType": "OWNER",
                                "identifier": "urn:li:userGeneratedContent"
                            }
                        ]
                    }
                }
                
                try:
                    reg_res = await client.post(
                        register_url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"},
                        json=register_payload
                    )
                    
                    if reg_res.status_code in [200, 201]:
                        reg_data = reg_res.json()
                        upload_mechanism = reg_data.get("value", {}).get("uploadMechanism", {})
                        upload_req = upload_mechanism.get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                        upload_url = upload_req.get("uploadUrl")
                        asset_urn = reg_data.get("value", {}).get("asset")
                        
                        if upload_url and asset_urn:
                            # Upload the binary file
                            with open(local_file_path, "rb") as f:
                                file_data = f.read()
                                
                            upload_headers = {
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/octet-stream",
                                "X-Restli-Protocol-Version": "2.0.0"
                            }
                            
                            upload_res = await client.put(upload_url, headers=upload_headers, content=file_data)
                            
                            if upload_res.status_code not in [200, 201]:
                                logging.error(f"LinkedIn Media Upload Error: {upload_res.status_code} - {upload_res.text}")
                                asset_urn = None
                    else:
                        logging.error(f"LinkedIn Register Upload Error: {reg_res.status_code} - {reg_res.text}")
                except Exception as e:
                    logging.error(f"LinkedIn Native Media Error exception: {str(e)}")
                    asset_urn = None

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
            
            if asset_urn:
                payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "VIDEO" if "video" in recipe else "IMAGE"
                payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                    {
                        "status": "READY",
                        "description": {"text": ""},
                        "media": asset_urn,
                        "title": {"text": "Media attachment"}
                    }
                ]
            elif media_urls:
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

    async def fetch_engagement(self, access_token: str, person_urn: str) -> dict:
        """Fetch LinkedIn profile engagement (limited)"""
        # LinkedIn API is restrictive for analytics
        return {
            "platform": "linkedin",
            "note": "LinkedIn analytics require Marketing Developer Platform approval",
        }
