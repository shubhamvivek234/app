"""
Regression test suite verifying fixes for the Unravler Outreach production-readiness audit (F01–F26).
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()


def test_f01_vercel_and_compose_hardening():
    """F01: outreach-site vercel.json uses HTTPS api.unravler.com and docker-compose binds 8001 to 127.0.0.1."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    site_vercel = json.loads((root / "outreach-site" / "vercel.json").read_text())
    destinations = [r.get("destination", "") for r in site_vercel.get("rewrites", [])]
    assert all(not d.startswith("http://3.107.7.100") for d in destinations)
    assert any(d.startswith("https://api.unravler.com/api/") for d in destinations)

    compose_text = (root / "docker-compose.yml").read_text()
    assert "${API_BIND_HOST:-127.0.0.1}:8001:8001" in compose_text
    assert "SENTRY_DSN: ${SENTRY_DSN:-}" in compose_text


@pytest.mark.asyncio
async def test_f02_session_exchange_enforces_totp_mfa():
    """F02: /auth/session blocks MFA-enabled accounts when TOTP code is missing."""
    import pyotp
    from api.routes.auth import SessionExchangeRequest, exchange_session
    from fastapi import Response
    from starlette.requests import Request
    from utils.encryption import encrypt

    mfa_secret = encrypt(pyotp.random_base32())
    fake_user = {
        "user_id": "u_mfa_1",
        "email": "mfa@example.com",
        "mfa_enabled": True,
        "mfa_secret": mfa_secret,
    }
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/session",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    response = Response()
    body = SessionExchangeRequest(id_token="firebase-token")

    with (
        patch("api.routes.auth.get_firebase_app", return_value=MagicMock()),
        patch("firebase_admin.auth.verify_id_token", return_value={"uid": "fb_1", "email": "mfa@example.com"}),
        patch("api.deps._bootstrap_user_from_claims", new=AsyncMock(return_value=fake_user)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await exchange_session(request=request, response=response, body=body, db=SimpleNamespace())
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {"mfa_required": True, "message": "TOTP code required"}


def test_f03_session_jti_does_not_collide_with_uid_when_iat_present():
    """F03: compute_session_jti uses uid:iat instead of bare sub so single logout does not poison uid blocklist."""
    from utils.session import compute_session_jti

    claims = {"sub": "user_abc", "iat": 1700000000}
    assert compute_session_jti(claims) == "user_abc:1700000000"
    explicit = {"sub": "user_abc", "iat": 1700000000, "jti": "jti_999"}
    assert compute_session_jti(explicit) == "jti_999"


def test_f06_celery_registers_notifications_and_gdpr_tasks():
    """F06: celery_app includes notifications and gdpr task modules."""
    from celery_workers.celery_app import _SCHEDULE_MODULES, _TASK_MODULES

    assert "celery_workers.tasks.notifications" in _TASK_MODULES
    assert "celery_workers.tasks.gdpr" in _TASK_MODULES
    assert "celery_workers.tasks.gdpr" in _SCHEDULE_MODULES


@pytest.mark.asyncio
async def test_f08_f09_prompt_hydration_does_not_fabricate_profile_facts():
    """F08 & F09: preview_evaluated_message preserves empty missing fields on real leads and marks preview mode."""
    from outreach.api.prompts import PromptPreviewRequest, _synthesize_prompt_output, preview_evaluated_message

    real_lead = {
        "id": "lead_real_1",
        "workspace_id": "ws_1",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "company_name": "Analytical Engine",
        "job_title": "",
        "school": "",
        "skills": "",
    }
    cursor_mock = SimpleNamespace(
        sort=lambda *a, **k: SimpleNamespace(
            limit=lambda *a2, **k2: SimpleNamespace(to_list=AsyncMock(return_value=[real_lead]))
        )
    )
    db = SimpleNamespace(
        outreach_leads=SimpleNamespace(
            find_one=AsyncMock(return_value=real_lead),
            find=MagicMock(return_value=cursor_mock),
        ),
        outreach_prompts=SimpleNamespace(
            find=MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[])))
        ),
    )
    req = PromptPreviewRequest(
        template="Hi {{first_name}} from {{school}}",
        lead_id="lead_real_1",
    )
    res = await preview_evaluated_message(
        req=req,
        current_user={"user_id": "u_1", "default_workspace_id": "ws_1"},
        db=db,
    )
    assert res["lead_preview"]["school"] == ""
    assert res["lead_preview"]["top_skill"] == ""
    assert "school" in res["missing_variables"]
    assert res["generation_mode"] == "heuristic_preview"

    synth = _synthesize_prompt_output("Intro", "Write a short intro to {{first_name}}", res["lead_preview"])
    assert "recent strategic initiatives" not in synth


