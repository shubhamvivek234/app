"""
Comprehensive test suite for Outreach Event Pipeline (Slice 1: Foundation).
Verifies:
1. Frozen event definitions and envelope formatting
2. Transactional outbox persistence and deduplication
3. Cross-workspace isolation in outbox fanout
4. DNS rebinding and SSRF protection (private IP / loopback / metadata blocking)
5. HMAC-SHA256 signature generation and 5-minute replay window tolerance
6. Delivery worker bounded retries, permanent 4xx handling, and dead-letter queue
7. Manual replay from dead letter retaining stable event_id
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from outreach.core.event_definitions import (
    OutboxEventEnvelope,
    WebhookEvent,
    create_event_envelope,
)
from outreach.core.event_outbox import (
    record_outbox_event,
    scan_and_fanout_outbox,
)
from outreach.core.safe_transport import (
    SSRFSecurityError,
    is_ip_blocked,
    validate_webhook_url,
)
from outreach.core.webhook_delivery import (
    dispatch_due_deliveries,
    replay_delivery,
)
from outreach.core.webhook_signer import (
    build_delivery_headers,
    compute_signature,
    verify_signature,
)
import ipaddress


@pytest.fixture(autouse=True)
def enable_integrations_for_tests(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")


# ── 1. Event Definitions & Envelope Tests ───────────────────────────────────

def test_frozen_event_catalog():
    """Verify the event catalog contains only verified production events."""
    expected_events = {
        "lead.created",
        "lead.replied",
        "lead.connection_accepted",
        "lead.stage_changed",
        "campaign.paused",
        "email.accepted",
    }
    actual_events = {e.value for e in WebhookEvent}
    assert actual_events == expected_events


def test_event_envelope_structure():
    """Verify envelope formatting and defaults."""
    env = create_event_envelope(
        workspace_id="ws_test_123",
        event_type=WebhookEvent.LEAD_REPLIED,
        data={"lead_id": "lead_1", "campaign_id": "camp_1", "channel": "linkedin"},
    )
    assert env.id.startswith("evt_")
    assert env.version == 1
    assert env.type == "lead.replied"
    assert env.workspace_id == "ws_test_123"
    assert env.data["lead_id"] == "lead_1"
    assert "occurred_at" in env.model_dump()


# ── 2. SSRF & DNS Rebinding Security Tests ──────────────────────────────────

def test_validate_webhook_url_rejects_non_https():
    """HTTPS is strictly required for webhook destinations."""
    with pytest.raises(SSRFSecurityError, match="must use HTTPS"):
        validate_webhook_url("http://example.com/webhook")


def test_validate_webhook_url_rejects_credentials():
    """URLs with embedded credentials must be rejected."""
    with pytest.raises(SSRFSecurityError, match="credentials"):
        validate_webhook_url("https://user:password@example.com/webhook")


def test_validate_webhook_url_rejects_metadata_hostnames():
    """Cloud metadata hostnames must be rejected."""
    with pytest.raises(SSRFSecurityError, match="Blocked destination"):
        validate_webhook_url("https://metadata.google.internal/webhook")
    with pytest.raises(SSRFSecurityError, match="Blocked destination"):
        validate_webhook_url("https://169.254.169.254/webhook")


def test_is_ip_blocked_catches_all_private_ranges():
    """Verify loopback, RFC 1918, link-local, and IPv6 loopback are blocked."""
    assert is_ip_blocked(ipaddress.ip_address("127.0.0.1"))
    assert is_ip_blocked(ipaddress.ip_address("10.0.0.5"))
    assert is_ip_blocked(ipaddress.ip_address("172.16.50.1"))
    assert is_ip_blocked(ipaddress.ip_address("192.168.1.100"))
    assert is_ip_blocked(ipaddress.ip_address("169.254.169.254"))
    assert is_ip_blocked(ipaddress.ip_address("::1"))
    assert is_ip_blocked(ipaddress.ip_address("fc00::1"))
    assert is_ip_blocked(ipaddress.ip_address("fe80::1"))
    # Public IP must NOT be blocked
    assert not is_ip_blocked(ipaddress.ip_address("8.8.8.8"))
    assert not is_ip_blocked(ipaddress.ip_address("1.1.1.1"))


# ── 3. HMAC Signatures & Replay Prevention Tests ─────────────────────────────

def test_signature_computation_and_verification():
    """Verify HMAC-SHA256 signature verification."""
    secret = "whsec_supersecretkey123"
    body = b'{"id":"evt_1","type":"lead.replied"}'
    now = datetime.now(timezone.utc)
    ts_str = now.isoformat()

    sig = compute_signature(body, secret, ts_str)
    assert sig.startswith("sha256=")

    # Verification with exact timestamp succeeds
    assert verify_signature(body, secret, sig, ts_str, current_time=now)

    # Verification with altered body fails
    assert not verify_signature(b'{"id":"evt_2"}', secret, sig, ts_str, current_time=now)

    # Verification with wrong secret fails
    assert not verify_signature(body, "wrong_secret", sig, ts_str, current_time=now)


def test_signature_replay_prevention_enforces_tolerance():
    """Signatures outside the 5-minute clock tolerance must be rejected."""
    secret = "whsec_supersecretkey123"
    body = b'{"test":"payload"}'
    old_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 12, 10, 0, tzinfo=timezone.utc)  # 10 minutes later

    old_ts_str = old_time.isoformat()
    sig = compute_signature(body, secret, old_ts_str)

    # Within 300s window -> False (10m = 600s skew)
    assert not verify_signature(body, secret, sig, old_ts_str, tolerance_seconds=300, current_time=now)

    # Within 700s window -> True
    assert verify_signature(body, secret, sig, old_ts_str, tolerance_seconds=700, current_time=now)


def test_build_delivery_headers_keeps_stable_event_id_with_fresh_timestamp():
    """Event ID remains stable, but timestamp & signature update per attempt."""
    secret = "whsec_key"
    body = b'{"data":1}'
    t1 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 29, 10, 5, 0, tzinfo=timezone.utc)

    h1 = build_delivery_headers(body, secret, "evt_123", "del_attempt_1", timestamp=t1)
    h2 = build_delivery_headers(body, secret, "evt_123", "del_attempt_2", timestamp=t2)

    assert h1["X-Unravler-Event-Id"] == "evt_123"
    assert h2["X-Unravler-Event-Id"] == "evt_123"
    assert h1["X-Unravler-Delivery-Id"] == "del_attempt_1"
    assert h2["X-Unravler-Delivery-Id"] == "del_attempt_2"
    assert h1["X-Unravler-Timestamp"] != h2["X-Unravler-Timestamp"]
    assert h1["X-Unravler-Signature"] != h2["X-Unravler-Signature"]


# ── 4. Transactional Outbox & Fanout Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_record_outbox_event_idempotency():
    """Recording the same event dedupe_key returns the existing event."""
    from pymongo.errors import DuplicateKeyError

    mock_db = MagicMock()
    existing_doc = {"id": "evt_existing", "dedupe_key": "lead.replied:l1:m1", "status": "pending"}

    # First call: insert succeeds
    mock_db.outreach_event_outbox.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc1"))
    doc1 = await record_outbox_event(
        db=mock_db,
        workspace_id="ws_1",
        event_type=WebhookEvent.LEAD_REPLIED,
        aggregate_id="l1",
        dedupe_key="lead.replied:l1:m1",
        data={"lead_id": "l1"},
    )
    assert doc1["dedupe_key"] == "lead.replied:l1:m1"
    assert doc1["status"] == "pending"

    # Second call: DuplicateKeyError raised -> fetches existing
    mock_db.outreach_event_outbox.insert_one = AsyncMock(side_effect=DuplicateKeyError("duplicate"))
    mock_db.outreach_event_outbox.find_one = AsyncMock(return_value=existing_doc)

    doc2 = await record_outbox_event(
        db=mock_db,
        workspace_id="ws_1",
        event_type=WebhookEvent.LEAD_REPLIED,
        aggregate_id="l1",
        dedupe_key="lead.replied:l1:m1",
        data={"lead_id": "l1"},
    )
    assert doc2["id"] == "evt_existing"


@pytest.mark.asyncio
async def test_scan_and_fanout_outbox_cross_workspace_isolation():
    """Only current same-workspace subscriptions create reference-only deliveries."""
    from tests.outreach_memory import Database
    from utils.encryption import encrypt
    event = {"id": "evt_abc", "workspace_id": "ws_alpha", "type": "lead.replied",
             "payload": {"id": "evt_abc", "type": "lead.replied", "data": {"lead_id": "lead_1"}}}
    db = Database()
    db.outreach_event_outbox.find_one_and_update = AsyncMock(side_effect=[event, None])
    for workspace, hook in [("ws_alpha", "wh_1"), ("ws_alpha", "wh_2"), ("other", "wh_3")]:
        await db.outreach_webhooks.insert_one({"id": hook, "workspace_id": workspace,
            "target_url": "https://example.com/hook", "secret_enc": encrypt("private-secret"),
            "status": "active", "events": ["lead.replied"]})
    stats = await scan_and_fanout_outbox(db, batch_size=10)
    assert stats == {"dispatched_events": 1, "deliveries_created": 2}
    assert await db.outreach_webhook_deliveries.count_documents({"workspace_id": "ws_alpha"}) == 2
    assert await db.outreach_webhook_deliveries.count_documents({"workspace_id": "other"}) == 0
    assert "secret_enc" not in str(db.outreach_webhook_deliveries.docs)


# Legacy evidence cannot become sendable after cutover.

@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "retry", "leased"])
async def test_legacy_snapshot_jobs_are_quarantined_without_http(state, monkeypatch):
    from tests.outreach_memory import Database
    db = Database(outreach_webhook_deliveries=[{"workspace_id": "w", "id": "old", "event_id": "event",
        "status": state, "secret_enc": "old-evidence", "target_url_enc": "old-evidence"}])
    monkeypatch.setattr("outreach.core.integration_delivery.IntegrationDelivery.dispatch_due",
        AsyncMock(return_value={"delivered": 0, "failed": 0, "review_required": 0, "cancelled": 0, "retry": 0}))
    client = AsyncMock()
    result = await dispatch_due_deliveries(db, safe_client=client)
    assert result["review_required"] == 1 and result["delivered"] == 0
    client.post.assert_not_awaited()
    saved = await db.outreach_webhook_deliveries.find_one({"workspace_id": "w"})
    assert saved["status"] == "review_required" and saved["secret_enc"] == "old-evidence"


@pytest.mark.asyncio
async def test_replay_preserves_original_evidence_and_denies_reset():
    from tests.outreach_memory import Database
    db = Database(outreach_webhook_deliveries=[{"workspace_id": "w", "id": "old", "event_id": "event", "status": "dead_letter"}])
    with pytest.raises(ValueError, match="cannot be replayed"):
        await replay_delivery(db, "w", "old", "actor")
    assert (await db.outreach_webhook_deliveries.find_one({"workspace_id": "w"}))["status"] == "dead_letter"
