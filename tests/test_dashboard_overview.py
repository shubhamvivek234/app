from datetime import datetime, timedelta, timezone

import pytest

from api.routes import dashboard as dashboard_routes


def _matches_value(value, expected):
    if isinstance(expected, dict):
        if "$exists" in expected:
            return (value is not None) == bool(expected["$exists"])
        if "$gte" in expected:
            return value is not None and value >= expected["$gte"]
        if "$in" in expected:
            return value in expected["$in"]
        if "$ne" in expected:
            return value != expected["$ne"]
    return value == expected


def _matches_query(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches_query(doc, condition) for condition in expected):
                return False
            continue
        if not _matches_value(doc.get(key), expected):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, spec, direction=None):
        docs = list(self._docs)
        if isinstance(spec, list):
            for key, sort_direction in reversed(spec):
                docs.sort(key=lambda doc: doc.get(key) or datetime.min.replace(tzinfo=timezone.utc), reverse=sort_direction < 0)
        else:
            docs.sort(key=lambda doc: doc.get(spec) or datetime.min.replace(tzinfo=timezone.utc), reverse=(direction or -1) < 0)
        self._docs = docs
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if _matches_query(doc, query))

    def find(self, query=None, projection=None, *_args, **_kwargs):
        filtered = [doc for doc in self.docs if _matches_query(doc, query or {})]
        if isinstance(projection, dict) and projection:
            excludes = {key for key, value in projection.items() if value == 0}
            includes = {key for key, value in projection.items() if value and key != "_id"}
            projected = []
            for doc in filtered:
                if includes:
                    next_doc = {key: doc.get(key) for key in includes}
                else:
                    next_doc = dict(doc)
                for key in excludes:
                    next_doc.pop(key, None)
                projected.append(next_doc)
            filtered = projected
        return FakeCursor(filtered)


class FakeDB:
    def __init__(self, *, posts=None, notifications=None, inbox_messages=None, social_accounts=None):
        self.posts = FakeCollection(posts or [])
        self.notifications = FakeCollection(notifications or [])
        self.inbox_messages = FakeCollection(inbox_messages or [])
        self.social_accounts = FakeCollection(social_accounts or [])


def _post(
    post_id,
    *,
    status,
    created_at,
    scheduled_time=None,
    published_at=None,
    account_ids=None,
    platforms=None,
    title=None,
    timezone_name="UTC",
    scheduled_timezone_explicit=False,
):
    return {
        "id": post_id,
        "workspace_id": "ws_1",
        "user_id": "user_1",
        "status": status,
        "content": f"Post body {post_id}",
        "title": title or f"Title {post_id}",
        "post_type": "video" if "video" in post_id else "text",
        "platforms": platforms or ["instagram"],
        "account_ids": account_ids or ["acct_1"],
        "social_account_ids": account_ids or ["acct_1"],
        "media_ids": [],
        "media_urls": [],
        "thumbnail_urls": [f"https://cdn.example/{post_id}.jpg"],
        "published_media_kind": "image",
        "created_at": created_at,
        "updated_at": created_at,
        "scheduled_time": scheduled_time,
        "published_at": published_at,
        "timezone": timezone_name,
        "scheduled_timezone_explicit": scheduled_timezone_explicit,
    }


def _account(
    account_id,
    *,
    platform="instagram",
    expires_at=None,
    token_error=None,
    restriction_type=None,
    refresh_token=None,
    requires_reconnect=False,
    reconnect_reason=None,
):
    return {
        "id": account_id,
        "account_id": account_id,
        "user_id": "user_1",
        "platform": platform,
        "platform_username": f"{platform}_{account_id}",
        "display_name": f"{platform.title()} {account_id}",
        "picture_url": f"https://cdn.example/{account_id}.jpg",
        "followers_count": 1200,
        "posts_count": 43,
        "is_active": True,
        "connected_at": datetime.now(timezone.utc) - timedelta(days=30),
        "expires_at": expires_at,
        "token_error": token_error,
        "refresh_token": refresh_token,
        "requires_reconnect": requires_reconnect,
        "reconnect_reason": reconnect_reason,
        "publish_restriction_type": restriction_type,
        "publish_action_required": "Reconnect TikTok in app settings." if restriction_type else None,
        "publish_error_code": "public_posting_blocked" if restriction_type else None,
    }


