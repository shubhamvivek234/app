"""Regression coverage for Analytics, Swipe Files, and Inbox safety fixes."""
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.api.analytics import get_outreach_analytics, live_activity_feed
from outreach.api.inbox import ReplyRequest, send_thread_reply, trigger_inbox_sync, get_inbox_job, list_inbox_threads
from outreach.api.swipe import CreateSwipeItemRequest, RepurposeSwipeRequest, list_swipe_items, repurpose_swipe_item
from outreach.engine.inbox_sync import InboxSynchronizer
from outreach.tasks.sequence_executor import SequenceExecutor


USER = {"user_id": "user_a", "default_workspace_id": "workspace_a"}


@pytest.mark.asyncio
async def test_analytics_does_not_turn_manual_pipeline_stages_into_sends():
    db = MagicMock()
    db.outreach_leads.count_documents = AsyncMock(return_value=4)
    db.outreach_tasks.count_documents = AsyncMock(return_value=0)
    db.outreach_engage_posts.count_documents = AsyncMock(return_value=0)
    db.outreach_accounts.count_documents = AsyncMock(return_value=0)
    db.social_accounts.count_documents = AsyncMock(return_value=0)

    result = await get_outreach_analytics(campaign_id="all", timeframe="7d", current_user=USER, db=db)

    assert result["kpis"]["requests"]["sent"] == 0
    assert result["kpis"]["messages"]["sent"] == 0
    assert len(result["daily_chart"]) == 7
    assert all(day["sent"] == day["messages_sent"] == 0 for day in result["daily_chart"])
    task_queries = [call.args[0] for call in db.outreach_tasks.count_documents.call_args_list]
    assert all(query["$and"][0] == {"workspace_id": "workspace_a"} for query in task_queries)


@pytest.mark.asyncio
async def test_analytics_rejects_other_workspace_campaign():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await get_outreach_analytics(campaign_id="other", timeframe="7d", current_user=USER, db=db)
    assert exc.value.status_code == 404
    db.outreach_campaigns.find_one.assert_awaited_with({"id": "other", "workspace_id": "workspace_a"})


@pytest.mark.asyncio
async def test_live_analytics_feed_is_workspace_scoped():
    db = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_tasks.find.return_value = cursor
    response = await live_activity_feed(current_user=USER, db=db)
    stream = response.body_iterator
    await anext(stream)
    await anext(stream)
    query = db.outreach_tasks.find.call_args.args[0]
    assert query["workspace_id"] == "workspace_a"
    assert "$or" not in query
    await stream.aclose()


@pytest.mark.asyncio
async def test_confirmed_sequence_action_is_recorded_once_for_analytics():
    db = MagicMock()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead_a", "workspace_id": "workspace_a", "campaign_id": "campaign_a",
        "linkedin_url": "https://linkedin.com/in/person-a", "assigned_account_id": "account_a",
    })
    db.outreach_campaigns.find_one = AsyncMock(return_value={"id": "campaign_a", "status": "active"})
    db.outreach_accounts.find_one = AsyncMock(return_value={"id": "account_a", "status": "active", "user_id": "user_a"})
    db.outreach_sequences.find_one = AsyncMock(return_value={
        "compiled_dag": {"root_node_ids": ["node_a"], "nodes": {"node_a": {
            "type": "connection_request", "config": {}, "next_default": None,
        }}},
    })
    db.outreach_leads.update_one = AsyncMock()
    db.outreach_tasks.update_one = AsyncMock()
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock, return_value=True), \
         patch("outreach.tasks.sequence_executor.VoyagerClient") as voyager:
        voyager.return_value.send_connection_invite = AsyncMock(return_value={"status": "sent"})
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "success"
    event_query, event_update = db.outreach_tasks.update_one.call_args.args
    assert event_query == {"id": "lead_a:node_a", "workspace_id": "workspace_a"}
    assert event_update["$setOnInsert"]["task_type"] == "connection_request"
    assert db.outreach_tasks.update_one.call_args.kwargs["upsert"] is True


def test_swipe_rejects_blank_copy_and_non_web_links():
    with pytest.raises(ValidationError):
        CreateSwipeItemRequest(content_text="   ")
    with pytest.raises(ValidationError):
        CreateSwipeItemRequest(content_text="A good post", post_url="javascript:alert(1)")


