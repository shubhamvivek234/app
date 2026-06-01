import pytest

from api.routes import analytics


@pytest.mark.asyncio
async def test_analytics_instagram_report_merges_reach_series_across_accounts(monkeypatch):
    async def fake_load_social_accounts(db, user_id, platform, account_id):
        assert platform == "instagram"
        return [
            {
                "id": "ig_1",
                "account_id": "ig_1",
                "platform": "instagram",
                "platform_user_id": "acct_a",
                "platform_username": "alpha",
                "display_name": "Alpha",
                "access_token": "enc-a",
                "user_id": user_id,
            },
            {
                "id": "ig_2",
                "account_id": "ig_2",
                "platform": "instagram",
                "platform_user_id": "acct_b",
                "platform_username": "beta",
                "display_name": "Beta",
                "access_token": "enc-b",
                "user_id": user_id,
            },
        ]

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return []

    class FakeInstagramAuth:
        async def fetch_feed(self, access_token, user_id, limit=100):
            return []

        async def fetch_engagement(self, access_token, user_id, days=None):
            if user_id == "acct_a":
                return {
                    "followers": 120,
                    "following": 12,
                    "posts_count": 8,
                    "followers_growth": 0,
                    "reach": 18,
                    "impressions": 25,
                    "profile_views": 6,
                    "reach_series": [
                        {"date": "2026-05-20", "count": 7},
                        {"date": "2026-05-21", "count": 11},
                    ],
                    "impressions_series": [
                        {"date": "2026-05-20", "count": 10},
                        {"date": "2026-05-21", "count": 15},
                    ],
                    "profile_views_series": [
                        {"date": "2026-05-20", "count": 2},
                        {"date": "2026-05-21", "count": 4},
                    ],
                }
            return {
                "followers": 80,
                "following": 6,
                "posts_count": 5,
                "followers_growth": 0,
                "reach": 13,
                "impressions": 20,
                "profile_views": 3,
                "reach_series": [
                    {"date": "2026-05-20", "count": 5},
                    {"date": "2026-05-22", "count": 8},
                ],
                "impressions_series": [
                    {"date": "2026-05-20", "count": 8},
                    {"date": "2026-05-22", "count": 12},
                ],
                "profile_views_series": [
                    {"date": "2026-05-20", "count": 1},
                    {"date": "2026-05-22", "count": 2},
                ],
            }

        async def fetch_follower_growth(self, access_token, user_id, days=None):
            return {
                "supported": True,
                "growth": 0,
                "growth_series": [],
            }

        async def fetch_demographics(self, access_token, user_id, metric="follower_demographics", timeframe=None):
            return {
                "supported": False,
                "metric": metric,
                "timeframe": timeframe,
                "age": [],
                "gender": [],
                "cities": [],
                "countries": [],
                "error": "Could not fetch demographics",
            }

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr("backend.app.social.instagram.InstagramAuth", FakeInstagramAuth)

    report = await analytics.analytics_instagram_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id=None,
    )

    assert report["supported"] is True
    assert report["summary"]["reach"] == 31
    assert report["summary"]["impressions"] == 45
    assert report["summary"]["profile_views"] == 9
    assert report["reach"]["reach_series"] == [
        {"date": "2026-05-20", "count": 12},
        {"date": "2026-05-21", "count": 11},
        {"date": "2026-05-22", "count": 8},
    ]
    assert report["reach"]["impressions_series"] == [
        {"date": "2026-05-20", "count": 18},
        {"date": "2026-05-21", "count": 15},
        {"date": "2026-05-22", "count": 12},
    ]
    assert report["reach"]["profile_views_series"] == [
        {"date": "2026-05-20", "count": 3},
        {"date": "2026-05-21", "count": 4},
        {"date": "2026-05-22", "count": 2},
    ]


