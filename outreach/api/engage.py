"""
Engage & Grow API Endpoints for LinkedIn Pre-Outreach Warming.
Allows SDRs and creators to organize target accounts into lists,
aggregate their newest LinkedIn posts, and interact (like/comment/AI-comment)
without tab flooding or triggering LinkedIn anti-bot detection.
"""
import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.engine.voyager_client import VoyagerClient
from outreach.models import EngageContact, EngageList, EngagePost
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engage", tags=["LinkedIn Engage & Grow"])


# ── DTOs ───────────────────────────────────────────────────────────────────

class CreateEngageListRequest(BaseModel):
    name: str
    emoji: str = "🎯"
    description: str = ""


class AddContactsRequest(BaseModel):
    profile_urls: List[str] = Field(default_factory=list)
    csv_text: Optional[str] = None


class LikePostRequest(BaseModel):
    sender_account_id: Optional[str] = None


class CommentPostRequest(BaseModel):
    comment_text: str
    auto_like: bool = True
    sender_account_id: Optional[str] = None


class AICommentRequest(BaseModel):
    post_text: str
    author_headline: str = ""
    tone: str = "insightful"  # insightful, supportive, humorous, questioning, challenger
    custom_prompt: str = ""
    writing_style_id: Optional[str] = None


# ── Helper Functions ───────────────────────────────────────────────────────

def _extract_vanity(url: str) -> str:
    cleaned = normalize_linkedin_url(url)
    parts = cleaned.rstrip("/").split("/")
    return parts[-1] if parts else "prospect"


