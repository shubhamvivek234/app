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

    async def to_list(self, _length=None):
        return list(self._docs)


class FakePostsCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.update_calls = []

    def find(self, *_args, **_kwargs):
        return FakeCursor(self.docs)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeMediaAssetsCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query, *_args, **_kwargs):
        wanted_ids = set(query.get("media_id", {}).get("$in", []))
        wanted_user_id = query.get("user_id")
        docs = [
            doc
            for doc in self.docs
            if doc.get("media_id") in wanted_ids and doc.get("user_id") == wanted_user_id
        ]
        return FakeCursor(docs)


class FakeDB:
    def __init__(self, post_docs, media_asset_docs=None):
        self.posts = FakePostsCollection(post_docs)
        self.media_assets = FakeMediaAssetsCollection(media_asset_docs or [])


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


def test_hydrate_post_card_fields_backfills_media_and_thumbnail_urls():
    db = FakeDB(
        post_docs=[],
        media_asset_docs=[
            {
                "media_id": "media-1",
                "user_id": "user-1",
                "media_url": "https://media.example/media-1.mp4",
                "thumbnail_url": "https://media.example/media-1.webp",
            }
        ],
    )
    doc = {
        "id": "post-1",
        "user_id": "user-1",
        "post_type": "video",
        "media_ids": ["media-1"],
        "media_urls": [],
        "thumbnail_urls": [],
        "media_url": None,
    }

    hydrated = asyncio.run(posts_routes._hydrate_post_card_fields_for_docs(db, [doc]))

    assert hydrated[0]["media_urls"] == ["https://media.example/media-1.mp4"]
    assert hydrated[0]["thumbnail_urls"] == ["https://media.example/media-1.webp"]
    assert hydrated[0]["media_url"] == "https://media.example/media-1.mp4"
    assert hydrated[0]["published_media_kind"] == "video"


def test_hydrate_post_card_fields_restores_published_thumbnail_url_from_key(monkeypatch):
    monkeypatch.setattr(
        posts_routes,
        "public_url_for_key",
        lambda key: f"https://cdn.example/{key}",
    )
    db = FakeDB(post_docs=[])
    doc = {
        "id": "post-2",
        "user_id": "user-1",
        "post_type": "image",
        "published_card_thumbnail_key": "published-card-thumbnails/user-1/post-2.webp",
        "published_card_thumbnail_url": None,
        "media_urls": [],
        "thumbnail_urls": [],
    }

    hydrated = asyncio.run(posts_routes._hydrate_post_card_fields_for_docs(db, [doc]))

    assert hydrated[0]["published_card_thumbnail_url"] == (
        "https://cdn.example/published-card-thumbnails/user-1/post-2.webp"
    )
