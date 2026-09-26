"""Webshare plan selection and sender proxy reservation regressions."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
)
from outreach.models import ProxyConfig
from utils.encryption import decrypt, encrypt


USER = {"user_id": "user_a", "default_workspace_id": "workspace_a"}


def fake_webshare(monkeypatch, handler):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "outreach.core.proxy_manager.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )


@pytest.mark.asyncio
async def test_free_webshare_plan_fails_before_proxy_assignment(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [{
            "id": 1, "status": "active", "proxy_type": "free", "proxy_subtype": "default",
        }], "next": None})

    fake_webshare(monkeypatch, handler)
    with pytest.raises(ProxyPlanRequiredError, match="Dedicated Static Residential"):
        await JITProxyManager(api_key="test-live-key").order_static_residential_proxy("US")

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v2/subscription/plan/"


@pytest.mark.asyncio
async def test_dedicated_isp_plan_selects_unassigned_country_proxy(monkeypatch):
    paths = []

    def handler(request):
        paths.append(str(request.url))
        if request.url.path.endswith("/subscription/plan/"):
            return httpx.Response(200, json={"results": [{
                "id": 42, "status": "active", "proxy_type": "dedicated", "proxy_subtype": "isp",
                "automatic_refresh_frequency": 0,
            }], "next": None})
        assert request.url.params["mode"] == "direct"
        assert request.url.params["country_code__in"] == "US"
        assert request.url.params["plan_id"] == "42"
        return httpx.Response(200, json={"results": [
            {"id": "d-1", "valid": True, "country_code": "US", "proxy_address": "1.2.3.4",
             "port": 8080, "username": "first", "password": "firstpass"},
            {"id": "d-2", "valid": True, "country_code": "US", "proxy_address": "5.6.7.8",
             "port": 8081, "username": "second", "password": "pa:ss@word"},
        ], "next": None})

    fake_webshare(monkeypatch, handler)
    manager = JITProxyManager(api_key="test-live-key")
    proxy = await manager.order_static_residential_proxy("US", {"webshare:42:d-1"})
    assert proxy.proxy_id == "webshare:42:d-2"
    assert proxy.provider == "webshare_plan"
    assert decrypt(proxy.password_enc) == "pa:ss@word"
    assert "pa%3Ass%40word@5.6.7.8:8081" in manager.format_proxy_url(proxy)
    assert len(paths) == 2
    with pytest.raises(ProxyInventoryExhaustedError):
        await manager.order_static_residential_proxy("US", {"webshare:42:d-1", "webshare:42:d-2"})


@pytest.mark.asyncio
async def test_connect_surfaces_missing_webshare_plan_without_saving_cookies(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    db = MagicMock()
    with patch("outreach.api.accounts.JITProxyManager") as manager:
        manager.return_value.is_mock = False
        manager.return_value.order_static_residential_proxy = AsyncMock(
            side_effect=ProxyPlanRequiredError("Webshare has no active Dedicated Static Residential (ISP) plan.")
        )
        with pytest.raises(HTTPException) as error:
            await connect_via_cookie(
                ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private"),
                current_user=USER, db=db,
            )
    assert error.value.status_code == 503
    assert "Dedicated Static Residential" in error.value.detail
    assert "AQprivate" not in error.value.detail
    db.outreach_accounts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_connect_retries_proxy_reservation_collision(monkeypatch):
    monkeypatch.delenv("OUTREACH_MOCK_AUTH", raising=False)
    db = MagicMock()
    db.outreach_proxy_leases.insert_one = AsyncMock(side_effect=[DuplicateKeyError("taken"), None])
    db.outreach_accounts.find_one = AsyncMock(return_value=None)
    db.outreach_accounts.insert_one = AsyncMock()
    first = ProxyConfig(proxy_id="webshare:42:d-1", provider="webshare_plan", host="1.2.3.4",
                        port=8080, username="one", password_enc=encrypt("password"))
    second = ProxyConfig(proxy_id="webshare:42:d-2", provider="webshare_plan", host="5.6.7.8",
                         port=8080, username="two", password_enc=encrypt("password"))

    with patch("outreach.api.accounts.JITProxyManager") as manager, patch(
        "outreach.api.accounts.SessionAuthenticator.validate_session_cookie",
        new_callable=AsyncMock,
    ) as verify:
        manager.return_value.is_mock = False
        manager.return_value.order_static_residential_proxy = AsyncMock(side_effect=[first, second])
        manager.return_value.format_proxy_url.return_value = "http://proxy.test:8080"
        verify.return_value = {"account_name": "Test Sender", "linkedin_urn": "urn:li:person:test"}
        result = await connect_via_cookie(
            ConnectCookieRequest(li_at="AQprivate", jsession_id="ajax:private"),
            current_user=USER, db=db,
        )

    assert result["proxy"]["proxy_id"] == "webshare:42:d-2"
    assert db.outreach_proxy_leases.insert_one.await_count == 2
    assert manager.return_value.order_static_residential_proxy.await_args_list[1].kwargs["excluded_proxy_ids"] == {
        "webshare:42:d-1",
    }
    assert db.outreach_accounts.insert_one.await_count == 1