@pytest.mark.asyncio
async def test_dashboard_overview_returns_full_normalized_sections_from_db(monkeypatch):
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[
            _post("sched-2", status="scheduled", created_at=now - timedelta(days=1), scheduled_time=now + timedelta(hours=4), account_ids=["acct_2"], platforms=["tiktok"], title="TikTok launch", timezone_name="Asia/Kolkata", scheduled_timezone_explicit=True),
            _post("draft-1", status="draft", created_at=now - timedelta(days=2), title="Draft"),
            _post("pub-1", status="published", created_at=now - timedelta(days=3), published_at=now - timedelta(hours=5), title="Published 1"),
            _post("failed-1", status="failed", created_at=now - timedelta(days=1), title="Failed"),
            _post("partial-1", status="partial", created_at=now - timedelta(hours=6), title="Partial"),
            _post("sched-1", status="scheduled", created_at=now - timedelta(hours=2), scheduled_time=now + timedelta(hours=1), account_ids=["acct_1"], platforms=["instagram"], title="Instagram queue", timezone_name="Asia/Kolkata", scheduled_timezone_explicit=True),
        ],
        notifications=[
            {
                "notification_id": "notif-1",
                "user_id": "user_1",
                "type": "account.disconnected",
                "message": "Instagram token expired.",
                "metadata": {"account_id": "acct_1"},
                "is_read": False,
                "created_at": now - timedelta(minutes=5),
            },
            {
                "notification_id": "notif-2",
                "user_id": "user_1",
                "type": "subscription.reactivated",
                "message": "Subscription updated successfully.",
                "metadata": {"subscription": True},
                "is_read": True,
                "created_at": now - timedelta(hours=5),
            },
        ],
        inbox_messages=[
            {"id": "msg-1", "workspace_id": "ws_1", "user_id": "user_1", "status": "unread", "type": "comment"},
            {"id": "msg-2", "workspace_id": "ws_1", "user_id": "user_1", "status": "unread", "type": "dm"},
            {"id": "msg-3", "workspace_id": "ws_1", "user_id": "user_1", "status": "read", "type": "dm"},
        ],
        social_accounts=[
            _account("acct_1", platform="instagram", expires_at=now - timedelta(hours=2), token_error="Instagram access expired."),
            _account("acct_2", platform="tiktok", expires_at=now + timedelta(days=30), restriction_type="public_posting_blocked"),
        ],
    )

    async def fake_hydrate_posts(_db, docs):
        return list(docs)

    monkeypatch.setattr(dashboard_routes, "_hydrate_post_card_fields_for_docs", fake_hydrate_posts)

    result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": False,
            "subscription_status": "expired",
        },
        db=db,
        days=7,
        refresh=False,
    )

    assert result["sections_returned"] == ["core", "queue", "wins", "activity", "health", "performance"]
    assert result["summary"] == {
        "total_posts": 6,
        "scheduled_posts": 2,
        "published_posts": 1,
        "draft_posts": 1,
        "failed_posts": 2,
        "connected_accounts": 2,
    }
    assert result["operations"]["verification_required"] is True
    assert result["operations"]["unread_inbox"] == 2
    assert result["operations"]["unread_comments"] == 1
    assert result["operations"]["unread_dms"] == 1

    action_ids = [item["id"] for item in result["action_items"]]
    assert "subscription-status" in action_ids
    assert "verify-email" in action_ids
    assert "reconnect-accounts" in action_ids
    assert "restricted-accounts" in action_ids
    assert "failed-posts" in action_ids
    assert "unread-inbox" in action_ids

    assert [post["id"] for post in result["upcoming_posts"]] == ["sched-1", "sched-2"]
    assert result["upcoming_posts"][0]["account_labels"] == ["Instagram acct_1"]
    assert result["upcoming_posts"][0]["timezone"] == "Asia/Kolkata"
    assert result["upcoming_posts"][0]["scheduled_timezone_explicit"] is True
    assert result["upcoming_posts"][0]["scheduled_time"].tzinfo is not None
    assert result["recent_published"][0]["id"] == "pub-1"
    assert result["recent_published"][0]["account_labels"] == ["Instagram acct_1"]

    assert result["account_health"][0]["health_state"] == "restricted"
    assert result["account_health"][1]["health_state"] == "reconnect_required"
    verify_email_item = next(item for item in result["action_items"] if item["id"] == "verify-email")
    assert "Account connection can continue" in verify_email_item["message"]

    assert result["performance_7d"]["published_in_period"] == 1
    assert result["performance_7d"]["platform_counts"]["instagram"] == 1
    assert result["performance_7d"]["type_counts"]["text"] == 1
    assert result["performance_7d"]["audience_totals"]["followers_total"] == 2400
    assert result["activity"][0]["target_path"] == "/accounts"
    assert result["activity"][0]["severity"] == "high"
    assert any(error["metric"] == "reach" for error in result["performance_7d"]["errors"])


@pytest.mark.asyncio
async def test_dashboard_overview_sections_skip_heavy_health_and_performance_logic(monkeypatch):
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[
            _post("sched-1", status="scheduled", created_at=now - timedelta(hours=1), scheduled_time=now + timedelta(hours=3)),
            _post("pub-1", status="published", created_at=now - timedelta(days=1), published_at=now - timedelta(hours=2)),
        ],
        social_accounts=[_account("acct_1", expires_at=now + timedelta(days=10))],
    )

    async def fake_hydrate_posts(_db, docs):
        return list(docs)

    async def forbidden_hydrate(_db, _account):
        raise AssertionError("dashboard should not hydrate account metadata for lightweight sections")

    monkeypatch.setattr(dashboard_routes, "_hydrate_post_card_fields_for_docs", fake_hydrate_posts)
    monkeypatch.setattr(dashboard_routes, "_hydrate_social_account_metadata", forbidden_hydrate)

    result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=False,
        sections="core,queue,wins,activity",
    )

    assert result["sections_returned"] == ["core", "queue", "wins", "activity"]
    assert "account_health" not in result
    assert "performance_7d" not in result
    assert result["summary"]["scheduled_posts"] == 1
    assert result["upcoming_posts"][0]["id"] == "sched-1"
    assert result["recent_published"][0]["id"] == "pub-1"


