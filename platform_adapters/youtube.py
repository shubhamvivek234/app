"""
YouTube platform adapter.
Resumable upload flow: initiate → chunk upload (5-10 MB).
Resume URI stored in Redis: upload:resume:{post_id}:youtube (TTL 24h).
publish() sets video privacy to "public" via PATCH.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

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

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CHUNK_SIZE = 8 * 1024 * 1024   # 8 MB chunks (must be multiple of 256 KB)
RESUME_KEY_TTL = 86400          # 24 hours


def _resume_redis_key(post_id: str) -> str:
    return f"upload:resume:{post_id}:youtube"


class YouTubeAdapter(PlatformAdapter):
    platform = "youtube"

    async def pre_upload(self, post: dict, *, redis=None) -> dict:
        """
        Resumable upload to YouTube.
        1. Check Redis for an existing resume URI (retry-safe).
        2. If none, POST metadata to initiate, store resume URI.
        3. Upload file in CHUNK_SIZE chunks from the resume position.
        Returns {"video_id": str}.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)
        media_url = post.get("media_url", "")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        resume_uri: str | None = None
        if redis:
            raw = await redis.get(_resume_redis_key(post_id))
            resume_uri = raw.decode() if isinstance(raw, bytes) else raw

        auth_headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=60) as client:
            if not resume_uri:
                # Initiate resumable upload session
                metadata = {
                    "snippet": {
                        "title": post.get("title") or post.get("content", "")[:100],
                        "description": post.get("content", ""),
                        "categoryId": post.get("category_id", "22"),
                    },
                    "status": {"privacyStatus": "private"},  # publish() will flip to public
                }
                init_resp = await client.post(
                    f"{YOUTUBE_UPLOAD_BASE}/videos",
                    params={"uploadType": "resumable", "part": "snippet,status"},
                    headers={**auth_headers, "X-Upload-Content-Type": "video/*"},
                    json=metadata,
                )
                if init_resp.status_code not in (200, 200):
                    if init_resp.status_code != 200:
                        if redis:
                            await record_failure(redis, self.platform)
                        raise PlatformHTTPError(init_resp.status_code, init_resp.text)
                resume_uri = init_resp.headers.get("Location", "")
                if not resume_uri:
                    raise PlatformResponseError("YouTube did not return a resumable upload URI")
                if redis:
                    await redis.setex(_resume_redis_key(post_id), RESUME_KEY_TTL, resume_uri)

            # EC11 — Chunked resumable upload: stream from media_url, upload in CHUNK_SIZE chunks.

            # Step 1: Determine total file size via HEAD request.
            head_resp = await client.head(media_url, follow_redirects=True)
            if head_resp.status_code != 200:
                raise PlatformHTTPError(head_resp.status_code, "Could not HEAD media file")
            total_size = int(head_resp.headers.get("Content-Length", 0))
            if total_size == 0:
                raise PlatformResponseError("Media file has unknown or zero Content-Length")

            # Step 2: Check if a previous partial upload exists (crash recovery).
            start_offset = 0
            if redis:
                saved_offset = await redis.get(f"{_resume_redis_key(post_id)}:offset")
                if saved_offset:
                    start_offset = int(saved_offset if isinstance(saved_offset, str) else saved_offset.decode())
                    logger.info("Resuming YouTube upload from offset %d / %d", start_offset, total_size)

            # Step 3: Stream media file and upload in CHUNK_SIZE chunks.
            upload_resp = None
            offset = start_offset

            async with client.stream("GET", media_url, headers={"Range": f"bytes={offset}-"}) as media_stream:
                if media_stream.status_code not in (200, 206):
                    raise PlatformHTTPError(media_stream.status_code, "Could not fetch media file")

                buffer = b""
                async for raw_chunk in media_stream.aiter_bytes():
                    buffer += raw_chunk

                    while len(buffer) >= CHUNK_SIZE:
                        chunk_data = buffer[:CHUNK_SIZE]
                        buffer = buffer[CHUNK_SIZE:]

                        chunk_end = offset + len(chunk_data) - 1
                        chunk_headers = {
                            **auth_headers,
                            "Content-Length": str(len(chunk_data)),
                            "Content-Range": f"bytes {offset}-{chunk_end}/{total_size}",
                        }
                        chunk_resp = await client.put(
                            resume_uri,
                            content=chunk_data,
                            headers=chunk_headers,
                        )

                        if chunk_resp.status_code in (200, 201):
                            upload_resp = chunk_resp
                            break
                        elif chunk_resp.status_code == 308:
                            # Resume Incomplete — read Range header for next offset.
                            range_header = chunk_resp.headers.get("Range", "")
                            if range_header:
                                offset = int(range_header.split("-")[1]) + 1
                            else:
                                offset += len(chunk_data)

                            # Persist progress for crash recovery.
                            if redis:
                                await redis.setex(
                                    f"{_resume_redis_key(post_id)}:offset",
                                    RESUME_KEY_TTL,
                                    str(offset),
                                )
                            # Store chunk_upload_progress on post document via redis.
                            progress = min(int((offset / total_size) * 100), 99)
                            if redis:
                                await redis.set(
                                    f"upload:progress:{post_id}:youtube",
                                    str(progress),
                                )
                            logger.debug("YouTube chunk upload progress: %d%% (%d/%d)", progress, offset, total_size)
                        else:
                            raise PlatformHTTPError(chunk_resp.status_code, chunk_resp.text)

                    if upload_resp is not None:
                        break

                # Upload the remaining buffer (final chunk, smaller than CHUNK_SIZE).
                if upload_resp is None and buffer:
                    chunk_end = offset + len(buffer) - 1
                    chunk_headers = {
                        **auth_headers,
                        "Content-Length": str(len(buffer)),
                        "Content-Range": f"bytes {offset}-{chunk_end}/{total_size}",
                    }
                    upload_resp = await client.put(
                        resume_uri,
                        content=buffer,
                        headers=chunk_headers,
                    )

            if upload_resp is None:
                raise PlatformResponseError("Upload completed without a final response from YouTube")

        if upload_resp.status_code not in (200, 201):
            if redis:
                await record_failure(redis, self.platform)
            raise PlatformHTTPError(upload_resp.status_code, upload_resp.text)

        resp_json = upload_resp.json()
        self._check_response_for_error(resp_json, self.platform)
        video_id = resp_json.get("id", "")
        if not video_id:
            raise PlatformResponseError("Missing 'id' in YouTube upload response")

        if redis:
            await record_success(redis, self.platform)
            await redis.delete(_resume_redis_key(post_id))
            await redis.delete(f"{_resume_redis_key(post_id)}:offset")
            await redis.set(f"upload:progress:{post_id}:youtube", "100")

        return {"video_id": video_id}

    async def publish(self, post: dict, *, redis=None) -> dict:
        """
        Set video privacy to 'public' via PATCH.
        Expects post["platform_container_ids"]["youtube"] to hold the video_id.
        """
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        post_id = str(post.get("id", ""))
        social_account_id = account.get("id", post_id)

        container_ids: dict = post.get("platform_container_ids") or {}
        video_id = container_ids.get("youtube", "")
        if not video_id:
            raise PlatformResponseError("No youtube video_id found — run pre_upload first")

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited — requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open — requeue", code=503)

        auth_headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{YOUTUBE_API_BASE}/videos",
                params={"part": "status"},
                headers=auth_headers,
                json={"id": video_id, "status": {"privacyStatus": "public"}},
            )
            if resp.status_code != 200:
                if redis:
                    await record_failure(redis, self.platform)
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": f"https://www.youtube.com/watch?v={video_id}",
            "platform_post_id": video_id,
        }

    async def check_status(self, platform_post_id: str, *, access_token: str = "") -> str:
        """
        Phase 5 — Poll YouTube API for video processing status.
        Returns: "published" | "processing" | "failed"
        """
        if not access_token:
            return "processing"  # no token available — can't poll; wait for webhook

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/videos",
                params={"part": "status", "id": platform_post_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return "processing"  # transient error — don't mark failed

        items = resp.json().get("items", [])
        if not items:
            return "failed"  # video not found

        upload_status = items[0].get("status", {}).get("uploadStatus", "")
        privacy_status = items[0].get("status", {}).get("privacyStatus", "")

        if upload_status == "processed" and privacy_status == "public":
            return "published"
        if upload_status in ("failed", "rejected", "deleted"):
            return "failed"
        return "processing"

    async def refresh_token(self, refresh_token: str) -> dict:
        """Exchange a refresh token with Google OAuth2."""
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
            )
            if resp.status_code != 200:
                raise PlatformHTTPError(resp.status_code, resp.text)
            resp_json = resp.json()

        self._check_response_for_error(resp_json, self.platform)
        access_token = resp_json.get("access_token", "")
        expires_in = int(resp_json.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return {"access_token": access_token, "expires_at": expires_at}
