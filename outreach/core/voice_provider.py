"""Single bounded TTS call. No retries, redirects, mock fallback or raw errors."""
import asyncio
from typing import Callable

import httpx

from outreach.core.voice_policy import MAX_PCM_BYTES, VOICE_POLICY, pcm_to_wav, require_configuration
from outreach.core.voice_key_custody import PreparedKey, prepare_key


async def generate_campaign_voice(binding: dict, *, credential: PreparedKey | None = None,
                                  allowed: Callable[[], bool] | None = None) -> bytes:
    require_configuration(binding)
    credential = credential or await prepare_key(expected_source=binding['context']['voice_provider_source_digest'])
    if not isinstance(credential, PreparedKey) or not credential.matches() or allowed is not None and not allowed():
        raise ValueError('Voice provider configuration changed')
    content = binding["content"]
    payload = {"text": content["body"], "model_id": VOICE_POLICY["model_id"],
        "voice_settings": {"stability": VOICE_POLICY["stability"], "similarity_boost": VOICE_POLICY["similarity_boost"]}}
    try:
        async with asyncio.timeout(30):
            async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
                require_configuration(binding)
                if not credential.matches() or allowed is not None and not allowed():
                    raise ValueError("Voice provider source changed")
                async with client.stream("POST", "https://api.elevenlabs.io/v1/text-to-speech/" + content["voice_id"],
                        params={"output_format": VOICE_POLICY["output_format"]},
                        headers={"xi-api-key": credential.value, "Accept-Encoding": "identity", "Content-Type": "application/json"},
                        json=payload) as response:
                    if response.status_code != 200:
                        raise ValueError("Voice provider did not return a usable recording")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("Encoded voice response is unavailable")
                    media = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if media not in {"audio/pcm", "audio/l16", "application/octet-stream"}:
                        raise ValueError("Voice provider returned an unexpected audio format")
                    audio = bytearray()
                    async for part in response.aiter_raw(chunk_size=16384):
                        if len(audio) + len(part) > MAX_PCM_BYTES:
                            raise ValueError("Voice provider recording exceeds the duration limit")
                        audio.extend(part)
        return pcm_to_wav(bytes(audio))
    except (httpx.HTTPError, TimeoutError, ValueError):
        raise ValueError("Voice generation outcome needs review") from None
