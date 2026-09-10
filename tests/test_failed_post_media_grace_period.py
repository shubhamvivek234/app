import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import posts as posts_routes
from celery_workers.tasks import cleanup, publish


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


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.update_calls = []

    def find(self, query=None, *_args, **_kwargs):
        if not query:
            return FakeCursor(self.docs)
        # Handle simple filtering
        filtered = []
        for doc in self.docs:
            if "media_id" in query and isinstance(query["media_id"], dict) and "$in" in query["media_id"]:
                if doc.get("media_id") in query["media_id"]["$in"]:
                    filtered.append(doc)
            else:
                filtered.append(doc)
        return FakeCursor(filtered)

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            match = True
            for k, v in query.items():
                if k == "$or":
                    continue
                if isinstance(v, dict) and "$exists" in v:
                    if v["$exists"] is False and k in doc and doc[k] is not None:
                        match = False
                        break
                    elif v["$exists"] is True and (k not in doc or doc[k] is None):
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, post_docs, media_asset_docs=None):
        self.posts = FakeCollection(post_docs)
        self.media_assets = FakeCollection(media_asset_docs or [])

    def __getitem__(self, name):
        if name == "posts":
            return self.posts
        if name == "media_assets":
            return self.media_assets
        return FakeCollection([])


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


def test_should_cleanup_media_gate():
    """Verify cleanup gate only allows successful/cancelled posts, blocking failed ones."""
    # Empty -> False
    assert publish.should_cleanup_media({}) is False

    # All published -> True
    assert publish.should_cleanup_media({"twitter": {"status": "published"}, "linkedin": {"status": "published"}}) is True

    # Published + Cancelled -> True
    assert publish.should_cleanup_media({"twitter": {"status": "published"}, "linkedin": {"status": "cancelled"}}) is True

    # Failed platform -> False (grace period!)
    assert publish.should_cleanup_media({"twitter": {"status": "failed"}, "linkedin": {"status": "published"}}) is False

    # Permanently failed platform -> False
    assert publish.should_cleanup_media({"twitter": {"status": "permanently_failed"}}) is False

    # All failed -> False
    assert publish.should_cleanup_media({"twitter": {"status": "failed"}, "facebook": {"status": "failed"}}) is False

    # In-flight / retrying -> False
    assert publish.should_cleanup_media({"twitter": {"status": "retrying"}}) is False


def test_cleanup_expired_failed_posts_media(monkeypatch):
    """Verify expired failed post media is deleted from storage and cleaned up."""
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(hours=50)

    post_doc = {
        "id": "post-failed-1",
        "status": "failed",
        "media_ids": ["media-1"],
        "media_urls": ["https://media.unravler.com/media/user-1/media-1.png"],
        "failed_media_expires_at": expired_time,
        "failed_at": expired_time,
    }
    asset_doc = {
        "media_id": "media-1",
        "storage_key": "media/user-1/media-1.png",
        "source_storage_key": "raw/user-1/media-1.png",
        "thumbnail_url": "https://media.unravler.com/thumbs/media-1.png",
    }
    db = FakeDB([post_doc], [asset_doc])
    delete_mock = AsyncMock()

    monkeypatch.setattr("db.mongo.get_client", AsyncMock(return_value=FakeClient(db)))
    monkeypatch.setattr(cleanup, "_delete_from_storage", delete_mock)
    monkeypatch.setattr("utils.temp_audio_cleanup.cleanup_temporary_audio_for_post_media", AsyncMock())

    result = asyncio.run(cleanup._async_cleanup_expired_failed_posts_media())

    assert result["cleaned"] == 1
    # Check delete calls for both raw source and storage key
    assert delete_mock.await_count == 2
    delete_mock.assert_any_await("raw/user-1/media-1.png")
    delete_mock.assert_any_await("media/user-1/media-1.png")

    # Verify post was updated with media_cleaned_at, media_expired, and media_urls unset
    assert db.posts.update_calls
    _query, update = db.posts.update_calls[0]
    assert update["$set"]["media_expired"] is True
    assert "media_cleaned_at" in update["$set"]
    assert "media_urls" in update["$unset"]
    assert "media_url" in update["$unset"]
    # Verify thumbnail was preserved
    assert update["$set"]["thumbnail_urls"] == ["https://media.unravler.com/thumbs/media-1.png"]


def test_retry_failed_post_guards_against_expired_media(monkeypatch):
    """Verify retry returns 409 if media was cleaned up after 48 hours."""
    post_doc = {
        "id": "post-expired-retry",
        "user_id": "u1",
        "status": "failed",
        "platforms": ["twitter"],
        "media_ids": ["media-expired-1"],
        "media_expired": True,
        "media_cleaned_at": datetime.now(timezone.utc).isoformat(),
        "platform_results": {"twitter": {"status": "failed"}},
    }
    db = FakeDB([post_doc])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            posts_routes.retry_failed_post(
                post_id="post-expired-retry",
                current_user={"user_id": "u1"},
                db=db,
                platform="twitter",
            )
        )
    assert exc_info.value.status_code == 409
    assert "48-hour grace period" in exc_info.value.detail


def test_retry_failed_post_rehydrates_media_within_grace_period(monkeypatch):
    """Verify retry re-hydrates media_urls from media_assets within grace period."""
    post_doc = {
        "id": "post-valid-retry",
        "user_id": "u1",
        "status": "failed",
        "platforms": ["twitter"],
        "media_ids": ["media-valid-1"],
        "media_urls": [],  # empty or lost
        "platform_results": {"twitter": {"status": "failed"}},
    }
    asset_doc = {
        "media_id": "media-valid-1",
        "media_url": "https://media.unravler.com/media/valid.png",
        "thumbnail_url": "https://media.unravler.com/thumbs/valid.png",
        "mime_type": "image/png",
    }
    db = FakeDB([post_doc], [asset_doc])

    monkeypatch.setattr("api.routes.posts.enqueue_task", lambda *args, **kwargs: None)

    res = asyncio.run(
        posts_routes.retry_failed_post(
            post_id="post-valid-retry",
            current_user={"user_id": "u1"},
            db=db,
            platform="twitter",
        )
    )
    assert res["retried"] is True
    assert db.posts.update_calls
    _query, update = db.posts.update_calls[0]
    assert update["$set"]["media_urls"] == ["https://media.unravler.com/media/valid.png"]
    assert update["$set"]["media_url"] == "https://media.unravler.com/media/valid.png"
    assert "failed_media_expires_at" in update["$set"]
