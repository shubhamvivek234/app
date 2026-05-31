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

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if query.get("id") == doc.get("id"):
                return doc
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, docs):
        self.posts = FakePostsCollection(docs)
        self.social_accounts = SimpleNamespace(find_one=AsyncMock(return_value=None))


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
    assert kwargs["dispatch_source"] == "recovery"
    assert apply_async_mock.call_args.kwargs["queue"] == "default"
    assert fake_db.posts.update_calls
    _query, update = fake_db.posts.update_calls[0]
    set_fields = update["$set"]
    assert set_fields["account_results.youtube-account-1.status"] == "retrying"
    assert set_fields["platform_results.youtube.status"] == "retrying"
    assert fake_db.posts.find_calls
    find_query = fake_db.posts.find_calls[0][0][0]
    cutoff = find_query["updated_at"]["$lt"]
    assert now - cutoff < timedelta(minutes=4)


@pytest.mark.asyncio
async def test_poll_status_requeues_retrying_orphaned_video_publish(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    last_attempt = now - timedelta(minutes=5)
    post = {
        "id": "post-2",
        "status": "processing",
        "platforms": ["youtube"],
        "post_type": "video",
        "updated_at": now - timedelta(minutes=6),
        "pre_upload_status": None,
        "publish_targets": [
            {
                "platform": "youtube",
                "account_id": "youtube-account-2",
            }
        ],
        "platform_results": {
            "youtube": {
                "status": "retrying",
                "platform_post_id": None,
                "last_attempt_at": last_attempt,
            }
        },
        "account_results": {
            "youtube-account-2": {
                "status": "retrying",
                "platform_post_id": None,
                "last_attempt_at": last_attempt,
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
    assert apply_async_mock.call_count == 1
    assert apply_async_mock.call_args.kwargs["queue"] == "default"
    kwargs = apply_async_mock.call_args.kwargs["kwargs"]
    assert kwargs["dispatch_source"] == "recovery"
    assert kwargs["account_id"] == "youtube-account-2"


@pytest.mark.asyncio
async def test_poll_status_finalizes_tiktok_processing_publish(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-tiktok-1",
        "user_id": "user-1",
        "status": "processing",
        "platforms": ["tiktok"],
        "post_type": "video",
        "updated_at": now - timedelta(minutes=20),
        "publish_targets": [
            {
                "platform": "tiktok",
                "account_id": "tiktok-account-1",
            }
        ],
        "platform_results": {
            "tiktok": {
                "status": "processing",
                "platform_post_id": "publish-123",
                "last_attempt_at": now - timedelta(minutes=20),
            }
        },
        "account_results": {
            "tiktok-account-1": {
                "status": "processing",
                "platform_post_id": "publish-123",
                "last_attempt_at": now - timedelta(minutes=20),
            }
        },
    }
    fake_db = FakeDB([post])
    fake_db.social_accounts = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "tiktok-account-1",
                "account_id": "tiktok-account-1",
                "platform": "tiktok",
                "user_id": "user-1",
                "is_active": True,
                "access_token": "encrypted-token",
            }
        )
    )

    monkeypatch.setattr(poll_status, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr("db.redis_client.get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr("utils.encryption.decrypt", Mock(return_value="plain-token"))
    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=SimpleNamespace(check_status=AsyncMock(return_value="published"))))

    finalize_mock = AsyncMock(return_value=("user-1", "processing", "published"))
    monkeypatch.setattr("celery_workers.tasks.publish._finalize_post_status", finalize_mock)

    result = await poll_status._async_poll()

    assert result["polled"] == 1
    assert result["resolved"] == 1
    finalize_mock.assert_awaited_once()
    assert any(
        "$set" in update and update["$set"].get("account_results.tiktok-account-1.status") == "published"
        for _query, update in fake_db.posts.update_calls
    )


@pytest.mark.asyncio
async def test_poll_status_handles_naive_mongo_datetimes(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    naive_updated = (now - timedelta(minutes=20)).replace(tzinfo=None)
    naive_attempt = (now - timedelta(minutes=20)).replace(tzinfo=None)
    post = {
        "id": "post-tiktok-naive-1",
        "user_id": "user-1",
        "status": "processing",
        "platforms": ["tiktok"],
        "post_type": "video",
        "updated_at": naive_updated,
        "publish_targets": [
            {
                "platform": "tiktok",
                "account_id": "tiktok-account-1",
            }
        ],
        "platform_results": {
            "tiktok": {
                "status": "processing",
                "platform_post_id": "publish-456",
                "last_attempt_at": naive_attempt,
            }
        },
        "account_results": {
            "tiktok-account-1": {
                "status": "processing",
                "platform_post_id": "publish-456",
                "last_attempt_at": naive_attempt,
            }
        },
    }
    fake_db = FakeDB([post])
    fake_db.social_accounts = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "tiktok-account-1",
                "account_id": "tiktok-account-1",
                "platform": "tiktok",
                "user_id": "user-1",
                "is_active": True,
                "access_token": "encrypted-token",
            }
        )
    )

    monkeypatch.setattr(poll_status, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr("db.redis_client.get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr("utils.encryption.decrypt", Mock(return_value="plain-token"))
    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=SimpleNamespace(check_status=AsyncMock(return_value="published"))))

    finalize_mock = AsyncMock(return_value=("user-1", "processing", "published"))
    monkeypatch.setattr("celery_workers.tasks.publish._finalize_post_status", finalize_mock)

    result = await poll_status._async_poll()

    assert result["polled"] == 1
    assert result["resolved"] == 1
    finalize_mock.assert_awaited_once()
