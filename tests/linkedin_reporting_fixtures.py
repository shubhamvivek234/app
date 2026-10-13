"""Synthetic rows using the production intent/outbox shapes; no transport."""
from datetime import datetime, timedelta, timezone

from outreach.core.authorization import canonical_hash


def clock():
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def intent(now, kind="send_message", *, node="n", lead="l", sender="s", campaign="c", age=2):
    at = now - timedelta(days=age)
    key = canonical_hash(["w", "enrollment", 1, node, kind])
    return {"_id": key, "logical_dedup_key": key, "workspace_id": "w", "campaign_id": campaign,
        "lead_id": lead, "sender_id": sender, "enrollment_id": "enrollment", "sequence_version": 1,
        "node_id": node, "legacy_operation_id": f"{lead}:{node}", "action_kind": kind,
        "created_at": at - timedelta(minutes=1), "status": "executed", "updated_at": now, "claim_token": "original-owner",
        "attempt": {"id": f"attempt-{node}", "owner_token": "original-owner", "sender_id": sender, "possible_submission_at": at - timedelta(seconds=1),
            "completed_at": at, "outcome": "provider_accepted",
            "provider_result_status": "invite_sent" if kind == "connection_request" else "message_sent"}}


def observation(row, at, *, key="evt_1", channel="linkedin"):
    event_type = "lead.connection_accepted" if row["action_kind"] == "connection_request" else "lead.replied"
    return {"id": key, "workspace_id": "w", "type": event_type, "aggregate_id": row["lead_id"],
        "occurred_at": at, "created_at": at, "status": "pending",
        "payload": {"id": key, "workspace_id": "w", "type": event_type, "occurred_at": at.isoformat(),
            "data": {"channel": channel, "campaign_id": row["campaign_id"],
                "lead_id": row["lead_id"], "sender_account_id": row["sender_id"]}}}
