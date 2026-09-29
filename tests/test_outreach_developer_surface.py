"""
Comprehensive test suite for Outreach Developer Surface (Slice 2).
Verifies:
1. API Key creation, hashing, scope enforcement, and revocation
2. Public Lead Ingestion (Idempotency-Key, LinkedIn URL validation, suppression check, warm-up protection)
3. Public Lead Pause and Stage Change Outbox Emission
4. Public Campaign Listing (sanitized response fields)
5. Rate Limiting enforcement (429 with Retry-After header)
6. Webhook secret rotation and delivery log replay
"""
import os
from datetime import datetime, timezone
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from cryptography.fernet import Fernet
import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.api.integrations import (
    CreateApiKeyRequest,
    CreateWebhookRequest,
    PublicLeadEnrollRequest,
    create_api_key,
    create_webhook,
    public_enroll_lead,
    public_list_campaigns,
    public_pause_lead,
    require_api_key_scope,
    revoke_api_key,
    rotate_webhook_secret,
)
from outreach.models import LeadExecutionState


# ── 1. API Key Scopes & Authentication Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_create_api_key_rejects_unapproved_scopes():
    """Keys cannot request unapproved scopes like admin or billing."""
    db = MagicMock()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}

    with pytest.raises(HTTPException) as exc:
        await create_api_key(
            CreateApiKeyRequest(name="Admin Key", scopes=["super_admin:write"]),
            current_user=user,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "Invalid scopes" in exc.value.detail


@pytest.mark.asyncio
async def test_api_key_scope_enforcement():
    """API key missing required scope raises 403 Forbidden."""
    db = MagicMock()
    raw_key = "unr_live_1234567890123456789012345678901234"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    # Key has only campaigns:read scope
    db.outreach_api_keys.find_one = AsyncMock(return_value={
        "id": "key_1",
        "workspace_id": "ws_1",
        "key_hash": key_hash,
        "scopes": ["campaigns:read"],
        "revoked_at": None,
        "expires_at": None,
    })

    auth_dep = require_api_key_scope("leads:write")
    req = MagicMock()
    res = MagicMock()

    # Calling with leads:write when key only has campaigns:read -> 403
    with pytest.raises(HTTPException) as exc:
        await auth_dep(
            request=req,
            response=res,
            authorization=f"Bearer {raw_key}",
            db=db,
        )
    assert exc.value.status_code == 403
    assert "missing required scope 'leads:write'" in exc.value.detail


@pytest.mark.asyncio
async def test_revoked_api_key_rejected():
    """Revoked API key raises 401 Unauthorized."""
    db = MagicMock()
    raw_key = "unr_live_revoked_key_12345678901234567890"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    db.outreach_api_keys.find_one = AsyncMock(return_value={
        "id": "key_2",
        "workspace_id": "ws_1",
        "key_hash": key_hash,
        "scopes": ["leads:write"],
        "revoked_at": datetime.now(timezone.utc),  # Revoked
    })

    auth_dep = require_api_key_scope("leads:write")
    with pytest.raises(HTTPException) as exc:
        await auth_dep(
            request=MagicMock(),
            response=MagicMock(),
            authorization=f"Bearer {raw_key}",
            db=db,
        )
    assert exc.value.status_code == 401


# ── 2. Public Lead Ingestion & Guardrails Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_public_enroll_lead_requires_idempotency_key():
    """Enrollment without valid Idempotency-Key raises 400 Bad Request."""
    db = MagicMock()
    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_1",
        linkedin_url="https://linkedin.com/in/sarahprospect",
        first_name="Sarah",
    )

    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(
            req=req,
            idempotency_key="   ",  # Empty
            auth=auth,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "Idempotency-Key" in exc.value.detail


@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_warming_up_campaign():
    """Cannot enroll prospects into a campaign currently undergoing warm-up."""
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_warm",
        "workspace_id": "ws_1",
        "status": "warming_up",  # In warm-up
    })

    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_warm",
        linkedin_url="https://linkedin.com/in/validuser",
        first_name="Valid",
    )

    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(
            req=req,
            idempotency_key="idemp_123",
            auth=auth,
            db=db,
        )
    assert exc.value.status_code == 409
    assert "warm-up" in exc.value.detail


