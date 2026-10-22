"""Completed LinkedIn coverage, credential fencing and durable priority sync."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import hashlib
import json
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.paid_access import _utc

PARSER_VERSION = 1
MAX_FRESHNESS_SECONDS = 1800


def credential_generation(account: dict) -> str:
    """Legacy sessions are bound to encrypted material without exposing it."""
    generation = account.get("credential_generation")
    if isinstance(generation, str) and generation:
        return generation
    material = [account.get("session_cookie_enc") or account.get("encrypted_session_cookie") or account.get("li_at_enc"),
                account.get("jsession_id") or account.get("jsession_id_enc"), account.get("li_a_enc")]
    return "legacy:" + hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def session_filter(account: dict) -> dict:
    query = {"id": account["id"], "workspace_id": account["workspace_id"], "status": "active"}
    for field in ("credential_generation", "session_cookie_enc", "encrypted_session_cookie", "jsession_id", "li_a_enc", "li_at_enc", "jsession_id_enc"):
        query[field] = account[field] if field in account else {"$exists": False}
    return query


def freshness_reason(account: dict, *, now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    marker = account.get("inbox_sync")
    if not isinstance(marker, dict) or marker.get("status") != "complete":
        return "inbox_sync_required"
    if marker.get("credential_generation") != credential_generation(account):
        return "inbox_generation_changed"
    started = _utc(marker.get("coverage_started_at"))
    completed = _utc(marker.get("completed_at"))
    if (marker.get("parser_version") != PARSER_VERSION or started is None or completed is None
            or completed < started or started > now or completed > now):
        return "inbox_coverage_invalid"
    if (now - started).total_seconds() >= MAX_FRESHNESS_SECONDS:
        return "inbox_stale"
    return None


async def request_priority_sync(db: AsyncIOMotorDatabase, workspace_id: str, sender_id: str, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    result = await db.outreach_accounts.update_one(
        {"id": sender_id, "workspace_id": workspace_id, "status": "active", "$or": [
            {"priority_sync_requested_at": {"$exists": False}},
            {"priority_sync_requested_at": {"$lte": now - timedelta(minutes=5)}},
        ]},
        {"$set": {"priority_sync_requested_at": now, "priority_sync_due_at": now}},
    )
    return result.modified_count == 1


async def require_fresh_inbox(db: AsyncIOMotorDatabase, workspace_id: str, account: dict) -> str | None:
    reason = freshness_reason(account)
    if reason:
        await request_priority_sync(db, workspace_id, account["id"])
    else:
        remember = getattr(type(db), "note_inbox_deadline", None)
        if callable(remember):
            remember(db, account)
    return reason
