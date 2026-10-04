"""Versioned campaign voice generation and bounded PCM WAV validation."""
import io
import os
import re
import wave

from outreach.core.authorization import canonical_hash

VOICE_POLICY = {"version": 1, "model_id": "eleven_turbo_v2_5", "output_format": "pcm_16000",
    "sample_rate": 16000, "stability": 0.5, "similarity_boost": 0.8,
    "max_script_chars": 1000, "max_seconds": 60, "daily_clips": 20, "daily_chars": 20000}
VOICE_POLICY_DIGEST = canonical_hash(VOICE_POLICY)
MAX_PCM_BYTES = VOICE_POLICY["sample_rate"] * 2 * VOICE_POLICY["max_seconds"]


def preparation_enabled() -> bool:
    return os.getenv("OUTREACH_VOICE_PREPARATION_ENABLED", "false").strip().lower() in {"true", "1"}


def require_configuration(binding: dict) -> None:
    """Never silently synthesize a mock recording in the paid preparation path."""
    voice = binding["content"].get("voice_id", "")
    body = binding["content"].get("body", "")
    if not preparation_enabled():
        raise ValueError("Campaign voice preparation is disabled")
    if not isinstance(voice, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", voice) or voice.startswith("voice_mock_"):
        raise ValueError("Select a real workspace voice profile before preparing")
    if not isinstance(body, str) or not body.strip() or len(body) > VOICE_POLICY["max_script_chars"]:
        raise ValueError("Voice script must contain 1–1000 finished characters")
    from outreach.core.voice_studio import source_digest
    if binding["context"].get("voice_provider_source_digest") != source_digest():
        raise ValueError("Voice provider source changed")
    if binding["context"].get("voice_policy_digest") != VOICE_POLICY_DIGEST:
        raise ValueError("Voice preparation policy changed")


def pcm_to_wav(pcm: bytes) -> bytes:
    if not isinstance(pcm, bytes) or not 0 < len(pcm) <= MAX_PCM_BYTES or len(pcm) % 2:
        raise ValueError("Voice audio is outside the preparation limits")
    result = io.BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(VOICE_POLICY["sample_rate"])
        output.writeframes(pcm)
    return result.getvalue()


def validate_audio(audio: bytes) -> dict:
    """Validate actual decoded length; a RIFF prefix alone is not audio evidence."""
    if not isinstance(audio, bytes) or not 44 < len(audio) <= MAX_PCM_BYTES + 44:
        raise ValueError("Prepared voice audio is invalid")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            frames = source.getnframes()
            if (source.getnchannels() != 1 or source.getsampwidth() != 2
                    or source.getframerate() != VOICE_POLICY["sample_rate"]
                    or source.getcomptype() != "NONE" or not 0 < frames <= MAX_PCM_BYTES // 2
                    or len(source.readframes(frames)) != frames * 2):
                raise ValueError("Prepared voice audio is outside the preparation limits")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Prepared voice audio is invalid") from exc
    return {"media_type": "audio/wav", "duration_ms": frames * 1000 // VOICE_POLICY["sample_rate"],
            "sample_rate": VOICE_POLICY["sample_rate"]}
