from datetime import datetime, timezone

import pytest

from api.routes import analytics


def _account(user_id="user_1", platform="instagram", account_id="acct_1", username=None):
    return {
        "id": account_id,
        "account_id": account_id,
        "platform": platform,
        "platform_user_id": f"{account_id}-platform",
        "platform_username": username or f"{platform}_{account_id}",
        "display_name": f"{platform.title()} {account_id}",
        "picture_url": f"https://cdn.example/{account_id}.jpg",
        "access_token": "enc-token",
        "user_id": user_id,
    }


@pytest.mark.asyncio
async def test_publish_feed_supports_multi_account_selection_and_live_metadata(monkeypatch):
    async def fake_load_social_accounts_by_ids(db, user_id, account_ids, platform=None):
        assert user_id == "user_1"
        assert platform == "instagram"
        assert account_ids == ["ig_1", "ig_2"]
        return [
            _account(platform="instagram", account_id="ig_1", username="alpha"),
            _account(platform="instagram", account_id="ig_2", username="beta"),
        ]

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        post_id = f"{account['account_id']}-post"
        return (
            [
                {
                    "id": post_id,
                    "platform_post_id": post_id,
                    "content": f"Caption {post_id}",
                    "media_url": f"https://cdn.example/{post_id}.jpg",
                    "media_type": "IMAGE",
                    "post_type": "IMAGE",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "permalink": f"https://example.com/{post_id}",
                    "likes": 12,
                    "comments_count": 3,
                    "shares": 1,
                    "views": None,
                }
            ],
            {},
        )

    monkeypatch.setattr(analytics, "_load_social_accounts_by_ids", fake_load_social_accounts_by_ids)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="instagram",
        account_id=None,
        account_ids_param="ig_1,ig_2",
        limit=50,
        refresh=False,
    )

    assert len(report["posts"]) == 2
    assert report["warnings"] == []
    assert report["errors"] == []
    assert report["meta"]["filtered_accounts"] == 2
    assert report["meta"]["live_accounts"] == 2
    assert report["meta"]["fallback_accounts"] == 0
    first = report["posts"][0]
    assert first["platform_post_id"]
    assert first["account_picture"].startswith("https://cdn.example/")
    assert first["account_display_name"].startswith("Instagram")
    assert first["source_mode"] == "live"
    assert first["metric_support"]["likes"]["supported"] is True
    assert first["metric_support"]["views"]["supported"] is False


@pytest.mark.asyncio
async def test_publish_feed_prefers_live_account_picture_metadata(monkeypatch):
    stale_picture = "https://cdn.example/stale.jpg"
    fresh_picture = "https://cdn.example/fresh.jpg"

    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        account = _account(platform="instagram", account_id="ig_1", username="tee_theory")
        account["picture_url"] = stale_picture
        return ([account], False)

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return (
            [
                {
                    "id": "ig_1-post",
                    "platform_post_id": "ig_1-post",
                    "content": "Caption",
                    "media_url": "https://cdn.example/post.jpg",
                    "media_type": "IMAGE",
                    "post_type": "IMAGE",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "permalink": "https://example.com/ig_1-post",
                    "likes": 2,
                    "comments_count": 1,
                    "shares": 0,
                    "views": None,
                }
            ],
            {
                "display_name": "Fresh Name",
                "picture_url": fresh_picture,
            },
        )

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="instagram",
        account_id="ig_1",
        account_ids_param=None,
        limit=50,
        refresh=False,
    )

    assert report["posts"][0]["account_picture"] == fresh_picture
    assert report["posts"][0]["account_display_name"] == "Fresh Name"
    assert report["connected_accounts"][0]["picture_url"] == fresh_picture


@pytest.mark.asyncio
async def test_publish_feed_marks_db_fallback_metrics_unsupported(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return ([_account(platform="tiktok", account_id="tt_1", username="tokalpha")], False)

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return [], {}

    async def fake_fetch_db_published_posts(db, user_id, account, limit=50):
        return [
            {
                "id": "fallback-1",
                "platform_post_id": "fallback-1",
                "content": "Fallback post",
                "media_url": "https://cdn.example/fallback.jpg",
                "media_type": "VIDEO",
                "post_type": "video",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "views": 0,
                "permalink": "https://example.com/fallback-1",
                "source_mode": "db_fallback",
            }
        ]

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_published_posts)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="tiktok",
        account_id="tt_1",
        account_ids_param=None,
        limit=50,
        refresh=False,
    )

    assert len(report["posts"]) == 1
    assert report["posts"][0]["source_mode"] == "db_fallback"
    assert report["posts"][0]["metric_support"]["likes"]["supported"] is False
    assert report["warnings"][0]["type"] == "fallback_used"
    assert report["meta"]["fallback_accounts"] == 1
    assert report["errors"] == []


@pytest.mark.asyncio
async def test_publish_feed_classifies_provider_errors_without_no_posts_pseudo_error(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return ([_account(platform="twitter", account_id="tw_1", username="birdy")], False)

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        raise Exception("CreditsDepleted")

    async def fake_fetch_db_published_posts(db, user_id, account, limit=50):
        return []

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_published_posts)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="twitter",
        account_id="tw_1",
        account_ids_param=None,
        limit=50,
        refresh=False,
    )

    assert report["posts"] == []
    assert len(report["errors"]) == 1
    assert report["errors"][0]["type"] == "credits_depleted"
    assert report["warnings"] == []
    assert "No recent posts were returned" not in report["errors"][0]["error"]
    assert report["message"] == "We could not load recent posts for one or more selected accounts."


@pytest.mark.asyncio
async def test_publish_feed_empty_state_returns_clean_message_without_errors(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return ([_account(platform="instagram", account_id="ig_1", username="alpha")], False)

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return [], {}

    async def fake_fetch_db_published_posts(db, user_id, account, limit=50):
        return []

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_published_posts)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="instagram",
        account_id="ig_1",
        account_ids_param=None,
        limit=50,
        refresh=False,
    )

    assert report["posts"] == []
    assert report["errors"] == []
    assert report["warnings"] == []
    assert report["message"] == "No published posts found for the selected filters."


@pytest.mark.asyncio
async def test_publish_feed_local_history_only_platform_returns_specific_empty_message(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return ([_account(platform="linkedin", account_id="li_1", username="brand-page")], False)

    async def fake_fetch_db_published_posts(db, user_id, account, limit=50):
        return []

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_published_posts)

    report = await analytics.publish_feed(
        current_user={"user_id": "user_1"},
        db=object(),
        platform="linkedin",
        account_id="li_1",
        account_ids_param=None,
        limit=50,
        refresh=False,
    )

    assert report["posts"] == []
    assert report["errors"] == []
    assert report["warnings"][0]["type"] == "local_history_only"
    assert "LinkedIn feed can only show posts published from Unravler right now. None were found for the selected filters." == report["message"]
