import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from media_pipeline.platform_specs import (
    PLATFORM_SPECS,
    get_platform_spec,
    is_vertical_required,
    get_recommended_aspect_ratio,
    get_max_media_size,
)
from media_pipeline.image_worker import auto_fit_image_vertical, auto_compress_image
from media_pipeline import ffmpeg_worker


def test_platform_specs_coverage():
    platforms = ["instagram", "facebook", "twitter", "linkedin", "tiktok", "youtube", "threads", "pinterest", "bluesky", "google_business"]
    for p in platforms:
        spec = get_platform_spec(p)
        assert spec is not None
        assert "max_image_bytes" in spec
        assert "max_video_bytes" in spec
        assert "max_duration_seconds" in spec

    assert is_vertical_required("tiktok") is True
    assert is_vertical_required("instagram", "Reel") is True
    assert is_vertical_required("instagram", "Story") is True
    assert is_vertical_required("youtube", "Shorts") is True
    assert is_vertical_required("twitter") is False
    assert is_vertical_required("linkedin") is False

    assert get_recommended_aspect_ratio("tiktok") == (9, 16)
    assert get_recommended_aspect_ratio("instagram", "Reel") == (9, 16)
    assert get_recommended_aspect_ratio("instagram", "Post") == (4, 5)

    assert get_max_media_size("twitter", "image") == 5 * 1024 * 1024
    assert get_max_media_size("twitter", "video") == 512 * 1024 * 1024
    assert get_max_media_size("instagram", "video") == 4 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_auto_fit_image_blur_pad(tmp_path):
    # Create 16:9 landscape image
    src = str(tmp_path / "landscape.jpg")
    out = str(tmp_path / "fitted_blur.jpg")
    img = Image.new("RGB", (1280, 720), color=(200, 50, 50))
    img.save(src, "JPEG")

    result = await auto_fit_image_vertical(src, out, mode="blur_pad", target_w=1080, target_h=1920)
    assert os.path.exists(result)

    with Image.open(result) as out_img:
        assert out_img.size == (1080, 1920)


@pytest.mark.asyncio
async def test_auto_fit_image_center_crop(tmp_path):
    # Create 16:9 landscape image
    src = str(tmp_path / "landscape2.jpg")
    out = str(tmp_path / "fitted_crop.jpg")
    img = Image.new("RGB", (1280, 720), color=(50, 120, 200))
    img.save(src, "JPEG")

    result = await auto_fit_image_vertical(src, out, mode="center_crop", target_w=1080, target_h=1920)
    assert os.path.exists(result)

    with Image.open(result) as out_img:
        assert out_img.size == (1080, 1920)


@pytest.mark.asyncio
async def test_auto_compress_image(tmp_path):
    src = str(tmp_path / "large.jpg")
    out = str(tmp_path / "compressed.jpg")
    # Generate noisy image to ensure non-trivial file size
    import random
    data = bytes([random.randint(0, 255) for _ in range(600 * 600 * 3)])
    img = Image.frombytes("RGB", (600, 600), data)
    img.save(src, "JPEG", quality=95)

    original_size = os.path.getsize(src)
    target_bytes = original_size // 2

    result = await auto_compress_image(src, out, target_max_bytes=target_bytes)
    assert os.path.exists(result)
    assert os.path.getsize(result) <= target_bytes


@pytest.mark.asyncio
async def test_auto_fit_video_invokes_ffmpeg(monkeypatch, tmp_path):
    mock_run = AsyncMock()
    monkeypatch.setattr(ffmpeg_worker, "_run_process", mock_run)
    monkeypatch.setattr(ffmpeg_worker, "_probe_has_audio", AsyncMock(return_value=True))

    input_path = str(tmp_path / "in.mp4")
    output_path = str(tmp_path / "out.mp4")
    Path(input_path).touch()

    res = await ffmpeg_worker.auto_fit_video_vertical(input_path, output_path, mode="blur_pad")
    assert res == output_path
    assert mock_run.call_count == 1
    call_args = mock_run.call_args[0][0]
    assert "ffmpeg" in call_args
    assert "-filter_complex" in call_args
    assert "boxblur=20:5" in ";".join(call_args)


@pytest.mark.asyncio
async def test_auto_compress_video_calculates_bitrate(monkeypatch, tmp_path):
    mock_run = AsyncMock()
    monkeypatch.setattr(ffmpeg_worker, "_run_process", mock_run)
    monkeypatch.setattr(ffmpeg_worker, "_probe_has_audio", AsyncMock(return_value=True))
    monkeypatch.setattr(ffmpeg_worker, "_probe_duration", AsyncMock(return_value=10.0))

    input_path = str(tmp_path / "in.mp4")
    output_path = str(tmp_path / "compressed.mp4")
    Path(input_path).touch()

    target_bytes = 5 * 1024 * 1024  # 5 MB
    res = await ffmpeg_worker.auto_compress_video(input_path, output_path, target_max_bytes=target_bytes, duration_sec=10.0)
    assert res == output_path
    assert mock_run.call_count == 1
    call_args = mock_run.call_args[0][0]
    assert "-b:v" in call_args
    idx = call_args.index("-b:v")
    bitrate = int(call_args[idx + 1])
    # Bitrate should be positive and bounded
    assert bitrate > 200_000


@pytest.mark.asyncio
async def test_auto_fit_vertical_route(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from api.routes.upload import auto_fit_vertical
    from api.models.media import MediaAutoFitRequest

    class _FakeMediaDocAssets:
        def __init__(self, doc):
            self.doc = dict(doc)

        async def find_one(self, query, projection=None):
            if query.get("media_id") == self.doc.get("media_id"):
                return dict(self.doc)
            return None

        async def update_one(self, query, update):
            if "$set" in update:
                self.doc.update(update["$set"])
            return SimpleNamespace(modified_count=1)

    class _FakeUploadDB:
        def __init__(self, doc):
            self.media_assets = _FakeMediaDocAssets(doc)

    fake_doc = {
        "media_id": "job-123",
        "user_id": "user-456",
        "mime_type": "image/jpeg",
        "asset_kind": "image",
        "url": "https://pub.r2.dev/uploads/test.jpg",
        "storage_key": "uploads/test.jpg",
        "status": "ready",
        "file_size_bytes": 1000,
        "created_at": datetime.now(timezone.utc),
    }
    db = _FakeUploadDB(fake_doc)
    current_user = {"user_id": "user-456", "plan": "pro"}

    # Mock local resolution and upload
    sample_file = str(tmp_path / "sample.jpg")
    img = Image.new("RGB", (800, 600), color=(10, 20, 30))
    img.save(sample_file, "JPEG")

    monkeypatch.setattr("api.routes.upload._resolve_media_local_file", AsyncMock(return_value=(sample_file, False)))
    monkeypatch.setattr("utils.storage.upload_file_from_path_async", AsyncMock(return_value="https://pub.r2.dev/media/user-456/job-123_v.jpg"))

    resp = await auto_fit_vertical(
        media_job_id="job-123",
        payload=MediaAutoFitRequest(mode="blur_pad"),
        current_user=current_user,
        db=db,
    )
    assert resp.media_id == "job-123"
    assert resp.width == 1080
    assert resp.height == 1920
    assert resp.media_url == "https://pub.r2.dev/media/user-456/job-123_v.jpg"

