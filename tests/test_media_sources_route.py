from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.models.media import CanvaCallbackRequest, RemoteMediaImportRequest
from api.routes import media_sources as media_sources_route
from utils.media_source_imports import assert_allowed_provider_url


class _FakeMediaAssetsCollection:
    def __init__(self):
        self.docs = []
        self.update_calls = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc["media_id"])

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def count_documents(self, _query):
        return 0


class _FakeDB:
    def __init__(self):
        self.media_assets = _FakeMediaAssetsCollection()


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)
        return 1


class _FakeUnsplashResponse:
    def __init__(self):
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {
                    "id": "photo_1",
                    "description": "Sunrise",
                    "urls": {
                        "thumb": "https://images.unsplash.com/thumb.jpg",
                        "small": "https://images.unsplash.com/small.jpg",
                        "full": "https://images.unsplash.com/full.jpg",
                    },
                    "links": {
                        "download_location": "https://api.unsplash.com/photos/photo_1/download",
                        "html": "https://unsplash.com/photos/photo_1",
                    },
                    "user": {
                        "name": "Ada",
                        "username": "ada",
                        "links": {"html": "https://unsplash.com/@ada"},
                    },
                }
            ],
            "total_pages": 3,
        }


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *_args, **_kwargs):
        return self.response


@pytest.mark.asyncio
async def test_search_unsplash_returns_normalized_payload(monkeypatch):
    monkeypatch.setattr(media_sources_route, "_resolve_unsplash_key", lambda: "unsplash-key")
    monkeypatch.setattr(
        media_sources_route.httpx,
        "AsyncClient",
        lambda timeout=20.0: _FakeAsyncClient(_FakeUnsplashResponse()),
    )

    result = await media_sources_route.search_unsplash.__wrapped__(
        request=SimpleNamespace(),
        current_user={"user_id": "user-1"},
        q="sunrise",
        page=2,
    )

    assert result["page"] == 2
    assert result["has_more"] is True
    assert result["results"][0]["id"] == "photo_1"
    assert result["results"][0]["photographer_name"] == "Ada"
    assert result["results"][0]["source_attribution"]["provider"] == "unsplash"


@pytest.mark.asyncio
async def test_import_media_sources_creates_jobs_and_stores_source_metadata(monkeypatch):
    db = _FakeDB()
    cache_redis = _FakeRedis()
    queued_tasks = []

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(media_sources_route, "_check_queue_depth", _noop)
    monkeypatch.setattr(media_sources_route, "_check_user_upload_backlog", _noop)
    monkeypatch.setattr(media_sources_route, "_reserve_concurrent_upload_slot", _noop)
    monkeypatch.setattr(media_sources_route, "_track_unsplash_download_if_needed", _noop)
    monkeypatch.setattr(
        media_sources_route,
        "enqueue_task",
        lambda task_name, **kwargs: queued_tasks.append((task_name, kwargs)),
    )

    payload = RemoteMediaImportRequest.model_validate(
        {
            "items": [
                {
                    "provider": "google_drive",
                    "download_url": "https://www.googleapis.com/drive/v3/files/abc?alt=media",
                    "name": "launch.mp4",
                    "source_item_id": "abc",
                    "source_label": "Launch cut",
                    "content_type": "video/mp4",
                    "auth_bearer_token": "token-1",
                },
                {
                    "provider": "dropbox",
                    "download_url": "https://www.dropbox.com/s/example/image.png?dl=1",
                    "name": "image.png",
                    "source_item_id": "dbx_1",
                    "source_label": "Dropbox image",
                },
            ]
        }
    )

    response = await media_sources_route.import_media_sources(
        payload=payload,
        current_user={"user_id": "user-1", "plan": "starter", "subscription_status": "active"},
        db=db,
        cache_redis=cache_redis,
        queue_redis=SimpleNamespace(),
    )

    assert len(response.imports) == 2
    assert len(db.media_assets.docs) == 2
    assert db.media_assets.docs[0]["source_provider"] == "google_drive"
    assert db.media_assets.docs[0]["source_item_id"] == "abc"
    assert db.media_assets.docs[0]["source_stage"] == media_sources_route.MediaSourceStage.FETCHING
    assert db.media_assets.docs[0]["source_auth_ref"].startswith("media_source_auth:")
    assert db.media_assets.docs[1]["source_provider"] == "dropbox"
    assert queued_tasks[0][0] == "celery_workers.tasks.media.import_remote_media"


@pytest.mark.asyncio
async def test_canva_callback_exchanges_code_and_stores_short_lived_session(monkeypatch):
    cache_redis = _FakeRedis()
    state_payload = {
        "user_id": "user-1",
        "code_verifier": "verifier",
        "redirect_uri": "https://app.example.com/api/media-sources/canva/callback",
        "frontend_base": "https://app.example.com",
    }
    cache_redis.store["canva_import_state:state-123"] = json.dumps(state_payload)

    async def fake_exchange_canva_code(*, code, verifier, redirect_uri):
        assert code == "auth-code"
        assert verifier == "verifier"
        assert redirect_uri == state_payload["redirect_uri"]
        return {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}

    monkeypatch.setattr(media_sources_route, "_exchange_canva_code", fake_exchange_canva_code)

    response = await media_sources_route.canva_import_callback(
        payload=CanvaCallbackRequest(code="auth-code", state="state-123"),
        current_user={"user_id": "user-1"},
        cache_redis=cache_redis,
    )

    assert response.session_id
    assert response.expires_at > datetime.now(timezone.utc)
    stored_keys = [key for key in cache_redis.store if key.startswith("canva_import_session:")]
    assert stored_keys


def test_provider_url_allowlist_blocks_cross_provider_targets():
    assert_allowed_provider_url("dropbox", "https://www.dropbox.com/s/example/file.jpg?dl=1")
    with pytest.raises(ValueError):
        assert_allowed_provider_url("dropbox", "https://example.com/file.jpg")
