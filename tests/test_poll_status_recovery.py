import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from celery_workers.tasks import poll_status
from celery_workers.tasks import publish as publish_tasks


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakePostsCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.update_calls = []
        self.find_calls = []

    def find(self, *args, **kwargs):
        self.find_calls.append((args, kwargs))
        return FakeCursor(self.docs)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, docs):
        self.posts = FakePostsCollection(docs)


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_poll_status_requeues_orphaned_child_publish_task(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-1",
        "status": "processing",
        "platforms": ["youtube"],
        "post_type": "video",
        "updated_at": now - timedelta(minutes=6),
        "pre_upload_status": None,
        "publish_targets": [
            {
                "platform": "youtube",
                "account_id": "youtube-account-1",
            }
        ],
        "platform_results": {
            "youtube": {
                "status": "pending",
                "platform_post_id": None,
                "last_attempt_at": None,
            }
        },
        "account_results": {
            "youtube-account-1": {
                "status": "pending",
                "platform_post_id": None,
                "last_attempt_at": None,
            }
        },
    }
    fake_db = FakeDB([post])

    monkeypatch.setattr(poll_status, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr("db.redis_client.get_cache_redis", Mock(return_value=object()))

    apply_async_mock = Mock()
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)

    result = await poll_status._async_poll()

    assert result["requeued"] == 1
    assert result["resolved"] == 0
    assert apply_async_mock.call_count == 1
    kwargs = apply_async_mock.call_args.kwargs["kwargs"]
    assert kwargs["post_id"] == "post-1"
    assert kwargs["platform"] == "youtube"
    assert kwargs["account_id"] == "youtube-account-1"
    assert fake_db.posts.update_calls
    _query, update = fake_db.posts.update_calls[0]
    set_fields = update["$set"]
    assert set_fields["account_results.youtube-account-1.status"] == "retrying"
    assert set_fields["platform_results.youtube.status"] == "retrying"
    assert fake_db.posts.find_calls
    find_query = fake_db.posts.find_calls[0][0][0]
    cutoff = find_query["updated_at"]["$lt"]
    assert now - cutoff < timedelta(minutes=4)
