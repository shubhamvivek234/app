from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.routes.rss_feeds import (
    DEFAULT_POST_TEMPLATE,
    CreateFeedRequest,
    ShareItemRequest,
    UpdateFeedRequest,
    ValidateFeedRequest,
    _format_post_content,
    _sync_feed_items,
    create_rss_feed,
    delete_rss_feed,
    list_rss_feeds,
    share_rss_item_to_social,
    update_rss_feed,
    validate_rss_feed,
)
from utils.rss_parser import (
    extract_images_from_html,
    parse_feed_xml,
    parse_pub_date,
    strip_html,
)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech News Daily</title>
    <link>https://technews.example.com</link>
    <description>Latest tech stories</description>
    <item>
      <title>Autonomous Agents Scale Fast</title>
      <link>https://technews.example.com/agents-2026</link>
      <description>&lt;p&gt;A breakthrough in multi-agent orchestration.&lt;img src="https://technews.example.com/img.jpg"/&gt;&lt;/p&gt;</description>
      <pubDate>Sat, 29 Aug 2026 12:00:00 GMT</pubDate>
      <guid>https://technews.example.com/agents-2026</guid>
    </item>
  </channel>
</rss>"""

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Engineering Blog</title>
  <link href="https://eng.example.com"/>
  <subtitle>Deep engineering posts</subtitle>
  <entry>
    <title>Building Distributed Schedulers</title>
    <link href="https://eng.example.com/schedulers"/>
    <id>urn:uuid:12345</id>
    <updated>2026-08-29T10:00:00Z</updated>
    <summary>How to maintain clock synchronization.</summary>
  </entry>
</feed>"""


class _FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, _length=None):
        return list(self.items)


