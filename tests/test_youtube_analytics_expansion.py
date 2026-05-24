from datetime import date

import pytest

from api.routes import analytics


def test_merge_named_weighted_metrics_uses_views_as_weight():
    rows = analytics._merge_named_weighted_metrics(
        [
            {"value": "SHORTS", "label": "Shorts", "views": 100, "engagedViews": 60, "averageViewPercentage": 70},
            {"value": "SHORTS", "label": "Shorts", "views": 300, "engagedViews": 150, "averageViewPercentage": 40},
        ],
        "value",
        ["views", "engagedViews"],
        ["averageViewPercentage"],
    )

    assert rows == [
        {
            "value": "SHORTS",
            "label": "Shorts",
            "views": 400,
            "engagedViews": 210,
            "averageViewPercentage": 47.5,
        }
    ]


def test_merge_youtube_watch_quality_series_weights_duration_and_percentage():
    merged = analytics._merge_youtube_watch_quality_series(
        [
            [
                {
                    "date": "2026-05-20",
                    "engaged_views": 10,
                    "views": 100,
                    "average_view_duration_seconds": 60,
                    "average_view_percentage": 50,
                }
            ],
            [
                {
                    "date": "2026-05-20",
                    "engaged_views": 15,
                    "views": 300,
                    "average_view_duration_seconds": 30,
                    "average_view_percentage": 25,
                }
            ],
        ]
    )

    assert merged == [
        {
            "date": "2026-05-20",
            "engaged_views": 25,
            "views": 400,
            "average_view_duration_seconds": 37.5,
            "average_view_percentage": 31.25,
        }
    ]


