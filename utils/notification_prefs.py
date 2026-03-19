"""
Phase 8 — Notification preferences with digest mode.
Users can configure per-event notification channels (email, in-app, none)
and opt into digest mode (batches notifications into hourly/daily digests).
"""
from __future__ import annotations

from enum import Enum


class NotificationChannel(str, Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    NONE = "none"


class DigestFrequency(str, Enum):
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"


# Default preferences applied to new users
DEFAULT_PREFERENCES: dict[str, dict] = {
    "post.published":    {"channels": ["in_app"], "digest": "immediate"},
    "post.failed":       {"channels": ["email", "in_app"], "digest": "immediate"},
    "post.dlq":          {"channels": ["email", "in_app"], "digest": "immediate"},
    "account.expiring":  {"channels": ["email", "in_app"], "digest": "immediate"},
    "team.invite":       {"channels": ["email", "in_app"], "digest": "immediate"},
    "billing.failed":    {"channels": ["email"], "digest": "immediate"},
    "analytics.weekly":  {"channels": ["email"], "digest": "daily"},
}


async def get_user_prefs(db, user_id: str) -> dict:
    """Fetch user notification preferences, falling back to defaults."""
    doc = await db.notification_prefs.find_one({"user_id": user_id})
    prefs = DEFAULT_PREFERENCES.copy()
    if doc:
        prefs.update(doc.get("prefs", {}))
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
