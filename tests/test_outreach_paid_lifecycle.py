"""Paid pilot lifecycle: no self-issued access, sticky sender leases, fail closed."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from outreach.api import billing
from outreach.api.campaigns import UpdateCampaignRequest, update_campaign
from outreach.core import paid_access


NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
USER = {"user_id": "owner-1", "default_workspace_id": "workspace-1", "email": "owner@example.com"}


def entitlement(*, paid_through=None, status="active", seats=1, cancel=False):
    return {
        "workspace_id": "workspace-1", "status": status, "seats": seats,
        "paid_through": paid_through or NOW + timedelta(days=30),
        "cancel_at_period_end": cancel,
        "payment_source": "manual_verified_invoice",
    }


@pytest.mark.asyncio
async def test_paid_access_requires_verified_unexpired_entitlement():
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value=None)
    assert await paid_access.get_active_entitlement(db, "workspace-1", NOW) is None
    db.outreach_entitlements.find_one.return_value = entitlement()
    assert (await paid_access.get_active_entitlement(db, "workspace-1", NOW))["seats"] == 1
    db.outreach_entitlements.find_one.return_value = entitlement(cancel=True)
    assert await paid_access.get_active_entitlement(db, "workspace-1", NOW)
    db.outreach_entitlements.find_one.return_value = entitlement(paid_through=NOW)
    assert await paid_access.get_active_entitlement(db, "workspace-1", NOW) is None
    db.outreach_entitlements.find_one.return_value = entitlement(status="pending")
    assert await paid_access.get_active_entitlement(db, "workspace-1", NOW) is None


@pytest.mark.asyncio
async def test_unpaid_owner_can_edit_draft_but_not_launch():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign-1", "workspace_id": "workspace-1", "status": "draft", "name": "Original",
    })
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value=None)
    updated = await update_campaign(
        "campaign-1", UpdateCampaignRequest(name="Revised"), current_user=USER, db=db,
    )
    assert updated["id"] == "campaign-1"
    db.outreach_campaigns.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_trial_and_self_service_seat_changes_are_retired():
    db = MagicMock()
    for action, request in (
        (billing.start_outreach_trial, billing.StartTrialRequest()),
        (billing.update_seats, billing.UpdateSeatsRequest(seats=2)),
    ):
        with pytest.raises(HTTPException) as error:
            await action(request, current_user=USER, db=db)
        assert error.value.status_code == 410
    db.outreach_entitlements.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_schedules_end_of_paid_period_without_clearing_proxy():
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value=entitlement())
    db.outreach_entitlements.update_one = AsyncMock()
    result = await billing.cancel_subscription(current_user=USER, db=db)
    assert result["status"] == "cancellation_scheduled"
    assert result["paid_through"] == entitlement()["paid_through"].isoformat()
    db.outreach_accounts.update_many.assert_not_called()
    db.outreach_proxy_leases.delete_one.assert_not_called()
    assert db.outreach_entitlements.update_one.await_args.args[0]["workspace_id"] == "workspace-1"


@pytest.mark.asyncio
async def test_manual_payment_records_unique_invoice_and_clears_pending_cancel():
    db = MagicMock()
    db.outreach_payment_receipts.insert_one = AsyncMock()
    db.outreach_entitlements.update_one = AsyncMock()
    db.outreach_access_requests.update_one = AsyncMock()
    db.outreach_access_requests.find_one = AsyncMock(return_value={"country_code": "IN", "seats": 1})
    db.outreach_proxy_inventory.count_documents = AsyncMock(return_value=1)
    db.outreach_sender_slots.count_documents = AsyncMock(return_value=0)
    result = await paid_access.record_verified_payment(
        db, "workspace-1", "invoice-123", "operator@example.com", 1,
        NOW + timedelta(days=30), now=NOW,
    )
    assert result["status"] == "active"
    assert result["price_usd_per_sender_month"] == 59
    assert db.outreach_payment_receipts.insert_one.await_args.args[0]["_id"] == "invoice-123"
    updates = db.outreach_entitlements.update_one.await_args.args[1]["$set"]
    assert updates["cancel_at_period_end"] is False
    assert updates["payment_source"] == "manual_verified_invoice"
    assert db.outreach_proxy_inventory.count_documents.await_args.args[0]["country_code"] == "IN"


@pytest.mark.asyncio
async def test_payment_rejects_missing_request_country():
    db = MagicMock()
    db.outreach_access_requests.find_one = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="country"):
        await paid_access.record_verified_payment(
            db, "workspace-1", "invoice-123", "operator@example.com", 1,
            NOW + timedelta(days=30), now=NOW,
        )
    db.outreach_payment_receipts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_expiry_pauses_actions_but_keeps_paid_proxy_lease():
    db = MagicMock()
    db.outreach_entitlements.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[entitlement(paid_through=NOW)])))
    db.outreach_entitlements.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_campaigns.update_many = AsyncMock()
    db.outreach_accounts.update_many = AsyncMock()
    db.outreach_tasks.update_many = AsyncMock()
    db.outreach_connection_jobs.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[{
        "id": "job-1", "workspace_id": "workspace-1", "sender_id": "sender-1",
        "proxy_id": "iproyal:one", "new_proxy_reservation": True, "created_slot": True,
    }])))
    db.outreach_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_proxy_leases.delete_one = AsyncMock()
    db.outreach_sender_slots.delete_one = AsyncMock()
    db.outreach_connection_locks.delete_one = AsyncMock()
    count = await paid_access.expire_due_entitlements(db, now=NOW)
    assert count == 1
    assert db.outreach_accounts.update_many.await_args.args[1]["$unset"]["session_cookie_enc"] == ""
    assert db.outreach_accounts.update_many.await_args.args[0] == {"workspace_id": "workspace-1"}
    assert db.outreach_connection_jobs.update_one.await_args.args[1]["$unset"]["li_at_enc"] == ""
    db.outreach_proxy_leases.delete_one.assert_awaited_once()
    assert db.outreach_proxy_leases.delete_one.await_args.args[0]["_id"] == "iproyal:one"
    db.outreach_sender_slots.delete_one.assert_awaited_once()
    db.outreach_connection_locks.delete_one.assert_awaited_once()
    db.outreach_proxy_inventory.update_one.assert_not_called()
