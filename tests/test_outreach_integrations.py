"""Tests for outreach integrations, webhooks, and public REST API."""
import os
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet
import pytest
from httpx import Response

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.core.webhook_dispatcher import dispatch_webhook, sign_payload
from outreach.api.integrations import authenticate_api_key, create_api_key, create_webhook, update_slack_config


def test_experimental_integrations_are_not_published_by_default():
    from outreach.api.router import router

    paths = [route.path for route in router.routes]
    assert not any(path.startswith("/outreach/integrations") for path in paths)
    assert not any(path.startswith("/outreach/public") for path in paths)


@pytest.fixture(autouse=True)
def enable_integrations_for_tests(monkeypatch, request):
    if request.node.name != "test_experimental_integrations_are_not_published_by_default":
        monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")


@pytest.mark.asyncio
async def test_webhook_signing_and_dispatch():
    secret = "whsec_test_secret_123"
    data = {"lead_id": "lead_123", "event": "lead.replied"}
    
    # Test signing
    payload = b'{"hello":"world"}'
    sig = sign_payload(payload, secret)
    assert len(sig) == 64  # SHA256 hex string
    
    # Test SSRF block
    result = await dispatch_webhook("http://127.0.0.1:8000/webhook", secret, "lead.replied", data)
    assert result["success"] is False
    assert "SSRF" in result["error"]


@pytest.mark.asyncio
async def test_webhook_dispatch_success():
    secret = "whsec_test_secret_123"
    data = {"lead_id": "lead_123"}
    
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=Response(200, text="OK"))
    
    with patch("outreach.core.webhook_dispatcher.is_safe_url", return_value=True):
        result = await dispatch_webhook(
            "https://example.com/webhook",
            secret,
            "lead.replied",
            data,
            http_client=mock_client,
        )
    assert result["success"] is True
    assert result["status_code"] == 200
    assert "event_id" in result


@pytest.mark.asyncio
async def test_create_webhook_enforces_ssrf():
    from outreach.api.integrations import CreateWebhookRequest
    from fastapi import HTTPException
    
    db = AsyncMock()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}
    
    # Unsafe URL should raise 400
    with pytest.raises(HTTPException) as exc:
        await create_webhook(
            CreateWebhookRequest(target_url="http://169.254.169.254/latest/meta-data/"),
            current_user=user,
            db=db,
        )
    assert exc.value.status_code == 400
    
    # Safe public URL succeeds
    with patch("outreach.api.integrations.is_safe_url", return_value=True):
        result = await create_webhook(
            CreateWebhookRequest(target_url="https://api.myapp.com/webhooks/unravler"),
            current_user=user,
            db=db,
        )
    assert result["target_url"] == "https://api.myapp.com/webhooks/unravler"
    assert result["secret"].startswith("whsec_")
    assert db.outreach_webhooks.insert_one.await_count == 1


@pytest.mark.asyncio
async def test_api_key_lifecycle():
    from outreach.api.integrations import CreateApiKeyRequest
    from fastapi import HTTPException
    
    db = AsyncMock()
    db.outreach_api_keys.insert_one = AsyncMock()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}
    
    created = await create_api_key(
        CreateApiKeyRequest(name="Zapier Prod Key"),
        current_user=user,
        db=db,
    )
    assert created["api_key"].startswith("unr_live_")
    assert created["key_prefix"].startswith("unr_live_")
    assert created["name"] == "Zapier Prod Key"
    
    # Test authentication
    import hashlib
    key_hash = hashlib.sha256(created["api_key"].encode()).hexdigest()
    db.outreach_api_keys.find_one = AsyncMock(return_value={"_id": "k1", "workspace_id": "ws_1"})
    db.outreach_api_keys.update_one = AsyncMock()
    
    ws_id = await authenticate_api_key(f"Bearer {created['api_key']}", db=db)
    assert ws_id == "ws_1"
    
    # Invalid key raises 401
    db.outreach_api_keys.find_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await authenticate_api_key("Bearer unr_live_invalid", db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_slack_config():
    from outreach.api.integrations import SlackConfigRequest
    
    db = AsyncMock()
    db.outreach_integrations.update_one = AsyncMock()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}
    
    with patch("outreach.api.integrations.is_safe_url", return_value=True):
        res = await update_slack_config(
            SlackConfigRequest(
                webhook_url="https://hooks.slack.com/services/T00/B00/XXXX",
                channel_name="#deals",
            ),
            current_user=user,
            db=db,
        )
    assert res["status"] == "saved"
    assert res["connected"] is True
    assert db.outreach_integrations.update_one.await_count == 1
