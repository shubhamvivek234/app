"""
Facebook platform adapter.
Supports text/image posts (/{page_id}/feed) and video posts (/{page_id}/videos).
Idempotency via X-FB-Idempotency-Key header.
"""
import logging

import httpx

from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
    PlatformResponseError,
)
from utils.encryption import decrypt
from utils.rate_limit import check_rate_limit
from utils.circuit_breaker import can_attempt, record_success, record_failure
from utils.idempotency import make_idempotency_key

logger = logging.getLogger(__name__)

import os

_FB_API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{_FB_API_VERSION}"


class FacebookAdapter(PlatformAdapter):
    platform = "facebook"

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Publish to a Facebook Page.
        - Text/image: POST /{page_id}/feed
        - Video: POST /{page_id}/videos
        Passes X-FB-Idempotency-Key to prevent duplicates on retry.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        page_id = account.get("platform_user_id", "")
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)
        post_type = post.get("post_type", "text")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        attempt = int(post.get("attempt", 0))
        idempotency_key = make_idempotency_key(post_id, self.platform, attempt)
        headers = {"X-FB-Idempotency-Key": idempotency_key}

        is_video = post_type == "video" or bool(post.get("media_url", ""))

        effective_content = post.get("effective_content", post.get("content", ""))

        if is_video:
            endpoint = f"{GRAPH_BASE}/{page_id}/videos"
            payload = {
                "file_url": post.get("media_url", ""),
                "description": effective_content,
                "access_token": access_token,
            }
        else:
            endpoint = f"{GRAPH_BASE}/{page_id}/feed"
            payload = {
                "message": effective_content,
                "access_token": access_token,
            }
            image_url = post.get("media_url", "")
            if image_url:
                payload["link"] = image_url

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, data=payload, headers=headers)
            if resp.status_code != 200:
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)

        platform_post_id = resp_json.get("id", resp_json.get("post_id", ""))
        if not platform_post_id:
            raise PlatformResponseError("Missing 'id' in Facebook publish response")

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": f"https://www.facebook.com/{platform_post_id}",
            "platform_post_id": platform_post_id,
        }
