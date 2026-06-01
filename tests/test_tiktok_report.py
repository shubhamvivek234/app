from datetime import datetime, timedelta, timezone

import pytest

from api.routes import analytics
from celery_workers.tasks import analytics as analytics_tasks


@pytest.mark.asyncio
async def test_analytics_tiktok_report_merges_snapshots_and_live_totals(monkeypatch):
    today = datetime.now(timezone.utc).date().isoformat()
    earlier = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()

    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        assert platform == "tiktok"
        return (
            [
                {
                    "id": "tt_1",
                    "account_id": "tt_1",
                    "platform": "tiktok",
                    "platform_user_id": "tiktok-user-1",
                    "platform_username": "tokalpha",
                    "display_name": "Tok Alpha",
                    "access_token": "enc-a",
                    "user_id": user_id,
                }
            ],
            False,
        )

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return []

    async def fake_load_snapshots(db, account_id, since_date=None):
        return [
            {
                "snapshot_date": earlier,
                "follower_count": 100,
                "likes_count": 240,
                "video_count": 4,
            }
        ]

    async def fake_load_previous_snapshot(db, account_id, before_date):
        return {"snapshot_date": earlier, "follower_count": 100}

    class FakeTikTokAuth:
        async def get_user_profile(self, access_token):
            return {
                "id": "tiktok-user-1",
                "name": "Tok Alpha",
                "username": "tokalpha",
                "followers_count": 125,
                "following_count": 12,
                "likes_count": 310,
                "video_count": 6,
            }

        async def fetch_posts(self, access_token, limit=100):
            return [
                {
                    "platform_post_id": "video-2",
                    "content": "Big post",
                    "media_url": "https://cdn.example/video-2.jpg",
                    "media_type": "VIDEO",
                    "post_url": "https://tiktok.example/video-2",
                    "metrics": {"likes": 20, "comments": 5, "shares": 4, "views": 200},
                    "published_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "platform_post_id": "video-1",
                    "content": "Second post",
                    "media_url": "https://cdn.example/video-1.jpg",
                    "media_type": "VIDEO",
                    "post_url": "https://tiktok.example/video-1",
                    "metrics": {"likes": 10, "comments": 2, "shares": 1, "views": 120},
                    "published_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                },
            ]

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "load_tiktok_analytics_snapshots", fake_load_snapshots)
    monkeypatch.setattr(analytics, "load_latest_tiktok_snapshot_before", fake_load_previous_snapshot)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr("backend.app.social.tiktok.TikTokAuth", FakeTikTokAuth)

    report = await analytics.analytics_tiktok_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id="tt_1",
    )

    assert report["supported"] is True
    assert report["source_mode"] == "live"
    assert report["summary"]["followers_total"] == 125
    assert report["summary"]["following_total"] == 12
    assert report["summary"]["likes_total"] == 310
    assert report["summary"]["videos_total"] == 6
    assert report["summary"]["net_followers"] == 25
    assert report["summary"]["post_views_total"] == 320
    assert report["overview"]["followers_series"] == [
        {"date": earlier, "count": 100},
        {"date": today, "count": 125},
    ]
    assert report["overview"]["profile_views_supported"] is False
    assert "profile-view analytics" in report["overview"]["profile_views_message"]
    assert report["content"]["top_posts_by_views"][0]["id"] == "video-2"
    assert report["content"]["top_posts_by_likes"][0]["likes"] == 20
    assert report["viewers"]["viewer_metrics_supported"] is False
    assert report["followers"]["demographics_supported"] is False


