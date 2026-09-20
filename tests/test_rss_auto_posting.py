"""Unit tests for RSS auto-posting backfill toggles and AI picture generator."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from api.routes.rss_feeds import CreateFeedRequest, _sync_feed_items
from utils.ai_image_service import generate_banner_image


def test_create_feed_request_defaults():
    req = CreateFeedRequest(feed_url="https://news.ycombinator.com/rss")
    assert req.sync_current_latest is False
    assert req.generate_ai_image is False
    assert req.auto_publish is True

    req_custom = CreateFeedRequest(
        feed_url="https://techcrunch.com/feed/",
        sync_current_latest=True,
        generate_ai_image=True,
    )
    assert req_custom.sync_current_latest is True
    assert req_custom.generate_ai_image is True


def test_ai_image_service_generates_url():
    title = "OpenAI Announces GPT-5 with Autonomous Agents"
    img_url = generate_banner_image(title, "Detailed announcement of next generation AI")
    assert img_url.startswith("https://image.pollinations.ai/prompt/")
    assert "width=1200" in img_url
    assert "height=675" in img_url


@pytest.mark.asyncio
async def test_initial_sync_without_backfill_does_not_schedule():
    """When sync_current_latest is False on initial sync, discovered items are not scheduled."""
    feed = {
        "id": "feed_1",
        "feed_url": "https://example.com/rss",
        "auto_publish": True,
        "sync_current_latest": False,
        "generate_ai_image": False,
        "target_account_ids": ["acc_1"],
        "post_template": "{title}",
    }

    mock_db = AsyncMock()
    mock_db.rss_feeds.update_one = AsyncMock()
    mock_db.rss_feed_items.find_one = AsyncMock(return_value=None)
    mock_db.rss_feed_items.insert_one = AsyncMock()
    mock_db.posts.insert_one = AsyncMock()
    
    # Mock accounts
    mock_acc_cursor = AsyncMock()
    mock_acc_cursor.to_list = AsyncMock(return_value=[{"id": "acc_1", "platform": "twitter"}])
    mock_db.social_accounts.find = lambda *args, **kwargs: mock_acc_cursor

    mock_items = [
        {"guid": "item_1", "title": "Article 1", "url": "https://example.com/1"},
        {"guid": "item_2", "title": "Article 2", "url": "https://example.com/2"},
    ]

    with patch("api.routes.rss_feeds.fetch_feed", AsyncMock(return_value=({}, mock_items, "etag1", "mod1", False))):
        stats = await _sync_feed_items(
            mock_db, feed, user_id="u1", workspace_id="w1", is_initial_sync=True
        )

    # 2 items discovered, 0 scheduled because sync_current_latest was False!
    assert stats["discovered"] == 2
    assert stats["scheduled"] == 0
    assert mock_db.posts.insert_one.call_count == 0


@pytest.mark.asyncio
async def test_initial_sync_with_sync_current_latest_schedules_single_newest():
    """When sync_current_latest is True on initial sync, only the newest item is scheduled."""
    feed = {
        "id": "feed_2",
        "feed_url": "https://example.com/rss",
        "auto_publish": True,
        "sync_current_latest": True,
        "generate_ai_image": True,
        "target_account_ids": ["acc_1"],
        "post_template": "{title}",
        "post_status": "scheduled",
    }

    mock_db = AsyncMock()
    mock_db.rss_feeds.update_one = AsyncMock()
    mock_db.rss_feed_items.find_one = AsyncMock(return_value=None)
    mock_db.rss_feed_items.insert_one = AsyncMock()
    mock_db.posts.insert_one = AsyncMock()

    mock_acc_cursor = AsyncMock()
    mock_acc_cursor.to_list = AsyncMock(return_value=[{"id": "acc_1", "platform": "twitter"}])
    mock_db.social_accounts.find = lambda *args, **kwargs: mock_acc_cursor

    mock_items = [
        {"guid": "newest_item", "title": "Newest Article", "url": "https://example.com/new"},
        {"guid": "old_item", "title": "Old Article", "url": "https://example.com/old"},
    ]

    with patch("api.routes.rss_feeds.fetch_feed", AsyncMock(return_value=({}, mock_items, "etag2", "mod2", False))):
        stats = await _sync_feed_items(
            mock_db, feed, user_id="u1", workspace_id="w1", is_initial_sync=True
        )

    assert stats["discovered"] == 2
    # Only newest item scheduled!
    assert stats["scheduled"] == 1
    assert mock_db.posts.insert_one.call_count == 1
    created_post = mock_db.posts.insert_one.call_args[0][0]
    # AI image generated since item had no media and generate_ai_image is True
    assert len(created_post["media_urls"]) == 1
    assert created_post["media_urls"][0].startswith("https://image.pollinations.ai/prompt/")
