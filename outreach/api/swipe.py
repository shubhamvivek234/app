"""
Swipe Files & 1-Click Content Repurposer API.
Curates viral LinkedIn inspiration and transforms structures into original posts or outbound hooks.
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.models import SwipeFileItem
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swipe", tags=["LinkedIn Swipe Files"])


class CreateSwipeItemRequest(BaseModel):
    content_text: str
    author_name: str = "Unknown Creator"
    author_avatar: str = ""
    post_url: str = ""
    tags: List[str] = Field(default_factory=lambda: ["LinkedIn"])


class RepurposeSwipeRequest(BaseModel):
    target_format: str = "post"  # 'post' | 'outbound_hook' | 'connection_note'
    custom_instructions: str = ""
    writing_style_id: Optional[str] = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_swipe_item(
    req: CreateSwipeItemRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Save an inspiring LinkedIn post into the swipe file."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    user_id = current_user.get("user_id")

    doc = SwipeFileItem(
        workspace_id=workspace_id,
        user_id=user_id,
        author_name=req.author_name.strip(),
        author_avatar=req.author_avatar,
        content_text=req.content_text.strip(),
        tags=req.tags,
        post_url=req.post_url.strip(),
    ).model_dump()

    await db.outreach_swipe_files.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_swipe_items(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all saved swipe file cards with tag and keyword filtering."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    query: dict = {"workspace_id": workspace_id, "is_archived": False}

    if tag and tag != "all":
        query["tags"] = tag

    if search:
        query["$or"] = [
            {"content_text": {"$regex": search, "$options": "i"}},
            {"author_name": {"$regex": search, "$options": "i"}},
        ]

    cursor = db.outreach_swipe_files.find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(100)


@router.delete("/{item_id}")
async def delete_swipe_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    res = await db.outreach_swipe_files.delete_one({"id": item_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Swipe item not found")
    return {"status": "deleted", "item_id": item_id}


@router.post("/{item_id}/repurpose")
async def repurpose_swipe_item(
    item_id: str,
    req: RepurposeSwipeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    1-Click AI Repurposing: Steals the hook structure, pacing, and core insight
    of the swiped post, rewriting it completely from scratch into original content or outreach copy.
    """
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    item = await db.outreach_swipe_files.find_one({"id": item_id, "workspace_id": workspace_id})
    if not item:
        raise HTTPException(status_code=404, detail="Swipe item not found")

    style_prompt = "Write in a direct, punchy, conversational LinkedIn style."
    if req.writing_style_id:
        style = await db.outreach_writing_styles.find_one({"id": req.writing_style_id})
        if style and style.get("extracted_style_prompt"):
            style_prompt = style["extracted_style_prompt"]

    instructions = {
        "post": "Transform this swiped post into a brand-new, original LinkedIn post adopting the exact structural hook and pacing, but with fresh industry examples.",
        "outbound_hook": "Extract the strongest hook angle from this post and convert it into a 2-sentence cold outreach opening line that stops the prospect in their tracks.",
        "connection_note": "Transform the core thesis of this post into an authentic, sub-300-character LinkedIn connection request note referencing this specific topic.",
    }.get(req.target_format, "Repurpose this content into an original post.")

    custom_extra = f"\nAdditional focus: {req.custom_instructions}" if req.custom_instructions else ""

    system_prompt = (
        f"You are a master LinkedIn copywriter and cold outbound strategist.\n"
        f"Style Guide: {style_prompt}\n"
        f"Task: {instructions}{custom_extra}\n\n"
        "Return ONLY the rewritten copy without conversational intro or meta-explanations."
    )

    user_prompt = f"Original Swiped Post:\n{item['content_text'][:2000]}"

    try:
        repurposed, _, _ = await free_llm.generate_text(system_prompt, user_prompt)
        return {
            "target_format": req.target_format,
            "repurposed_text": repurposed.strip(),
            "original_author": item.get("author_name"),
        }
    except Exception as exc:
        logger.warning("Repurposing failed, using fallback: %s", exc)
        return {
            "target_format": req.target_format,
            "repurposed_text": f"Here is the counter-intuitive truth about {item['content_text'][:50]}...\n\nMost teams optimize for the wrong metrics. Focus on velocity and clarity instead.",
            "original_author": item.get("author_name"),
        }
