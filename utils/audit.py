"""
Phase 7.5 — Audit event stream.
Writes immutable audit records to the audit_events collection.
Every significant action (post created/updated/deleted, account connected,
member invited, billing changed) is recorded here.
"""
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {
    "post.created",
    "post.updated",
    "post.deleted",
    "post.published",
    "post.failed",
    "account.connected",
    "account.disconnected",
    "member.invited",
    "member.removed",
    "member.role_changed",
    "billing.plan_changed",
    "billing.payment_failed",
    "webhook.registered",
    "webhook.deleted",
    "api_key.created",
    "api_key.revoked",
    "mfa.enabled",
    "mfa.disabled",
    "security.impossible_travel",
}


async def log_audit_event(
    db,
    *,
    action: str,
    actor_id: str,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Write an immutable audit event. Never raises — log failure but don't block
    the main operation.

    Documents are stored in audit_events collection with a 90-day TTL index.
    They are append-only — never update or delete audit records.
    """
    if action not in _VALID_ACTIONS:
        logger.warning("Unknown audit action: %s — recording anyway", action)

    event = {
        "action": action,
        "actor_id": actor_id,
        "workspace_id": workspace_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "created_at": datetime.now(timezone.utc),
    }

    try:
        await db.audit_events.insert_one(event)
    except Exception as exc:
        logger.error("Failed to write audit event action=%s: %s", action, exc)
