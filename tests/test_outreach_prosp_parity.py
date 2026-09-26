"""
Prosp AI Parity Test Suite:
Tests Lead Finder, Post Engagers Ingestion, Pipeline Stage Updating,
Inbox Reminders/Snippets/Tags, AI Prompt Library & Preview, and Outreach Analytics.
"""
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from fastapi import HTTPException

from outreach.api.leads import (
    LeadFinderPreviewRequest,
    LeadFinderEnrollRequest,
    ImportPostEngagersRequest,
    UpdateLeadStageRequest,
    preview_lead_finder,
    enroll_finder_leads,
    import_post_engagers,
    update_lead_stage,
    list_leads,
)
from outreach.api.inbox import (
    CreateReminderRequest,
    CreateSnippetRequest,
    CreateTagRequest,
    ToggleTagRequest,
    create_thread_reminder,
    list_thread_reminders,
    delete_thread_reminder,
    list_snippets,
    create_snippet,
    delete_snippet,
    list_tags,
    create_tag,
    delete_tag,
    toggle_thread_tag,
)
from outreach.api.prompts import (
    CreateAIPromptRequest,
    PromptPreviewRequest,
    list_prompts,
    create_prompt,
    delete_prompt,
    preview_evaluated_message,
)
from outreach.api.analytics import get_outreach_analytics, live_activity_feed


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n):
        idx = int(getattr(n, "default", n))
        self.items = self.items[idx:]
        return self

    def limit(self, n):
        idx = int(getattr(n, "default", n))
        self.items = self.items[:idx]
        return self

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query=None, *args, **kwargs):
        return MockCursor(self.items)

    async def find_one(self, query=None, *args, **kwargs):
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    if not any(item.get(sub_k) == sub_v for cond in v for sub_k, sub_v in cond.items()):
                        match = False
                elif isinstance(v, dict) and "$ne" in v:
                    if item.get(k) == v["$ne"]:
                        match = False
                elif item.get(k) != v:
                    match = False
            if match:
                return dict(item)
        return None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return AsyncMock(inserted_id="mock_id")

    async def insert_many(self, docs):
        self.items.extend([dict(d) for d in docs])
        return AsyncMock(inserted_ids=["mock_id" for _ in docs])

    async def update_one(self, query, update, upsert=False):
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in cond.items()) for cond in v):
                        match = False
                elif item.get(k) != v:
                    match = False
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                if "$unset" in update:
                    for un_k in update["$unset"]:
                        item.pop(un_k, None)
                return AsyncMock(modified_count=1, matched_count=1)
        if upsert:
            new_item = dict(query)
            if "$set" in update:
                new_item.update(update["$set"])
            self.items.append(new_item)
            return AsyncMock(upserted_id="mock_upserted_id")
        return AsyncMock(modified_count=0, matched_count=0)

    async def delete_one(self, query):
        for i, item in enumerate(self.items):
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    if not any(item.get(sub_k) == sub_v for cond in v for sub_k, sub_v in cond.items()):
                        match = False
                elif item.get(k) != v:
                    match = False
            if match:
                self.items.pop(i)
                return AsyncMock(deleted_count=1)
        return AsyncMock(deleted_count=0)

    async def count_documents(self, query=None):
        return len(self.items)


class MockDatabase:
    def __init__(self):
        self.outreach_leads = MockCollection()
        self.outreach_campaigns = MockCollection()
        self.outreach_inbox_threads = MockCollection()
        self.outreach_inbox_reminders = MockCollection()
        self.outreach_inbox_snippets = MockCollection()
        self.outreach_inbox_tags = MockCollection()
        self.outreach_ai_prompts = MockCollection()
        self.outreach_tasks = MockCollection()
        self.outreach_do_not_contact = MockCollection()


USER = {"user_id": "usr_test_1", "default_workspace_id": "ws_test_1", "name": "Growth Pro"}


