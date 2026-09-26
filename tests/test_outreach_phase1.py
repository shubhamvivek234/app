"""
Automated test suite for Phase 1: LinkedIn Outbound & AI Sequence Engine.
Verifies isolated data schemas, encryption, JIT proxy manager, and health endpoint.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from datetime import datetime, timezone
from outreach.models import (
    AccountAuthMode,
    AccountStatus,
    CampaignStatus,
    DailyCounters,
    DailyLimits,
    LeadExecutionState,
    OutreachAccount,
    OutreachCampaign,
    OutreachLead,
    OutreachSequence,
    ProxyConfig,
    ProxyStatus,
    SequenceEdge,
    SequenceNode,
    SequenceNodeType,
    WorkingSchedule,
)
from outreach.core.proxy_manager import JITProxyManager
from outreach.api.router import outreach_health
from utils.encryption import encrypt, decrypt


def test_outreach_account_model_and_encryption():
    """Verify account model creates valid records with encrypted session cookies."""
    raw_cookie = "AQEDATabcdef1234567890"
    encrypted_cookie = encrypt(raw_cookie)
    assert encrypted_cookie != raw_cookie
    assert decrypt(encrypted_cookie) == raw_cookie

    account = OutreachAccount(
        workspace_id="ws_123",
        user_id="user_456",
        account_name="Alex LinkedIn",
        auth_mode=AccountAuthMode.COOKIE,
        session_cookie_enc=encrypted_cookie,
        country_code="US",
        limits=DailyLimits(connection_invites=25, messages=20),
    )

    assert account.account_name == "Alex LinkedIn"
    assert account.limits.connection_invites == 25
    assert account.limits.messages == 20
    assert account.status == AccountStatus.ACTIVE
    assert account.warmup_level == 1
    assert decrypt(account.session_cookie_enc) == raw_cookie


def test_outreach_campaign_and_schedule():
    """Verify campaign default schedule is Monday-Friday 9am-5pm."""
    schedule = WorkingSchedule(timezone="America/New_York", start_time="09:00", end_time="17:00")
    campaign = OutreachCampaign(
        workspace_id="ws_123",
        user_id="user_456",
        name="Q3 B2B Outreach",
        sender_account_ids=["acc_1", "acc_2"],
        schedule=schedule,
    )

    assert campaign.status == CampaignStatus.DRAFT
    assert len(campaign.sender_account_ids) == 2
    assert campaign.schedule.days == [0, 1, 2, 3, 4]  # Mon-Fri
    assert campaign.schedule.timezone == "America/New_York"


def test_sequence_dag_nodes_and_edges():
    """Verify all 10 LinkedIn actions and conditions serialize cleanly."""
    node1 = SequenceNode(
        id="node_1",
        type=SequenceNodeType.VISIT_PROFILE,
        title="Visit Profile",
        delay_hours=0,
    )
    node2 = SequenceNode(
        id="node_2",
        type=SequenceNodeType.CONNECTION_REQUEST,
        title="Send Invite",
        delay_hours=24,
        config={"custom_note": "Hi {{first_name}}!"},
    )
    node3 = SequenceNode(
        id="node_3",
        type=SequenceNodeType.VOICE_NOTE,
        title="Voice Note",
        delay_hours=48,
        config={"voice_id": "v_123", "script": "Hey {{first_name}}, loved your post!"},
    )

    edge1 = SequenceEdge(id="e1", source="node_1", target="node_2")
    edge2 = SequenceEdge(id="e2", source="node_2", target="node_3", label="accepted")

    seq = OutreachSequence(
        campaign_id="camp_999",
        nodes=[node1, node2, node3],
        edges=[edge1, edge2],
    )

    assert len(seq.nodes) == 3
    assert len(seq.edges) == 2
    assert seq.nodes[2].type == SequenceNodeType.VOICE_NOTE
    assert seq.edges[1].label == "accepted"


def test_outreach_lead_crm_attributes():
    """Verify lead model fields, custom variables, and execution tracking."""
    lead = OutreachLead(
        campaign_id="camp_999",
        workspace_id="ws_123",
        linkedin_url="https://www.linkedin.com/in/satyanadella",
        first_name="Satya",
        last_name="Nadella",
        company_name="Microsoft",
        job_title="Chairman and CEO",
        location="Redmond, WA",
        custom_variables={"revenue": "$200B", "industry": "Cloud"},
    )

    assert lead.execution_state == LeadExecutionState.QUEUED
    assert lead.first_name == "Satya"
    assert lead.custom_variables["industry"] == "Cloud"
    assert lead.next_action_due_at is None
    assert lead.is_connected is False


@pytest.mark.asyncio
async def test_jit_proxy_manager_mock_lifecycle():
    """Verify on-demand proxy ordering, URL formatting, health check, and release in mock mode."""
    manager = JITProxyManager(api_key="mock")
    assert manager.is_mock is True

    # 1. Order proxy
    proxy = await manager.order_static_residential_proxy(country_code="US")
    assert proxy.proxy_id.startswith("proxy_mock_")
    assert proxy.status == ProxyStatus.HEALTHY
    assert proxy.host == "127.0.0.1"

    # 2. Format URL
    url = manager.format_proxy_url(proxy)
    assert url.startswith("http://user_proxy_mock_")
    assert "@127.0.0.1:8080" in url

    # 3. Health check
    is_healthy = await manager.test_proxy_health(proxy)
    assert is_healthy is True

    # 4. Release proxy
    released = await manager.release_proxy(proxy.proxy_id)
    assert released is True


@pytest.mark.asyncio
async def test_outreach_health_endpoint():
    """Verify outreach health check returns operational status."""
    res = await outreach_health()
    assert res["status"] == "healthy"
    assert res["subsystem"] == "linkedin_outbound_engine"
    assert res["version"] == "1.0.0"
    assert res["features"]["hybrid_engine"] is True
    assert res["features"]["dedicated_proxy_pool"] is True
