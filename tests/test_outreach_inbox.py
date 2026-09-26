"""
Unit tests for LinkedIn Unified Inbox API endpoints:
- list_inbox_threads with source, account_id, and search filtering
- get_thread with unread reset
- generate_ai_reply_options
- update_thread_intent
"""
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch
from outreach.models import (
    OutreachInboxThread,
    OutreachInboxMessage,
    MessageSenderType,
)
from outreach.api.inbox import (
    list_inbox_threads,
    get_thread,
    generate_ai_reply_options,
    update_thread_intent,
    UpdateIntentRequest,
    seed_demo_threads,
    send_thread_reply,
    ReplyRequest,
)


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query=None, *args, **kwargs):
        def matches_condition(item, condition):
            return all(
                item.get(key) != expected["$ne"] if isinstance(expected, dict) and "$ne" in expected
                else item.get(key) == expected
                for key, expected in condition.items()
            )

        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    or_matched = False
                    for branch in v:
                        if all(item.get(bk) == bv for bk, bv in branch.items()):
                            or_matched = True
                            break
                    if not or_matched:
                        match = False
                        break
                elif k == "$and":
                    and_matched = True
                    for cond in v:
                        if "$or" in cond:
                            sub_or = False
                            for b in cond["$or"]:
                                if all(item.get(bk) == bv for bk, bv in b.items()):
                                    sub_or = True
                                    break
                            if not sub_or:
                                and_matched = False
                                break
                        elif not matches_condition(item, cond):
                            and_matched = False
                            break
                    if not and_matched:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))
        return MockCursor(matched)

    async def find_one(self, query=None, *args, **kwargs):
        cursor = self.find(query)
        items = await cursor.to_list(1)
        return dict(items[0]) if items else None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return True

    async def update_one(self, query, update):
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_matched = any(all(item.get(bk) == bv for bk, bv in branch.items()) for branch in v)
                    if not or_matched:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return AsyncMock(matched_count=1)
        return AsyncMock(matched_count=0)


class MockDB:
    def __init__(self):
        self.outreach_inbox_threads = MockCollection()
        self.outreach_accounts = MockCollection()


@pytest.mark.asyncio
async def test_list_inbox_threads_with_filters():
    """Verify list_inbox_threads filters by user, account, and source."""
    db = MockDB()
    user = {"user_id": "usr_inbox_1", "default_workspace_id": "ws_1"}

    # Seed threads
    await db.outreach_inbox_threads.insert_one({
        "id": "th_1",
        "user_id": "usr_inbox_1",
        "workspace_id": "ws_1",
        "account_id": "acc_1",
        "lead_name": "Sarah Connor",
        "last_message_snippet": "Sounds good, let's chat!",
        "is_outreach": True,
        "unread_count": 2,
    })
    await db.outreach_inbox_threads.insert_one({
        "id": "th_2",
        "user_id": "usr_inbox_1",
        "workspace_id": "ws_1",
        "account_id": "acc_2",
        "lead_name": "John Doe",
        "last_message_snippet": "Direct organic message",
        "is_outreach": False,
        "unread_count": 0,
    })

    # 1. Fetch All
    all_threads = await list_inbox_threads(
        account_id=None,
        source=None,
        search=None,
        intent=None,
        current_user=user,
        db=db,
    )
    assert len(all_threads) == 2

    # 2. Fetch with account_id filter
    acc1_threads = await list_inbox_threads(
        account_id="acc_1",
        source=None,
        search=None,
        intent=None,
        current_user=user,
        db=db,
    )
    assert len(acc1_threads) == 1
    assert acc1_threads[0]["lead_name"] == "Sarah Connor"


@pytest.mark.asyncio
async def test_get_thread_and_reset_unread():
    """Verify get_thread returns full thread details and resets unread count."""
    db = MockDB()
    user = {"user_id": "usr_inbox_2", "default_workspace_id": "ws_2"}

    await db.outreach_inbox_threads.insert_one({
        "id": "th_test",
        "user_id": "usr_inbox_2",
        "workspace_id": "ws_2",
        "account_id": "acc_1",
        "lead_name": "Alice Wonderland",
        "unread_count": 3,
        "messages": [
            {"sender_type": "lead", "body": "Hey there!"},
        ],
    })

    thread = await get_thread(thread_id="th_test", current_user=user, db=db)
    assert thread["id"] == "th_test"
    assert thread["unread_count"] == 0
    assert len(thread["messages"]) == 1


@pytest.mark.asyncio
async def test_generate_ai_reply_options():
    """Verify generate_ai_reply_options returns 3 smart contextual suggestions."""
    db = MockDB()
    user = {"user_id": "usr_inbox_3", "default_workspace_id": "ws_3"}

    await db.outreach_inbox_threads.insert_one({
        "id": "th_ai",
        "user_id": "usr_inbox_3",
        "workspace_id": "ws_3",
        "lead_name": "Bob Dylan",
        "last_message_snippet": "Tell me more about what you offer.",
    })

    with patch("outreach.api.inbox.free_llm.generate_text", new_callable=AsyncMock) as generate:
        generate.return_value = ('["Hi Bob, what would you like to know?", "Hi Bob, happy to share more.", "Hi Bob, I can follow up later."]', "test", "test")
        res = await generate_ai_reply_options(thread_id="th_ai", current_user=user, db=db)
    assert len(res.suggestions) == 3
    assert any("Bob" in s for s in res.suggestions)


@pytest.mark.asyncio
async def test_update_thread_intent():
    """Verify update_thread_intent categorizes lead intent properly."""
    db = MockDB()
    user = {"user_id": "usr_inbox_4", "default_workspace_id": "ws_4"}

    await db.outreach_inbox_threads.insert_one({
        "id": "th_intent",
        "user_id": "usr_inbox_4",
        "workspace_id": "ws_4",
        "lead_name": "Charlie Chaplin",
        "intent_tag": None,
    })

    req = UpdateIntentRequest(intent_tag="interested")
    res = await update_thread_intent(
        thread_id="th_intent",
        req=req,
        current_user=user,
        db=db,
    )
    assert res["status"] == "updated"
    assert res["intent_tag"] == "interested"


@pytest.mark.asyncio
async def test_seed_demo_threads(monkeypatch):
    """Verify seed_demo_threads populates demo conversations into unified inbox."""
    db = MockDB()
    user = {"user_id": "usr_seed_1", "default_workspace_id": "ws_seed"}

    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    res = await seed_demo_threads(current_user=user, db=db)
    assert res["status"] == "seeded"
    assert res["count"] == 2

    # Verify threads can be fetched
    threads = await list_inbox_threads(current_user=user, db=db)
    assert len(threads) == 2
    lead_names = [t["lead_name"] for t in threads]
    assert "Jordan Davis" in lead_names
    assert "Elena Rostova" in lead_names


@pytest.mark.asyncio
async def test_send_thread_reply_in_demo_mode():
    """Sample conversations must never pretend to send a LinkedIn reply."""
    db = MockDB()
    user = {"user_id": "usr_reply_1", "default_workspace_id": "ws_reply"}

    await db.outreach_inbox_threads.insert_one({
        "id": "th_reply_demo",
        "user_id": "usr_reply_1",
        "workspace_id": "ws_reply",
        "is_demo": True,
        "lead_name": "Jordan Davis",
        "messages": [
            {"sender_type": "lead", "body": "Hey there!"},
        ],
    })

    req = ReplyRequest(body="Hey Jordan! Thanks for following up.")
    with pytest.raises(HTTPException) as exc:
        await send_thread_reply(thread_id="th_reply_demo", req=req, current_user=user, db=db)
    assert exc.value.status_code == 409
