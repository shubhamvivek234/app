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
from datetime import timedelta
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.core.safety_shield import SafetyShield
from outreach.engine.voyager_client import VoyagerClient
from outreach.models import EngageContact, EngageList, EngagePost
from utils.free_llm_router import free_llm
from utils.request_context import get_trace_id

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
    sender_account_id: Optional[str] = None


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


class EngageListSettingsRequest(BaseModel):
    campaign_id: str | None = None
    warmup_hours: int = Field(default=24, ge=0, le=168)


class CreateEngageDraftRequest(BaseModel):
    post_id: str
    comment_text: str = Field(min_length=1, max_length=2000)


class UpdateEngageDraftRequest(BaseModel):
    comment_text: str | None = Field(default=None, min_length=1, max_length=2000)
    status: str | None = None


# ── Helper Functions ───────────────────────────────────────────────────────

def _extract_vanity(url: str) -> str:
    cleaned = normalize_linkedin_url(url)
    parts = cleaned.rstrip("/").split("/")
    return parts[-1] if parts else "prospect"


async def _reject_armed_list_changes(list_id: str, workspace_id: str, db: AsyncIOMotorDatabase) -> None:
    campaign = await db.outreach_campaigns.find_one({
        "workspace_id": workspace_id, "status": "warming_up",
        "auto_launch_list_id": list_id, "is_deleted": {"$ne": True},
    })
    if campaign:
        raise HTTPException(status_code=409, detail="Cancel the campaign's conditional launch before changing or deleting its Engage list")


# ── Endpoints ──────────────────────────────────────────────────────────────

async def _resolve_sender_account(
    workspace_id: str,
    db: AsyncIOMotorDatabase,
    sender_account_id: str | None = None,
) -> dict:
    """
    Resolves the sender account for engage actions.
    Raises 400 if no active account exists (no silent mock fallback).
    """
    if sender_account_id:
        account = await db.outreach_accounts.find_one(
            {"id": sender_account_id, "workspace_id": workspace_id, "status": "active"}
        )
        if not account:
            raise HTTPException(
                status_code=400,
                detail="Selected sender account is not active or doesn't exist. Connect a LinkedIn account first.",
            )
    else:
        account = await db.outreach_accounts.find_one(
            {"workspace_id": workspace_id, "status": "active"}
        )
        if not account:
            raise HTTPException(
                status_code=400,
                detail="No active LinkedIn account connected. Connect an account in Settings before engaging.",
            )
    return account


async def _require_voyager_success(result: dict, expected: str, account: dict, db: AsyncIOMotorDatabase) -> None:
    if result.get("status") == expected:
        return
    code = result.get("status_code") or 0
    message = result.get("text") or result.get("error") or "LinkedIn did not confirm this action."
    if SafetyShield.should_trip_circuit_breaker(code, message):
        await SafetyShield.trip_circuit_breaker(
            account["id"], f"Engage action triggered: HTTP {code}: {message[:120]}", db, account["workspace_id"]
        )
        raise HTTPException(status_code=503, detail="LinkedIn restriction detected. Sender paused for safety.")
    raise HTTPException(status_code=502, detail=f"LinkedIn action failed: {message[:200]}")


def _build_voyager(account: dict) -> VoyagerClient:
    """Build VoyagerClient from a resolved account document."""
    from outreach.core.crypto import decrypt_secret

    proxy_cfg = account.get("proxy") or {}
    proxy_url = None
    if proxy_cfg.get("host"):
        proxy_pass = decrypt_secret(proxy_cfg.get("password_enc", ""))
        proxy_url = f"http://{proxy_cfg.get('username', '')}:{proxy_pass}@{proxy_cfg['host']}:{proxy_cfg.get('port', 8080)}"

    return VoyagerClient(
        session_cookie_enc=account.get("session_cookie_enc", ""),
        jsession_id=account.get("jsession_id", "ajax:123"),
        proxy_url=proxy_url,
    )

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
        contacts_c = await db.outreach_engage_contacts.count_documents({"list_id": list_id, "workspace_id": workspace_id})
        pending_c = await db.outreach_engage_posts.count_documents({"list_id": list_id, "workspace_id": workspace_id, "status": "pending"})
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

    contacts = await db.outreach_engage_contacts.find({"list_id": list_id, "workspace_id": workspace_id}, {"_id": 0}).to_list(1000)
    for contact in contacts:
        if contact.get("enrichment_status") != "verified":
            contact.update({"full_name": "", "headline": "", "avatar_url": "", "profile_urn": "",
                            "enrichment_status": contact.get("enrichment_status") or "unverified"})
    engage_list["contacts"] = contacts
    return engage_list


