"""Central notification emitter for important user-facing events."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from utils.notification_prefs import should_notify

IMPORTANT_NOTIFICATION_EVENTS = {
    "post.scheduled",
    "post.published",
    "post.failed",
    "post.dlq",
    "account.reconnect_required",
    "subscription.expiring",
    "billing.failed",
}

IMPORTANT_NOTIFICATION_TYPES = {
    "post.scheduled",
    "post.published",
    "post.failed",
    "post.partial_failed",
    "post.dlq",
    "publish_success",
    "publish_failed",
    "publish_permanently_failed",
    "publish_partial_recovery",
    "publish_recovered",
    "pre_upload_timeout",
    "account.reconnect_required",
    "account.suspended",
    "subscription.expiring",
    "subscription.expired",
    "subscription_expiring",
    "subscription.grace_reminder",
    "subscription.grace_final_warning",
    "posts_paused",
    "subscription.posts_deleted",
    "billing.payment_failed",
    "billing.payment_failed_final",
}

DEFAULT_CHANNELS: dict[str, tuple[str, ...]] = {
    "post.scheduled": ("in_app",),
    "post.published": ("in_app",),
    "post.failed": ("email", "in_app"),
    "post.dlq": ("email", "in_app"),
    "account.reconnect_required": ("email", "in_app"),
    "subscription.expiring": ("email", "in_app"),
    "billing.failed": ("email", "in_app"),
}


def default_target_path(event: str, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    if event in {"post.scheduled", "post.published", "post.failed", "post.dlq"}:
        return "/content-library"
    if event == "account.reconnect_required" or metadata.get("account_id"):
        return "/accounts"
    if event in {"subscription.expiring", "billing.failed"}:
        return "/billing"
    return "/dashboard"


async def emit_notification(
    db,
    *,
    user_id: str,
    event: str,
    notification_type: str,
    title: str,
    message: str,
    severity: str = "low",
    channels: Iterable[str] | None = None,
    metadata: dict[str, Any] | None = None,
    target_path: str | None = None,
    dedup_key: str | None = None,
    created_at: datetime | None = None,
    update_existing: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> list[str]:
    """Write preference-aware notifications with a consistent document shape.

    Returns the channels that were inserted or updated.
    """
    if not user_id:
        return []

    normalized_channels = tuple(channels or DEFAULT_CHANNELS.get(event, ("in_app",)))
    now = created_at or datetime.now(timezone.utc)
    written: list[str] = []
    metadata = metadata or {}

    for channel in normalized_channels:
        if not await should_notify(db, user_id, event, channel):
            continue

        notification_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "id": notification_id,
            "notification_id": notification_id,
            "user_id": user_id,
            "event": event,
            "type": notification_type,
            "title": title,
            "message": message,
            "severity": severity,
            "channel": channel,
            "metadata": metadata,
            "target_path": target_path or default_target_path(event, metadata),
            "dedup_key": dedup_key,
            "is_read": False,
            "read": False,
            "created_at": now,
        }
        if extra_fields:
            payload.update(extra_fields)

        if dedup_key:
            query = {
                "user_id": user_id,
                "channel": channel,
                "dedup_key": dedup_key,
            }
            if update_existing:
                set_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"id", "notification_id"}
                }
                result = await db.notifications.update_one(
                    query,
                    {
                        "$set": set_payload,
                        "$setOnInsert": {
                            "id": notification_id,
                            "notification_id": notification_id,
                        },
                    },
                    upsert=True,
                )
            else:
                result = await db.notifications.update_one(
                    query,
                    {"$setOnInsert": payload},
                    upsert=True,
                )
            if getattr(result, "matched_count", 0) or getattr(result, "upserted_id", None):
                written.append(channel)
            continue

        await db.notifications.insert_one(payload)
        written.append(channel)

    return written
