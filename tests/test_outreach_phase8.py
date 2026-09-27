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


def test_paid_pilot_has_one_honest_monthly_price():
    assert calculate_price_per_seat(1, "monthly") == 59.0
    assert calculate_price_per_seat(5, "monthly") == 59.0
    with pytest.raises(ValueError):
        calculate_price_per_seat(6, "monthly")
    with pytest.raises(ValueError):
        calculate_price_per_seat(1, "annual")


@pytest.mark.asyncio
async def test_customer_cannot_self_activate_trial_or_extra_seats():
    from fastapi import HTTPException
    db = AsyncMock()
    user = {"user_id": "owner-1", "default_workspace_id": "ws-1"}
    with pytest.raises(HTTPException) as trial:
        await start_outreach_trial(StartTrialRequest(), current_user=user, db=db)
    with pytest.raises(HTTPException) as seats:
        await update_seats(UpdateSeatsRequest(seats=2), current_user=user, db=db)
    assert trial.value.status_code == seats.value.status_code == 410
    db.outreach_entitlements.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_read_is_workspace_scoped_and_has_no_fake_checkout():
    db = AsyncMock()
    db.outreach_entitlements.find_one.return_value = None
    db.outreach_access_requests.find_one.return_value = None
    user = {"user_id": "owner-1", "default_workspace_id": "ws-1", "email": "owner@example.com"}
    result = await get_outreach_plans(current_user=user, db=db)
    assert result["price_usd_per_sender_month"] == 59
    assert result["trial_available"] is False
    assert result["checkout_available"] is False
    assert result["access_active"] is False
    db.outreach_entitlements.find_one.assert_awaited_with({"workspace_id": "ws-1"})


@pytest.mark.asyncio
async def test_cancel_schedules_paid_period_end_without_touching_sender_or_ip():
    db = AsyncMock()
    paid_through = datetime.now(timezone.utc) + timedelta(days=30)
    db.outreach_entitlements.find_one.return_value = {
        "workspace_id": "ws-1", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": paid_through,
    }
    result = await cancel_subscription(
        current_user={"user_id": "owner-1", "default_workspace_id": "ws-1"}, db=db,
    )
    assert result["status"] == "cancellation_scheduled"
    assert result["paid_through"] == paid_through.isoformat()
    db.outreach_accounts.update_many.assert_not_awaited()
    db.outreach_proxy_leases.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_billing_email_updates_entitlement_in_authenticated_workspace():
    from outreach.api.billing import update_billing_email, UpdateBillingEmailRequest
    db = AsyncMock()
    user = {"user_id": "owner-1", "default_workspace_id": "ws-1"}
    result = await update_billing_email(
        UpdateBillingEmailRequest(billing_email="Accounts@Company.com"), current_user=user, db=db,
    )
    assert result["billing_email"] == "accounts@company.com"
    assert db.outreach_entitlements.update_one.await_args.args[0] == {"workspace_id": "ws-1"}
