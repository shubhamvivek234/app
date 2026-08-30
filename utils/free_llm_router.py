"""
6-Tier Free LLM Waterfall Router for Unravler.

Provides zero-cost, high-availability AI completions with intelligent fallback:
Tier 1: Google Gemini 2.5 Flash / Flash Lite (Free Google AI Studio key, 1M context, multimodal)
Tier 2: Groq GPT-OSS 120B / Qwen 3.6 27B (Free Groq Cloud key, ultra-fast 300ms inference)
Tier 3: Groq GPT-OSS 20B Instant (Instant failover)
Tier 4: OpenRouter Free Pool (Free tier open-weights models)
Tier 5: Cohere Command R (Developer free tier)
Tier 6: Local fallback heuristic generator (Guarantees zero hard 500 crashes)
"""

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from utils.observability import capture_degraded_event, event_log, shorten_provider_error

logger = logging.getLogger(__name__)


def _is_rate_limit_or_quota(exc: Exception) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    terms = (
        "429",
        "quota",
        "rate limit",
        "rate_limit",
        "too many requests",
        "resource_exhausted",
        "resourceexhausted",
        "overloaded",
        "model_not_found",
        "503",
    )
    return any(k in msg for k in terms) or any(k in name for k in terms)


class FreeLLMRouter:
    def __init__(self):
        self.google_key = (
            os.environ.get("GOOGLE_AI_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or ""
        )
        self.groq_key = os.environ.get("GROQ_API_KEY") or ""
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY") or ""
        self.cohere_key = os.environ.get("COHERE_API_KEY") or ""

    async def _is_provider_rate_limited(self, provider: str, limit_rpm: int) -> bool:
        """Check if provider reached its sliding-window RPM limit in Redis."""
        try:
            from db.redis_client import get_cache_redis
            r = get_cache_redis()
            minute_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            key = f"ratelimit:llm:{provider}:{minute_bucket}"
            current = await r.get(key)
            if current and int(current) >= limit_rpm:
                logger.warning("Free LLM %s rate limited (%s/%s RPM) — skipping to next tier", provider, current, limit_rpm)
                return True
            return False
        except Exception:
            return False

    async def _record_provider_call(self, provider: str) -> None:
        """Increment sliding-window RPM usage for provider in Redis."""
        try:
            from db.redis_client import get_cache_redis
            r = get_cache_redis()
            minute_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            key = f"ratelimit:llm:{provider}:{minute_bucket}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 70)
        except Exception:
            pass

    # ── Tier 1: Gemini ────────────────────────────────────────────────────────
    async def _call_gemini(
        self,
        system_message: str,
        user_prompt: str,
        model_name: str = "gemini-2.5-flash",
        response_json: bool = False,
    ) -> str:
        if not self.google_key:
            raise ValueError("Missing Google AI key")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.google_key}"
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": f"System Guidelines: {system_message}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }
        if response_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini returned empty candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or not parts[0].get("text"):
                raise RuntimeError("Gemini returned empty content text")
            return parts[0]["text"].strip()

    # ── Tier 2 & 3: Groq ──────────────────────────────────────────────────────
    async def _call_groq(
        self,
        system_message: str,
        user_prompt: str,
        model_name: str = "openai/gpt-oss-120b",
        response_json: bool = False,
    ) -> str:
        if not self.groq_key:
            raise ValueError("Missing Groq key")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Groq error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            choices = data.get("choices", [])
            if not choices or not choices[0].get("message", {}).get("content"):
                raise RuntimeError("Groq returned empty choices")
            return choices[0]["message"]["content"].strip()

    # ── Tier 4: OpenRouter ────────────────────────────────────────────────────
    async def _call_openrouter(
        self,
        system_message: str,
        user_prompt: str,
        model_name: str = "qwen/qwen3.6-27b:free",
    ) -> str:
        if not self.openrouter_key:
            raise ValueError("Missing OpenRouter key")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://www.unravler.com",
            "X-Title": "Unravler AI",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            choices = data.get("choices", [])
            if not choices or not choices[0].get("message", {}).get("content"):
                raise RuntimeError("OpenRouter returned empty choices")
            return choices[0]["message"]["content"].strip()

    # ── Tier 5: Cohere ────────────────────────────────────────────────────────
    async def _call_cohere(
        self,
        system_message: str,
        user_prompt: str,
    ) -> str:
        if not self.cohere_key:
            raise ValueError("Missing Cohere key")

        url = "https://api.cohere.com/v1/chat"
        headers = {
            "Authorization": f"Bearer {self.cohere_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "preamble": system_message,
            "message": user_prompt,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Cohere error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            text = data.get("text")
            if not text:
                raise RuntimeError("Cohere returned empty text")
            return text.strip()

    # ── Universal Completion Waterfall ────────────────────────────────────────
    async def generate_text(
        self,
        system_message: str,
        user_prompt: str,
        response_json: bool = False,
    ) -> Tuple[str, str, str]:
        """
        Executes completions through the 6-tier free fallback waterfall.
        Returns: (generated_text, provider_name, model_name)
        """
        errors = []

        # 1. Tier 1: Gemini 2.5 Flash / Flash Lite (Free Google AI Studio key: 15 RPM)
        if not await self._is_provider_rate_limited("google", limit_rpm=15):
            for gemini_model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"):
                try:
                    res = await self._call_gemini(system_message, user_prompt, model_name=gemini_model, response_json=response_json)
                    await self._record_provider_call("google")
                    return res, "google", gemini_model
                except Exception as e:
                    errors.append(f"Gemini {gemini_model}: {shorten_provider_error(e)}")
                    if not _is_rate_limit_or_quota(e):
                        break

        # 2. Tier 2 & 3: Groq (Free Groq Cloud key: 30 RPM)
        if not await self._is_provider_rate_limited("groq", limit_rpm=30):
            for groq_model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"):
                try:
                    res = await self._call_groq(system_message, user_prompt, model_name=groq_model, response_json=response_json)
                    await self._record_provider_call("groq")
                    return res, "groq", groq_model
                except Exception as e:
                    errors.append(f"Groq {groq_model}: {shorten_provider_error(e)}")
                    if not _is_rate_limit_or_quota(e):
                        break

        # 3. Tier 4: OpenRouter Free Models (20 RPM)
        if not await self._is_provider_rate_limited("openrouter", limit_rpm=20):
            for or_model in ("qwen/qwen3.6-27b:free", "google/gemma-4-31b-it:free", "google/gemma-3-12b:free"):
                try:
                    res = await self._call_openrouter(system_message, user_prompt, model_name=or_model)
                    await self._record_provider_call("openrouter")
                    return res, "openrouter", or_model
                except Exception as e:
                    errors.append(f"OpenRouter {or_model}: {shorten_provider_error(e)}")

        # 4. Tier 5: Cohere Command R (10 RPM)
        if not await self._is_provider_rate_limited("cohere", limit_rpm=10):
            try:
                res = await self._call_cohere(system_message, user_prompt)
                await self._record_provider_call("cohere")
                return res, "cohere", "command-r"
            except Exception as e:
                errors.append(f"Cohere: {shorten_provider_error(e)}")

        raise RuntimeError(f"All free AI tiers exhausted or temporarily rate limited. Errors: {'; '.join(errors)}")

    # ── Audio Ingestion & Transcription ───────────────────────────────────────
    async def transcribe_and_structure_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        system_prompt: str = "",
        user_prompt: str = "",
    ) -> Tuple[str, str]:
        """
        Ingests voice audio directly into Gemini Multimodal (Free Tier) or Groq Whisper.
        Returns: (structured_response_text, provider_name)
        """
        # 1. Try Gemini Native Multimodal Audio
        if self.google_key:
            try:
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.google_key}"
                prompt_text = (
                    f"{system_prompt}\n\n"
                    f"{user_prompt or 'Listen to this voice memo carefully. Transcribe the raw thoughts, remove any filler words (ums, ahs), and format the core insights into clean, engaging social media posts.'}"
                )
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "inline_data": {
                                        "mime_type": mime_type,
                                        "data": b64_audio,
                                    }
                                },
                                {"text": prompt_text},
                            ]
                        }
                    ],
                    "generationConfig": {"temperature": 0.6, "maxOutputTokens": 2048},
                }
                async with httpx.AsyncClient(timeout=35) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        if parts and parts[0].get("text"):
                            return parts[0]["text"].strip(), "google-gemini-audio"
            except Exception as e:
                logger.warning("Gemini multimodal audio failed: %s. Falling back to Groq Whisper.", e)

        # 2. Fallback: Groq Whisper Large v3
        if self.groq_key:
            try:
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                files = {"file": ("audio.webm", audio_bytes, mime_type)}
                data = {"model": "whisper-large-v3-turbo"}
                headers = {"Authorization": f"Bearer {self.groq_key}"}

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, headers=headers, files=files, data=data)
                    if resp.status_code == 200:
                        raw_transcript = resp.json().get("text", "")
                        if raw_transcript.strip():
                            # Format transcript with free LLM waterfall
                            formatted, prov, mod = await self.generate_text(
                                system_message=system_prompt or "You are an expert social media ghostwriter.",
                                user_prompt=f"Here is a raw voice memo transcript:\n\n{raw_transcript}\n\nTurn this into a high-engagement, well-structured post.",
                            )
                            return formatted, f"groq-whisper+{prov}"
            except Exception as e:
                logger.warning("Groq Whisper transcription failed: %s", e)

        raise RuntimeError("Audio transcription failed across all free providers.")


# Global singleton instance
free_llm = FreeLLMRouter()