@router.get("/accounts")
async def list_engage_accounts(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    accounts = await db.outreach_accounts.find(
        {"workspace_id": workspace_id, "status": "active"},
        {"_id": 0, "id": 1, "account_name": 1, "avatar_url": 1, "vanity_name": 1},
    ).to_list(100)
    return accounts


@router.patch("/lists/{list_id}/settings")
async def update_engage_list_settings(
    list_id: str,
    req: EngageListSettingsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    await _reject_armed_list_changes(list_id, workspace_id, db)
    if req.campaign_id:
        campaign = await db.outreach_campaigns.find_one({
            "id": req.campaign_id, "workspace_id": workspace_id, "is_deleted": {"$ne": True},
        })
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found in this workspace")
        if campaign.get("status") != "draft":
            raise HTTPException(status_code=409, detail="Only draft campaigns can be linked to a warm-up list")
    result = await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id},
        {"$set": {"campaign_id": req.campaign_id, "warmup_hours": req.warmup_hours, "updated_at": datetime.now(timezone.utc)}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Engagement list not found")
    return {"campaign_id": req.campaign_id, "warmup_hours": req.warmup_hours}


@router.get("/lists/{list_id}/stats")
async def get_engage_list_stats(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if not await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}):
        raise HTTPException(status_code=404, detail="Engagement list not found")
    base = {"list_id": list_id, "workspace_id": workspace_id}
    counts = {status: await db.outreach_engage_posts.count_documents({**base, "status": status})
              for status in ("pending", "commented", "discarded")}
    counts["liked"] = await db.outreach_engage_posts.count_documents({
        **base, "$or": [{"status": "liked"}, {"liked_at": {"$ne": None}}],
    })
    counts["contacts"] = await db.outreach_engage_contacts.count_documents(base)
    counts["total"] = await db.outreach_engage_posts.count_documents(base)
    return counts


@router.get("/lists/{list_id}/report")
async def get_engage_report(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Printable summary of recorded actions, excluding drafts and legacy status-only rows."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    engage_list = await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id})
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")
    base = {"list_id": list_id, "workspace_id": workspace_id}
    posts = await db.outreach_engage_posts.find(base, {
        "_id": 0, "contact_id": 1, "liked_at": 1, "commented_at": 1, "discarded_at": 1,
    }).to_list(10000)
    liked = [post for post in posts if isinstance(post.get("liked_at"), datetime)]
    commented = [post for post in posts if isinstance(post.get("commented_at"), datetime)]
    discarded = [post for post in posts if isinstance(post.get("discarded_at"), datetime)]
    engaged_contacts = {post.get("contact_id") for post in liked + commented if post.get("contact_id")}
    return {
        "list_name": engage_list.get("name", "Engage list"),
        "generated_at": datetime.now(timezone.utc),
        "contacts": await db.outreach_engage_contacts.count_documents(base),
        "posts_fetched": len(posts),
        "likes_sent": len(liked),
        "comments_published": len(commented),
        "posts_discarded": len(discarded),
        "contacts_engaged": len(engaged_contacts),
        "limited_to_recent_10000_posts": len(posts) == 10000,
    }


@router.get("/lists/{list_id}/drafts")
async def list_engage_drafts(
    list_id: str,
    status_filter: str = "pending",
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List human-reviewed comment drafts. Self-reported completion is not engagement."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if status_filter not in {"pending", "completed", "dismissed", "all"}:
        raise HTTPException(status_code=400, detail="Invalid draft status")
    if not await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}):
        raise HTTPException(status_code=404, detail="Engagement list not found")
    base = {"list_id": list_id, "workspace_id": workspace_id}
    query = base if status_filter == "all" else {**base, "status": status_filter}
    drafts = await db.outreach_engage_drafts.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    pending_count = await db.outreach_engage_drafts.count_documents({**base, "status": "pending"})
    return {"drafts": drafts, "pending_count": pending_count}


@router.post("/lists/{list_id}/drafts", status_code=status.HTTP_201_CREATED)
async def create_engage_draft(
    list_id: str,
    req: CreateEngageDraftRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if not await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}):
        raise HTTPException(status_code=404, detail="Engagement list not found")
    post = await db.outreach_engage_posts.find_one({
        "id": req.post_id, "list_id": list_id, "workspace_id": workspace_id,
    })
    if not post:
        raise HTTPException(status_code=404, detail="Post not found in this list")
    if post.get("status") in {"commented", "discarded"}:
        raise HTTPException(status_code=409, detail="This post can no longer be drafted")
    content = req.comment_text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Draft text cannot be empty")
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex, "list_id": list_id, "workspace_id": workspace_id,
        "post_id": req.post_id, "contact_id": post.get("contact_id"),
        "post_url": post.get("post_url", ""),
        "author_name": post.get("author_name", "LinkedIn Member"),
        "post_excerpt": (post.get("content_text") or "")[:500],
        "comment_text": content, "status": "pending", "source": "manual_review",
        "created_by": current_user.get("user_id"), "created_at": now, "updated_at": now,
    }
    await db.outreach_engage_drafts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/lists/{list_id}/drafts/{draft_id}")
