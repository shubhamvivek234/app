"""
Automated test suite for Phase 5: Hybrid Execution Engine (Voyager API + Rate Limiter + Campaigns).
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from types import SimpleNamespace
from outreach.core.crypto import encrypt_secret


@pytest.fixture(autouse=True)
def sandbox_linkedin_sessions(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from outreach.models import WorkingSchedule, LeadExecutionState
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.engine.voyager_client import VoyagerClient
from outreach.tasks.sequence_executor import SequenceExecutor, interpolate_template
from outreach.api.campaigns import (
    CreateCampaignRequest,
    create_campaign,
    list_campaigns,
    launch_campaign,
    pause_campaign,
)


def test_working_hours_gatekeeper():
    """Verify schedule checker accurately identifies business hours vs after-hours/weekends."""
    schedule = WorkingSchedule(
        timezone="UTC",
        start_time="09:00",
        end_time="17:00",
        days=[0, 1, 2, 3, 4],  # Mon-Fri
    )

    # Wednesday 11:00 AM UTC (Within hours)
    wed_noon = datetime(2026, 9, 23, 11, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert OutboundRateLimiter.is_within_working_hours(schedule, wed_noon) is True

    # Wednesday 20:00 PM UTC (After hours)
    wed_night = datetime(2026, 9, 23, 20, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert OutboundRateLimiter.is_within_working_hours(schedule, wed_night) is False

    # Saturday 12:00 PM UTC (Weekend)
    sat_noon = datetime(2026, 9, 26, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert OutboundRateLimiter.is_within_working_hours(schedule, sat_noon) is False


@pytest.mark.asyncio
async def test_daily_limit_governor():
    """Verify rate limiter blocks actions once configured cap is reached."""
    mock_db = AsyncMock()
    mock_db.outreach_accounts.update_one = AsyncMock(side_effect=[
        SimpleNamespace(matched_count=1), SimpleNamespace(matched_count=0),
    ])

    account = {
        "id": "acc_1",
        "limits": {"connection_invites": 20},
        "counters": {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "connection_invites": 19},
    }

    # 1. 20th action should succeed
    allowed1 = await OutboundRateLimiter.check_and_increment_daily_limit(account, "connection_invites", mock_db)
    assert allowed1 is True

    # 2. 21st action should be blocked
    account["counters"]["connection_invites"] = 20
    allowed2 = await OutboundRateLimiter.check_and_increment_daily_limit(account, "connection_invites", mock_db)
    assert allowed2 is False


def test_template_interpolation():
    """Verify dynamic token replacement in messages."""
    tpl = "Hi {{first_name}}, loved your work at {{company_name}}!"
    lead = {"first_name": "Satya", "company_name": "Microsoft"}
    assert interpolate_template(tpl, lead) == "Hi Satya, loved your work at Microsoft!"


@pytest.mark.asyncio
async def test_voyager_client_mock_methods():
    """Verify lightweight voyager actions execute cleanly."""
    client = VoyagerClient(session_cookie_enc="mock_cookie_test")

    visit_res = await client.visit_profile("https://linkedin.com/in/test")
    assert visit_res["status"] == "viewed"

    invite_res = await client.send_connection_invite("urn:li:test", "Custom note")
    assert invite_res["status"] == "invite_sent"

    msg_res = await client.send_direct_message("urn:li:test", "Hello")
    assert msg_res["status"] == "message_sent"


@pytest.mark.asyncio
async def test_campaign_api_lifecycle():
    """Verify campaign creation, lead pooling, and launch/pause states."""
    mock_db = AsyncMock()
    mock_db.outreach_campaigns.insert_one = AsyncMock()

    user = {"user_id": "u1", "default_workspace_id": "ws1"}

    # 1. Create Campaign
    req = CreateCampaignRequest(name="Q4 SaaS Founders", sender_account_ids=["acc_1", "acc_2"])
    camp = await create_campaign(req=req, current_user=user, db=mock_db)
    assert camp["name"] == "Q4 SaaS Founders"
    assert camp["status"] == "draft"

    # 2. Mock Launch with 3 leads pooled across 2 senders
    mock_db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": camp["id"],
        "user_id": "u1",
        "workspace_id": "ws1",
        "status": "draft",
        "schedule": camp["schedule"],
        "sender_account_ids": ["acc_1", "acc_2"],
    })
    senders_cursor = AsyncMock()
    senders_cursor.to_list = AsyncMock(return_value=[
        {"id": account_id, "workspace_id": "ws1", "status": "active", "session_cookie_enc": encrypt_secret(f"mock_{account_id}")}
        for account_id in ("acc_1", "acc_2")
    ])
    mock_db.outreach_accounts.find = lambda query: senders_cursor
    mock_db.outreach_leads.count_documents = AsyncMock(return_value=3)
    empty_cursor = AsyncMock()
    empty_cursor.to_list = AsyncMock(return_value=[])
    mock_db.outreach_engage_lists.find = lambda query: empty_cursor

    # 3 unassigned leads
    fake_leads = [{"id": "lead_1"}, {"id": "lead_2"}, {"id": "lead_3"}]
    mock_db.outreach_leads.find.return_value.to_list = AsyncMock(return_value=fake_leads)
    mock_db.outreach_leads.update_one = AsyncMock()
    mock_db.outreach_campaigns.update_one = AsyncMock()

    launch_res = await launch_campaign(camp["id"], current_user=user, db=mock_db)
    assert launch_res["status"] == "launched"
    assert launch_res["allocated_leads_count"] == 3

    # 3. Pause
    pause_res = await pause_campaign(camp["id"], current_user=user, db=mock_db)
    assert pause_res["status"] == "paused"