@pytest.mark.asyncio
async def test_swipe_search_is_literal_and_generation_failure_is_visible():
    db = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_swipe_files.find.return_value = cursor
    await list_swipe_items(search="[.*]", current_user=USER, db=db)
    query = db.outreach_swipe_files.find.call_args.args[0]
    assert query["$or"][0]["content_text"]["$regex"] == re.escape("[.*]")

    db.outreach_swipe_files.find_one = AsyncMock(return_value={"content_text": "Sample", "author_name": "A"})
    with patch("outreach.api.swipe.free_llm.generate_text", new_callable=AsyncMock, side_effect=RuntimeError("provider down")):
        with pytest.raises(HTTPException) as exc:
            await repurpose_swipe_item("item_1", RepurposeSwipeRequest(), current_user=USER, db=db)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_inbox_sync_does_not_match_leads_by_name():
    db = MagicMock()
    account = {"id": "account_a", "workspace_id": "workspace_a", "status": "active", "session_cookie_enc": "encrypted"}
    db.outreach_accounts.find_one = AsyncMock(return_value=account)
    db.outreach_inbox_threads.find_one = AsyncMock(return_value=None)
    db.outreach_inbox_threads.insert_one = AsyncMock()
    db.outreach_leads.find_one = AsyncMock(return_value=None)
    db.outreach_leads.update_one = AsyncMock()
    conversation = {
        "thread_urn": "urn:li:fs_conversation:thread1",
        "lead_urn": "urn:li:fsd_profile:member1",
        "lead_name": "Common Name",
        "messages": [{"sender_type": "lead", "body": "Not interested, please remove me"}],
    }
    with patch("outreach.engine.inbox_sync.VoyagerClient") as client:
        client.return_value.fetch_conversations = AsyncMock(return_value=[conversation])
        result = await InboxSynchronizer(db, "workspace_a", "user_a").sync_account_inbox("account_a")

    assert result["synced_threads"] == 1
    assert result["new_replies_detected"] == 0
    assert db.outreach_inbox_threads.insert_one.call_args.args[0]["intent_tag"] == "not_interested"
    db.outreach_leads.update_one.assert_not_awaited()
    identity_query = db.outreach_leads.find_one.call_args.args[0]
    assert identity_query == {"workspace_id": "workspace_a", "$or": [{"linkedin_urn": "urn:li:fsd_profile:member1"}]}


@pytest.mark.asyncio
async def test_inbox_sync_never_reads_sender_from_another_workspace():
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    result = await InboxSynchronizer(db, "workspace_a", "user_a").sync_account_inbox("account_a")
    assert result["status"] == "error"
    db.outreach_accounts.find_one.assert_awaited_with({"id": "account_a", "workspace_id": "workspace_a"})


@pytest.mark.asyncio
async def test_inbox_list_excludes_old_sample_conversations():
    db = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_inbox_threads.find.return_value = cursor
    await list_inbox_threads(current_user=USER, db=db)
    query = db.outreach_inbox_threads.find.call_args.args[0]
    assert {"is_demo": {"$ne": True}} in query["$and"]


@pytest.mark.asyncio
async def test_inbox_sync_increments_campaign_only_for_new_verified_reply():
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "account_a", "workspace_id": "workspace_a", "status": "active", "session_cookie_enc": "encrypted",
    })
    db.outreach_inbox_threads.find_one = AsyncMock(side_effect=[None, {"id": "thread_a", "workspace_id": "workspace_a"}])
    db.outreach_inbox_threads.insert_one = AsyncMock()
    db.outreach_inbox_threads.update_one = AsyncMock()
    db.outreach_inbox_threads.count_documents = AsyncMock(return_value=1)
    db.outreach_leads.find_one = AsyncMock(return_value={"id": "lead_a", "campaign_id": "campaign_a"})
    db.outreach_leads.update_one = AsyncMock(side_effect=[MagicMock(modified_count=1), MagicMock(modified_count=0)])
    db.outreach_campaigns.update_one = AsyncMock()
    conversation = {
        "thread_urn": "urn:li:fs_conversation:thread1", "lead_urn": "urn:li:fsd_profile:member1",
        "lead_name": "Jordan Davis", "lead_profile_url": "https://linkedin.com/in/jordan-davis",
        "messages": [{"sender_type": "lead", "body": "Interested"}],
    }
    with patch("outreach.engine.inbox_sync.VoyagerClient") as client:
        client.return_value.fetch_conversations = AsyncMock(return_value=[conversation])
        synchronizer = InboxSynchronizer(db, "workspace_a", "user_a")
        first = await synchronizer.sync_account_inbox("account_a")
        second = await synchronizer.sync_account_inbox("account_a")

    assert first["new_replies_detected"] == 1
    assert second["new_replies_detected"] == 0
    assert db.outreach_campaigns.update_one.await_count == 2
    assert db.outreach_campaigns.update_one.call_args.args[1] == {"$set": {"interested_count": 1}}
    assert db.outreach_leads.update_one.call_args_list[0].args[0]["id"] == "lead_a"