@pytest.mark.asyncio
async def test_f10_sequence_executor_resolves_canonical_lead_tags():
    """F10: _resolve_sequence_tag_updates populates canonical tag_ids and tag_revision."""
    from outreach.tasks.sequence_executor import _resolve_sequence_tag_updates

    inserted_tags = []

    class FakeTagColl:
        async def find_one(self, query):
            return None

        async def count_documents(self, query):
            return 0

        async def insert_one(self, doc):
            inserted_tags.append(doc)

    db = SimpleNamespace(outreach_lead_tags=FakeTagColl())
    lead = {"id": "lead_1", "tags": [], "tag_ids": [], "tag_revision": 2}
    updates = await _resolve_sequence_tag_updates(db, "ws_123", lead, "Warm Prospect")
    assert "Warm Prospect" in updates["tags"]
    assert len(updates["tag_ids"]) == 1
    assert updates["tag_ids"][0].startswith("tag_")
    assert updates["tag_revision"] == 3
    assert len(inserted_tags) == 1
    assert inserted_tags[0]["name"] == "Warm Prospect"


@pytest.mark.asyncio
async def test_f11_accept_invite_verifies_workspace_and_claims_atomically():
    """F11: accept_invite returns 404 if workspace is missing or invite claim loses race."""
    from api.routes.team import accept_invite

    now = datetime.now(timezone.utc)
    invite_doc = {
        "invite_id": "inv_1",
        "token": "tok_123",
        "workspace_id": "ws_deleted",
        "email": "member@example.com",
        "role": "editor",
        "status": "pending",
        "expires_at": (now + timedelta(days=2)).isoformat(),
    }
    db_missing_ws = SimpleNamespace(
        workspace_invites=SimpleNamespace(find_one=AsyncMock(return_value=invite_doc)),
        workspaces=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    user = {"user_id": "u_2", "email": "member@example.com", "email_verified": True}
    with pytest.raises(HTTPException) as exc_info:
        await accept_invite("tok_123", user, db_missing_ws)
    assert exc_info.value.status_code == 404


def test_f15_log_scrub_redacts_query_key_and_token():
    """F15: LogScrubFilter redacts ?key= and ?token= query parameters."""
    from utils.log_scrub import LogScrubFilter

    raw = "POST https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent?key=AIzaSySecretKey123 HTTP/1.1"
    scrubbed = LogScrubFilter._scrub(raw)
    assert "AIzaSySecretKey123" not in scrubbed
    assert "[REDACTED]" in scrubbed


@pytest.mark.asyncio
async def test_f16_f25_outreach_health_and_overview_report_runtime_truth():
    """F16 & F25: /outreach/health exposes runtime_gates and /outreach/overview queries DB counts."""
    from outreach.api.router import outreach_health, outreach_overview

    health = await outreach_health()
    assert "runtime_gates" in health
    assert "live_actions_enabled" in health["runtime_gates"]
    assert health["runtime_gates"]["integrations_enabled"] is True
    assert health["runtime_gates"]["conditional_auto_launch_enabled"] is True

    db = SimpleNamespace(
        outreach_accounts=SimpleNamespace(count_documents=AsyncMock(return_value=2)),
        outreach_campaigns=SimpleNamespace(count_documents=AsyncMock(return_value=3)),
        outreach_leads=SimpleNamespace(count_documents=AsyncMock(side_effect=[45, 7])),
    )
    overview = await outreach_overview(
        current_user={"user_id": "u_1", "default_workspace_id": "ws_1"},
        db=db,
    )
    assert overview["connected_senders_count"] == 2
    assert overview["active_campaigns_count"] == 3
    assert overview["total_leads_enrolled"] == 45
    assert overview["replies_received"] == 7


@pytest.mark.asyncio
async def test_f20_account_allowance_uses_warmup_weekly_ceiling():
    """F20: _compute_sender_readiness uses WarmUpGovernor.get_weekly_invite_ceiling instead of hardcoded 100."""
    from outreach.api.accounts import _compute_sender_readiness

    now = datetime.now(timezone.utc)
    acc = {
        "id": "acc_1",
        "status": "active",
        "session_cookie_enc": "enc_cookie",
        "proxy": {"host": "1.2.3.4"},
        "warmup_started_at": now - timedelta(days=2),
        "weekly_invites_sent": 40,
        "limits": {"connection_invites": 25, "messages": 40, "profile_visits": 50, "email_sends": 35},
        "daily_counters": {"date": now.strftime("%Y-%m-%d")},
    }
    res = await _compute_sender_readiness(acc, "ws_1", SimpleNamespace(), now, has_entitlement=True)
    assert "weekly_invite_ceiling" in res["effective_allowance"]
    assert res["effective_allowance"]["weekly_invite_ceiling"] >= 100
    assert res["effective_allowance"]["weekly_invites_remaining"] == res["effective_allowance"]["weekly_invite_ceiling"] - 40


def test_f26_non_outreach_routes_hidden_by_default():
    """F26: frontend App.js and backend api/main.py hide legacy social-scheduler routes by default."""
    from pathlib import Path
    from api.main import create_app

    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "src" / "App.js").read_text()
    assert "import CreatePost" not in app_js
    assert "import CalendarView" not in app_js
    assert 'path="/outreach/*"' in app_js

    fastapi_app = create_app()
    mounted_paths = {getattr(r, "path", "") for r in fastapi_app.routes}
    assert any(p.startswith("/api/v1/outreach") for p in mounted_paths)
    assert any(p.startswith("/api/v1/auth") for p in mounted_paths)
    assert not any(p.startswith("/api/v1/posts") for p in mounted_paths)
    assert not any(p.startswith("/api/v1/hashtags") for p in mounted_paths)
