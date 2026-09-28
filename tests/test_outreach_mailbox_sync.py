"""Inbound email attribution must not invent a verified response."""
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from outreach.core.mailbox_sync import (
    _apply_inbound, _dsn_failed_recipient, _gmail_dsn_recipient, _gmail_messages,
    _graph_messages, _mark_inbound,
    bootstrap_mailbox_sync, sync_mailbox_replies,
)


def test_delivery_status_part_identifies_bounced_recipient_not_body_text():
    raw = (b'MIME-Version: 1.0\r\nContent-Type: multipart/report; report-type=delivery-status; boundary="dsn"\r\n'
           b'\r\n--dsn\r\nContent-Type: text/plain\r\n\r\nDelivery failed.\r\n'
           b'--dsn\r\nContent-Type: message/delivery-status\r\n\r\n'
           b'Final-Recipient: rfc822; lead@example.com\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n--dsn--\r\n')
    assert _dsn_failed_recipient(raw) == "lead@example.com"
    assert _dsn_failed_recipient(b"From: postmaster@example.com\r\n\r\nFinal-Recipient: rfc822; fake@example.com") is None


@pytest.mark.asyncio
async def test_unreferenced_inbound_pauses_without_counting_a_reply():
    db = MagicMock()
    db.outreach_email_inbound_events.find_one = AsyncMock(return_value=None)
    db.outreach_email_inbound_events.update_one = AsyncMock()
    db.outreach_email_operations.find_one = AsyncMock(return_value={
        "_id": "operation", "lead_id": "lead", "campaign_id": "campaign",
        "message_id": "<outbound@example.com>",
    })
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_campaigns.update_one = AsyncMock()
    mailbox = {"workspace_id": "ws", "sender_account_id": "sender", "email": "sender@example.com"}
    message = {"id": "provider-id", "from": "lead@example.com"}
    with patch("outreach.core.mailbox_sync.suppress_email", new_callable=AsyncMock):
        result = await _apply_inbound(
            db, mailbox, "provider-id", "lead@example.com",
            datetime.now(timezone.utc) + timedelta(seconds=1), message, kind="reply",
        )
    updates = db.outreach_leads.update_one.await_args.args[1]["$set"]
    assert result["status"] == "possible_reply"
    assert updates["execution_state"] == "waiting_trigger"
    assert "has_replied" not in updates
    assert "email_opted_out" not in updates
    db.outreach_campaigns.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_reference_confirms_reply_without_claiming_opt_out():
    db = MagicMock()
    db.outreach_email_inbound_events.find_one = AsyncMock(return_value=None)
    db.outreach_email_inbound_events.update_one = AsyncMock()
    db.outreach_email_operations.find_one = AsyncMock(return_value={
        "_id": "operation", "lead_id": "lead", "campaign_id": "campaign",
        "message_id": "<outbound@example.com>",
    })
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_campaigns.update_one = AsyncMock()
    mailbox = {"workspace_id": "ws", "sender_account_id": "sender", "email": "sender@example.com"}
    message = {"id": "provider-id", "from": "lead@example.com", "in_reply_to": "<outbound@example.com>"}
    with patch("outreach.core.mailbox_sync.suppress_email", new_callable=AsyncMock):
        result = await _apply_inbound(
            db, mailbox, "provider-id", "lead@example.com",
            datetime.now(timezone.utc) + timedelta(seconds=1), message, kind="reply",
        )
    updates = db.outreach_leads.update_one.await_args.args[1]["$set"]
    assert result["status"] == "reply"
    assert updates["has_replied"] is True
    assert "email_opted_out" not in updates
    db.outreach_campaigns.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_alias_reply_matches_original_message_reference_before_sender_address():
    db = MagicMock()
    db.outreach_email_inbound_events.find_one = AsyncMock(return_value=None)
    db.outreach_email_inbound_events.update_one = AsyncMock()
    db.outreach_email_operations.find_one = AsyncMock(return_value={
        "_id": "operation", "lead_id": "lead", "campaign_id": "campaign",
        "recipient": "lead@example.com", "message_id": "<outbound@example.com>",
    })
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_campaigns.update_one = AsyncMock()
    mailbox = {"workspace_id": "ws", "sender_account_id": "sender", "email": "sender@example.com"}
    message = {"id": "alias-message", "from": "alias@example.net", "in_reply_to": "<outbound@example.com>"}
    with patch("outreach.core.mailbox_sync.suppress_email", new_callable=AsyncMock) as suppress:
        result = await _apply_inbound(
            db, mailbox, "alias-message", "alias@example.net",
            datetime.now(timezone.utc) + timedelta(seconds=1), message, kind="reply",
        )
    assert result["status"] == "reply"
    assert db.outreach_email_operations.find_one.await_args_list[0].args[0]["message_id"] == {"$in": ["<outbound@example.com>"]}
    assert suppress.await_args.kwargs["email"] == "lead@example.com"


