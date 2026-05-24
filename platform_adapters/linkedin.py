"""
LinkedIn platform adapter.
Publishes via /v2/ugcPosts with author URN urn:li:person:{user_id}.
Images: register upload via /v2/assets?action=registerUpload first.
Documents: PDF upload flow (stub — TODO).
"""
import logging
import os
from datetime import datetime, timezone, timedelta

import httpx

from utils.ssrf_guard import assert_safe_url

from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
    PlatformResponseError,
)
from utils.encryption import decrypt
from utils.rate_limit import check_rate_limit, get_retry_after_seconds
from utils.circuit_breaker import can_attempt, record_success, record_failure

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


class LinkedInAdapter(PlatformAdapter):
    platform = "linkedin"

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Publish a UGC post to LinkedIn.
        - Text only: ugcPosts with shareMediaCategory NONE.
        - Image: register upload asset first, then attach.
        - Document/PDF: stub — TODO implement PDF upload flow.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        user_id = account.get("platform_user_id", "")
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)
        post_type = str(post.get("post_type", "text") or "text").lower()
        media_urls = [url for url in (post.get("media_urls") or []) if url]
        media_url = post.get("media_url") or (media_urls[0] if media_urls else "")
        poll = post.get("effective_poll") or None

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError(
                    "Rate limited — requeue",
                    code=429,
                    retry_after=await get_retry_after_seconds(redis, self.platform, str(social_account_id)),
                )
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        author_urn = self._resolve_author_urn(account, user_id)
        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        if poll:
            if media_url or media_urls or post.get("effective_linkedin_document_url"):
                raise PlatformAPIError("LinkedIn poll posts cannot include media or document attachments")
            platform_post_id = await self._publish_poll_post(
                auth_headers=auth_headers,
                author_urn=author_urn,
                text=post.get("effective_content", post.get("content", "")) or str(poll.get("question") or "").strip(),
                poll=poll,
            )
            if redis:
                await record_success(redis, self.platform)
            return {
                "post_url": f"https://www.linkedin.com/feed/update/{platform_post_id}/",
                "platform_post_id": platform_post_id,
            }

        async with httpx.AsyncClient(timeout=120) as client:
            asset_urn: str | None = None

            if media_url and post_type in {"image", "carousel", "mixed"}:
                assert_safe_url(media_url)  # Gap 5.4: SSRF guard
                logger.info("LinkedIn registering image upload for post %s from %s", post_id, media_url)
                asset_urn = await self._register_and_upload_image(
                    client, auth_headers, author_urn, media_url
                )
            elif post_type == "document" and media_url:
                # TODO: implement LinkedIn document (PDF) upload flow
                logger.warning("LinkedIn document upload not yet implemented for post %s", post_id)

            ugc_body = self._build_ugc_body(
                author_urn=author_urn,
                text=post.get("effective_content", post.get("content", "")),
                asset_urn=asset_urn,
                post_type=post_type,
            )

            resp = await client.post(f"{LINKEDIN_API_BASE}/ugcPosts", headers=auth_headers, json=ugc_body)
            if resp.status_code not in (200, 201):
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)
        platform_post_id = resp_json.get("id", "")
        if not platform_post_id:
            raise PlatformResponseError("Missing 'id' in LinkedIn ugcPosts response")

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": f"https://www.linkedin.com/feed/update/{platform_post_id}/",
            "platform_post_id": platform_post_id,
        }

    @staticmethod
    def _resolve_author_urn(account: dict, fallback_user_id: str) -> str:
        metadata = account.get("metadata") or {}
        organization_urn = (
            metadata.get("organization_urn")
            or metadata.get("org_urn")
        )
        if organization_urn:
            return organization_urn if str(organization_urn).startswith("urn:li:organization:") else f"urn:li:organization:{organization_urn}"
        return f"urn:li:person:{fallback_user_id}"

    async def _publish_poll_post(
        self,
        *,
        auth_headers: dict,
        author_urn: str,
        text: str,
        poll: dict,
    ) -> str:
        poll_options = [str(option).strip() for option in (poll.get("options") or []) if str(option).strip()]
        if len(poll_options) < 2:
            raise PlatformAPIError("LinkedIn poll requires at least two options")

        duration = str(poll.get("duration") or "ONE_DAY").upper()
        if duration not in {"ONE_DAY", "THREE_DAYS", "SEVEN_DAYS", "FOURTEEN_DAYS"}:
            raise PlatformAPIError("LinkedIn poll duration is invalid")

        payload = {
            "author": author_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
            "content": {
                "poll": {
                    "question": str(poll.get("question") or "").strip(),
                    "options": [{"text": option} for option in poll_options],
                    "settings": {"duration": duration},
                }
            },
        }

        rest_headers = {
            **auth_headers,
            "Linkedin-Version": os.environ.get("LINKEDIN_API_VERSION", "202603"),
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{LINKEDIN_REST_BASE}/posts", headers=rest_headers, json=payload)
            if resp.status_code not in (200, 201):
                raise PlatformHTTPError(resp.status_code, resp.text)
            platform_post_id = resp.headers.get("x-restli-id", "")
            if not platform_post_id:
                body = resp.json() if resp.content else {}
                platform_post_id = body.get("id", "")
            if not platform_post_id:
                raise PlatformResponseError("Missing LinkedIn poll post id")
            return platform_post_id

    async def _register_and_upload_image(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        author_urn: str,
        image_url: str,
    ) -> str:
        """Register an upload slot, upload image bytes, return asset URN."""
        register_body = {
            "registerUploadRequest": {
                "owner": author_urn,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "serviceRelationships": [
                    {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                ],
            }
        }
        reg_resp = await client.post(
            f"{LINKEDIN_API_BASE}/assets",
            params={"action": "registerUpload"},
            headers=auth_headers,
            json=register_body,
        )
        if reg_resp.status_code != 200:
            raise PlatformHTTPError(reg_resp.status_code, f"LinkedIn registerUpload failed: {reg_resp.text}")
        reg_json = reg_resp.json()
        self._check_response_for_error(reg_json, self.platform)

        value = reg_json.get("value", {})
        upload_url = value.get("uploadMechanism", {}).get(
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
        ).get("uploadUrl", "")
        asset_urn = value.get("asset", "")

        if not upload_url or not asset_urn:
            raise PlatformResponseError("LinkedIn registerUpload missing uploadUrl or asset URN")

        # Fetch image bytes
        img_resp = await client.get(image_url)
        if img_resp.status_code != 200:
            raise PlatformHTTPError(img_resp.status_code, "Could not fetch image for LinkedIn upload")

        # Upload binary
        upload_resp = await client.put(
            upload_url,
            content=img_resp.content,
            headers={"Authorization": auth_headers.get("Authorization", "")},
        )
        if upload_resp.status_code not in (200, 201):
            raise PlatformHTTPError(upload_resp.status_code, f"LinkedIn image upload failed: {upload_resp.text}")

        return asset_urn

    def _build_ugc_body(
        self,
        author_urn: str,
        text: str,
        asset_urn: str | None,
        post_type: str,
    ) -> dict:
        """Construct the ugcPosts request body."""
        if asset_urn:
            media_category = "IMAGE"
            media = [{"status": "READY", "media": asset_urn}]
        else:
            media_category = "NONE"
            media = []

        body: dict = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": media_category,
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        if media:
            body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media
        return body

    async def refresh_token(self, refresh_token: str) -> dict:
        """Exchange a LinkedIn refresh token for a new access token."""
        client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
        client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)
        access_token = resp_json.get("access_token", "")
        expires_in = int(resp_json.get("expires_in", 5183944))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return {"access_token": access_token, "expires_at": expires_at}
