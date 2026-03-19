"""
Phase 7.5.1 — Audit event stream (db layer).
Append-only audit_events collection — one document per significant action.
This module owns the collection schema and index setup.
The write helper lives in utils/audit.py to avoid circular imports.

Full event catalogue (architecture Section 25.13):
    post.scheduled, post.published, post.failed, post.cancelled, post.updated, post.deleted
    account.connected, account.disconnected
    workspace.created, workspace.member_invited, workspace.member_removed, workspace.member_role_changed
    subscription.created, subscription.upgraded, subscription.downgraded, subscription.cancelled
    billing.payment_succeeded, billing.payment_failed
    user.login, user.login_failed, user.mfa_enabled, user.mfa_disabled, user.deleted
    admin.action, admin.user_suspended, admin.dlq_retried
    api_key.created, api_key.revoked
    webhook.registered, webhook.deleted, webhook.delivery_failed
    security.impossible_travel, security.brute_force_lockout
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


# ── Collection name ────────────────────────────────────────────────────────────
COLLECTION = "audit_events"

# Retention: 90 days per architecture Section 25.13
AUDIT_TTL_SECONDS = int(os.getenv("AUDIT_TTL_SECONDS", str(90 * 24 * 3600)))


def new_event(
    *,
    action: str,
    actor_id: str,
    resource_type: str,
    resource_id: str,
    workspace_id: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """
    Build an audit event document ready to insert into audit_events.
    Caller is responsible for inserting via db.audit_events.insert_one(doc).
    """
    now = datetime.now(timezone.utc)
    return {
        "action": action,
        "actor_id": actor_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "workspace_id": workspace_id,
        "metadata": metadata or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": now,
        # TTL field — MongoDB removes the document after AUDIT_TTL_SECONDS
        "expires_at": now + timedelta(seconds=AUDIT_TTL_SECONDS),
    }


async def ensure_indexes(db) -> None:
    """
    Create indexes on audit_events collection.
    Called from api/main.py lifespan alongside db/indexes.py.
    """
    coll = db[COLLECTION]

    # TTL index — auto-expire records after 90 days
    await coll.create_index("expires_at", expireAfterSeconds=0, background=True)

    # Query patterns: by actor, resource, workspace, action
    await coll.create_index([("actor_id", 1), ("created_at", -1)], background=True)
    await coll.create_index([("resource_type", 1), ("resource_id", 1), ("created_at", -1)], background=True)
    await coll.create_index([("workspace_id", 1), ("created_at", -1)], background=True)
    await coll.create_index([("action", 1), ("created_at", -1)], background=True)
