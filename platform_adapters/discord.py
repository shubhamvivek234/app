"""
Discord platform adapter.
Publishes text, media, and rich embeds directly via Discord incoming webhook.
"""
import logging
import httpx
from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
)
from utils.encryption import decrypt

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    platform = "discord"

    async def publish(self, post: dict) -> dict:
        access_token = post.get("access_token")
        if not access_token:
            raise PlatformAPIError("Discord account missing webhook access_token")

        try:
            webhook_url = decrypt(access_token) if len(access_token) > 40 and not access_token.startswith("http") else access_token
        except Exception:
            webhook_url = access_token

        content = post.get("content", "")
        title = post.get("title")
        media_urls = post.get("media_urls") or ([post.get("media_url")] if post.get("media_url") else [])

        embeds = []
        if title or media_urls:
            embed = {}
            if title:
                embed["title"] = title[:256]
            if content and len(content) > 1900:
                embed["description"] = content[:4096]
                content = ""  # Put in embed instead to avoid 2000 char limit
            if media_urls and len(media_urls) > 0:
                embed["image"] = {"url": media_urls[0]}
            embed["footer"] = {"text": "Published via Unravler"}
            embeds.append(embed)

        payload = {}
        if content:
            payload["content"] = content[:2000]
        if embeds:
            payload["embeds"] = embeds

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{webhook_url}?wait=true", json=payload)

        if resp.status_code in (200, 204):
            data = resp.json() if resp.text else {}
            msg_id = str(data.get("id", "discord_webhook_msg"))
            channel_id = str(data.get("channel_id", ""))
            post_url = f"https://discord.com/channels/@me/{channel_id}/{msg_id}" if channel_id else webhook_url
            return {
                "platform_post_id": msg_id,
                "post_url": post_url,
            }

        logger.error("Discord publish error %s: %s", resp.status_code, resp.text[:300])
        raise PlatformHTTPError(status_code=resp.status_code, message=f"Discord webhook error: {resp.text[:200]}")
