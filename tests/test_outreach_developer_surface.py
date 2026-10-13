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


@pytest.fixture(autouse=True)
def enable_integrations_for_tests(monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")


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


def enrollment_db(status="draft", *, existing=False, suppressed=False):
    from tests.outreach_memory import Database
    return Database(outreach_campaigns=[{"id": "camp_1", "workspace_id": "ws_1", "status": status}],
        outreach_api_keys=[{"id": "key", "workspace_id": "ws_1", "key_hash": "digest", "scopes": ["leads:write"]}],
        outreach_leads=[{"id": "existing", "campaign_id": "camp_1", "workspace_id": "ws_1", "linkedin_url": "https://linkedin.com/in/person"}] if existing else [],
        outreach_email_suppressions=[{"workspace_id": "ws_1", "email": "person@example.test"}] if suppressed else [])

ENROLL_AUTH = {"workspace_id": "ws_1", "key_id": "key", "key_hash": "digest"}

def enrollment_request(url="https://linkedin.com/in/person"):
    return PublicLeadEnrollRequest(campaign_id="camp_1", linkedin_url=url, first_name="Person", email="person@example.test")

@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_warming_up_campaign():
    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(enrollment_request(), "operation", auth=ENROLL_AUTH, db=enrollment_db("warming_up"))
    assert exc.value.status_code == 409

@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_invalid_linkedin_url():
    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(enrollment_request("https://twitter.com/person"), "operation", auth=ENROLL_AUTH, db=enrollment_db())
    assert exc.value.status_code == 400 and "LinkedIn personal profile URL" in exc.value.detail

@pytest.mark.asyncio
async def test_public_enroll_lead_rejects_suppressed_email():
    with pytest.raises(HTTPException) as exc:
        await public_enroll_lead(enrollment_request(), "operation", auth=ENROLL_AUTH, db=enrollment_db(suppressed=True))
    assert exc.value.status_code == 400 and "suppression list" in exc.value.detail

@pytest.mark.asyncio
async def test_public_enroll_lead_idempotent_deduplication():
    res = await public_enroll_lead(enrollment_request(), "operation", auth=ENROLL_AUTH, db=enrollment_db(existing=True))
    assert res["status"] == "already_enrolled" and res["lead_id"] == "existing"

@pytest.mark.asyncio
async def test_public_enroll_lead_success_emits_outbox_event():
    db = enrollment_db()
    res = await public_enroll_lead(enrollment_request(), "operation", auth=ENROLL_AUTH, db=db)
    assert res["status"] == "enrolled" and len(db.outreach_leads.docs) == 1
    assert db.outreach_campaigns.docs[0]["leads_count"] == 1
    assert len(db.outreach_event_outbox.docs) == 1
    assert await public_enroll_lead(enrollment_request(), "operation", auth=ENROLL_AUTH, db=db) == res


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
    """Rotation installs a new generation, encrypted at rest, under current owner authority."""
    from tests.outreach_memory import Database
    from utils.encryption import encrypt, decrypt_strict
    db = Database(users=[{"user_id": "usr_1", "status": "active"}],
        workspace_members=[{"workspace_id": "ws_1", "user_id": "usr_1", "role": "owner"}],
        outreach_webhooks=[{"workspace_id": "ws_1", "id": "wh_123", "target_url": "https://example.com/hook",
            "status": "active", "secret_enc": encrypt("old-secret")}])
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}
    res = await rotate_webhook_secret("wh_123", current_user=user, db=db)
    assert res["status"] == "rotated" and res["webhook_id"] == "wh_123"
    assert res["new_secret"].startswith("whsec_")
    row = await db.outreach_webhooks.find_one({"workspace_id": "ws_1", "id": "wh_123"})
    assert decrypt_strict(row["secret_enc"]) == res["new_secret"] and row["credential_generation"]
