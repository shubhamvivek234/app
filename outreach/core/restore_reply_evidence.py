"""Validate bounded outside-backup reply evidence without importing messages."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
import re
from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core.restore_epoch import now
from outreach.core.restore_reconciliation import ReconciliationError, _digest, _reference, bounded_json

UTC_TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z')


def validate(records: list[dict[str, Any]], *, workspace_id: str) -> dict[str, Any]:
    """Check immutable reply metadata and return a non-authorizing summary.

    Raw message bodies, provider tokens, and transport receipts are rejected.
    The result is suitable for suppression review only; it never creates inbox
    history or grants permission to send.
    """
    _reference(workspace_id, "workspace_id")
    records = bounded_json(records)
    if not isinstance(records, list) or not records or len(records) > 100:
        raise ReconciliationError("bounded reply evidence records are required")
    seen: set[str] = set()
    events: set[str] = set()
    latest: dict[tuple[str, str], datetime] = {}
    captured_time = now()
    for row in records:
        if not isinstance(row, dict):
            raise ReconciliationError("reply evidence row is malformed")
        if set(row) != {"record_id", "workspace_id", "sender_digest", "recipient_digest",
                        "event_digest", "observed_at"}:
            raise ReconciliationError("reply evidence contains unsupported or private fields")
        record_id = _reference(row["record_id"], "record_id")
        if record_id in seen or row["workspace_id"] != workspace_id:
            raise ReconciliationError("reply evidence identity or scope is ambiguous")
        seen.add(record_id)
        for field in ("sender_digest", "recipient_digest", "event_digest"):
            _digest(row[field], field)
        if row['event_digest'] in events:
            raise ReconciliationError("Reply event digest is duplicated or ambiguously bound")
        events.add(row['event_digest'])
        value = row["observed_at"]
        if not isinstance(value, str) or not UTC_TIME.fullmatch(value):
            raise ReconciliationError("reply evidence timestamp is malformed")
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ReconciliationError("reply evidence timestamp is malformed") from None
        if stamp.tzinfo is None:
            raise ReconciliationError("reply evidence timestamp must include UTC")
        stamp = stamp.astimezone(timezone.utc)
        if stamp > captured_time:
            raise ReconciliationError("Reply evidence timestamp is in the future")
        key = (row["sender_digest"], row["recipient_digest"])
        if key in latest and stamp < latest[key]:
            raise ReconciliationError("reply evidence timestamps are not monotonic")
        latest[key] = stamp
    return {
        "workspace_id": workspace_id,
        "reply_metadata_valid": True,
        "reply_evidence_verified": False,
        "reply_evidence_authenticated": False,
        "sender_mapping_verified": False,
        "reply_count": len(records),
        "reply_digest": canonical_hash(records),
        "suppression_review_required": True,
        "reply_history_restored": False,
        "activation_allowed": False,
    }
