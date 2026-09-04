from datetime import datetime
from unittest.mock import AsyncMock, patch
import pytest
from zoneinfo import ZoneInfo

from platform_adapters.base import PlatformAPIError
from platform_adapters.youtube import YouTubeAdapter
from utils.youtube_quota_tracker import (
    COST_VIDEO_INSERT,
    COST_VIDEO_UPDATE,
    check_quota_available,
    get_pacific_date_and_reset_seconds,
    get_quota_status,
    record_quota_consumption,
)


def test_pacific_date_and_reset_seconds():
    date_str, resets_in = get_pacific_date_and_reset_seconds()
    assert len(date_str) == 10
    assert date_str.count("-") == 2
    assert resets_in > 0
    assert resets_in <= 86400


@pytest.mark.asyncio
async def test_check_quota_available_and_record():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"3200"  # 2 uploads consumed
    mock_redis.incrby.return_value = 4800

    with patch("utils.youtube_quota_tracker.DEFAULT_DAILY_QUOTA", 10000):
        is_avail, status = await check_quota_available(mock_redis, COST_VIDEO_INSERT)
        assert is_avail is True
        assert status["used"] == 3200
        assert status["remaining"] == 6800
        assert status["percent_used"] == 32.0

        updated = await record_quota_consumption(mock_redis, COST_VIDEO_INSERT)
        assert updated["used"] == 4800
        mock_redis.incrby.assert_called_once()
        mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_quota_exhausted_rejects():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"9600"  # 6 uploads consumed (10,000 limit)

    with patch("utils.youtube_quota_tracker.DEFAULT_DAILY_QUOTA", 10000):
        is_avail, status = await check_quota_available(mock_redis, COST_VIDEO_INSERT)
        assert is_avail is False
        assert status["remaining"] == 400  # not enough for 1600


@pytest.mark.asyncio
async def test_youtube_adapter_enforces_quota():
    mock_redis = AsyncMock()
    async def fake_get(key):
        if "yt:quota:usage" in str(key):
            return b"9600"
        return None

    mock_redis.get.side_effect = fake_get

    adapter = YouTubeAdapter()
    post = {
        "id": "post-123",
        "account": {"access_token": "enc-token"},
        "media_url": "https://r2.dev/video.mp4",
        "content": "Test video",
    }

    with patch("platform_adapters.youtube.can_attempt", AsyncMock(return_value=True)):
        with patch("platform_adapters.youtube.decrypt", return_value="plain-token"):
            with patch("utils.youtube_quota_tracker.DEFAULT_DAILY_QUOTA", 10000):
                with pytest.raises(PlatformAPIError) as exc_info:
                    await adapter.pre_upload(post, redis=mock_redis)

                assert "YouTube daily API quota limit reached" in str(exc_info.value)
                assert exc_info.value.code == 429
