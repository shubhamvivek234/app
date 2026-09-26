"""IPRoyal pilot inventory and one-sender lease regressions."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.api.accounts import ConnectCookieRequest, connect_via_cookie
from outreach.core.proxy_manager import (
    JITProxyManager,
    ProxyInventoryExhaustedError,
    ProxyPlanRequiredError,
    ProxyProvisioningError,
)
from outreach.models import ProxyConfig
from utils.encryption import decrypt, encrypt


PILOT_URL = "http://pilot:pa%3Ass%40word@191.116.125.248:12323"
USER = {"user_id": "user_a", "default_workspace_id": "workspace_a"}


def configure_iproyal(monkeypatch):
    monkeypatch.setenv("OUTREACH_PROXY_PROVIDER", "iproyal")
    monkeypatch.setenv("IPROYAL_PROXY_URL", PILOT_URL)
    monkeypatch.setenv("IPROYAL_PROXY_COUNTRY", "IN")
    monkeypatch.setenv("WEBSHARE_API_KEY", "mock")


@pytest.mark.asyncio
async def test_iproyal_pilot_selects_one_dedicated_ip_without_webshare(monkeypatch):
    configure_iproyal(monkeypatch)
    manager = JITProxyManager()
    assert manager.is_mock is False

    proxy = await manager.order_static_residential_proxy("IN")
    assert proxy.provider == "iproyal_static"
    assert proxy.proxy_id.startswith("iproyal:")
    assert proxy.host == "191.116.125.248"
    assert proxy.port == 12323
    assert proxy.username == "pilot"
    assert decrypt(proxy.password_enc) == "pa:ss@word"
    assert manager.format_proxy_url(proxy) == PILOT_URL

    with pytest.raises(ProxyInventoryExhaustedError, match="already assigned"):
        await manager.order_static_residential_proxy("IN", {proxy.proxy_id})


@pytest.mark.asyncio
async def test_iproyal_country_must_match_purchased_ip(monkeypatch):
    configure_iproyal(monkeypatch)
    with pytest.raises(ProxyInventoryExhaustedError, match="IN"):
        await JITProxyManager().order_static_residential_proxy("US")


@pytest.mark.asyncio
async def test_iproyal_missing_credentials_do_not_fall_back_to_mock_or_webshare(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("IPROYAL_PROXY_URL")
    with pytest.raises(ProxyPlanRequiredError, match="IPRoyal"):
        await JITProxyManager().order_static_residential_proxy("IN")


@pytest.mark.asyncio
@pytest.mark.parametrize("proxy_url", [
    "socks5://pilot:secret@191.116.125.248:12324",
    "http://pilot@191.116.125.248:12323",
    "http://pilot:secret@127.0.0.1:12323",
    "http://pilot:secret@geo.iproyal.com:12323",
    "http://pilot:secret@191.116.125.248:12323/path",
    "http://pilot:secret@191.116.125.248:99999",
])
async def test_iproyal_rejects_non_static_or_incomplete_proxy_configuration(monkeypatch, proxy_url):
    configure_iproyal(monkeypatch)
    monkeypatch.setenv("IPROYAL_PROXY_URL", proxy_url)
    with pytest.raises(ProxyProvisioningError, match="IPRoyal"):
        await JITProxyManager().order_static_residential_proxy("IN")


@pytest.mark.asyncio
async def test_iproyal_pilot_lease_cannot_be_used_by_second_sender(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    manager = JITProxyManager()
    proxy = await manager.order_static_residential_proxy("IN")
    db = MagicMock()
    db.outreach_proxy_leases.insert_one = AsyncMock(side_effect=DuplicateKeyError("taken"))

    with patch("outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock) as verify:
        with pytest.raises(HTTPException) as error:
            await connect_via_cookie(
                ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="IN"),
                current_user=USER,
                db=db,
            )

    assert error.value.status_code == 503
    assert "IPRoyal" in error.value.detail
    assert PILOT_URL not in error.value.detail
    verify.assert_not_called()
    db.outreach_accounts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_iproyal_pilot_connects_one_verified_sender_without_exposing_secrets(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    db = MagicMock()
    db.outreach_proxy_leases.insert_one = AsyncMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()

    with patch("outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock) as verify:
        verify.return_value = {"account_name": "Pilot Sender", "linkedin_urn": "urn:li:person:pilot"}
        result = await connect_via_cookie(
            ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="in"),
            current_user=USER, db=db,
        )

    verify.assert_awaited_once()
    assert verify.await_args.kwargs["proxy_url"] == PILOT_URL
    db.outreach_proxy_leases.insert_one.assert_awaited_once()
    db.outreach_accounts.insert_one.assert_awaited_once()
    saved = db.outreach_accounts.insert_one.await_args.args[0]
    assert saved["proxy"]["provider"] == "iproyal_static"
    assert saved["country_code"] == "IN"
    assert saved["session_cookie_enc"] != "AQprivate"
    assert saved["jsession_id"] != "ajax:private"
    assert "session_cookie_enc" not in result
    assert "jsession_id" not in result
    assert "password_enc" not in result["proxy"]
    assert "username" not in result["proxy"]


@pytest.mark.asyncio
async def test_iproyal_reconnect_reuses_same_sender_lease(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    proxy = await JITProxyManager().order_static_residential_proxy("IN")
    existing = {
        "id": "sender-1", "workspace_id": "workspace_a", "user_id": "user_a",
        "linkedin_urn": "urn:li:person:one", "proxy": proxy.model_dump(),
    }
    updated = {**existing, "account_name": "Sender One"}
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(side_effect=[existing, updated])
    db.outreach_proxy_leases.find_one = AsyncMock(return_value={"_id": proxy.proxy_id, "workspace_id": "workspace_a"})
    db.outreach_accounts.update_one = AsyncMock()

    with patch("outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock) as verify:
        verify.return_value = {"account_name": "Sender One", "linkedin_urn": "urn:li:person:one"}
        result = await connect_via_cookie(
            ConnectCookieRequest(
                li_at="AQnew", jsession_id="ajax:new", country_code="IN",
                reconnect_account_id="sender-1",
            ),
            current_user=USER, db=db,
        )

    assert result["id"] == "sender-1"
    assert "password_enc" not in result["proxy"]
    assert "username" not in result["proxy"]
    db.outreach_proxy_leases.insert_one.assert_not_called()
    db.outreach_accounts.insert_one.assert_not_called()
    db.outreach_accounts.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_iproyal_reconnect_rejects_different_linkedin_identity(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    proxy: ProxyConfig = await JITProxyManager().order_static_residential_proxy("IN")
    existing = {
        "id": "sender-1", "workspace_id": "workspace_a", "user_id": "user_a",
        "linkedin_urn": "urn:li:person:one", "proxy": proxy.model_dump(),
    }
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(return_value=existing)
    db.outreach_proxy_leases.find_one = AsyncMock(return_value={"_id": proxy.proxy_id, "workspace_id": "workspace_a"})

    with patch("outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock) as verify:
        verify.return_value = {"account_name": "Other Sender", "linkedin_urn": "urn:li:person:other"}
        with pytest.raises(HTTPException) as error:
            await connect_via_cookie(
                ConnectCookieRequest(
                    li_at="AQother", jsession_id="ajax:other", country_code="IN",
                    reconnect_account_id="sender-1",
                ),
                current_user=USER, db=db,
            )

    assert error.value.status_code == 400
    db.outreach_accounts.update_one.assert_not_called()
    db.outreach_proxy_leases.insert_one.assert_not_called()


def test_corrupt_stored_proxy_credentials_fail_closed():
    with pytest.raises(ProxyProvisioningError, match="credentials"):
        JITProxyManager.format_proxy_url({
            "host": "191.116.125.248", "port": 12323,
            "username": "pilot", "password_enc": "not-encrypted",
        })


@pytest.mark.asyncio
async def test_proxy_format_failure_releases_new_reservation(monkeypatch):
    configure_iproyal(monkeypatch)
    db = MagicMock()
    db.outreach_proxy_leases.insert_one = AsyncMock()
    db.outreach_proxy_leases.delete_one = AsyncMock()

    with patch("outreach.api.accounts.JITProxyManager.format_proxy_url", side_effect=ProxyProvisioningError("Stored proxy credentials cannot be decrypted")), patch(
        "outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock,
    ) as verify:
        with pytest.raises(HTTPException) as error:
            await connect_via_cookie(
                ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private", country_code="IN"),
                current_user=USER, db=db,
            )

    assert error.value.status_code == 502
    db.outreach_proxy_leases.delete_one.assert_awaited_once()
    verify.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_can_migrate_sender_from_iproyal_to_webshare(monkeypatch):
    configure_iproyal(monkeypatch)
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    old_proxy = await JITProxyManager().order_static_residential_proxy("IN")
    new_proxy = ProxyConfig(
        proxy_id="webshare:42:new", provider="webshare_plan",
        host="8.8.8.8", port=8080, username="webshare",
        password_enc=encrypt("private"), country_code="IN",
    )
    existing = {
        "id": "sender-1", "workspace_id": "workspace_a", "user_id": "user_a",
        "linkedin_urn": "urn:li:person:one", "proxy": old_proxy.model_dump(),
    }
    updated = {**existing, "proxy": new_proxy.model_dump()}
    db = MagicMock()
    db.outreach_accounts.find_one = AsyncMock(side_effect=[existing, updated])
    db.outreach_accounts.update_one = AsyncMock()
    db.outreach_proxy_leases.insert_one = AsyncMock()
    db.outreach_proxy_leases.delete_one = AsyncMock()

    with patch("outreach.api.accounts.JITProxyManager") as factory, patch(
        "outreach.api.accounts.SessionAuthenticator.validate_session_cookie", new_callable=AsyncMock,
    ) as verify:
        manager = factory.return_value
        manager.provider = "webshare"
        manager.is_mock = False
        manager.order_static_residential_proxy = AsyncMock(return_value=new_proxy)
        manager.format_proxy_url.return_value = "http://new.proxy:8080"
        manager.release_proxy = AsyncMock(return_value=True)
        verify.return_value = {"account_name": "Sender One", "linkedin_urn": "urn:li:person:one"}
        result = await connect_via_cookie(
            ConnectCookieRequest(
                li_at="AQnew", jsession_id="ajax:new", country_code="IN",
                reconnect_account_id="sender-1",
            ),
            current_user=USER, db=db,
        )

    assert result["proxy"]["provider"] == "webshare_plan"
    db.outreach_proxy_leases.insert_one.assert_awaited_once()
    db.outreach_proxy_leases.delete_one.assert_awaited_once_with({
        "_id": old_proxy.proxy_id, "workspace_id": "workspace_a",
    })
    manager.release_proxy.assert_awaited_once_with(old_proxy.proxy_id)
