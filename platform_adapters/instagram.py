"""
Instagram platform adapter.
Two-step publish: pre_upload (video container creation + poll) → publish (media_publish).
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

GRAPH_BASE = "https://graph.facebook.com/v19.0"
CONTAINER_POLL_INTERVAL = 10   # seconds (Celery retry countdown)
OAUTH_TOKEN_URL = "https://graph.facebook.com/oauth/access_token"


class InstagramAdapter(PlatformAdapter):
    platform = "instagram"

    async def pre_upload(self, post: dict, *, redis=None) -> dict:
        """
        Phase 1: Create a video container on the Graph API.
        Returns {"container_id": str}.
        Polling is driven by Celery: call this once, check status_code once,
        raise self.retry(countdown=CONTAINER_POLL_INTERVAL) if not FINISHED.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        user_id = account.get("platform_user_id", "")
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        container_ids: dict = post.get("platform_container_ids") or {}
        container_id = container_ids.get("instagram")

        async with httpx.AsyncClient(timeout=30) as client:
            if not container_id:
                # Create container
                payload = {
                    "video_url": post.get("media_url", ""),
                    "caption": post.get("content", ""),
                    "media_type": "REELS",
                    "access_token": access_token,
                }
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

            # Check container status (single poll — caller retries via Celery)
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
        if post.get("pre_upload_status") != "ready":
            raise PlatformAPIError("pre_upload not ready — cannot publish")

        # EC4: container expiry check
        expiry_map: dict = post.get("container_expiry_at") or {}
        expiry_raw = expiry_map.get("instagram")
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
        container_id = container_ids.get("instagram", "")
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
        """Exchange a long-lived token using the Graph API OAuth endpoint."""
        client_id = __import__("os").environ.get("INSTAGRAM_CLIENT_ID", "")
        client_secret = __import__("os").environ.get("INSTAGRAM_CLIENT_SECRET", "")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "grant_type": "fb_exchange_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "fb_exchange_token": refresh_token,
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
