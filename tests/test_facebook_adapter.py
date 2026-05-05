from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from platform_adapters.facebook import FacebookAdapter


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _DummyClient:
    def __init__(self, calls: list[dict], response: _DummyResponse):
        self._calls = calls
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, endpoint: str, data: dict, headers: dict):
        self._calls.append(
            {
                "endpoint": endpoint,
                "data": data,
                "headers": headers,
            }
        )
        return self._response


@pytest.mark.parametrize(
    ("post", "expected_suffix", "expected_payload_key"),
    [
        (
            {
                "id": "post-text",
                "post_type": "text",
                "content": "hello",
                "account": {"access_token": "encrypted-token", "platform_user_id": "page-1"},
            },
            "/page-1/feed",
            "message",
        ),
        (
            {
                "id": "post-image",
                "post_type": "image",
                "content": "hello image",
                "media_url": "https://media.unravler.com/image.png",
                "account": {"access_token": "encrypted-token", "platform_user_id": "page-1"},
            },
            "/page-1/photos",
            "url",
        ),
        (
            {
                "id": "post-video",
                "post_type": "video",
                "content": "hello video",
                "media_url": "https://media.unravler.com/video.mp4",
                "account": {"access_token": "encrypted-token", "platform_user_id": "page-1"},
            },
            "/page-1/videos",
            "file_url",
        ),
    ],
)
def test_facebook_adapter_selects_correct_publish_endpoint(post, expected_suffix, expected_payload_key):
    calls: list[dict] = []
    response = _DummyResponse(200, {"id": "fb-post-123"})

    with patch("platform_adapters.facebook.decrypt", return_value="page-token"), patch(
        "platform_adapters.facebook.httpx.AsyncClient",
        return_value=_DummyClient(calls, response),
    ):
        adapter = FacebookAdapter()
        result = asyncio.run(adapter.publish(post))

    assert result["platform_post_id"] == "fb-post-123"
    assert len(calls) == 1
    assert calls[0]["endpoint"].endswith(expected_suffix)
    assert calls[0]["data"]["access_token"] == "page-token"
    assert expected_payload_key in calls[0]["data"]
