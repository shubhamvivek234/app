"""
Twitter/X platform adapter.
Text-only: POST /2/tweets.
Media: upload via /1.1/media/upload.json (INIT/APPEND/FINALIZE), then attach media_ids.
Error 187 (duplicate tweet) → permanent error, do not retry.
"""
import logging

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

TWITTER_V2_BASE = "https://api.twitter.com/2"
TWITTER_V1_MEDIA = "https://upload.twitter.com/1.1/media/upload.json"

DUPLICATE_TWEET_CODE = 187   # permanent — do not retry


class TwitterAdapter(PlatformAdapter):
    platform = "twitter"

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Publish a tweet. Uploads any media first, then attaches media_ids.
        Error 187 is raised as a permanent PlatformAPIError.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        media_url = post.get("media_url", "")
        media_ids: list[str] = []

        async with httpx.AsyncClient(timeout=60) as client:
            if media_url:
                media_ids = await self._upload_media(client, auth_headers, media_url)

            tweet_body: dict = {"text": post.get("content", "")}
            if media_ids:
                tweet_body["media"] = {"media_ids": media_ids}

            resp = await client.post(
                f"{TWITTER_V2_BASE}/tweets",
                headers={**auth_headers, "Content-Type": "application/json"},
                json=tweet_body,
            )
            if resp.status_code not in (200, 201):
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        # Twitter v2 wraps errors in resp body with HTTP 200 for some errors
        errors = resp_json.get("errors", [])
        if errors:
            first = errors[0] if isinstance(errors, list) else errors
            code = first.get("code") if isinstance(first, dict) else None
            msg = first.get("message", str(first)) if isinstance(first, dict) else str(first)
            if code == DUPLICATE_TWEET_CODE:
                # Permanent — signal no retry
                raise PlatformAPIError(
                    f"Duplicate tweet (error 187): {msg}", code=DUPLICATE_TWEET_CODE
                )
            raise PlatformAPIError(msg, code=code)

        self._check_response_for_error(resp_json, self.platform)
        data = resp_json.get("data", {})
        tweet_id = data.get("id", "")
        if not tweet_id:
            raise PlatformResponseError("Missing tweet 'id' in Twitter response")

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": f"https://twitter.com/i/web/status/{tweet_id}",
            "platform_post_id": tweet_id,
        }

    async def _upload_media(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        media_url: str,
    ) -> list[str]:
        """
        Upload media via Twitter v1.1 chunked upload (INIT → APPEND → FINALIZE).
        Returns list containing the media_id string.
        TODO: implement chunked APPEND for large files; currently single-segment.
        """
        assert_safe_url(media_url)  # Gap 5.4: SSRF guard
        file_resp = await client.get(media_url)
        if file_resp.status_code != 200:
            raise PlatformHTTPError(file_resp.status_code, "Could not fetch media for Twitter upload")
        media_bytes = file_resp.content
        total_bytes = len(media_bytes)
        media_type = file_resp.headers.get("content-type", "video/mp4")

        # INIT
        init_resp = await client.post(
            TWITTER_V1_MEDIA,
            headers=auth_headers,
            data={
                "command": "INIT",
                "total_bytes": str(total_bytes),
                "media_type": media_type,
            },
        )
        if init_resp.status_code != 202:
            raise PlatformHTTPError(init_resp.status_code, f"Media INIT failed: {init_resp.text}")
        media_id = init_resp.json().get("media_id_string", "")
        if not media_id:
            raise PlatformResponseError("Missing media_id_string from INIT response")

        # APPEND (single segment — TODO: chunk for files > 5 MB)
        append_resp = await client.post(
            TWITTER_V1_MEDIA,
            headers=auth_headers,
            data={"command": "APPEND", "media_id": media_id, "segment_index": "0"},
            files={"media": media_bytes},
        )
        if append_resp.status_code != 204:
            raise PlatformHTTPError(append_resp.status_code, f"Media APPEND failed: {append_resp.text}")

        # FINALIZE
        final_resp = await client.post(
            TWITTER_V1_MEDIA,
            headers=auth_headers,
            data={"command": "FINALIZE", "media_id": media_id},
        )
        if final_resp.status_code not in (200, 201):
            raise PlatformHTTPError(final_resp.status_code, f"Media FINALIZE failed: {final_resp.text}")

        return [media_id]
