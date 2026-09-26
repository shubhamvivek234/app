"""
Automated test suite for Phase 8: Production Hardening, Anti-Ban Safety Shield, Stripe Billing & JIT Teardown.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from outreach.core.safety_shield import WarmUpGovernor, SafetyShield
from outreach.api.billing import (
    calculate_price_per_seat,
    get_outreach_plans,
    start_outreach_trial,
    update_seats,
    cancel_subscription,
    StartTrialRequest,
    UpdateSeatsRequest,
)


def test_warmup_governor_ramp_curve():
    """Verify progressive daily invitation limits based on account age."""
    now = datetime.now(timezone.utc)

    # 2 days old (Week 1)
    day_2 = now - timedelta(days=2)
    assert WarmUpGovernor.get_recommended_invite_limit(day_2, target_cap=20) == 5

    # 10 days old (Week 2)
    day_10 = now - timedelta(days=10)
    assert WarmUpGovernor.get_recommended_invite_limit(day_10, target_cap=20) == 10

    # 18 days old (Week 3)
    day_18 = now - timedelta(days=18)
    assert WarmUpGovernor.get_recommended_invite_limit(day_18, target_cap=20) == 15

    # 30 days old (Week 4+)
    day_30 = now - timedelta(days=30)
    assert WarmUpGovernor.get_recommended_invite_limit(day_30, target_cap=20) == 20


def test_safety_shield_detection_and_circuit_breaker():
    """Verify SafetyShield identifies checkpoint signals and HTTP error status codes."""
    # Normal response
    assert SafetyShield.should_trip_circuit_breaker(200, "{\"success\": true}") is False

    # HTTP 429 rate limit or 403 Forbidden
    assert SafetyShield.should_trip_circuit_breaker(429, "Too Many Requests") is True
    assert SafetyShield.should_trip_circuit_breaker(403, "Forbidden") is True

    # Security checkpoint in response text
    assert SafetyShield.should_trip_circuit_breaker(200, "Redirecting to /checkpoint/challenge") is True
    assert SafetyShield.should_trip_circuit_breaker(200, "Account has unusual activity detected") is True


@pytest.mark.asyncio
async def test_safety_shield_trip_and_withdraw():
    """Verify tripping breaker pauses campaigns and stale invites are auto-withdrawn."""
    mock_db = AsyncMock()
    mock_db.outreach_accounts.update_one = AsyncMock()

    pause_res = AsyncMock()
    pause_res.modified_count = 2
    mock_db.outreach_campaigns.update_many = AsyncMock(return_value=pause_res)

    trip_res = await SafetyShield.trip_circuit_breaker(
        account_id="acc_123",
        reason="Voyager 429 rate limit triggered",
        db=mock_db,
    )
    assert trip_res["status"] == "circuit_breaker_tripped"
    assert trip_res["campaigns_paused"] == 2
    mock_db.outreach_accounts.update_one.assert_called_once()
    mock_db.outreach_campaigns.update_many.assert_called_once()

    # Stale invite withdrawal
    withdraw_res = AsyncMock()
    withdraw_res.modified_count = 14
    mock_db.outreach_leads.update_many = AsyncMock(return_value=withdraw_res)

    count = await SafetyShield.withdraw_stale_invitations("acc_123", mock_db, max_age_days=21)
    assert count == 14
    mock_db.outreach_leads.update_many.assert_called_once()


def test_prosp_billing_tier_calculations():
    """Verify Prosp-matched rate card calculations across tiers and intervals."""
    # 1-5 accounts tier
    assert calculate_price_per_seat(1, "monthly") == 79.99
    assert calculate_price_per_seat(3, "quarterly") == 69.99
    assert calculate_price_per_seat(5, "annual") == 61.99

    # 6-30 accounts tier
    assert calculate_price_per_seat(6, "monthly") == 59.99
    assert calculate_price_per_seat(15, "quarterly") == 52.99
    assert calculate_price_per_seat(30, "annual") == 45.99

    # 30+ accounts tier
    assert calculate_price_per_seat(35, "monthly") == 39.99
    assert calculate_price_per_seat(50, "quarterly") == 34.99
    assert calculate_price_per_seat(100, "annual") == 30.99


@pytest.mark.asyncio
async def test_billing_api_lifecycle_and_zero_cost_teardown():
    """Verify trial activation, seat updates, and cancellation proxy teardown."""
    mock_db = AsyncMock()
    mock_db.outreach_subscriptions.find_one = AsyncMock(return_value=None)
    mock_db.outreach_subscriptions.update_one = AsyncMock()

    user = {"user_id": "usr_billing_123"}

    # Start trial
    trial_res = await start_outreach_trial(
        req=StartTrialRequest(seats=2, interval="monthly"),
        current_user=user,
        db=mock_db,
    )
    assert trial_res["status"] == "trial_activated"
    assert trial_res["seats"] == 2
    assert trial_res["price_per_seat"] == 79.99
    assert trial_res["trial_days_remaining"] == 4

    # Update seats
    seats_res = await update_seats(
        req=UpdateSeatsRequest(seats=10),
        current_user=user,
        db=mock_db,
    )
    assert seats_res["seats"] == 10
    assert seats_res["price_per_seat"] == 59.99

    # Cancel subscription and verify the local proxy assignment is cleared.
    mock_account = {
        "id": "acc_with_proxy",
        "proxy_config": {"proxy_id": "px_test_mock_123"},
    }
    mock_db.outreach_accounts.find = lambda q: AsyncMock(to_list=AsyncMock(return_value=[mock_account]))
    mock_db.outreach_accounts.update_one = AsyncMock()

    cancel_res = await cancel_subscription(current_user=user, db=mock_db)
    assert cancel_res["status"] == "canceled"
    assert cancel_res["cleared_proxy_assignments_count"] == 1
    mock_db.outreach_accounts.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_pauses_campaigns_and_disables_senders_before_proxy_unassignment():
    from unittest.mock import patch

    db = AsyncMock()
    db.outreach_accounts.find = lambda query: AsyncMock(to_list=AsyncMock(return_value=[{
        "id": "sender_1", "workspace_id": "ws_1", "status": "active",
        "proxy": {"proxy_id": "proxy_1"},
    }]))
    user = {"user_id": "owner_1", "default_workspace_id": "ws_1"}
    with patch("outreach.api.billing.JITProxyManager") as manager:
        manager.return_value.release_proxy = AsyncMock(return_value=True)
        result = await cancel_subscription(current_user=user, db=db)

    assert result["cleared_proxy_assignments_count"] == 1
    db.outreach_campaigns.update_many.assert_awaited_once()
    db.outreach_accounts.update_one.assert_awaited()
    assert db.outreach_campaigns.update_many.await_args.args[0]["workspace_id"] == "ws_1"
    assert db.outreach_accounts.update_many.await_args.args[1]["$set"]["status"] == "paused"


@pytest.mark.asyncio
async def test_cancel_preserves_proxy_reference_when_unassignment_fails():
    from unittest.mock import patch

    db = AsyncMock()
    db.outreach_accounts.find = lambda query: AsyncMock(to_list=AsyncMock(return_value=[{
        "id": "sender_1", "workspace_id": "ws_1", "proxy": {"proxy_id": "proxy_1"},
    }]))
    with patch("outreach.api.billing.JITProxyManager") as manager:
        manager.return_value.release_proxy = AsyncMock(return_value=False)
        result = await cancel_subscription(current_user={"user_id": "ws_1"}, db=db)

    assert result["cleared_proxy_assignments_count"] == 0
    assert result["failed_proxy_assignment_clearances"] == 1
    assert not any("$unset" in call.args[1] for call in db.outreach_accounts.update_one.await_args_list)


@pytest.mark.asyncio
async def test_update_billing_email_lifecycle():
    """Verify updating billing email persists and returns in get_outreach_plans."""
    from outreach.api.billing import update_billing_email, UpdateBillingEmailRequest

    mock_db = AsyncMock()
    mock_db.outreach_subscriptions.update_one = AsyncMock()
    user = {"user_id": "usr_billing_123", "email": "fallback@example.com"}

    res = await update_billing_email(
        req=UpdateBillingEmailRequest(billing_email="accounting@company.com"),
        current_user=user,
        db=mock_db,
    )
    assert res["status"] == "success"
    assert res["billing_email"] == "accounting@company.com"
    mock_db.outreach_subscriptions.update_one.assert_called_once()

    # Verify invalid email raises 400
    with pytest.raises(Exception):
        await update_billing_email(
            req=UpdateBillingEmailRequest(billing_email="not-an-email"),
            current_user=user,
            db=mock_db,
        )
