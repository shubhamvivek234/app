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
from typing import Any


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
    """Legacy mock helper. Real work requires the durable Studio protocol."""
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv('ELEVENLABS_API_KEY', 'mock')
        self.is_mock = self.api_key in ('mock', 'test', '')

    def _mock_only(self):
        if not self.is_mock:
            raise VoiceCloningError('Real voice operations require a durable Voice Studio job')

    async def create_voice_clone(self, audio_bytes: bytes, voice_name: str, filename: str = 'sample.wav') -> str:
        self._mock_only()
        return f'voice_mock_{uuid.uuid4().hex[:10]}'

    async def synthesize_voice_note(self, voice_id: str, template_text: str, lead: dict[str, Any]) -> bytes:
        self._mock_only()
        return generate_mock_voice_wav()

    async def delete_voice_clone(self, voice_id: str) -> bool:
        self._mock_only()
        return True
