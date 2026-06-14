from datetime import datetime, timezone

import pytest
from starlette.requests import Request

from api.routes import user as user_routes
from api.routes import webhooks as webhook_routes
from api.routes import posts as post_routes
from api.routes import notifications as notification_routes
from celery_workers.tasks import subscription_check as subscription_check_tasks
from celery_workers.tasks import publish as publish_tasks


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("InsertOneResult", (), {"inserted_id": doc.get("_id")})()

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                for key, value in update.get("$setOnInsert", {}).items():
                    doc.setdefault(key, value)
                return type("UpdateResult", (), {"matched_count": 1, "upserted_id": None})()

        if upsert:
            new_doc = dict(query)
            for key, value in update.get("$setOnInsert", {}).items():
                new_doc[key] = value
            for key, value in update.get("$set", {}).items():
                new_doc[key] = value
            self.docs.append(new_doc)
            return type("UpdateResult", (), {"matched_count": 0, "upserted_id": new_doc.get("_id", "upserted")})()

        return type("UpdateResult", (), {"matched_count": 0, "upserted_id": None})()


class _FakeDB:
    def __init__(self):
        self.notification_prefs = _FakeCollection()
        self.notifications = _FakeCollection()


def _request(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


def test_notification_normalizer_handles_legacy_read_field():
    normalized = notification_routes._normalize_notification(
        {
            "notification_id": "notice-1",
            "user_id": "user-1",
            "type": "publish_failed",
            "message": "Post failed.",
            "read": False,
            "created_at": datetime.now(timezone.utc),
        }
    )

    assert normalized["id"] == "notice-1"
    assert normalized["is_read"] is False
    assert normalized["read"] is False
    assert normalized["target_path"] == "/dashboard"


@pytest.mark.asyncio
async def test_notification_preferences_routes_return_supported_catalog_only():
    db = _FakeDB()
    current_user = {"user_id": "user-1"}

    initial = await user_routes.get_notification_preferences(
        request=_request("/api/user/notification-preferences"),
        current_user=current_user,
        db=db,
    )

    assert set(initial.preferences.keys()) == {
        "post.scheduled",
        "post.published",
        "post.failed",
        "post.dlq",
        "account.reconnect_required",
        "subscription.expiring",
        "account.expiring",
        "billing.failed",
    }
    assert "analytics.weekly" not in initial.preferences

    updated = await user_routes.update_notification_preferences(
        request=_request("/api/user/notification-preferences"),
        body=user_routes.NotificationPreferencesUpdate(
            preferences={
                "post.failed": {"channels": ["email", "sms"], "digest": "immediate"},
                "billing.failed": {"channels": ["in_app"], "digest": "hourly"},
                "analytics.weekly": {"channels": ["email"], "digest": "daily"},
                "unknown.event": {"channels": ["email"], "digest": "immediate"},
            }
        ),
        current_user=current_user,
        db=db,
    )

    assert updated.preferences["post.failed"]["channels"] == ["email"]
    assert updated.preferences["billing.failed"]["channels"] == ["in_app"]
    assert "analytics.weekly" not in updated.preferences
    assert "unknown.event" not in updated.preferences


@pytest.mark.asyncio
async def test_account_expiring_notifications_respect_user_channels():
    db = _FakeDB()
    db.notification_prefs.docs.append(
        {
            "user_id": "user-1",
            "prefs": {
                "account.expiring": {
                    "channels": ["in_app"],
                    "digest": "immediate",
                }
            },
        }
    )

    await subscription_check_tasks._emit_account_expiring_notifications(
        db,
        user_id="user-1",
        notification_type="subscription_expiring",
        message="Subscription expires soon.",
        now=datetime.now(timezone.utc),
        metadata={"post_count": 3},
    )

    assert len(db.notifications.docs) == 1
    assert db.notifications.docs[0]["channel"] == "in_app"
    assert db.notifications.docs[0]["event"] == "subscription.expiring"
    assert db.notifications.docs[0]["type"] == "subscription_expiring"
    assert db.notifications.docs[0]["target_path"] == "/billing"


@pytest.mark.asyncio
async def test_billing_failed_notifications_respect_user_channels():
    db = _FakeDB()
    db.notification_prefs.docs.append(
        {
            "user_id": "user-1",
            "prefs": {
                "billing.failed": {
                    "channels": ["email"],
                    "digest": "immediate",
                }
            },
        }
    )

    await webhook_routes._emit_billing_failed_notifications(
        db,
        user_id="user-1",
        provider="Stripe",
        attempt_count=2,
        now=datetime.now(timezone.utc),
    )

    assert len(db.notifications.docs) == 1
    assert db.notifications.docs[0]["channel"] == "email"
    assert db.notifications.docs[0]["event"] == "billing.failed"
    assert db.notifications.docs[0]["type"] == "billing.payment_failed"
    assert db.notifications.docs[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_scheduled_post_notification_upserts_single_in_app_doc():
    db = _FakeDB()
    scheduled_time = datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc)

    post = {
        "id": "post-1",
        "user_id": "user-1",
        "title": "Launch post",
        "platforms": ["instagram", "youtube"],
        "scheduled_time": scheduled_time,
        "timezone": "Asia/Kolkata",
    }

    await post_routes._emit_scheduled_post_notification(db, post, now=scheduled_time)
    post["scheduled_time"] = datetime(2026, 6, 21, 11, 0, tzinfo=timezone.utc)
    await post_routes._emit_scheduled_post_notification(db, post, now=post["scheduled_time"])

    assert len(db.notifications.docs) == 1
    notification = db.notifications.docs[0]
    assert notification["event"] == "post.scheduled"
    assert notification["channel"] == "in_app"
    assert notification["dedup_key"] == "post:post-1:scheduled"
    assert "2026-06-21T11:00:00+00:00" in notification["message"]


@pytest.mark.asyncio
async def test_aggregate_publish_notification_uses_in_app_default_for_success():
    db = _FakeDB()

    await publish_tasks._emit_aggregate_publish_notification(
        db,
        post={
            "id": "post-1",
            "user_id": "user-1",
            "title": "Launch post",
            "platforms": ["instagram", "youtube"],
        },
        aggregate_status="published",
        result_entries={
            "instagram": {"status": "published"},
            "youtube": {"status": "published"},
        },
        created_at=datetime.now(timezone.utc),
    )

    assert len(db.notifications.docs) == 1
    assert db.notifications.docs[0]["event"] == "post.published"
    assert db.notifications.docs[0]["channel"] == "in_app"
    assert db.notifications.docs[0]["target_path"] == "/content-library?status=published"


@pytest.mark.asyncio
async def test_aggregate_publish_notification_uses_dlq_for_permanent_failure():
    db = _FakeDB()

    await publish_tasks._emit_aggregate_publish_notification(
        db,
        post={
            "id": "post-2",
            "user_id": "user-1",
            "content": "Video launch",
            "platforms": ["youtube"],
        },
        aggregate_status="failed",
        result_entries={
            "youtube": {"status": "permanently_failed"},
        },
        created_at=datetime.now(timezone.utc),
    )

    assert len(db.notifications.docs) == 2
    channels = {doc["channel"] for doc in db.notifications.docs}
    assert channels == {"email", "in_app"}
    assert {doc["event"] for doc in db.notifications.docs} == {"post.dlq"}
