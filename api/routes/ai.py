"""
AI generation routes used by the active modular FastAPI app.

Supports:
- /ai/generate-content
- /ai/generate-hashtags

Provider order:
1. Gemini 2.0 Flash Lite
2. Groq LLaMA 3.3 70B Versatile
3. OpenRouter free models
4. Cohere Command R
"""
import logging
import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser
from api.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])

_CONTENT_BASE = (
    "You are a social media content expert. Generate engaging, brand-safe posts. "
    "Return only the post text with no explanations or meta-commentary."
)

_PLATFORM_HINTS: dict[str, str] = {
    "twitter": " Keep it under 280 characters for Twitter/X.",
    "linkedin": " Make it professional and insight-driven for LinkedIn.",
    "instagram": " Make it engaging for Instagram with 3-5 relevant hashtags.",
    "facebook": " Write in a conversational tone suitable for Facebook.",
    "tiktok": " Write a short, punchy caption with trending language for TikTok.",
    "youtube": " Write a concise, keyword-rich description for YouTube.",
    "bluesky": " Keep it concise and thoughtful for Bluesky.",
    "discord": " Write casually, like a community update in Discord.",
}


class AIContentRequest(BaseModel):
    prompt: str
    platform: str | None = None
    tone: str | None = None
    language: str | None = None


class AIContentResponse(BaseModel):
    content: str
    platform: str | None = None
    provider: str | None = None
    model: str | None = None


class HashtagGenerateRequest(BaseModel):
    topic: str
    platform: str | None = None
    count: int = Field(default=20, ge=1, le=30)


class HashtagGenerateResponse(BaseModel):
    hashtags: list[str]
    provider: str | None = None
    model: str | None = None


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "429" in msg
        or "quota" in msg
        or "rate limit" in msg
        or "too many requests" in msg
        or "resource_exhausted" in msg
        or type(exc).__name__ in ("ResourceExhausted", "RateLimitError")
    )


def _build_system_message(platform: str | None, tone: str | None, language: str | None) -> str:
    platform_hint = _PLATFORM_HINTS.get((platform or "").lower(), "")
    tone_hint = f" Use a {tone} tone." if tone else ""
    language_hint = ""
    if language and language.strip():
        language_hint = (
            f" Write the final post in {language.strip()}. "
            "Use natural, fluent phrasing for that language and script. "
            "Do not mention translation or provide alternatives."
        )
    return f"{_CONTENT_BASE}{platform_hint}{tone_hint}{language_hint}"


