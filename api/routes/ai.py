"""
AI content generation — /ai/generate-content.
Uses the Emergent LLM gateway (EMERGENT_LLM_KEY) to produce platform-tailored captions.
Rate-limited to prevent abuse.
"""
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from api.deps import CurrentUser
from api.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])


# ── Platform-specific system prompt suffixes ──────────────────────────────────

_PLATFORM_HINTS: dict[str, str] = {
    "twitter":   " Keep it under 280 characters for Twitter/X.",
    "linkedin":  " Make it professional and insight-driven for LinkedIn.",
    "instagram": " Make it engaging for Instagram with 3–5 relevant hashtags.",
    "facebook":  " Write in a conversational tone suitable for Facebook.",
    "tiktok":    " Write a short, punchy caption with trending language for TikTok.",
    "youtube":   " Write a concise, keyword-rich description for YouTube.",
}

_SYSTEM_MESSAGE_BASE = (
    "You are a social media content expert. "
    "Generate engaging, brand-safe social media posts. "
    "Return only the post text — no explanations or meta-commentary."
)


# ── Request / response models ─────────────────────────────────────────────────

class AIContentRequest(BaseModel):
    prompt: str
    platform: str | None = None  # e.g. "instagram", "twitter"
    tone: str | None = None       # e.g. "professional", "casual", "humorous"


class AIContentResponse(BaseModel):
    content: str
    platform: str | None = None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/ai/generate-content", response_model=AIContentResponse)
@limiter.limit("20/minute")
async def generate_content(
    request: Request,
    body: AIContentRequest,
    current_user: CurrentUser,
) -> AIContentResponse:
    """
    Generate platform-tailored social media content using the Emergent LLM gateway.
    Requires EMERGENT_LLM_KEY environment variable.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured",
        )

    if not body.prompt or not body.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Prompt cannot be empty",
        )

    # Build system message
    platform_hint = _PLATFORM_HINTS.get(body.platform or "", "")
    tone_hint = f" Use a {body.tone} tone." if body.tone else ""
    system_message = f"{_SYSTEM_MESSAGE_BASE}{platform_hint}{tone_hint}"

    user_id = current_user["user_id"]

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

        session_id = f"content-gen-{user_id}-{uuid.uuid4()}"
        chat = (
            LlmChat(
                api_key=api_key,
                session_id=session_id,
                system_message=system_message,
            )
            .with_model("openai", "gpt-4o-mini")
        )

        user_message = UserMessage(text=body.prompt.strip())
        response = await chat.send_message(user_message)

    except Exception as exc:
        logger.error("AI generation error user=%s platform=%s: %s", user_id, body.platform, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content generation failed. Please try again.",
        ) from exc

    logger.info("AI content generated: user=%s platform=%s", user_id, body.platform)
    return AIContentResponse(content=response, platform=body.platform)
