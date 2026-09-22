"""
Phase 6: ElevenLabs Instant Voice Cloning & Dynamic Audio Personalization Pipeline.
Allows users to clone their voice from a 30s audio sample and synthesize customized
voice notes with lead tokens ({{first_name}}, {{company_name}}).
"""
import os
import io
import uuid
import math
import struct
import wave
import logging
import httpx
from typing import Any
from outreach.core.dag_compiler import interpolate_template

logger = logging.getLogger(__name__)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


def generate_mock_voice_wav(duration_s: float = 1.5, sample_rate: int = 16000) -> bytes:
    """
    Generates a valid, browser-playable 16-bit PCM WAV audio sample simulating voice tone.
    Guarantees that mock previews produce real audible sound in all web browsers.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        n_samples = int(duration_s * sample_rate)
        frames = []
        for i in range(n_samples):
            t = i / sample_rate
            env = min(t / 0.08, 1.0) * min((duration_s - t) / 0.15, 1.0)
            pitch = 220.0 + 35.0 * math.sin(2 * math.pi * 2.5 * t)
            sample_val = int(
                env * 14000.0 * (0.65 * math.sin(2 * math.pi * pitch * t) + 0.35 * math.sin(4 * math.pi * pitch * t))
            )
            frames.append(struct.pack("<h", max(-32767, min(32767, sample_val))))
        wav.writeframes(b"".join(frames))
    return buf.getvalue()


class VoiceCloningError(Exception):
    pass


class VoiceCloner:
    """
    Manages ElevenLabs Instant Voice Cloning and dynamic audio note synthesis.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "mock")
        self.is_mock = self.api_key in ("mock", "test", "")

    async def create_voice_clone(self, audio_bytes: bytes, voice_name: str, filename: str = "sample.wav") -> str:
        """
        Submits a 30-second audio recording to ElevenLabs and returns the created voice_id.
        """
        if self.is_mock:
            mock_voice_id = f"voice_mock_{uuid.uuid4().hex[:10]}"
            logger.info("VoiceCloner [MOCK]: Created mock voice clone '%s' -> %s", voice_name, mock_voice_id)
            return mock_voice_id

        headers = {"xi-api-key": self.api_key}
        files = {"files": (filename, audio_bytes, "audio/wav")}
        data = {
            "name": voice_name,
            "description": "Cloned via Unravler LinkedIn Outreach Voice Studio",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{ELEVENLABS_API_URL}/voices/add", headers=headers, data=data, files=files)
                if resp.status_code not in (200, 201):
                    logger.error("ElevenLabs create voice failed: %s %s", resp.status_code, resp.text)
                    raise VoiceCloningError(f"ElevenLabs returned status {resp.status_code}")

                voice_id = resp.json().get("voice_id")
                logger.info("VoiceCloner: Successfully created ElevenLabs voice_id=%s", voice_id)
                return str(voice_id)
        except Exception as exc:
            logger.exception("Error during voice cloning: %s", exc)
            raise VoiceCloningError(f"Voice clone generation failed: {exc}") from exc

    async def synthesize_voice_note(
        self,
        voice_id: str,
        template_text: str,
        lead: dict[str, Any],
    ) -> bytes:
        """
        Interpolates lead variables and synthesizes a personalized audio note.
        """
        personalized_script = interpolate_template(template_text, lead)

        if self.is_mock or voice_id.startswith("voice_mock_"):
            logger.info("VoiceCloner [MOCK]: Synthesizing audio for '%s': %s", voice_id, personalized_script[:50])
            return generate_mock_voice_wav()

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": personalized_script,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    return resp.content
                logger.error("Synthesis failed: %s %s", resp.status_code, resp.text)
                raise VoiceCloningError(f"Speech synthesis error: {resp.status_code}")
        except Exception as exc:
            logger.error("Failed to synthesize voice note: %s", exc)
            raise VoiceCloningError(f"Speech synthesis failed: {exc}") from exc

    async def delete_voice_clone(self, voice_id: str) -> bool:
        """Removes voice clone from ElevenLabs account."""
        if self.is_mock or voice_id.startswith("voice_mock_"):
            logger.info("VoiceCloner [MOCK]: Deleted voice_id=%s", voice_id)
            return True

        headers = {"xi-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(f"{ELEVENLABS_API_URL}/voices/{voice_id}", headers=headers)
                return resp.status_code in (200, 204)
        except Exception as exc:
            logger.error("Failed to delete ElevenLabs voice %s: %s", voice_id, exc)
            return False
