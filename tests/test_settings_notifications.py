from datetime import datetime, timezone

import pytest
from starlette.requests import Request

from api.routes import user as user_routes
from api.routes import webhooks as webhook_routes
from celery_workers.tasks import subscription_check as subscription_check_tasks


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
        "post.published",
        "post.failed",
        "post.dlq",
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
    assert db.notifications.docs[0]["type"] == "subscription_expiring"


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
    assert db.notifications.docs[0]["type"] == "billing.payment_failed"
