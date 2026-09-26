"""First-run account connection and campaign launch safety regressions."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.api.accounts import (
    ConnectCookieRequest,
    connect_via_cookie,
    disconnect_account,
    list_outreach_accounts,
    login_start,
    login_verify_2fa,
    router as accounts_router,
)
from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.campaigns import LaunchCampaignRequest, launch_campaign
from outreach.api.sequences import SaveSequenceRequest, save_campaign_sequence
from outreach.engine.session_authenticator import InvalidSessionError, SessionAuthenticator
from outreach.engine.voyager_client import VoyagerClient
from outreach.core.crypto import encrypt_secret, decrypt_secret
from outreach.core.dag_compiler import DAGCompiler


USER = {"user_id": "user_a", "default_workspace_id": "workspace_a"}


def test_builtin_templates_do_not_claim_unmeasured_conversion_rates():
    templates = DAGCompiler.get_prebuilt_templates()
    assert all(not any(key in template for key in ("uses", "acceptance", "reply")) for template in templates)


@pytest.mark.asyncio
async def test_live_auth_rejects_mock_cookie_without_contacting_linkedin(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    with patch("outreach.engine.session_authenticator.httpx.AsyncClient") as http_client:
        with pytest.raises(InvalidSessionError):
            await SessionAuthenticator.validate_session_cookie("mock_session")
    http_client.assert_not_called()


@pytest.mark.asyncio
async def test_session_verification_network_error_does_not_expose_proxy_secret(monkeypatch, caplog):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    with patch("outreach.engine.session_authenticator.httpx.AsyncClient",
               side_effect=httpx.ProxyError("http://user:secret@proxy.example")):
        with pytest.raises(InvalidSessionError) as error:
            await SessionAuthenticator.validate_session_cookie("AQsession", jsession_id="ajax:123")
    assert "secret" not in str(error.value)
    assert "secret" not in caplog.text


def test_live_voyager_cannot_treat_a_mock_cookie_as_a_real_sender(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    with pytest.raises(ValueError):
        VoyagerClient(encrypt_secret("mock_sender"), jsession_id="ajax:123")


@pytest.mark.asyncio
async def test_retired_credential_endpoints_reject_without_parsing_password_or_allocating_proxy(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    with patch("outreach.api.accounts.JITProxyManager") as proxy:
        with pytest.raises(HTTPException) as start_error:
            await login_start(current_user=USER)
        with pytest.raises(HTTPException) as verify_error:
            await login_verify_2fa(current_user=USER)
    assert start_error.value.status_code == verify_error.value.status_code == 410
    proxy.assert_not_called()


@pytest.mark.asyncio
async def test_retired_credential_http_routes_do_not_parse_request_bodies():
    app = FastAPI()
    app.include_router(accounts_router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for route in ("login-start", "login-verify-2fa"):
            response = await client.post(
                f"/api/v1/outreach/accounts/{route}",
                content="{invalid-json",
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 410


@pytest.mark.asyncio
async def test_session_connection_http_route_verifies_and_returns_no_secrets(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    monkeypatch.setenv("WEBSHARE_API_KEY", "mock")
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()
    app = FastAPI()
    app.include_router(accounts_router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/outreach/accounts/connect-cookie",
            json={"li_at": "mock_account", "jsession_id": "ajax:private-csrf", "country_code": "US"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert response.json()["workspace_id"] == USER["default_workspace_id"]
    assert all(key not in response.json() for key in ("session_cookie_enc", "li_a_enc", "jsession_id"))
    stored = db.outreach_accounts.insert_one.call_args.args[0]
    assert decrypt_secret(stored["session_cookie_enc"]) == "mock_account"
    assert decrypt_secret(stored["jsession_id"]) == "ajax:private-csrf"


@pytest.mark.asyncio
async def test_cookie_connect_uses_authenticated_workspace_not_payload(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()
    result = await connect_via_cookie(
        ConnectCookieRequest(li_at="mock_workspace_a", workspace_id="workspace_b"), current_user=USER, db=db,
    )
    assert result["workspace_id"] == "workspace_a"
    assert db.outreach_accounts.insert_one.call_args.args[0]["workspace_id"] == "workspace_a"


@pytest.mark.asyncio
async def test_cookie_connect_encrypts_csrf_cookie_at_rest(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()
    result = await connect_via_cookie(
        ConnectCookieRequest(li_at="mock_workspace_a", jsession_id="ajax:private-csrf"),
        current_user=USER, db=db,
    )
    stored = db.outreach_accounts.insert_one.call_args.args[0]
    assert stored["jsession_id"] != "ajax:private-csrf"
    assert decrypt_secret(stored["jsession_id"]) == "ajax:private-csrf"
    assert "jsession_id" not in result


@pytest.mark.asyncio
async def test_live_cookie_connect_rejects_missing_csrf_before_proxy_allocation(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    with patch("outreach.api.accounts.JITProxyManager") as proxy:
        with pytest.raises(HTTPException) as error:
            await connect_via_cookie(
                ConnectCookieRequest(li_at="AQsession-value", jsession_id=""),
                current_user=USER, db=MagicMock(),
            )
    assert error.value.status_code == 400
    proxy.assert_not_called()


def test_voyager_decrypts_new_csrf_cookie_and_accepts_legacy_plaintext(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    encrypted = encrypt_secret("ajax:private-csrf")
    client = VoyagerClient(encrypt_secret("mock_sender"), jsession_id=encrypted)
    legacy = VoyagerClient(encrypt_secret("mock_sender"), jsession_id="ajax:legacy")
    assert client._get_headers()["Csrf-Token"] == "ajax:private-csrf"
    assert legacy._get_headers()["Csrf-Token"] == "ajax:legacy"


@pytest.mark.asyncio
async def test_cookie_connect_releases_new_proxy_if_account_save_fails(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    monkeypatch.setenv("WEBSHARE_API_KEY", "mock")
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock(side_effect=RuntimeError("database unavailable"))
    with patch("outreach.api.accounts.JITProxyManager.release_proxy", new_callable=AsyncMock) as release_proxy:
        release_proxy.return_value = True
        with pytest.raises(RuntimeError):
            await connect_via_cookie(ConnectCookieRequest(li_at="mock_cookie"), current_user=USER, db=db)
        release_proxy.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_list_is_workspace_scoped_and_does_not_return_secrets():
    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{
        "id": "account_a", "workspace_id": "workspace_a", "session_cookie_enc": "secret",
        "encrypted_session_cookie": "legacy-secret", "li_a_enc": "another-secret",
    }])
    db.outreach_accounts.find.return_value = cursor
    result = await list_outreach_accounts(current_user=USER, db=db)
    assert db.outreach_accounts.find.call_args.args[0] == {"workspace_id": "workspace_a"}
    assert not any(key in result[0] for key in ("session_cookie_enc", "encrypted_session_cookie", "li_a_enc"))


@pytest.mark.asyncio
async def test_disconnect_pauses_sender_before_releasing_proxy_and_keeps_retry_path():
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "account_a", "workspace_id": "workspace_a", "status": "active",
        "proxy": {"proxy_id": "proxy_a"},
    })
    operations = []
    db.outreach_accounts.update_one = AsyncMock(side_effect=lambda *args: operations.append("deactivate"))
    db.outreach_campaigns.update_many = AsyncMock(side_effect=lambda *args: operations.append("pause"))
    db.outreach_tasks.update_many = AsyncMock(side_effect=lambda *args: operations.append("cancel"))
    db.outreach_accounts.delete_one = AsyncMock()
    with patch("outreach.api.accounts.JITProxyManager") as manager:
        manager.return_value.release_proxy = AsyncMock(side_effect=lambda *args: operations.append("release") or False)
        with pytest.raises(HTTPException) as exc:
            await disconnect_account("account_a", current_user=USER, db=db)
    assert exc.value.status_code == 502
    assert operations == ["deactivate", "pause", "cancel", "release"]
    db.outreach_accounts.delete_one.assert_not_called()


@pytest.mark.asyncio
async def test_launch_rejects_active_campaign_before_changing_anything():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "active",
    })
    with pytest.raises(HTTPException) as exc:
        await launch_campaign("campaign_a", req=LaunchCampaignRequest(), current_user=USER, db=db)
    assert exc.value.status_code == 409
    db.outreach_campaigns.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_launch_rejects_sender_without_verified_session():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "draft",
        "sender_account_ids": ["account_a"],
    })
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{
        "id": "account_a", "workspace_id": "workspace_a", "status": "active",
    }])
    db.outreach_accounts.find.return_value = cursor
    with pytest.raises(HTTPException) as exc:
        await launch_campaign("campaign_a", req=LaunchCampaignRequest(), current_user=USER, db=db)
    assert exc.value.status_code == 400
    assert db.outreach_accounts.find.call_args.args[0]["workspace_id"] == "workspace_a"


@pytest.mark.asyncio
async def test_launch_rejects_legacy_mock_cookie_even_with_proxy(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "draft",
        "sender_account_ids": ["account_a"],
    })
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{
        "id": "account_a", "workspace_id": "workspace_a", "status": "active",
        "session_cookie_enc": encrypt_secret("mock_old_session"),
        "jsession_id": "ajax:123", "proxy": {"host": "198.51.100.3"},
    }])
    db.outreach_accounts.find.return_value = cursor
    with pytest.raises(HTTPException) as exc:
        await launch_campaign("campaign_a", req=LaunchCampaignRequest(), current_user=USER, db=db)
    assert exc.value.status_code == 400
    db.outreach_campaigns.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_sequence_save_cannot_change_an_active_campaign():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "active",
    })
    request = SaveSequenceRequest(campaign_id="campaign_a", nodes=[{"id": "one", "type": "visit_profile"}], edges=[])
    with pytest.raises(HTTPException) as exc:
        await save_campaign_sequence(request, current_user=USER, db=db)
    assert exc.value.status_code == 409
    assert db.outreach_campaigns.find_one.call_args.args[0]["workspace_id"] == "workspace_a"
    db.outreach_sequences.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_sequence_save_rejects_tree_that_does_not_match_execution_nodes():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "draft",
    })
    request = SaveSequenceRequest(
        campaign_id="campaign_a", nodes=[{"id": "one", "type": "visit_profile"}], edges=[],
        tree=[{"id": "different", "type": "visit_profile"}],
    )
    with pytest.raises(HTTPException) as exc:
        await save_campaign_sequence(request, current_user=USER, db=db)
    assert exc.value.status_code == 400
    db.outreach_sequences.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_launch_never_activates_without_a_sequence_root():
    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "campaign_a", "workspace_id": "workspace_a", "status": "draft",
        "sender_account_ids": ["account_a"], "schedule": {}, "limits": {},
    })
    sender_cursor = MagicMock()
    sender_cursor.to_list = AsyncMock(return_value=[{
        "id": "account_a", "workspace_id": "workspace_a", "status": "active",
        "session_cookie_enc": "encrypted", "proxy": {"host": "198.51.100.5"},
    }])
    db.outreach_accounts.find.return_value = sender_cursor
    db.outreach_sequences.find_one = AsyncMock(return_value=None)
    db.outreach_leads.count_documents = AsyncMock(return_value=1)
    with patch("outreach.api.campaigns.OutboundRateLimiter.has_valid_working_window", return_value=True), \
         patch("outreach.api.campaigns.DAGCompiler.get_prebuilt_templates", return_value=[]):
        with pytest.raises(HTTPException) as exc:
            await launch_campaign("campaign_a", req=LaunchCampaignRequest(), current_user=USER, db=db)
    assert exc.value.status_code == 400
    db.outreach_campaigns.update_one.assert_not_called()
