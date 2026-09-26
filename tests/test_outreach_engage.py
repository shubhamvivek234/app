"""
Unit tests for the LinkedIn Pre-Outreach Engage & Grow Studio,
Writing Styles Mimicry, and Swipe Files Repurposer.
"""
import pytest


@pytest.fixture(autouse=True)
def sandbox_linkedin_sessions(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from outreach.api.engage import (
    CreateEngageListRequest,
    AddContactsRequest,
    CommentPostRequest,
    LikePostRequest,
    AICommentRequest,
    create_engage_list,
    list_engage_lists,
    get_engage_list,
    delete_engage_list,
    add_contacts_to_list,
    fetch_latest_posts_for_list,
    get_engage_posts_feed,
    like_engage_post,
    queue_like_engage_post,
    comment_engage_post,
    discard_engage_post,
    generate_ai_comments,
)
from outreach.models import EngagePost
from outreach.engine.voyager_client import VoyagerClient
from outreach.api.styles import (
    CreateWritingStyleRequest,
    create_writing_style,
    list_writing_styles,
    delete_writing_style,
)
from outreach.api.swipe import (
    CreateSwipeItemRequest,
    RepurposeSwipeRequest,
    create_swipe_item,
    list_swipe_items,
    repurpose_swipe_item,
)


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, count):
        self.items = self.items[count:]
        return self

    def limit(self, count):
        self.items = self.items[:count]
        return self

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query=None, *args, **kwargs):
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if isinstance(v, dict):
                    if "$regex" in v:
                        import re
                        if not re.search(v["$regex"], str(item.get(k, "")), re.IGNORECASE):
                            match = False
                            break
                    elif "$ne" in v:
                        if item.get(k) == v["$ne"]:
                            match = False
                            break
                elif isinstance(item.get(k), list):
                    if v not in item.get(k):
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
        res = await cursor.to_list(1)
        return res[0] if res else None

    async def insert_one(self, doc):
        d = dict(doc)
        if "id" not in d:
            d["id"] = "doc_" + str(len(self.items))
        self.items.append(d)
        return d

    async def update_one(self, query, update):
        target = await self.find_one(query)
        if target:
            for item in self.items:
                if item.get("id") == target.get("id"):
                    if "$set" in update:
                        item.update(update["$set"])
                    return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def update_many(self, query, update):
        count = 0
        for item in self.items:
            if "$set" in update:
                item.update(update["$set"])
                count += 1
        return type("UpdateResult", (), {"modified_count": count})()

    async def delete_one(self, query):
        for idx, item in enumerate(self.items):
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                self.items.pop(idx)
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    async def delete_many(self, query):
        rem = []
        count = 0
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
            else:
                rem.append(item)
        self.items = rem
        return type("DeleteResult", (), {"deleted_count": count})()

    async def count_documents(self, query=None):
        cursor = self.find(query)
        res = await cursor.to_list()
        return len(res)


class MockDB:
    def __init__(self):
        self.outreach_engage_lists = MockCollection()
        self.outreach_engage_contacts = MockCollection()
        self.outreach_engage_posts = MockCollection()
        self.outreach_engage_drafts = MockCollection()
        self.outreach_writing_styles = MockCollection()
        self.outreach_swipe_files = MockCollection()
        self.outreach_accounts = MockCollection()
        self.outreach_campaigns = MockCollection()


@pytest.fixture
def mock_user():
    return {
        "user_id": "usr_test123",
        "default_workspace_id": "ws_test123",
        "email": "test@unravler.com",
    }


@pytest.fixture
def db():
    return MockDB()


@pytest.mark.asyncio
async def test_create_and_list_engage_lists(db, mock_user):
    req = CreateEngageListRequest(name="Agency Prospects", emoji="💼", description="Tier 1 agency leads")
    created = await create_engage_list(req, current_user=mock_user, db=db)
    assert created["name"] == "Agency Prospects"
    assert created["emoji"] == "💼"
    assert created["workspace_id"] == "ws_test123"

    lists = await list_engage_lists(current_user=mock_user, db=db)
    assert len(lists) == 1
    assert lists[0]["name"] == "Agency Prospects"
    assert lists[0]["contacts_count"] == 0


