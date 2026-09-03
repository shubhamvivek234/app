"""
AI generation routes used by the active modular FastAPI app.

Supports:
- /ai/generate-content (Standard & Brand Voice copy generator)
- /ai/generate-hashtags (Platform-optimized hashtag extractor)
- /ai/repurpose (Universal YouTube / Web Article / Text to Multi-Network Social Distribution Package)
- /ai/voice-to-post (PostCast Voice Memo Audio to Social Posts)
- /ai/content-dna/scan (1-Click Writing Style & Profile Voice Extraction)
- /ai/suggest-comment (Focus Mode 1-Click Insightful Comment Suggestions)

Powered by the 6-Tier Free LLM Waterfall Router.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB
from api.limiter import limiter
from utils.content_repurposer import extract_content_from_source, repurpose_content_to_social
from utils.free_llm_router import free_llm
from utils.observability import capture_degraded_event, event_log, shorten_provider_error
from api.data.viral_hooks_catalog import VIRAL_HOOKS, CATEGORIES, NICHES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])

_CONTENT_BASE = (
    "You are a social media content expert and ghostwriter. Generate engaging, brand-safe posts. "
    "Return only the post text with no explanations or meta-commentary."
)

_PLATFORM_HINTS: dict[str, str] = {
    "twitter": " Keep it under 280 characters for Twitter/X.",
    "linkedin": " Make it professional and insight-driven for LinkedIn with strong paragraph white-spacing.",
    "instagram": " Make it engaging for Instagram with 3-5 relevant hashtags.",
    "facebook": " Write in a conversational tone suitable for Facebook.",
    "tiktok": " Write a short, punchy caption with trending language for TikTok.",
    "youtube": " Write a concise, keyword-rich description for YouTube.",
    "bluesky": " Keep it concise and thoughtful for Bluesky.",
    "discord": " Write casually, like a community update in Discord.",
    "telegram": " Write a clear broadcast announcement for Telegram channels.",
}


class BrandVoiceConfig(BaseModel):
    brand_name: str | None = None
    tone: str | None = None
    target_audience: str | None = None
    mission: str | None = None
    banned_words: list[str] = Field(default_factory=list)
    formatting_rules: str | None = None
    custom_guidelines: str | None = None
    signature_cta: str | None = None


class AIContentRequest(BaseModel):
    prompt: str
    platform: str | None = None
    tone: str | None = None
    language: str | None = None
    use_brand_voice: bool = True


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


class RepurposeRequest(BaseModel):
    url_or_text: str
    tone: str | None = "engaging"
    use_brand_voice: bool = True


class CarouselSlide(BaseModel):
    slide_num: int
    type: str = "content"
    title: str
    body: str


class RepurposeResponse(BaseModel):
    source_title: str
    linkedin_post: str
    twitter_thread: list[str]
    instagram_caption: str
    carousel_slides: list[CarouselSlide]
    key_takeaways: list[str]
    provider: str | None = None
    model: str | None = None


class VoiceToPostRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    tone: str | None = None
    use_brand_voice: bool = True


class VoiceToPostResponse(BaseModel):
    linkedin_post: str
    twitter_thread: list[str]
    instagram_caption: str
    carousel_slides: list[CarouselSlide] = Field(default_factory=list)
    provider: str | None = None


class ContentDNAScanResponse(BaseModel):
    tone: str
    sentence_cadence: str
    hook_style: str
    emoji_density: str
    vocabulary_tier: str
    sample_hooks: list[str]
    posts_analyzed: int
    content_dna: dict[str, Any]


class SuggestCommentRequest(BaseModel):
    post_content: str
    author_name: str | None = None
    platform: str | None = "linkedin"


class SuggestCommentResponse(BaseModel):
    suggestions: list[str]
    provider: str | None = None


class StoryboardBeat(BaseModel):
    timestamp: str
    stage: str
    visual_cue: str
    on_screen_text: str
    spoken_dialogue: str


class GenerateScriptRequest(BaseModel):
    topic: str
    niche: str | None = "saas_tech"
    platform: str | None = "tiktok"
    target_duration: str | None = "30s"
    hook_style: str | None = "contrarian"
    use_brand_voice: bool = True


class GenerateScriptResponse(BaseModel):
    title: str
    hooks: list[str]
    selected_hook: str
    storyboard: list[StoryboardBeat]
    full_script: str
    call_to_action: str
    recommended_hashtags: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class AutoFillHookRequest(BaseModel):
    hook_template: str
    topic_or_brand: str
    niche: str | None = "saas_tech"


class AutoFillHookResponse(BaseModel):
    variations: list[str]
    provider: str | None = None



def _build_system_message(
    platform: str | None,
    tone: str | None,
    language: str | None,
    brand_voice: dict | None = None,
) -> str:
    platform_hint = _PLATFORM_HINTS.get((platform or "").lower(), "")
    tone_hint = f" Use a {tone} tone." if tone else ""
    language_hint = ""
    if language and language.strip():
        language_hint = (
            f" Write the final post in {language.strip()}. "
            "Use natural, fluent phrasing for that language and script. "
            "Do not mention translation or provide alternatives."
        )

    brand_hint = ""
    if brand_voice:
        b_parts = []
        if brand_voice.get("brand_name"):
            b_parts.append(f"Brand: {brand_voice['brand_name']}.")
        if brand_voice.get("tone"):
            b_parts.append(f"Voice Tone: {brand_voice['tone']}.")
        if brand_voice.get("target_audience"):
            b_parts.append(f"Target Audience: {brand_voice['target_audience']}.")
        if brand_voice.get("mission"):
            b_parts.append(f"Mission: {brand_voice['mission']}.")
        if brand_voice.get("formatting_rules"):
            b_parts.append(f"Style Rules: {brand_voice['formatting_rules']}.")
        if brand_voice.get("custom_guidelines"):
            b_parts.append(f"Guidelines: {brand_voice['custom_guidelines']}.")
        if brand_voice.get("content_dna"):
            dna = brand_voice["content_dna"]
            b_parts.append(f"Content DNA: Tone={dna.get('tone')}, Hook={dna.get('hook_style')}, Cadence={dna.get('sentence_cadence')}.")
        banned = [w.strip() for w in brand_voice.get("banned_words", []) if w and w.strip()]
        if banned:
            b_parts.append(f"NEVER use these words/phrases: {', '.join(banned)}.")
        if brand_voice.get("signature_cta"):
            b_parts.append(f"Always conclude with this signature Call-To-Action (CTA): \"{brand_voice['signature_cta']}\".")
        if b_parts:
            brand_hint = " BRAND VOICE & GUIDELINES: " + " ".join(b_parts)

    return f"{_CONTENT_BASE}{platform_hint}{tone_hint}{brand_hint}{language_hint}"


async def _ai_waterfall(system_message: str, prompt: str) -> tuple[str, str, str]:
    """AI waterfall supporting direct provider fallback and httpx client patching."""
    google_key = os.environ.get("GOOGLE_AI_KEY") or os.environ.get("GOOGLE_API_KEY")
    if google_key and google_key != "google-key":
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_key}"
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    url,
                    json={"contents": [{"parts": [{"text": f"{system_message}\n\n{prompt}"}]}]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    if parts and parts[0].get("text"):
                        return parts[0]["text"].strip(), "google", "gemini-2.5-flash"
        except Exception:
            pass

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": "openai/gpt-oss-120b",
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip(), "groq", "openai/gpt-oss-120b"
        except Exception:
            pass

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        async def _call_openrouter(model_name: str) -> tuple[str, str, str]:
            async with httpx.AsyncClient(timeout=20) as client:
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
                return resp.json()["choices"][0]["message"]["content"].strip(), "openrouter", model_name

        for model_name in (
            "openai/gpt-oss-120b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-4-31b-it:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
        ):
            try:
                return await _call_openrouter(model_name)
            except Exception:
                pass

    cohere_key = os.environ.get("COHERE_API_KEY")
    if cohere_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.cohere.com/v1/chat",
                    headers={"Authorization": f"Bearer {cohere_key}", "Content-Type": "application/json"},
                    json={"preamble": system_message, "message": prompt},
                )
                if resp.status_code == 200:
                    return resp.json().get("text", "").strip(), "cohere", "command-r"
        except Exception:
            pass

    return await free_llm.generate_text(system_message, prompt)


# ── 1. Standard Content Generation ───────────────────────────────────────────

@router.post("/ai/generate-content", response_model=AIContentResponse)
@limiter.limit("30/minute")
async def generate_content(
    request: Request,
    body: AIContentRequest,
    current_user: CurrentUser,
    db: DB,
) -> AIContentResponse:
    if not body.prompt or not body.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Prompt cannot be empty",
        )

    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    brand_voice = None
    if body.use_brand_voice:
        brand_voice = await db.brand_voices.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})

    system_msg = _build_system_message(body.platform, body.tone, body.language, brand_voice=brand_voice)

    try:
        content, provider, model = await free_llm.generate_text(system_msg, body.prompt.strip())
    except Exception as exc:
        event_log(
            logger,
            "error",
            "ai.content.failed",
            exc_info=exc,
            route="/ai/generate-content",
            user_id=current_user["user_id"],
            platform=body.platform,
            provider_error=shorten_provider_error(exc),
            outcome="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content generation failed across all free tiers. Please try again in a moment.",
        ) from exc

    return AIContentResponse(
        content=content,
        platform=body.platform,
        provider=provider,
        model=model,
    )


# ── 2. Hashtags Generator ───────────────────────────────────────────────────

@router.post("/ai/generate-hashtags", response_model=HashtagGenerateResponse)
@limiter.limit("30/minute")
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
        raw, provider, model = await free_llm.generate_text(system_message, user_prompt)
        hashtags = re.findall(r"#\w+", raw)[:count]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI hashtag generation failed. Please try again.",
        ) from exc

    if not hashtags:
        # Fallback generated from topic words
        words = re.findall(r"\w+", body.topic.strip().lower())
        hashtags = [f"#{w}" for w in words[:count]]

    return HashtagGenerateResponse(
        hashtags=hashtags,
        provider=provider,
        model=model,
    )


# ── 3. Universal Content Repurposer (YouTube / Web / PDF / Text) ────────────

@router.post("/ai/repurpose", response_model=RepurposeResponse)
@limiter.limit("20/minute")
async def repurpose_content(
    request: Request,
    body: RepurposeRequest,
    current_user: CurrentUser,
    db: DB,
) -> RepurposeResponse:
    """Repurposes a YouTube link, Article URL, or notes into multi-network social posts."""
    if not body.url_or_text or not body.url_or_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid URL or text to repurpose.",
        )

    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    brand_voice = None
    if body.use_brand_voice:
        brand_voice = await db.brand_voices.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})

    try:
        # 1. Extract source content
        extracted = await extract_content_from_source(body.url_or_text.strip())
        source_title = extracted.get("title") or "Source Content"
        source_text = extracted.get("text") or ""

        if not source_text:
            raise ValueError("No text content could be extracted from the provided source.")

        # 2. Repurpose via Free LLM Waterfall
        result = await repurpose_content_to_social(
            source_text=source_text,
            source_title=source_title,
            tone=body.tone or "engaging",
            brand_voice=brand_voice,
        )

        slides = [
            CarouselSlide(
                slide_num=s.get("slide_num", i + 1),
                type=s.get("type", "content"),
                title=s.get("title", f"Point {i+1}"),
                body=s.get("body", ""),
            )
            for i, s in enumerate(result.get("carousel_slides", []))
        ]

        return RepurposeResponse(
            source_title=source_title,
            linkedin_post=result.get("linkedin_post", ""),
            twitter_thread=result.get("twitter_thread", []),
            instagram_caption=result.get("instagram_caption", ""),
            carousel_slides=slides,
            key_takeaways=result.get("key_takeaways", []),
            provider=result.get("provider"),
            model=result.get("model"),
        )
    except Exception as exc:
        logger.error("Repurposing failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content repurposing failed: {shorten_provider_error(exc)}",
        ) from exc


# ── 4. "PostCast" Voice-to-Post Studio ──────────────────────────────────────

@router.post("/ai/voice-to-post", response_model=VoiceToPostResponse)
@limiter.limit("20/minute")
async def voice_to_post(
    request: Request,
    body: VoiceToPostRequest,
    current_user: CurrentUser,
    db: DB,
) -> VoiceToPostResponse:
    """Takes a raw voice note audio recording and writes polished, platform-tailored social drafts."""
    if not body.audio_base64:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Audio recording is required.",
        )

    try:
        audio_bytes = base64.b64decode(body.audio_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 audio encoding.",
        ) from exc

    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    brand_voice = None
    if body.use_brand_voice:
        brand_voice = await db.brand_voices.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})

    system_prompt = (
        "You are an elite executive ghostwriter. "
        "The user is speaking their raw ideas, lessons, or stream-of-consciousness thoughts in this voice memo.\n"
        "1. Remove all disfluencies (ums, ahs, repetitions, stuttering).\n"
        "2. Extract the core insight and convert it into a structured LinkedIn post, a 3-5 tweet X thread, and an Instagram story caption.\n"
        "Return ONLY a JSON object: {\n"
        '  "linkedin_post": "...",\n'
        '  "twitter_thread": ["Tweet 1", "Tweet 2", "Tweet 3"],\n'
        '  "instagram_caption": "..."\n'
        "}"
    )

    try:
        structured_text, provider = await free_llm.transcribe_and_structure_audio(
            audio_bytes=audio_bytes,
            mime_type=body.mime_type or "audio/webm",
            system_prompt=system_prompt,
        )

        cleaned = structured_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)

        data = json.loads(cleaned)
        return VoiceToPostResponse(
            linkedin_post=data.get("linkedin_post", structured_text),
            twitter_thread=data.get("twitter_thread", [structured_text[:270]]),
            instagram_caption=data.get("instagram_caption", structured_text[:500]),
            carousel_slides=[],
            provider=provider,
        )
    except Exception as exc:
        logger.error("Voice-to-post failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice-to-post processing failed: {shorten_provider_error(exc)}",
        ) from exc


# ── 5. Content DNA & Writing Style Profiler ─────────────────────────────────

@router.post("/ai/content-dna/scan", response_model=ContentDNAScanResponse)
@limiter.limit("10/minute")
async def scan_content_dna(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> ContentDNAScanResponse:
    """Scans the user's published posts to extract their unique writing style & Content DNA."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    # Find last 20 published posts
    cursor = db.posts.find(
        {"user_id": user_id, "status": "published", "content": {"$exists": True, "$ne": ""}}
    ).sort("created_at", -1).limit(20)
    posts = await cursor.to_list(length=20)

    if len(posts) < 3:
        # Fallback to general posts or drafts if few published posts
        cursor = db.posts.find(
            {"user_id": user_id, "content": {"$exists": True, "$ne": ""}}
        ).sort("created_at", -1).limit(20)
        posts = await cursor.to_list(length=20)

    sample_texts = [p.get("content", "") for p in posts if p.get("content")]
    if not sample_texts:
        # Default starter DNA profile
        default_dna = {
            "tone": "Direct & Authoritative",
            "sentence_cadence": "Short, punchy 1-2 sentence paragraphs",
            "hook_style": "Contrarian / Problem Statement",
            "emoji_density": "Minimal (1-2 per post)",
            "vocabulary_tier": "Clear B2B executive phrasing",
            "sample_hooks": [
                "Most founders get this completely backward:",
                "Here is the simple framework we used to scale:",
            ],
        }
        await db.brand_voices.update_one(
            {"user_id": user_id},
            {"$set": {"content_dna": default_dna, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return ContentDNAScanResponse(
            **default_dna,
            posts_analyzed=0,
            content_dna=default_dna,
        )

    joined_samples = "\n---\n".join(sample_texts[:15])

    system_prompt = (
        "You are an expert linguistic analyst. Analyze these sample social media posts written by the user. "
        "Extract their exact writing style DNA.\n"
        "Return ONLY a JSON object with this exact structure:\n"
        "{\n"
        '  "tone": "2-4 adjectives (e.g. Punchy, Analytical, Conversational)",\n'
        '  "sentence_cadence": "Sentence length and paragraph break habits",\n'
        '  "hook_style": "How they start their posts (e.g. Questions, Contrarian, Stories)",\n'
        '  "emoji_density": "None / Minimal / Moderate / Heavy",\n'
        '  "vocabulary_tier": "Conversational / B2B Executive / Technical / Storyteller",\n'
        '  "sample_hooks": ["Hook example 1", "Hook example 2"]\n'
        "}"
    )

    try:
        raw_res, provider, model = await free_llm.generate_text(
            system_message=system_prompt,
            user_prompt=f"Sample Posts:\n{joined_samples[:7000]}",
            response_json=True,
        )
        cleaned = raw_res.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
        dna_data = json.loads(cleaned)

        # Store in brand_voices
        await db.brand_voices.update_one(
            {"user_id": user_id},
            {"$set": {"content_dna": dna_data, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

        return ContentDNAScanResponse(
            tone=dna_data.get("tone", "Authentic & Insightful"),
            sentence_cadence=dna_data.get("sentence_cadence", "Short paragraphs"),
            hook_style=dna_data.get("hook_style", "Curiosity hook"),
            emoji_density=dna_data.get("emoji_density", "Minimal"),
            vocabulary_tier=dna_data.get("vocabulary_tier", "B2B Professional"),
            sample_hooks=dna_data.get("sample_hooks", []),
            posts_analyzed=len(sample_texts),
            content_dna=dna_data,
        )
    except Exception as exc:
        logger.error("Content DNA scan failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content DNA scan failed: {shorten_provider_error(exc)}",
        ) from exc


# ── 6. Focus Mode AI Comment Assistant ──────────────────────────────────────

@router.post("/ai/suggest-comment", response_model=SuggestCommentResponse)
@limiter.limit("30/minute")
async def suggest_comment(
    request: Request,
    body: SuggestCommentRequest,
    current_user: CurrentUser,
    db: DB,
) -> SuggestCommentResponse:
    """Generates 3 insightful, context-aware comment replies for Focus Mode engagement."""
    if not body.post_content or not body.post_content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Post content is required to generate comment suggestions.",
        )

    user_id = current_user["user_id"]
    brand_voice = await db.brand_voices.find_one({"user_id": user_id})
    dna = (brand_voice or {}).get("content_dna", {})

    system_prompt = (
        "You are an active LinkedIn & Twitter industry expert. "
        "Generate 3 distinct, thoughtful, value-add comment replies to the provided post. "
        "Avoid generic bot phrases like 'Great post!', 'Thanks for sharing!', or 'Totally agree!'. "
        "Provide:\n"
        "1. Option 1: An insightful addition / supporting insight\n"
        "2. Option 2: A respectful contrarian / nuanced angle\n"
        "3. Option 3: A high-value follow-up question to spark conversation\n\n"
        f"Author Tone DNA: {dna.get('tone', 'Smart and professional')}\n\n"
        "Return ONLY a JSON array of 3 string comments: [\"Comment 1\", \"Comment 2\", \"Comment 3\"]"
    )

    try:
        raw_res, provider, model = await free_llm.generate_text(
            system_message=system_prompt,
            user_prompt=f"Target Post by {body.author_name or 'Creator'}:\n{body.post_content[:2000]}",
            response_json=True,
        )
        cleaned = raw_res.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)

        comments = json.loads(cleaned)
        if isinstance(comments, dict) and "suggestions" in comments:
            comments = comments["suggestions"]
        if not isinstance(comments, list):
            comments = [str(comments)]

        return SuggestCommentResponse(
            suggestions=comments[:3],
            provider=provider,
        )
    except Exception as exc:
        logger.error("Comment suggestion failed: %s", exc)
        return SuggestCommentResponse(
            suggestions=[
                "Strong perspective. The biggest differentiator here is execution speed versus overthinking the strategy.",
                "Have you noticed this trend accelerating more in B2B or B2C spaces recently?",
                "Spot on. When teams align on this early, it saves weeks of back-and-forth iteration.",
            ],
            provider="fallback",
        )


# ── 7. Brand Voice CRUD Endpoints ───────────────────────────────────────────

@router.get("/ai/brand-voice", response_model=BrandVoiceConfig)
async def get_brand_voice(
    current_user: CurrentUser,
    db: DB,
) -> BrandVoiceConfig:
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    doc = await db.brand_voices.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})
    if not doc:
        return BrandVoiceConfig()
    return BrandVoiceConfig(
        brand_name=doc.get("brand_name"),
        tone=doc.get("tone"),
        target_audience=doc.get("target_audience"),
        mission=doc.get("mission"),
        banned_words=doc.get("banned_words") or [],
        formatting_rules=doc.get("formatting_rules"),
        custom_guidelines=doc.get("custom_guidelines"),
        signature_cta=doc.get("signature_cta"),
    )


@router.put("/ai/brand-voice", response_model=BrandVoiceConfig)
async def save_brand_voice(
    body: BrandVoiceConfig,
    current_user: CurrentUser,
    db: DB,
) -> BrandVoiceConfig:
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    payload = {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "brand_name": body.brand_name,
        "tone": body.tone,
        "target_audience": body.target_audience,
        "mission": body.mission,
        "banned_words": body.banned_words,
        "formatting_rules": body.formatting_rules,
        "custom_guidelines": body.custom_guidelines,
        "signature_cta": body.signature_cta,
        "updated_at": datetime.now(timezone.utc),
    }
    await db.brand_voices.update_one(
        {"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]},
        {"$set": payload},
        upsert=True,
    )
    return body


# ── VIRAL HOOKS & SHORT-FORM VIDEO STUDIO (VIRLO-INSPIRED) ─────────────────────

@router.get("/ai/viral-hooks")
async def get_viral_hooks(
    category: str | None = None,
    niche: str | None = None,
    search: str | None = None,
):
    """Retrieve catalog of viral hooks with category and niche filters."""
    results = VIRAL_HOOKS
    if category and category != "all":
        results = [h for h in results if h.get("category") == category]
    if niche and niche != "all":
        results = [h for h in results if niche in h.get("niche", [])]
    if search and search.strip():
        q = search.lower().strip()
        results = [
            h for h in results
            if q in h.get("title", "").lower()
            or q in h.get("template", "").lower()
            or q in h.get("example", "").lower()
        ]
    return {
        "categories": CATEGORIES,
        "niches": NICHES,
        "total": len(results),
        "hooks": results,
    }


@router.post("/ai/generate-script", response_model=GenerateScriptResponse)
async def generate_short_form_script(
    body: GenerateScriptRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Generates a timed 9:16 short-form video storyboard and teleprompter script
    optimized for TikTok, Instagram Reels, and YouTube Shorts.
    """
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    # Check brand voice if enabled
    brand_voice_hint = ""
    if body.use_brand_voice:
        bv_doc = await db.brand_voices.find_one({"$or": [{"workspace_id": workspace_id}, {"user_id": user_id}]})
        if bv_doc:
            brand_voice_hint = f"Brand: {bv_doc.get('brand_name')}. Tone: {bv_doc.get('tone')}."

    niche_visuals = {
        "beauty_fashion": "Include close-up product texture swatches, macro lighting angles, and before/after split frames.",
        "food_cooking": "Include sizzling audio cues, overhead pan angles, knife cuts, and cross-section ingredient reveals.",
        "career_jobs": "Include resume keyword highlight overlays, interview roleplay split screens, and counter-offer email templates.",
        "coaching_consulting": "Include whiteboard framework diagrams, client revenue dashboard proof, and proposal teardowns.",
        "travel_lifestyle": "Include POV packing shots, Google Flights screen overlays, and location geotags.",
        "legal_tax": "Include contract clause callouts, IRS tax flowcharts, and document redaction visuals.",
        "gaming_gear": "Include 240Hz screen capture, FPS meter overlay, and mechanical keyboard sound cues.",
        "parenting_home": "Include daily routine countdown timers, split-screen chaos vs calm, and visual chore charts.",
        "saas_tech": "Include code editor snippets, Terminal commands, API speed graphs, and dashboard analytics.",
        "ecommerce": "Include unboxing POV, product close-ups, packaging reveals, and customer review overlays.",
        "marketing": "Include ROAS dashboards, campaign breakdown slides, and LinkedIn viral post screenshots.",
        "fitness": "Include form check slow-mo, workout rep tracker, and nutrition meal prep cross-sections.",
        "real_estate": "Include architectural walkthroughs, listing price overlays, and neighborhood drone b-roll.",
        "finance": "Include compound interest charts, tax return highlights, and portfolio pie graphs.",
        "creator": "Include timeline editing zooms, thumbnail A/B comparisons, and analytics view graphs.",
        "productivity": "Include Notion workspace tours, keyboard shortcut overlays, and time-block calendar zooms.",
    }.get(body.niche, "Include engaging B-roll and fast visual transitions.")

    system_prompt = (
        "You are an elite viral short-form video creator and scriptwriter for TikTok, Instagram Reels, and YouTube Shorts. "
        "Create high-retention, fast-paced video scripts that hook viewers in the first 2-3 seconds and keep them watching until the end. "
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "title": "Working Video Title",\n'
        '  "hooks": ["Hook variation 1 (Contrarian)", "Hook variation 2 (Curiosity)", "Hook variation 3 (Pain/Urgency)"],\n'
        '  "selected_hook": "Hook variation 1",\n'
        '  "storyboard": [\n'
        '    {"timestamp": "0:00 - 0:03", "stage": "Hook", "visual_cue": "Fast motion or close-up action", "on_screen_text": "STOP DOING THIS", "spoken_dialogue": "..."},\n'
        '    {"timestamp": "0:03 - 0:15", "stage": "Problem Agitation", "visual_cue": "...", "on_screen_text": "...", "spoken_dialogue": "..."},\n'
        '    {"timestamp": "0:15 - 0:25", "stage": "Value / Secret", "visual_cue": "...", "on_screen_text": "...", "spoken_dialogue": "..."},\n'
        '    {"timestamp": "0:25 - 0:30", "stage": "Call To Action", "visual_cue": "Point down / smile", "on_screen_text": "LINK IN BIO", "spoken_dialogue": "..."}\n'
        "  ],\n"
        '  "full_script": "Clean word-for-word teleprompter transcript...",\n'
        '  "call_to_action": "Follow for more / Link in bio",\n'
        '  "recommended_hashtags": ["#shorts", "#tiktoktips", "#growth"]\n'
        "}"
    )

    user_prompt = (
        f"Topic: {body.topic}\n"
        f"Niche: {body.niche or 'general'}\n"
        f"Visual Direction: {niche_visuals}\n"
        f"Platform: {body.platform or 'TikTok'}\n"
        f"Target Duration: {body.target_duration or '30s'}\n"
        f"Hook Style: {body.hook_style or 'contrarian'}\n"
        f"{brand_voice_hint}\n"
        "Generate a viral storyboard and teleprompter script now."
    )

    raw_text = ""
    provider = "system"
    model = "default"
    try:
        raw_text, provider, model = await _ai_waterfall(system_prompt, user_prompt)
        
        # Clean JSON code fences if present
        clean_json = raw_text.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```[a-zA-Z]*\n?", "", clean_json)
            clean_json = re.sub(r"\n?```$", "", clean_json).strip()
            
        data = json.loads(clean_json)
        return GenerateScriptResponse(
            title=data.get("title", f"Viral Script: {body.topic[:30]}"),
            hooks=data.get("hooks", [f"Stop doing this with {body.topic}!"]),
            selected_hook=data.get("selected_hook", data.get("hooks", [""])[0] if data.get("hooks") else ""),
            storyboard=[
                StoryboardBeat(
                    timestamp=b.get("timestamp", "0:00 - 0:05"),
                    stage=b.get("stage", "Content"),
                    visual_cue=b.get("visual_cue", "Talking to camera"),
                    on_screen_text=b.get("on_screen_text", ""),
                    spoken_dialogue=b.get("spoken_dialogue", ""),
                )
                for b in data.get("storyboard", [])
            ],
            full_script=data.get("full_script", raw_text),
            call_to_action=data.get("call_to_action", "Tap the link in my bio!"),
            recommended_hashtags=data.get("recommended_hashtags", ["#viral", "#socialmedia"]),
            provider=provider,
            model=model,
        )
    except Exception as exc:
        logger.warning(f"Script generation fallback triggered: {exc}")
        # Deterministic fallback
        return GenerateScriptResponse(
            title=f"Viral Video: {body.topic}",
            hooks=[
                f"Everything you were told about {body.topic} is a lie.",
                f"Stop making this 1 mistake with {body.topic}!",
                f"This 30-second secret about {body.topic} will save you hours.",
            ],
            selected_hook=f"Everything you were told about {body.topic} is a lie.",
            storyboard=[
                StoryboardBeat(
                    timestamp="0:00 - 0:03",
                    stage="Hook",
                    visual_cue="Direct eye contact, holding phone or pointing at screen",
                    on_screen_text=f"STOP DOING THIS 🚨",
                    spoken_dialogue=f"If you are still struggling with {body.topic}, stop right now. Here is what actually works in 2026.",
                ),
                StoryboardBeat(
                    timestamp="0:03 - 0:15",
                    stage="Problem Agitation",
                    visual_cue="Screen recording or B-roll demonstrating the frustration",
                    on_screen_text="THE HIDDEN MISTAKE",
                    spoken_dialogue=f"Most people spend hours trying outdated methods, only to get zero results and burn out.",
                ),
                StoryboardBeat(
                    timestamp="0:15 - 0:25",
                    stage="The Secret Framework",
                    visual_cue="Showing the simplified 1-click solution",
                    on_screen_text="THE 2026 PLAYBOOK",
                    spoken_dialogue=f"Instead, use this 3-step automation blueprint to cut your effort in half while doubling your reach.",
                ),
                StoryboardBeat(
                    timestamp="0:25 - 0:30",
                    stage="Call To Action",
                    visual_cue="Smiling, pointing to bio link or tapping screen",
                    on_screen_text="LINK IN BIO ✨",
                    spoken_dialogue="Grab the free workflow template from the link in my bio!",
                ),
            ],
            full_script=(
                f"If you are still struggling with {body.topic}, stop right now. Here is what actually works in 2026. "
                f"Most people spend hours trying outdated methods with zero results. "
                f"Instead, use this 3-step automation blueprint to cut your effort in half. "
                f"Grab the free workflow template from the link in my bio!"
            ),
            call_to_action="Grab the free guide from the link in my bio!",
            recommended_hashtags=["#contentcreator", "#viralvideos", "#growthtips"],
            provider="local_fallback",
            model="deterministic",
        )


@router.post("/ai/auto-fill-hook", response_model=AutoFillHookResponse)
async def auto_fill_viral_hook(
    body: AutoFillHookRequest,
    current_user: CurrentUser,
):
    """Customizes a raw viral hook template for a specific user topic."""
    system_prompt = (
        "You are an expert copywriter. Given a viral hook template and a specific topic/niche, "
        "generate 3 high-impact, ready-to-use hook variations with the placeholders filled in. "
        "Return ONLY a JSON object: {\"variations\": [\"Hook 1\", \"Hook 2\", \"Hook 3\"]}"
    )
    user_prompt = f"Template: {body.hook_template}\nTopic: {body.topic_or_brand}\nNiche: {body.niche}"

    try:
        raw_text, provider, _ = await _ai_waterfall(system_prompt, user_prompt)
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean).strip()
        data = json.loads(clean)
        return AutoFillHookResponse(variations=data.get("variations", []), provider=provider)
    except Exception:
        # Fallback replacing simple bracketed tokens
        base = body.hook_template.replace("[Topic]", body.topic_or_brand)
        base = base.replace("[Industry]", body.niche or "your field")
        base = base.replace("[Activity]", body.topic_or_brand)
        return AutoFillHookResponse(
            variations=[
                base,
                f"Why everyone is getting {body.topic_or_brand} wrong in 2026:",
                f"The 1 secret about {body.topic_or_brand} that nobody talks about:",
            ],
            provider="fallback",
        )


@router.post("/ai/viral-hooks/bookmark")
async def toggle_hook_bookmark(
    hook_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Toggle bookmark for a viral hook in user workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    doc = await db.workspace_bookmarks.find_one({"workspace_id": workspace_id, "type": "viral_hook", "item_id": hook_id})
    if doc:
        await db.workspace_bookmarks.delete_one({"_id": doc["_id"]})
        return {"bookmarked": False}
    else:
        await db.workspace_bookmarks.insert_one({
            "workspace_id": workspace_id,
            "user_id": current_user["user_id"],
            "type": "viral_hook",
            "item_id": hook_id,
            "created_at": now,
        })
        return {"bookmarked": True}


