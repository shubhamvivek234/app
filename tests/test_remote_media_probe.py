import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from media_pipeline.validation import (
    _detect_mime_from_buffer,
    probe_remote_media_stream,
    validate_remote_media,
)
from utils.storage import read_storage_byte_range, read_storage_byte_range_async


def test_detect_mime_from_buffer_mp4():
    # Standard MP4 ftyp box
    fake_header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    assert _detect_mime_from_buffer(fake_header) == "video/mp4"


def test_detect_mime_from_buffer_jpeg():
    fake_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01"
    assert _detect_mime_from_buffer(fake_header) == "image/jpeg"


def test_detect_mime_from_buffer_png():
    fake_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert _detect_mime_from_buffer(fake_header) == "image/png"


def test_detect_mime_from_buffer_webp():
    fake_header = b"RIFF\x00\x10\x00\x00WEBPVP8 "
    assert _detect_mime_from_buffer(fake_header) == "image/webp"


@pytest.mark.asyncio
async def test_probe_remote_media_stream_success():
    fake_probe_output = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "color_transfer": "bt709",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
        ],
        "format": {
            "duration": "120.5",
        },
    }

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b'{"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920}], "format": {"duration": "120.5"}}', b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        res = await probe_remote_media_stream("https://pub-r2.dev/video.mp4")
        assert "streams" in res
        assert res["streams"][0]["codec_name"] == "h264"


@pytest.mark.asyncio
async def test_validate_remote_media_fast_path_attributes():
    fake_probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "color_transfer": "bt709",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
        ],
        "format": {
            "duration": "60.0",
        },
    }

    with patch("media_pipeline.validation.probe_remote_media_stream", AsyncMock(return_value=fake_probe)):
        header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
        res = await validate_remote_media(
            url="https://signed-url.r2.cloudflarestorage.com/video.mp4",
            claimed_mime="video/mp4",
            file_size_bytes=15 * 1024 * 1024 * 1024,
            header_bytes=header,
        )

        assert res["is_video"] is True
        assert res["codec"] == "h264"
        assert res["width"] == 1080
        assert res["height"] == 1920
        assert res["duration"] == 60.0
        assert res["has_audio"] is True
        assert res["needs_hdr_conversion"] is False
        assert res["is_animated_gif"] is False


@pytest.mark.asyncio
async def test_read_storage_byte_range_r2():
    with patch("utils.storage._STORAGE_BACKEND", "r2"):
        with patch("utils.storage._r2_read_byte_range", return_value=b"test-bytes") as mock_read:
            result = await read_storage_byte_range_async("uploads/raw.mp4", 0, 16384)
            assert result == b"test-bytes"
            mock_read.assert_called_once_with("uploads/raw.mp4", 0, 16384)
