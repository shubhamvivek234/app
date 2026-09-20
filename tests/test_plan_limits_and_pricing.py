"""
Unit tests for plan limits, Twitter rate limits, and pricing structures.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from utils.plan_limits import has_link, get_plan_limits, check_twitter_post_limits, PLAN_LIMITS
from api.routes.payments import _PRICING


def test_has_link_detection():
    assert has_link("Check out this blog post: https://unravler.com/blog") is True
    assert has_link("Visit www.github.com/socialentangler for updates") is True
    assert has_link("Just a regular tweet about marketing and growth without any links.") is False
    assert has_link("") is False
    assert has_link(None) is False


def test_plan_limits_structure():
    starter = get_plan_limits("starter")
    assert starter["accounts"] == 6
    assert starter["twitter_total"] == 60
    assert starter["twitter_links"] == 15
    assert starter["twitter_daily"] == 5
    assert starter["clipping_minutes"] == 30

    pro = get_plan_limits("pro")
    assert pro["accounts"] == 18
    assert pro["twitter_total"] == 180
    assert pro["twitter_links"] == 40
    assert pro["twitter_daily"] == 12
    assert pro["clipping_minutes"] == 120

    agency = get_plan_limits("agency")
    assert agency["accounts"] == 50
    assert agency["twitter_total"] == 500
    assert agency["twitter_links"] == 120
    assert agency["twitter_daily"] == 30
    assert agency["clipping_minutes"] == 400

    # Aliases
    assert get_plan_limits("creator")["accounts"] == 18
    assert get_plan_limits("business")["accounts"] == 50
    assert get_plan_limits("unknown_plan")["accounts"] == 6


def test_pricing_dictionary():
    assert _PRICING["starter"]["amount"] == 19
    assert _PRICING["starter_annual"]["amount"] == 192
    assert _PRICING["pro"]["amount"] == 45
    assert _PRICING["pro_annual"]["amount"] == 468
    assert _PRICING["agency"]["amount"] == 110
    assert _PRICING["agency_annual"]["amount"] == 1188
    assert _PRICING["twitter_link_booster"]["amount"] == 15
    assert _PRICING["twitter_byok"]["amount"] == 5


@pytest.mark.asyncio
async def test_twitter_daily_limit_exceeded():
    db = MagicMock()
    # Daily count is 5 for starter plan (max is 5)
    db.posts.count_documents = AsyncMock(return_value=5)

    with pytest.raises(HTTPException) as exc_info:
        await check_twitter_post_limits(
            db=db,
            user_id="user_123",
            plan="starter",
            content="Normal tweet without links",
            byok_enabled=False,
        )
    assert exc_info.value.status_code == 429
    assert "Daily Twitter/X post limit reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_twitter_monthly_total_limit_exceeded():
    db = MagicMock()
    # First call for daily is 1 (allowed), second call for monthly total is 60 (limit reached)
    db.posts.count_documents = AsyncMock(side_effect=[1, 60])

    with pytest.raises(HTTPException) as exc_info:
        await check_twitter_post_limits(
            db=db,
            user_id="user_123",
            plan="starter",
            content="Another regular tweet",
            byok_enabled=False,
        )
    assert exc_info.value.status_code == 429
    assert "Monthly Twitter/X limit reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_twitter_link_limit_exceeded():
    db = MagicMock()
    # 1. daily count: 1
    # 2. monthly total: 20
    # 3. monthly link count: 15 (max is 15 for starter)
    db.posts.count_documents = AsyncMock(side_effect=[1, 20, 15])
    db.users.find_one = AsyncMock(return_value={"extra_twitter_links": 0})

    with pytest.raises(HTTPException) as exc_info:
        await check_twitter_post_limits(
            db=db,
            user_id="user_123",
            plan="starter",
            content="Check out this awesome tool: https://unravler.com",
            byok_enabled=False,
        )
    assert exc_info.value.status_code == 429
    assert "Monthly Twitter/X link post limit reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_twitter_byok_bypasses_limits():
    db = MagicMock()
    # Should not even call count_documents
    db.posts.count_documents = AsyncMock()

    # Even with high usage, byok_enabled=True passes with no exception
    await check_twitter_post_limits(
        db=db,
        user_id="user_123",
        plan="starter",
        content="Tweet with link: https://unravler.com",
        byok_enabled=True,
    )
    db.posts.count_documents.assert_not_called()
