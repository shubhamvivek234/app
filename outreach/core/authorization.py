"""Compatible authorization snapshots; MongoDB remains the dispatch authority."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from outreach.core.inbox_freshness import credential_generation


def canonical_hash(value: Any) -> str:
    """Frame structured fields unambiguously before hashing a policy binding."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def authorization_snapshot(campaign: dict, account: dict, sequence: dict) -> dict:
    return {
        "workspace_id": campaign.get("workspace_id"), "campaign_id": campaign.get("id"),
        "sender_id": account.get("id"), "revision": campaign.get("authorization_revision", 0),
        "credential_generation": credential_generation(account),
        "sequence_version": sequence.get("version", 1),
        "sequence_digest": canonical_hash(sequence.get("compiled_dag")),
    }


def dispatch_block_reason(lead: dict, campaign: dict, account: dict, sequence: dict,
                          expected: dict) -> str | None:
    """Validate a prepared mutation against freshly loaded tenant-scoped records."""
    workspace = expected.get("workspace_id")
    if not workspace or any(doc.get("workspace_id") != workspace for doc in (lead, campaign, account, sequence)):
        return "scope_changed"
    from outreach.core.search_sources import unverified_search_lead
    if unverified_search_lead(lead):
        return "search_source_review_required"
    if campaign.get("id") != expected.get("campaign_id") or lead.get("campaign_id") != campaign.get("id"):
        return "scope_changed"
    if sequence.get("campaign_id") != campaign.get("id") or sequence.get("is_deleted"):
        return "sequence_changed"
    if campaign.get("is_deleted") or campaign.get("status") != "active":
        return "campaign_not_active"
    if campaign.get("sequence_edit_pending"):
        return "sequence_changed"
    if campaign.get("pause_reasons"):
        return "campaign_paused"
    revision = campaign.get("authorization_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        return "authorization_required"
    if revision != expected.get("revision") or lead.get("authorized_revision") != revision:
        return "authorization_stale"
    if account.get("status") != "active" or account.get("id") != expected.get("sender_id"):
        return "sender_changed"
    if lead.get("assigned_account_id") != account.get("id") or account.get("id") not in (campaign.get("sender_account_ids") or []):
        return "sender_changed"
    if credential_generation(account) != expected.get("credential_generation"):
        return "sender_changed"
    if (sequence.get("version", 1) != expected.get("sequence_version")
            or lead.get("sequence_version") != expected.get("sequence_version")
            or canonical_hash(sequence.get("compiled_dag")) != expected.get("sequence_digest")):
        return "sequence_changed"
    if (lead.get("has_replied") or lead.get("do_not_contact") or lead.get("is_suppressed")
            or lead.get("execution_state") in {"replied", "finished", "bounced", "failed"}):
        return "lead_suppressed"
    if lead.get("execution_state") not in {"queued", "waiting_delay"}:
        return "lead_paused"
    return None
