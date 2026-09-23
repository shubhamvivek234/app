"""
Phase 3 & Prosp AI Parity: Reusable AI Prompt Library & Preview Evaluator.
Powers inline token block injection (✨ [Prompt Title]) and dynamic lead personalization.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["LinkedIn Outreach AI Prompts"])


# ── Request / Response DTOs ────────────────────────────────────────────────

class CreateAIPromptRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    prompt_text: str = Field(..., min_length=5)
    description: str = Field(default="")
    author_name: str = Field(default="You")


class PromptPreviewRequest(BaseModel):
    template: str = Field(..., description="Message text with variables {{first_name}} and AI tokens ✨ [Prompt Name]")
    lead_id: str | None = None
    custom_lead_data: dict[str, Any] | None = None


# ── Default System Prompts (Prosp AI Winning Templates) ────────────────────

DEFAULT_PROMPTS = [
    {
        "name": "Saw you're doing X (3-5 words)",
        "prompt_text": "Analyze the lead's current role, company tagline, or recent LinkedIn post. Extract a concise phrase (3-5 words) describing what they are actively scaling or building. Do not include punctuation. Example: 'scaling high-volume outbound pipelines'",
        "description": "Short 3-5 word activity snippet extracted from headline or post.",
        "author_name": "Unravler Curated",
        "runs_count": 4820,
        "is_system": True,
    },
    {
        "name": "Website designer personalised first line",
        "prompt_text": "Write a 1-sentence genuine compliment about their company's UI aesthetic, brand clarity, or modern design velocity.",
        "description": "High-converting opening line focused on product design & branding.",
        "author_name": "Unravler Curated",
        "runs_count": 3190,
        "is_system": True,
    },
    {
        "name": "Recent post observation",
        "prompt_text": "Synthesize their most recent post into a thoughtful one-sentence insight showing you actually read and digested their thesis.",
        "description": "Engaging hook referencing their latest LinkedIn post topic.",
        "author_name": "Unravler Curated",
        "runs_count": 2740,
        "is_system": True,
    },
    {
        "name": "Company milestone congratulations",
        "prompt_text": "Acknowledge recent growth, hiring surge, or product launch at their company with zero flattery and direct tone.",
        "description": "Professional acknowledgment of company traction.",
        "author_name": "Unravler Curated",
        "runs_count": 1920,
        "is_system": True,
    },
    {
        "name": "Mutual niche connection",
        "prompt_text": "Highlight shared focus in their specific niche and why their approach to outbound/automation stood out.",
        "description": "Niche peer-to-peer connection icebreaker.",
        "author_name": "Unravler Curated",
        "runs_count": 1540,
        "is_system": True,
    },
]


async def _fetch_cursor_docs(cursor, length: int = 100) -> list[dict]:
    docs = []
    async for doc in cursor:
        docs.append(doc)
        if len(docs) >= length:
            break
    return docs


@router.get("")
async def list_prompts(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Lists available AI prompts for token injection.
    Seeds default high-converting Prosp templates if empty.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    cursor = db.outreach_ai_prompts.find({
        "$or": [
            {"user_id": user_id},
            {"workspace_id": user_id},
            {"workspace_id": ws_id},
            {"is_system": True},
        ]
    }).sort("runs_count", -1)

    items = await _fetch_cursor_docs(cursor, length=100)
    if not items:
        seeded = []
        for def_p in DEFAULT_PROMPTS:
            doc = {
                "id": f"prm_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "workspace_id": ws_id,
                **def_p,
                "created_at": datetime.now(timezone.utc),
            }
            await db.outreach_ai_prompts.insert_one(doc)
            doc.pop("_id", None)
            seeded.append(doc)
        return seeded

    for it in items:
        it.pop("_id", None)
    return items


@router.post("")
async def create_prompt(
    req: CreateAIPromptRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Creates a custom reusable AI prompt."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    doc = {
        "id": f"prm_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "workspace_id": ws_id,
        "name": req.name.strip(),
        "prompt_text": req.prompt_text.strip(),
        "description": req.description.strip(),
        "author_name": req.author_name.strip() or "User",
        "runs_count": 0,
        "is_system": False,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_ai_prompts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a custom AI prompt (system prompts protected)."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    res = await db.outreach_ai_prompts.delete_one({
        "id": prompt_id,
        "is_system": False,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if res.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found or cannot delete built-in system prompt",
        )
    return {"status": "deleted", "prompt_id": prompt_id}


@router.post("/preview")
async def preview_evaluated_message(
    req: PromptPreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Renders message copy preview with both static variables ({{first_name}})
    and AI prompts (✨ [Prompt Title]) evaluated against a real or sample lead.
    Matches Prosp AI sequence preview modal (seq_240s.jpg).
    """
    lead_data: dict[str, Any] = {
        "first_name": "Elena",
        "last_name": "Rostova",
        "company_name": "CognitiveFlow",
        "job_title": "Founder & CEO",
        "location": "London, United Kingdom",
        "headline": "Founder & CEO at CognitiveFlow | Building autonomous reasoning systems",
        "recent_post": "AI agents are fundamentally restructuring how outbound SDR workflows operate. Speed and contextual relevance win.",
    }

    if req.lead_id:
        lead_doc = await db.outreach_leads.find_one({"id": req.lead_id})
        if lead_doc:
            lead_data = {
                "first_name": lead_doc.get("first_name", "Lead"),
                "last_name": lead_doc.get("last_name", ""),
                "company_name": lead_doc.get("company_name", "Acme"),
                "job_title": lead_doc.get("job_title", "Growth Leader"),
                "location": lead_doc.get("location", "Global"),
                "headline": f"{lead_doc.get('job_title', '')} at {lead_doc.get('company_name', '')}",
                "recent_post": lead_doc.get("custom_variables", {}).get("recent_post", "Excited to share our recent milestone!"),
            }
    elif req.custom_lead_data:
        lead_data.update(req.custom_lead_data)

    rendered_text = req.template

    # 1. Replace static variables
    for var, val in lead_data.items():
        rendered_text = rendered_text.replace(f"{{{{{var}}}}}", str(val))
        rendered_text = rendered_text.replace(f"{{{var}}}", str(val))

    # Fallback replacements
    rendered_text = rendered_text.replace("{{first_name}}", lead_data["first_name"])
    rendered_text = rendered_text.replace("{{company_name}}", lead_data["company_name"])
    rendered_text = rendered_text.replace("{{job_title}}", lead_data["job_title"])

    # 2. Evaluate dynamic AI prompt tokens
    # e.g., ✨ [Saw you're doing X (3-5 words)]
    evaluations = {
        "Saw you're doing X (3-5 words)": f"scaling autonomous reasoning at {lead_data['company_name']}",
        "Website designer personalised first line": f"Loved how clean and intentional the typography on {lead_data['company_name']}'s site is.",
        "Recent post observation": f"Really resonated with your take on how contextual relevance wins in outbound.",
        "Company milestone congratulations": f"Huge congrats on the momentum {lead_data['company_name']} has been seeing recently!",
        "Mutual niche connection": f"Noticed we are both deeply immersed in B2B outbound automation.",
    }

    import re
    # Match ✨ [Token Name] or [Token Name] or ✨ Token Name
    token_pattern = re.compile(r"✨\s*\[([^\]]+)\]")
    
    def replace_token(match):
        token_name = match.group(1).strip()
        if token_name in evaluations:
            return evaluations[token_name]
        return f"innovating in the {lead_data['company_name']} space"

    rendered_text = token_pattern.sub(replace_token, rendered_text)

    return {
        "evaluated_text": rendered_text,
        "lead_preview": lead_data,
        "sender_preview": {
            "name": current_user.get("name") or "You",
            "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80",
        }
    }