@pytest.mark.asyncio
async def test_old_sync_cannot_mark_reconnected_mailbox_healthy(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    mailbox = {
        "workspace_id": "ws", "sender_account_id": "sender", "status": "active",
        "provider": "gmail", "history_id": "old-100", "connection_job_id": "old-job",
        "sync_status": "healthy", "email": "sender@example.com",
    }
    db.outreach_mailboxes.find_one = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(side_effect=[
        MagicMock(modified_count=1),  # old cycle takes the lease
        MagicMock(modified_count=0),  # new connection rejects old cursor update
        MagicMock(modified_count=0),  # cannot mark new connection stale
        MagicMock(modified_count=1),  # release only old lease owner
    ])
    with patch("outreach.core.mailbox_sync._paid_sender", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.mailbox_sync.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access"), \
         patch("outreach.core.mailbox_sync._gmail_messages", new_callable=AsyncMock,
               return_value=([], "new-101")):
        result = await sync_mailbox_replies(db, workspace_id="ws", sender_account_id="sender")
    assert result == {"status": "stale"}
    final_query = db.outreach_mailboxes.update_one.await_args_list[1].args[0]
    assert final_query["connection_job_id"] == "old-job"
    assert final_query["history_id"] == "old-100"


@pytest.mark.asyncio
async def test_gmail_history_reads_only_new_inbound_message_metadata():
    received = datetime(2026, 9, 28, tzinfo=timezone.utc)
    calls = []

    async def provider_get(url, token, *, params=None):
        calls.append((url, params))
        if url.endswith("/history"):
            return httpx.Response(200, json={
                "history": [{"messagesAdded": [{"message": {"id": "message-1"}}]}],
                "historyId": "102",
            })
        return httpx.Response(200, json={
            "id": "message-1", "threadId": "thread-1", "internalDate": str(int(received.timestamp() * 1000)),
            "labelIds": ["INBOX"], "payload": {"headers": [
                {"name": "From", "value": "Lead <lead@example.com>"},
                {"name": "In-Reply-To", "value": "<outbound@mail.unravler.com>"},
            ]},
        })

    with patch("outreach.core.mailbox_sync._provider_get", new_callable=AsyncMock,
               side_effect=provider_get):
        messages, cursor = await _gmail_messages({"history_id": "100"}, "access")
    assert cursor == "102"
    assert messages == [{
        "id": "message-1", "thread_id": "thread-1", "from": "lead@example.com",
        "received_at": received, "references": None,
        "in_reply_to": "<outbound@mail.unravler.com>", "failed_recipient": None,
    }]
    assert calls[0][1]["startHistoryId"] == "100"
    assert calls[1][1]["format"] == "metadata"


@pytest.mark.asyncio
async def test_microsoft_delta_requires_complete_link_and_maps_reply_headers():
    link = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=next"
    response = httpx.Response(200, json={
        "value": [{
            "id": "graph-message", "from": {"emailAddress": {"address": "Alias@Example.com"}},
            "receivedDateTime": "2026-09-28T08:00:00Z",
            "internetMessageHeaders": [{"name": "In-Reply-To", "value": "<outbound@mail.unravler.com>"}],
        }], "@odata.deltaLink": link,
    })
    with patch("outreach.core.mailbox_sync._provider_get", new_callable=AsyncMock,
               return_value=response) as provider_get:
        messages, cursor = await _graph_messages({"delta_url": link}, "access")
    assert cursor == link
    assert messages[0]["from"] == "alias@example.com"
    assert messages[0]["in_reply_to"] == "<outbound@mail.unravler.com>"
    provider_get.assert_awaited_once_with(link, "access")


@pytest.mark.asyncio
async def test_gmail_bootstrap_persists_cursor_only_for_same_connection(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    mailbox = {
        "workspace_id": "ws", "sender_account_id": "sender", "status": "active",
        "provider": "gmail", "connection_job_id": "job-1", "history_id": None,
    }
    db.outreach_mailboxes.find_one = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("outreach.core.mailbox_sync._paid_sender", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.mailbox_sync.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access"), \
         patch("outreach.core.mailbox_sync._provider_get", new_callable=AsyncMock,
               return_value=httpx.Response(200, json={"historyId": "123"})):
        result = await bootstrap_mailbox_sync(db, "ws", "sender")
    assert result == {"status": "healthy"}
    query, update = db.outreach_mailboxes.update_one.await_args.args
    assert query["connection_job_id"] == "job-1"
    assert query["history_id"] is None
    assert update["$set"]["history_id"] == "123"


@pytest.mark.asyncio
async def test_completed_gmail_sync_advances_cursor_and_counts_confirmed_reply(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    mailbox = {
        "workspace_id": "ws", "sender_account_id": "sender", "status": "active",
        "provider": "gmail", "connection_job_id": "job-1", "history_id": "100",
        "sync_status": "healthy", "email": "sender@example.com",
    }
    db.outreach_mailboxes.find_one = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("outreach.core.mailbox_sync._paid_sender", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.mailbox_sync.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access"), \
         patch("outreach.core.mailbox_sync._gmail_messages", new_callable=AsyncMock,
               return_value=([{"id": "reply-1", "from": "lead@example.com"}], "101")), \
         patch("outreach.core.mailbox_sync._mark_inbound", new_callable=AsyncMock,
               return_value={"status": "reply"}):
        result = await sync_mailbox_replies(db, workspace_id="ws", sender_account_id="sender")
    assert result == {"status": "healthy", "replies": 1, "bounces": 0}
    final_update = db.outreach_mailboxes.update_one.await_args_list[1].args[1]["$set"]
    assert final_update["history_id"] == "101"
    assert final_update["sync_status"] == "healthy"


@pytest.mark.asyncio
async def test_microsoft_bootstrap_obtains_a_complete_inbox_delta(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    mailbox = {"workspace_id": "ws", "sender_account_id": "sender", "status": "active",
               "provider": "microsoft", "connection_job_id": "job-graph", "delta_url": None}
    db.outreach_mailboxes.find_one = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    delta = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=complete"
    with patch("outreach.core.mailbox_sync._paid_sender", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.mailbox_sync.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access"), \
         patch("outreach.core.mailbox_sync._provider_get", new_callable=AsyncMock,
               return_value=httpx.Response(200, json={"value": [], "@odata.deltaLink": delta})) as get:
        result = await bootstrap_mailbox_sync(db, "ws", "sender")
    assert result == {"status": "healthy"}
    assert get.await_args.args[0].endswith("/mailFolders/inbox/messages/delta")
    assert get.await_args.kwargs["params"]["changeType"] == "created"
    assert db.outreach_mailboxes.update_one.await_args.args[1]["$set"]["delta_url"] == delta


@pytest.mark.asyncio
async def test_structured_gmail_delivery_report_is_loaded_from_raw_message():
    raw = (b'MIME-Version: 1.0\r\nContent-Type: multipart/report; report-type=delivery-status; boundary="dsn"\r\n'
           b'\r\n--dsn\r\nContent-Type: message/delivery-status\r\n\r\n'
           b'Final-Recipient: rfc822; lead@example.com\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n--dsn--\r\n')
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    with patch("outreach.core.mailbox_sync._provider_get", new_callable=AsyncMock,
               return_value=httpx.Response(200, json={"raw": encoded})) as get:
        recipient = await _gmail_dsn_recipient("provider-id", "access")
    assert recipient == "lead@example.com"
    assert get.await_args.kwargs["params"] == {"format": "raw"}


@pytest.mark.asyncio
async def test_bounce_stops_and_suppresses_only_matching_post_send_lead():
    db = MagicMock()
    db.outreach_email_inbound_events.find_one = AsyncMock(return_value=None)
    db.outreach_email_inbound_events.update_one = AsyncMock()
    db.outreach_email_operations.find_one = AsyncMock(return_value={
        "_id": "operation", "lead_id": "lead", "campaign_id": "campaign",
        "recipient": "lead@example.com", "message_id": "<outbound@example.com>",
    })
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mailbox = {"workspace_id": "ws", "sender_account_id": "sender", "email": "sender@example.com"}
    with patch("outreach.core.mailbox_sync.suppress_email", new_callable=AsyncMock) as suppress:
        result = await _mark_inbound(db, mailbox, {
            "id": "bounce-id", "from": "mailer-daemon@provider.example",
            "failed_recipient": "lead@example.com",
            "received_at": datetime.now(timezone.utc),
        })
    assert result["status"] == "bounce"
    assert suppress.await_args.kwargs["email"] == "lead@example.com"
    assert db.outreach_leads.update_one.await_args.args[1]["$set"]["execution_state"] == "bounced"
