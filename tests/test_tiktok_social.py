import pytest

from backend.app.social.tiktok import TikTokAuth


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _CapturingAsyncClient:
    def __init__(self, response, calls):
        self._response = response
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        return self._response


@pytest.mark.asyncio
async def test_tiktok_fetch_posts_requests_required_fields_and_normalizes_response(monkeypatch):
    calls = []
    response = _FakeResponse(
        200,
        {
            "data": {
                "videos": [
                    {
                        "id": "video-1",
                        "title": "",
                        "video_description": "From TikTok description",
                        "create_time": 1717200000,
                        "cover_image_url": "https://cdn.example/video-1.jpg",
                        "share_url": "https://www.tiktok.com/@tok/video/1",
                        "like_count": 14,
                        "comment_count": 3,
                        "share_count": 2,
                        "view_count": 190,
                    }
                ]
            },
            "error": {"code": "ok", "message": ""},
        },
    )
    monkeypatch.setattr(
        "backend.app.social.tiktok.httpx.AsyncClient",
        lambda: _CapturingAsyncClient(response, calls),
    )

    posts = await TikTokAuth().fetch_posts("access-token", limit=25)

    assert len(posts) == 1
    assert posts[0]["platform_post_id"] == "video-1"
    assert posts[0]["content"] == "From TikTok description"
    assert posts[0]["post_url"] == "https://www.tiktok.com/@tok/video/1"
    assert posts[0]["metrics"]["views"] == 190
    assert posts[0]["published_at"] is not None

    _, kwargs = calls[0]
    assert kwargs["params"]["fields"] == TikTokAuth.VIDEO_LIST_FIELDS
    assert kwargs["json"] == {"max_count": 25}


@pytest.mark.asyncio
async def test_tiktok_fetch_posts_returns_empty_list_on_api_error(monkeypatch):
    monkeypatch.setattr(
        "backend.app.social.tiktok.httpx.AsyncClient",
        lambda: _CapturingAsyncClient(
            _FakeResponse(
                200,
                {"error": {"code": "scope_not_authorized", "message": "video.list not granted"}},
            ),
            [],
        ),
    )

    posts = await TikTokAuth().fetch_posts("access-token")

    assert posts == []
