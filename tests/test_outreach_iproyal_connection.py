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
async def test_managed_sender_readiness_rejects_proxy_reserved_for_other_workspace(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from outreach.core.paid_access import sender_is_ready
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    now = datetime.now(timezone.utc)
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "workspace_a", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": now + timedelta(days=30),
    })
    db.outreach_proxy_leases.find_one = AsyncMock(return_value={
        "_id": "iproyal:one", "workspace_id": "workspace_a", "sender_id": "sender-1",
    })
    db.outreach_proxy_inventory.find_one = AsyncMock(return_value={
        "_id": "iproyal:one", "status": "available", "provider": "iproyal_static",
        "country_code": "IN", "last_workspace_id": "workspace_b",
        "expires_at": now + timedelta(days=30),
    })
    account = {
        "id": "sender-1", "workspace_id": "workspace_a", "status": "active",
        "country_code": "IN", "proxy": {"proxy_id": "iproyal:one"},
    }
    assert await sender_is_ready(db, "workspace_a", account) is False


def test_corrupt_stored_proxy_credentials_fail_closed():
    with pytest.raises(ProxyProvisioningError, match="credentials"):
        JITProxyManager.format_proxy_url({
            "host": "191.116.125.248", "port": 12323,
            "username": "pilot", "password_enc": "not-encrypted",
        })
