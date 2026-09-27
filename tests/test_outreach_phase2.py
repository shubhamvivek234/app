"""LinkedIn session connection and residential proxy regressions."""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock, patch
from outreach.engine.session_authenticator import (
    SessionAuthenticator,
    InvalidSessionError,
)
from outreach.api.accounts import (
    ConnectCookieRequest,
    UpdateLimitsRequest,
    connect_via_cookie,
    list_outreach_accounts,
    update_account_limits,
    disconnect_account,
)


@pytest.fixture(autouse=True)
def sandbox_linkedin_auth(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")


@pytest.mark.asyncio
async def test_session_cookie_validation_mock():
    """Verify mock cookie validation returns structured profile data."""
    profile = await SessionAuthenticator.validate_session_cookie("mock_li_at_test_pro_123")
    assert "account_name" in profile
    assert profile["account_name"] != ""
    assert "linkedin_urn" in profile


@pytest.mark.asyncio
async def test_empty_cookie_raises_error():
    """Verify empty or whitespace cookie raises InvalidSessionError."""
    with pytest.raises(InvalidSessionError):
        await SessionAuthenticator.validate_session_cookie("   ")


@pytest.mark.asyncio
async def test_connect_via_cookie_queues_encrypted_job_in_authenticated_workspace(monkeypatch):
    """API never calls LinkedIn and never sends cookies through the broker."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    db = AsyncMock()
    db.outreach_entitlements.find_one.return_value = {
        "workspace_id": "ws_test", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice",
        "paid_through": datetime.now(timezone.utc) + timedelta(days=30),
    }
    db.outreach_proxy_leases.find_one.return_value = None
    req = ConnectCookieRequest(
        li_at="AQprivate", jsession_id="ajax:private", li_a="nav-private",
        country_code="IN", workspace_id="other-workspace",
    )
    with patch("outreach.api.connection_jobs.reserve_sender_proxy", new_callable=AsyncMock,
               return_value=SimpleNamespace(proxy_id="iproyal:one")), patch(
        "outreach.api.connection_jobs._enqueue_connection_job",
    ) as enqueue, patch(
        "outreach.engine.session_authenticator.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock,
    ) as verify:
        result = await connect_via_cookie(req, current_user={
            "user_id": "user_p2_123", "default_workspace_id": "ws_test",
        }, db=db)
    assert result["status"] == "queued"
    saved = db.outreach_connection_jobs.insert_one.await_args.args[0]
    assert saved["workspace_id"] == "ws_test"
    assert saved["li_at_enc"] != "AQprivate"
    assert saved["jsession_id_enc"] != "ajax:private"
    verify.assert_not_awaited()
    assert "AQprivate" not in str(enqueue.call_args)


@pytest.mark.asyncio
async def test_reconnect_queues_same_sender_without_using_second_seat(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    db = AsyncMock()
    db.outreach_entitlements.find_one.return_value = {
        "workspace_id": "ws_test", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice",
        "paid_through": datetime.now(timezone.utc) + timedelta(days=30),
    }
    db.outreach_accounts.find_one.return_value = {
        "id": "sender-1", "workspace_id": "ws_test", "country_code": "IN",
    }
    db.outreach_sender_slots.find_one.return_value = {
        "_id": "ws_test:1", "workspace_id": "ws_test", "sender_id": "sender-1",
    }
    db.outreach_proxy_leases.find_one.return_value = {
        "_id": "iproyal:one", "workspace_id": "ws_test", "sender_id": "sender-1",
    }
    with patch("outreach.api.connection_jobs.reserve_sender_proxy", new_callable=AsyncMock,
               return_value=SimpleNamespace(proxy_id="iproyal:one")), patch(
        "outreach.api.connection_jobs._enqueue_connection_job",
    ):
        result = await connect_via_cookie(
            ConnectCookieRequest(li_at="AQnew", jsession_id="ajax:new", country_code="IN",
                                 reconnect_account_id="sender-1"),
            current_user={"user_id": "user_p2_123", "default_workspace_id": "ws_test"}, db=db,
        )
    assert result["status"] == "queued"
    assert db.outreach_connection_jobs.insert_one.await_args.args[0]["sender_id"] == "sender-1"
    db.outreach_sender_slots.insert_one.assert_not_awaited()
@pytest.mark.asyncio
async def test_update_limits_and_disconnect_account():
    """Verify limit update capping and account disconnection."""
    mock_account = {
        "id": "acc_target_1",
        "user_id": "user_p2_123",
        "account_name": "Satya Nadella",
        "limits": {"connection_invites": 20, "messages": 20},
        "proxy": {"proxy_id": "proxy_mock_12345"},
    }
    mock_db = AsyncMock()
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=mock_account)
    mock_db.outreach_accounts.update_one = AsyncMock(return_value=AsyncMock(modified_count=1))
    mock_db.outreach_accounts.delete_one = AsyncMock(return_value=AsyncMock(deleted_count=1))

    user = {"user_id": "user_p2_123"}

    # 1. Update limits
    req = UpdateLimitsRequest(connection_invites=50, messages=15)  # 50 should cap at 35
    updated = await update_account_limits("acc_target_1", req=req, current_user=user, db=mock_db)
    assert updated["id"] == "acc_target_1"

    # 2. Disconnect
    del_res = await disconnect_account("acc_target_1", current_user=user, db=mock_db)
    assert del_res["status"] == "success"
    mock_db.outreach_accounts.delete_one.assert_not_awaited()
    mock_db.outreach_proxy_leases.delete_one.assert_not_awaited()
    assert "session_cookie_enc" in mock_db.outreach_accounts.update_one.await_args.args[1]["$unset"]
    mock_db.outreach_campaigns.update_many.assert_awaited_once()
    mock_db.outreach_tasks.update_many.assert_awaited_once()
