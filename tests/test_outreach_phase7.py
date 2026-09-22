"""
Automated test suite for Phase 7: Multi-Account Unified Inbox & Conversation Synchronization Engine.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from outreach.core.crypto import encrypt_secret
from outreach.engine.inbox_sync import InboxSynchronizer
from outreach.engine.voyager_client import VoyagerClient
from outreach.api.inbox import (
    list_inbox_threads,
    get_thread,
    send_thread_reply,
    trigger_inbox_sync,
    update_thread_intent,
    ReplyRequest,
    UpdateIntentRequest,
)


@pytest.mark.asyncio
async def test_voyager_fetch_and_reply_methods():
    """Verify VoyagerClient conversation fetching and thread reply dispatching."""
    enc_cookie = encrypt_secret("li_at=mock_session_123")
    client = VoyagerClient(session_cookie_enc=enc_cookie)
    assert client.is_mock is True

    # Fetch conversations
    convs = await client.fetch_conversations()
    assert len(convs) >= 1
    assert "lead_name" in convs[0]
    assert convs[0]["lead_name"] == "Jordan Davis"

    # Send conversation reply
    reply_res = await client.send_conversation_reply(
        thread_urn=convs[0]["lead_urn"],
        message_body="Awesome, looking forward to speaking!",
    )
    assert reply_res["status"] == "sent"


@pytest.mark.asyncio
async def test_inbox_synchronizer_thread_indexing_and_lead_reply_detection():
    """Verify InboxSynchronizer pulls threads into DB and marks lead as REPLIED in CRM."""
    mock_db = AsyncMock()

    # Mock account
    enc_cookie = encrypt_secret("li_at=test_cookie")
    mock_account = {
        "id": "acc_sender_1",
        "workspace_id": "ws_123",
        "name": "Sarah Miller",
        "encrypted_session_cookie": enc_cookie,
    }
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=mock_account)
    mock_db.outreach_accounts.find = lambda q: AsyncMock(to_list=AsyncMock(return_value=[mock_account]))

    # Mock existing threads in DB (none initially)
    mock_db.outreach_inbox_threads.find_one = AsyncMock(return_value=None)
    mock_db.outreach_inbox_threads.insert_one = AsyncMock()

    # Mock lead update
    lead_update_res = AsyncMock()
    lead_update_res.modified_count = 1
    mock_db.outreach_leads.update_many = AsyncMock(return_value=lead_update_res)

    syncer = InboxSynchronizer(db=mock_db, workspace_id="ws_123")
    res = await syncer.sync_account_inbox("acc_sender_1")

    assert res["account_id"] == "acc_sender_1"
    assert res["synced_threads"] >= 1
    assert res["new_replies_detected"] == 1
    mock_db.outreach_inbox_threads.insert_one.assert_called_once()
    mock_db.outreach_leads.update_many.assert_called_once()


@pytest.mark.asyncio
async def test_inbox_api_list_and_thread_detail():
    """Verify listing inbox threads and fetching full thread with unread reset."""
    mock_db = AsyncMock()
    sample_thread = {
        "id": "thr_999",
        "workspace_id": "ws_123",
        "account_id": "acc_sender_1",
        "lead_name": "Jordan Davis",
        "lead_headline": "Head of Growth",
        "last_message_snippet": "Let's talk soon!",
        "last_message_at": datetime.now(timezone.utc),
        "unread_count": 2,
        "intent_tag": "interested",
        "messages": [
            {"sender_type": "user", "sender_name": "You", "body": "Hey Jordan!"},
            {"sender_type": "lead", "sender_name": "Jordan Davis", "body": "Let's talk soon!"},
        ],
    }

    mock_db.outreach_inbox_threads.find = lambda q: AsyncMock(
        sort=lambda f, d: AsyncMock(to_list=AsyncMock(return_value=[sample_thread]))
    )
    mock_db.outreach_inbox_threads.find_one = AsyncMock(return_value=sample_thread)
    mock_db.outreach_inbox_threads.update_one = AsyncMock()

    user = {"user_id": "ws_123"}

    # Test list
    threads = await list_inbox_threads(
        account_id=None,
        search=None,
        intent=None,
        current_user=user,
        db=mock_db,
    )
    assert len(threads) == 1
    assert threads[0]["lead_name"] == "Jordan Davis"

    # Test get thread
    detail = await get_thread(thread_id="thr_999", current_user=user, db=mock_db)
    assert detail["id"] == "thr_999"
    assert detail["unread_count"] == 0
    mock_db.outreach_inbox_threads.update_one.assert_called_with(
        {"id": "thr_999"},
        {"$set": {"unread_count": 0}},
    )


@pytest.mark.asyncio
async def test_inbox_api_send_reply_and_update_intent():
    """Verify sending direct reply to lead from assigned account and updating intent."""
    mock_db = AsyncMock()
    enc_cookie = encrypt_secret("li_at=test_cookie")

    sample_thread = {
        "id": "thr_999",
        "workspace_id": "ws_123",
        "account_id": "acc_sender_1",
        "lead_name": "Jordan Davis",
        "lead_urn": "urn:li:fsd_profile:ACoAA12345",
        "messages": [],
    }
    sample_account = {
        "id": "acc_sender_1",
        "workspace_id": "ws_123",
        "name": "Sarah Miller",
        "encrypted_session_cookie": enc_cookie,
    }

    mock_db.outreach_inbox_threads.find_one = AsyncMock(return_value=sample_thread)
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=sample_account)
    mock_db.outreach_inbox_threads.update_one = AsyncMock(return_value=AsyncMock(matched_count=1))

    user = {"user_id": "ws_123"}

    # Send reply
    reply_res = await send_thread_reply(
        thread_id="thr_999",
        req=ReplyRequest(body="Perfect, sending over an invite now!"),
        current_user=user,
        db=mock_db,
    )
    assert reply_res["status"] == "sent"
    assert reply_res["message"]["body"] == "Perfect, sending over an invite now!"
    assert reply_res["message"]["sender_name"] == "Sarah Miller"

    # Update intent
    intent_res = await update_thread_intent(
        thread_id="thr_999",
        req=UpdateIntentRequest(intent_tag="interested"),
        current_user=user,
        db=mock_db,
    )
    assert intent_res["status"] == "updated"
    assert intent_res["intent_tag"] == "interested"
