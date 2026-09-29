"""
Comprehensive tests for Outreach Integrations:
Slice 3 (Slack Pilot), Slice 4 (Zapier/Make REST Hooks), and Slice 5 (HubSpot & Google Sheets).
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from outreach.core.crm_sync import (
    FORMULA_INJECTION_PREFIXES,
    sanitize_spreadsheet_value,
    sanitize_row_data,
    sync_lead_to_hubspot,
)
from outreach.core.event_definitions import WebhookEvent
from outreach.core.event_outbox import record_outbox_event, scan_and_fanout_outbox
from outreach.core.slack_notifier import (
    format_slack_event_card,
    format_slack_test_card,
    send_slack_notification,
    validate_slack_webhook_url,
)
from outreach.core.webhook_delivery import dispatch_due_deliveries


# ── Slice 3: Slack Pilot Tests ─────────────────────────────────────────────

def test_slack_webhook_url_validation_valid():
    """Valid Slack incoming webhook URLs pass validation."""
    valid_url = "https://hooks.slack.com/services/T012AB34C5D/B098ZY76X5W/dummy-test-token-placeholder"
    assert validate_slack_webhook_url(valid_url) == valid_url

    gov_url = "https://hooks.gov-slack.com/services/T012AB34C5D/B098ZY76X5W/dummy-gov-token"
    assert validate_slack_webhook_url(gov_url) == gov_url


def test_slack_webhook_url_validation_invalid_domains_and_schemes():
    """Non-HTTPS or unapproved domains must fail-closed."""
    with pytest.raises(ValueError, match="HTTPS"):
        validate_slack_webhook_url("http://hooks.slack.com/services/T1/B2/token")

    with pytest.raises(ValueError, match="hooks.slack.com"):
        validate_slack_webhook_url("https://malicious-site.com/services/T1/B2/token")

    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_slack_webhook_url("https://user:pass@hooks.slack.com/services/T1/B2/token")

    with pytest.raises(ValueError, match="query parameters"):
        validate_slack_webhook_url("https://hooks.slack.com/services/T1/B2/token?foo=bar")

    with pytest.raises(ValueError, match="missing expected"):
        validate_slack_webhook_url("https://hooks.slack.com/services/short")


def test_format_slack_event_card_blocks_and_no_body_leak():
    """Block Kit payload must contain event info but never leak private body text."""
    payload = {
        "id": "evt_998877",
        "type": "lead.replied",
        "version": 1,
        "occurred_at": "2026-09-29T12:00:00Z",
        "workspace_id": "ws_123",
        "data": {
            "lead_id": "lead_abc",
            "campaign_id": "camp_xyz",
            "channel": "linkedin",
            "linkedin_url": "https://www.linkedin.com/in/test-prospect",
            "private_message_body": "This secret message should NEVER appear in Slack",
        },
    }

    card = format_slack_event_card(payload)
    assert "Prospect Replied" in card["text"]
    assert len(card["blocks"]) >= 3

    # Ensure private message body is NOT in any block text
    card_str = str(card)
    assert "This secret message should NEVER appear in Slack" not in card_str
    assert "lead_abc" in card_str
    assert "camp_xyz" in card_str
    assert "https://www.linkedin.com/in/test-prospect" in card_str


def test_format_slack_test_card():
    """Test ping card formats correctly."""
    card = format_slack_test_card()
    assert "Unravler Outreach Connected" in card["blocks"][0]["text"]["text"]
    assert "DNS-pinned transport" in str(card)


@pytest.mark.asyncio
async def test_slack_fanout_and_delivery_end_to_end():
    """Event outbox fans out to connected Slack integration and delivery engine delivers it."""
    outbox_docs = []
    deliveries = []
    integrations = [{
        "workspace_id": "ws_test",
        "provider": "slack",
        "status": "connected",
        "access_token_enc": "enc_slack_url",
        "metadata": {
            "notify_on_replies": True,
            "notify_on_accepts": True,
        },
    }]

    mock_db = MagicMock()

    # Outbox find_one_and_update
    event_doc = {
        "id": "evt_replied_01",
        "workspace_id": "ws_test",
        "type": "lead.replied",
        "status": "pending",
        "payload": {
            "id": "evt_replied_01",
            "type": "lead.replied",
            "data": {"lead_id": "lead_123", "campaign_id": "camp_456", "channel": "linkedin"},
        },
    }

    call_count = 0
    async def mock_find_one_and_update_outbox(q, u, **kwargs):
        nonlocal call_count
        if call_count == 0:
            call_count += 1
            return event_doc
        return None

    mock_db.outreach_event_outbox.find_one_and_update = mock_find_one_and_update_outbox
    mock_db.outreach_event_outbox.update_one = AsyncMock()

    # Webhooks cursor returns empty list (no standard webhooks)
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.outreach_webhooks.find.return_value = mock_cursor

    # Integrations find_one returns slack integration
    async def mock_find_integration(q, **kwargs):
        if q.get("provider") == "slack" and q.get("status") == "connected":
            return integrations[0]
        return None

    mock_db.outreach_integrations.find_one = mock_find_integration
    mock_db.outreach_integrations.update_one = AsyncMock()

    # Deliveries insert
    async def mock_insert_delivery(doc, **kwargs):
        deliveries.append(doc)
    mock_db.outreach_webhook_deliveries.insert_one = mock_insert_delivery

    # 1. Fan-out
    res = await scan_and_fanout_outbox(mock_db, batch_size=1)
    assert len(deliveries) == 1
    slack_delivery = deliveries[0]
    assert slack_delivery["destination_id"] == "slack"
    assert slack_delivery["destination_type"] == "slack"

    # 2. Dispatch delivery via mock safe client
    delivery_call_count = 0
    async def mock_delivery_claim(q, u, **kwargs):
        nonlocal delivery_call_count
        if delivery_call_count == 0:
            delivery_call_count += 1
            return slack_delivery
        return None

    mock_db.outreach_webhook_deliveries.find_one_and_update = mock_delivery_claim
    mock_db.outreach_webhook_deliveries.update_one = AsyncMock()

    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=200, text="ok")
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("outreach.core.webhook_delivery.decrypt_secret", return_value="https://hooks.slack.com/services/T1/B2/token"):
        dispatch_res = await dispatch_due_deliveries(mock_db, batch_size=1, safe_client=mock_client)

    assert dispatch_res["delivered"] == 1
    mock_client.post.assert_called_once()
    posted_call = mock_client.post.call_args
    assert posted_call[0][0] == "https://hooks.slack.com/services/T1/B2/token"
    # Verify Block Kit was sent
    import json
    body_sent = json.loads(posted_call[1]["content"].decode("utf-8"))
    assert "blocks" in body_sent
    assert mock_db.outreach_integrations.update_one.called


# ── Slice 4: Automation Private Pilot (Zapier/Make REST Hooks) Tests ───────

@pytest.mark.asyncio
async def test_rest_hook_subscribe_and_unsubscribe():
    """REST hook subscribe creates an active webhook with source='rest_hook' and unsubscribe removes it."""
    from outreach.api.integrations import public_subscribe_hook, public_unsubscribe_hook, SubscribeRestHookRequest

    webhooks_store = {}
    mock_db = MagicMock()
    mock_db.outreach_webhooks.count_documents = AsyncMock(return_value=0)

    async def mock_insert_wh(doc):
        webhooks_store[doc["id"]] = doc
    mock_db.outreach_webhooks.insert_one = mock_insert_wh

    async def mock_delete_wh(q):
        hook_id = q.get("id")
        if hook_id in webhooks_store:
            del webhooks_store[hook_id]
            res = MagicMock()
            res.deleted_count = 1
            return res
        res = MagicMock()
        res.deleted_count = 0
        return res
    mock_db.outreach_webhooks.delete_one = mock_delete_wh

    req = SubscribeRestHookRequest(
        event="lead.replied",
        target_url="https://hooks.zapier.com/hooks/catch/12345/abcdef/",
    )

    auth = {"workspace_id": "ws_pilot_01", "scopes": ["leads:read"]}

    with patch("outreach.api.integrations.validate_webhook_url", return_value=req.target_url), \
         patch("outreach.api.integrations.encrypt_secret", return_value="enc_secret_mock"):
        sub_resp = await public_subscribe_hook(req, auth=auth, db=mock_db)

    assert "id" in sub_resp
    assert sub_resp["event"] == "lead.replied"
    assert sub_resp["id"] in webhooks_store
    assert webhooks_store[sub_resp["id"]]["source"] == "rest_hook"

    # Unsubscribe
    unsub_resp = await public_unsubscribe_hook(sub_resp["id"], auth=auth, db=mock_db)
    assert unsub_resp["status"] == "unsubscribed"
    assert sub_resp["id"] not in webhooks_store


@pytest.mark.asyncio
async def test_rest_hook_sample_endpoint():
    """GET /public/hooks/sample returns compliant schema for supported events."""
    from outreach.api.integrations import public_hook_sample

    auth = {"workspace_id": "ws_sample_test", "scopes": ["leads:read"]}
    sample_replied = await public_hook_sample(event="lead.replied", auth=auth)
    assert sample_replied["type"] == "lead.replied"
    assert sample_replied["workspace_id"] == "ws_sample_test"
    assert "lead_id" in sample_replied["data"]
    assert "channel" in sample_replied["data"]


# ── Slice 5: CRM & Google Sheets Tests ─────────────────────────────────────

def test_formula_injection_defense():
    """Neutralize dangerous formula triggers (=, +, -, @, \\t, \\r)."""
    assert sanitize_spreadsheet_value("=1+1") == "'=1+1"
    assert sanitize_spreadsheet_value("+SUM(A1:A10)") == "'+SUM(A1:A10)"
    assert sanitize_spreadsheet_value("-100") == "'-100"
    assert sanitize_spreadsheet_value("@SUM") == "'@SUM"
    assert sanitize_spreadsheet_value("\tcmd|' /C calc'!A0") == "'cmd|' /C calc'!A0"

    # Safe text remains unchanged
    assert sanitize_spreadsheet_value("Alex Rivera") == "Alex Rivera"
    assert sanitize_spreadsheet_value("alex@company.com") == "alex@company.com"
    assert sanitize_spreadsheet_value("https://linkedin.com/in/alex") == "https://linkedin.com/in/alex"

    row = {
        "name": "=cmd|' /C calc'!A0",
        "email": "normal@domain.com",
        "company": "+Exploit",
    }
    cleaned = sanitize_row_data(row)
    assert cleaned["name"].startswith("'")
    assert cleaned["company"].startswith("'")
    assert cleaned["email"] == "normal@domain.com"


@pytest.mark.asyncio
async def test_hubspot_contact_sync_creates_mapping():
    """HubSpot sync creates contact, maps properties, and saves external mapping record."""
    mock_db = MagicMock()
    mock_lead = {
        "id": "lead_hs_01",
        "workspace_id": "ws_hs",
        "email": "sarah.connor@example.com",
        "first_name": "Sarah",
        "last_name": "Connor",
        "company_name": "Cyberdyne Systems",
        "job_title": "Security Lead",
        "linkedin_url": "https://www.linkedin.com/in/sarah-connor",
        "pipeline_stage": "replied",
    }
    mock_db.outreach_leads.find_one = AsyncMock(return_value=mock_lead)
    mock_db.outreach_external_mappings.find_one = AsyncMock(return_value=None)
    mock_db.outreach_external_mappings.update_one = AsyncMock()

    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": "hs_contact_98765"}
    mock_client.post = AsyncMock(return_value=mock_resp)

    res = await sync_lead_to_hubspot(
        mock_db,
        workspace_id="ws_hs",
        lead_id="lead_hs_01",
        access_token="hs_test_token",
        portal_id="portal_123",
        safe_client=mock_client,
    )

    assert res["status"] == "synced"
    assert res["hubspot_contact_id"] == "hs_contact_98765"
    assert mock_db.outreach_external_mappings.update_one.called
    saved_doc = mock_db.outreach_external_mappings.update_one.call_args[0][1]["$set"]
    assert saved_doc["external_id"] == "hs_contact_98765"
    assert saved_doc["provider"] == "hubspot"
