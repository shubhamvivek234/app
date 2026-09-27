"""Background connection verification rechecks entitlement and proxy ownership."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.core.crypto import encrypt_secret
from celery_workers.tasks.outreach import _verify_sender_connection


NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def approved_pilot(monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")


def make_db(*, paid=True, proxy_valid=True):
    db = MagicMock()
    job = {
        "id": "job-1", "workspace_id": "ws-1", "sender_id": "sender-1", "user_id": "user-1",
        "proxy_id": "iproyal:one", "country_code": "IN", "reconnect": False,
        "created_slot": True, "new_proxy_reservation": True, "status": "running",
        "li_at_enc": encrypt_secret("AQsecret"), "jsession_id_enc": encrypt_secret("ajax:csrf"),
        "li_a_enc": "", "user_agent": "Test browser", "premium_product": "classic",
    }
    db.outreach_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_connection_jobs.find_one = AsyncMock(return_value=job)
    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "ws-1", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": NOW + timedelta(days=30),
    } if paid else None)
    db.outreach_sender_slots.find_one = AsyncMock(return_value={"sender_id": "sender-1", "workspace_id": "ws-1"})
    db.outreach_proxy_leases.find_one = AsyncMock(return_value={
        "_id": "iproyal:one", "workspace_id": "ws-1", "sender_id": "sender-1",
    })
    db.outreach_proxy_inventory.find_one = AsyncMock(return_value={
        "_id": "iproyal:one", "provider": "iproyal_static", "status": "available",
        "host": "191.116.125.248", "port": 12323, "username": "pilot",
        "password_enc": encrypt_secret("password"), "country_code": "IN",
        "last_workspace_id": "ws-1",
        "expires_at": NOW + timedelta(days=30) if proxy_valid else NOW - timedelta(days=1),
    })
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()
    db.outreach_connection_locks.delete_one = AsyncMock()
    db.outreach_sender_slots.delete_one = AsyncMock()
    db.outreach_proxy_leases.delete_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_worker_verifies_session_and_scrubs_pending_secrets():
    db = make_db()
    with patch("celery_workers.tasks.outreach.JITProxyManager.test_proxy_health", new_callable=AsyncMock, return_value=True), patch(
        "celery_workers.tasks.outreach.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock,
        return_value={"account_name": "Pilot", "linkedin_urn": "urn:li:person:one"},
    ) as verify:
        result = await _verify_sender_connection("job-1", "ws-1", "job-1", db=db)
    assert result["status"] == "completed"
    assert verify.await_args.kwargs["li_at"] == "AQsecret"
    saved = db.outreach_accounts.insert_one.await_args.args[0]
    assert saved["id"] == "sender-1"
    assert saved["session_cookie_enc"] != "AQsecret"
    assert any("li_at_enc" in call.args[1].get("$unset", {}) for call in db.outreach_connection_jobs.update_one.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("paid,proxy_valid", [(False, True), (True, False)])
async def test_worker_fails_closed_if_payment_or_provider_term_expired(paid, proxy_valid):
    db = make_db(paid=paid, proxy_valid=proxy_valid)
    with patch("celery_workers.tasks.outreach.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock) as verify:
        result = await _verify_sender_connection("job-1", "ws-1", "job-1", db=db)
    assert result["status"] == "failed"
    verify.assert_not_called()
    db.outreach_accounts.insert_one.assert_not_called()
    db.outreach_sender_slots.delete_one.assert_awaited_once()