@pytest.mark.asyncio
async def test_analytics_tiktok_report_uses_db_fallback_when_video_list_unavailable(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return (
            [
                {
                    "id": "tt_1",
                    "account_id": "tt_1",
                    "platform": "tiktok",
                    "platform_user_id": "tiktok-user-1",
                    "platform_username": "tokalpha",
                    "display_name": "Tok Alpha",
                    "access_token": "enc-a",
                    "user_id": user_id,
                }
            ],
            False,
        )

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return [
            {
                "id": "fallback-post-1",
                "content": "Fallback post",
                "media_url": "https://cdn.example/fallback.jpg",
                "media_type": "VIDEO",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "views": 0,
                "permalink": "https://tiktok.example/fallback-post-1",
            }
        ]

    async def fake_load_snapshots(db, account_id, since_date=None):
        return []

    async def fake_load_previous_snapshot(db, account_id, before_date):
        return None

    class FakeTikTokAuth:
        async def get_user_profile(self, access_token):
            return {
                "id": "tiktok-user-1",
                "name": "Tok Alpha",
                "username": "tokalpha",
                "followers_count": 10,
                "following_count": 2,
                "likes_count": 55,
                "video_count": 1,
            }

        async def fetch_posts(self, access_token, limit=100):
            return []

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "load_tiktok_analytics_snapshots", fake_load_snapshots)
    monkeypatch.setattr(analytics, "load_latest_tiktok_snapshot_before", fake_load_previous_snapshot)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr("backend.app.social.tiktok.TikTokAuth", FakeTikTokAuth)

    report = await analytics.analytics_tiktok_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id="tt_1",
    )

    assert report["supported"] is True
    assert report["source_mode"] == "db_fallback"
    assert report["summary"]["post_views_total"] == 0
    assert report["content"]["content_source_message"] is not None
    assert report["content"]["top_posts_by_views"][0]["id"] == "fallback-post-1"
    assert "fallback mode" in report["message"].lower()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self._docs)

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)


class _FakePostsCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, social_accounts_docs, posts_docs):
        self.social_accounts = _FakeCollection(social_accounts_docs)
        self.posts = _FakePostsCollection(posts_docs)


class _FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_refresh_tiktok_analytics_snapshots_uses_db_fallback(monkeypatch):
    stored_snapshots = []

    async def fake_store_snapshot(db, **kwargs):
        stored_snapshots.append(kwargs)

    class FakeTikTokAuth:
        async def get_user_profile(self, access_token):
            return {
                "id": "tiktok-user-1",
                "followers_count": 15,
                "following_count": 3,
                "likes_count": 40,
                "video_count": 2,
            }

        async def fetch_posts(self, access_token, limit=50):
            return []

    fake_db = _FakeDB(
        social_accounts_docs=[
            {
                "account_id": "tt_1",
                "id": "tt_1",
                "platform": "tiktok",
                "platform_user_id": "tiktok-user-1",
                "user_id": "user_1",
                "access_token": "enc-a",
            }
        ],
        posts_docs=[
            {
                "id": "post-1",
                "content": "Fallback TikTok post",
                "thumbnail_urls": ["https://cdn.example/thumb.jpg"],
                "media_urls": [],
                "video_url": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "published_at": datetime.now(timezone.utc).isoformat(),
                "platform_results": {
                    "tiktok": {
                        "status": "published",
                        "platform_post_id": "post-1",
                        "post_url": "https://tiktok.example/post-1",
                    }
                },
                "platform_post_urls": {"tiktok": "https://tiktok.example/post-1"},
                "status": "published",
            }
        ],
    )

    async def fake_get_client():
        return _FakeClient(fake_db)

    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setattr(analytics_tasks, "get_client", fake_get_client)
    monkeypatch.setattr(analytics_tasks, "decrypt", lambda value: "access-token")
    monkeypatch.setattr(analytics_tasks, "store_tiktok_analytics_snapshot", fake_store_snapshot)
    monkeypatch.setattr("backend.app.social.tiktok.TikTokAuth", FakeTikTokAuth)

    result = await analytics_tasks._async_refresh_tiktok_analytics_snapshots()

    assert result["snapshots_written"] == 1
    assert result["fallback_used"] == 1
    assert stored_snapshots[0]["source_mode"] == "db_fallback"
    assert stored_snapshots[0]["follower_count"] == 15
    assert stored_snapshots[0]["posts"][0]["content"] == "Fallback TikTok post"