@pytest.mark.asyncio
async def test_add_contacts_and_fetch_posts(db, mock_user):
    # 0. Seed an active sender account (required after B2 fix: no silent mock fallback)
    await db.outreach_accounts.insert_one({
        "id": "acc_test_engage",
        "workspace_id": "ws_test123",
        "status": "active",
        "session_cookie_enc": "mock_cookie",
        "jsession_id": "ajax:123",
        "counters": {},
        "limits": {"post_likes": 50, "comments": 50},
    })

    # 1. Create list
    req = CreateEngageListRequest(name="SaaS Founders", emoji="🚀")
    lst = await create_engage_list(req, current_user=mock_user, db=db)
    list_id = lst["id"]

    # 2. Add contacts
    csv_sample = "Name,Profile\nSatya,https://www.linkedin.com/in/satyanadella/\nSam,https://www.linkedin.com/in/sama/"
    contact_req = AddContactsRequest(
        profile_urls=["https://www.linkedin.com/in/reedhastings/"],
        csv_text=csv_sample,
    )
    with patch("celery_workers.celery_app.celery_app.send_task") as send_task:
        add_res = await add_contacts_to_list(list_id, contact_req, current_user=mock_user, db=db)
        send_task.assert_called_once()
    assert add_res["status"] == "success"
    assert add_res["added_count"] == 3

    # 3. Fetch queues background work; the API no longer scrapes on the request path.
    with patch("celery_workers.celery_app.celery_app.send_task") as send_task, \
         patch.object(db.outreach_engage_lists, "update_one", new_callable=AsyncMock) as update_one:
        update_one.return_value = SimpleNamespace(modified_count=1)
        fetch_res = await fetch_latest_posts_for_list(list_id, current_user=mock_user, db=db)
        assert fetch_res["status"] == "queued"
        send_task.assert_called_once()

    contact = db.outreach_engage_contacts.items[0]
    await db.outreach_engage_posts.insert_one(EngagePost(
        list_id=list_id, contact_id=contact["id"], workspace_id="ws_test123",
        author_name="Verified Prospect", author_urn="urn:li:fsd_profile:123",
        post_urn="urn:li:activity:123", content_text="A recent post",
    ).model_dump())

    # 4. Read posts feed
    feed = await get_engage_posts_feed(list_id, status_filter="pending", current_user=mock_user, db=db)
    assert len(feed["posts"]) == 1
    first_post = feed["posts"][0]
    assert first_post["status"] == "pending"

    # 5. 1-Click Like
    with patch.object(db.outreach_engage_posts, "update_one", new_callable=AsyncMock) as update_one, \
         patch("outreach.api.engage.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock) as limit:
        update_one.return_value = SimpleNamespace(modified_count=1)
        limit.return_value = True
        like_res = await like_engage_post(first_post["id"], LikePostRequest(), current_user=mock_user, db=db)
    assert like_res["status"] == "liked"
    db.outreach_engage_posts.items[0]["status"] = "liked"

    # 6. In-line Comment with auto-like
    comment_req = CommentPostRequest(comment_text="Incredible point on follow-up speed. Totally agreed!", auto_like=True)
    with patch.object(db.outreach_engage_posts, "update_one", new_callable=AsyncMock) as update_one, \
         patch("outreach.api.engage.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock) as limit:
        update_one.return_value = SimpleNamespace(modified_count=1)
        limit.return_value = True
        com_res = await comment_engage_post(first_post["id"], comment_req, current_user=mock_user, db=db)
    assert com_res["status"] == "commented"
    assert com_res["auto_liked"] is False
    assert com_res["comment"] == "Incredible point on follow-up speed. Totally agreed!"


@pytest.mark.asyncio
async def test_mock_enrichment_never_claims_a_guessed_identity():
    profile = await VoyagerClient("mock_cookie").fetch_profile_info("jane-smith-123")
    assert profile["verified"] is False
    assert profile["profile_urn"] == ""
    assert profile["full_name"] == "LinkedIn Member"


def test_voyager_extracts_image_and_article_media():
    update = {"content": {"media": [
        {"vectorImage": {"rootUrl": "https://media.licdn.com/", "artifacts": [
            {"fileIdentifyingUrlPathSegment": "image.jpg"}]}},
        {"article": {"navigationUrl": "https://www.linkedin.com/pulse/example"}},
    ]}}
    assert VoyagerClient._update_media_urls(update) == [
        "https://media.licdn.com/image.jpg", "https://www.linkedin.com/pulse/example",
    ]


@pytest.mark.asyncio
async def test_duplicate_like_is_rejected_before_voyager(db, mock_user):
    await db.outreach_engage_posts.insert_one(EngagePost(
        list_id="list_1", contact_id="contact_1", workspace_id="ws_test123",
        author_name="Prospect", post_urn="urn:li:activity:123", status="liked",
    ).model_dump())
    post_id = db.outreach_engage_posts.items[0]["id"]
    with patch("outreach.engine.voyager_client.VoyagerClient.like_update", new_callable=AsyncMock) as voyager_like:
        with pytest.raises(HTTPException) as exc:
            await like_engage_post(post_id, LikePostRequest(), current_user=mock_user, db=db)
        assert exc.value.status_code == 409
        voyager_like.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_like_is_not_recorded_as_success(db, mock_user):
    await db.outreach_accounts.insert_one({
        "id": "acc_1", "workspace_id": "ws_test123", "status": "active",
        "session_cookie_enc": "mock_cookie", "jsession_id": "ajax:123",
    })
    await db.outreach_engage_posts.insert_one(EngagePost(
        list_id="list_1", contact_id="contact_1", workspace_id="ws_test123",
        author_name="Prospect", post_urn="urn:li:activity:123",
    ).model_dump())
    post_id = db.outreach_engage_posts.items[0]["id"]
    with patch.object(db.outreach_engage_posts, "update_one", new_callable=AsyncMock) as update_one, \
         patch("outreach.api.engage.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock) as limit, \
         patch("outreach.engine.voyager_client.VoyagerClient.like_update", new_callable=AsyncMock) as voyager_like:
        update_one.return_value = SimpleNamespace(modified_count=1)
        limit.return_value = True
        voyager_like.return_value = {"status": "failed", "status_code": 500}
        with pytest.raises(HTTPException) as exc:
            await like_engage_post(post_id, LikePostRequest(), current_user=mock_user, db=db)
        assert exc.value.status_code == 502
    assert db.outreach_engage_posts.items[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_like_endpoint_only_queues_worker_action(db, mock_user):
    await db.outreach_accounts.insert_one({
        "id": "acc_1", "workspace_id": "ws_test123", "status": "active",
    })
    await db.outreach_engage_posts.insert_one(EngagePost(
        list_id="list_1", contact_id="contact_1", workspace_id="ws_test123",
        author_name="Prospect", post_urn="urn:li:activity:123",
    ).model_dump())
    post_id = db.outreach_engage_posts.items[0]["id"]
    with patch.object(db.outreach_engage_posts, "update_one", new_callable=AsyncMock) as update_one, \
         patch("celery_workers.celery_app.celery_app.send_task") as send_task, \
         patch("outreach.engine.voyager_client.VoyagerClient.like_update", new_callable=AsyncMock) as voyager_like:
        update_one.return_value = SimpleNamespace(modified_count=1)
        result = await queue_like_engage_post(post_id, LikePostRequest(sender_account_id="acc_1"),
                                              current_user=mock_user, db=db)
        assert result["status"] == "queued"
        send_task.assert_called_once()
        voyager_like.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_comment_generator(db, mock_user):
    req = AICommentRequest(
        post_text="Speed to lead is everything. Responding in under 15 minutes triples demo close rates.",
        author_headline="VP of Sales",
        tone="insightful",
    )
    with patch("outreach.api.engage.free_llm.generate_text", new_callable=AsyncMock) as generate:
        generate.return_value = ('["A useful comment about speed.", "A second relevant angle.", "A thoughtful question for the author?"]', None, None)
        res = await generate_ai_comments(req, current_user=mock_user, db=db)
    assert res["tone"] == "insightful"
    assert len(res["comments"]) == 3
    for c in res["comments"]:
        assert len(c) > 10


@pytest.mark.asyncio
async def test_writing_styles_crud(db, mock_user):
    req = CreateWritingStyleRequest(
        name="Punchy Founder",
        sample_posts=[
            "Most founders overcomplicate cold outreach. Keep it under 50 words.",
            "Here is the counter-intuitive metric we track every Monday morning.",
        ],
        is_default=True,
    )
    created = await create_writing_style(req, current_user=mock_user, db=db)
    assert created["name"] == "Punchy Founder"
    assert created["is_default"] is True

    styles = await list_writing_styles(current_user=mock_user, db=db)
    assert len(styles) == 1

    del_res = await delete_writing_style(created["id"], current_user=mock_user, db=db)
    assert del_res["status"] == "deleted"


@pytest.mark.asyncio
async def test_swipe_files_and_repurpose(db, mock_user):
    create_req = CreateSwipeItemRequest(
        author_name="Justin Welsh",
        content_text="The 1-person business model is not about doing everything yourself. It's about ruthless leverage.",
        tags=["Solopreneur", "Leverage"],
    )
    item = await create_swipe_item(create_req, current_user=mock_user, db=db)
    assert item["author_name"] == "Justin Welsh"

    items = await list_swipe_items(tag="Solopreneur", current_user=mock_user, db=db)
    assert len(items) == 1

    repurpose_req = RepurposeSwipeRequest(target_format="outbound_hook")
    with patch("outreach.api.swipe.free_llm.generate_text", new_callable=AsyncMock) as generate:
        generate.return_value = ("A fresh and original outreach hook for your prospect.", "test", "test")
        rep_res = await repurpose_swipe_item(item["id"], repurpose_req, current_user=mock_user, db=db)
    assert rep_res["target_format"] == "outbound_hook"
    assert len(rep_res["repurposed_text"]) > 10
