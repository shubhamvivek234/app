from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest

from utils.notification_emails import (
    _build_notification_html,
    send_notification_email_async,
)
from celery_workers.tasks.notifications import (
    _async_send_notification_email,
)
from api.routes import notifications as notification_routes


def _match_condition(doc: dict, query: dict) -> bool:
    if not query:
        return True
    if "$and" in query and not all(_match_condition(doc, q) for q in query["$and"]):
        return False
    if "$or" in query and not any(_match_condition(doc, q) for q in query["$or"]):
        return False
    for k, v in query.items():
        if k in ("$and", "$or"):
            continue
        val = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v and val not in v["$in"]:
                return False
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$exists" in v:
                exists = k in doc
                if exists != v["$exists"]:
                    return False
        elif val != v:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match_condition(doc, query):
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
            if _match_condition(doc, query):
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

    async def delete_many(self, query):
        initial_len = len(self.docs)
        self.docs = [doc for doc in self.docs if not _match_condition(doc, query)]
        deleted_count = initial_len - len(self.docs)
        return type("DeleteResult", (), {"deleted_count": deleted_count})()


class _FakeDB:
    def __init__(self):
        self.users = _FakeCollection([
            {"user_id": "user-1", "email": "creator@example.com", "name": "Creator Alex"},
            {"user_id": "user-disabled", "email": "optout@example.com", "name": "Optout User"},
        ])
        self.notification_prefs = _FakeCollection([
            {
                "user_id": "user-disabled",
                "prefs": {
                    "post.published": {"channels": ["in_app"], "digest": "immediate"},
                    "post.failed": {"channels": ["in_app"], "digest": "immediate"},
                },
            }
        ])
        self.notifications = _FakeCollection([
            {"notification_id": "n1", "user_id": "user-1", "event": "post.published", "message": "msg 1", "read": False},
            {"notification_id": "n2", "user_id": "user-1", "event": "post.failed", "message": "msg 2", "read": True},
            {"notification_id": "n3", "user_id": "user-2", "event": "post.published", "message": "other user msg", "read": False},
        ])


def test_render_notification_email_html():
    html = _build_notification_html(
        event="post.published",
        title="Post Published Successfully",
        message="Your post 'Product Launch 2026' was successfully published to LinkedIn and X.",
        action_url="https://app.unravler.com/content-library?status=published",
        display_name="Alex",
        metadata={"platform": "linkedin", "post_id": "post-xyz"},
    )

    assert "Post Published Successfully" in html
    assert "Product Launch 2026" in html
    assert "https://app.unravler.com/content-library?status=published" in html
    assert "Alex" in html
    assert "post-xyz" in html


@pytest.mark.asyncio
async def test_send_notification_email_async_with_resend_mock():
    mock_send = MagicMock(return_value={"id": "resend-msg-123"})

    env_overrides = {
        "RESEND_API_KEY": "re_test_12345",
        "SENDER_EMAIL": "alerts@unravler.com",
        "SENDER_NAME": "Unravler",
    }
    with patch.dict("os.environ", env_overrides, clear=False), \
         patch("resend.Emails.send", mock_send):
        result = await send_notification_email_async(
            email="creator@example.com",
            event="post.failed",
            title="Post Failed",
            message="Publishing failed on Instagram due to expired token.",
            target_path="/accounts",
        )

        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[0][0]
        assert call_kwargs["to"] == ["creator@example.com"]
        assert "Post Failed" in call_kwargs["subject"]


@pytest.mark.asyncio
async def test_send_notification_email_task_preference_gating():
    fake_db = _FakeDB()
    fake_client = {"social_media_db": fake_db}

    # User 1 has default preferences (which allows post.failed via email and in_app)
    with patch("celery_workers.tasks.notifications.get_client", return_value=fake_client), \
         patch("celery_workers.tasks.notifications.send_notification_email_async") as mock_send_async:
        mock_send_async.return_value = True

        # Test case 1: User with email channel enabled receives email
        res1 = await _async_send_notification_email(
            user_id="user-1",
            event="post.failed",
            title="Post Failed",
            message="Your scheduled post failed.",
            target_path="/posts",
        )
        assert res1 is True
        mock_send_async.assert_called_once()

        # Test case 2: User who disabled email preference gets suppressed (returns False)
        mock_send_async.reset_mock()
        res2 = await _async_send_notification_email(
            user_id="user-disabled",
            event="post.failed",
            title="Post Failed",
            message="Your scheduled post failed.",
            target_path="/posts",
        )
        assert res2 is False
        mock_send_async.assert_not_called()

        # Test case 3: Non-existent user
        res3 = await _async_send_notification_email(
            user_id="user-non-existent",
            event="post.failed",
            title="Post Failed",
            message="Your scheduled post failed.",
        )
        assert res3 is False


@pytest.mark.asyncio
async def test_clear_all_notifications_endpoint():
    fake_db = _FakeDB()
    current_user = {"user_id": "user-1"}

    res = await notification_routes.clear_all_notifications(
        current_user=current_user,
        db=fake_db,
    )

    assert res["deleted"] == 2
    # Ensure other user's notifications remain intact
    assert len(fake_db.notifications.docs) == 1
    assert fake_db.notifications.docs[0]["user_id"] == "user-2"
