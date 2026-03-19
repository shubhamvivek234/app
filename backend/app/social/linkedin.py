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
        raw_uri = os.environ.get('LINKEDIN_REDIRECT_URI')
        # User requested exact localhost URL. Removing redirectmeto.com proxy
        self.redirect_uri = raw_uri

    def get_auth_url(self, state: str) -> str:
        """Generate LinkedIn OAuth URL"""
        if not self.client_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="LinkedIn credentials not configured")
        
        # w_organization_social triggers LinkedIn's native page selector during OAuth
        # Must be enabled in the LinkedIn Developer App → Auth → OAuth 2.0 scopes
        scopes = "openid profile email w_member_social w_organization_social"
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

    async def fetch_organizations(self, access_token: str) -> list:
        """
        Fetch LinkedIn org pages the token is authorized for.
        Works with w_organization_social scope (no r_organization_admin needed).
        Tries both ADMINISTRATOR role and any-role to maximise results.
        """
        async with httpx.AsyncClient() as client:
            orgs = []
            seen_urns = set()

            for role in ("ADMINISTRATOR", None):
                params = {
                    "q": "roleAssignee",
                    "state": "APPROVED",
                    "count": 20,
                }
                if role:
                    params["role"] = role

                resp = await client.get(
                    "https://api.linkedin.com/v2/organizationAcls",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Restli-Protocol-Version": "2.0.0",
                        "LinkedIn-Version": "202304",
                    },
                )
                logging.info(f"[LinkedIn] organizationAcls (role={role}) → {resp.status_code}")

                if resp.status_code != 200:
                    logging.warning(f"[LinkedIn] organizationAcls failed: {resp.status_code} {resp.text[:200]}")
                    continue

                for el in resp.json().get("elements", []):
                    org_urn = el.get("organizationalTarget", "")
                    if not org_urn or org_urn in seen_urns:
                        continue
                    seen_urns.add(org_urn)

                    org_id = org_urn.split(":")[-1]

                    # Try to fetch org name
                    name = f"Organization {org_id}"
                    org_resp = await client.get(
                        f"https://api.linkedin.com/v2/organizations/{org_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "X-Restli-Protocol-Version": "2.0.0",
                        },
                    )
                    if org_resp.status_code == 200:
                        od = org_resp.json()
                        name = (
                            od.get("localizedName")
                            or (od.get("name") or {}).get("localized", {}).get("en_US")
                            or name
                        )

                    orgs.append({"org_id": org_id, "org_urn": org_urn, "name": name, "logo_url": None})

            return orgs

    async def fetch_posts(self, access_token: str, person_urn: str, limit: int = 20) -> list:
        """
        Fetch LinkedIn member's posts.
        Note: Requires r_member_social scope which is restricted for most apps.
        Returns empty list gracefully if insufficient permissions.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                params={
                    "q": "authors",
                    "authors": f"List(urn:li:person:{person_urn})",
                    "count": limit,
                },
            )

            logging.info(f"[LinkedIn] fetch_posts status: {response.status_code}")

            if response.status_code != 200:
                logging.warning(
                    f"[LinkedIn] fetch_posts unavailable (r_member_social scope may be needed): {response.text}"
                )
                return []

            data = response.json()
            elements = data.get("elements", [])

            normalized = []
            for post in elements:
                content_obj = (
                    post.get("specificContent", {})
                    .get("com.linkedin.ugc.ShareContent", {})
                )
                text = content_obj.get("shareCommentary", {}).get("text", "")

                media_url = None
                media_list = content_obj.get("media", [])
                if media_list:
                    media_url = media_list[0].get("originalUrl")

                post_urn = post.get("id", "")
                published_at = None
                first_pub = post.get("firstPublishedAt")
                if first_pub:
                    from datetime import datetime
                    published_at = datetime.utcfromtimestamp(first_pub / 1000).isoformat() + "Z"

                normalized.append({
                    "platform_post_id": post_urn,
                    "content": text,
                    "media_url": media_url,
                    "media_type": "IMAGE" if media_url else "TEXT",
                    "post_url": f"https://www.linkedin.com/feed/update/{post_urn}/",
                    "metrics": {
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                    },
                    "published_at": published_at,
                })

            return normalized
