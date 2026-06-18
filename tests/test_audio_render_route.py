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
            if doc.get(key) != value:
                return None
        return dict(doc)

    async def insert_one(self, doc):
        self.inserted_docs.append(dict(doc))
        self.docs[doc["media_id"]] = dict(doc)
        return SimpleNamespace(inserted_id=doc["media_id"])


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


@pytest.mark.asyncio
async def test_render_video_audio_queues_placeholder_asset(monkeypatch):
    queued = []
    db = _FakeDB(
        [
            {
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
            },
            {
                "media_id": "audio-1",
                "user_id": "user-1",
                "status": "ready",
                "asset_kind": "audio",
                "mime_type": "audio/mpeg",
                "storage_key": "media/user-1/audio-1.mp3",
                "source_label": "Brand bed",
            },
        ]
    )
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
