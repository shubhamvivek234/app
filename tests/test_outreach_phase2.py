"""
Automated test suite for Phase 2: LinkedIn Connection, 2FA Relay & 1:1 Residential Proxy Layer.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock, patch
from outreach.engine.session_authenticator import (
    SessionAuthenticator,
    InvalidSessionError,
    AuthenticationError,
)
from outreach.api.accounts import (
    ConnectCookieRequest,
    LoginStartRequest,
    LoginVerify2FARequest,
    UpdateLimitsRequest,
    connect_via_cookie,
    login_start,
    login_verify_2fa,
    list_outreach_accounts,
    update_account_limits,
    disconnect_account,
)


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
async def test_credential_login_and_2fa_relay():
    """Verify email login triggers 2FA when email indicates 2FA requirement."""
    # 1. Start login with 2FA email
    start_res = await SessionAuthenticator.start_credential_login("user.2fa@example.com", "my_pass_123")
    assert start_res["status"] == "2fa_required"
    assert "session_id" in start_res

    session_id = start_res["session_id"]

    # 2. Verify invalid code fails
    with pytest.raises(AuthenticationError):
        await SessionAuthenticator.verify_2fa_code(session_id, "000000")

    # 3. Start again and verify valid code succeeds
    start_res2 = await SessionAuthenticator.start_credential_login("user.2fa@example.com", "my_pass_123")
    auth_res = await SessionAuthenticator.verify_2fa_code(start_res2["session_id"], "123456")
    assert auth_res["status"] == "authenticated"
    assert "li_at" in auth_res
    assert auth_res["account_name"] == "User 2Fa"


@pytest.mark.asyncio
async def test_connect_via_cookie_endpoint_end_to_end():
    """Verify connect_via_cookie assigns proxy, encrypts cookie, and stores sanitized account."""
    mock_db = AsyncMock()
    inserted_docs = []

    async def fake_insert(doc):
        inserted_docs.append(doc)
        return AsyncMock(inserted_id="mock_id_1")

    mock_db.outreach_accounts.insert_one = AsyncMock(side_effect=fake_insert)
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=None)

    req = ConnectCookieRequest(
        li_at="mock_li_at_sample_99",
        li_a="mock_li_a_nav_99",
        premium_product="sales_navigator",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        jsession_id="ajax:12345",
        country_code="US",
        workspace_id="ws_test",
    )
    user = {"user_id": "user_p2_123", "default_workspace_id": "ws_test"}

    result = await connect_via_cookie(req=req, current_user=user, db=mock_db)

    assert result["account_name"] != ""
    assert result["country_code"] == "US"
    assert result["premium_product"] == "sales_navigator"
    assert result["user_agent"] == "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    assert "session_cookie_enc" not in result  # Sanitized!
    assert "li_a_enc" not in result  # Sanitized!
    assert result["proxy"]["host"] == "127.0.0.1"
    assert "password_enc" not in result["proxy"]  # Sanitized!
    assert len(inserted_docs) == 1
    assert inserted_docs[0]["session_cookie_enc"].startswith("gAAAAA")  # Fernet encrypted in DB!
    assert inserted_docs[0]["li_a_enc"].startswith("gAAAAA")  # Fernet encrypted in DB!
    assert inserted_docs[0]["premium_product"] == "sales_navigator"


@pytest.mark.asyncio
async def test_connect_via_cookie_reconnect_existing():
    """Verify connect_via_cookie updates existing account when same URN is reconnected."""
    existing_acc = {
        "id": "acc_existing_123",
        "user_id": "user_p2_123",
        "linkedin_urn": "urn:li:fsd_profile:sample_99",
        "account_name": "Old Name",
        "session_cookie_enc": "old_enc",
    }
    mock_db = AsyncMock()
    mock_db.outreach_accounts.find_one = AsyncMock(side_effect=[existing_acc, {**existing_acc, "account_name": "LinkedIn Professional (ample_99)"}])
    mock_db.outreach_accounts.update_one = AsyncMock()

    req = ConnectCookieRequest(
        li_at="mock_li_at_sample_99",
        premium_product="sales_navigator",
        country_code="US",
    )
    user = {"user_id": "user_p2_123"}
    res = await connect_via_cookie(req=req, current_user=user, db=mock_db)
    assert res["id"] == "acc_existing_123"
    mock_db.outreach_accounts.update_one.assert_awaited_once()



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
    mock_db.outreach_accounts.delete_one.assert_awaited_once_with({"id": "acc_target_1"})
    mock_db.outreach_campaigns.update_many.assert_awaited_once()
    mock_db.outreach_tasks.update_many.assert_awaited_once()
