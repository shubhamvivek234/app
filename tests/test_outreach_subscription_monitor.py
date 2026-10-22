"""Tests for Outreach Subscription, Active Users, Expiry & Voice Quota Monitor."""
from datetime import datetime, timedelta, timezone

import pytest

from outreach.api import billing
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_workspace_subscription_monitor_returns_live_telemetry_and_enforces_tenant_isolation():
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()
    paid_through = (now + timedelta(days=5)).isoformat()

    db = Database(
        workspaces=[
            {"workspace_id": "ws-alpha", "name": "Alpha Growth", "owner_id": "u-alpha"},
            {"workspace_id": "ws-beta", "name": "Beta Corp", "owner_id": "u-beta"},
        ],
        workspace_members=[
            {"workspace_id": "ws-alpha", "user_id": "u-alpha", "role": "owner", "updated_at": now.isoformat()},
        ],
        users=[
            {
                "user_id": "u-alpha",
                "email": "founder@alphagrowth.io",
                "display_name": "Alpha Founder",
                "last_login_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "user_id": "u-beta",
                "email": "ceo@betacorp.io",
                "display_name": "Beta CEO",
                "last_login_at": (now - timedelta(days=3)).isoformat(),
            },
        ],
        outreach_entitlements=[
            {
                "workspace_id": "ws-alpha",
                "status": "active",
                "seats": 2,
                "paid_through": paid_through,
                "payment_source": "manual_verified_invoice",
                "price_usd_per_sender_month": 59,
                "billing_email": "billing@alphagrowth.io",
                "cancel_at_period_end": False,
            },
            {
                "workspace_id": "ws-beta",
                "status": "active",
                "seats": 3,
                "paid_through": (now + timedelta(days=25)).isoformat(),
                "payment_source": "manual_verified_invoice",
                "price_usd_per_sender_month": 59,
            },
        ],
        outreach_accounts=[
            {
                "id": "acc-1",
                "workspace_id": "ws-alpha",
                "account_name": "Alex Rivera",
                "status": "active",
                "premium_product": "sales_navigator",
                "activity_control_enabled": True,
                "proxy": {"country_code": "US", "status": "healthy"},
                "limits": {"voice_notes": 20, "connection_invites": 25, "messages": 40},
                "counters": {"date": today_iso, "voice_notes": 6, "connection_invites": 10, "messages": 14},
            }
        ],
        outreach_campaigns=[
            {"id": "camp-1", "workspace_id": "ws-alpha", "status": "active"},
        ],
        outreach_voice_preparation_budgets=[
            {"_id": f"ws-alpha:{today_iso}", "workspace_id": "ws-alpha", "day": today_iso, "clips": 6, "chars": 2450},
        ],
        outreach_voices=[
            {"id": "v-1", "workspace_id": "ws-alpha", "name": "Alex Clone", "status": "active"},
        ],
    )

    ordinary_user = {
        "user_id": "u-alpha",
        "email": "founder@alphagrowth.io",
        "display_name": "Alpha Founder",
        "default_workspace_id": "ws-alpha",
        "role": "",
    }

    res = await billing.get_subscription_monitor(current_user=ordinary_user, db=db)

    assert res["is_platform_operator"] is False
    assert res["platform_overview"] is None

    ws = res["workspace"]
    assert ws["workspace_id"] == "ws-alpha"
    assert ws["workspace_name"] == "Alpha Growth"
    assert ws["access_active"] is True
    assert ws["lifecycle_state"] == "expiring_soon"
    assert ws["expiring_soon"] is True
    assert ws["seats_granted"] == 2
    assert ws["seats_used"] == 1
    assert ws["seats_remaining"] == 1
    assert ws["monthly_recurring_usd"] == 118
    assert ws["days_remaining"] in (5, 6)
    assert ws["active_members_24h"] == 1
    assert ws["voice_usage"]["today_clips_used"] == 6
    assert ws["voice_usage"]["today_chars_used"] == 2450
    assert ws["voice_usage"]["voices_cloned_count"] == 1
    assert len(ws["senders"]) == 1
    assert ws["senders"][0]["daily_voice_notes_used"] == 6
    assert ws["senders"][0]["daily_invites_used"] == 10


