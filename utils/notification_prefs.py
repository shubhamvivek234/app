"""
Phase 8 — Notification preferences with digest mode.
Users can configure per-event notification channels (email, in-app, none)
and opt into digest mode (batches notifications into hourly/daily digests).
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class NotificationChannel(str, Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    NONE = "none"


class DigestFrequency(str, Enum):
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"


SUPPORTED_NOTIFICATION_EVENTS: tuple[str, ...] = (
    "post.published",
    "post.failed",
    "post.dlq",
    "account.expiring",
    "billing.failed",
)

# Default preferences applied to new users and returned to Settings.
DEFAULT_PREFERENCES: dict[str, dict[str, Any]] = {
    "post.published": {"channels": ["in_app"], "digest": "immediate"},
    "post.failed": {"channels": ["email", "in_app"], "digest": "immediate"},
    "post.dlq": {"channels": ["email", "in_app"], "digest": "immediate"},
    "account.expiring": {"channels": ["email", "in_app"], "digest": "immediate"},
    "billing.failed": {"channels": ["email"], "digest": "immediate"},
}

_VALID_CHANNELS = {NotificationChannel.EMAIL.value, NotificationChannel.IN_APP.value}
_VALID_DIGESTS = {item.value for item in DigestFrequency}


def build_default_preferences() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(DEFAULT_PREFERENCES)


def sanitize_preferences(preferences: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(preferences, Mapping):
        return {}

    sanitized: dict[str, dict[str, Any]] = {}
    for event in SUPPORTED_NOTIFICATION_EVENTS:
        raw_pref = preferences.get(event)
        if not isinstance(raw_pref, Mapping):
            continue

        default_pref = DEFAULT_PREFERENCES[event]
        raw_channels = raw_pref.get("channels", default_pref["channels"])
        channels: list[str] = []
        if isinstance(raw_channels, list):
            for channel in raw_channels:
                if channel in _VALID_CHANNELS and channel not in channels:
                    channels.append(channel)

        digest = raw_pref.get("digest", default_pref["digest"])
        if digest not in _VALID_DIGESTS:
            digest = default_pref["digest"]

        sanitized[event] = {
            "channels": channels,
            "digest": digest,
        }

    return sanitized


async def get_user_prefs(db, user_id: str) -> dict:
    """Fetch user notification preferences, falling back to defaults."""
    doc = await db.notification_prefs.find_one({"user_id": user_id})
    prefs = build_default_preferences()
    if doc:
        prefs.update(sanitize_preferences(doc.get("prefs", {})))
    return prefs


async def should_notify(
    db,
    user_id: str,
    event: str,
    channel: str,
) -> bool:
    """
    Returns True if the user has enabled `channel` for `event`.
    If channel is not in the user's preference for this event, returns False.
    """
    prefs = await get_user_prefs(db, user_id)
    event_pref = prefs.get(event, {})
    return channel in event_pref.get("channels", [])


async def get_digest_frequency(db, user_id: str, event: str) -> str:
    """Return the digest frequency for the given event."""
    prefs = await get_user_prefs(db, user_id)
    return prefs.get(event, {}).get("digest", "immediate")


async def insert_notification_if_enabled(
    db,
    *,
    user_id: str,
    event: str,
    channel: str,
    notification_type: str,
    message: str,
    created_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> bool:
    """
    Insert a notification document only when the user has enabled the given
    event/channel pair. This keeps notification producers aligned with prefs.
    """
    if not await should_notify(db, user_id, event, channel):
        return False

    payload: dict[str, Any] = {
        "user_id": user_id,
        "type": notification_type,
        "channel": channel,
        "message": message,
        "created_at": created_at or datetime.now(timezone.utc),
    }
    if metadata:
        payload["metadata"] = metadata
    if extra_fields:
        payload.update(extra_fields)

    await db.notifications.insert_one(payload)
    return True
