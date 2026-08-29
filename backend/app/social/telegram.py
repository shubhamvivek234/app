"""
Telegram Bot channel & group integration.

Allows users to connect a Telegram channel or group using:
  1. A Bot Token created via @BotFather
  2. A Chat ID (e.g., @mychannel or -100123456789)
"""

import httpx
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class TelegramBot:
    """Validate and post via Telegram Bot API."""

    @staticmethod
    async def validate(bot_token: str, chat_id: str) -> dict:
        """
        Validate bot token via getMe and test if the bot has access to chat_id via getChat.
        """
        bot_token = bot_token.strip()
        chat_id = chat_id.strip()

        if not bot_token:
            raise ValueError("Bot Token is required.")
        if not chat_id:
            raise ValueError("Chat ID (e.g. @channel or -100...) is required.")

        async with httpx.AsyncClient(timeout=10) as client:
            # 1. Verify Bot Token
            me_resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            if me_resp.status_code != 200:
                raise ValueError("Invalid Telegram Bot Token. Please check the token from @BotFather.")

            bot_info = me_resp.json().get("result", {})
            bot_username = bot_info.get("username", "Telegram Bot")

            # 2. Verify Chat Access
            chat_resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getChat",
                params={"chat_id": chat_id},
            )
            chat_title = chat_id
            if chat_resp.status_code == 200:
                chat_data = chat_resp.json().get("result", {})
                chat_title = chat_data.get("title") or chat_data.get("username") or chat_id

            return {
                "bot_id": str(bot_info.get("id", "")),
                "bot_username": bot_username,
                "chat_id": chat_id,
                "chat_title": chat_title,
            }

    @staticmethod
    async def post_message(
        bot_token: str,
        chat_id: str,
        content: str,
        media_urls: Optional[List[str]] = None,
    ) -> dict:
        """
        Send message or media to Telegram chat.
        """
        bot_token = bot_token.strip()
        chat_id = chat_id.strip()

        async with httpx.AsyncClient(timeout=20) as client:
            if media_urls and len(media_urls) > 0:
                media_url = media_urls[0]
                is_video = any(media_url.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm", ".avi"])
                endpoint = "sendVideo" if is_video else "sendPhoto"
                payload = {
                    "chat_id": chat_id,
                    ("video" if is_video else "photo"): media_url,
                    "caption": content[:1024],
                }
                r = await client.post(f"https://api.telegram.org/bot{bot_token}/{endpoint}", json=payload)
            else:
                payload = {
                    "chat_id": chat_id,
                    "text": content,
                    "disable_web_page_preview": False,
                }
                r = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)

            if r.status_code == 200 and r.json().get("ok"):
                result = r.json().get("result", {})
                message_id = str(result.get("message_id", ""))
                return {
                    "success": True,
                    "message_id": message_id,
                    "post_url": f"https://t.me/{chat_id.lstrip('@')}/{message_id}" if chat_id.startswith("@") else None,
                }

            err_desc = r.json().get("description", f"HTTP {r.status_code}")
            logger.error("Telegram post failed: %s", err_desc)
            raise RuntimeError(f"Telegram API Error: {err_desc}")
