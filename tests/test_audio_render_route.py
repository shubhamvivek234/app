from types import SimpleNamespace

import pytest

from api.models.media import AudioRenderRequest
from api.routes import audio as audio_route


class _FakeMediaAssetsCollection:
    def __init__(self, docs):
        self.docs = {doc["media_id"]: dict(doc) for doc in docs}
        self.inserted_docs = []

    async def find_one(self, query, *_args, **_kwargs):
        doc = self.docs.get(query.get("media_id"))
        if not doc:
            return None
        for key, value in query.items():
            if key == "$or":
                matched_or = False
                for branch in value:
                    if all(doc.get(k) == v for k, v in branch.items()):
                        matched_or = True
                        break
                if not matched_or:
                    return None
            elif doc.get(key) != value:
                return None
        return dict(doc)

    async def insert_one(self, doc):
        self.inserted_docs.append(dict(doc))
        self.docs[doc["media_id"]] = dict(doc)
        return SimpleNamespace(inserted_id=doc["media_id"])

    async def update_one(self, query, update, *_args, **_kwargs):
        doc = await self.find_one(query)
        if not doc:
            return SimpleNamespace(matched_count=0, modified_count=0)
        target = self.docs[doc["media_id"]]
        if "$set" in update:
            for k, v in update["$set"].items():
                target[k] = v
        if "$unset" in update:
            for k in update["$unset"]:
                target.pop(k, None)
        return SimpleNamespace(matched_count=1, modified_count=1)


class _FakeDB:
    def __init__(self, docs):
        self.media_assets = _FakeMediaAssetsCollection(docs)


def _payload(audio_media_id="audio-1"):
    return AudioRenderRequest.model_validate(
        {
            "mix": {
                "audio_media_id": audio_media_id,
                "trim_start_ms": 0,
                "video_offset_ms": 0,
                "mute_original": True,
            }
        }
    )


def _base_render_docs(video_overrides=None, audio_overrides=None):
    video_doc = {
        "media_id": "video-1",
        "user_id": "user-1",
        "status": "ready",
        "asset_kind": "video",
        "mime_type": "video/mp4",
        "storage_key": "media/user-1/video-1.mp4",
        "thumbnail_url": "https://cdn.example/thumb.webp",
        "duration_seconds": 12,
        "width": 1080,
        "height": 1920,
        "has_audio": True,
    }
    audio_doc = {
        "media_id": "audio-1",
        "user_id": "user-1",
        "status": "ready",
        "asset_kind": "audio",
        "mime_type": "audio/mpeg",
        "storage_key": "media/user-1/audio-1.mp3",
        "source_label": "Brand bed",
    }
    video_doc.update(video_overrides or {})
    audio_doc.update(audio_overrides or {})
    return [video_doc, audio_doc]


@pytest.mark.asyncio
async def test_render_video_audio_queues_placeholder_asset(monkeypatch):
    queued = []
    db = _FakeDB(_base_render_docs())
    monkeypatch.setattr(audio_route, "enqueue_task", lambda task_name, **kwargs: queued.append((task_name, kwargs)))

    response = await audio_route.render_video_audio(
        video_media_id="video-1",
        payload=_payload(),
        current_user={
            "user_id": "user-1",
            "default_workspace_id": "ws-1",
            "subscription_status": "active",
        },
        db=db,
    )

    assert response.status == "processing"
    assert response.render_job_id
    assert len(db.media_assets.inserted_docs) == 1
    inserted = db.media_assets.inserted_docs[0]
    assert inserted["status"] == "processing"
    assert inserted["asset_kind"] == "video"
    assert inserted["parent_media_id"] == "video-1"
    assert inserted["audio_mix"]["source_label"] == "Brand bed"
    assert queued[0][0] == "celery_workers.tasks.media.render_video_audio_mix"


