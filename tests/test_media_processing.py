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