async def update_engage_draft(
    list_id: str,
    draft_id: str,
    req: UpdateEngageDraftRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if req.status is not None and req.status not in {"pending", "completed", "dismissed"}:
        raise HTTPException(status_code=400, detail="Invalid draft status")
    query = {"id": draft_id, "list_id": list_id, "workspace_id": workspace_id}
    draft = await db.outreach_engage_drafts.find_one(query, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Only pending drafts can be changed")
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if req.comment_text is not None:
        updates["comment_text"] = req.comment_text.strip()
        if not updates["comment_text"]:
            raise HTTPException(status_code=400, detail="Draft text cannot be empty")
    if req.status is not None:
        updates["status"] = req.status
        if req.status == "completed":
            updates["completion_source"] = "self_reported"
            updates["completed_at"] = updates["updated_at"]
    result = await db.outreach_engage_drafts.update_one({**query, "status": "pending"}, {"$set": updates})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="Draft changed while you were reviewing it")
    return {**draft, **updates}


@router.delete("/lists/{list_id}", status_code=status.HTTP_200_OK)
async def delete_engage_list(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete an engagement list, including its contacts, posts, and review drafts."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    await _reject_armed_list_changes(list_id, workspace_id, db)
    result = await db.outreach_engage_lists.delete_one({"id": list_id, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    await db.outreach_engage_contacts.delete_many({"list_id": list_id, "workspace_id": workspace_id})
    await db.outreach_engage_posts.delete_many({"list_id": list_id, "workspace_id": workspace_id})
    await db.outreach_engage_drafts.delete_many({"list_id": list_id, "workspace_id": workspace_id})
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

    try:
        account = await _resolve_sender_account(workspace_id, db, req.sender_account_id)
    except HTTPException:
        if req.sender_account_id:
            raise
        account = None
    cleaned_urls = [normalize_linkedin_url(raw) for raw in extracted_urls if raw.strip()]
    invalid_count = sum(not url for url in cleaned_urls)
    cleaned_urls = list(dict.fromkeys(url for url in cleaned_urls if url))
    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="Add at least one valid LinkedIn /in/ profile URL.")
    current_count = await db.outreach_engage_contacts.count_documents({"list_id": list_id, "workspace_id": workspace_id})
    if current_count + len(cleaned_urls) > 1000:
        raise HTTPException(status_code=400, detail="Engagement lists are limited to 1,000 contacts. Split this upload into smaller lists.")

    added_count = 0
    for cleaned_url in cleaned_urls:
        vanity = _extract_vanity(cleaned_url)

        # Deduplicate within list
        existing = await db.outreach_engage_contacts.find_one({"list_id": list_id, "workspace_id": workspace_id, "profile_url": cleaned_url})
        if not existing:
            contact = EngageContact(
                list_id=list_id,
                workspace_id=workspace_id,
                profile_url=cleaned_url,
                vanity_name=vanity,
                full_name="",
                headline="",
                avatar_url="",
                profile_urn="",
                enrichment_status="pending",
            ).model_dump()
            await db.outreach_engage_contacts.insert_one(contact)
            added_count += 1

    # Update list count
    new_count = await db.outreach_engage_contacts.count_documents({"list_id": list_id, "workspace_id": workspace_id})
    await db.outreach_engage_lists.update_one({"id": list_id, "workspace_id": workspace_id}, {"$set": {"contacts_count": new_count}})

    if added_count and account:
        try:
            await db.outreach_engage_lists.update_one(
                {"id": list_id, "workspace_id": workspace_id}, {"$set": {"enrichment_status": "queued"}},
            )
            from celery_workers.celery_app import celery_app
            celery_app.send_task(
                "celery_workers.tasks.engage.enrich_contacts",
                args=[list_id, workspace_id, account["id"]], queue="outreach", ignore_result=True,
                headers={"x-trace-id": get_trace_id() or uuid.uuid4().hex},
            )
        except Exception as exc:
            logger.exception("Failed to queue contact enrichment for %s", list_id)
            await db.outreach_engage_lists.update_one(
                {"id": list_id, "workspace_id": workspace_id},
                {"$set": {"enrichment_status": "failed", "fetch_error": str(exc)[:200]}},
            )
            raise HTTPException(status_code=503, detail="Contacts were saved, but verification could not be queued. Use Fetch Latest Posts after the worker recovers.")

    if added_count and not account:
        await db.outreach_engage_lists.update_one(
            {"id": list_id, "workspace_id": workspace_id},
            {"$set": {"enrichment_status": "waiting_for_sender"}},
        )
    return {"status": "success", "added_count": added_count, "invalid_count": invalid_count,
            "total_contacts": new_count, "enrichment_status": "queued" if account and added_count else "waiting_for_sender" if added_count else "idle"}


@router.delete("/lists/{list_id}/contacts/{contact_id}")
async def delete_engage_contact(
    list_id: str,
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if not await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}):
        raise HTTPException(status_code=404, detail="Engagement list not found")
    result = await db.outreach_engage_contacts.delete_one({
        "id": contact_id, "list_id": list_id, "workspace_id": workspace_id,
    })
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.outreach_engage_posts.delete_many({
        "contact_id": contact_id, "list_id": list_id, "workspace_id": workspace_id,
    })
    await db.outreach_engage_drafts.delete_many({
        "contact_id": contact_id, "list_id": list_id, "workspace_id": workspace_id,
    })
    total = await db.outreach_engage_contacts.count_documents({"list_id": list_id, "workspace_id": workspace_id})
    pending = await db.outreach_engage_posts.count_documents({
        "list_id": list_id, "workspace_id": workspace_id, "status": "pending",
    })
    await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id},
        {"$set": {"contacts_count": total, "pending_posts_count": pending}},
    )
    return {"status": "deleted", "contact_id": contact_id}


