import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from celery_workers.tasks import publish as publish_tasks


class FakePostsCollection:
    def __init__(self, post):
        self.post = dict(post)
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        if query.get("id") != self.post["id"]:
            return None
        return dict(self.post)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if "$set" in update:
            self.post.update(update["$set"])
        if "$push" in update:
            for key, value in update["$push"].items():
                self.post.setdefault(key, []).append(value)
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, post):
        self.posts = FakePostsCollection(post)


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_publish_post_dispatches_children_explicitly_and_records_task_ids(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-1",
        "version": 1,
        "post_type": "video",
        "platforms": ["youtube", "linkedin"],
        "publish_targets": [
            {"platform": "youtube", "account_id": "youtube-account-1"},
            {"platform": "linkedin", "account_id": "linkedin-account-1"},
        ],
        "account_results": {
            "youtube-account-1": {"status": "pending"},
            "linkedin-account-1": {"status": "pending"},
        },
        "platform_results": {
            "youtube": {"status": "pending"},
            "linkedin": {"status": "pending"},
        },
        "status_history": [{"status": "queued", "timestamp": datetime.now(timezone.utc), "actor": "user"}],
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="parent-task-1"))

    monkeypatch.setattr(publish_tasks, "_check_poison_pill", AsyncMock(return_value=False))
    monkeypatch.setattr("celery_workers.shutdown_handler.is_shutting_down", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "_jitter_seconds", Mock(return_value=0))

    child_results = [SimpleNamespace(id="child-youtube"), SimpleNamespace(id="child-linkedin")]
    apply_async_mock = Mock(side_effect=child_results)
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)

    result = await publish_tasks._async_publish_post(fake_task, "post-1", 1)

    assert result["status"] == "dispatched"
    assert [child["task_id"] for child in result["child_tasks"]] == ["child-youtube", "child-linkedin"]
    assert apply_async_mock.call_count == 2

    youtube_call = apply_async_mock.call_args_list[0]
    linkedin_call = apply_async_mock.call_args_list[1]
    assert youtube_call.kwargs["queue"] == "publish_video"
    assert linkedin_call.kwargs["queue"] == "publish_video"

    assert len(fake_db.posts.update_calls) == 2
    dispatch_update = fake_db.posts.update_calls[1][1]["$set"]
    assert dispatch_update["account_results.youtube-account-1.dispatch_task_id"] == "child-youtube"
    assert dispatch_update["account_results.linkedin-account-1.dispatch_task_id"] == "child-linkedin"
    assert dispatch_update["platform_results.youtube.dispatch_task_id"] == "child-youtube"
    assert dispatch_update["platform_results.linkedin.dispatch_task_id"] == "child-linkedin"
