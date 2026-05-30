from unittest.mock import AsyncMock

import pytest

from platform_adapters.tiktok import TikTokAdapter


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.headers = {}

    def json(self):
        return self._payload


class _QueuedAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_tiktok_check_status_maps_publish_complete(monkeypatch):
    monkeypatch.setattr(
        "platform_adapters.tiktok.httpx.AsyncClient",
        lambda timeout=15: _QueuedAsyncClient([
            _FakeResponse(
                200,
                {
                    "data": {"status": "PUBLISH_COMPLETE"},
                    "error": {"code": "ok", "message": ""},
                },
            )
        ]),
    )

    status = await TikTokAdapter().check_status("publish-1", access_token="token")

    assert status == "published"


@pytest.mark.asyncio
async def test_tiktok_check_status_maps_failed(monkeypatch):
    monkeypatch.setattr(
        "platform_adapters.tiktok.httpx.AsyncClient",
        lambda timeout=15: _QueuedAsyncClient([
            _FakeResponse(
                200,
                {
                    "data": {"status": "FAILED", "fail_reason": "picture_size_check_failed"},
                    "error": {"code": "ok", "message": ""},
                },
            )
        ]),
    )

    status = await TikTokAdapter().check_status("publish-1", access_token="token")

    assert status == "failed"


@pytest.mark.asyncio
async def test_tiktok_check_status_maps_inbox_delivered_to_pending(monkeypatch):
    monkeypatch.setattr(
        "platform_adapters.tiktok.httpx.AsyncClient",
        lambda timeout=15: _QueuedAsyncClient([
            _FakeResponse(
                200,
                {
                    "data": {"status": "SEND_TO_USER_INBOX"},
                    "error": {"code": "ok", "message": ""},
                },
            )
        ]),
    )

    status = await TikTokAdapter().check_status("publish-1", access_token="token")

    assert status == "pending"
