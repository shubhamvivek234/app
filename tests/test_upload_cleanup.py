import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.models.media import MediaStatus
from celery_workers.tasks import cleanup


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


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.update_calls = []

    def find(self, *_args, **_kwargs):
        return FakeCursor(self.docs)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, docs):
        self.media_assets = FakeCollection(docs)


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


@pytest.mark.asyncio
async def test_stale_upload_scan_recovers_existing_raw_object(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    doc = {
        "media_id": "media-1",
        "user_id": "user-1",
        "status": MediaStatus.PENDING_UPLOAD,
        "source_storage_key": "raw/user-1/media-1.jpg",
        "upload_mode": "single",
        "upload_expires_at": 1,
    }
    db = FakeDB([doc])

    monkeypatch.setattr(cleanup, "_release_upload_slot_if_possible", AsyncMock())
    monkeypatch.setattr("utils.storage.head_storage_object_async", AsyncMock(return_value={"size": 1234}))
    monkeypatch.setattr(
        "db.mongo.get_client",
        AsyncMock(return_value=FakeClient(db)),
    )

    process_media_stub = SimpleNamespace(apply_async=Mock())
    monkeypatch.setattr("celery_workers.tasks.media.process_media", process_media_stub, raising=False)

    result = await cleanup._async_scan_stale_direct_uploads()

    assert result["recovered"] == 1
    assert result["failed"] == 0
    assert db.media_assets.update_calls
    _query, update = db.media_assets.update_calls[0]
    assert update["$set"]["status"] == MediaStatus.PROCESSING
    assert update["$set"]["recovered_from_expired_upload"] is True


@pytest.mark.asyncio
async def test_stale_upload_scan_fails_missing_raw_object(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    doc = {
        "media_id": "media-2",
        "user_id": "user-2",
        "status": MediaStatus.PENDING_UPLOAD,
        "source_storage_key": "raw/user-2/media-2.mp4",
        "upload_mode": "multipart",
        "upload_session_id": "upload-123",
        "upload_expires_at": 1,
    }
    db = FakeDB([doc])

    monkeypatch.setattr(cleanup, "_release_upload_slot_if_possible", AsyncMock())
    monkeypatch.setattr("utils.storage.head_storage_object_async", AsyncMock(return_value=None))
    abort_mock = Mock()
    monkeypatch.setattr("utils.storage.abort_direct_upload_session", abort_mock)
    monkeypatch.setattr(
        "db.mongo.get_client",
        AsyncMock(return_value=FakeClient(db)),
    )

    result = await cleanup._async_scan_stale_direct_uploads()

    assert result["recovered"] == 0
    assert result["failed"] == 1
    assert abort_mock.call_count == 1
    assert db.media_assets.update_calls
    _query, update = db.media_assets.update_calls[0]
    assert update["$set"]["status"] == MediaStatus.FAILED
    assert update["$set"]["error_message"] == "Direct upload expired before completion"