@router.get("/lists/{list_id}/contacts/{contact_id}/history")
async def get_engage_contact_history(
    list_id: str,
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    contact = await db.outreach_engage_contacts.find_one({
        "id": contact_id, "list_id": list_id, "workspace_id": workspace_id,
    })
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    posts = await db.outreach_engage_posts.find(
        {"contact_id": contact_id, "list_id": list_id, "workspace_id": workspace_id,
         "status": {"$in": ["liked", "commented", "discarded"]}},
        {"_id": 0, "id": 1, "status": 1, "post_url": 1, "published_at": 1,
         "liked_at": 1, "commented_at": 1, "discarded_at": 1, "user_comment": 1},
    ).sort("created_at", -1).to_list(200)
    events = []
    for post in posts:
        for action, at_field in (("liked", "liked_at"), ("commented", "commented_at"), ("discarded", "discarded_at")):
            if post.get(at_field) or post.get("status") == action:
                events.append({"post_id": post["id"], "action": action, "at": post.get(at_field),
                               "post_url": post.get("post_url"),
                               "comment": post.get("user_comment") if action == "commented" else ""})
    def event_time(event: dict) -> datetime:
        value = event.get("at")
        if not isinstance(value, datetime):
            return datetime.min.replace(tzinfo=timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    events.sort(key=event_time, reverse=True)
    return {"contact_id": contact_id, "events": events}


@router.get("/lists/{list_id}/export.csv")
async def export_engage_report(
    list_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if not await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id}):
        raise HTTPException(status_code=404, detail="Engagement list not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Contact", "Action", "Action date (UTC)", "Post URL", "Comment"])
    cursor = db.outreach_engage_posts.find({"list_id": list_id, "workspace_id": workspace_id})

    def safe(value: Any) -> str:
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    async for post in cursor:
        for action, at_field in (("liked", "liked_at"), ("commented", "commented_at"), ("discarded", "discarded_at")):
            if (at := post.get(at_field)) or post.get("status") == action:
                writer.writerow([safe(post.get("author_name")), action, safe(at.isoformat() if isinstance(at, datetime) else at),
                                 safe(post.get("post_url")), safe(post.get("user_comment") if action == "commented" else "")])
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="engage-{list_id}.csv"',
    })


