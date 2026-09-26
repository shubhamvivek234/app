"""
Swipe Files & 1-Click Content Repurposer API.
Curates viral LinkedIn inspiration and transforms structures into original posts or outbound hooks.
"""
import logging
import re
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.models import SwipeFileItem
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swipe", tags=["LinkedIn Swipe Files"])


class CreateSwipeItemRequest(BaseModel):
    content_text: str = Field(..., min_length=1, max_length=20000)
    author_name: str = Field(default="Unknown Creator", max_length=150)
    author_avatar: str = ""
    post_url: str = ""
    tags: List[str] = Field(default_factory=lambda: ["LinkedIn"])

    @field_validator("content_text")
    @classmethod
    def content_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content cannot be blank")
        return value.strip()

    @field_validator("post_url")
    @classmethod
    def original_url_is_http(cls, value: str) -> str:
        value = value.strip()
        if value:
            parsed = urlparse(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ValueError("Original link must be an HTTP or HTTPS URL")
        return value


class RepurposeSwipeRequest(BaseModel):
    target_format: Literal["post", "outbound_hook", "connection_note"] = "post"
    custom_instructions: str = Field(default="", max_length=1000)
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
        author_name=req.author_name.strip() or "Unknown Creator",
        author_avatar=req.author_avatar,
        content_text=req.content_text.strip(),
        tags=[tag.strip()[:60] for tag in req.tags[:10] if tag.strip()],
        post_url=req.post_url.strip(),
    ).model_dump()

    await db.outreach_swipe_files.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_swipe_items(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all saved swipe file cards with tag and keyword filtering."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Invalid swipe pagination")
    query: dict = {"workspace_id": workspace_id, "is_archived": {"$ne": True}}

    if tag and tag != "all":
        query["tags"] = tag

    if search and search.strip():
        pattern = re.escape(search.strip()[:100])
        query["$or"] = [
            {"content_text": {"$regex": pattern, "$options": "i"}},
            {"author_name": {"$regex": pattern, "$options": "i"}},
        ]

    cursor = db.outreach_swipe_files.find(query, {"_id": 0}).sort("created_at", -1)
    if skip:
        cursor = cursor.skip(skip)
    return await cursor.to_list(limit)


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
        style = await db.outreach_writing_styles.find_one({"id": req.writing_style_id, "workspace_id": workspace_id})
        if not style:
            raise HTTPException(status_code=404, detail="Writing style not found")
        if style.get("extracted_style_prompt"):
            style_prompt = style["extracted_style_prompt"]

    instructions = {
        "post": "Transform this swiped post into a brand-new, original LinkedIn post adopting the exact structural hook and pacing, but with fresh industry examples.",
        "outbound_hook": "Extract the strongest hook angle from this post and convert it into a 2-sentence cold outreach opening line that stops the prospect in their tracks.",
        "connection_note": "Transform the core thesis of this post into an authentic, sub-300-character LinkedIn connection request note referencing this specific topic.",
    }[req.target_format]

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
        if not repurposed or not repurposed.strip():
            raise ValueError("AI returned an empty response")
        return {
            "target_format": req.target_format,
            "repurposed_text": repurposed.strip(),
            "original_author": item.get("author_name"),
        }
    except Exception as exc:
        logger.warning("Swipe repurposing failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI repurposing is unavailable. Please try again.") from exc