@pytest.mark.asyncio
async def test_render_video_audio_rejects_non_audio_selection():
    db = _FakeDB(
        [
            {
                "media_id": "video-1",
                "user_id": "user-1",
                "status": "ready",
                "asset_kind": "video",
                "mime_type": "video/mp4",
                "storage_key": "media/user-1/video-1.mp4",
            },
            {
                "media_id": "image-1",
                "user_id": "user-1",
                "status": "ready",
                "asset_kind": "image",
                "mime_type": "image/png",
                "storage_key": "media/user-1/image-1.png",
            },
        ]
    )

    with pytest.raises(Exception) as excinfo:
        await audio_route.render_video_audio(
            video_media_id="video-1",
            payload=_payload("image-1"),
            current_user={
                "user_id": "user-1",
                "default_workspace_id": "ws-1",
                "subscription_status": "active",
            },
            db=db,
        )

    assert getattr(excinfo.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_render_video_audio_rejects_fully_silent_mix():
    db = _FakeDB(_base_render_docs())
    payload = AudioRenderRequest.model_validate(
        {
            "mix": {
                "audio_media_id": "audio-1",
                "selected_volume": 0,
                "original_volume": 0.5,
                "mute_original": True,
            }
        }
    )

    with pytest.raises(Exception) as excinfo:
        await audio_route.render_video_audio(
            video_media_id="video-1",
            payload=payload,
            current_user={
                "user_id": "user-1",
                "default_workspace_id": "ws-1",
                "subscription_status": "active",
            },
            db=db,
        )

    assert getattr(excinfo.value, "status_code", None) == 422
    assert "silent" in str(getattr(excinfo.value, "detail", "")).lower()


@pytest.mark.asyncio
async def test_render_video_audio_allows_zero_selected_when_original_is_audible(monkeypatch):
    queued = []
    db = _FakeDB(_base_render_docs())
    payload = AudioRenderRequest.model_validate(
        {
            "mix": {
                "audio_media_id": "audio-1",
                "selected_volume": 0,
                "original_volume": 0.4,
                "mute_original": False,
            }
        }
    )
    monkeypatch.setattr(audio_route, "enqueue_task", lambda task_name, **kwargs: queued.append((task_name, kwargs)))

    response = await audio_route.render_video_audio(
        video_media_id="video-1",
        payload=payload,
        current_user={
            "user_id": "user-1",
            "default_workspace_id": "ws-1",
            "subscription_status": "active",
        },
        db=db,
    )

    assert response.status == "processing"
    assert queued[0][1]["args"][-1]["selected_volume"] == 0
    assert queued[0][1]["args"][-1]["mute_original"] is False


@pytest.mark.asyncio
async def test_list_stock_audio_tracks():
    tracks = await audio_route.list_stock_audio_tracks(
        current_user={"user_id": "user-1"},
    )
    assert len(tracks) >= 6
    chill_tracks = await audio_route.list_stock_audio_tracks(
        current_user={"user_id": "user-1"},
        category="chill",
    )
    assert len(chill_tracks) >= 1
    assert all(t["category"] == "chill" for t in chill_tracks)


@pytest.mark.asyncio
async def test_render_video_with_stock_audio_track(monkeypatch):
    queued = []
    # DB only contains the video; audio is loaded from stock catalog
    db = _FakeDB([_base_render_docs()[0]])
    monkeypatch.setattr(audio_route, "enqueue_task", lambda task_name, **kwargs: queued.append((task_name, kwargs)))

    response = await audio_route.render_video_audio(
        video_media_id="video-1",
        payload=_payload("stock_lofi_chill"),
        current_user={
            "user_id": "user-1",
            "default_workspace_id": "ws-1",
            "subscription_status": "active",
        },
        db=db,
    )

    assert response.status == "processing"
    assert len(db.media_assets.inserted_docs) == 1
    inserted = db.media_assets.inserted_docs[0]
    assert inserted["audio_mix"]["audio_media_id"] == "stock_lofi_chill"
    assert "Lo-Fi Study Chill" in inserted["audio_mix"]["source_label"]


@pytest.mark.asyncio
async def test_persist_audio_asset():
    db = _FakeDB(
        [
            {
                "media_id": "temp-audio-1",
                "user_id": "user-1",
                "temporary": True,
                "purpose": "composer_audio_temp",
                "composer_session_id": "sess-123",
                "cleanup_after": "2026-09-20T10:00:00Z",
            }
        ]
    )

    result = await audio_route.persist_audio_asset(
        audio_id="temp-audio-1",
        current_user={"user_id": "user-1"},
        db=db,
    )

    assert result["status"] == "persisted"
    updated = db.media_assets.docs["temp-audio-1"]
    assert updated["temporary"] is False
    assert "purpose" not in updated
    assert "composer_session_id" not in updated

