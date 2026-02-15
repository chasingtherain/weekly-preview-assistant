"""Telegram Agent - Core logic.

Sends formatted text messages to a Telegram chat via the Bot API.
Uses the requests library directly (no python-telegram-bot dependency).
"""

import logging
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramAgent:
    """Sends messages to a Telegram chat via Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        """Initialize the TelegramAgent.

        Args:
            bot_token: Telegram bot token from @BotFather.
            chat_id: Target chat/group ID.
        """
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> dict[str, Any]:
        """Send a text message to the configured Telegram chat.

        Args:
            text: The message text to send.

        Returns:
            Result dict with "message_id", "chat_id", and "sent_at" on success,
            or "error" key on failure.
        """
        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage"

        try:
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                error_desc = data.get("description", "Unknown Telegram API error")
                logger.error("Telegram API error: %s", error_desc)
                return {"error": error_desc}

            result_msg = data.get("result", {})
            return {
                "message_id": result_msg.get("message_id"),
                "chat_id": str(self.chat_id),
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }

        except requests.Timeout:
            logger.error("Telegram API request timed out")
            return {"error": "Request timed out"}
        except requests.RequestException as e:
            logger.error("Telegram API request failed: %s", e)
            return {"error": str(e)}
