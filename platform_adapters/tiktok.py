"""
TikTok platform adapter.
Content Posting API v2: /v2/post/publish/video/init/
Aggressive rate limits (5 posts/day) — enforced via utils.rate_limit.
Feature flag: TIKTOK_ENABLED env var must be "true" to allow publishing.
"""
import logging
import os

import httpx

from utils.ssrf_guard import assert_safe_url

from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
    PlatformResponseError,
)
from utils.encryption import decrypt
from utils.rate_limit import check_rate_limit
from utils.circuit_breaker import can_attempt, record_success, record_failure

logger = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com"
TIKTOK_PUBLISH_INIT = f"{TIKTOK_API_BASE}/v2/post/publish/video/init/"


def _require_tiktok_enabled() -> None:
    """Raise a clear error if tiktok_enabled feature flag is off."""
    from utils.feature_flags import is_enabled
    if not is_enabled("tiktok_enabled"):
        raise PlatformAPIError(
            "TikTok publishing is disabled. Set TIKTOK_ENABLED=true to enable."
        )


class TikTokAdapter(PlatformAdapter):
    platform = "tiktok"

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Publish a video to TikTok via Content Posting API v2.
        Steps:
          1. Feature-flag check (TIKTOK_ENABLED).
          2. Rate limit + circuit breaker check.
          3. POST /v2/post/publish/video/init/ to get publish_id and upload_url.
          4. PUT video bytes to upload_url.
          5. Return publish_id as platform_post_id.
        TikTok enforces a strict 5-posts/day limit; rate_limit.py reflects this.
        """
        _require_tiktok_enabled()

        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)
        media_url = post.get("media_url", "")

        if not media_url:
            raise PlatformAPIError("TikTok publish requires a media_url (video)")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError(
                    "TikTok rate limit reached (5 posts/day) — requeue for tomorrow", code=429
                )
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        assert_safe_url(media_url)  # Gap 5.4: SSRF guard before any network fetch
        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Fetch video to determine size
            file_resp = await client.get(media_url)
            if file_resp.status_code != 200:
                raise PlatformHTTPError(file_resp.status_code, "Could not fetch video for TikTok upload")
            video_bytes = file_resp.content
            total_bytes = len(video_bytes)

            # Step 2: Initiate publish session
            init_body = {
                "post_info": {
                    "title": post.get("content", "")[:150],  # TikTok title max 150 chars
                    "privacy_level": post.get("tiktok_privacy", "PUBLIC_TO_EVERYONE"),
                    "disable_duet": post.get("disable_duet", False),
                    "disable_comment": post.get("disable_comment", False),
                    "disable_stitch": post.get("disable_stitch", False),
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": total_bytes,
                    "chunk_size": total_bytes,
                    "total_chunk_count": 1,
                },
            }

            init_resp = await client.post(TIKTOK_PUBLISH_INIT, headers=auth_headers, json=init_body)
            if init_resp.status_code != 200:
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(init_resp.status_code, init_resp.text)
            init_json = init_resp.json()

        # TikTok wraps errors in data.error_code / error
        error_code = init_json.get("error", {}).get("code", "ok")
        if error_code and error_code != "ok":
            if redis:
                await record_failure(redis, self.platform)
            msg = init_json.get("error", {}).get("message", str(error_code))
            raise PlatformAPIError(msg, code=error_code)

        self._check_response_for_error(init_json, self.platform)
        data = init_json.get("data", {})
        publish_id = data.get("publish_id", "")
        upload_url = data.get("upload_url", "")

        if not publish_id or not upload_url:
            raise PlatformResponseError("TikTok init response missing publish_id or upload_url")

        # Step 3: Upload video chunk(s)
        async with httpx.AsyncClient(timeout=120) as client:
            upload_resp = await client.put(
                upload_url,
                content=video_bytes,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(total_bytes),
                    "Content-Range": f"bytes 0-{total_bytes - 1}/{total_bytes}",
                },
            )

        if upload_resp.status_code not in (200, 201, 206):
            if redis:
                await record_failure(redis, self.platform)
            raise PlatformHTTPError(upload_resp.status_code, f"TikTok video upload failed: {upload_resp.text}")

        if redis:
            await record_success(redis, self.platform)

        # TikTok does not return a public URL immediately — post goes through review
        return {
            "post_url": "",   # Available after TikTok review completes
            "platform_post_id": publish_id,
        }
