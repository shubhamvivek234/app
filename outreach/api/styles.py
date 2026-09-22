"""
Content Writing Styles API for LinkedIn Outbound & AI Generation.
Allows users to mimic their own authentic voice or admired creators by analyzing sample posts.
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.models import WritingStyle
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/styles", tags=["LinkedIn Writing Styles"])


class CreateWritingStyleRequest(BaseModel):
    name: str
    sample_posts: List[str] = Field(..., min_length=1, description="List of 3 to 10 sample posts")
    is_default: bool = False


class UpdateWritingStyleRequest(BaseModel):
    name: Optional[str] = None
    extracted_style_prompt: Optional[str] = None
    is_default: Optional[bool] = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_writing_style(
    req: CreateWritingStyleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Analyze sample posts and extract a persistent writing style persona."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    user_id = current_user.get("user_id")

    combined_samples = "\n\n--- SAMPLE ---\n\n".join(req.sample_posts[:10])

    system_prompt = (
        "You are an expert linguistic analyst and ghostwriter. "
        "Analyze the provided LinkedIn posts and extract the author's distinct writing style.\n"
        "Summarize:\n"
        "1. Sentence rhythm & length (short/punchy vs long/story)\n"
        "2. Hook technique (questions, bold stats, counter-intuitive statements)\n"
        "3. Spacing and paragraph cadence\n"
        "4. Tone and vocabulary (approachable, direct, academic, visionary)\n"
        "5. 4-6 tone keywords\n\n"
        "Write a concise 3-4 sentence system instruction that another AI can use to reproduce this exact voice."
    )

    style_prompt = "Write in a direct, punchy, conversational LinkedIn style with short 1-2 sentence paragraphs and clear hooks."
    keywords = ["authentic", "concise", "conversational", "impactful"]

    try:
        analysis, _, _ = await free_llm.generate_text(system_prompt, combined_samples[:4000])
        if analysis:
            style_prompt = analysis.strip()
            # Extract keywords if possible
            k_match = re.findall(r"\b([A-Za-z]{4,12})\b", analysis)
            if k_match:
                keywords = list(set([k.lower() for k in k_match[:6]]))
    except Exception as exc:
        logger.warning("Style extraction LLM failed, using default: %s", exc)

    if req.is_default:
        await db.outreach_writing_styles.update_many({"workspace_id": workspace_id}, {"$set": {"is_default": False}})

    doc = WritingStyle(
        workspace_id=workspace_id,
        user_id=user_id,
        name=req.name.strip(),
        sample_posts=req.sample_posts,
        extracted_style_prompt=style_prompt,
        tone_keywords=keywords,
        is_default=req.is_default,
    ).model_dump()

    await db.outreach_writing_styles.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_writing_styles(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Retrieve all writing styles for the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    cursor = db.outreach_writing_styles.find({"workspace_id": workspace_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(50)


@router.get("/{style_id}")
async def get_writing_style(
    style_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    style = await db.outreach_writing_styles.find_one({"id": style_id, "workspace_id": workspace_id}, {"_id": 0})
    if not style:
        raise HTTPException(status_code=404, detail="Writing style not found")
    return style


@router.delete("/{style_id}")
async def delete_writing_style(
    style_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    res = await db.outreach_writing_styles.delete_one({"id": style_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Writing style not found")
    return {"status": "deleted", "style_id": style_id}
