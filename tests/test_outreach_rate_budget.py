import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from outreach.core.rate_budget import RateBudget


@pytest.fixture(autouse=True)
def reset_budget_memory():
    RateBudget.reset_memory()


@pytest.mark.asyncio
async def test_working_hours_before_start():
    # Sender in America/New_York working 09:00 - 17:00 Mon-Fri
    sender = {
        "working_timezone": "America/New_York",
        "working_hours_start": "09:00",
        "working_hours_end": "17:00",
        "working_days": [0, 1, 2, 3, 4],
        "status": "active",
        "min_interval_seconds": 30,
        "hourly_action_cap": 10,
        "daily_action_cap": 50,
    }

    # Simulate 07:30 AM New York time on a Wednesday
    tz = ZoneInfo("America/New_York")
    test_now = datetime(2026, 10, 7, 7, 30, 0, tzinfo=tz).astimezone(timezone.utc)

    allowed, wait_sec, reason = await RateBudget.acquire_token(
        sender_id="sender-1",
        sender_config=sender,
        now=test_now,
    )

    assert allowed is False
    assert reason == "before_working_hours"
    # Wait time should be 90 minutes (5400 seconds)
    assert 5300 <= wait_sec <= 5500


@pytest.mark.asyncio
async def test_working_hours_weekend():
    sender = {
        "working_timezone": "America/New_York",
        "working_hours_start": "09:00",
        "working_hours_end": "17:00",
        "working_days": [0, 1, 2, 3, 4],  # Mon-Fri
        "status": "active",
    }

    # Saturday at 11:00 AM
    tz = ZoneInfo("America/New_York")
    test_now = datetime(2026, 10, 10, 11, 0, 0, tzinfo=tz).astimezone(timezone.utc)

    allowed, wait_sec, reason = await RateBudget.acquire_token(
        sender_id="sender-1",
        sender_config=sender,
        now=test_now,
    )

    assert allowed is False
    assert reason == "outside_working_days"
    # Should wait until Monday 09:00 AM (approx 46 hours = ~165,600s)
    assert wait_sec > 86400


@pytest.mark.asyncio
async def test_minimum_interval_cooldown():
    sender = {
        "working_timezone": "UTC",
        "working_hours_start": "09:00",
        "working_hours_end": "17:00",
        "working_days": [0, 1, 2, 3, 4],
        "status": "active",
        "min_interval_seconds": 60,
        "hourly_action_cap": 10,
        "daily_action_cap": 50,
    }

    # Wednesday at 10:00:00 AM UTC
    t0 = datetime(2026, 10, 7, 10, 0, 0, tzinfo=timezone.utc)

    # First request: should succeed
    allowed, wait_sec, reason = await RateBudget.acquire_token("sender-2", sender, now=t0)
    assert allowed is True
    assert wait_sec == 0
    assert reason == "ok"

    # Second request 15 seconds later: should be in cooldown
    t1 = t0 + timedelta(seconds=15)
    allowed, wait_sec, reason = await RateBudget.acquire_token("sender-2", sender, now=t1)
    assert allowed is False
    assert reason == "min_interval_cooldown"
    assert 40 <= wait_sec <= 46

    # Third request 65 seconds after t0: should succeed
    t2 = t0 + timedelta(seconds=65)
    allowed, wait_sec, reason = await RateBudget.acquire_token("sender-2", sender, now=t2)
    assert allowed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_hourly_cap_exhaustion():
    sender = {
        "working_timezone": "UTC",
        "working_hours_start": "09:00",
        "working_hours_end": "17:00",
        "working_days": [0, 1, 2, 3, 4],
        "status": "active",
        "min_interval_seconds": 1,
        "hourly_action_cap": 3,
        "daily_action_cap": 50,
    }

    t0 = datetime(2026, 10, 7, 10, 15, 0, tzinfo=timezone.utc)

    # Acquire 3 tokens
    for i in range(3):
        t_req = t0 + timedelta(seconds=i * 2)
        allowed, _, _ = await RateBudget.acquire_token("sender-3", sender, now=t_req)
        assert allowed is True

    # 4th token in same hour: should fail with hourly_cap_reached
    t_over = t0 + timedelta(seconds=10)
    allowed, wait_sec, reason = await RateBudget.acquire_token("sender-3", sender, now=t_over)
    assert allowed is False
    assert reason == "hourly_cap_reached"
    # Should wait until 11:00 (approx 45 minutes = ~2700s)
    assert 2600 <= wait_sec <= 2800


@pytest.mark.asyncio
async def test_circuit_breaker_active():
    sender = {
        "status": "checkpoint_detected",
        "stop_reason": "rate_limited_429",
    }
    allowed, wait_sec, reason = await RateBudget.acquire_token("sender-4", sender)
    assert allowed is False
    assert "sender_stopped" in reason
