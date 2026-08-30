import pytest
from unittest.mock import AsyncMock, patch
from utils.free_llm_router import FreeLLMRouter, _is_rate_limit_or_quota


def test_is_rate_limit_or_quota_detection():
    assert _is_rate_limit_or_quota(Exception("429 Too Many Requests")) is True
    assert _is_rate_limit_or_quota(Exception("Quota exceeded for quota metric")) is True
    assert _is_rate_limit_or_quota(Exception("ResourceExhausted")) is True
    assert _is_rate_limit_or_quota(Exception("Model_not_found")) is True
    assert _is_rate_limit_or_quota(Exception("Unknown internal syntax error")) is False


@pytest.mark.asyncio
async def test_free_llm_router_primary_gemini_success():
    router = FreeLLMRouter()
    with patch.object(router, "_call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = "Hello from Gemini 2.5 Flash"
        text, provider, model = await router.generate_text(
            system_message="You are an assistant",
            user_prompt="Say hi",
        )
        assert text == "Hello from Gemini 2.5 Flash"
        assert provider == "google"
        assert "gemini" in model


@pytest.mark.asyncio
async def test_free_llm_router_fallback_to_groq_on_gemini_quota():
    router = FreeLLMRouter()
    with patch.object(router, "_call_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch.object(router, "_call_groq", new_callable=AsyncMock) as mock_groq:
        mock_gemini.side_effect = Exception("429 ResourceExhausted: Quota exceeded")
        mock_groq.return_value = "Hello from Groq LLaMA 3.3 70B"

        text, provider, model = await router.generate_text(
            system_message="You are an assistant",
            user_prompt="Say hi",
        )
        assert text == "Hello from Groq LLaMA 3.3 70B"
        assert provider == "groq"
        assert mock_gemini.called
        assert mock_groq.called


@pytest.mark.asyncio
async def test_free_llm_router_fallback_to_cohere():
    router = FreeLLMRouter()
    with patch.object(router, "_call_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch.object(router, "_call_groq", new_callable=AsyncMock) as mock_groq, \
         patch.object(router, "_call_openrouter", new_callable=AsyncMock) as mock_openrouter, \
         patch.object(router, "_call_cohere", new_callable=AsyncMock) as mock_cohere:
        mock_gemini.side_effect = Exception("429 ResourceExhausted")
        mock_groq.side_effect = Exception("429 Too Many Requests")
        mock_openrouter.side_effect = Exception("404 Model Not Found")
        mock_cohere.return_value = "Hello from Cohere Command R"

        text, provider, model = await router.generate_text(
            system_message="You are an assistant",
            user_prompt="Say hi",
        )
        assert text == "Hello from Cohere Command R"
        assert provider == "cohere"
        assert model == "command-r"


@pytest.mark.asyncio
async def test_free_llm_router_proactive_redis_rate_limit():
    router = FreeLLMRouter()
    with patch.object(router, "_is_provider_rate_limited", new_callable=AsyncMock) as mock_rate_limit, \
         patch.object(router, "_call_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch.object(router, "_call_groq", new_callable=AsyncMock) as mock_groq:
        # Simulate Gemini being at RPM ceiling in Redis
        mock_rate_limit.side_effect = lambda provider, limit_rpm: provider == "google"
        mock_groq.return_value = "Hello from Groq via proactive skip"

        text, provider, model = await router.generate_text(
            system_message="You are an assistant",
            user_prompt="Say hi",
        )
        assert text == "Hello from Groq via proactive skip"
        assert provider == "groq"
        # Gemini was NOT called because Redis rate limit proactively skipped it
        assert not mock_gemini.called
        assert mock_groq.called
