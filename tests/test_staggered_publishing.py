"""
Unit tests for Staggered Cross-Posting delays.
"""
import pytest
from datetime import datetime, timezone, timedelta
from api.models.post import CreatePostRequest, UpdatePostRequest, PostResponse, PostStatus


def test_staggered_post_models():
    # 1. Create with stagger
    req = CreatePostRequest(
        content="Cross-platform announcement",
        platforms=["twitter", "linkedin", "threads"],
        stagger_delay_minutes=15,
        stagger_order=["twitter", "linkedin", "threads"],
    )
    assert req.stagger_delay_minutes == 15
    assert req.stagger_order == ["twitter", "linkedin", "threads"]

    # 2. Update with stagger
    up = UpdatePostRequest(
        version=1,
        stagger_delay_minutes=30,
        stagger_order=["linkedin", "twitter"],
    )
    assert up.stagger_delay_minutes == 30
    assert up.stagger_order == ["linkedin", "twitter"]

    # 3. Post response serialization
    now = datetime.now(timezone.utc)
    res = PostResponse(
        id="post_stag_1",
        user_id="usr_1",
        content="Test content",
        platforms=["twitter", "linkedin"],
        status=PostStatus.SCHEDULED,
        stagger_delay_minutes=15,
        stagger_order=["twitter", "linkedin"],
        created_at=now,
        updated_at=now,
    )
    assert res.stagger_delay_minutes == 15
    assert res.stagger_order == ["twitter", "linkedin"]


def test_stagger_delay_calculations():
    # Emulate the dispatch calculation in publish.py
    targets = [
        {"platform": "twitter", "account_id": "acc_1"},
        {"platform": "linkedin", "account_id": "acc_2"},
        {"platform": "threads", "account_id": "acc_3"},
    ]
    stagger_delay_minutes = 20
    jitter = 5
    base_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    delays = []
    scheduled_times = []
    for idx, t in enumerate(targets):
        stagger_sec = idx * stagger_delay_minutes * 60
        target_countdown = jitter + stagger_sec
        target_scheduled_at = base_time + timedelta(seconds=target_countdown)
        delays.append(target_countdown)
        scheduled_times.append(target_scheduled_at)

    # First platform: 0 min stagger (only jitter = 5s)
    assert delays[0] == 5
    # Second platform: 20 min stagger (1200s + 5s = 1205s)
    assert delays[1] == 1205
    # Third platform: 40 min stagger (2400s + 5s = 2405s)
    assert delays[2] == 2405

    assert scheduled_times[1] - scheduled_times[0] == timedelta(minutes=20)
    assert scheduled_times[2] - scheduled_times[1] == timedelta(minutes=20)
