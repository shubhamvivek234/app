"""
AI generation routes used by the active modular FastAPI app.

Supports:
- /ai/generate-content
- /ai/generate-hashtags

Provider order:
1. Gemini 2.0 Flash Lite
2. Groq LLaMA 3.3 70B Versatile
3. Cohere Command R
4. OpenRouter Gemma 3 12B free
5. Emergent fallback via gpt-4o-mini
"""
import logging
import os
import re
import uuid

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


def _build_system_message(platform: str | None, tone: str | None) -> str:
    platform_hint = _PLATFORM_HINTS.get((platform or "").lower(), "")
    tone_hint = f" Use a {tone} tone." if tone else ""
    return f"{_CONTENT_BASE}{platform_hint}{tone_hint}"


async def _ai_waterfall(system_message: str, prompt: str) -> tuple[str, str, str]:
    rate_limit_errors: list[str] = []

    google_key = os.environ.get("GOOGLE_AI_KEY")
    if google_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=google_key)
            model_name = "gemini-2.0-flash-lite"
            model = genai.GenerativeModel(model_name, system_instruction=system_message)
            result = model.generate_content(prompt)
            text = getattr(result, "text", None)
            if not text:
                raise RuntimeError("Gemini returned empty content")
            return text, "google", model_name
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("[AI waterfall] Gemini rate-limited: %s", exc)
                rate_limit_errors.append(f"Gemini: {exc}")
            else:
                logger.exception("[AI waterfall] Gemini failed")

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
            text = resp.choices[0].message.content
            if not text:
                raise RuntimeError("Groq returned empty content")
            return text, "groq", model_name
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("[AI waterfall] Groq rate-limited: %s", exc)
                rate_limit_errors.append(f"Groq: {exc}")
            else:
                logger.exception("[AI waterfall] Groq failed")

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
            text = resp.message.content[0].text
            if not text:
                raise RuntimeError("Cohere returned empty content")
            return text, "cohere", model_name
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("[AI waterfall] Cohere rate-limited: %s", exc)
                rate_limit_errors.append(f"Cohere: {exc}")
            else:
                logger.exception("[AI waterfall] Cohere failed")

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            model_name = "google/gemma-3-12b:free"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://app.unravler.com",
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
                if resp.status_code == 429:
                    raise HTTPException(status_code=429, detail="OpenRouter rate-limited")
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
                if not text:
                    raise RuntimeError("OpenRouter returned empty content")
                return text, "openrouter", model_name
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("[AI waterfall] OpenRouter rate-limited: %s", exc)
                rate_limit_errors.append(f"OpenRouter: {exc}")
            else:
                logger.exception("[AI waterfall] OpenRouter failed")

    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if emergent_key:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

            model_provider = "emergent-openai"
            model_name = "gpt-4o-mini"
            chat = LlmChat(
                api_key=emergent_key,
                session_id=f"content-gen-{uuid.uuid4()}",
                system_message=system_message,
            ).with_model("openai", model_name)
            text = await chat.send_message(UserMessage(text=prompt))
            if not text:
                raise RuntimeError("Emergent returned empty content")
            return text, model_provider, model_name
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("[AI waterfall] Emergent rate-limited: %s", exc)
                rate_limit_errors.append(f"Emergent: {exc}")
            else:
                logger.exception("[AI waterfall] Emergent failed")

    if rate_limit_errors:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"All AI providers are rate-limited. Details: {'; '.join(rate_limit_errors)}",
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
            _build_system_message(body.platform, body.tone),
            body.prompt.strip(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "AI content generation failed user=%s platform=%s error=%s",
            current_user["user_id"],
            body.platform,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content generation failed. Please try again.",
        ) from exc

    logger.info(
        "AI content generated user=%s platform=%s provider=%s model=%s",
        current_user["user_id"],
        body.platform,
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
