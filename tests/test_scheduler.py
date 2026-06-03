import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from celery_workers.tasks import publish as publish_tasks
from celery_workers.tasks import scheduler


class _FakeCursor:
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


class _FakePostsCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.find_calls = []
        self.claim_calls = []

    def find(self, query, projection=None, limit=0, **_kwargs):
        self.find_calls.append((query, projection, limit))
        matches = []
        for doc in self.docs:
            if query.get("status") and doc.get("status") != query["status"]:
                continue
            scheduled_time = doc.get("scheduled_time")
            scheduled_filter = query.get("scheduled_time") or {}
            if "$lte" in scheduled_filter and not (scheduled_time <= scheduled_filter["$lte"]):
                continue
            if "$gt" in scheduled_filter and not (scheduled_time > scheduled_filter["$gt"]):
                continue
            post_type_filter = query.get("post_type") or {}
            allowed_types = post_type_filter.get("$in")
            if allowed_types and doc.get("post_type") not in allowed_types:
                continue
            if projection:
                projected = {
                    key: doc[key]
                    for key in projection.keys()
                    if projection[key] and key in doc
                }
                matches.append(projected)
            else:
                matches.append(dict(doc))
        if limit:
            matches = matches[:limit]
        return _FakeCursor(matches)

    async def find_one_and_update(self, query, update, **_kwargs):
        self.claim_calls.append((query, update))
        for index, doc in enumerate(self.docs):
            if query.get("id") and doc.get("id") != query["id"]:
                continue
            if query.get("status") and doc.get("status") != query["status"]:
                continue
            if "$set" in update:
                self.docs[index].update(update["$set"])
            if "$push" in update:
                for key, value in update["$push"].items():
                    self.docs[index].setdefault(key, []).append(value)
            return dict(self.docs[index])
        return None

    async def update_one(self, query, update):
        for index, doc in enumerate(self.docs):
            if query.get("id") and doc.get("id") != query["id"]:
                continue
            if "$set" in update:
                self.docs[index].update(update["$set"])
            return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class _FakeDB:
    def __init__(self, docs):
        self.posts = _FakePostsCollection(docs)


class _FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_scan_and_enqueue_delays_parent_until_exact_scheduled_time(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=18)
    fake_db = _FakeDB([
        {
            "id": "post-1",
            "status": "scheduled",
            "scheduled_time": scheduled_time,
            "platforms": ["instagram"],
            "version": 3,
            "post_type": "text",
        }
    ])

    monkeypatch.setattr(scheduler, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    apply_async_mock = Mock()
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 1
    assert apply_async_mock.call_count == 1
    call = apply_async_mock.call_args
    assert call.kwargs["queue"] == "high_priority"
    assert call.kwargs["kwargs"] == {"post_id": "post-1", "version": 3}

    expected_delay = (
        scheduled_time - datetime.fromisoformat(result["scan_time"])
    ).total_seconds()
    assert abs(call.kwargs["countdown"] - expected_delay) < 2.5
    assert fake_db.posts.docs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_scan_and_enqueue_processes_multiple_batches(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc) + timedelta(seconds=20)
    fake_db = _FakeDB([
        {
            "id": "post-1",
            "status": "scheduled",
            "scheduled_time": now,
            "platforms": ["instagram"],
            "version": 1,
            "post_type": "text",
        },
        {
            "id": "post-2",
            "status": "scheduled",
            "scheduled_time": now,
            "platforms": ["instagram"],
            "version": 1,
            "post_type": "text",
        },
        {
            "id": "post-3",
            "status": "scheduled",
            "scheduled_time": now,
            "platforms": ["instagram"],
            "version": 1,
            "post_type": "text",
        },
    ])

    monkeypatch.setenv("SCHEDULE_SCAN_BATCH_SIZE", "1")
    monkeypatch.setenv("SCHEDULE_SCAN_MAX_BATCHES", "2")
    monkeypatch.setattr(scheduler, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    apply_async_mock = Mock()
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 2
    assert apply_async_mock.call_count == 2
    assert [doc["status"] for doc in fake_db.posts.docs] == ["queued", "queued", "scheduled"]
