import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from celery_workers.tasks import cleanup


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

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if doc.get("id") == query.get("id"):
                return dict(doc)
        return None

    def find(self, query, *_args, **_kwargs):
        excluded_id = query.get("id", {}).get("$ne")
        user_id = query.get("user_id")
        workspace_id = query.get("workspace_id")
        require_not_deleted = query.get("deleted_at") == {"$exists": False}

        matches = []
        for doc in self.docs:
            if excluded_id and doc.get("id") == excluded_id:
                continue
            if user_id is not None and doc.get("user_id") != user_id:
                continue
            if workspace_id != doc.get("workspace_id"):
                continue
            if require_not_deleted and "deleted_at" in doc:
                continue
            matches.append(dict(doc))
        return _FakeCursor(matches)


class _FakeMediaAssetsCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.delete_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if doc.get("media_id") == query.get("media_id"):
                return dict(doc)
        return None

    async def delete_one(self, query):
        media_id = query.get("media_id")
        self.delete_calls.append(query)
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if doc.get("media_id") != media_id]
        return SimpleNamespace(deleted_count=1 if len(self.docs) != before else 0)


class _FakeDB:
    def __init__(self, post_docs, media_docs):
        self.posts = _FakePostsCollection(post_docs)
        self.media_assets = _FakeMediaAssetsCollection(media_docs)


class _FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


def test_cleanup_deleted_post_media_deletes_orphaned_asset_and_storage_refs(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    deleted_post = {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "media_ids": ["media-1"],
        "deleted_at": datetime.now(timezone.utc),
    }
    media_doc = {
        "media_id": "media-1",
        "storage_key": "media/user-1/media-1.jpg",
        "source_storage_key": "raw/user-1/media-1.jpg",
        "thumbnail_url": "https://cdn.example/thumb.webp",
        "media_url": "https://cdn.example/media-1.jpg",
    }
    db = _FakeDB([deleted_post], [media_doc])
    delete_mock = AsyncMock()

    monkeypatch.setattr("db.mongo.get_client", AsyncMock(return_value=_FakeClient(db)))
    monkeypatch.setattr(cleanup, "_delete_from_storage", delete_mock)

    result = asyncio.run(cleanup._async_cleanup_deleted_post_media("post-1"))

    assert result == {"status": "cleaned", "deleted_media": 1, "retained_media": 0, "failed_media": 0}
    assert delete_mock.await_count == 4
    assert db.media_assets.delete_calls == [{"media_id": "media-1"}]
    assert db.media_assets.docs == []


def test_cleanup_deleted_post_media_preserves_shared_assets(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    deleted_post = {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "media_ids": ["media-1"],
        "deleted_at": datetime.now(timezone.utc),
    }
    active_post = {
        "id": "post-2",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "media_ids": ["media-1"],
    }
    media_doc = {
        "media_id": "media-1",
        "storage_key": "media/user-1/media-1.jpg",
    }
    db = _FakeDB([deleted_post, active_post], [media_doc])
    delete_mock = AsyncMock()

    monkeypatch.setattr("db.mongo.get_client", AsyncMock(return_value=_FakeClient(db)))
    monkeypatch.setattr(cleanup, "_delete_from_storage", delete_mock)

    result = asyncio.run(cleanup._async_cleanup_deleted_post_media("post-1"))

    assert result == {"status": "cleaned", "deleted_media": 0, "retained_media": 1, "failed_media": 0}
    delete_mock.assert_not_awaited()
    assert db.media_assets.docs == [media_doc]


def test_cleanup_deleted_post_media_collects_override_media_ids(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    deleted_post = {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "media_ids": [],
        "platform_overrides": {"instagram": {"media_ids": ["media-2"]}},
        "account_overrides": {"acct-1": {"media_ids": ["media-3"]}},
        "deleted_at": datetime.now(timezone.utc),
    }
    media_docs = [
        {"media_id": "media-2", "storage_key": "media/user-1/media-2.jpg"},
        {"media_id": "media-3", "storage_key": "media/user-1/media-3.jpg"},
    ]
    db = _FakeDB([deleted_post], media_docs)
    delete_mock = AsyncMock()

    monkeypatch.setattr("db.mongo.get_client", AsyncMock(return_value=_FakeClient(db)))
    monkeypatch.setattr(cleanup, "_delete_from_storage", delete_mock)

    result = asyncio.run(cleanup._async_cleanup_deleted_post_media("post-1"))

    assert result == {"status": "cleaned", "deleted_media": 2, "retained_media": 0, "failed_media": 0}
    assert sorted(call.args[0] for call in delete_mock.await_args_list) == [
        "media/user-1/media-2.jpg",
        "media/user-1/media-3.jpg",
    ]


def test_cleanup_deleted_post_media_keeps_db_record_when_storage_delete_fails(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    deleted_post = {
        "id": "post-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "media_ids": ["media-1"],
        "deleted_at": datetime.now(timezone.utc),
    }
    media_doc = {
        "media_id": "media-1",
        "storage_key": "media/user-1/media-1.jpg",
        "source_storage_key": "raw/user-1/media-1.jpg",
    }
    db = _FakeDB([deleted_post], [media_doc])

    async def _raise_once(_ref):
        raise RuntimeError("r2 delete failed")

    monkeypatch.setattr("db.mongo.get_client", AsyncMock(return_value=_FakeClient(db)))
    monkeypatch.setattr(cleanup, "_delete_from_storage", AsyncMock(side_effect=_raise_once))

    result = asyncio.run(cleanup._async_cleanup_deleted_post_media("post-1"))

    assert result == {"status": "cleaned", "deleted_media": 0, "retained_media": 0, "failed_media": 1}
    assert db.media_assets.delete_calls == []
    assert db.media_assets.docs == [media_doc]