class _FakeCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query, projection=None):
        res = self.items
        if "workspace_id" in query:
            res = [i for i in res if i.get("workspace_id") == query["workspace_id"]]
        if "status" in query and isinstance(query["status"], str):
            res = [i for i in res if i.get("status") == query["status"]]
        return _FakeCursor(res)

    async def find_one(self, query, projection=None):
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$ne":
                    continue
                if isinstance(v, dict) and "$in" in v:
                    if item.get(k) not in v["$in"]:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                return dict(item)
        return None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update):
        for item in self.items:
            if all(item.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    item.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one_and_update(self, query, update, return_document=True, projection=None):
        for item in self.items:
            if all(item.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    item.update(update["$set"])
                return dict(item)
        return None

    async def delete_one(self, query):
        orig_len = len(self.items)
        self.items = [i for i in self.items if not all(i.get(k) == v for k, v in query.items())]
        return SimpleNamespace(deleted_count=orig_len - len(self.items))

    async def delete_many(self, query):
        orig_len = len(self.items)
        self.items = [i for i in self.items if not all(i.get(k) == v for k, v in query.items())]
        return SimpleNamespace(deleted_count=orig_len - len(self.items))

    async def count_documents(self, query):
        count = 0
        for item in self.items:
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if item.get(k) not in v["$in"]:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count


class _FakeDB:
    def __init__(self, feeds=None, items=None, accounts=None, posts=None):
        self.rss_feeds = _FakeCollection(feeds or [])
        self.rss_feed_items = _FakeCollection(items or [])
        self.social_accounts = _FakeCollection(accounts or [])
        self.posts = _FakeCollection(posts or [])


def test_rss_parser_extracts_rss2_feed():
    feed_meta, items = parse_feed_xml(SAMPLE_RSS_XML, source_url="https://technews.example.com/rss")
    assert feed_meta["title"] == "Tech News Daily"
    assert len(items) == 1
    assert items[0]["title"] == "Autonomous Agents Scale Fast"
    assert items[0]["url"] == "https://technews.example.com/agents-2026"
    assert "https://technews.example.com/img.jpg" in items[0]["media_urls"]


def test_rss_parser_extracts_atom_feed():
    feed_meta, items = parse_feed_xml(SAMPLE_ATOM_XML, source_url="https://eng.example.com/atom")
    assert feed_meta["title"] == "Engineering Blog"
    assert len(items) == 1
    assert items[0]["title"] == "Building Distributed Schedulers"
    assert items[0]["url"] == "https://eng.example.com/schedulers"


def test_strip_html_and_template_formatting():
    raw = "<p>Hello <b>World</b> &amp; Friends!</p>"
    clean = strip_html(raw)
    assert clean == "Hello World & Friends!"

    item = {"title": "New AI release", "url": "https://ai.example.com", "summary": "Great news"}
    tpl = "{title} - {link}"
    formatted = _format_post_content(tpl, item)
    assert formatted == "New AI release - https://ai.example.com"


@pytest.mark.asyncio
async def test_sync_feed_items_creates_post_and_deduplicates():
    accounts = [{"id": "acc_1", "username": "brand_tw", "platform": "twitter", "workspace_id": "ws_1"}]
    feed = {
        "id": "feed_1",
        "workspace_id": "ws_1",
        "feed_url": "https://technews.example.com/rss",
        "title": "Tech News",
        "auto_publish": True,
        "target_account_ids": ["acc_1"],
        "post_status": "scheduled",
        "post_template": "{title} {link}",
        "use_timeslot": False,
    }
    fake_db = _FakeDB(accounts=accounts, feeds=[feed])

    with patch("api.routes.rss_feeds.fetch_feed") as mock_fetch:
        mock_fetch.return_value = (
            {"title": "Tech News", "description": ""},
            [
                {
                    "guid": "item_1",
                    "url": "https://technews.example.com/item1",
                    "title": "Item 1",
                    "summary": "Summary 1",
                    "pub_date": datetime.now(timezone.utc),
                    "media_urls": [],
                }
            ],
            "etag1",
            "mod1",
            False,
        )
        stats = await _sync_feed_items(fake_db, feed, user_id="user_1", workspace_id="ws_1")
        assert stats["discovered"] == 1
        assert stats["scheduled"] == 1

        # Check post document creation
        assert len(fake_db.posts.items) == 1
        post = fake_db.posts.items[0]
        assert post["id"] is not None
        assert post["post_id"] == post["id"]
        assert post["version"] == 1
        assert post["source"] == "rss_automation"
        assert post["content"] == "Item 1 https://technews.example.com/item1"
        assert "twitter" in post["platforms"]
        assert "acc_1" in post["account_results"]

        # Run sync again with same items -> should deduplicate
        stats_second = await _sync_feed_items(fake_db, feed, user_id="user_1", workspace_id="ws_1")
        assert stats_second["discovered"] == 0
        assert stats_second["scheduled"] == 0
        assert len(fake_db.posts.items) == 1  # No duplicate post created


@pytest.mark.asyncio
async def test_share_rss_item_endpoint():
    item = {
        "id": "item_123",
        "feed_id": "feed_1",
        "workspace_id": "ws_1",
        "title": "Exciting Article",
        "url": "https://example.com/article",
        "summary": "Article summary",
        "media_urls": ["https://example.com/thumb.jpg"],
    }
    accounts = [{"id": "acc_li", "username": "brand_li", "platform": "linkedin", "workspace_id": "ws_1"}]
    fake_db = _FakeDB(items=[item], accounts=accounts)
    user = {"user_id": "user_1", "default_workspace_id": "ws_1"}

    req = ShareItemRequest(
        target_account_ids=["acc_li"],
        custom_content="Must read article: https://example.com/article",
        use_timeslot=False,
    )

    res = await share_rss_item_to_social("item_123", req, current_user=user, db=fake_db)
    assert res["shared"] is True
    assert len(fake_db.posts.items) == 1
    post = fake_db.posts.items[0]
    assert post["content"] == "Must read article: https://example.com/article"
    assert post["platforms"] == ["linkedin"]
    assert post["media_url"] == "https://example.com/thumb.jpg"
    assert post["source"] == "rss_manual_share"


@pytest.mark.asyncio
async def test_sync_feed_keyword_filtering():
    accounts = [{"id": "acc_1", "username": "brand_tw", "platform": "twitter", "workspace_id": "ws_1"}]
    feed = {
        "id": "feed_kw",
        "workspace_id": "ws_1",
        "feed_url": "https://technews.example.com/rss",
        "title": "Tech News",
        "auto_publish": True,
        "target_account_ids": ["acc_1"],
        "post_status": "scheduled",
        "include_keywords": ["artificial intelligence", "deep learning"],
        "exclude_keywords": ["crypto"],
        "use_timeslot": False,
    }
    fake_db = _FakeDB(accounts=accounts, feeds=[feed])

    with patch("api.routes.rss_feeds.fetch_feed") as mock_fetch:
        mock_fetch.return_value = (
            {"title": "Tech News", "description": ""},
            [
                {
                    "guid": "item_include",
                    "url": "https://technews.example.com/ai",
                    "title": "New Deep Learning Breakthrough",
                    "summary": "Massive scaling achieved.",
                    "pub_date": datetime.now(timezone.utc),
                },
                {
                    "guid": "item_exclude",
                    "url": "https://technews.example.com/crypto",
                    "title": "Deep Learning with Crypto",
                    "summary": "Bitcoin and AI merge.",
                    "pub_date": datetime.now(timezone.utc),
                },
                {
                    "guid": "item_no_match",
                    "url": "https://technews.example.com/cooking",
                    "title": "Summer recipes",
                    "summary": "Tasty meals.",
                    "pub_date": datetime.now(timezone.utc),
                },
            ],
            "etag2",
            "mod2",
            False,
        )
        stats = await _sync_feed_items(fake_db, feed, user_id="user_1", workspace_id="ws_1")
        assert stats["discovered"] == 3
        assert stats["scheduled"] == 1  # only item_include scheduled

        # Check items statuses
        items_by_guid = {i["guid"]: i for i in fake_db.rss_feed_items.items}
        assert items_by_guid["item_include"]["status"] == "scheduled"
        assert items_by_guid["item_exclude"]["status"] == "skipped_keyword"
        assert items_by_guid["item_no_match"]["status"] == "skipped_keyword"


@pytest.mark.asyncio
async def test_validate_feed_endpoint():
    with patch("api.routes.rss_feeds.fetch_feed") as mock_fetch:
        mock_fetch.return_value = (
            {"title": "Tech Weekly", "description": "Weekly digest", "site_url": "https://tech.example.com", "icon_url": None},
            [
                {
                    "guid": "g1",
                    "url": "https://tech.example.com/1",
                    "title": "Article 1",
                    "summary": "Summary 1",
                    "pub_date": datetime.now(timezone.utc),
                }
            ],
            "e1",
            "m1",
            False,
        )
        req = ValidateFeedRequest(feed_url="https://tech.example.com/feed")
        user = {"user_id": "u1", "default_workspace_id": "ws1"}
        res = await validate_rss_feed(req, current_user=user)
        assert res.valid is True
        assert res.title == "Tech Weekly"
        assert len(res.sample_items) == 1
        assert res.sample_items[0].title == "Article 1"


@pytest.mark.asyncio
async def test_crud_rss_feed_endpoints():
    fake_db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws1"}

    with patch("api.routes.rss_feeds.fetch_feed") as mock_fetch:
        mock_fetch.return_value = (
            {"title": "Tech Feed", "description": "Tech news", "site_url": "https://tech.example.com", "icon_url": None},
            [],
            "etag",
            "mod",
            False,
        )
        # Create
        create_req = CreateFeedRequest(
            feed_url="https://tech.example.com/feed.xml",
            title="My Tech Blog",
            target_account_ids=["acc_1"],
            auto_publish=True,
        )
        created = await create_rss_feed(create_req, current_user=user, db=fake_db)
        feed_id = created["feed"]["id"]
        assert feed_id is not None
        assert created["feed"]["title"] == "My Tech Blog"

        # List
        feed_list = await list_rss_feeds(current_user=user, db=fake_db)
        assert len(feed_list["feeds"]) == 1

        # Update
        patch_req = UpdateFeedRequest(title="Updated Title", status="paused")
        updated = await update_rss_feed(feed_id, patch_req, current_user=user, db=fake_db)
        assert updated["title"] == "Updated Title"
        assert updated["status"] == "paused"

        # Delete
        del_res = await delete_rss_feed(feed_id, current_user=user, db=fake_db)
        assert del_res["deleted"] is True
        assert len(fake_db.rss_feeds.items) == 0

