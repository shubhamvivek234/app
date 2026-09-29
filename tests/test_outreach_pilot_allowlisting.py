"""
Comprehensive tests for Outreach Mailbox & Integrations Workspace Pilot Allowlisting.
Verifies fail-closed gates across API routes, campaign preflight, and background workers.
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from outreach.core.mailbox_connection import (
    is_mailbox_pilot_allowed,
    is_email_send_pilot_allowed,
)
from outreach.core.integrations_pilot import (
    is_integrations_pilot_allowed,
    integrations_enabled,
)
from outreach.api.mailboxes import list_mailboxes, authorize_mailbox, AuthorizeMailboxRequest
from outreach.core.mailbox_sync import bootstrap_mailbox_sync, sync_mailbox_replies
from outreach.api.campaigns import get_campaign_preflight
from outreach.api.integrations import (
    create_webhook,
    CreateWebhookRequest,
    authenticate_api_key,
    require_api_key_scope,
)
from outreach.core.event_outbox import scan_and_fanout_outbox
from outreach.core.webhook_delivery import dispatch_due_deliveries


# ── 1. Mailbox Allowlist Unit Tests ──────────────────────────────────────────

def test_mailbox_allowlist_matching(monkeypatch):
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "ws_pilot_1, ws_pilot_2")

    assert is_mailbox_pilot_allowed("ws_pilot_1") is True
    assert is_mailbox_pilot_allowed("ws_pilot_2") is True
    assert is_mailbox_pilot_allowed("ws_other") is False
    assert is_mailbox_pilot_allowed("") is False
    assert is_mailbox_pilot_allowed(None) is False

    assert is_email_send_pilot_allowed("ws_pilot_1") is True
    assert is_email_send_pilot_allowed("ws_other") is False

    # Wildcard allowlist
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "*")
    assert is_mailbox_pilot_allowed("ws_any") is True

    # Global disable overrides allowlist
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "false")
    assert is_mailbox_pilot_allowed("ws_pilot_1") is False


@pytest.mark.asyncio
async def test_list_mailboxes_reports_pilot_enabled_state(monkeypatch):
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_mailboxes.find.return_value = cursor

    # Pilot workspace
    res_pilot = await list_mailboxes(current_user={"default_workspace_id": "ws_pilot"}, db=db)
    assert res_pilot["connection_enabled"] is True
    assert res_pilot["send_enabled"] is True
    assert res_pilot["sync_enabled"] is True

    # Non-pilot workspace
    res_other = await list_mailboxes(current_user={"default_workspace_id": "ws_other"}, db=db)
    assert res_other["connection_enabled"] is False
    assert res_other["send_enabled"] is False
    assert res_other["sync_enabled"] is False


@pytest.mark.asyncio
async def test_authorize_mailbox_blocks_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    req = AuthorizeMailboxRequest(sender_account_id="acc_1")
    resp = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await authorize_mailbox(
            provider="gmail",
            request=req,
            response=resp,
            current_user={"default_workspace_id": "ws_non_pilot", "user_id": "usr_1"},
            db=db,
        )
    assert exc.value.status_code == 503
    assert "not enabled for this workspace in the current pilot" in exc.value.detail


@pytest.mark.asyncio
async def test_mailbox_sync_worker_skips_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    db.outreach_mailboxes.update_one = AsyncMock()

    res = await bootstrap_mailbox_sync(db, workspace_id="ws_non_pilot", sender_account_id="acc_1")
    assert res["status"] == "disabled"

    res_sync = await sync_mailbox_replies(db, workspace_id="ws_non_pilot", sender_account_id="acc_1")
    assert res_sync["status"] == "unavailable"


@pytest.mark.asyncio
async def test_campaign_preflight_blocks_email_step_for_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    # Entitlement active
    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "status": "active", "seats": 1, "paid_through": "2029-01-01T00:00:00Z",
    })
    # Campaign with email sequence
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_1",
        "workspace_id": "ws_non_pilot",
        "sender_account_ids": ["acc_1"],
        "schedule": {"working_hours": {"start": "09:00", "end": "18:00"}, "days_of_week": [1, 2, 3, 4, 5]},
    })
    db.outreach_sequences.find_one = AsyncMock(return_value={
        "campaign_id": "camp_1",
        "nodes": [
            {"id": "n1", "type": "visit_profile", "config": {}},
            {"id": "n2", "type": "send_email", "config": {"subject": "Hi", "body": "Hello"}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })
    cursor_acc = MagicMock()
    cursor_acc.to_list = AsyncMock(return_value=[{
        "id": "acc_1", "status": "active", "proxy": {"host": "10.0.0.1"},
    }])
    db.outreach_accounts.find.return_value = cursor_acc
    db.outreach_leads.count_documents = AsyncMock(return_value=5)

    user = {"default_workspace_id": "ws_non_pilot", "user_id": "usr_1"}
    res = await get_campaign_preflight("camp_1", current_user=user, db=db)

    mailbox_check = next((c for c in res["checklist"] if c["id"] == "mailboxes"), None)
    assert mailbox_check is not None
    assert mailbox_check["passed"] is False
    assert "not enabled for this workspace in the current pilot" in mailbox_check["message"]
    assert any("Email sequence steps are not enabled" in b for b in res["blockers"])


# ── 2. Integrations Allowlist Unit Tests ──────────────────────────────────────

def test_integrations_allowlist_matching(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "ws_alpha, ws_beta")

    assert is_integrations_pilot_allowed("ws_alpha") is True
    assert is_integrations_pilot_allowed("ws_beta") is True
    assert is_integrations_pilot_allowed("ws_gamma") is False

    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "false")
    assert is_integrations_pilot_allowed("ws_alpha") is False


@pytest.mark.asyncio
async def test_create_webhook_blocks_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    user = {"default_workspace_id": "ws_non_pilot", "user_id": "usr_1"}

    with pytest.raises(HTTPException) as exc:
        await create_webhook(
            CreateWebhookRequest(target_url="https://example.com/webhook"),
            current_user=user,
            db=db,
        )
    assert exc.value.status_code == 503
    assert "Integrations are not enabled for this workspace in the current pilot" in exc.value.detail


@pytest.mark.asyncio
async def test_api_key_auth_blocks_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    db.outreach_api_keys.find_one = AsyncMock(return_value={
        "_id": "k1",
        "workspace_id": "ws_non_pilot",
        "scopes": ["leads:read"],
    })

    with pytest.raises(HTTPException) as exc:
        await authenticate_api_key(
            authorization="Bearer unr_live_abcdef1234567890abcdef1234567890",
            db=db,
        )
    assert exc.value.status_code == 503
    assert "Integrations are not enabled for this workspace in the current pilot" in exc.value.detail


@pytest.mark.asyncio
async def test_outbox_fanout_suppresses_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    db.outreach_event_outbox.find_one_and_update = AsyncMock(side_effect=[
        {
            "_id": "doc_1",
            "id": "evt_1",
            "workspace_id": "ws_non_pilot",
            "type": "lead.replied",
            "payload": {},
        },
        None,
    ])
    db.outreach_event_outbox.update_one = AsyncMock()

    res = await scan_and_fanout_outbox(db, batch_size=1)
    db.outreach_event_outbox.update_one.assert_awaited_once()
    call_args = db.outreach_event_outbox.update_one.call_args[0]
    assert call_args[1]["$set"]["status"] == "suppressed"
    assert "Integrations not enabled for workspace in current pilot" in call_args[1]["$set"]["suppressed_reason"]


@pytest.mark.asyncio
async def test_webhook_delivery_cancels_non_pilot_workspace(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "ws_pilot")

    db = MagicMock()
    db.outreach_webhook_deliveries.find_one_and_update = AsyncMock(side_effect=[
        {
            "id": "del_1",
            "event_id": "evt_1",
            "workspace_id": "ws_non_pilot",
            "target_url": "https://example.com/hook",
            "attempt": 0,
        },
        None,
    ])
    db.outreach_webhook_deliveries.update_one = AsyncMock()

    mock_client = AsyncMock()
    await dispatch_due_deliveries(db, batch_size=1, safe_client=mock_client)
    db.outreach_webhook_deliveries.update_one.assert_awaited_once()
    call_args = db.outreach_webhook_deliveries.update_one.call_args[0]
    assert call_args[1]["$set"]["status"] == "cancelled"
    assert "Integrations not enabled for workspace in current pilot" in call_args[1]["$set"]["last_error"]
