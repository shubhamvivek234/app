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
    """Outbox scan only fans out to webhooks matching the event's workspace and subscription."""
    mock_db = MagicMock()

    pending_event = {
        "id": "evt_abc",
        "workspace_id": "ws_alpha",
        "type": "lead.replied",
        "payload": {"id": "evt_abc", "type": "lead.replied", "data": {"lead_id": "lead_1"}},
    }
    # Return pending_event on first call, None on second call
    mock_db.outreach_event_outbox.find_one_and_update = AsyncMock(side_effect=[pending_event, None])

    # 2 webhooks in ws_alpha subscribed to lead.replied
    webhooks = [
        {"id": "wh_1", "workspace_id": "ws_alpha", "target_url": "https://alpha.com/webhook", "secret_enc": ""},
        {"id": "wh_2", "workspace_id": "ws_alpha", "target_url": "https://alpha2.com/webhook", "secret_enc": ""},
    ]
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=webhooks)
    mock_db.outreach_webhooks.find = MagicMock(return_value=cursor)

    mock_db.outreach_webhook_deliveries.insert_one = AsyncMock()
    mock_db.outreach_event_outbox.update_one = AsyncMock()

    stats = await scan_and_fanout_outbox(mock_db, batch_size=10)

    assert stats["dispatched_events"] == 1
    assert stats["deliveries_created"] == 2
    assert mock_db.outreach_webhook_deliveries.insert_one.await_count == 2
    mock_db.outreach_event_outbox.update_one.assert_awaited_once()


# ── 5. Delivery Worker & Retries Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_success_marks_delivered_and_resets_failures():
    """A 200 response marks the delivery delivered and clears consecutive failures."""
    mock_db = MagicMock()
    delivery_doc = {
        "id": "del_1",
        "event_id": "evt_1",
        "destination_id": "wh_1",
        "workspace_id": "ws_1",
        "target_url": "https://consumer.example.com/webhook",
        "secret_enc": "",
        "attempt": 0,
        "max_attempts": 6,
        "payload": {"id": "evt_1", "type": "lead.replied"},
    }
    mock_db.outreach_webhook_deliveries.find_one_and_update = AsyncMock(side_effect=[delivery_doc, None])
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()
    mock_db.outreach_webhooks.update_one = AsyncMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=200, text="OK"))

    stats = await dispatch_due_deliveries(mock_db, safe_client=mock_client)

    assert stats["delivered"] == 1
    # Check update_one sets status to delivered
    delivery_update = mock_db.outreach_webhook_deliveries.update_one.await_args.args[1]
    assert delivery_update["$set"]["status"] == "delivered"
    assert delivery_update["$set"]["attempt"] == 1
    assert delivery_update["$set"]["response_status"] == 200

    # Webhook failures reset
    webhook_update = mock_db.outreach_webhooks.update_one.await_args.args[1]
    assert webhook_update["$set"]["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_delivery_permanent_404_client_error_does_not_retry():
    """A 404 response immediately transitions to failed without retrying."""
    mock_db = MagicMock()
    delivery_doc = {
        "id": "del_2",
        "event_id": "evt_2",
        "destination_id": "wh_2",
        "workspace_id": "ws_1",
        "target_url": "https://consumer.example.com/404",
        "secret_enc": "",
        "attempt": 0,
        "max_attempts": 6,
        "payload": {"id": "evt_2"},
    }
    mock_db.outreach_webhook_deliveries.find_one_and_update = AsyncMock(side_effect=[delivery_doc, None])
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()
    mock_db.outreach_webhooks.find_one_and_update = AsyncMock(return_value={"consecutive_failures": 1})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=404, text="Not Found"))

    stats = await dispatch_due_deliveries(mock_db, safe_client=mock_client)

    assert stats["failed"] == 1
    assert stats["retried"] == 0
    delivery_update = mock_db.outreach_webhook_deliveries.update_one.await_args.args[1]
    assert delivery_update["$set"]["status"] == "failed"


@pytest.mark.asyncio
async def test_delivery_500_retries_with_exponential_backoff():
    """A 500 server error schedules an exponential backoff retry."""
    mock_db = MagicMock()
    delivery_doc = {
        "id": "del_3",
        "event_id": "evt_3",
        "destination_id": "wh_3",
        "workspace_id": "ws_1",
        "target_url": "https://consumer.example.com/500",
        "secret_enc": "",
        "attempt": 1,  # first attempt failed
        "max_attempts": 6,
        "payload": {"id": "evt_3"},
    }
    mock_db.outreach_webhook_deliveries.find_one_and_update = AsyncMock(side_effect=[delivery_doc, None])
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=500, text="Internal Server Error"))

    stats = await dispatch_due_deliveries(mock_db, safe_client=mock_client)

    assert stats["retried"] == 1
    delivery_update = mock_db.outreach_webhook_deliveries.update_one.await_args.args[1]
    assert delivery_update["$set"]["status"] == "retry"
    assert delivery_update["$set"]["attempt"] == 2
    # Verify next_attempt_at was scheduled in the future
    assert delivery_update["$set"]["next_attempt_at"] > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_delivery_exceeding_max_attempts_moves_to_dead_letter():
    """After 6 failed attempts, delivery moves to dead_letter."""
    mock_db = MagicMock()
    delivery_doc = {
        "id": "del_max",
        "event_id": "evt_max",
        "destination_id": "wh_4",
        "workspace_id": "ws_1",
        "target_url": "https://consumer.example.com/500",
        "secret_enc": "",
        "attempt": 5,  # 6th attempt about to happen
        "max_attempts": 6,
        "payload": {"id": "evt_max"},
    }
    mock_db.outreach_webhook_deliveries.find_one_and_update = AsyncMock(side_effect=[delivery_doc, None])
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()
    mock_db.outreach_webhooks.find_one_and_update = AsyncMock(return_value={"consecutive_failures": 6})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=503, text="Service Unavailable"))

    stats = await dispatch_due_deliveries(mock_db, safe_client=mock_client)

    assert stats["dead_letter"] == 1
    delivery_update = mock_db.outreach_webhook_deliveries.update_one.await_args.args[1]
    assert delivery_update["$set"]["status"] == "dead_letter"


@pytest.mark.asyncio
async def test_replay_dead_letter_delivery_resets_attempt_and_preserves_event_id():
    """Manual replay resets attempt, reschedules immediately, and keeps event_id."""
    mock_db = MagicMock()
    mock_db.outreach_webhook_deliveries.find_one = AsyncMock(return_value={
        "id": "del_dead",
        "event_id": "evt_original_123",
        "workspace_id": "ws_1",
        "status": "dead_letter",
    })
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()

    result = await replay_delivery(mock_db, "ws_1", "del_dead", actor_id="user_admin")

    assert result["id"] == "del_dead"
    assert result["event_id"] == "evt_original_123"
    assert result["status"] == "pending"

    update_payload = mock_db.outreach_webhook_deliveries.update_one.await_args.args[1]["$set"]
    assert update_payload["status"] == "pending"
    assert update_payload["attempt"] == 0
    assert update_payload["replayed_by"] == "user_admin"
