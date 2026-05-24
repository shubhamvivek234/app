from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.routes import posts as posts_route
from celery_workers.tasks import publish as publish_tasks


class _FakePostsCollection:
    def __init__(self, existing):
        self.existing = existing
        self.find_calls = []
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        self.find_calls.append(query)
        if query.get("id") == self.existing.get("id") and query.get("user_id") == self.existing.get("user_id"):
            return dict(self.existing)
        if query.get("id") == self.existing.get("id") and "user_id" not in query:
            return dict(self.existing)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if "$set" in update:
            self.existing.update(update["$set"])
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, existing):
        self.posts = _FakePostsCollection(existing)


class _FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_delete_processing_post_revokes_parent_and_child_tasks(monkeypatch):
    existing = {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "status": "processing",
        "queue_job_id": "parent-task-id",
        "platform_results": {
            "youtube": {"status": "pending", "dispatch_task_id": "child-platform-task"},
        },
        "account_results": {
            "youtube-account-1": {"status": "pending", "dispatch_task_id": "child-account-task"},
        },
    }
    db = _FakeDB(existing)
    revoke_mock = Mock()
    enqueue_mock = Mock()

    monkeypatch.setattr(posts_route, "revoke_task", revoke_mock)
    monkeypatch.setattr(posts_route, "enqueue_task", enqueue_mock)
    monkeypatch.setattr(posts_route, "log_audit_event", AsyncMock())

    await posts_route.delete_post("post-1", {"user_id": "user-1"}, db)

    assert revoke_mock.call_count == 3
    revoke_mock.assert_any_call("parent-task-id", terminate=False)
    revoke_mock.assert_any_call("child-platform-task", terminate=False)
    revoke_mock.assert_any_call("child-account-task", terminate=False)

    assert db.posts.update_calls
    set_updates = db.posts.update_calls[0][1]["$set"]
    assert set_updates["status"] == "cancelled"
    assert set_updates["platform_results.youtube.status"] == "cancelled"
    assert set_updates["account_results.youtube-account-1.status"] == "cancelled"
    enqueue_mock.assert_called_once()


@pytest.mark.asyncio
async def test_publish_parent_aborts_when_post_already_cancelled(monkeypatch):
    monkeypatch.setenv("DB_NAME", "testdb")
    fake_task = SimpleNamespace(request=SimpleNamespace(id="parent-task-1"))
    existing = {
        "id": "post-1",
        "status": "cancelled",
        "deleted_at": datetime.now(timezone.utc),
        "version": 1,
    }

    monkeypatch.setattr(publish_tasks, "_check_poison_pill", AsyncMock(return_value=False))
    monkeypatch.setattr("celery_workers.shutdown_handler.is_shutting_down", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=_FakeClient(_FakeDB(existing))))

    apply_async_mock = Mock()
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)

    result = await publish_tasks._async_publish_post(fake_task, "post-1", 1)

    assert result["status"] == "post_deleted"
    apply_async_mock.assert_not_called()
