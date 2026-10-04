"""Provider protocol checks use MockTransport; no remote network or credits."""
import io
import json
import wave

import httpx
import pytest

from outreach.core.content_approval import sequence_binding
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_policy import MAX_PCM_BYTES, pcm_to_wav, validate_audio
from outreach.core.voice_provider import generate_campaign_voice
from tests.test_outreach_voice_preparation import voice_db


class RawStream(httpx.AsyncByteStream):
    def __init__(self, body): self.body = body
    async def __aiter__(self): yield self.body


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr("outreach.core.voice_provider.httpx.AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_provider_uses_exact_rendered_script_fixed_model_and_pcm_output(voice_db, monkeypatch):
    binding = await sequence_binding(voice_db, "w", "l")
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, headers={"Content-Type": "audio/pcm"}, stream=RawStream(bytes(32000)))
    mock_client(monkeypatch, respond)
    audio = await generate_campaign_voice(binding)
    assert validate_audio(audio)["duration_ms"] == 1000
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST" and request.url.host == "api.elevenlabs.io"
    assert request.url.params["output_format"] == "pcm_16000"
    assert request.url.path.endswith("/voice1")
    assert json.loads(request.content) == {"text": binding["content"]["body"], "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "status", "redirect", "type", "empty", "oversize", "odd"])
async def test_provider_failure_is_sanitized_and_has_no_retry(voice_db, monkeypatch, failure):
    seen = []
    def respond(request):
        seen.append(request)
        if failure == "timeout": raise httpx.ReadTimeout("private provider detail", request=request)
        if failure == "status": return httpx.Response(429, text="private provider detail")
        if failure == "redirect": return httpx.Response(302, headers={"location": "https://external.invalid"})
        body = b"" if failure == "empty" else bytes(MAX_PCM_BYTES + 2) if failure == "oversize" else bytes(3) if failure == "odd" else bytes(32000)
        return httpx.Response(200, headers={"Content-Type": "text/html" if failure == "type" else "audio/pcm"}, stream=RawStream(body))
    mock_client(monkeypatch, respond)
    with pytest.raises(ValueError, match="outcome needs review") as error:
        await generate_campaign_voice(await sequence_binding(voice_db, "w", "l"))
    assert "private" not in str(error.value)
    assert len(seen) == 1


@pytest.mark.parametrize("audio", [b"RIFF-bogus", b"", generate_mock_voice_wav()[:-5], generate_mock_voice_wav(sample_rate=8000)])
def test_audio_validation_rejects_prefix_only_truncation_and_wrong_rate(audio):
    with pytest.raises(ValueError): validate_audio(audio)


def test_pcm_size_and_wav_channels_are_checked():
    with pytest.raises(ValueError): pcm_to_wav(bytes(MAX_PCM_BYTES + 2))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(bytes(32000))
    with pytest.raises(ValueError): validate_audio(buffer.getvalue())
