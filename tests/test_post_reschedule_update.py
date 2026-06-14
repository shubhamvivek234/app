from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.models.post import UpdatePostRequest
from api.routes import posts as posts_route


class _FakePostsCollection:
    def __init__(self, existing):
        self.existing = existing
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        if query.get("id") != self.existing.get("id"):
            return None
        if query.get("user_id") and query.get("user_id") != self.existing.get("user_id"):
            return None
        if query.get("deleted_at") == {"$exists": False} and self.existing.get("deleted_at"):
            return None
        return dict(self.existing)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if query.get("version") != self.existing.get("version"):
            return SimpleNamespace(matched_count=0, modified_count=0)
        if "$set" in update:
            self.existing.update(update["$set"])
        if "$inc" in update:
            for key, increment in update["$inc"].items():
                self.existing[key] = self.existing.get(key, 0) + increment
        return SimpleNamespace(matched_count=1, modified_count=1)


class _FakeDB:
    def __init__(self, existing):
        self.posts = _FakePostsCollection(existing)


def _base_post(**overrides):
    now = datetime.now(timezone.utc)
    return {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "content": "Scheduled caption",
        "platforms": ["instagram"],
        "account_ids": ["acct-1"],
        "social_account_ids": ["acct-1"],
        "status": "scheduled",
        "post_type": "image",
        "scheduled_time": now + timedelta(hours=2),
        "timezone": "UTC",
        "scheduled_timezone_explicit": True,
        "created_at": now - timedelta(days=1),
        "updated_at": now - timedelta(hours=1),
        "version": 1,
        **overrides,
    }


def _current_user(**overrides):
    return {
        "user_id": "user-1",
        "default_workspace_id": "ws-1",
        "email_verified": True,
        **overrides,
    }


@pytest.mark.asyncio
async def test_update_post_reschedules_with_density_warning(monkeypatch):
    existing = _base_post()
    db = _FakeDB(existing)
    target_time = datetime.now(timezone.utc) + timedelta(days=2)
    density_warning = SimpleNamespace(message="High Instagram volume in this time window")

    check_density = AsyncMock(return_value=[density_warning])
    event_log = Mock()
    monkeypatch.setattr(posts_route, "check_schedule_density", check_density)
    monkeypatch.setattr(posts_route, "event_log", event_log)
    monkeypatch.setattr(posts_route, "log_audit_event", AsyncMock())

    response = await posts_route.update_post(
        "post-1",
        UpdatePostRequest(
            scheduled_time=target_time,
            timezone="Asia/Kolkata",
            version=1,
        ),
        _current_user(),
        db,
    )

    assert response.scheduled_time == target_time
    assert response.timezone == "Asia/Kolkata"
    assert response.scheduled_timezone_explicit is True
    assert response.version == 2
    assert db.posts.update_calls[0][0]["version"] == 1
    assert db.posts.update_calls[0][1]["$set"]["scheduled_time"] == target_time
    assert db.posts.update_calls[0][1]["$set"]["timezone"] == "Asia/Kolkata"
    check_density.assert_awaited_once_with(db, "ws-1", ["instagram"], target_time)
    event_log.assert_called_once()


@pytest.mark.asyncio
async def test_update_post_version_conflict_does_not_change_schedule(monkeypatch):
    original_time = datetime.now(timezone.utc) + timedelta(hours=4)
    existing = _base_post(scheduled_time=original_time, version=7)
    db = _FakeDB(existing)

    monkeypatch.setattr(posts_route, "check_schedule_density", AsyncMock(return_value=[]))
    monkeypatch.setattr(posts_route, "log_audit_event", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await posts_route.update_post(
            "post-1",
            UpdatePostRequest(
                scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
                timezone="Asia/Kolkata",
                version=6,
            ),
            _current_user(),
            db,
        )

    assert exc.value.status_code == 409
    assert existing["scheduled_time"] == original_time
    assert existing["version"] == 7


@pytest.mark.asyncio
async def test_update_post_rejects_queued_reschedule(monkeypatch):
    existing = _base_post(status="queued")
    db = _FakeDB(existing)
    check_density = AsyncMock(return_value=[])
    monkeypatch.setattr(posts_route, "check_schedule_density", check_density)

    with pytest.raises(HTTPException) as exc:
        await posts_route.update_post(
            "post-1",
            UpdatePostRequest(
                scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
                timezone="Asia/Kolkata",
                version=1,
            ),
            _current_user(),
            db,
        )

    assert exc.value.status_code == 409
    assert "being published" in exc.value.detail
    assert db.posts.update_calls == []
    check_density.assert_not_awaited()


def test_update_post_request_rejects_past_reschedule_time():
    with pytest.raises(ValidationError):
        UpdatePostRequest(
            scheduled_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            timezone="Asia/Kolkata",
            version=1,
        )
