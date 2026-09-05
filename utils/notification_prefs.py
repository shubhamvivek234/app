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
    "post.scheduled",
    "post.published",
    "post.failed",
    "post.dlq",
    "account.reconnect_required",
    "subscription.expiring",
    "account.expiring",
    "billing.failed",
    "approval.submitted",
    "approval.approved",
    "approval.changes_requested",
    "approval.returned",
    "approval.overdue",
)

# Default preferences applied to new users and returned to Settings.
DEFAULT_PREFERENCES: dict[str, dict[str, Any]] = {
    "post.scheduled": {"channels": ["in_app"], "digest": "immediate"},
    "post.published": {"channels": ["in_app"], "digest": "immediate"},
    "post.failed": {"channels": ["email", "in_app"], "digest": "immediate"},
    "post.dlq": {"channels": ["email", "in_app"], "digest": "immediate"},
    "account.reconnect_required": {"channels": ["email", "in_app"], "digest": "immediate"},
    "subscription.expiring": {"channels": ["email", "in_app"], "digest": "immediate"},
    "account.expiring": {"channels": ["email", "in_app"], "digest": "immediate"},
    "billing.failed": {"channels": ["email", "in_app"], "digest": "immediate"},
    "approval.submitted": {"channels": ["in_app"], "digest": "immediate"},
    "approval.approved": {"channels": ["in_app"], "digest": "immediate"},
    "approval.changes_requested": {"channels": ["in_app"], "digest": "immediate"},
    "approval.returned": {"channels": ["in_app"], "digest": "immediate"},
    "approval.overdue": {"channels": ["email", "in_app"], "digest": "immediate"},
}

_EVENT_ALIASES: dict[str, tuple[str, ...]] = {
    "subscription.expiring": ("account.expiring",),
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


def _apply_alias_preferences(
    prefs: dict[str, dict[str, Any]],
    raw_prefs: Mapping[str, Any] | None,
) -> None:
    if not isinstance(raw_prefs, Mapping):
        return
    for event, aliases in _EVENT_ALIASES.items():
        if event in raw_prefs:
            continue
        for alias in aliases:
            alias_pref = sanitize_preferences({alias: raw_prefs.get(alias)}).get(alias)
            if alias_pref is not None:
                prefs[event] = alias_pref
                break


async def get_user_prefs(db, user_id: str) -> dict:
    """Fetch user notification preferences, falling back to defaults."""
    doc = await db.notification_prefs.find_one({"user_id": user_id})
    prefs = build_default_preferences()
    if doc:
        raw_prefs = doc.get("prefs", {})
        prefs.update(sanitize_preferences(raw_prefs))
        _apply_alias_preferences(prefs, raw_prefs)
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
    if event == "user.welcome":
        return True

    prefs = await get_user_prefs(db, user_id)
    event_pref = prefs.get(event, {})
    if channel in event_pref.get("channels", []):
        return True
    for alias in _EVENT_ALIASES.get(event, ()):
        alias_pref = prefs.get(alias, {})
        if channel in alias_pref.get("channels", []):
            return True
    return False


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
