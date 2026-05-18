"""Threads platform adapter."""
import json
import logging

import httpx

from platform_adapters.base import (
    PlatformAdapter,
    PlatformAPIError,
    PlatformHTTPError,
)
from utils.circuit_breaker import can_attempt, record_success
from utils.encryption import decrypt
from utils.rate_limit import check_rate_limit
from utils.ssrf_guard import assert_safe_url

logger = logging.getLogger(__name__)

THREADS_GRAPH_BASE = "https://graph.threads.net/v1.0"


class ThreadsAdapter(PlatformAdapter):
    platform = "threads"

    async def publish(self, post: dict, *, redis=None) -> dict:
        account = post.get("account", {})
        access_token = decrypt(account.get("access_token", ""))
        user_id = str(account.get("platform_user_id") or "me")
        social_account_id = account.get("id", post.get("id", ""))
        poll = post.get("effective_poll") or None
        media_urls = [url for url in (post.get("media_urls") or []) if url]
        media_url = post.get("media_url") or (media_urls[0] if media_urls else "")
        text = post.get("effective_content", post.get("content", "")) or ""

        if redis:
            if not await check_rate_limit(redis, self.platform, str(social_account_id)):
                raise PlatformAPIError("Rate limited - requeue", code=429)
            if not await can_attempt(redis, self.platform):
                raise PlatformAPIError("Circuit open - requeue", code=503)

        if poll and not text.strip():
            text = str(poll.get("question") or "").strip()

        async with httpx.AsyncClient(timeout=120) as client:
            creation_id = await self._create_container(
                client=client,
                access_token=access_token,
                user_id=user_id,
                text=text,
                post_type=str(post.get("post_type") or "").lower(),
                media_url=media_url,
                media_urls=media_urls,
                poll=poll,
            )
            published_id = await self._publish_container(
                client=client,
                access_token=access_token,
                user_id=user_id,
                creation_id=creation_id,
            )
            permalink = await self._fetch_permalink(
                client=client,
                access_token=access_token,
                post_id=published_id,
            )

        if redis:
            await record_success(redis, self.platform)

        return {
            "post_url": permalink or f"https://www.threads.net/t/{published_id}",
            "platform_post_id": published_id,
        }

    async def _create_container(
        self,
        *,
        client: httpx.AsyncClient,
        access_token: str,
        user_id: str,
        text: str,
        post_type: str,
        media_url: str,
        media_urls: list[str],
        poll: dict | None,
    ) -> str:
        params = {
            "media_type": "TEXT",
            "text": text,
            "access_token": access_token,
        }

        if poll:
            if media_urls:
                raise PlatformAPIError("Threads poll posts cannot include media")
            poll_options = [str(option).strip() for option in (poll.get("options") or []) if str(option).strip()]
            if len(poll_options) < 2:
                raise PlatformAPIError("Threads poll requires at least two options")
            params["poll_attachment"] = json.dumps({
                "option_a": poll_options[0],
                "option_b": poll_options[1],
                **({"option_c": poll_options[2]} if len(poll_options) > 2 else {}),
                **({"option_d": poll_options[3]} if len(poll_options) > 3 else {}),
            })
        elif media_url:
            assert_safe_url(media_url)
            is_video = post_type in {"video", "reel", "story"} or any(
                str(url).lower().split("?")[0].endswith(ext) for url in media_urls for ext in (".mp4", ".mov", ".webm")
            )
            if is_video:
                params["media_type"] = "VIDEO"
                params["video_url"] = media_url
            else:
                params["media_type"] = "IMAGE"
                params["image_url"] = media_url

        resp = await client.post(f"{THREADS_GRAPH_BASE}/{user_id}/threads", params=params)
        if resp.status_code != 200:
            raise PlatformHTTPError(resp.status_code, resp.text)
        response_json = resp.json()
        self._check_response_for_error(response_json, self.platform)
        creation_id = response_json.get("id")
        if not creation_id:
            raise PlatformAPIError("Threads container id missing")
        return creation_id

    async def _publish_container(
        self,
        *,
        client: httpx.AsyncClient,
        access_token: str,
        user_id: str,
        creation_id: str,
    ) -> str:
        resp = await client.post(
            f"{THREADS_GRAPH_BASE}/{user_id}/threads_publish",
            params={"creation_id": creation_id, "access_token": access_token},
        )
        if resp.status_code != 200:
            raise PlatformHTTPError(resp.status_code, resp.text)
        response_json = resp.json()
        self._check_response_for_error(response_json, self.platform)
        post_id = response_json.get("id")
        if not post_id:
            raise PlatformAPIError("Threads publish id missing")
        return post_id

    async def _fetch_permalink(
        self,
        *,
        client: httpx.AsyncClient,
        access_token: str,
        post_id: str,
    ) -> str | None:
        resp = await client.get(
            f"{THREADS_GRAPH_BASE}/{post_id}",
            params={"fields": "permalink", "access_token": access_token},
        )
        if resp.status_code != 200:
            logger.warning("Threads permalink fetch failed for %s: %s", post_id, resp.text)
            return None
        return resp.json().get("permalink")
