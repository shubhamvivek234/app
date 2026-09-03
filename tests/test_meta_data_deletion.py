import base64
import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request

from api.routes.webhooks import (
    _parse_fb_signed_request,
    facebook_data_deletion_callback,
    facebook_deauthorize_callback,
)
from api.routes.user import get_data_deletion_status


def _make_signed_request(payload_dict: dict, secret: str) -> str:
    payload_json = json.dumps(payload_dict)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{sig_b64}.{payload_b64}"


def test_parse_fb_signed_request_valid():
    secret = "test_meta_secret_123"
    data = {"user_id": "fb_12345678", "algorithm": "HMAC-SHA256"}
    signed_req = _make_signed_request(data, secret)
    
    parsed = _parse_fb_signed_request(signed_req, secret)
    assert parsed is not None
    assert parsed.get("user_id") == "fb_12345678"


def test_parse_fb_signed_request_tampered():
    secret = "test_meta_secret_123"
    data = {"user_id": "fb_12345678"}
    signed_req = _make_signed_request(data, "wrong_secret")
    
    parsed = _parse_fb_signed_request(signed_req, secret)
    assert parsed is None


@pytest.mark.asyncio
async def test_facebook_data_deletion_callback_flow():
    secret = "test_meta_secret_123"
    signed_req = _make_signed_request({"user_id": "fb_999888"}, secret)

    # Fake request
    request = MagicMock()
    request.form = AsyncMock(return_value={"signed_request": signed_req})
    request.json = AsyncMock(side_effect=Exception("not json"))

    # Fake DB
    db = MagicMock()
    db.social_accounts.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
    db.data_deletions.update_one = AsyncMock()

    import os
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("META_APP_SECRET", secret)
        resp = await facebook_data_deletion_callback(request, db)

    assert "url" in resp
    assert "confirmation_code" in resp
    assert resp["url"].startswith("https://www.unravler.com/data-deletion?code=")
    db.social_accounts.delete_many.assert_awaited_once()
    db.data_deletions.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_data_deletion_status():
    db = MagicMock()
    code = "abc123code"
    now = datetime.now(timezone.utc)
    db.data_deletions.find_one = AsyncMock(return_value={
        "confirmation_code": code,
        "status": "completed",
        "details": "All tokens purged.",
        "created_at": now,
    })

    request = Request(scope={
        "type": "http",
        "method": "GET",
        "path": "/api/user/data-deletion-status",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    })
    result = await get_data_deletion_status(request, code, db)
    assert result["found"] is True
    assert result["status"] == "completed"
    assert result["confirmation_code"] == code