# ── 1. Lead Finder & Post Engagers Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_lead_finder():
    req = LeadFinderPreviewRequest(
        title="VP of Growth",
        industry="SaaS & Enterprise Software",
        location="San Francisco, CA",
        connection_degree="2nd",
        has_posted_recently=True,
        limit=5,
    )
    db = MockDatabase()
    with pytest.raises(HTTPException) as exc:
        await preview_lead_finder(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_enroll_finder_leads():
    db = MockDatabase()
    db.outreach_campaigns.items.append({"id": "cmp_1", "workspace_id": "ws_test_1", "status": "draft", "name": "Test Campaign", "leads_count": 0})

    leads = [
        {"linkedin_url": "https://linkedin.com/in/lead-1", "first_name": "L1", "last_name": "One"},
        {"linkedin_url": "https://linkedin.com/in/lead-2", "first_name": "L2", "last_name": "Two"},
    ]
    req = LeadFinderEnrollRequest(campaign_id="cmp_1", leads=leads)
    with pytest.raises(HTTPException) as exc:
        await enroll_finder_leads(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_import_post_engagers():
    db = MockDatabase()
    db.outreach_campaigns.items.append({"id": "cmp_1", "workspace_id": "ws_test_1", "status": "draft", "name": "Engager Campaign", "leads_count": 0})

    req = ImportPostEngagersRequest(
        campaign_id="cmp_1",
        post_url="https://www.linkedin.com/posts/satyanadella_ai-advances-activity-12345",
        push_option="Only existing comments/likes",
        export_likes=True,
        export_comments=True,
        max_leads=8,
    )
    with pytest.raises(HTTPException) as exc:
        await import_post_engagers(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_update_lead_stage_and_filtering():
    db = MockDatabase()
    lead_doc = {
        "id": "lead_stage_1",
        "workspace_id": "ws_test_1",
        "first_name": "Alex",
        "last_name": "Tester",
        "pipeline_stage": "unassigned",
    }
    db.outreach_leads.items.append(lead_doc)

    # Update stage to 'call_booked'
    req = UpdateLeadStageRequest(pipeline_stage="call_booked")
    res = await update_lead_stage("lead_stage_1", req, current_user=USER, db=db)

    assert res["status"] == "updated"
    assert res["pipeline_stage"] == "call_booked"
    assert lead_doc["pipeline_stage"] == "call_booked"

    # Filter with pipeline_stage
    list_res = await list_leads(pipeline_stage="call_booked", skip=0, limit=50, current_user=USER, db=db)
    assert list_res["total"] == 1


# ── 2. Inbox Reminders, Snippets & Tags Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_inbox_reminders():
    db = MockDatabase()
    thread_doc = {"id": "th_1", "user_id": USER["user_id"], "workspace_id": USER["default_workspace_id"]}
    db.outreach_inbox_threads.items.append(thread_doc)

    rem_time = datetime.now(timezone.utc) + timedelta(days=1)
    req = CreateReminderRequest(remind_at=rem_time, note="Follow up on pitch deck")

    # Set reminder
    res = await create_thread_reminder("th_1", req, current_user=USER, db=db)
    assert res["status"] == "created"
    assert res["reminder"]["note"] == "Follow up on pitch deck"
    assert thread_doc["reminder_note"] == "Follow up on pitch deck"

    # List reminders
    rems = await list_thread_reminders("th_1", current_user=USER, db=db)
    assert len(rems) == 1

    # Delete reminder
    del_res = await delete_thread_reminder(res["reminder"]["id"], current_user=USER, db=db)
    assert del_res["status"] == "deleted"


@pytest.mark.asyncio
async def test_inbox_snippets():
    db = MockDatabase()

    # 1. Listing seeds default snippets if empty
    snips = await list_snippets(current_user=USER, db=db)
    assert len(snips) >= 3
    titles = [s["title"] for s in snips]
    assert "Calendar link" in titles
    assert "Pricing list" in titles

    # 2. Create custom snippet
    new_req = CreateSnippetRequest(
        title="Demo Link",
        body="Here is our 2-min interactive tour: https://unravler.com/demo",
        shortcut="demo",
    )
    created = await create_snippet(new_req, current_user=USER, db=db)
    assert created["title"] == "Demo Link"

    # 3. Delete snippet
    del_res = await delete_snippet(created["id"], current_user=USER, db=db)
    assert del_res["status"] == "deleted"


@pytest.mark.asyncio
async def test_inbox_tags():
    db = MockDatabase()
    thread_doc = {
        "id": "th_tag_1",
        "user_id": USER["user_id"],
        "workspace_id": USER["default_workspace_id"],
        "tags": ["Hot lead"],
    }
    db.outreach_inbox_threads.items.append(thread_doc)

    # 1. Listing seeds default tags if empty
    tags = await list_tags(current_user=USER, db=db)
    assert len(tags) >= 5
    tag_names = [t["name"] for t in tags]
    assert "Hot lead" in tag_names
    assert "Wants to speak later" in tag_names

    # 2. Create custom tag
    new_tag_req = CreateTagRequest(name="Enterprise VIP", color="#10b981")
    created = await create_tag(new_tag_req, current_user=USER, db=db)
    assert created["name"] == "Enterprise VIP"

    # 3. Toggle tag on thread (add new tag)
    toggle_req = ToggleTagRequest(tag_name="Enterprise VIP")
    toggle_res = await toggle_thread_tag("th_tag_1", toggle_req, current_user=USER, db=db)
    assert "Enterprise VIP" in toggle_res["tags"]
    assert "Hot lead" in toggle_res["tags"]

    # 4. Toggle tag off
    toggle_off_res = await toggle_thread_tag("th_tag_1", toggle_req, current_user=USER, db=db)
    assert "Enterprise VIP" not in toggle_off_res["tags"]
    assert "Hot lead" in toggle_off_res["tags"]


# ── 3. AI Prompts Library & Message Preview Tests ──────────────────────────

@pytest.mark.asyncio
async def test_prompts_library_and_preview():
    db = MockDatabase()

    # 1. Listing seeds default high-converting Prosp prompts
    prompts = await list_prompts(current_user=USER, db=db)
    assert len(prompts) >= 5
    prompt_names = [p["name"] for p in prompts]
    assert "Saw you're doing X (3-5 words)" in prompt_names
    assert "Website designer personalised first line" in prompt_names

    # 2. Create custom prompt
    req = CreateAIPromptRequest(
        name="Conference Speaker Opener",
        prompt_text="Congratulate them on their recent keynote speech at SaaStr.",
        description="Speaker invite hook",
        author_name="Sales Team",
    )
    created = await create_prompt(req, current_user=USER, db=db)
    assert created["name"] == "Conference Speaker Opener"

    # 3. Evaluate preview with both variable {{first_name}} and AI token ✨ [Saw you're doing X (3-5 words)]
    prev_req = PromptPreviewRequest(
        template="Hey {{first_name}}, saw that you're ✨ [Saw you're doing X (3-5 words)]. Let's chat!",
        custom_lead_data={"first_name": "Jordan", "company_name": "Supabase"},
    )
    prev_res = await preview_evaluated_message(prev_req, current_user=USER, db=db)
    assert "Hey Jordan" in prev_res["evaluated_text"]
    assert "[Prompt guidance not generated:" in prev_res["evaluated_text"]


# ── 4. Outreach Analytics Dashboard Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_outreach_analytics():
    db = MockDatabase()
    res = await get_outreach_analytics(campaign_id="all", timeframe="14d", current_user=USER, db=db)

    assert "kpis" in res
    assert "requests" in res["kpis"]
    assert "messages" in res["kpis"]
    assert "engagement" in res["kpis"]
    assert "email" in res["kpis"]
    assert "daily_chart" in res
    assert len(res["daily_chart"]) == 14
    assert res["daily_chart"][0]["sent"] >= 0
    assert res["daily_chart"][0]["accepted"] >= 0


@pytest.mark.asyncio
async def test_outreach_analytics_live_feed():
    db = MockDatabase()
    res = await live_activity_feed(current_user=USER, db=db)
    assert res.media_type == "text/event-stream"
    assert res.headers["Cache-Control"] == "no-cache"
    assert res.headers["Connection"] == "keep-alive"
