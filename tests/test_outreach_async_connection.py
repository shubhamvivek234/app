"""Session values never travel through Celery payloads or API network calls."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.api.accounts import ConnectCookieRequest, connect_via_cookie
from outreach.models import ProxyConfig, ProxyStatus


USER = {"user_id": "owner-1", "default_workspace_id": "workspace-1"}


@pytest.fixture(autouse=True)
def approved_pilot(monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")


def proxy():
    return ProxyConfig(
        proxy_id="iproyal:one", provider="iproyal_static", host="191.116.125.248",
        port=12323, username="pilot", password_enc="encrypted", country_code="IN",
        status=ProxyStatus.HEALTHY, assigned_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_connection_queues_encrypted_job_and_never_calls_linkedin_in_api():
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "workspace-1", "status": "active", "seats": 1,
        "paid_through": datetime.now(timezone.utc) + timedelta(days=30),
        "payment_source": "manual_verified_invoice",
    })
    db.outreach_sender_slots.insert_one = AsyncMock()
    db.outreach_connection_locks.insert_one = AsyncMock()
    db.outreach_proxy_leases.find_one = AsyncMock(return_value=None)
    db.outreach_connection_jobs.insert_one = AsyncMock()
    with patch("outreach.api.connection_jobs.reserve_sender_proxy", new_callable=AsyncMock, return_value=proxy()), patch(
        "outreach.engine.session_authenticator.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock,
    ) as linkedin, patch("outreach.api.connection_jobs._enqueue_connection_job") as enqueue:
        result = await connect_via_cookie(
            ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="IN"),
            current_user=USER, db=db,
        )
    assert result["status"] == "queued"
    assert result["job_id"]
    linkedin.assert_not_called()
    queued = db.outreach_connection_jobs.insert_one.await_args.args[0]
    assert queued["li_at_enc"] != "AQprivate"
    assert queued["jsession_id_enc"] != "ajax:private"
    assert "AQprivate" not in str(enqueue.call_args)
    assert "ajax:private" not in str(enqueue.call_args)


@pytest.mark.asyncio
async def test_no_paid_entitlement_rejects_before_proxy_reservation():
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value=None)
    with patch("outreach.api.connection_jobs.reserve_sender_proxy", new_callable=AsyncMock) as reserve:
        with pytest.raises(Exception) as error:
            await connect_via_cookie(
                ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="IN"),
                current_user=USER, db=db,
            )
    assert error.value.status_code == 402
    reserve.assert_not_called()


@pytest.mark.asyncio
async def test_live_connection_rejects_mock_auth_before_allocating_slot(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    db = MagicMock()
    with pytest.raises(Exception) as error:
        await connect_via_cookie(
            ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="IN"),
            current_user=USER, db=db,
        )
    assert error.value.status_code == 503
    db.outreach_sender_slots.insert_one.assert_not_called()