@pytest.mark.asyncio
async def test_inbox_reply_never_falls_back_to_another_sender():
    db = MagicMock()
    db.outreach_inbox_threads.find_one = AsyncMock(return_value={
        "id": "thread_a", "workspace_id": "workspace_a", "account_id": "missing_account",
        "conversation_urn": "urn:li:fs_conversation:thread1",
    })
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_inbox_jobs.insert_one = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await send_thread_reply("thread_a", ReplyRequest(body="Hello"), current_user=USER, db=db)
    assert exc.value.status_code == 409
    db.outreach_accounts.find_one.assert_awaited_once()
    db.outreach_inbox_jobs.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbox_reply_is_queued_without_optimistic_sent_message():
    db = MagicMock()
    db.outreach_inbox_threads.find_one = AsyncMock(return_value={
        "id": "thread_a", "workspace_id": "workspace_a", "account_id": "account_a",
        "conversation_urn": "urn:li:fs_conversation:thread1",
    })
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "account_a", "status": "active", "session_cookie_enc": "encrypted",
    })
    db.outreach_inbox_jobs.insert_one = AsyncMock()
    db.outreach_inbox_jobs.count_documents = AsyncMock(return_value=0)
    db.outreach_inbox_threads.update_one = AsyncMock()
    with patch("celery_workers.tasks.outreach.send_inbox_reply.apply_async") as enqueue:
        result = await send_thread_reply("thread_a", ReplyRequest(body="Hello"), current_user=USER, db=db)
    assert result["status"] == "queued"
    enqueue.assert_called_once()
    db.outreach_inbox_threads.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbox_sync_is_queued_and_job_status_is_workspace_scoped():
    db = MagicMock()
    db.outreach_accounts.count_documents = AsyncMock(return_value=1)
    db.outreach_inbox_jobs.insert_one = AsyncMock()
    db.outreach_inbox_jobs.count_documents = AsyncMock(return_value=0)
    db.outreach_inbox_jobs.find_one = AsyncMock(return_value=None)
    with patch("celery_workers.tasks.outreach.sync_inbox.apply_async") as enqueue:
        result = await trigger_inbox_sync(account_id=None, current_user=USER, db=db)
    assert result["status"] == "queued"
    enqueue.assert_called_once()
    with pytest.raises(HTTPException) as exc:
        await get_inbox_job(result["job_id"], current_user=USER, db=db)
    assert exc.value.status_code == 404
    db.outreach_inbox_jobs.find_one.assert_awaited_with({"id": result["job_id"], "workspace_id": "workspace_a"})


@pytest.mark.asyncio
async def test_inbox_worker_records_only_confirmed_reply():
    from celery_workers.tasks.outreach import _send_inbox_reply

    db = MagicMock()
    db.outreach_inbox_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_inbox_threads.find_one = AsyncMock(return_value={
        "id": "thread_a", "account_id": "account_a", "conversation_urn": "urn:li:fs_conversation:thread1",
    })
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "account_a", "status": "active", "session_cookie_enc": "encrypted",
    })
    db.outreach_inbox_threads.update_one = AsyncMock()
    with patch("celery_workers.tasks.outreach._inbox_db", new_callable=AsyncMock, return_value=db), \
         patch("outreach.engine.voyager_client.VoyagerClient") as voyager, \
         patch("outreach.core.rate_limiter.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock, return_value=True):
        voyager.return_value.is_mock = False
        voyager.return_value.send_conversation_reply = AsyncMock(return_value={"status": "failed", "status_code": 500})
        with pytest.raises(RuntimeError):
            await _send_inbox_reply("job_a", "workspace_a", "account_a", "thread_a", "Hello")
        db.outreach_inbox_threads.update_one.assert_not_awaited()

        voyager.return_value.send_conversation_reply = AsyncMock(return_value={"status": "sent"})
        result = await _send_inbox_reply("job_b", "workspace_a", "account_a", "thread_a", "Hello")
        assert result["status"] == "sent"
        assert db.outreach_inbox_threads.update_one.call_args.args[1]["$push"]["messages"]["body"] == "Hello"