@pytest.mark.asyncio
async def test_dashboard_health_uses_stored_state_by_default_and_hydrates_missing_metadata_on_refresh(monkeypatch):
    now = datetime.now(timezone.utc)
    complete_account = _account("acct_complete", expires_at=now + timedelta(days=10))
    missing_account = _account("acct_missing", expires_at=now + timedelta(days=4))
    missing_account["picture_url"] = None
    missing_account["display_name"] = None
    db = FakeDB(
        social_accounts=[complete_account, missing_account],
    )

    calls = []

    async def tracked_hydrate(_db, account):
        calls.append(account["account_id"])
        hydrated = dict(account)
        hydrated["picture_url"] = "https://cdn.example/refreshed.jpg"
        hydrated["display_name"] = "Refreshed account"
        return hydrated

    monkeypatch.setattr(dashboard_routes, "_hydrate_social_account_metadata", tracked_hydrate)

    default_result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=False,
        sections="health",
    )

    assert default_result["sections_returned"] == ["health"]
    assert calls == []
    assert len(default_result["account_health"]) == 2

    refresh_result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=True,
        sections="health",
    )

    assert refresh_result["sections_returned"] == ["health"]
    assert calls == ["acct_missing"]
    assert any(account["display_name"] == "Refreshed account" for account in refresh_result["account_health"])


@pytest.mark.asyncio
async def test_dashboard_health_matches_connected_accounts_logic_for_refreshable_expired_tokens():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        social_accounts=[
            _account("acct_refreshable", expires_at=now - timedelta(hours=2), refresh_token="encrypted-refresh"),
            _account("acct_reconnect", expires_at=now - timedelta(hours=1)),
        ],
    )

    result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=False,
        sections="core,health",
    )

    states = {account["account_id"]: account["health_state"] for account in result["account_health"]}
    assert states["acct_refreshable"] == "healthy"
    assert states["acct_reconnect"] == "reconnect_required"
    action_ids = [item["id"] for item in result["action_items"]]
    assert "reconnect-accounts" in action_ids


@pytest.mark.asyncio
async def test_dashboard_raw_account_loader_keeps_refresh_capability_without_exposing_token():
    db = FakeDB(
        social_accounts=[
            _account("acct_refreshable", refresh_token="encrypted-refresh"),
            _account("acct_manual", refresh_token=None),
        ],
    )

    result = await dashboard_routes._load_raw_accounts(db, "user_1")

    mapped = {account["account_id"]: account for account in result}
    assert mapped["acct_refreshable"]["has_refresh_token"] is True
    assert mapped["acct_manual"]["has_refresh_token"] is False
    assert "refresh_token" not in mapped["acct_refreshable"]
    assert "refresh_token" not in mapped["acct_manual"]


@pytest.mark.asyncio
async def test_dashboard_queue_is_sorted_nearest_first_after_hydration(monkeypatch):
    now = datetime.now(timezone.utc)
    posts = [
        _post("sched-later", status="scheduled", created_at=now - timedelta(hours=3), scheduled_time=now + timedelta(hours=6)),
        _post("sched-soon", status="scheduled", created_at=now - timedelta(hours=1), scheduled_time=now + timedelta(minutes=20)),
        _post("sched-middle", status="scheduled", created_at=now - timedelta(hours=2), scheduled_time=now + timedelta(hours=2)),
    ]
    db = FakeDB(posts=posts)

    async def reverse_hydrate(_db, docs):
        return list(reversed(docs))

    monkeypatch.setattr(dashboard_routes, "_hydrate_post_card_fields_for_docs", reverse_hydrate)

    result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=False,
        sections="queue",
    )

    assert [post["id"] for post in result["upcoming_posts"]] == ["sched-soon", "sched-middle", "sched-later"]


@pytest.mark.asyncio
async def test_dashboard_overview_returns_partial_data_when_one_section_fails(monkeypatch):
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[_post("sched-1", status="scheduled", created_at=now - timedelta(hours=1), scheduled_time=now + timedelta(hours=1))],
        social_accounts=[_account("acct_1", expires_at=now + timedelta(days=10))],
    )

    async def broken_hydrate_posts(_db, _docs):
        raise RuntimeError("post hydration unavailable")

    monkeypatch.setattr(dashboard_routes, "_hydrate_post_card_fields_for_docs", broken_hydrate_posts)

    result = await dashboard_routes.dashboard_overview(
        current_user={
            "user_id": "user_1",
            "default_workspace_id": "ws_1",
            "email_verified": True,
            "subscription_status": "active",
        },
        db=db,
        days=7,
        refresh=False,
        sections="core,queue",
    )

    assert result["sections_returned"] == ["core"]
    assert result["summary"]["scheduled_posts"] == 1
    assert result["section_errors"]["queue"] == "post hydration unavailable"
    assert "upcoming_posts" not in result
