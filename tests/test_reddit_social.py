import pytest
from backend.app.social.reddit import RedditAuth


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

    async def get(self, *args, **kwargs):
        self._calls.append(("GET", args, kwargs))
        return self._response

    async def post(self, *args, **kwargs):
        self._calls.append(("POST", args, kwargs))
        return self._response


def test_reddit_auth_user_agent_format():
    auth = RedditAuth()
    assert "UnravlerApp" in auth.user_agent
    assert auth.user_agent.startswith("web:")


def test_reddit_auth_user_agent_env_override(monkeypatch):
    monkeypatch.setenv("REDDIT_USER_AGENT", "custom-agent:v2.0 (by /u/CustomDev)")
    auth = RedditAuth()
    assert auth.user_agent == "custom-agent:v2.0 (by /u/CustomDev)"


@pytest.mark.asyncio
async def test_reddit_requests_send_user_agent(monkeypatch):
    calls = []
    fake_profile = {"id": "red123", "name": "test_creator"}
    fake_response = _FakeResponse(200, fake_profile)

    monkeypatch.setattr(
        "backend.app.social.reddit.httpx.AsyncClient",
        lambda: _CapturingAsyncClient(fake_response, calls),
    )

    auth = RedditAuth()
    profile = await auth.get_user_profile("test_access_token")

    assert profile["name"] == "test_creator"
    assert len(calls) == 1
    method, args, kwargs = calls[0]
    assert method == "GET"
    assert kwargs["headers"]["User-Agent"] == auth.user_agent
    assert kwargs["headers"]["Authorization"] == "Bearer test_access_token"
