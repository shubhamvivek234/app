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
async def test_managed_pilot_does_not_silently_fall_back_to_webshare():
    """Webshare inventory remains a future adapter, not a paid-pilot fallback."""
    from outreach.core.managed_proxy import ManagedProxyUnavailable, reserve_sender_proxy
    db = MagicMock()
    db.outreach_proxy_leases.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_proxy_inventory.find.return_value = cursor
    with pytest.raises(ManagedProxyUnavailable):
        await reserve_sender_proxy(db, "workspace-a", "sender-a", "US")
    assert db.outreach_proxy_inventory.find.call_args.args[0]["provider"] == "iproyal_static"