def _extract_name_from_vanity(vanity: str) -> str:
    cleaned = re.sub(r"-\d+$", "", vanity).replace("-", " ")
    return cleaned.title() if cleaned else "LinkedIn Member"


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/lists", status_code=status.HTTP_201_CREATED)
async def create_engage_list(
    req: CreateEngageListRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new engagement list (e.g. 'Dream 50 SaaS Founders')."""
    user_id = current_user.get("user_id") or "usr_default"
    workspace_id = current_user.get("default_workspace_id") or user_id

    doc = EngageList(
        workspace_id=workspace_id,
        user_id=user_id,
        name=req.name.strip(),
        emoji=req.emoji,
        description=req.description.strip(),
        contacts_count=0,
        pending_posts_count=0,
    ).model_dump()

    await db.outreach_engage_lists.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/lists")
async def list_engage_lists(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Retrieve all engagement lists for the workspace with live contact/pending counts."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")

    cursor = db.outreach_engage_lists.find({"workspace_id": workspace_id}, {"_id": 0}).sort("created_at", -1)
    lists = await cursor.to_list(100)

    # Sync live counts
    for l in lists:
        list_id = l["id"]
        contacts_c = await db.outreach_engage_contacts.count_documents({"list_id": list_id})
        pending_c = await db.outreach_engage_posts.count_documents({"list_id": list_id, "status": "pending"})
        l["contacts_count"] = contacts_c
        l["pending_posts_count"] = pending_c

    return lists


@router.get("/lists/{list_id}")
async def get_engage_list(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get details and contacts for an engagement list."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    engage_list = await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}, {"_id": 0})
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    contacts = await db.outreach_engage_contacts.find({"list_id": list_id}, {"_id": 0}).to_list(200)
    engage_list["contacts"] = contacts
    return engage_list


@router.delete("/lists/{list_id}", status_code=status.HTTP_200_OK)
async def delete_engage_list(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete an engagement list, including all its contacts and cached posts."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    result = await db.outreach_engage_lists.delete_one({"id": list_id, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    await db.outreach_engage_contacts.delete_many({"list_id": list_id})
    await db.outreach_engage_posts.delete_many({"list_id": list_id})
    return {"status": "deleted", "list_id": list_id}


@router.post("/lists/{list_id}/contacts")
async def add_contacts_to_list(
    list_id: str,
    req: AddContactsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Add LinkedIn profile URLs to an engagement list manually or via CSV."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    engage_list = await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id})
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    extracted_urls = list(req.profile_urls)

    if req.csv_text:
        try:
            reader = csv.reader(io.StringIO(req.csv_text))
            for row in reader:
                for col in row:
                    val = col.strip()
                    if "linkedin.com/in/" in val or "linkedin.com/sales/" in val:
                        extracted_urls.append(val)
        except Exception as exc:
            logger.warning("Error parsing CSV text for contacts: %s", exc)

    added_count = 0
    for raw_url in extracted_urls:
        if not raw_url.strip():
            continue
        cleaned_url = normalize_linkedin_url(raw_url)
        vanity = _extract_vanity(cleaned_url)

        # Deduplicate within list
        existing = await db.outreach_engage_contacts.find_one({"list_id": list_id, "profile_url": cleaned_url})
        if not existing:
            contact = EngageContact(
                list_id=list_id,
                workspace_id=workspace_id,
                profile_url=cleaned_url,
                vanity_name=vanity,
                full_name=_extract_name_from_vanity(vanity),
                headline=f"Leader at {vanity.replace('-', ' ').title()}",
                profile_urn=f"urn:li:fsd_profile:{vanity}",
            ).model_dump()
            await db.outreach_engage_contacts.insert_one(contact)
            added_count += 1

    # Update list count
    new_count = await db.outreach_engage_contacts.count_documents({"list_id": list_id})
    await db.outreach_engage_lists.update_one({"id": list_id}, {"$set": {"contacts_count": new_count}})

    return {"status": "success", "added_count": added_count, "total_contacts": new_count}


@router.post("/lists/{list_id}/fetch")
async def fetch_latest_posts_for_list(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    1-Click Fetch: Pulls recent posts from all contacts in this list
    via Voyager without browser tab clutter.
    """
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    engage_list = await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id})
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    contacts = await db.outreach_engage_contacts.find({"list_id": list_id}).to_list(100)
    if not contacts:
        return {"status": "empty", "message": "No contacts in list. Add contacts first.", "posts_fetched": 0}

    # Use first available sender account or fallback to mock
    account = await db.outreach_accounts.find_one({"workspace_id": workspace_id, "status": "active"})
    cookie_enc = account.get("session_cookie_enc", "mock_cookie") if account else "mock_cookie"
    jsession = account.get("jsession_id", "ajax:123") if account else "ajax:123"

    voyager = VoyagerClient(session_cookie_enc=cookie_enc, jsession_id=jsession)

    new_posts_count = 0
    now = datetime.now(timezone.utc)

    for c in contacts:
        profile_urn = c.get("profile_urn") or f"urn:li:fsd_profile:{c.get('vanity_name', 'user')}"
        updates = await voyager.fetch_profile_recent_updates(profile_urn, count=3)

        for u in updates:
            post_urn = u.get("post_urn")
            if not post_urn:
                continue

            existing_post = await db.outreach_engage_posts.find_one({"list_id": list_id, "post_urn": post_urn})
            if not existing_post:
                post_doc = EngagePost(
                    list_id=list_id,
                    contact_id=c["id"],
                    workspace_id=workspace_id,
                    author_name=c.get("full_name") or "LinkedIn Member",
                    author_headline=c.get("headline", ""),
                    author_avatar=c.get("avatar_url", ""),
                    author_profile_url=c.get("profile_url", ""),
                    author_urn=profile_urn,
                    post_urn=post_urn,
                    post_url=u.get("post_url", ""),
                    published_at=u.get("published_at", "Recently"),
                    content_text=u.get("content_text", ""),
                    reactions_count=u.get("reactions_count", 0),
                    comments_count=u.get("comments_count", 0),
                    media_urls=u.get("media_urls", []),
                    status="pending",
                ).model_dump()
                await db.outreach_engage_posts.insert_one(post_doc)
                new_posts_count += 1

        await db.outreach_engage_contacts.update_one(
            {"id": c["id"]},
            {"$set": {"last_fetched_at": now}}
        )

    # Refresh list counters
    pending_count = await db.outreach_engage_posts.count_documents({"list_id": list_id, "status": "pending"})
    await db.outreach_engage_lists.update_one({"id": list_id}, {"$set": {"pending_posts_count": pending_count}})

    return {
        "status": "success",
        "posts_fetched": new_posts_count,
        "pending_posts": pending_count,
    }


@router.get("/lists/{list_id}/posts")
async def get_engage_posts_feed(
    list_id: str,
    status_filter: str = "pending",
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):

    """Retrieve the aggregated post cards feed for this engagement list."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")

    query: dict[str, Any] = {"list_id": list_id, "workspace_id": workspace_id}
    if status_filter != "all":
        query["status"] = status_filter

    cursor = db.outreach_engage_posts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    posts = await cursor.to_list(limit)
    total = await db.outreach_engage_posts.count_documents(query)

    return {"posts": posts, "total": total, "status": status_filter}


@router.post("/posts/{post_id}/like")
async def like_engage_post(
    post_id: str,
    req: LikePostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """1-Click Like a post via Voyager."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    account = await db.outreach_accounts.find_one({"workspace_id": workspace_id, "status": "active"})
    cookie_enc = account.get("session_cookie_enc", "mock_cookie") if account else "mock_cookie"
    jsession = account.get("jsession_id", "ajax:123") if account else "ajax:123"

    voyager = VoyagerClient(session_cookie_enc=cookie_enc, jsession_id=jsession)
    res = await voyager.like_update(post["post_urn"])

    await db.outreach_engage_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "liked", "reactions_count": post.get("reactions_count", 0) + 1}}
    )

    return {"status": "liked", "post_id": post_id, "details": res}


