"""
Telegram platform adapter.
Publishes text and media directly to Telegram channels/groups via Telegram Bot API.
"""
import json
import logging
import httpx
from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
)
from utils.encryption import decrypt
from backend.app.social.telegram import TelegramBot

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    platform = "telegram"

    async def publish(self, post: dict) -> dict:
        access_token = post.get("access_token")
        if not access_token:
            raise PlatformAPIError("Telegram account missing access_token credentials")

        try:
            raw_creds = decrypt(access_token) if not access_token.startswith("{") else access_token
            creds = json.loads(raw_creds)
            bot_token = creds["bot_token"]
            chat_id = creds["chat_id"]
        except Exception as exc:
            raise PlatformAPIError(f"Failed to parse Telegram credentials: {str(exc)}")

        content = post.get("content", "")
        media_urls = post.get("media_urls") or ([post.get("media_url")] if post.get("media_url") else [])

        try:
            res = await TelegramBot.post_message(
                bot_token=bot_token,
                chat_id=chat_id,
                content=content,
                media_urls=media_urls,
            )
            return {
                "platform_post_id": res.get("message_id", "telegram_msg"),
                "post_url": res.get("post_url"),
            }
        except Exception as exc:
            logger.error("Telegram publish error: %s", exc)
            raise PlatformAPIError(f"Telegram publish error: {str(exc)}")
