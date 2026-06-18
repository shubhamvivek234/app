import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from celery_workers.tasks import media as media_tasks
from media_pipeline import ffmpeg_worker


class _FakeMediaAssetsCollection:
    def __init__(self, asset_doc):
        self.asset_doc = dict(asset_doc)
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        if query.get("media_id") == self.asset_doc.get("media_id"):
            return dict(self.asset_doc)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if "$set" in update:
            self.asset_doc.update(update["$set"])
        if "$unset" in update:
            for key in update["$unset"].keys():
                self.asset_doc.pop(key, None)
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, asset_doc):
        self.media_assets = _FakeMediaAssetsCollection(asset_doc)


class _FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


class _FakeRedis:
    def __init__(self, seed=None):
        self.store = dict(seed or {})

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        return 1

    async def setex(self, key, _ttl, value):
        self.store[key] = value
        return True


class _FakeManyMediaAssetsCollection:
    def __init__(self, docs):
        self.docs = {doc["media_id"]: dict(doc) for doc in docs}
        self.inserted_docs = []
        self.update_calls = []

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

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        doc = self.docs.get(query.get("media_id"))
        if not doc:
            return SimpleNamespace(modified_count=0)
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for key in update["$unset"].keys():
                doc.pop(key, None)
        return SimpleNamespace(modified_count=1)


class _FakeManyDB:
    def __init__(self, docs):
        self.media_assets = _FakeManyMediaAssetsCollection(docs)


