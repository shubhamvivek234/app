"""
Unit tests for Phase 1 Postly-inspired features:
- Workspace Approval Governance & Editor role interception
- Universal First Comment execution pipeline
- AI Remix for Recurring / Evergreen posts
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.models.post import CreatePostRequest, PostStatus
from api.routes.team import (
    ApprovalPolicyUpdate,
    get_workspace_approval_policy,
    update_workspace_approval_policy,
)
from api.routes.posts import create_post
from starlette.requests import Request


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, length=None):
        return list(self.items)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, initial=None):
        self.items = list(initial or [])

    def find(self, query=None, projection=None, *args, **kwargs):
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif "." in k:
                    parts = k.split(".")
                    cur = item
                    for p in parts:
                        cur = cur.get(p) if isinstance(cur, dict) else None
                    if cur != v:
                        match = False
                        break
                elif isinstance(v, dict) and "$in" in v:
                    if item.get(k) not in v["$in"]:
                        match = False
                        break
                elif isinstance(v, dict) and "$ne" in v:
                    if item.get(k) == v["$ne"]:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))
        return FakeCursor(matched)

    async def find_one(self, query=None, projection=None, *args, **kwargs):
        cursor = self.find(query, projection)
        if cursor.items:
            return dict(cursor.items[0])
        return None

    async def count_documents(self, query=None):
        return len(self.find(query).items)

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id") or "inserted_id")

    async def update_one(self, query, update, upsert=False):
        found = False
        for i, item in enumerate(self.items):
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                found = True
                if "$set" in update:
                    item.update(update["$set"])
                if "$push" in update:
                    for push_k, push_v in update["$push"].items():
                        item.setdefault(push_k, []).append(push_v)
                return MagicMock(modified_count=1)
        if not found and upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            self.items.append(new_doc)
            return MagicMock(upserted_id="upserted_id")
    async def delete_one(self, query):
        for i, item in enumerate(self.items):
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                self.items.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def update_many(self, query, update):
        cnt = 0
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                cnt += 1
        return MagicMock(modified_count=cnt)

    async def find_one_and_update(self, query, update, return_document=None, projection=None):
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return dict(item)
        return None


class FakeDB:
    def __init__(self):
        self.workspaces = FakeCollection()
        self.workspace_members = FakeCollection()
        self.posts = FakeCollection()
        self.social_accounts = FakeCollection()
        self.approval_activity = FakeCollection()
        self.notifications = FakeCollection()
        self.rss_feeds = FakeCollection()
        self.rss_feed_items = FakeCollection()
        self.campaigns = FakeCollection()
        self.short_links = FakeCollection()
        self.inbox_messages = FakeCollection()
        self.users = FakeCollection()


@pytest.mark.asyncio
async def test_workspace_approval_policy_crud():
    db = FakeDB()
    user = {"user_id": "usr_owner_1", "default_workspace_id": "ws_alpha", "role": "owner"}

    policy = await get_workspace_approval_policy(current_user=user, db=db)
    assert policy["enabled"] is False
    assert "editor" in policy["required_for_roles"]

    update_body = ApprovalPolicyUpdate(
        enabled=True,
        required_for_roles=["editor", "creator", "client"],
        auto_assign_reviewer_id="usr_admin_99",
    )
    res = await update_workspace_approval_policy(update_body, current_user=user, db=db)
    assert res["status"] == "ok"
    assert res["approval_policy"]["enabled"] is True

    policy_after = await get_workspace_approval_policy(current_user=user, db=db)
    assert policy_after["enabled"] is True
    assert policy_after["auto_assign_reviewer_id"] == "usr_admin_99"
    assert "editor" in policy_after["required_for_roles"]


@pytest.mark.asyncio
async def test_editor_post_interception_when_policy_enabled():
    db = FakeDB()
    await db.workspaces.insert_one({
        "workspace_id": "ws_governed",
        "name": "Governed Agency",
        "approval_policy": {
            "enabled": True,
            "required_for_roles": ["editor", "client"],
            "auto_assign_reviewer_id": "usr_lead_approver",
        },
    })
    await db.workspace_members.insert_one({
        "workspace_id": "ws_governed",
        "user_id": "usr_editor_1",
        "role": "editor",
    })
    await db.social_accounts.insert_one({
        "id": "acct_twitter_1",
        "account_id": "acct_twitter_1",
        "user_id": "usr_editor_1",
        "platform": "twitter",
        "is_active": True,
    })

    editor_user = {
        "user_id": "usr_editor_1",
        "default_workspace_id": "ws_governed",
        "role": "editor",
        "email_verified": True,
        "subscription_status": "active",
    }

    body = CreatePostRequest(
        content="This is an urgent announcement",
        platforms=["twitter"],
        publish_now=True,
        workspace_id="ws_governed",
    )

    req = Request(scope={
        "type": "http",
        "method": "POST",
        "path": "/api/posts",
        "client": ("10.99.1.5", 12345),
        "headers": [],
    })
    mock_redis = AsyncMock()

    with patch("api.routes.posts.enqueue_task"):
        post_res = await create_post(
            request=req,
            body=body,
            current_user=editor_user,
            db=db,
            queue_redis=mock_redis,
        )

    assert post_res.status == PostStatus.PENDING_APPROVAL

    saved = await db.posts.find_one({"id": post_res.id})
    assert saved is not None
    assert saved["status"] == PostStatus.PENDING_APPROVAL
    assert saved["assigned_reviewer_id"] == "usr_lead_approver"

    activity = await db.approval_activity.find_one({"post_id": post_res.id})
    assert activity is not None
    assert activity["action"] == "submitted"
    assert activity["actor_id"] == "usr_editor_1"


@pytest.mark.asyncio
async def test_first_comment_publish_success():
    from utils.first_comment import post_first_comment

    account = {"platform": "twitter", "access_token": "mock_token_12345"}
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "tweet_comment_999"}}
        mock_post.return_value = mock_response

        res = await post_first_comment(
            platform="twitter",
            platform_post_id="root_tweet_111",
            first_comment_text="Here is the link: https://unravler.com",
            account=account,
        )

        assert res["status"] == "published"
        assert res["comment_id"] == "tweet_comment_999"


@pytest.mark.asyncio
async def test_recurring_ai_remix_invoked_on_spawn():
    from celery_workers.tasks.recurring import _async_spawn

    db = FakeDB()
    now = datetime.now(timezone.utc)
    template_id = "tmpl_recurring_123"

    await db.posts.insert_one({
        "_id": template_id,
        "id": template_id,
        "user_id": "usr_creator",
        "workspace_id": "ws_1",
        "content": "Original recurring tips and tricks post: https://unravler.com",
        "status": "template",
        "recurrence": {
            "enabled": True,
            "frequency": "daily",
            "interval": 1,
            "ai_remix": True,
            "next_occurrence": now - timedelta(minutes=5),
        },
    })

    with patch("utils.free_llm_router.free_llm.generate_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ("✨ Freshly remixed viral hook for tips and tricks: https://unravler.com", "gemini", "gemini-2.5-flash")

        res = await _async_spawn(db)
        assert res.get("spawned", 0) >= 1

        spawned_post = await db.posts.find_one({"recurrence_template_id": template_id})
        assert spawned_post is not None
        assert "Freshly remixed viral hook" in spawned_post["content"]
        assert spawned_post.get("ai_remixed") is True


def test_brand_voice_signature_cta_included_in_system_message():
    from api.routes.ai import _build_system_message

    brand_voice = {
        "brand_name": "Unravler Growth",
        "tone": "Confident & Authoritative",
        "signature_cta": "👉 Sign up at unravler.com/signup for a 14-day free trial",
        "banned_words": ["synergy", "cheap"],
    }

    system_message = _build_system_message(
        platform="twitter",
        tone="professional",
        language="English",
        brand_voice=brand_voice,
    )

    assert "unravler.com/signup" in system_message
    assert "Always conclude with this signature Call-To-Action (CTA)" in system_message
    assert "Confident & Authoritative" in system_message
    assert "synergy" in system_message


@pytest.mark.asyncio
async def test_rss_sync_with_ai_enhancement():
    from api.routes.rss_feeds import _sync_feed_items

    db = FakeDB()
    now = datetime.now(timezone.utc)

    feed = {
        "id": "feed_tech_news",
        "user_id": "usr_rss_owner",
        "workspace_id": "ws_rss",
        "feed_url": "https://example.com/rss.xml",
        "auto_publish": True,
        "use_ai_enhancement": True,
        "ai_tone": "witty",
        "target_account_ids": ["acct_rss_tw"],
        "target_platforms": ["twitter"],
        "max_posts_per_day": 5,
        "status": "active",
    }
    await db.rss_feeds.insert_one(feed)
    await db.social_accounts.insert_one({
        "id": "acct_rss_tw",
        "account_id": "acct_rss_tw",
        "user_id": "usr_rss_owner",
        "workspace_id": "ws_rss",
        "platform": "twitter",
        "is_active": True,
    })

    raw_items = [{
        "guid": "guid_item_1",
        "url": "https://example.com/ai-breakthrough",
        "title": "Quantum AI Breakthrough Announced",
        "summary": "Scientists have achieved milestone results in quantum LLM reasoning.",
        "author": "Dr. Smith",
        "pub_date": now,
        "media_urls": [],
    }]

    mock_feed_meta = MagicMock(title="Tech Dispatch", description="Tech", site_url="https://example.com", icon_url=None)

    with patch("api.routes.rss_feeds.fetch_feed") as mock_fetch, \
         patch("utils.free_llm_router.free_llm.generate_text", new_callable=AsyncMock) as mock_llm:
        mock_fetch.return_value = (mock_feed_meta, raw_items, "etag_1", "last_mod_1", False)
        mock_llm.return_value = ("🔥 Breakthrough: Quantum AI reasoning is officially here! Takeaways... https://example.com/ai-breakthrough #Quantum #AI", "gemini", "gemini-2.5-flash")

        res = await _sync_feed_items(db, feed, "usr_rss_owner", "ws_rss")
        assert res.get("scheduled", 0) >= 1

        post = await db.posts.find_one({"workspace_id": "ws_rss"})
        assert post is not None
        assert "Breakthrough: Quantum AI" in post["content"]
        assert "https://example.com/ai-breakthrough" in post["content"]


def test_thread_splitter_pagination():
    from utils.thread_splitter import split_into_thread

    short_text = "This is a brief update under 280 chars."
    assert split_into_thread(short_text, "twitter") == [short_text]

    long_text = (
        "1. First point about agency automation and enterprise growth.\n\n"
        "2. Second point highlighting why approval workflows protect brand reputation.\n\n"
        "3. Third point detailing how first comment scheduling drives link clicks without harming the algorithm.\n\n"
        "4. Fourth point exploring how AI remix keeps evergreen content fresh forever.\n\n"
        "5. Fifth point reviewing campaign ROI across Twitter, LinkedIn, and Facebook with automatic analytics sync."
    )
    thread = split_into_thread(long_text, platform="twitter")
    assert len(thread) >= 2
    assert thread[0].endswith(f"(1/{len(thread)})")
    assert thread[-1].endswith(f"({len(thread)}/{len(thread)})")
    for tweet in thread:
        assert len(tweet) <= 280


@pytest.mark.asyncio
async def test_campaigns_crud_and_roi_aggregation():
    from api.routes.campaigns import create_campaign, list_campaigns, delete_campaign, CampaignCreate

    db = FakeDB()
    user = {"user_id": "usr_camp_owner", "default_workspace_id": "ws_camp", "email_verified": True}

    body = CampaignCreate(
        name="Q3 Product Launch",
        description="Multi-platform global launch for Unravler v6",
        color="#8b5cf6",
        target_platforms=["twitter", "linkedin"],
        budget=5000.0,
        status="active",
    )

    camp = await create_campaign(body=body, current_user=user, db=db)
    assert camp.id.startswith("cmp_")
    assert camp.name == "Q3 Product Launch"

    # Insert a post tagged with this campaign
    await db.posts.insert_one({
        "id": "post_camp_1",
        "workspace_id": "ws_camp",
        "campaign_id": camp.id,
        "content": "Excited to launch Unravler v6!",
        "metrics": {"impressions": 1250, "engagements": 340},
    })

    # Insert a short link tagged with this campaign
    await db.short_links.insert_one({
        "workspace_id": "ws_camp",
        "campaign_id": camp.id,
        "clicks": 420,
    })

    listed = await list_campaigns(current_user=user, db=db)
    assert len(listed) == 1
    assert listed[0].post_count == 1
    assert listed[0].total_clicks == 420
    assert listed[0].total_impressions == 1250
    assert listed[0].total_engagements == 340

    await delete_campaign(campaign_id=camp.id, current_user=user, db=db)
    after_del = await list_campaigns(current_user=user, db=db)
    assert len(after_del) == 0


@pytest.mark.asyncio
async def test_inbox_lead_tagging():
    from api.routes.inbox import update_inbox_message

    db = FakeDB()
    user = {"user_id": "usr_inbox_agent", "default_workspace_id": "ws_inbox"}

    msg_id = "msg_lead_123"
    await db.inbox_messages.insert_one({
        "id": msg_id,
        "message_id": msg_id,
        "user_id": "usr_inbox_agent",
        "workspace_id": "ws_inbox",
        "sender_name": "Sarah Connor",
        "content": "Can we get an enterprise demo for our 50-person agency?",
        "platform": "instagram",
        "status": "unread",
        "received_at": datetime.now(timezone.utc),
    })

    # Update with CRM lead tag and notes
    patch_body = {
        "lead_tag": "high_intent",
        "crm_notes": "Needs 50 seats by end of month. Schedule demo.",
    }
    updated = await update_inbox_message(message_id=msg_id, body=patch_body, current_user=user, db=db)
    assert updated["lead_tag"] == "high_intent"
    assert "Needs 50 seats" in updated["crm_notes"]




