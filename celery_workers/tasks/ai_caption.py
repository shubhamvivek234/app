"""
Phase 7.5 — AI caption generation via Claude API.
Async Celery task. Result cached in Redis (1h TTL).
Runs pre-publish for content intelligence suggestions.
"""
import asyncio
import hashlib
import json
import logging
import os

import httpx

from celery_workers.celery_app import celery_app
from db.redis_client import get_cache_redis

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600   # 1 hour
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # Fast + cheap for caption generation
_MAX_TOKENS = 512


def _cache_key(prompt_hash: str) -> str:
    return f"ai_caption:{prompt_hash}"


@celery_app.task(
    name="celery_workers.tasks.ai_caption.generate_caption",
    time_limit=60,  # 60s hard limit
    soft_time_limit=45,
)
def generate_caption(
    content_brief: str,
    platform: str,
    tone: str = "professional",
    language: str = "en",
) -> dict:
    """
    Generate a platform-optimized caption for the given content brief.
    Returns {"caption": str, "hashtags": list[str], "cached": bool}.
    Result is cached in Redis by content hash for 1 hour.
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_generate(content_brief, platform, tone, language)
    )


async def _async_generate(
    content_brief: str,
    platform: str,
    tone: str,
    language: str,
) -> dict:
    # Cache lookup
    cache_input = f"{content_brief}|{platform}|{tone}|{language}"
    prompt_hash = hashlib.sha256(cache_input.encode()).hexdigest()[:16]
    cache_key = _cache_key(prompt_hash)

    r = get_cache_redis()
    cached = await r.get(cache_key)
    if cached:
        result = json.loads(cached)
        result["cached"] = True
        return result

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning empty caption")
        return {"caption": "", "hashtags": [], "cached": False}

    # Platform-specific guidance
    platform_guidance = {
        "instagram": "Add 5-10 relevant hashtags. Max 2200 chars. Engaging first line.",
        "twitter": "Max 280 chars including hashtags. Punchy and direct. 1-3 hashtags.",
        "linkedin": "Professional tone. No excessive hashtags. Max 3000 chars.",
        "facebook": "Conversational. Call to action. Max 63206 chars.",
        "tiktok": "Trendy, casual. 3-5 trending hashtags. Max 2200 chars.",
        "youtube": "Include SEO keywords naturally. Max 5000 chars for description.",
    }.get(platform, "Keep it concise and engaging.")

    system_prompt = (
        f"You are a social media content expert. Generate captions optimized for {platform}. "
        f"Tone: {tone}. Language: {language}. {platform_guidance} "
        "Return valid JSON: {\"caption\": \"...\", \"hashtags\": [\"#tag1\", \"#tag2\"]}"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _CLAUDE_MODEL,
                    "max_tokens": _MAX_TOKENS,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": f"Content brief: {content_brief}"}
                    ],
                },
            )

        if resp.status_code != 200:
            logger.warning("Claude API error %d: %s", resp.status_code, resp.text[:200])
            return {"caption": content_brief, "hashtags": [], "cached": False}

        text = resp.json()["content"][0]["text"].strip()

        # Parse JSON response
        try:
            parsed = json.loads(text)
            caption = parsed.get("caption", content_brief)
            hashtags = parsed.get("hashtags", [])
        except json.JSONDecodeError:
            # Fallback: return raw text as caption
            caption = text
            hashtags = []

    except Exception as exc:
        logger.warning("Caption generation failed: %s", exc)
        return {"caption": content_brief, "hashtags": [], "cached": False}

    result = {"caption": caption, "hashtags": hashtags, "cached": False}

    # Cache the result
    await r.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(result))

    return result
