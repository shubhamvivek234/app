"""New execution controls are tested independently of legacy paid-gate stubs."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from outreach.models import Entitlement, ProxyAsset, SenderConnection
from outreach.core.authorization import authorization_snapshot, dispatch_block_reason
from outreach.core.inbox_freshness import credential_generation, freshness_reason, request_priority_sync
from tests.outreach_memory import Database

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def context():
    campaign = {"id": "c", "workspace_id": "w", "status": "active", "authorization_revision": 2,
                "pause_reasons": [], "sender_account_ids": ["a"]}
    account = {"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g1"}
    sequence = {"campaign_id": "c", "workspace_id": "w", "version": 1, "compiled_dag": {"nodes": {}}}
    lead = {"id": "l", "workspace_id": "w", "campaign_id": "c", "assigned_account_id": "a",
            "authorized_revision": 2, "sequence_version": 1, "current_node_id": "n", "execution_state": "queued"}
    return lead, campaign, account, sequence


def test_existing_domain_ids_and_fields_remain_compatible():
    ent = Entitlement(workspace_id="uuid-string", seats=2, paid_through=NOW, payment_source="manual_verified_invoice")
    assert ent.model_dump()["seats"] == 2
    proxy = ProxyAsset.model_validate({"_id": "iproyal:old", "last_workspace_id": "w", "country_code": "IN", "expires_at": NOW})
    assert proxy.id == "iproyal:old"
    assert SenderConnection(id="a", workspace_id="w", status="active").id == "a"
    with pytest.raises(ValidationError):
        Entitlement(workspace_id="w", seats=0, paid_through=NOW)


@pytest.mark.parametrize("change,reason", [
    ({"status": "paused"}, "campaign_not_active"),
    ({"pause_reasons": ["billing_expired", "operator_pause"]}, "campaign_paused"),
    ({"authorization_revision": 3}, "authorization_stale"),
    ({"authorization_revision": 0}, "authorization_required"),
    ({"is_deleted": True}, "campaign_not_active"),
])
def test_current_authorization_denies_stale_or_blocked_work(change, reason):
    lead, campaign, account, sequence = context()
    expected = authorization_snapshot(campaign, account, sequence)
    campaign.update(change)
    assert dispatch_block_reason(lead, campaign, account, sequence, expected) == reason


def test_sender_reconnect_and_sequence_change_fence_prepared_work():
    lead, campaign, account, sequence = context()
    expected = authorization_snapshot(campaign, account, sequence)
    account["credential_generation"] = "g2"
    assert dispatch_block_reason(lead, campaign, account, sequence, expected) == "sender_changed"
    account["credential_generation"] = "g1"
    sequence["compiled_dag"] = {"nodes": {"changed": {}}}
    assert dispatch_block_reason(lead, campaign, account, sequence, expected) == "sequence_changed"


def test_suppression_and_cross_workspace_context_are_denied():
    lead, campaign, account, sequence = context()
    expected = authorization_snapshot(campaign, account, sequence)
    lead["has_replied"] = True
    assert dispatch_block_reason(lead, campaign, account, sequence, expected) == "lead_suppressed"
    lead.pop("has_replied")
    account["workspace_id"] = "other"
    assert dispatch_block_reason(lead, campaign, account, sequence, expected) == "scope_changed"


def fresh_account():
    account = {"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g"}
    account["inbox_sync"] = {"status": "complete", "credential_generation": credential_generation(account),
                             "coverage_started_at": NOW - timedelta(minutes=2), "completed_at": NOW - timedelta(minutes=1),
                             "parser_version": 1}
    return account


@pytest.mark.parametrize("field,val", [
    ("status", "partial"), ("status", "running"), ("credential_generation", "old"),
    ("coverage_started_at", NOW + timedelta(seconds=1)),
    ("coverage_started_at", NOW - timedelta(minutes=30)),
    ("completed_at", None), ("parser_version", 0),
])
def test_missing_partial_future_and_old_freshness_denies_followups(field, val):
    account = fresh_account()
    account["inbox_sync"][field] = val
    assert freshness_reason(account, now=NOW)


def test_complete_coverage_is_aged_from_start_and_legacy_credentials_are_bound():
    account = fresh_account()
    assert freshness_reason(account, now=NOW) is None
    account.pop("inbox_sync")
    assert freshness_reason(account, now=NOW) == "inbox_sync_required"
    legacy = {"session_cookie_enc": "ciphertext1", "jsession_id": "ciphertext2"}
    generation = credential_generation(legacy)
    legacy["session_cookie_enc"] = "new-ciphertext"
    assert credential_generation(legacy) != generation


@pytest.mark.asyncio
async def test_priority_sync_requests_are_durable_and_deduplicated():
    db = Database(outreach_accounts=[fresh_account()])
    assert await request_priority_sync(db, "w", "a", now=NOW)
    assert not await request_priority_sync(db, "w", "a", now=NOW)
    assert not await request_priority_sync(db, "other", "a", now=NOW)
    assert await request_priority_sync(db, "w", "a", now=NOW + timedelta(minutes=6))


@pytest.mark.asyncio
@pytest.mark.parametrize("page,complete", [([], True), ([{"bad_schema": True}], False),
                                          ([{"lead_urn": "urn:l", "thread_urn": "urn:t", "messages": [{"sender_type": "unknown"}]}], False)])
async def test_sync_only_publishes_complete_parsed_coverage(monkeypatch, page, complete):
    from unittest.mock import AsyncMock
    from outreach.engine import inbox_sync
    account = fresh_account()
    account["session_cookie_enc"] = "ciphertext"
    db = Database(outreach_accounts=[account])
    client = type("Client", (), {"fetch_conversations": AsyncMock(return_value=page)})()
    monkeypatch.setattr(inbox_sync, "VoyagerClient", lambda **kwargs: client)
    monkeypatch.setattr(inbox_sync, "sender_is_ready", AsyncMock(return_value=True))
    # These parser/reconnect tests isolate credential opening with their fake client.
    monkeypatch.setattr("outreach.core.session_custody.account_session", AsyncMock(return_value={"li_at": "local-test-cookie", "jsession_id": "ajax:local", "li_a": ""}))
    result = await inbox_sync.InboxSynchronizer(db, "w").sync_account_inbox("a")
    stored = await db.outreach_accounts.find_one({"id": "a"})
    assert (freshness_reason(stored) is None) == complete
    assert result["coverage_complete"] == complete


@pytest.mark.asyncio
async def test_capped_sync_and_reconnect_cannot_create_freshness(monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.engine import inbox_sync
    account = fresh_account()
    account["session_cookie_enc"] = "ciphertext"
    db = Database(outreach_accounts=[account])
    calls = 0

    async def fetch(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await db.outreach_accounts.update_one({"id": "a"}, {"$set": {"credential_generation": "new"}})
        return []

    client = type("Client", (), {"fetch_conversations": staticmethod(fetch)})()
    monkeypatch.setattr(inbox_sync, "VoyagerClient", lambda **kwargs: client)
    monkeypatch.setattr(inbox_sync, "sender_is_ready", AsyncMock(return_value=True))
    # These parser/reconnect tests isolate credential opening with their fake client.
    monkeypatch.setattr("outreach.core.session_custody.account_session", AsyncMock(return_value={"li_at": "local-test-cookie", "jsession_id": "ajax:local", "li_a": ""}))
    result = await inbox_sync.InboxSynchronizer(db, "w").sync_account_inbox("a")
    assert not result["coverage_complete"]
    assert freshness_reason(await db.outreach_accounts.find_one({"id": "a"}))


@pytest.mark.asyncio
async def test_final_preflight_observes_reply_before_dispatch(monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.tasks import sequence_executor as executor
    lead, campaign, account, sequence = context()
    expected = authorization_snapshot(campaign, account, sequence)
    db = Database(outreach_leads=[lead], outreach_campaigns=[campaign], outreach_accounts=[account], outreach_sequences=[sequence])
    await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
    monkeypatch.setattr(executor, "sender_is_ready", AsyncMock(return_value=True))
    reason = await executor._preflight_dispatch(db, lead, expected, "send_message")
    assert reason == "lead_suppressed"


@pytest.mark.asyncio
async def test_conditional_advancement_does_not_overwrite_a_reply():
    from outreach.tasks.sequence_executor import _advance_lead
    lead, _, _, _ = context()
    db = Database(outreach_leads=[lead])
    await db.outreach_leads.update_one({"id": "l"}, {"$set": {"has_replied": True, "execution_state": "replied"}})
    assert not await _advance_lead(db, lead, {"execution_state": "finished"})
    assert (await db.outreach_leads.find_one({"id": "l"}))["execution_state"] == "replied"