@pytest.mark.asyncio
async def test_analytics_youtube_report_includes_expansion_blocks(monkeypatch):
    async def fake_load_social_accounts_for_report(db, user_id, platform, account_id):
        return ([{
            "id": "yt_1",
            "account_id": "yt_1",
            "platform": "youtube",
            "platform_user_id": "UC123",
            "platform_username": "Prodcaster",
            "display_name": "Prodcaster",
            "access_token": "encrypted-token",
            "user_id": user_id,
        }], False)

    async def fake_fetch_db_posts(db, user_id, account, limit=100):
        return []

    async def fake_store_snapshot(*args, **kwargs):
        return None

    async def fake_load_snapshot(*args, **kwargs):
        return None

    class FakeGoogleAuth:
        async def get_channel_info(self, access_token):
            return {"id": "UC123", "subscribers": 120}

        async def fetch_youtube_engagement(self, access_token, channel_id, days=None):
            return {
                "subscribers": 120,
                "period_views": 500,
                "period_minutes_watched": 120.5,
                "period_likes": 18,
                "period_comments": 4,
                "period_shares": 3,
            }

        async def fetch_youtube_feed(self, access_token, channel_id, limit=100):
            return [
                {
                    "id": "vid_a",
                    "content": "Video A",
                    "media_url": "https://cdn.example.com/thumb-a.jpg",
                    "media_type": "VIDEO",
                    "timestamp": "2026-05-20T10:00:00Z",
                    "likes": 12,
                    "comments_count": 3,
                    "shares": 2,
                    "views": 220,
                    "permalink": "https://youtube.com/watch?v=vid_a",
                }
            ]

        async def query_channel_analytics_totals(self, access_token, metrics, start_date, end_date):
            if start_date == date(2026, 4, 1):
                if "engagedViews" in metrics:
                    return [{"engagedViews": 80, "averageViewDuration": 30, "averageViewPercentage": 35, "views": 200}]
                if "cardImpressions" in metrics:
                    return [{"cardImpressions": 10, "cardTeaserImpressions": 4, "cardClicks": 1, "cardTeaserClicks": 1}]
                return [{"likes": 6, "comments": 2, "shares": 1, "views": 180, "estimatedMinutesWatched": 40, "subscribersGained": 2, "subscribersLost": 1}]

            if "engagedViews" in metrics:
                return [{"engagedViews": 140, "averageViewDuration": 48, "averageViewPercentage": 52, "views": 400}]
            if "cardImpressions" in metrics:
                return [{"cardImpressions": 20, "cardTeaserImpressions": 8, "cardClicks": 3, "cardTeaserClicks": 2}]
            return [{"likes": 18, "comments": 4, "shares": 3, "views": 500, "estimatedMinutesWatched": 120.5}]

        async def query_channel_analytics_time_series(self, access_token, metrics, start_date, end_date, dimension="day"):
            if metrics == ["subscribersGained", "subscribersLost"]:
                return [
                    {"day": "2026-05-20", "subscribersGained": 2, "subscribersLost": 1},
                    {"day": "2026-05-21", "subscribersGained": 3, "subscribersLost": 0},
                ]
            if metrics == ["views", "estimatedMinutesWatched"]:
                return [
                    {"day": "2026-05-20", "views": 200, "estimatedMinutesWatched": 40.5},
                    {"day": "2026-05-21", "views": 300, "estimatedMinutesWatched": 80},
                ]
            if metrics == ["engagedViews", "averageViewDuration", "averageViewPercentage", "views"]:
                return [
                    {"day": "2026-05-20", "engagedViews": 60, "averageViewDuration": 42, "averageViewPercentage": 45, "views": 200},
                    {"day": "2026-05-21", "engagedViews": 80, "averageViewDuration": 52, "averageViewPercentage": 56, "views": 300},
                ]
            return []

        async def query_channel_dimension_breakdown(self, access_token, metrics, start_date, end_date, dimensions, filters=None, sort=None, max_results=None):
            if dimensions == ["video"]:
                if sort == ["-estimatedMinutesWatched"]:
                    return [
                        {"video": "vid_b", "views": 180, "estimatedMinutesWatched": 70, "likes": 8, "comments": 2, "shares": 1},
                        {"video": "vid_a", "views": 220, "estimatedMinutesWatched": 50, "likes": 12, "comments": 3, "shares": 2},
                    ]
                return [
                    {"video": "vid_a", "views": 220, "estimatedMinutesWatched": 50, "likes": 12, "comments": 3, "shares": 2},
                    {"video": "vid_b", "views": 180, "estimatedMinutesWatched": 70, "likes": 8, "comments": 2, "shares": 1},
                ]
            if dimensions == ["country"] and metrics == ["subscribersGained"]:
                return [{"country": "IN", "subscribersGained": 4}]
            if dimensions == ["country"] and metrics == ["views"]:
                return [{"country": "IN", "views": 320}, {"country": "US", "views": 180}]
            if dimensions == ["country"] and metrics == ["estimatedMinutesWatched"]:
                return [{"country": "IN", "estimatedMinutesWatched": 90.5}, {"country": "US", "estimatedMinutesWatched": 30}]
            if dimensions == ["insightTrafficSourceType"]:
                return [{"insightTrafficSourceType": "YT_SEARCH", "views": 220, "estimatedMinutesWatched": 55}]
            if dimensions == ["insightPlaybackLocationType"]:
                return [{"insightPlaybackLocationType": "WATCH", "views": 500, "estimatedMinutesWatched": 120.5}]
            if dimensions == ["operatingSystem"]:
                return [{"operatingSystem": "ANDROID", "views": 300, "estimatedMinutesWatched": 80}]
            if dimensions == ["deviceType"]:
                return [{"deviceType": "MOBILE", "views": 280}, {"deviceType": "DESKTOP", "views": 120}]
            if dimensions == ["subscribedStatus"]:
                return [
                    {"subscribedStatus": "UNSUBSCRIBED", "views": 350, "estimatedMinutesWatched": 100},
                    {"subscribedStatus": "SUBSCRIBED", "views": 50, "estimatedMinutesWatched": 20.5},
                ]
            if dimensions == ["creatorContentType"]:
                return [{"creatorContentType": "SHORTS", "views": 260, "estimatedMinutesWatched": 45, "engagedViews": 120, "averageViewDuration": 28, "averageViewPercentage": 63}]
            if dimensions == ["liveOrOnDemand"]:
                return [{"liveOrOnDemand": "ON_DEMAND", "views": 400, "estimatedMinutesWatched": 120.5, "engagedViews": 140, "averageViewDuration": 48, "averageViewPercentage": 52}]
            if dimensions == ["insightTrafficSourceDetail"]:
                return [{"insightTrafficSourceDetail": "social entangler", "views": 120, "estimatedMinutesWatched": 24}]
            if dimensions == ["ageGroup", "gender"]:
                return [
                    {"ageGroup": "AGE_18_24", "gender": "MALE", "viewerPercentage": 35},
                    {"ageGroup": "AGE_18_24", "gender": "FEMALE", "viewerPercentage": 15},
                    {"ageGroup": "AGE_25_34", "gender": "MALE", "viewerPercentage": 30},
                    {"ageGroup": "AGE_25_34", "gender": "FEMALE", "viewerPercentage": 20},
                ]
            if dimensions == ["sharingService"]:
                return [{"sharingService": "WHATS_APP", "shares": 9, "views": 70, "estimatedMinutesWatched": 10}]
            return []

        async def query_video_retention(self, access_token, video_id, start_date, end_date):
            return [
                {"elapsedVideoTimeRatio": 0.1, "audienceWatchRatio": 95, "relativeRetentionPerformance": 1.12},
                {"elapsedVideoTimeRatio": 0.5, "audienceWatchRatio": 62, "relativeRetentionPerformance": 0.91},
            ]

        async def fetch_video_details(self, access_token, video_ids):
            return {
                "vid_a": {
                    "snippet": {
                        "title": "Video A",
                        "publishedAt": "2026-05-20T10:00:00Z",
                        "thumbnails": {"high": {"url": "https://cdn.example.com/thumb-a.jpg"}},
                    },
                    "statistics": {"viewCount": "220", "likeCount": "12", "commentCount": "3"},
                },
                "vid_b": {
                    "snippet": {
                        "title": "Video B",
                        "publishedAt": "2026-05-18T08:00:00Z",
                        "thumbnails": {"high": {"url": "https://cdn.example.com/thumb-b.jpg"}},
                    },
                    "statistics": {"viewCount": "180", "likeCount": "8", "commentCount": "2"},
                },
            }

    monkeypatch.setattr(analytics, "_load_social_accounts_for_report", fake_load_social_accounts_for_report)
    monkeypatch.setattr(analytics, "_fetch_db_published_posts", fake_fetch_db_posts)
    monkeypatch.setattr(analytics, "decrypt", lambda value: "access-token")
    monkeypatch.setattr(analytics, "_youtube_period_bounds", lambda days: (
        date(2026, 5, 1),
        date(2026, 5, 30),
        date(2026, 4, 1),
        date(2026, 4, 30),
    ))
    monkeypatch.setattr(analytics, "compute_youtube_settled_window", lambda days, selected_end_date: (
        date(2026, 4, 28),
        date(2026, 5, 27),
        True,
    ))
    monkeypatch.setattr(analytics, "store_youtube_geography_snapshot", fake_store_snapshot)
    monkeypatch.setattr(analytics, "load_latest_youtube_geography_snapshot", fake_load_snapshot)
    monkeypatch.setattr("backend.app.social.google.GoogleAuth", FakeGoogleAuth)

    report = await analytics.analytics_youtube_report(
        current_user={"user_id": "user_1"},
        db=object(),
        days=30,
        account_id="yt_1",
        group_by="day",
    )

    assert report["supported"] is True
    assert report["summary"]["watch_quality_summary"]["engaged_views"] == 140
    assert report["summary"]["watch_quality_summary"]["average_view_duration_seconds"] == 48
    assert report["summary"]["watch_quality_summary"]["average_view_percentage"] == 52
    assert report["audience"]["viewer_demographics"]["age_groups"]
    assert report["audience"]["viewer_demographics"]["gender_distribution"]
    assert report["video_performance"]["operating_system"][0]["label"] == "Android"
    assert report["video_performance"]["content_type_breakdown"]["creator_content_type"][0]["label"] == "Shorts"
    assert report["video_performance"]["sharing_services"][0]["label"] == "WhatsApp"
    assert report["video_performance"]["retention"]["selected_video_id"] == "vid_a"
    assert len(report["video_performance"]["retention"]["videos"]) == 2
    assert report["supports"]["watch_quality"] is True
    assert report["supports"]["viewer_demographics"] is True
    assert report["supports"]["retention"] is True
