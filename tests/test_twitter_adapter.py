from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from platform_adapters.twitter import TwitterAdapter


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


class _DummyStreamResponse:
    def __init__(self, body: bytes, status_code: int = 200):
        self.status_code = status_code
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        yield self._body


class _DummyClient:
    def __init__(self):
        self.status_calls = 0
        self.append_calls = 0
        self.init_data = None

    async def head(self, media_url: str, follow_redirects: bool = True):
        return _DummyResponse(
            200,
            headers={
                "content-length": "4",
                "content-type": "video/mp4",
            },
        )

    def stream(self, method: str, media_url: str, follow_redirects: bool = False):
        assert method == "GET"
        assert follow_redirects is True
        return _DummyStreamResponse(b"test")

    async def post(self, endpoint: str, headers: dict, data: dict, files: dict | None = None):
        command = data["command"]
        if command == "INIT":
            self.init_data = data
            return _DummyResponse(202, {"media_id_string": "media-123"})
        if command == "APPEND":
            self.append_calls += 1
            return _DummyResponse(204, {})
        if command == "FINALIZE":
            return _DummyResponse(
                201,
                {
                    "media_id_string": "media-123",
                    "processing_info": {
                        "state": "pending",
                        "check_after_secs": 0,
                    },
                },
            )
        raise AssertionError(f"Unexpected command: {command}")

    async def get(self, endpoint: str, headers: dict, params: dict):
        assert params["command"] == "STATUS"
        self.status_calls += 1
        if self.status_calls == 1:
            return _DummyResponse(
                200,
                {
                    "processing_info": {
                        "state": "in_progress",
                        "check_after_secs": 0,
                    }
                },
            )
        return _DummyResponse(
            200,
            {
                "processing_info": {
                    "state": "succeeded",
                }
            },
        )


def test_twitter_adapter_waits_for_media_processing_before_returning_media_id():
    client = _DummyClient()

    with patch("platform_adapters.twitter.assert_safe_url"), patch(
        "platform_adapters.twitter.asyncio.sleep",
        new=AsyncMock(),
    ):
        adapter = TwitterAdapter()
        media_ids = asyncio.run(
            adapter._upload_media(
                client,
                {"Authorization": "Bearer token"},
                "https://media.unravler.com/video.mp4",
            )
        )

    assert media_ids == ["media-123"]
    assert client.append_calls == 1
    assert client.status_calls == 2
    assert client.init_data["media_category"] == "tweet_video"
