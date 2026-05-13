"""
Instagram platform adapter.
Two-step publish for media posts:
- image posts: create image container, immediately publishable
- video/reel/story posts: create reel container, poll until FINISHED, then publish
EC4: container expiry check before publish.
EC29: error code 9007 treated as success (already published).
EC24: revocation subcodes 458/460 → permanent error, do not refresh token.
"""
import logging
from datetime import datetime, timezone

import httpx

from platform_adapters.base import (
    PlatformAdapter,
    AlreadyPublishedError,
    PlatformHTTPError,
    PlatformAPIError,
    PlatformResponseError,
)
from utils.encryption import decrypt
from utils.rate_limit import check_rate_limit
from utils.circuit_breaker import can_attempt, record_success, record_failure

logger = logging.getLogger(__name__)

import os

_FB_API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.instagram.com/{_FB_API_VERSION}"
CONTAINER_POLL_INTERVAL = 10   # seconds (Celery retry countdown)
OAUTH_TOKEN_URL = f"{GRAPH_BASE}/refresh_access_token"


class InstagramAdapter(PlatformAdapter):
    platform = "instagram"

    @staticmethod
    def _is_video_like(post: dict) -> bool:
        post_type = str(post.get("post_type") or "").lower()
        return post_type in {"video", "reel", "story"} or "video" in post_type

    @staticmethod
    def _is_multi_image(post: dict) -> bool:
        media_urls = [url for url in (post.get("media_urls") or []) if url]
        return str(post.get("post_type") or "").lower() == "carousel" and len(media_urls) > 1

    async def pre_upload(self, post: dict, *, redis=None) -> dict:
        """
        Phase 1: Create an Instagram media container.
        - image posts return ready immediately
        - video/reel/story posts return pending until processing finishes
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        user_id = account.get("platform_user_id", "")
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)
        media_url = post.get("media_url", "")
        caption = post.get("effective_content", post.get("content", ""))

        if self._is_multi_image(post):
            raise PlatformAPIError("Instagram carousel publishing is not supported in the current adapter")

        if not media_url:
            raise PlatformAPIError("Instagram publish requires a media_url")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        target_key = post.get("publish_target_key") or "instagram"
        container_ids: dict = post.get("platform_container_ids") or {}
        container_id = container_ids.get(target_key)

        async with httpx.AsyncClient(timeout=30) as client:
            if not container_id:
                payload = {
                    "caption": caption,
                    "access_token": access_token,
                }
                if self._is_video_like(post):
                    payload["media_type"] = "REELS"
                    payload["video_url"] = media_url
                else:
                    payload["image_url"] = media_url
                resp = await client.post(f"{GRAPH_BASE}/{user_id}/media", data=payload)
                if resp.status_code != 200:
                    if redis:
                        await record_failure(redis, self.platform)
                    raise PlatformHTTPError(resp.status_code, resp.text)
                resp_json = resp.json()
                self._check_response_for_error(resp_json, self.platform)
                container_id = resp_json.get("id", "")
                if not container_id:
                    raise PlatformResponseError("Missing container id in response")

            # Image containers are immediately publishable after creation.
            if not self._is_video_like(post):
                if redis:
                    await record_success(redis, self.platform)
                return {"container_id": container_id, "pre_upload_status": "ready"}

            # Check container status once for video-like media.
            params = {
                "fields": "status_code",
                "access_token": access_token,
            }
            poll_resp = await client.get(f"{GRAPH_BASE}/{container_id}", params=params)
            if poll_resp.status_code != 200:
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(poll_resp.status_code, poll_resp.text)
            poll_json = poll_resp.json()
            self._check_response_for_error(poll_json, self.platform)

        status_code = poll_json.get("status_code", "")
        if status_code == "FINISHED":
            if redis:
                await record_success(redis, self.platform)
            return {"container_id": container_id, "pre_upload_status": "ready"}

        if status_code == "ERROR":
            if redis:
                await record_failure(redis, self.platform)
            raise PlatformAPIError(f"Container processing failed: {poll_json.get('status', '')}")

        # EC12: Still IN_PROGRESS — dispatch non-blocking container status check
        # Instead of polling here, return pending with container_id.
        # The Celery task layer should dispatch check_instagram_container_status
        # which checks once, releases the worker, and retries via Celery countdown.
        return {"container_id": container_id, "pre_upload_status": "pending"}

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Phase 2: Publish a finished container via media_publish.
        EC4: Reject if container expired (older than 24h).
        EC29: error 9007 treated as success.
        """
        target_key = post.get("publish_target_key") or "instagram"
        instagram_state = ((post.get("pre_upload_results") or {}).get(target_key) or {})
        pre_upload_status = instagram_state.get("status") or post.get("pre_upload_status")
        if pre_upload_status != "ready":
            raise PlatformAPIError("pre_upload not ready — cannot publish")

        # EC4: container expiry check
        expiry_map: dict = post.get("container_expiry_at") or {}
        expiry_raw = expiry_map.get(target_key)
        if expiry_raw:
            try:
                expiry_dt = datetime.fromisoformat(str(expiry_raw))
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expiry_dt:
                    raise PlatformAPIError("Instagram container expired (EC4) — re-run pre_upload")
            except (ValueError, TypeError):
                logger.warning("Could not parse container_expiry_at for instagram")

        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        user_id = account.get("platform_user_id", "")
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)

        container_ids: dict = post.get("platform_container_ids") or {}
        container_id = container_ids.get(target_key, "")
        if not container_id:
            raise PlatformResponseError("No instagram container_id on post")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        # Idempotency key passed as header (Graph API does not natively support it,
        # but we track it ourselves via utils.idempotency in the Celery task layer)
        payload = {
            "creation_id": container_id,
            "access_token": access_token,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{GRAPH_BASE}/{user_id}/media_publish", data=payload)
            if resp.status_code != 200:
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        try:
            self._check_response_for_error(resp_json, self.platform)
        except AlreadyPublishedError:
            # EC29: already published → treat as success
            logger.info("Instagram EC29: post %s already published — treating as success", post_id)
            platform_post_id = resp_json.get("id", container_id)
            if redis:
                await record_success(redis, self.platform)
            return {
                "post_url": f"https://www.instagram.com/p/{platform_post_id}/",
                "platform_post_id": platform_post_id,
            }

        platform_post_id = resp_json.get("id", "")
        if not platform_post_id:
            raise PlatformResponseError("Missing 'id' in media_publish response")

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": f"https://www.instagram.com/p/{platform_post_id}/",
            "platform_post_id": platform_post_id,
        }

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh a long-lived Instagram token for Instagram Login integrations."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                OAUTH_TOKEN_URL,
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": refresh_token,
                },
            )
            if resp.status_code != 200:
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)
        access_token = resp_json.get("access_token", "")
        expires_in = int(resp_json.get("expires_in", 5183944))  # ~60 days default
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return {"access_token": access_token, "expires_at": expires_at}