@pytest.mark.asyncio
async def test_process_media_uses_storage_copy_for_passthrough_r2(monkeypatch, tmp_path):
    os.environ["DB_NAME"] = "testdb"
    asset_doc = {
        "media_id": "media-1",
        "user_id": "user-1",
        "source_storage_key": "raw/user-1/media-1.jpg",
        "mime_type": "image/jpeg",
        "original_filename": "photo.jpg",
    }
    fake_db = _FakeDB(asset_doc)
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=0), max_retries=2)

    async def _fake_download(_reference, destination_path):
        Path(destination_path).write_bytes(b"raw-image-bytes")
        return destination_path

    monkeypatch.setattr(media_tasks, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    monkeypatch.setattr("media_pipeline.validation.validate_media", AsyncMock(return_value={"width": 1200, "height": 1200, "duration": None}))
    monkeypatch.setattr("media_pipeline.thumbnail.generate_thumbnail", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.storage.download_file_to_path_async", AsyncMock(side_effect=_fake_download))
    copy_mock = AsyncMock(return_value="https://cdn.example/media/user-1/media-1.jpg")
    monkeypatch.setattr("utils.storage.copy_storage_object_async", copy_mock)
    upload_from_path_mock = AsyncMock(return_value="https://cdn.example/should-not-upload")
    monkeypatch.setattr("utils.storage.upload_file_from_path_async", upload_from_path_mock)
    monkeypatch.setattr("utils.storage.upload_file_async", AsyncMock(return_value="https://cdn.example/thumb.webp"))
    delete_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("utils.storage.delete_file_async", delete_mock)

    result = await media_tasks._async_process_media(fake_task, "media-1", "user-1")

    assert result["status"] == "ready"
    copy_mock.assert_awaited_once_with(
        "raw/user-1/media-1.jpg",
        "media/user-1/media-1.jpg",
        content_type="image/jpeg",
    )
    upload_from_path_mock.assert_not_called()
    delete_mock.assert_awaited_once_with("raw/user-1/media-1.jpg")
    assert fake_db.media_assets.asset_doc["storage_key"] == "media/user-1/media-1.jpg"


def test_build_transcode_scale_filter_preserves_portrait_assets():
    assert (
        ffmpeg_worker._build_transcode_scale_filter(1080, 1920)
        == "scale=-2:min(1920\\,ih):flags=lanczos"
    )
    assert (
        ffmpeg_worker._build_transcode_scale_filter(3840, 2160)
        == "scale=min(1920\\,iw):-2:flags=lanczos"
    )


@pytest.mark.asyncio
async def test_process_video_transcodes_when_portrait_height_exceeds_limit(monkeypatch):
    run_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(ffmpeg_worker, "_run_process", run_mock)

    output_path = await ffmpeg_worker.process_video(
        "/tmp/input.mp4",
        {
            "codec": "h264",
            "width": 1080,
            "height": 2560,
        },
    )

    assert output_path.endswith(".mp4")
    run_mock.assert_awaited_once()


def test_build_audio_mix_command_mutes_original_and_offsets_selected_track():
    command = ffmpeg_worker.build_audio_mix_command(
        video_path="/tmp/video.mp4",
        audio_path="/tmp/audio.mp3",
        output_path="/tmp/out.mp4",
        video_duration_seconds=15,
        video_has_audio=True,
        mix={
            "trim_start_ms": 2000,
            "trim_end_ms": 7000,
            "video_offset_ms": 1500,
            "loop_to_video_end": True,
            "fade_in_ms": 500,
            "fade_out_ms": 500,
            "selected_volume": 0.8,
            "original_volume": 0,
            "mute_original": True,
            "normalize_audio": True,
        },
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "atrim=start=2.000:end=7.000" in filter_complex
    assert "adelay=1500|1500" in filter_complex
    assert "afade=t=in:st=0:d=0.500" in filter_complex
    assert "[0:a]" not in filter_complex
    assert command[-1] == "/tmp/out.mp4"


@pytest.mark.asyncio
async def test_process_media_audio_skips_thumbnail_and_marks_audio_ready(monkeypatch, tmp_path):
    os.environ["DB_NAME"] = "testdb"
    source = tmp_path / "track.mp3"
    source.write_bytes(b"audio")
    asset_doc = {
        "media_id": "audio-1",
        "user_id": "user-1",
        "quarantine_path": str(source),
        "mime_type": "audio/mpeg",
        "original_filename": "track.mp3",
    }
    fake_db = _FakeDB(asset_doc)
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=0), max_retries=2)

    monkeypatch.setattr(media_tasks, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    monkeypatch.setattr(
        "media_pipeline.validation.validate_media",
        AsyncMock(return_value={"duration": 12.5, "is_audio": True, "has_audio": True}),
    )
    thumbnail_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("media_pipeline.thumbnail.generate_thumbnail", thumbnail_mock)
    monkeypatch.setattr("utils.storage.copy_storage_object_async", AsyncMock(return_value="unused"))
    monkeypatch.setattr("utils.storage.upload_file_from_path_async", AsyncMock(return_value="https://cdn.example/media/user-1/audio-1.mp3"))
    monkeypatch.setattr("utils.storage.upload_file_async", AsyncMock(return_value="unused"))
    monkeypatch.setattr("utils.storage.delete_file_async", AsyncMock(return_value=None))

    result = await media_tasks._async_process_media(fake_task, "audio-1", "user-1")

    assert result["status"] == "ready"
    thumbnail_mock.assert_not_called()
    assert fake_db.media_assets.asset_doc["asset_kind"] == "audio"
    assert fake_db.media_assets.asset_doc["duration_seconds"] == 12.5
    assert fake_db.media_assets.asset_doc["thumbnail_url"] is None


@pytest.mark.asyncio
async def test_render_video_audio_mix_creates_ready_rendered_asset(monkeypatch, tmp_path):
    os.environ["DB_NAME"] = "testdb"
    docs = [
        {
            "media_id": "rendered-1",
            "user_id": "user-1",
            "status": "processing",
            "asset_kind": "video",
            "render_job_id": "render-1",
        },
        {
            "media_id": "video-1",
            "user_id": "user-1",
            "status": "ready",
            "asset_kind": "video",
            "mime_type": "video/mp4",
            "storage_key": "media/user-1/video-1.mp4",
        },
        {
            "media_id": "audio-1",
            "user_id": "user-1",
            "status": "ready",
            "asset_kind": "audio",
            "mime_type": "audio/mpeg",
            "storage_key": "media/user-1/audio-1.mp3",
        },
    ]
    fake_db = _FakeManyDB(docs)
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=1), max_retries=1)

    async def fake_download(_reference, destination_path):
        Path(destination_path).write_bytes(b"source")
        return destination_path

    async def fake_validate(path, claimed_mime=None):
        if str(path).endswith(".mp3"):
            return {"is_audio": True, "duration": 4.0, "has_audio": True}
        return {"is_video": True, "duration": 9.0, "width": 1080, "height": 1920, "has_audio": True}

    async def fake_render(*, output_path, **_kwargs):
        Path(output_path).write_bytes(b"rendered-video")
        return output_path

    monkeypatch.setattr(media_tasks, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    monkeypatch.setattr("utils.storage.download_file_to_path_async", AsyncMock(side_effect=fake_download))
    monkeypatch.setattr("media_pipeline.validation.validate_media", AsyncMock(side_effect=fake_validate))
    monkeypatch.setattr("media_pipeline.ffmpeg_worker.render_video_with_audio", AsyncMock(side_effect=fake_render))
    monkeypatch.setattr("utils.storage.upload_file_from_path_async", AsyncMock(return_value="https://cdn.example/media/user-1/rendered-1.mp4"))

    result = await media_tasks._async_render_video_audio_mix(
        fake_task,
        "render-1",
        "rendered-1",
        "video-1",
        "audio-1",
        "user-1",
        {"audio_media_id": "audio-1", "mute_original": True},
    )

    assert result["status"] == "ready"
    rendered_doc = fake_db.media_assets.docs["rendered-1"]
    assert rendered_doc["status"] == "ready"
    assert rendered_doc["media_url"] == "https://cdn.example/media/user-1/rendered-1.mp4"
    assert rendered_doc["asset_kind"] == "video"
    assert rendered_doc["has_audio"] is True


@pytest.mark.asyncio
async def test_import_remote_media_marks_failed_when_provider_fetch_breaks(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    asset_doc = {
        "media_id": "media-import-1",
        "user_id": "user-1",
        "source_provider": "dropbox",
        "source_download_url": "https://www.dropbox.com/s/example/file.jpg?dl=1",
        "source_auth_ref": "media_source_auth:1",
        "source_storage_key": "raw/user-1/media-import-1.jpg",
        "mime_type": "image/jpeg",
        "max_file_size_bytes": 1024,
        "original_filename": "file.jpg",
    }
    fake_db = _FakeDB(asset_doc)
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=1), max_retries=1)
    fake_redis = _FakeRedis({"media_source_auth:1": '{"type":"bearer","token":"abc"}'})

    monkeypatch.setattr(media_tasks, "get_client", AsyncMock(return_value=_FakeClient(fake_db)))
    monkeypatch.setattr("db.redis_client.get_cache_redis", lambda: fake_redis)
    monkeypatch.setattr("utils.media_source_imports.stream_remote_file_to_path", AsyncMock(side_effect=ValueError("blocked")))
    monkeypatch.setattr("api.routes.upload._release_concurrent_slot", AsyncMock(return_value=None))

    with pytest.raises(ValueError, match="blocked"):
        await media_tasks._async_import_remote_media(fake_task, "media-import-1", "user-1")

    assert fake_db.media_assets.asset_doc["status"] == "failed"
    assert fake_db.media_assets.asset_doc["source_stage"] == "failed"
    assert fake_db.media_assets.asset_doc["error_message"] == "blocked"
    assert "media_source_auth:1" not in fake_redis.store
