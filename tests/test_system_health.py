import pytest
from unittest.mock import AsyncMock, MagicMock
from api.routes.system_health import get_scaling_alerts


@pytest.mark.asyncio
async def test_get_scaling_alerts_healthy():
    mock_db = MagicMock()
    mock_db.posts.count_documents = AsyncMock(return_value=0)

    mock_queue_redis = MagicMock()
    mock_queue_redis.llen = AsyncMock(return_value=2)

    mock_cache_redis = MagicMock()
    mock_cache_redis.info = AsyncMock(return_value={
        "used_memory": 50 * 1024 * 1024,
        "maxmemory": 512 * 1024 * 1024,
    })

    result = await get_scaling_alerts(
        db=mock_db,
        queue_redis=mock_queue_redis,
        cache_redis=mock_cache_redis,
    )

    assert result["status"] == "healthy"
    assert result["total_queued_tasks"] > 0
    assert result["redis_memory"]["used_percentage"] < 20.0
    assert "optimal" in result["recommendation"].lower()


@pytest.mark.asyncio
async def test_get_scaling_alerts_critical_queue_pressure():
    mock_db = MagicMock()
    mock_db.posts.count_documents = AsyncMock(return_value=15)

    mock_queue_redis = MagicMock()
    # Simulate high queue pressure on publish_light
    async def fake_llen(queue_name):
        if queue_name == "publish_light":
            return 150
        return 5
    mock_queue_redis.llen = AsyncMock(side_effect=fake_llen)

    mock_cache_redis = MagicMock()
    mock_cache_redis.info = AsyncMock(return_value={
        "used_memory": 480 * 1024 * 1024,
        "maxmemory": 512 * 1024 * 1024,
    })

    result = await get_scaling_alerts(
        db=mock_db,
        queue_redis=mock_queue_redis,
        cache_redis=mock_cache_redis,
    )

    assert result["status"] == "critical"
    assert result["queue_depths"]["publish_light"] == 150
    assert result["redis_memory"]["used_percentage"] > 85.0
    assert len(result["alerts"]) >= 2