@router.post("/lists/{list_id}/fetch", status_code=status.HTTP_202_ACCEPTED)
async def fetch_latest_posts_for_list(
    list_id: str,
    sender_account_id: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Queue a bounded background fetch; never scrape LinkedIn on the API request path."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    engage_list = await db.outreach_engage_lists.find_one({"id": list_id, "workspace_id": workspace_id})
    if not engage_list:
        raise HTTPException(status_code=404, detail="Engagement list not found")

    contact_count = await db.outreach_engage_contacts.count_documents({"list_id": list_id, "workspace_id": workspace_id})
    if not contact_count:
        return {"status": "empty", "message": "No contacts in list. Add contacts first.", "posts_fetched": 0}

    account = await _resolve_sender_account(workspace_id, db, sender_account_id)
    now = datetime.now(timezone.utc)
    claimed = await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id, "$or": [
            {"fetch_status": {"$nin": ["queued", "running"]}},
            {"fetch_started_at": {"$lt": now - timedelta(hours=2)}},
        ]},
        {"$set": {"fetch_status": "queued", "fetch_error": "", "fetch_started_at": now}},
    )
    if not claimed.modified_count:
        return {"status": "already_running"}
    try:
        from celery_workers.celery_app import celery_app
        celery_app.send_task(
            "celery_workers.tasks.engage.fetch_posts",
            args=[list_id, workspace_id, account["id"]], queue="outreach", ignore_result=True,
            headers={"x-trace-id": get_trace_id() or uuid.uuid4().hex},
        )
    except Exception as exc:
        logger.exception("Failed to queue Engage fetch for %s", list_id)
        await db.outreach_engage_lists.update_one(
            {"id": list_id, "workspace_id": workspace_id},
            {"$set": {"fetch_status": "failed", "fetch_error": str(exc)[:200]}},
        )
        raise HTTPException(status_code=503, detail="Post fetch could not be queued. Please retry.")
    return {"status": "queued", "contacts": contact_count}


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

    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Invalid post pagination")

    query: dict[str, Any] = {"list_id": list_id, "workspace_id": workspace_id}
    if status_filter != "all":
        query["status"] = status_filter

    cursor = db.outreach_engage_posts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    posts = await cursor.to_list(limit)
    contact_ids = list({post.get("contact_id") for post in posts if post.get("contact_id")})
    if contact_ids:
        verified_contacts = await db.outreach_engage_contacts.find({
            "id": {"$in": contact_ids}, "list_id": list_id, "workspace_id": workspace_id,
            "enrichment_status": "verified",
        }, {"id": 1}).to_list(limit)
        verified_ids = {contact["id"] for contact in verified_contacts}
        for post in posts:
            if post.get("contact_id") not in verified_ids:
                post.update({"author_name": "LinkedIn Member", "author_headline": "", "author_avatar": ""})
    total = await db.outreach_engage_posts.count_documents(query)

    return {"posts": posts, "total": total, "status": status_filter}


