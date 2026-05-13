import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import posts as posts_routes
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


class FakePostsCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.update_calls = []

    def find(self, *_args, **_kwargs):
        return FakeCursor(self.docs)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, post_docs):
        self.posts = FakePostsCollection(post_docs)


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


def test_cleanup_expired_published_card_thumbnails_unsets_thumbnail_fields(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post_doc = {
        "id": "post-1",
        "published_card_thumbnail_key": "published-card-thumbnails/user-1/post-1.webp",
        "published_card_thumbnail_url": "https://media.unravler.com/published-card-thumbnails/user-1/post-1.webp",
        "published_card_thumbnail_created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    db = FakeDB([post_doc])
    delete_mock = AsyncMock()

    monkeypatch.setattr(
        "db.mongo.get_client",
        AsyncMock(return_value=FakeClient(db)),
    )
    monkeypatch.setattr(cleanup, "_delete_from_storage", delete_mock)

    result = asyncio.run(cleanup._async_cleanup_expired_published_card_thumbnails())

    assert result["cleaned"] == 1
    delete_mock.assert_awaited_once_with("published-card-thumbnails/user-1/post-1.webp")
    assert db.posts.update_calls
    _query, update = db.posts.update_calls[0]
    assert "published_card_thumbnail_url" in update["$unset"]
    assert "published_card_thumbnail_key" in update["$unset"]
    assert "published_card_thumbnail_created_at" in update["$unset"]


def test_infer_published_media_kind_supports_mixed_posts():
    doc = {
        "media_types": ["image", "video"],
        "post_type": "mixed",
    }

    assert posts_routes._infer_published_media_kind(doc) == "mixed"


def test_infer_published_media_kind_falls_back_to_text():
    doc = {
        "content": "Text only post",
        "post_type": "text",
        "media_urls": [],
        "thumbnail_urls": [],
    }

    assert posts_routes._infer_published_media_kind(doc) == "text"
