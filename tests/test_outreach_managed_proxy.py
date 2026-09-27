"""Managed proxy inventory never silently switches country or customer."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.core.managed_proxy import (
    ManagedProxyUnavailable, import_iproyal_proxy, reserve_sender_proxy,
)
from outreach.core.proxy_manager import JITProxyManager
from outreach.models import ProxyConfig, ProxyStatus


NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
PROXY = "http://pilot:secret@191.116.125.248:12323"


@pytest.mark.asyncio
async def test_real_ip_health_is_not_bypassed_by_mock_webshare_key(monkeypatch):
    monkeypatch.setenv("OUTREACH_PROXY_PROVIDER", "webshare")
    manager = JITProxyManager(api_key="mock")
    real_ip = ProxyConfig(
        proxy_id="iproyal:one", provider="iproyal_static", host="191.116.125.248",
        port=12323, username="pilot", password_enc="encrypted", country_code="IN",
        status=ProxyStatus.HEALTHY, assigned_at=NOW,
    )
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(manager, "format_proxy_url", lambda proxy: "http://pilot:secret@191.116.125.248:12323")
        patcher.setattr("outreach.core.proxy_manager.httpx.AsyncClient", lambda **kw: (_ for _ in ()).throw(RuntimeError("health attempted")))
        assert await manager.test_proxy_health(real_ip) is False


@pytest.mark.asyncio
async def test_operator_import_encrypts_credentials_and_records_provider_term():
    db = MagicMock()
    db.outreach_proxy_inventory.insert_one = AsyncMock()
    result = await import_iproyal_proxy(
        db, PROXY, "IN", "order-123", "workspace-a", NOW + timedelta(days=30), now=NOW,
    )
    assert result["provider"] == "iproyal_static"
    assert result["country_code"] == "IN"
    saved = db.outreach_proxy_inventory.insert_one.await_args.args[0]
    assert saved["password_enc"] != "secret"
    assert "secret" not in str(result)
    assert saved["provider_order_id"] == "order-123"


@pytest.mark.asyncio
async def test_inventory_rejects_private_proxy_ip():
    with pytest.raises(ValueError, match="public static IP"):
        await import_iproyal_proxy(
            MagicMock(), "http://u:p@127.0.0.1:8888", "IN", "order-1", "workspace-a",
            NOW + timedelta(days=30), now=NOW,
        )


@pytest.mark.asyncio
async def test_reservation_is_sender_specific_and_keeps_original_customer():
    db = MagicMock()
    candidate = {
        "_id": "iproyal:1", "provider": "iproyal_static", "host": "191.116.125.248",
        "port": 12323, "username": "pilot", "password_enc": "encrypted",
        "country_code": "IN", "status": "available", "expires_at": NOW + timedelta(days=30),
    }
    db.outreach_proxy_inventory.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[candidate])))
    db.outreach_proxy_inventory.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_proxy_leases.insert_one = AsyncMock()
    db.outreach_proxy_leases.find_one = AsyncMock(return_value=None)
    proxy = await reserve_sender_proxy(db, "workspace-a", "sender-a", "IN", now=NOW)
    assert proxy.proxy_id == "iproyal:1"
    lease = db.outreach_proxy_leases.insert_one.await_args.args[0]
    assert lease["sender_id"] == "sender-a"
    assert lease["workspace_id"] == "workspace-a"
    assert db.outreach_proxy_inventory.update_one.await_args.args[1]["$set"]["last_workspace_id"] == "workspace-a"


@pytest.mark.asyncio
async def test_no_inventory_or_duplicate_lease_fails_without_fallback():
    db = MagicMock()
    db.outreach_proxy_leases.find_one = AsyncMock(return_value=None)
    db.outreach_proxy_inventory.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    with pytest.raises(ManagedProxyUnavailable):
        await reserve_sender_proxy(db, "workspace-a", "sender-a", "FR", now=NOW)
    db.outreach_proxy_inventory.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[{
        "_id": "iproyal:1", "country_code": "FR", "expires_at": NOW + timedelta(days=30),
        "provider": "iproyal_static", "status": "available",
    }])))
    db.outreach_proxy_inventory.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_proxy_leases.insert_one = AsyncMock(side_effect=DuplicateKeyError("taken"))
    with pytest.raises(ManagedProxyUnavailable):
        await reserve_sender_proxy(db, "workspace-a", "sender-a", "FR", now=NOW)
