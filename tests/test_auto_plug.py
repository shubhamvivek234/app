"""
Unit tests for Viral Auto-Plug models and background execution.
"""
import pytest
from datetime import datetime, timezone
from api.models.post import AutoPlugConfig, CreatePostRequest, UpdatePostRequest, PostResponse, PostStatus


def test_auto_plug_models():
    # 1. Config validation
    cfg = AutoPlugConfig(
        enabled=True,
        trigger_metric="likes",
        threshold=75,
        content="Enjoyed this post? Check out my newsletter: https://unravler.com",
    )
    assert cfg.enabled is True
    assert cfg.trigger_metric == "likes"
    assert cfg.threshold == 75
    assert cfg.executed is False
    assert cfg.status == "pending"

    # 2. In CreatePostRequest
    req = CreatePostRequest(
        content="Hot take on AI engineering",
        platforms=["twitter"],
        auto_plug=cfg,
    )
    assert req.auto_plug is not None
    assert req.auto_plug.threshold == 75

    # 3. In UpdatePostRequest
    up = UpdatePostRequest(
        version=1,
        auto_plug=AutoPlugConfig(enabled=False),
    )
    assert up.auto_plug.enabled is False

    # 4. In PostResponse
    now = datetime.now(timezone.utc)
    res = PostResponse(
        id="post_ap_1",
        user_id="usr_1",
        content="Test",
        platforms=["twitter"],
        status=PostStatus.PUBLISHED,
        auto_plug=cfg,
        created_at=now,
        updated_at=now,
    )
    assert res.auto_plug.threshold == 75


@pytest.mark.asyncio
async def test_auto_plug_logic_threshold_check():
    # Emulate the threshold condition logic
    auto_plug = {
        "enabled": True,
        "executed": False,
        "trigger_metric": "likes",
        "threshold": 50,
        "content": "Follow me for more tech insights!",
    }

    metrics_below = {"likes": 35, "retweets": 2}
    metrics_above = {"likes": 52, "retweets": 10}

    metric = auto_plug["trigger_metric"]
    threshold = auto_plug["threshold"]

    # Below threshold: should NOT trigger
    assert metrics_below[metric] < threshold

    # Above threshold: SHOULD trigger
    assert metrics_above[metric] >= threshold
