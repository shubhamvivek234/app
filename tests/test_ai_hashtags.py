import pytest

from api.routes import ai as ai_route


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": "#alpha #beta #gamma #delta #epsilon #zeta"
                    }
                }
            ]
        }


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_ai_waterfall_falls_through_when_google_sdk_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_AI_KEY", "google-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.setattr(ai_route.httpx, "AsyncClient", _FakeAsyncClient)

    text, provider, model = await ai_route._ai_waterfall(
        "Return hashtags only.",
        "Generate 6 hashtags for a coffee launch.",
    )

    assert provider == "openrouter"
    assert model == "openai/gpt-oss-120b:free"
    assert "#alpha" in text
