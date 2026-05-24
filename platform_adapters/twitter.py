"""
Twitter/X platform adapter.
Text-only: POST /2/tweets.
Media: upload via /1.1/media/upload.json (INIT/APPEND/FINALIZE), then attach media_ids.
For videos, FINALIZE may return processing_info; we must poll STATUS until the media is ready.
Error 187 (duplicate tweet) → permanent error, do not retry.
"""
import asyncio
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
from utils.rate_limit import check_rate_limit, get_retry_after_seconds
from utils.circuit_breaker import can_attempt, record_success, record_failure

logger = logging.getLogger(__name__)

TWITTER_V2_BASE = "https://api.twitter.com/2"
TWITTER_V1_MEDIA = "https://upload.twitter.com/1.1/media/upload.json"
TWITTER_MEDIA_STATUS_POLL_LIMIT = 12
TWITTER_POLL_DURATION_MINUTES = {
    "ONE_DAY": 24 * 60,
    "THREE_DAYS": 3 * 24 * 60,
    "SEVEN_DAYS": 7 * 24 * 60,
}

DUPLICATE_TWEET_CODE = 187   # permanent — do not retry


class TwitterAdapter(PlatformAdapter):
    platform = "twitter"

    @staticmethod
    def _media_category_for_type(media_type: str) -> str | None:
        media_type = (media_type or "").lower()
        if media_type.startswith("video/"):
            return "tweet_video"
        if media_type == "image/gif":
            return "tweet_gif"
        if media_type.startswith("image/"):
            return "tweet_image"
        return None

    async def _wait_for_media_ready(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        media_id: str,
        processing_info: dict | None,
    ) -> None:
        """
        Twitter FINALIZE may return before video processing is complete.
        Poll STATUS until the media becomes usable or fails definitively.
        """
        current = processing_info or {}
        poll_count = 0

        while current:
            state = str(current.get("state") or "").lower()
            if state == "succeeded":
                return
            if state == "failed":
                error = current.get("error") or {}
                message = error.get("message") or "Twitter media processing failed"
                code = error.get("code")
                raise PlatformAPIError(message, code=code)
            if state not in {"pending", "in_progress"}:
                return

            if poll_count >= TWITTER_MEDIA_STATUS_POLL_LIMIT:
                raise PlatformAPIError("Twitter media processing timed out before publish")

            check_after_secs = int(current.get("check_after_secs") or 1)
            await asyncio.sleep(max(check_after_secs, 1))
            poll_count += 1

            status_resp = await client.get(
                TWITTER_V1_MEDIA,
                headers=auth_headers,
                params={"command": "STATUS", "media_id": media_id},
            )
            if status_resp.status_code != 200:
                raise PlatformHTTPError(
                    status_resp.status_code,
                    f"Media STATUS failed: {status_resp.text}",
                )
            status_json = status_resp.json()
            current = status_json.get("processing_info") or {}

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
                raise PlatformAPIError(
                    "Rate limited — requeue",
                    code=429,
                    retry_after=await get_retry_after_seconds(redis, self.platform, str(social_account_id)),
                )
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        media_url = post.get("media_url", "")
        media_ids: list[str] = []
        poll = post.get("effective_poll") or None

        async with httpx.AsyncClient(timeout=60) as client:
            if media_url:
                media_ids = await self._upload_media(client, auth_headers, media_url)

            tweet_text = post.get("effective_content", post.get("content", "")) or ""
            if poll and not tweet_text.strip():
                tweet_text = str(poll.get("question") or "").strip()
            tweet_body: dict = {"text": tweet_text}
            if poll:
                if media_ids:
                    raise PlatformAPIError("Twitter/X poll posts cannot include media")
                poll_options = [str(option).strip() for option in (poll.get("options") or []) if str(option).strip()]
                if len(poll_options) < 2:
                    raise PlatformAPIError("Twitter/X poll requires at least two options")
                duration_minutes = TWITTER_POLL_DURATION_MINUTES.get(str(poll.get("duration") or "ONE_DAY").upper())
                if not duration_minutes:
                    raise PlatformAPIError("Twitter/X poll duration is invalid")
                tweet_body["poll"] = {
                    "options": poll_options,
                    "duration_minutes": duration_minutes,
                }
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
        Streams media in 5MB segments to avoid loading entire file into memory.
        """
        assert_safe_url(media_url)  # Gap 5.4: SSRF guard

        # Get file size via HEAD request
        head_resp = await client.head(media_url, follow_redirects=True)
        content_length = head_resp.headers.get("content-length")
        if not content_length:
            # Fallback: fetch with Range header to get Content-Length
            range_resp = await client.get(
                media_url,
                headers={"Range": "bytes=0-0"},
                follow_redirects=True,
            )
            content_length = range_resp.headers.get("content-range", "").split("/")[-1]
        total_bytes = int(content_length) if content_length else 0

        if total_bytes == 0:
            raise PlatformAPIError("Cannot determine media file size for Twitter upload")

        media_type = head_resp.headers.get("content-type", "video/mp4")
        media_category = self._media_category_for_type(media_type)

        # INIT
        init_data = {
            "command": "INIT",
            "total_bytes": str(total_bytes),
            "media_type": media_type,
        }
        if media_category:
            init_data["media_category"] = media_category
        init_resp = await client.post(
            TWITTER_V1_MEDIA,
            headers=auth_headers,
            data=init_data,
        )
        if init_resp.status_code != 202:
            raise PlatformHTTPError(init_resp.status_code, f"Media INIT failed: {init_resp.text}")
        media_id = init_resp.json().get("media_id_string", "")
        if not media_id:
            raise PlatformResponseError("Missing media_id_string from INIT response")

        # APPEND — stream in 5 MB segments (Twitter's recommended chunk size)
        _TWITTER_CHUNK_SIZE = 5 * 1024 * 1024
        segment_index = 0

        async with client.stream("GET", media_url, follow_redirects=True) as media_stream:
            if media_stream.status_code not in (200, 206):
                raise PlatformHTTPError(media_stream.status_code, "Could not stream media for Twitter upload")

            buffer = b""
            async for raw_chunk in media_stream.aiter_bytes():
                buffer += raw_chunk

                while len(buffer) >= _TWITTER_CHUNK_SIZE:
                    segment = buffer[:_TWITTER_CHUNK_SIZE]
                    buffer = buffer[_TWITTER_CHUNK_SIZE:]

                    append_resp = await client.post(
                        TWITTER_V1_MEDIA,
                        headers=auth_headers,
                        data={"command": "APPEND", "media_id": media_id, "segment_index": str(segment_index)},
                        files={"media": segment},
                    )
                    if append_resp.status_code != 204:
                        raise PlatformHTTPError(append_resp.status_code, f"Media APPEND failed: {append_resp.text}")
                    segment_index += 1

            # Upload remaining buffer (last chunk, smaller than _TWITTER_CHUNK_SIZE)
            if buffer:
                append_resp = await client.post(
                    TWITTER_V1_MEDIA,
                    headers=auth_headers,
                    data={"command": "APPEND", "media_id": media_id, "segment_index": str(segment_index)},
                    files={"media": buffer},
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
        final_json = final_resp.json()
        await self._wait_for_media_ready(
            client,
            auth_headers,
            media_id,
            final_json.get("processing_info"),
        )

        return [media_id]