@pytest.mark.asyncio
async def test_analytics_instagram_report_returns_empty_reach_series_when_no_daily_insights(monkeypatch):
    async def fake_load_social_accounts(db, user_id, platform, account_id):
        return [
            {
                "id": "ig_1",
                "account_id": "ig_1",
                "platform": "instagram",
                "platform_user_id": "acct_a",
                "platform_username": "alpha",
                "display_name": "Alpha",
                "access_token": "enc-a",
                "user_id": user_id,
            }
        ]

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return []

    class FakeInstagramAuth:
        async def fetch_feed(self, access_token, user_id, limit=100):
            return []

        async def fetch_engagement(self, access_token, user_id, days=None):
            return {
                "followers": 0,
                "following": 0,
                "posts_count": 0,
                "followers_growth": 0,
                "reach": 0,
                "impressions": 0,
                "profile_views": 0,
                "reach_series": [],
                "impressions_series": [],
                "profile_views_series": [],
            }

        async def fetch_follower_growth(self, access_token, user_id, days=None):
            return {
                "supported": False,
                "growth": 0,
                "growth_series": [],
            }

        async def fetch_demographics(self, access_token, user_id, metric="follower_demographics", timeframe=None):
            return {
                "supported": False,
                "metric": metric,
                "timeframe": timeframe,
                "age": [],
                "gender": [],
                "cities": [],
                "countries": [],
                "error": "Could not fetch demographics",
            }

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr("backend.app.social.instagram.InstagramAuth", FakeInstagramAuth)

    report = await analytics.analytics_instagram_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id="ig_1",
    )

    assert report["supported"] is True
    assert report["summary"]["reach"] == 0
    assert report["summary"]["impressions"] == 0
    assert report["summary"]["profile_views"] == 0
    assert report["reach"] == {
        "reach_series": [],
        "impressions_series": [],
        "profile_views_series": [],
    }
    assert report["audience"]["follower_growth_supported"] is False
    assert report["audience"]["demographics_supported"] is False


@pytest.mark.asyncio
async def test_analytics_instagram_report_includes_audience_diagnostics(monkeypatch):
    async def fake_load_social_accounts(db, user_id, platform, account_id):
        return [
            {
                "id": "ig_1",
                "account_id": "ig_1",
                "platform": "instagram",
                "platform_user_id": "acct_a",
                "platform_username": "alpha",
                "display_name": "Alpha",
                "access_token": "enc-a",
                "user_id": user_id,
            }
        ]

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return []

    class FakeInstagramAuth:
        async def fetch_feed(self, access_token, user_id, limit=100):
            return []

        async def fetch_engagement(self, access_token, user_id, days=None):
            return {
                "followers": 10,
                "following": 2,
                "posts_count": 1,
                "followers_growth": 0,
                "reach": 0,
                "impressions": 0,
                "profile_views": 0,
                "reach_series": [],
                "impressions_series": [],
                "profile_views_series": [],
            }

        async def fetch_follower_growth(self, access_token, user_id, days=None):
            return {
                "supported": False,
                "source": None,
                "growth": 0,
                "growth_series": [],
                "error": "follower_count: unavailable; follows_and_unfollows: unavailable",
                "error_type": "empty_response",
            }

        async def fetch_demographics(self, access_token, user_id, metric="follower_demographics", timeframe=None):
            return {
                "supported": False,
                "metric": metric,
                "timeframe": timeframe,
                "age": [],
                "gender": [],
                "cities": [],
                "countries": [],
                "error": f"{metric} unavailable",
                "error_type": "api_rejected" if metric != "follower_demographics" else "empty_response",
            }

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr("backend.app.social.instagram.InstagramAuth", FakeInstagramAuth)

    report = await analytics.analytics_instagram_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id="ig_1",
    )

    assert report["supported"] is True
    assert report["audience"]["follower_growth_supported"] is False
    assert "follower_count" in report["audience"]["follower_growth_error"]
    assert report["audience"]["audience_unavailable_message"] is not None
    assert report["audience"]["demographics_supported"] is False
    assert report["audience"]["demographics_error_details"][0]["metric"] == "follower_demographics"
    assert report["audience"]["demographics_error_details"][0]["error_type"] == "empty_response"
