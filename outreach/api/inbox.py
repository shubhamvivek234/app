"""
Phase 7: Multi-Account Unified Inbox API Router for LinkedIn Outreach Engine.
Allows viewing unified conversations across all senders, searching threads,
sending direct replies, and manual syncing.
"""
import os
import re
import uuid
import logging
import json
from typing import Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.models import MessageSenderType
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["LinkedIn Unified Inbox"])


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 1000) -> list[dict[str, Any]]:
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


class ReplyRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)


class UpdateIntentRequest(BaseModel):
    intent_tag: str = Field(..., pattern="^(interested|objection|not_interested)$")


class AIReplyResponse(BaseModel):
    suggestions: list[str]


@router.get("")
async def list_inbox_threads(
    account_id: str | None = Query(None, description="Filter by sender account id or null for All"),
    source: str | None = Query(None, description="Filter by source: 'outreach' (Unravler) or 'all'"),
    search: str | None = Query(None, description="Search prospect name or message snippet"),
    intent: str | None = Query(None, description="Filter by intent tag"),
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of inbox threads matching media_1790103710555.png with Unravler/All source filtering.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Invalid inbox pagination")

    acc_id = account_id if isinstance(account_id, str) else None
    src = source if isinstance(source, str) else None
    srch = search.strip() if isinstance(search, str) and search.strip() else None
    intnt = intent if isinstance(intent, str) else None

    base_conditions: list[dict[str, Any]] = [{"workspace_id": ws_id}]
    if os.getenv("OUTREACH_MOCK_AUTH", "false").lower() not in {"true", "1"}:
        base_conditions.append({"is_demo": {"$ne": True}})

    if acc_id and acc_id not in ("all", "All", ""):
        base_conditions.append({"account_id": acc_id})

    if intnt and intnt not in ("all", "All"):
        base_conditions.append({"intent_tag": intnt})

    if src == "outreach":
        base_conditions.append({
            "$or": [
                {"is_outreach": True},
                {"campaign_id": {"$exists": True, "$ne": None}},
            ]
        })

    if srch:
        pattern = re.escape(srch[:100])
        base_conditions.append({
            "$or": [
                {"lead_name": {"$regex": pattern, "$options": "i"}},
                {"last_message_snippet": {"$regex": pattern, "$options": "i"}},
            ]
        })

    filter_q: dict[str, Any] = {"$and": base_conditions} if len(base_conditions) > 1 else base_conditions[0]

    cursor = db.outreach_inbox_threads.find(filter_q).sort("last_message_at", -1)
    if skip:
        cursor = cursor.skip(skip)
    threads = await _fetch_cursor_docs(cursor, length=limit)

    clean_threads = []
    for t in threads:
        doc = dict(t)
        doc.pop("_id", None)
        clean_threads.append(doc)

    return clean_threads


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns full message history for a conversation thread and resets unread count.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    # Reset unread
    await db.outreach_inbox_threads.update_one({"id": thread_id, "workspace_id": ws_id}, {"$set": {"unread_count": 0}})

    doc = dict(thread)
    doc.pop("_id", None)
    doc["unread_count"] = 0
    return doc


@router.post("/{thread_id}/reply", status_code=status.HTTP_202_ACCEPTED)
async def send_thread_reply(
    thread_id: str,
    req: ReplyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Queues a reply on the assigned sender and records it only after LinkedIn confirms delivery.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    account_id = thread.get("account_id")
    account = None
    if account_id and account_id not in ("all", "All"):
        account = await db.outreach_accounts.find_one({
            "id": account_id,
            "workspace_id": ws_id,
        })
    if thread.get("is_demo"):
        raise HTTPException(status_code=409, detail="Sample conversations cannot be sent to LinkedIn")
    if not account or account.get("status") != "active" or not (account.get("session_cookie_enc") or account.get("encrypted_session_cookie")):
        raise HTTPException(status_code=409, detail="The assigned sender account is unavailable")
    if not thread.get("conversation_urn"):
        raise HTTPException(status_code=409, detail="This conversation has no verified LinkedIn thread ID. Sync it first.")
    if not req.body.strip():
        raise HTTPException(status_code=422, detail="Reply cannot be blank")
    pending = await db.outreach_inbox_jobs.count_documents({
        "workspace_id": ws_id, "thread_id": thread_id, "kind": "reply",
        "status": {"$in": ["queued", "running"]},
    })
    if pending:
        raise HTTPException(status_code=409, detail="A reply is already being sent for this conversation")

    from celery_workers.tasks.outreach import send_inbox_reply
    job_id = f"inbox_{uuid.uuid4().hex}"
    await db.outreach_inbox_jobs.insert_one({
        "id": job_id, "kind": "reply", "workspace_id": ws_id, "user_id": user_id,
        "thread_id": thread_id, "status": "queued", "created_at": datetime.now(timezone.utc),
    })
    try:
        send_inbox_reply.apply_async(args=(job_id, ws_id, account_id, thread_id, req.body.strip()), queue="outreach")
    except Exception as exc:
        logger.exception("Could not queue inbox reply")
        await db.outreach_inbox_jobs.update_one({"id": job_id, "workspace_id": ws_id}, {"$set": {"status": "failed"}})
        raise HTTPException(status_code=503, detail="Reply queue is unavailable") from exc
    return {"status": "queued", "job_id": job_id}


@router.post("/{thread_id}/ai-reply", response_model=AIReplyResponse)
async def generate_ai_reply_options(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Generates 3 contextual AI response suggestions for the active conversation.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    lead_name = thread.get("lead_name", "there").split()[0]
    lead_messages = [m.get("body", "") for m in thread.get("messages", []) if m.get("sender_type") == "lead"]
    context = lead_messages[-1] if lead_messages else thread.get("last_message_snippet", "")
    try:
        generated, _, _ = await free_llm.generate_text(
            "Write exactly three distinct, concise LinkedIn reply suggestions as a JSON array of strings. "
            "Use only facts in the prospect's message. Do not invent prices, calendar links, claims, or commitments. "
            "One answer should ask a useful clarifying question, one should be direct, and one should politely defer.",
            f"Prospect name: {lead_name}\nTheir latest message: {context[:2000]}",
            response_json=True,
        )
        parsed = json.loads(generated)
        if isinstance(parsed, dict):
            parsed = parsed.get("suggestions")
        if not isinstance(parsed, list) or len(parsed) != 3 or not all(isinstance(item, str) and item.strip() for item in parsed):
            raise ValueError("AI returned an invalid suggestion set")
        if any(url not in context for item in parsed for url in re.findall(r"https?://\S+", item)):
            raise ValueError("AI introduced a link that was not in the conversation")
        return AIReplyResponse(suggestions=[item.strip()[:1000] for item in parsed])
    except Exception as exc:
        logger.warning("Inbox AI suggestions failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI suggestions are unavailable. Please try again.") from exc


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_inbox_sync(
    account_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Queues a Voyager sync for the selected sender or all active senders.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    selected = account_id if isinstance(account_id, str) and account_id not in ("all", "All", "") else None
    if selected:
        account = await db.outreach_accounts.find_one({"id": selected, "workspace_id": ws_id, "status": "active"})
        if not account:
            raise HTTPException(status_code=404, detail="Active sender account not found")
    else:
        active_count = await db.outreach_accounts.count_documents({"workspace_id": ws_id, "status": "active"})
        if not active_count:
            raise HTTPException(status_code=409, detail="Connect an active sender account before syncing")
    if await db.outreach_inbox_jobs.count_documents({
        "workspace_id": ws_id, "kind": "sync", "account_id": selected,
        "status": {"$in": ["queued", "running"]},
    }):
        raise HTTPException(status_code=409, detail="An inbox sync is already running")

    from celery_workers.tasks.outreach import sync_inbox
    job_id = f"inbox_{uuid.uuid4().hex}"
    await db.outreach_inbox_jobs.insert_one({
        "id": job_id, "kind": "sync", "workspace_id": ws_id, "user_id": user_id,
        "account_id": selected, "status": "queued", "created_at": datetime.now(timezone.utc),
    })
    try:
        sync_inbox.apply_async(args=(job_id, ws_id, user_id, selected), queue="outreach")
    except Exception as exc:
        logger.exception("Could not queue inbox sync")
        await db.outreach_inbox_jobs.update_one({"id": job_id, "workspace_id": ws_id}, {"$set": {"status": "failed"}})
        raise HTTPException(status_code=503, detail="Inbox sync queue is unavailable") from exc
    return {"status": "queued", "job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_inbox_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    job = await db.outreach_inbox_jobs.find_one({"id": job_id, "workspace_id": ws_id})
    if not job:
        raise HTTPException(status_code=404, detail="Inbox job not found")
    return {key: value for key, value in job.items() if key not in {"_id", "user_id"}}


@router.post("/seed-demo")
async def seed_demo_threads(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Seeds realistic sample LinkedIn conversation threads into the unified inbox.
    """
    if os.getenv("OUTREACH_MOCK_AUTH", "false").lower() not in {"true", "1"}:
        raise HTTPException(status_code=404, detail="Not found")
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)

    demo_threads = [
        {
            "id": f"th_demo_jordan_{uuid.uuid4().hex[:6]}",
            "user_id": user_id,
            "workspace_id": ws_id,
            "account_id": "all",
            "campaign_id": "cmp_outbound_alpha",
            "campaign_name": "SaaS Leaders Outbound",
            "is_outreach": True,
            "is_demo": True,
            "lead_name": "Jordan Davis",
            "lead_headline": "Head of Growth at FinTech Labs",
            "lead_avatar": "",
            "lead_urn": "urn:li:fsd_profile:ACoAABuilder1",
            "last_message_snippet": "Thanks for reaching out! Would love to chat next week.",
            "last_message_at": now - timedelta(minutes=15),
            "unread_count": 1,
            "intent_tag": "interested",
            "tags": ["Hot lead"],
            "messages": [
                {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "sender_type": MessageSenderType.USER,
                    "sender_name": "You",
                    "body": "Hey Jordan, saw your team at FinTech Labs is scaling outbound operations!",
                    "timestamp": now - timedelta(hours=3),
                },
                {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "sender_type": MessageSenderType.LEAD,
                    "sender_name": "Jordan Davis",
                    "body": "Thanks for reaching out! Would love to chat next week. What does your schedule look like?",
                    "timestamp": now - timedelta(minutes=15),
                },
            ],
        },
        {
            "id": f"th_demo_elena_{uuid.uuid4().hex[:6]}",
            "user_id": user_id,
            "workspace_id": ws_id,
            "account_id": "all",
            "campaign_id": "cmp_outbound_alpha",
            "campaign_name": "SaaS Leaders Outbound",
            "is_outreach": True,
            "is_demo": True,
            "lead_name": "Elena Rostova",
            "lead_headline": "VP of Revenue Operations @ CloudScale",
            "lead_avatar": "",
            "lead_urn": "urn:li:fsd_profile:ACoAABuilder2",
            "last_message_snippet": "Can you share what the pricing structure looks like?",
            "last_message_at": now - timedelta(hours=5),
            "unread_count": 0,
            "intent_tag": "objection",
            "tags": ["Wants to speak later"],
            "messages": [
                {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "sender_type": MessageSenderType.USER,
                    "sender_name": "You",
                    "body": "Hi Elena, noticed your recent post on RevOps automation metrics—spot on!",
                    "timestamp": now - timedelta(days=1),
                },
                {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "sender_type": MessageSenderType.LEAD,
                    "sender_name": "Elena Rostova",
                    "body": "Thanks for connecting! Can you share what the pricing structure looks like?",
                    "timestamp": now - timedelta(hours=5),
                },
            ],
        },
    ]

    for dt in demo_threads:
        await db.outreach_inbox_threads.insert_one(dict(dt))

    return {"status": "seeded", "count": len(demo_threads)}


@router.patch("/{thread_id}/intent")
async def update_thread_intent(
    thread_id: str,
    req: UpdateIntentRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Updates the intent classification tag for a lead conversation and reconciles campaign metrics.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    old_intent = thread.get("intent_tag")
    await db.outreach_inbox_threads.update_one(
        {"id": thread_id, "workspace_id": ws_id},
        {"$set": {"intent_tag": req.intent_tag, "intent_source": "manual"}},
    )

    if old_intent != req.intent_tag and thread.get("campaign_id"):
        interested_count = await db.outreach_inbox_threads.count_documents({
            "workspace_id": ws_id, "campaign_id": thread["campaign_id"], "intent_tag": "interested",
        })
        await db.outreach_campaigns.update_one(
            {"id": thread["campaign_id"], "workspace_id": ws_id},
            {"$set": {"interested_count": interested_count}},
        )

    return {"status": "updated", "thread_id": thread_id, "intent_tag": req.intent_tag}


# ── Reminders, Snippets & Tags DTOs ────────────────────────────────────────

class CreateReminderRequest(BaseModel):
    remind_at: datetime
    note: str = Field(default="", max_length=500)


class CreateSnippetRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1, max_length=4000)
    shortcut: str = Field(default="", max_length=40)


class CreateTagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    color: str = Field(default="#6366f1", pattern="^#[0-9a-fA-F]{6}$")


class ToggleTagRequest(BaseModel):
    tag_name: str = Field(..., min_length=1, max_length=60)


# ── Reminders Endpoints ───────────────────────────────────────────────────

@router.post("/{thread_id}/reminders")
async def create_thread_reminder(
    thread_id: str,
    req: CreateReminderRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Schedules a follow-up reminder for a conversation thread."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    remind_at = req.remind_at.replace(tzinfo=timezone.utc) if req.remind_at.tzinfo is None else req.remind_at.astimezone(timezone.utc)
    if remind_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Reminder time must be in the future")

    import uuid
    reminder_id = f"rem_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": reminder_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "workspace_id": ws_id,
        "remind_at": remind_at,
        "note": req.note,
        "is_completed": False,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_inbox_reminders.insert_one(doc)
    await db.outreach_inbox_threads.update_one(
        {"id": thread_id, "workspace_id": ws_id},
        {"$set": {"remind_at": remind_at, "reminder_note": req.note}},
    )

    doc.pop("_id", None)
    return {"status": "created", "reminder": doc}


@router.get("/{thread_id}/reminders")
async def list_thread_reminders(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Fetches reminders for a specific thread."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    thread = await db.outreach_inbox_threads.find_one({"id": thread_id, "workspace_id": ws_id})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    cursor = db.outreach_inbox_reminders.find({
        "thread_id": thread_id,
        "workspace_id": ws_id,
    }).sort("remind_at", 1)

    items = await _fetch_cursor_docs(cursor, length=50)
    for it in items:
        it.pop("_id", None)
    return items


@router.delete("/reminders/{reminder_id}")
async def delete_thread_reminder(
    reminder_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes or cancels a reminder."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    rem = await db.outreach_inbox_reminders.find_one({
        "id": reminder_id,
        "workspace_id": ws_id,
    })
    if not rem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")

    await db.outreach_inbox_reminders.delete_one({"id": reminder_id, "workspace_id": ws_id})
    next_reminders = await _fetch_cursor_docs(db.outreach_inbox_reminders.find({
        "thread_id": rem["thread_id"], "workspace_id": ws_id,
    }).sort("remind_at", 1), length=1)
    next_reminder = next_reminders[0] if next_reminders else None
    if next_reminder:
        await db.outreach_inbox_threads.update_one(
            {"id": rem["thread_id"], "workspace_id": ws_id},
            {"$set": {"remind_at": next_reminder["remind_at"], "reminder_note": next_reminder.get("note", "")}},
        )
    else:
        await db.outreach_inbox_threads.update_one(
            {"id": rem["thread_id"], "workspace_id": ws_id},
            {"$unset": {"remind_at": "", "reminder_note": ""}},
        )
    return {"status": "deleted", "reminder_id": reminder_id, "next_reminder": next_reminder and {
        "id": next_reminder["id"], "remind_at": next_reminder["remind_at"], "note": next_reminder.get("note", ""),
    }}


# ── Snippets Endpoints ────────────────────────────────────────────────────

DEFAULT_SNIPPETS = [
    {
        "title": "Calendar link",
        "body": "I'd be happy to share a calendar link if you'd like to schedule a call.",
        "shortcut": "cal",
    },
    {
        "title": "Pricing list",
        "body": "I can share current pricing and help identify which plan fits your needs.",
        "shortcut": "price",
    },
    {
        "title": "More info",
        "body": "Happy to send a concise overview. Which part would be most useful to learn more about?",
        "shortcut": "info",
    },
]

LEGACY_SNIPPET_REPLACEMENTS = {
    "Let's do it. Here's my calendar link: https://calendly.com/unravler/30min": DEFAULT_SNIPPETS[0]["body"],
    "Here's our pricing: Starter is $49/mo, Pro is $99/mo with unlimited sender accounts.": DEFAULT_SNIPPETS[1]["body"],
    "No problem! Here's a brief overview of how our automated LinkedIn sequences and pre-warming work: https://unravler.com/features": DEFAULT_SNIPPETS[2]["body"],
}

@router.get("/snippets/list")
async def list_snippets(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists saved reply snippets. Seeds standard defaults if empty."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    cursor = db.outreach_inbox_snippets.find({
        "workspace_id": ws_id,
    }).sort("created_at", 1)

    items = await _fetch_cursor_docs(cursor, length=100)
    if not items:
        # Seed defaults
        import uuid
        seeded = []
        for def_s in DEFAULT_SNIPPETS:
            doc = {
                "id": f"snp_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "workspace_id": ws_id,
                **def_s,
                "created_at": datetime.now(timezone.utc),
            }
            await db.outreach_inbox_snippets.insert_one(doc)
            doc.pop("_id", None)
            seeded.append(doc)
        return seeded

    for it in items:
        replacement = LEGACY_SNIPPET_REPLACEMENTS.get(it.get("body"))
        if replacement:
            await db.outreach_inbox_snippets.update_one(
                {"id": it["id"], "workspace_id": ws_id, "body": it["body"]},
                {"$set": {"body": replacement}},
            )
            it["body"] = replacement
        it.pop("_id", None)
    return items


@router.post("/snippets")
async def create_snippet(
    req: CreateSnippetRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Creates a new reusable saved reply snippet."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    if not req.title.strip() or not req.body.strip():
        raise HTTPException(status_code=422, detail="Snippet title and body cannot be blank")

    import uuid
    doc = {
        "id": f"snp_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "workspace_id": ws_id,
        "title": req.title.strip(),
        "body": req.body.strip(),
        "shortcut": req.shortcut.strip(),
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_inbox_snippets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/snippets/{snippet_id}")
async def delete_snippet(
    snippet_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a saved snippet."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    res = await db.outreach_inbox_snippets.delete_one({
        "id": snippet_id,
        "workspace_id": ws_id,
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snippet not found")
    return {"status": "deleted", "snippet_id": snippet_id}


# ── Tags Endpoints ────────────────────────────────────────────────────────

DEFAULT_TAGS = [
    {"name": "Wants to speak later", "color": "#a855f7"},
    {"name": "Hot lead", "color": "#ef4444"},
    {"name": "Potential Partner", "color": "#3b82f6"},
    {"name": "Sequence 1", "color": "#ec4899"},
    {"name": "Sequence 2", "color": "#06b6d4"},
]

@router.get("/tags/list")
async def list_tags(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists inbox tags with colored indicators. Seeds defaults if empty."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    cursor = db.outreach_inbox_tags.find({
        "workspace_id": ws_id,
    }).sort("created_at", 1)

    items = await _fetch_cursor_docs(cursor, length=100)
    if not items:
        import uuid
        seeded = []
        for def_t in DEFAULT_TAGS:
            doc = {
                "id": f"tag_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "workspace_id": ws_id,
                **def_t,
                "created_at": datetime.now(timezone.utc),
            }
            await db.outreach_inbox_tags.insert_one(doc)
            doc.pop("_id", None)
            seeded.append(doc)
        return seeded

    for it in items:
        it.pop("_id", None)
    return items


@router.post("/tags")
async def create_tag(
    req: CreateTagRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Creates a custom lead tag with color."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="Tag name cannot be blank")
    existing = await db.outreach_inbox_tags.find_one({"workspace_id": ws_id, "name": req.name.strip()})
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")

    import uuid
    doc = {
        "id": f"tag_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "workspace_id": ws_id,
        "name": req.name.strip(),
        "color": req.color,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_inbox_tags.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes an inbox tag."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    tag = await db.outreach_inbox_tags.find_one({"id": tag_id, "workspace_id": ws_id})
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    res = await db.outreach_inbox_tags.delete_one({
        "id": tag_id,
        "workspace_id": ws_id,
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if hasattr(db.outreach_inbox_threads, "update_many"):
        await db.outreach_inbox_threads.update_many(
            {"workspace_id": ws_id, "tags": tag["name"]},
            {"$pull": {"tags": tag["name"]}},
        )
    return {"status": "deleted", "tag_id": tag_id}


@router.patch("/{thread_id}/tags")
async def toggle_thread_tag(
    thread_id: str,
    req: ToggleTagRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Toggles a tag on or off a thread."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "workspace_id": ws_id,
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    existing_tags = thread.get("tags") or []
    tag_name = req.tag_name.strip()
    if not tag_name or not await db.outreach_inbox_tags.find_one({"workspace_id": ws_id, "name": tag_name}):
        raise HTTPException(status_code=404, detail="Tag not found")

    if tag_name in existing_tags:
        new_tags = [t for t in existing_tags if t != tag_name]
    else:
        new_tags = existing_tags + [tag_name]

    await db.outreach_inbox_threads.update_one(
        {"id": thread_id, "workspace_id": ws_id},
        {"$set": {"tags": new_tags}},
    )

    return {"status": "updated", "thread_id": thread_id, "tags": new_tags}