@router.post("/posts/{post_id}/comment")
async def comment_engage_post(
    post_id: str,
    req: CommentPostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Post an in-line comment to LinkedIn with optional auto-like."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not req.comment_text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")

    account = await db.outreach_accounts.find_one({"workspace_id": workspace_id, "status": "active"})
    cookie_enc = account.get("session_cookie_enc", "mock_cookie") if account else "mock_cookie"
    jsession = account.get("jsession_id", "ajax:123") if account else "ajax:123"

    voyager = VoyagerClient(session_cookie_enc=cookie_enc, jsession_id=jsession)

    now = datetime.now(timezone.utc)
    if req.auto_like:
        res = await voyager.auto_like_and_comment(post["post_urn"], req.comment_text.strip())
    else:
        res = await voyager.comment_on_update(post["post_urn"], req.comment_text.strip())

    await db.outreach_engage_posts.update_one(
        {"id": post_id},
        {
            "$set": {
                "status": "commented",
                "user_comment": req.comment_text.strip(),
                "commented_at": now,
                "comments_count": post.get("comments_count", 0) + 1,
            }
        },
    )

    # Decrement pending count on list
    pending_count = await db.outreach_engage_posts.count_documents({"list_id": post["list_id"], "status": "pending"})
    await db.outreach_engage_lists.update_one({"id": post["list_id"]}, {"$set": {"pending_posts_count": pending_count}})

    return {
        "status": "commented",
        "post_id": post_id,
        "comment": req.comment_text.strip(),
        "timestamp": now.isoformat(),
        "details": res,
    }


@router.post("/posts/{post_id}/discard")
async def discard_engage_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Dismiss a post from the pending feed."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    await db.outreach_engage_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "discarded"}}
    )

    # Decrement pending count on list
    pending_count = await db.outreach_engage_posts.count_documents({"list_id": post["list_id"], "status": "pending"})
    await db.outreach_engage_lists.update_one({"id": post["list_id"]}, {"$set": {"pending_posts_count": pending_count}})

    return {"status": "discarded", "post_id": post_id}


@router.post("/ai-comment")
async def generate_ai_comments(
    req: AICommentRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Generate 3 high-impact LinkedIn comments tailored to the post's core message.
    Bans generic praise ("Great share! Totally agree!") in favor of insightful contributions.
    """
    if not req.post_text.strip():
        raise HTTPException(status_code=400, detail="Post text is required")

    tone_guidance = {
        "insightful": "Add an expert data point, framework, or operational nuance that enriches the author's point.",
        "supportive": "Validate their thesis with an empathetic real-world confirmation or encouraging peer observation.",
        "humorous": "Use light, witty professional banter that highlights an absurd truth of the industry without being sarcastic.",
        "questioning": "Pose a thought-provoking open-ended question that prompts a high-value debate in their comments.",
        "challenger": "Respectfully present a counter-intuitive alternate scenario or exception to their rule.",
    }.get(req.tone.lower(), "Provide a thoughtful, authentic professional perspective.")

    custom_instr = f"\nCustom focus: {req.custom_prompt.strip()}" if req.custom_prompt else ""
    author_info = f"\nAuthor Headline: {req.author_headline}" if req.author_headline else ""

    system_prompt = (
        "You are an elite LinkedIn ghostwriter and B2B engagement specialist. "
        "Your task is to write 3 distinct, high-value LinkedIn comments for the provided post.\n\n"
        "Strict Guidelines:\n"
        "1. NEVER use generic corporate filler: 'Great post!', '100% agree!', 'Thanks for sharing!', 'Spot on!'.\n"
        "2. Add genuine intellectual or operational value that encourages the author to reply back.\n"
        "3. Keep each comment concise: 1 to 3 punchy sentences (under 45 words).\n"
        "4. Tone objective: " + tone_guidance + "\n\n"
        "Respond ONLY with a valid JSON array of 3 strings matching this exact format:\n"
        '["First high-value comment...", "Second high-value comment...", "Third high-value comment..."]'
    )

    user_prompt = f"Post Content:\n{req.post_text[:1200]}{author_info}{custom_instr}"

    try:
        response_text, _, _ = await free_llm.generate_text(system_prompt, user_prompt)
        match = re.search(r"\[\s*\"[\s\S]*\"\s*\]", response_text)
        if match:
            comments = json.loads(match.group(0))
            if isinstance(comments, list) and len(comments) >= 1:
                return {"tone": req.tone, "comments": comments[:3]}
    except Exception as exc:
        logger.warning("AI comment generation failed, using high-value fallbacks: %s", exc)

    # Deterministic high-quality fallbacks based on post snippet
    snippet = req.post_text.strip().split("\n")[0][:60]
    fallback_comments = [
        f"This resonates heavily. The friction usually isn't in strategy, but in consistent follow-through across the first 48 hours.",
        f"Such an under-discussed angle. When you prioritize authentic touchpoints over volume, conversion economics completely shift.",
        f"Spot-on observation regarding {snippet.lower()}. Have you found that smaller teams execute this significantly faster?",
    ]

    return {"tone": req.tone, "comments": fallback_comments}