@pytest.mark.asyncio
async def test_platform_operator_receives_cross_workspace_subscription_and_activity_overview(monkeypatch):
    monkeypatch.setenv("OUTREACH_OPERATOR_EMAILS", "operator@unravler.com")
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()

    db = Database(
        workspaces=[
            {"workspace_id": "ws-1", "name": "Acme Outbound", "owner_id": "u-1"},
            {"workspace_id": "ws-2", "name": "Zenith Labs", "owner_id": "u-2"},
            {"workspace_id": "ws-3", "name": "Pending Co", "owner_id": "u-3"},
        ],
        users=[
            {"user_id": "u-1", "email": "operator@unravler.com", "display_name": "Shubham", "last_login_at": now.isoformat()},
            {"user_id": "u-2", "email": "ops@zenith.io", "display_name": "Zenith Ops", "last_login_at": (now - timedelta(days=2)).isoformat()},
            {"user_id": "u-3", "email": "lead@pending.co", "display_name": "Pending Lead", "last_login_at": (now - timedelta(days=10)).isoformat()},
        ],
        outreach_entitlements=[
            {
                "workspace_id": "ws-1",
                "status": "active",
                "seats": 3,
                "paid_through": (now + timedelta(days=20)).isoformat(),
                "payment_source": "manual_verified_invoice",
                "price_usd_per_sender_month": 59,
            },
            {
                "workspace_id": "ws-2",
                "status": "active",
                "seats": 1,
                "paid_through": (now + timedelta(days=3)).isoformat(),
                "payment_source": "manual_verified_invoice",
                "price_usd_per_sender_month": 59,
            },
        ],
        outreach_access_requests=[
            {"workspace_id": "ws-3", "seats": 2, "country_code": "IN", "status": "pending_quote"},
        ],
        outreach_accounts=[
            {"id": "a1", "workspace_id": "ws-1", "status": "active"},
            {"id": "a2", "workspace_id": "ws-1", "status": "active"},
            {"id": "a3", "workspace_id": "ws-2", "status": "active"},
        ],
        outreach_voice_preparation_budgets=[
            {"_id": f"ws-1:{today_iso}", "workspace_id": "ws-1", "day": today_iso, "clips": 4, "chars": 1500},
            {"_id": f"ws-2:{today_iso}", "workspace_id": "ws-2", "day": today_iso, "clips": 2, "chars": 800},
        ],
    )

    operator_user = {
        "user_id": "u-1",
        "email": "operator@unravler.com",
        "display_name": "Shubham",
        "default_workspace_id": "ws-1",
    }

    res = await billing.get_subscription_monitor(current_user=operator_user, db=db)

    assert res["is_platform_operator"] is True
    overview = res["platform_overview"]
    assert overview is not None

    kpis = overview["kpis"]
    assert kpis["total_users"] == 3
    assert kpis["active_users_24h"] == 1
    assert kpis["active_users_7d"] == 2
    assert kpis["total_workspaces"] == 3
    assert kpis["active_paid_workspaces"] == 2
    assert kpis["expiring_soon_workspaces"] == 1
    assert kpis["pending_quote_workspaces"] == 1
    assert kpis["total_granted_seats"] == 4
    assert kpis["total_connected_senders"] == 3
    assert kpis["mrr_usd"] == 4 * 59
    assert kpis["voice_clips_today"] == 6
    assert kpis["voice_chars_today"] == 2300

    # Expiring soon workspace (ws-2) should sort first in subscribers table
    subs = overview["subscribers"]
    assert len(subs) == 3
    assert subs[0]["workspace_id"] == "ws-2"
    assert subs[0]["lifecycle_state"] == "expiring_soon"
