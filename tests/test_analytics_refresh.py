from datetime import datetime, timedelta, timezone

import pytest

from api.routes import analytics


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, length=None):
        return list(self._docs)


class _FakePostsCollection:
    def __init__(
        self,
        *,
        published_count=0,
        scheduled_count=0,
        failed_count=0,
        platform_docs=None,
        type_docs=None,
        timeline_docs=None,
    ):
        self.published_count = published_count
        self.scheduled_count = scheduled_count
        self.failed_count = failed_count
        self.platform_docs = platform_docs or []
        self.type_docs = type_docs or []
        self.timeline_docs = timeline_docs or []

    async def count_documents(self, query):
        status = query.get("status")
        if status == "scheduled":
            return self.scheduled_count
        if status == "failed":
            return self.failed_count
        if status == "published":
            return self.published_count
        return 0

    def aggregate(self, pipeline):
        if any(stage.get("$unwind") == "$platforms" for stage in pipeline if isinstance(stage, dict)):
            return _FakeCursor(self.platform_docs)

        group_id = next(
            (stage.get("$group", {}).get("_id") for stage in pipeline if isinstance(stage, dict) and "$group" in stage),
            None,
        )
        if isinstance(group_id, dict) and "$substr" in group_id:
            return _FakeCursor(self.timeline_docs)

        return _FakeCursor(self.type_docs)


class _FakeDB:
    def __init__(self, posts):
        self.posts = posts


def _account(user_id="user_1", platform="youtube", account_id="yt_1"):
    return {
        "id": account_id,
        "account_id": account_id,
        "platform": platform,
        "platform_user_id": f"{account_id}-platform",
        "platform_username": f"{platform}_account",
        "display_name": f"{platform.title()} Account",
        "access_token": "enc-token",
        "user_id": user_id,
    }


@pytest.mark.asyncio
async def test_analytics_overview_refresh_prefers_provider_counts_for_selected_scope(monkeypatch):
    today = datetime.now(timezone.utc).isoformat()

    async def fake_load_social_accounts(db, user_id, platform, account_id):
        assert platform == "youtube"
        assert account_id == "yt_1"
        return [_account(user_id=user_id, platform=platform, account_id=account_id)]

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return (
            [
                {
                    "id": "video-1",
                    "timestamp": today,
                    "media_type": "VIDEO",
                }
            ],
            {"followers": 125, "following": 10, "posts_count": 4},
        )

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)

    fake_db = _FakeDB(
        _FakePostsCollection(
            published_count=9,
            scheduled_count=2,
            failed_count=1,
            platform_docs=[{"_id": "youtube", "count": 9}],
            type_docs=[{"_id": "video", "count": 9}],
        )
    )

    report = await analytics.analytics_overview(
        current_user={"user_id": "user_1"},
        db=fake_db,
        days=30,
        platform="youtube",
        account_id="yt_1",
        refresh=True,
    )

    assert report["published_in_period"] == 1
    assert report["scheduled_count"] == 2
    assert report["failed_count"] == 1
    assert report["platform_counts"] == {"youtube": 1}
    assert report["type_counts"]["video"] == 1


@pytest.mark.asyncio
async def test_analytics_timeline_refresh_prefers_provider_timeline_for_selected_scope(monkeypatch):
    in_window = datetime.now(timezone.utc)
    out_of_window = in_window - timedelta(days=60)

    async def fake_load_social_accounts(db, user_id, platform, account_id):
        return [_account(user_id=user_id, platform=platform, account_id=account_id)]

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return (
            [
                {
                    "id": "video-1",
                    "timestamp": in_window.isoformat(),
                    "media_type": "VIDEO",
                },
                {
                    "id": "video-2",
                    "timestamp": out_of_window.isoformat(),
                    "media_type": "VIDEO",
                },
            ],
            {},
        )

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)

    fake_db = _FakeDB(
        _FakePostsCollection(
            timeline_docs=[{"_id": "2026-05-01", "count": 9}],
        )
    )

    report = await analytics.analytics_timeline(
        current_user={"user_id": "user_1"},
        db=fake_db,
        days=30,
        platform="youtube",
        account_id="yt_1",
        refresh=True,
    )

    assert report["timeline"] == [{"date": in_window.date().isoformat(), "count": 1}]


@pytest.mark.asyncio
async def test_analytics_overview_refresh_without_platform_keeps_aggregate_db_counts(monkeypatch):
    async def fake_load_social_accounts(db, user_id, platform, account_id):
        assert platform is None
        return [_account(user_id=user_id, platform="youtube", account_id="yt_1")]

    async def fake_fetch_account_feed_and_stats(db, account, days=None):
        return (
            [
                {
                    "id": "video-1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "media_type": "VIDEO",
                }
            ],
            {"followers": 125, "following": 10, "posts_count": 4},
        )

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_account_feed_and_stats", fake_fetch_account_feed_and_stats)

    fake_db = _FakeDB(
        _FakePostsCollection(
            published_count=9,
            scheduled_count=2,
            failed_count=1,
            platform_docs=[{"_id": "youtube", "count": 9}],
            type_docs=[{"_id": "video", "count": 9}],
        )
    )

    report = await analytics.analytics_overview(
        current_user={"user_id": "user_1"},
        db=fake_db,
        days=30,
        platform=None,
        account_id=None,
        refresh=True,
    )

    assert report["published_in_period"] == 9
    assert report["platform_counts"] == {"youtube": 9}
    assert report["type_counts"]["video"] == 9
