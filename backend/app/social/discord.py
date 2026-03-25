"""
Discord webhook integration.

Discord doesn't offer a user-post OAuth flow like Instagram/Twitter.
The standard approach (used by Buffer, Hootsuite, etc.) is webhook-based:
  1. User creates a webhook in their Discord server → Settings → Integrations → Webhooks
  2. They copy the webhook URL and paste it into SocialEntangler
  3. We validate it by calling Discord's GET /webhooks/{id}/{token} endpoint
  4. We store the webhook URL (encrypted) as the access_token

Posting: POST to the webhook URL with {"content": "..."} or embeds.
No client credentials required on our side.
"""

import httpx
import re
import logging

logger = logging.getLogger(__name__)

WEBHOOK_RE = re.compile(
    r"^https://discord(?:app)?\.com/api/webhooks/(\d+)/([A-Za-z0-9_\-]+)$"
)


class DiscordWebhook:
    """Validate and post via a Discord incoming webhook."""

    @staticmethod
    def parse_webhook_url(url: str) -> tuple[str, str] | None:
        """Return (webhook_id, webhook_token) or None if invalid format."""
        m = WEBHOOK_RE.match(url.strip())
        if not m:
            return None
        return m.group(1), m.group(2)

    @staticmethod
    async def validate(webhook_url: str) -> dict:
        """
        Call Discord GET /webhooks/{id}/{token} to verify the webhook exists.
        Returns the webhook metadata dict on success.
        Raises ValueError on failure.
        """
        parsed = DiscordWebhook.parse_webhook_url(webhook_url)
        if not parsed:
            raise ValueError(
                "Invalid Discord webhook URL. "
                "It should look like: https://discord.com/api/webhooks/123/abc..."
            )

        wid, wtoken = parsed
        api_url = f"https://discord.com/api/webhooks/{wid}/{wtoken}"

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(api_url)

        if r.status_code == 401 or r.status_code == 404:
            raise ValueError("Discord webhook not found or has been deleted.")
        if r.status_code != 200:
            raise ValueError(f"Discord returned HTTP {r.status_code} when validating webhook.")

        data = r.json()
        return {
            "webhook_id": str(data.get("id", wid)),
            "guild_id": str(data.get("guild_id", "")),
            "channel_id": str(data.get("channel_id", "")),
            "channel_name": data.get("name", ""),  # webhook name, not channel name
        }

    @staticmethod
    async def post_message(webhook_url: str, content: str, username: str | None = None) -> bool:
        """
        Send a message via Discord webhook.
        Returns True on success, raises on failure.
        """
        payload: dict = {"content": content}
        if username:
            payload["username"] = username

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(webhook_url, json=payload)

        if r.status_code in (200, 204):
            return True

        logger.error("Discord webhook post failed: status=%s body=%s", r.status_code, r.text[:200])
        raise RuntimeError(f"Discord webhook returned HTTP {r.status_code}")