async def _ai_waterfall(system_message: str, prompt: str) -> tuple[str, str, str]:
    provider_errors: list[str] = []

    def _record_provider_error(provider: str, exc: Exception) -> None:
        detail = str(exc).replace("\n", " ").strip()
        if len(detail) > 220:
            detail = detail[:217] + "..."
        provider_errors.append(f"{provider}: {type(exc).__name__}: {detail}")

    def _ensure_text(provider: str, text: str | None) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            raise RuntimeError(f"{provider} returned empty content")
        return cleaned

    google_key = os.environ.get("GOOGLE_AI_KEY")
    if google_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=google_key)
            model_name = "gemini-2.0-flash-lite"
            model = genai.GenerativeModel(model_name, system_instruction=system_message)
            result = model.generate_content(prompt)
            text = _ensure_text("Gemini", getattr(result, "text", None))
            return text, "google", model_name
        except Exception as exc:
            logger.warning("[AI waterfall] Gemini failed: %s", exc)
            _record_provider_error("Gemini", exc)

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import AsyncGroq  # type: ignore

            model_name = "llama-3.3-70b-versatile"
            client = AsyncGroq(api_key=groq_key)
            resp = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
            )
            text = _ensure_text("Groq", resp.choices[0].message.content)
            return text, "groq", model_name
        except Exception as exc:
            logger.warning("[AI waterfall] Groq failed: %s", exc)
            _record_provider_error("Groq", exc)

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        async def _call_openrouter(model_name: str) -> tuple[str, str, str]:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://www.unravler.com",
                        "X-Title": "Unravler AI",
                    },
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                resp.raise_for_status()
                text = _ensure_text(
                    f"OpenRouter {model_name}",
                    resp.json()["choices"][0]["message"]["content"],
                )
                return text, "openrouter", model_name

        for model_name in (
            "openai/gpt-oss-120b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-4-31b-it:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "google/gemma-3-12b:free",
        ):
            try:
                return await _call_openrouter(model_name)
            except Exception as exc:
                logger.warning("[AI waterfall] OpenRouter %s failed: %s", model_name, exc)
                _record_provider_error(f"OpenRouter/{model_name}", exc)

    cohere_key = os.environ.get("COHERE_API_KEY")
    if cohere_key:
        try:
            import cohere  # type: ignore

            model_name = "command-r"
            client = cohere.AsyncClientV2(api_key=cohere_key)
            resp = await client.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
            )
            text = ""
            if getattr(resp, "message", None) and getattr(resp.message, "content", None):
                first_item = resp.message.content[0]
                text = getattr(first_item, "text", "") or ""
            text = _ensure_text("Cohere", text)
            return text, "cohere", model_name
        except Exception as exc:
            logger.warning("[AI waterfall] Cohere failed: %s", exc)
            _record_provider_error("Cohere", exc)

    if provider_errors:
        detail = "; ".join(provider_errors)
        if any("429" in err or "quota" in err.lower() or "rate" in err.lower() for err in provider_errors):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"All configured AI providers failed or were rate-limited. Details: {detail}",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"All configured AI providers failed. Details: {detail}",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No AI provider configured",
    )


@router.post("/ai/generate-content", response_model=AIContentResponse)
@limiter.limit("20/minute")
async def generate_content(
    request: Request,
    body: AIContentRequest,
    current_user: CurrentUser,
) -> AIContentResponse:
    if not body.prompt or not body.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Prompt cannot be empty",
        )

    try:
        content, provider, model = await _ai_waterfall(
            _build_system_message(body.platform, body.tone, body.language),
            body.prompt.strip(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "AI content generation failed user=%s platform=%s language=%s error=%s",
            current_user["user_id"],
            body.platform,
            body.language,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content generation failed. Please try again.",
        ) from exc

    logger.info(
        "AI content generated user=%s platform=%s language=%s provider=%s model=%s",
        current_user["user_id"],
        body.platform,
        body.language,
        provider,
        model,
    )
    return AIContentResponse(
        content=content,
        platform=body.platform,
        provider=provider,
        model=model,
    )


@router.post("/ai/generate-hashtags", response_model=HashtagGenerateResponse)
@limiter.limit("20/minute")
async def generate_hashtags(
    request: Request,
    body: HashtagGenerateRequest,
    current_user: CurrentUser,
) -> HashtagGenerateResponse:
    if not body.topic or not body.topic.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Topic cannot be empty",
        )

    count = max(5, min(30, body.count))
    platform_hint = f" optimized for {body.platform}" if body.platform else ""
    system_message = (
        "You are a social media hashtag expert. "
        f"Return ONLY a plain list of {count} relevant, trending hashtags{platform_hint}. "
        "Format: space-separated on one line, each starting with #. "
        "No explanations, no numbering, no bullet points, no extra text."
    )
    user_prompt = f"Generate {count} hashtags for a post about: {body.topic.strip()}"

    try:
        raw, provider, model = await _ai_waterfall(system_message, user_prompt)
        hashtags = re.findall(r"#\w+", raw)[:count]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "AI hashtag generation failed user=%s platform=%s error=%s",
            current_user["user_id"],
            body.platform,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI hashtag generation failed. Please try again.",
        ) from exc

    if not hashtags:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI hashtag generation returned no hashtags",
        )

    logger.info(
        "AI hashtags generated user=%s platform=%s provider=%s model=%s count=%s",
        current_user["user_id"],
        body.platform,
        provider,
        model,
        len(hashtags),
    )
    return HashtagGenerateResponse(
        hashtags=hashtags,
        provider=provider,
        model=model,
    )
