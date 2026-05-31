from unittest.mock import AsyncMock

import pytest

from platform_adapters.tiktok import TikTokAdapter


class _FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.headers = headers or {}

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


class _FakeStreamResponse:
    def __init__(self, status_code, chunks):
        self.status_code = status_code
        self._chunks = list(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _PublishAsyncClient:
    def __init__(self, *, head_response, init_response, upload_response, media_chunks):
        self._head_response = head_response
        self._init_response = init_response
        self._upload_response = upload_response
        self._media_chunks = list(media_chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def head(self, *args, **kwargs):
        return self._head_response

    async def post(self, *args, **kwargs):
        return self._init_response

    def stream(self, *args, **kwargs):
        return _FakeStreamResponse(200, self._media_chunks)

    async def put(self, *args, **kwargs):
        return self._upload_response


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


@pytest.mark.asyncio
async def test_tiktok_publish_does_not_use_local_rate_limiter(monkeypatch):
    monkeypatch.setattr("platform_adapters.tiktok._require_tiktok_enabled", lambda: None)
    monkeypatch.setattr("platform_adapters.tiktok.decrypt", lambda _value: "token")
    monkeypatch.setattr("platform_adapters.tiktok.assert_safe_url", lambda _url: None)
    check_rate_limit_mock = AsyncMock(side_effect=AssertionError("local TikTok rate limiter should not run"))
    monkeypatch.setattr("platform_adapters.tiktok.check_rate_limit", check_rate_limit_mock, raising=False)
    monkeypatch.setattr("platform_adapters.tiktok.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("platform_adapters.tiktok.record_success", AsyncMock(return_value=None))
    monkeypatch.setattr("platform_adapters.tiktok.record_failure", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "platform_adapters.tiktok.httpx.AsyncClient",
        lambda timeout=120: _PublishAsyncClient(
            head_response=_FakeResponse(200, {}, headers={"content-length": "11"}),
            init_response=_FakeResponse(
                200,
                {
                    "data": {"publish_id": "publish-1", "upload_url": "https://upload.example/video"},
                    "error": {"code": "ok", "message": ""},
                },
            ),
            upload_response=_FakeResponse(200, {}),
            media_chunks=[b"video-bytes"],
        ),
    )

    post = {
        "id": "post-1",
        "media_url": "https://media.example/video.mp4",
        "effective_title": "TikTok clip",
        "account": {"id": "tiktok-account-1", "access_token": "encrypted"},
    }

    result = await TikTokAdapter().publish(post, redis=object())

    assert result == {
        "post_url": "",
        "platform_post_id": "publish-1",
        "status": "processing",
    }
    check_rate_limit_mock.assert_not_awaited()