async def like_engage_post(
    post_id: str,
    req: LikePostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """1-Click Like a post via Voyager with rate limiting and safety checks."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    claimed = await db.outreach_engage_posts.update_one(
        {"id": post_id, "workspace_id": workspace_id, "status": "pending", "$or": [
            {"action_claimed_at": {"$exists": False}},
            {"action_claimed_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=2)}},
        ]},
        {"$set": {"action_claimed_at": datetime.now(timezone.utc)}},
    )
    if not claimed.modified_count:
        raise HTTPException(status_code=409, detail="Post is already being engaged or has been liked.")

    try:
        account = await _resolve_sender_account(workspace_id, db, req.sender_account_id)
        allowed = await OutboundRateLimiter.check_and_increment_daily_limit(account, "post_likes", db)
        if not allowed:
            raise HTTPException(status_code=429, detail="Daily like limit reached for this LinkedIn account.")
        res = await _build_voyager(account).like_update(post["post_urn"])
        await _require_voyager_success(res, "liked", account, db)
        now = datetime.now(timezone.utc)
        await db.outreach_engage_posts.update_one(
            {"id": post_id, "workspace_id": workspace_id},
            {"$set": {"status": "liked", "liked_at": now, "liked_by_account_id": account["id"],
                      "reactions_count": post.get("reactions_count", 0) + 1}},
        )
        pending_count = await db.outreach_engage_posts.count_documents({
            "list_id": post["list_id"], "workspace_id": workspace_id, "status": "pending",
        })
        await db.outreach_engage_lists.update_one(
            {"id": post["list_id"], "workspace_id": workspace_id}, {"$set": {"pending_posts_count": pending_count}},
        )
        return {"status": "liked", "post_id": post_id, "details": res}
    finally:
        await db.outreach_engage_posts.update_one(
            {"id": post_id, "workspace_id": workspace_id}, {"$unset": {"action_claimed_at": ""}},
        )


async def comment_engage_post(
    post_id: str,
    req: CommentPostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Post an in-line comment to LinkedIn with optional auto-like, rate limiting, and safety checks."""
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not req.comment_text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")
    claimed = await db.outreach_engage_posts.update_one(
        {"id": post_id, "workspace_id": workspace_id, "status": {"$in": ["pending", "liked"]}, "$or": [
            {"action_claimed_at": {"$exists": False}},
            {"action_claimed_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=2)}},
        ]},
        {"$set": {"action_claimed_at": datetime.now(timezone.utc)}},
    )
    if not claimed.modified_count:
        raise HTTPException(status_code=409, detail="Post is already being engaged or has been commented on.")

    try:
        account = await _resolve_sender_account(workspace_id, db, req.sender_account_id)
        allowed = await OutboundRateLimiter.check_and_increment_daily_limit(account, "comments", db)
        if not allowed:
            raise HTTPException(status_code=429, detail="Daily comment limit reached for this LinkedIn account.")
        auto_like = bool(req.auto_like and post["status"] == "pending")
        if auto_like:
            account = await db.outreach_accounts.find_one({"id": account["id"], "workspace_id": workspace_id})
            auto_like = await OutboundRateLimiter.check_and_increment_daily_limit(account, "post_likes", db)
        voyager = _build_voyager(account)
        if auto_like:
            res = await voyager.auto_like_and_comment(post["post_urn"], req.comment_text.strip())
            like_res = res.get("like") or {}
            await _require_voyager_success(like_res, "liked", account, db)
            await db.outreach_engage_posts.update_one(
                {"id": post_id, "workspace_id": workspace_id},
                {"$set": {"status": "liked", "liked_at": datetime.now(timezone.utc),
                          "liked_by_account_id": account["id"], "reactions_count": post.get("reactions_count", 0) + 1}},
            )
            comment_res = res.get("comment") or {}
        else:
            res = await voyager.comment_on_update(post["post_urn"], req.comment_text.strip())
            comment_res = res
        await _require_voyager_success(comment_res, "commented", account, db)

        now = datetime.now(timezone.utc)
        await db.outreach_engage_posts.update_one(
            {"id": post_id, "workspace_id": workspace_id},
            {"$set": {"status": "commented", "user_comment": req.comment_text.strip(),
                      "commented_at": now, "commented_by_account_id": account["id"],
                      "comments_count": post.get("comments_count", 0) + 1}},
        )
        pending_count = await db.outreach_engage_posts.count_documents({
            "list_id": post["list_id"], "workspace_id": workspace_id, "status": "pending",
        })
        await db.outreach_engage_lists.update_one(
            {"id": post["list_id"], "workspace_id": workspace_id}, {"$set": {"pending_posts_count": pending_count}},
        )
        return {"status": "commented", "post_id": post_id, "comment": req.comment_text.strip(),
                "auto_liked": auto_like, "timestamp": now.isoformat(), "details": res}
    finally:
        await db.outreach_engage_posts.update_one(
            {"id": post_id, "workspace_id": workspace_id}, {"$unset": {"action_claimed_at": ""}},
        )


async def _queue_engage_action(
    post_id: str,
    workspace_id: str,
    sender_account_id: str | None,
    action: str,
    payload: str | None,
    db: AsyncIOMotorDatabase,
) -> dict:
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    account = await _resolve_sender_account(workspace_id, db, sender_account_id)
    allowed_statuses = ["pending"] if action == "like" else ["pending", "liked"]
    now = datetime.now(timezone.utc)
    action_id = uuid.uuid4().hex
    claimed = await db.outreach_engage_posts.update_one(
        {"id": post_id, "workspace_id": workspace_id, "status": {"$in": allowed_statuses},
         "action_claimed_at": {"$exists": False}, "$or": [
             {"action_queued_at": {"$exists": False}},
             {"action_queued_at": {"$lt": now - timedelta(hours=2)}},
         ]},
        {"$set": {"action_queued_at": now, "action_id": action_id, "action_error": ""}},
    )
    if not claimed.modified_count:
        raise HTTPException(status_code=409, detail="Post is already queued, being engaged, or completed.")
    try:
        from celery_workers.celery_app import celery_app
        celery_app.send_task(
            f"celery_workers.tasks.engage.{action}_post",
            args=[post_id, workspace_id, account["id"], payload, action_id], queue="outreach", ignore_result=True,
            headers={"x-trace-id": get_trace_id() or action_id},
        )
    except Exception as exc:
        await db.outreach_engage_posts.update_one(
            {"id": post_id, "workspace_id": workspace_id, "action_id": action_id},
            {"$unset": {"action_queued_at": "", "action_id": ""},
             "$set": {"action_error": "Could not queue LinkedIn action."}},
        )
        logger.exception("Could not queue Engage %s for post %s", action, post_id)
        raise HTTPException(status_code=503, detail="Could not queue LinkedIn action. Please retry.") from exc
    return {"status": "queued", "post_id": post_id, "action": action}


@router.post("/posts/{post_id}/like", status_code=status.HTTP_202_ACCEPTED)
async def queue_like_engage_post(
    post_id: str,
    req: LikePostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    return await _queue_engage_action(post_id, workspace_id, req.sender_account_id, "like", None, db)


@router.post("/posts/{post_id}/comment", status_code=status.HTTP_202_ACCEPTED)
async def queue_comment_engage_post(
    post_id: str,
    req: CommentPostRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not req.comment_text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    return await _queue_engage_action(post_id, workspace_id, req.sender_account_id, "comment",
                                      json.dumps({"comment_text": req.comment_text.strip(), "auto_like": req.auto_like}), db)


@router.get("/posts/{post_id}/action")
async def get_engage_post_action(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    post = await db.outreach_engage_posts.find_one({"id": post_id, "workspace_id": workspace_id},
                                                  {"_id": 0, "status": 1, "action_queued_at": 1,
                                                   "action_claimed_at": 1, "action_error": 1,
                                                   "liked_at": 1, "commented_at": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


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

    if post.get("status") in {"liked", "commented"}:
        raise HTTPException(status_code=409, detail="Engaged posts cannot be discarded from history.")
    changed = await db.outreach_engage_posts.update_one(
        {"id": post_id, "workspace_id": workspace_id, "status": "pending",
         "action_claimed_at": {"$exists": False}, "action_queued_at": {"$exists": False}},
        {"$set": {"status": "discarded", "discarded_at": datetime.now(timezone.utc)}},
    )
    if not changed.modified_count:
        raise HTTPException(status_code=409, detail="Post is already being engaged.")

    # Decrement pending count on list
    pending_count = await db.outreach_engage_posts.count_documents({"list_id": post["list_id"], "workspace_id": workspace_id, "status": "pending"})
    await db.outreach_engage_lists.update_one({"id": post["list_id"], "workspace_id": workspace_id}, {"$set": {"pending_posts_count": pending_count}})

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
    style_instr = ""
    if req.writing_style_id:
        workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
        style = await db.outreach_writing_styles.find_one({
            "id": req.writing_style_id, "workspace_id": workspace_id,
        })
        if not style:
            raise HTTPException(status_code=404, detail="Writing style not found")
        style_instr = f"\nWriting style: {style.get('extracted_style_prompt', '')[:1000]}"

    system_prompt = (
        "You are an elite LinkedIn ghostwriter and B2B engagement specialist. "
        "Your task is to write 3 distinct, high-value LinkedIn comments for the provided post.\n\n"
        "Strict Guidelines:\n"
        "1. NEVER use generic corporate filler: 'Great post!', '100% agree!', 'Thanks for sharing!', 'Spot on!'.\n"
        "2. Add genuine intellectual or operational value that encourages the author to reply back.\n"
        "3. Keep each comment concise: 1 to 3 punchy sentences (under 45 words).\n"
        "4. Tone objective: " + tone_guidance + style_instr + "\n\n"
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
        logger.warning("AI comment generation failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI comments are temporarily unavailable. Please write a comment manually.") from exc

    raise HTTPException(status_code=502, detail="AI did not return usable comments. Please retry or write one manually.")