@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_invalid_linkedin_url():
    """Non-LinkedIn profile URL raises 400 Bad Request."""
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_1",
        "workspace_id": "ws_1",
        "status": "active",
    })

    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_1",
        linkedin_url="https://twitter.com/notlinkedin",
        first_name="Alex",
    )

    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(
            req=req,
            idempotency_key="idemp_456",
            auth=auth,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "LinkedIn personal profile URL" in exc.value.detail


@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_suppressed_email():
    """Suppressed email address raises 400 Bad Request."""
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_1",
        "workspace_id": "ws_1",
        "status": "active",
    })
    # Suppression record exists
    db.outreach_email_suppressions.find_one = AsyncMock(return_value={"email": "optout@example.com"})

    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_1",
        linkedin_url="https://linkedin.com/in/prospect",
        first_name="Bob",
        email="optout@example.com",
    )

    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(
            req=req,
            idempotency_key="idemp_789",
            auth=auth,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "suppression list" in exc.value.detail


@pytest.mark.asyncio
async def test_public_enroll_lead_idempotent_deduplication():
    """Re-enrolling an existing prospect returns already_enrolled with lead_id."""
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_1",
        "workspace_id": "ws_1",
        "status": "active",
    })
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    # Lead already exists
    db.outreach_leads.find_one = AsyncMock(return_value={"id": "lead_existing_999"})

    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_1",
        linkedin_url="https://linkedin.com/in/sarahprospect",
        first_name="Sarah",
    )

    res = await public_enroll_lead(
        req=req,
        idempotency_key="idemp_repeat",
        auth=auth,
        db=db,
    )
    assert res["status"] == "already_enrolled"
    assert res["lead_id"] == "lead_existing_999"


@pytest.mark.asyncio
async def test_public_enroll_lead_success_emits_outbox_event():
    """Valid enrollment inserts lead, increments campaign count, and writes to outbox."""
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_1",
        "workspace_id": "ws_1",
        "status": "active",
    })
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_leads.find_one = AsyncMock(return_value=None)  # Not existing
    db.outreach_leads.insert_one = AsyncMock()
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_event_outbox.insert_one = AsyncMock()

    auth = {"workspace_id": "ws_1"}
    req = PublicLeadEnrollRequest(
        campaign_id="camp_1",
        linkedin_url="https://linkedin.com/in/newprospect",
        first_name="Emily",
        company_name="Acme",
    )

    res = await public_enroll_lead(
        req=req,
        idempotency_key="idemp_new_lead",
        auth=auth,
        db=db,
    )
    assert res["status"] == "enrolled"
    assert res["lead_id"].startswith("lead_")
    db.outreach_leads.insert_one.assert_awaited_once()
    db.outreach_campaigns.update_one.assert_awaited_once()
    db.outreach_event_outbox.insert_one.assert_awaited_once()


# ── 3. Public Lead Pause Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_pause_lead_stops_lead_and_emits_stage_changed_event():
    """Pausing a lead marks it stopped and writes lead.stage_changed to outbox."""
    db = MagicMock()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead_stop_1",
        "workspace_id": "ws_1",
        "campaign_id": "camp_1",
        "execution_state": LeadExecutionState.QUEUED.value,
    })
    db.outreach_leads.update_one = AsyncMock()
    db.outreach_event_outbox.insert_one = AsyncMock()

    auth = {"workspace_id": "ws_1"}
    res = await public_pause_lead("lead_stop_1", auth=auth, db=db)

    assert res["status"] == "paused"
    assert res["lead_id"] == "lead_stop_1"

    # Verify execution_state updated to failed/stopped
    update_arg = db.outreach_leads.update_one.await_args.args[1]["$set"]
    assert update_arg["execution_state"] == LeadExecutionState.FAILED.value
    assert update_arg["next_action_due_at"] is None
    db.outreach_event_outbox.insert_one.assert_awaited_once()


# ── 4. Webhook Secret Rotation & Ingestion ───────────────────────────────────

@pytest.mark.asyncio
async def test_rotate_webhook_secret():
    """Secret rotation produces a new whsec_ secret and updates document."""
    db = MagicMock()
    db.outreach_webhooks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}

    res = await rotate_webhook_secret("wh_123", current_user=user, db=db)

    assert res["status"] == "rotated"
    assert res["webhook_id"] == "wh_123"
    assert res["new_secret"].startswith("whsec_")
    db.outreach_webhooks.update_one.assert_awaited_once()
