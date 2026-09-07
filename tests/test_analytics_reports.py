import pytest
from api.routes.analytics import (
    ReportExportRequest,
    ReportScheduleRequest,
    delete_report_schedule,
    export_analytics_csv,
    export_branded_analytics_report,
    list_report_schedules,
    schedule_analytics_report,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, items=None):
        self.docs = {d.get("id"): d for d in (items or [])}

    async def count_documents(self, query):
        return len(self.docs)

    def find(self, query):
        return _FakeCursor(self.docs.values())

    async def insert_one(self, doc):
        self.docs[doc["id"]] = doc
        return doc

    async def delete_one(self, query):
        sched_id = query.get("id")
        if sched_id in self.docs:
            del self.docs[sched_id]
            from types import SimpleNamespace
            return SimpleNamespace(deleted_count=1)
        from types import SimpleNamespace
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.posts = _FakeCollection([
            {"id": "p1", "status": "published", "content": "Post 1", "platforms": ["twitter"]},
        ])
        self.social_accounts = _FakeCollection([
            {"id": "a1", "platform": "twitter", "username": "acme", "is_active": True},
        ])
        self.analytics_schedules = _FakeCollection()


@pytest.mark.asyncio
async def test_export_branded_analytics_report():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}
    req = ReportExportRequest(
        agency_name="Premier Social Agency",
        client_name="Nike",
    )
    report = await export_branded_analytics_report(req, current_user=user, db=db)
    assert report["agency_name"] == "Premier Social Agency"
    assert report["client_name"] == "Nike"
    assert report["metrics"]["total_published_posts"] == 1
    assert len(report["channels"]) == 1


@pytest.mark.asyncio
async def test_schedule_analytics_report_crud():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}
    req = ReportScheduleRequest(
        recipient_email="client@example.com",
        client_name="Nike",
        frequency="monthly",
    )
    res = await schedule_analytics_report(req, current_user=user, db=db)
    assert res["ok"] is True

    schedules = await list_report_schedules(current_user=user, db=db)
    assert len(schedules) == 1
    assert schedules[0]["recipient_email"] == "client@example.com"

    await delete_report_schedule(schedules[0]["id"], current_user=user, db=db)
    schedules_after = await list_report_schedules(current_user=user, db=db)
    assert len(schedules_after) == 0


@pytest.mark.asyncio
async def test_export_analytics_csv():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}
    req = ReportExportRequest()
    res = await export_analytics_csv(req, current_user=user, db=db)
    assert res["ok"] is True
    assert res["count"] == 1
    assert res["rows"][0]["post_id"] == "p1"


def test_google_business_analytics_capabilities():
    from api.routes.analytics import _PLATFORM_ANALYTICS_CAPABILITIES, _platform_label, _published_match, _scheduled_match

    assert "google_business" in _PLATFORM_ANALYTICS_CAPABILITIES
    cap = _PLATFORM_ANALYTICS_CAPABILITIES["google_business"]
    assert cap["supports"]["views"] is True
    assert cap["supports"]["likes"] is False

    assert _platform_label("google_business") == "Google Business Profile"
    assert _platform_label("gbp") == "Google Business Profile"

    # Test query matching both google_business and gbp
    pub_query = _published_match("ws_1", "2026-01-01T00:00:00Z", platform="google_business")
    assert pub_query["platforms"] == {"$in": ["google_business", "gbp"]}

    sched_query = _scheduled_match("ws_1", platform="gbp")
    assert sched_query["platforms"] == {"$in": ["google_business", "gbp"]}


def test_reddit_and_gbp_capabilities():
    from api.routes.analytics import _PLATFORM_ANALYTICS_CAPABILITIES, _published_match

    assert "reddit" in _PLATFORM_ANALYTICS_CAPABILITIES
    reddit_cap = _PLATFORM_ANALYTICS_CAPABILITIES["reddit"]
    assert reddit_cap["supports"]["likes"] is True
    assert reddit_cap["supports"]["comments"] is True
    assert reddit_cap["supports"]["views"] is True
    assert reddit_cap["supports"]["shares"] is False

    assert "gbp" in _PLATFORM_ANALYTICS_CAPABILITIES
    assert _PLATFORM_ANALYTICS_CAPABILITIES["gbp"]["supports"]["views"] is True

    pub_match_acc = _published_match("ws_1", "2026-01-01T00:00:00Z", account_id="acc_123")
    assert {"social_account_ids": "acc_123"} in pub_match_acc["$or"]
    assert {"account_ids": "acc_123"} in pub_match_acc["$or"]
    assert {"platform_account_ids": "acc_123"} in pub_match_acc["$or"]
    assert {"social_account_id": "acc_123"} in pub_match_acc["$or"]


@pytest.mark.asyncio
async def test_fetch_db_published_posts_retains_metrics():
    from api.routes.analytics import _fetch_db_published_posts, _feed_metric_support

    class _MockFindCursor:
        def __init__(self, docs):
            self.docs = docs

        def sort(self, *a, **k):
            return self

        async def to_list(self, length=None):
            return self.docs

    class _MockPostsCol:
        def __init__(self, docs):
            self.docs = docs

        def find(self, query, projection=None):
            return _MockFindCursor(self.docs)

    class _MockDB:
        def __init__(self, docs):
            self.posts = _MockPostsCol(docs)

    db = _MockDB([
        {
            "id": "post_gbp_1",
            "content": "Special offer today!",
            "status": "published",
            "platforms": ["google_business"],
            "social_account_ids": ["acc_gbp_1"],
            "platform_results": {
                "google_business": {
                    "status": "success",
                    "views": 450,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "post_url": "https://business.google.com/post/1",
                }
            },
        },
        {
            "id": "post_tw_1",
            "content": "Exciting product update",
            "status": "published",
            "platforms": ["twitter"],
            "social_account_ids": ["acc_tw_1"],
            "platform_results": {
                "twitter": {
                    "status": "success",
                    "likes": 42,
                    "comments_count": 8,
                    "shares": 15,
                    "views": 1200,
                }
            },
        },
    ])

    account_gbp = {"platform": "google_business", "account_id": "acc_gbp_1"}
    posts_gbp = await _fetch_db_published_posts(db, "u1", account_gbp, limit=10)
    assert len(posts_gbp) == 2  # mock cursor returns all
    p_gbp = posts_gbp[0]
    assert p_gbp["views"] == 450
    assert p_gbp["permalink"] == "https://business.google.com/post/1"

    support_gbp = _feed_metric_support("google_business", p_gbp, source_mode="db_fallback")
    assert support_gbp["views"]["supported"] is True

    account_tw = {"platform": "twitter", "account_id": "acc_tw_1"}
    posts_tw = await _fetch_db_published_posts(db, "u1", account_tw, limit=10)
    p_tw = posts_tw[1]
    assert p_tw["likes"] == 42
    assert p_tw["comments_count"] == 8
    assert p_tw["shares"] == 15
    assert p_tw["views"] == 1200


