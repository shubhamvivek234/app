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

    def _matches(self, doc, query):
        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches(doc, branch) for branch in expected):
                    return False
                continue

            value = doc.get(key)
            if isinstance(expected, dict):
                for operator, operand in expected.items():
                    left = scheduler._coerce_utc_datetime(value)
                    right = scheduler._coerce_utc_datetime(operand)
                    if operator == "$lte" and not (left <= right):
                        return False
                    if operator == "$gt" and not (left > right):
                        return False
                    if operator == "$exists" and ((key in doc) != operand):
                        return False
                    if operator == "$in" and value not in operand:
                        return False
            elif value != expected:
                return False
        return True

    def find(self, query, projection=None, limit=0, **_kwargs):
        self.find_calls.append((query, projection, limit))
        matches = []
        for doc in self.docs:
            if not self._matches(doc, query):
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
            if not self._matches(doc, query):
                continue
            if "$set" in update:
                self.docs[index].update(update["$set"])
            if "$unset" in update:
                for key in update["$unset"].keys():
                    self.docs[index].pop(key, None)
            if "$push" in update:
                for key, value in update["$push"].items():
                    self.docs[index].setdefault(key, []).append(value)
            return dict(self.docs[index])
        return None

    async def update_one(self, query, update):
        for index, doc in enumerate(self.docs):
            if not self._matches(doc, query):
                continue
            if "$set" in update:
                self.docs[index].update(update["$set"])
            if "$unset" in update:
                for key in update["$unset"].keys():
                    self.docs[index].pop(key, None)
            if "$push" in update:
                for key, value in update["$push"].items():
                    self.docs[index].setdefault(key, []).append(value)
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
    apply_async_mock = Mock(return_value=SimpleNamespace(id="job-1"))
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 1
    assert result["recovered"] == 0
    assert apply_async_mock.call_count == 1
    call = apply_async_mock.call_args
    assert call.kwargs["queue"] == "high_priority"
    assert call.kwargs["kwargs"] == {"post_id": "post-1", "version": 3}

    expected_delay = (
        scheduled_time - datetime.fromisoformat(result["scan_time"])
    ).total_seconds()
    assert abs(call.kwargs["countdown"] - expected_delay) < 2.5
    assert fake_db.posts.docs[0]["status"] == "queued"
    assert fake_db.posts.docs[0]["queue_job_id"] == "job-1"


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
    apply_async_mock = Mock(side_effect=[
        SimpleNamespace(id="job-1"),
        SimpleNamespace(id="job-2"),
    ])
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 2
    assert result["recovered"] == 0
    assert apply_async_mock.call_count == 2
    assert [doc["status"] for doc in fake_db.posts.docs] == ["queued", "queued", "scheduled"]


@pytest.mark.asyncio
async def test_scan_and_enqueue_coerces_naive_scheduled_time(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    scheduled_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=12)
    naive_scheduled_time = scheduled_time.replace(tzinfo=None)
    fake_db = _FakeDB([
        {
            "id": "post-naive",
            "status": "scheduled",
            "scheduled_time": naive_scheduled_time,
            "platforms": ["instagram"],
            "version": 4,
            "post_type": "text",
        }
    ])

    monkeypatch.setattr(scheduler, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    apply_async_mock = Mock(return_value=SimpleNamespace(id="job-naive"))
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 1
    assert fake_db.posts.docs[0]["status"] == "queued"
    assert fake_db.posts.docs[0]["queue_job_id"] == "job-naive"
    assert apply_async_mock.call_args.kwargs["queue"] == "high_priority"


@pytest.mark.asyncio
async def test_scan_and_enqueue_reverts_status_when_parent_enqueue_fails(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=10)
    fake_db = _FakeDB([
        {
            "id": "post-fail",
            "status": "scheduled",
            "scheduled_time": scheduled_time,
            "platforms": ["instagram"],
            "version": 1,
            "post_type": "text",
        }
    ])

    monkeypatch.setattr(scheduler, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", Mock(side_effect=RuntimeError("broker down")))

    result = await scheduler._async_scan_and_enqueue()

    assert result["enqueued"] == 0
    assert fake_db.posts.docs[0]["status"] == "scheduled"
    assert "scheduler_claimed_at" not in fake_db.posts.docs[0]
    assert fake_db.posts.docs[0]["queue_job_id"] is None
    assert fake_db.posts.docs[0]["status_history"][-1]["message"] == "Parent publish enqueue failed; reverted to scheduled for retry"


@pytest.mark.asyncio
async def test_scan_and_enqueue_recovers_stale_claimed_posts(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    stale_claim = now - timedelta(minutes=8)
    fake_db = _FakeDB([
        {
            "id": "post-stale",
            "status": "queued",
            "scheduled_time": now - timedelta(minutes=2),
            "platforms": ["instagram"],
            "version": 2,
            "post_type": "text",
            "queue_job_id": None,
            "scheduler_claimed_at": stale_claim,
            "status_history": [{"status": "queued", "timestamp": stale_claim.isoformat(), "actor": "beat_scheduler"}],
        }
    ])

    monkeypatch.setenv("SCHEDULER_CLAIM_RECOVERY_SECS", "60")
    monkeypatch.setattr(scheduler, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    apply_async_mock = Mock(return_value=SimpleNamespace(id="job-recovered"))
    monkeypatch.setattr(publish_tasks.publish_post, "apply_async", apply_async_mock)

    result = await scheduler._async_scan_and_enqueue()

    assert result["recovered"] == 1
    assert result["enqueued"] == 1
    assert fake_db.posts.docs[0]["status"] == "queued"
    assert fake_db.posts.docs[0]["queue_job_id"] == "job-recovered"
    assert fake_db.posts.docs[0]["status_history"][-2]["actor"] == "beat_scheduler_recovery"
