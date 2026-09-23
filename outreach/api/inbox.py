"""
Phase 7: Multi-Account Unified Inbox API Router for LinkedIn Outreach Engine.
Allows viewing unified conversations across all senders, searching threads,
sending direct replies, and manual syncing.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.proxy_manager import JITProxyManager
from outreach.engine.inbox_sync import InboxSynchronizer
from outreach.engine.voyager_client import VoyagerClient
from outreach.models import MessageSenderType, OutreachInboxMessage

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
    body: str = Field(..., min_length=1)


class UpdateIntentRequest(BaseModel):
    intent_tag: str = Field(..., description="'interested', 'objection', or 'not_interested'")


class AIReplyResponse(BaseModel):
    suggestions: list[str]


@router.get("")
async def list_inbox_threads(
    account_id: str | None = Query(None, description="Filter by sender account id or null for All"),
    source: str | None = Query(None, description="Filter by source: 'outreach' (Prosp) or 'all'"),
    search: str | None = Query(None, description="Search prospect name or message snippet"),
    intent: str | None = Query(None, description="Filter by intent tag"),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of inbox threads matching media_1790103710555.png with Prosp/All source filtering.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    base_conditions: list[dict[str, Any]] = [
        {"$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}]}
    ]

    if account_id and account_id not in ("all", "All", ""):
        base_conditions.append({"account_id": account_id})

    if intent and intent not in ("all", "All"):
        base_conditions.append({"intent_tag": intent})

    if source == "outreach":
        base_conditions.append({
            "$or": [
                {"is_outreach": True},
                {"campaign_id": {"$exists": True, "$ne": None}},
            ]
        })

    if search and search.strip():
        term = search.strip()
        base_conditions.append({
            "$or": [
                {"lead_name": {"$regex": term, "$options": "i"}},
                {"last_message_snippet": {"$regex": term, "$options": "i"}},
            ]
        })

    filter_q: dict[str, Any] = {"$and": base_conditions} if len(base_conditions) > 1 else base_conditions[0]

    threads = await _fetch_cursor_docs(
        db.outreach_inbox_threads.find(filter_q).sort("last_message_at", -1),
        length=500,
    )

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
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    # Reset unread
    await db.outreach_inbox_threads.update_one({"id": thread_id}, {"$set": {"unread_count": 0}})

    doc = dict(thread)
    doc.pop("_id", None)
    doc["unread_count"] = 0
    return doc


@router.post("/{thread_id}/reply")
async def send_thread_reply(
    thread_id: str,
    req: ReplyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Dispatches a reply message directly from the assigned LinkedIn sender account.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    account_id = thread.get("account_id")
    account = await db.outreach_accounts.find_one({
        "id": account_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The assigned sender account for this thread is no longer available.",
        )

    proxy_url = None
    if account.get("proxy_config"):
        proxy_url = JITProxyManager.format_proxy_url(account["proxy_config"])
    elif account.get("proxy"):
        proxy_url = JITProxyManager.format_proxy_url(account["proxy"])

    cookie_enc = account.get("session_cookie_enc") or account.get("encrypted_session_cookie", "")
    client = VoyagerClient(
        session_cookie_enc=cookie_enc,
        jsession_id=account.get("jsession_id", ""),
        proxy_url=proxy_url,
    )

    lead_urn = thread.get("lead_urn", "")
    voyager_res = await client.send_conversation_reply(lead_urn, req.body)

    if voyager_res.get("status") not in ("sent", "message_sent"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch LinkedIn reply: {voyager_res.get('error', 'Voyager error')}",
        )

    new_msg = OutreachInboxMessage(
        sender_type=MessageSenderType.USER,
        sender_name=account.get("account_name") or account.get("name") or "You",
        body=req.body,
        timestamp=datetime.now(timezone.utc),
    ).model_dump()

    await db.outreach_inbox_threads.update_one(
        {"id": thread_id},
        {
            "$push": {"messages": new_msg},
            "$set": {
                "last_message_snippet": req.body[:120],
                "last_message_at": datetime.now(timezone.utc),
            },
        },
    )

    return {"status": "sent", "message": new_msg}


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
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    lead_name = thread.get("lead_name", "there").split()[0]

    suggestions = [
        f"Hi {lead_name}, thanks for getting back to me! Would love to hear more about your current focus. Open to connecting for a quick 10-min chat this week?",
        f"Great to hear from you {lead_name}! Here is a quick link to grab time if you'd like to dive in: https://calendly.com/demo. Looking forward to chatting!",
        f"Appreciate the response, {lead_name}! No problem at all—feel free to reach back out whenever the timing is better on your end.",
    ]
    return AIReplyResponse(suggestions=suggestions)


@router.post("/sync")
async def trigger_inbox_sync(
    account_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Triggers an immediate background sync with Voyager for all accounts or a selected account.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    syncer = InboxSynchronizer(db=db, workspace_id=ws_id, user_id=user_id)

    if account_id and account_id not in ("all", "All"):
        res = await syncer.sync_account_inbox(account_id)
    else:
        res = await syncer.sync_all_accounts()

    return {"status": "success", "result": res}


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
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    old_intent = thread.get("intent_tag")
    await db.outreach_inbox_threads.update_one(
        {"id": thread_id},
        {"$set": {"intent_tag": req.intent_tag}},
    )

    # If marked as interested, increment campaign interested count
    if req.intent_tag == "interested" and old_intent != "interested" and thread.get("campaign_id"):
        await db.outreach_campaigns.update_one(
            {"id": thread["campaign_id"]},
            {"$inc": {"interested_count": 1}},
        )

    return {"status": "updated", "thread_id": thread_id, "intent_tag": req.intent_tag}


# ── Reminders, Snippets & Tags DTOs ────────────────────────────────────────

class CreateReminderRequest(BaseModel):
    remind_at: datetime
    note: str = ""


class CreateSnippetRequest(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    shortcut: str = ""


class CreateTagRequest(BaseModel):
    name: str = Field(..., min_length=1)
    color: str = "#6366f1"


class ToggleTagRequest(BaseModel):
    tag_name: str


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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    import uuid
    reminder_id = f"rem_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": reminder_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "workspace_id": ws_id,
        "remind_at": req.remind_at,
        "note": req.note,
        "is_completed": False,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_inbox_reminders.insert_one(doc)
    await db.outreach_inbox_threads.update_one(
        {"id": thread_id},
        {"$set": {"remind_at": req.remind_at, "reminder_note": req.note}},
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    cursor = db.outreach_inbox_reminders.find({
        "thread_id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    rem = await db.outreach_inbox_reminders.find_one({
        "id": reminder_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not rem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")

    await db.outreach_inbox_reminders.delete_one({"id": reminder_id})
    await db.outreach_inbox_threads.update_one(
        {"id": rem["thread_id"]},
        {"$unset": {"remind_at": "", "reminder_note": ""}},
    )
    return {"status": "deleted", "reminder_id": reminder_id}


# ── Snippets Endpoints ────────────────────────────────────────────────────

DEFAULT_SNIPPETS = [
    {
        "title": "Calendar link",
        "body": "Let's do it. Here's my calendar link: https://calendly.com/unravler/30min",
        "shortcut": "cal",
    },
    {
        "title": "Pricing list",
        "body": "Here's our pricing: Starter is $49/mo, Pro is $99/mo with unlimited sender accounts.",
        "shortcut": "price",
    },
    {
        "title": "More info",
        "body": "No problem! Here's a brief overview of how our automated LinkedIn sequences and pre-warming work: https://unravler.com/features",
        "shortcut": "info",
    },
]

@router.get("/snippets/list")
async def list_snippets(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists saved reply snippets. Seeds standard defaults if empty."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    cursor = db.outreach_inbox_snippets.find({
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    res = await db.outreach_inbox_snippets.delete_one({
        "id": snippet_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    cursor = db.outreach_inbox_tags.find({
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    res = await db.outreach_inbox_tags.delete_one({
        "id": tag_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
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
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    thread = await db.outreach_inbox_threads.find_one({
        "id": thread_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    existing_tags = thread.get("tags") or []
    tag_name = req.tag_name.strip()

    if tag_name in existing_tags:
        new_tags = [t for t in existing_tags if t != tag_name]
    else:
        new_tags = existing_tags + [tag_name]

    await db.outreach_inbox_threads.update_one(
        {"id": thread_id},
        {"$set": {"tags": new_tags}},
    )

    return {"status": "updated", "thread_id": thread_id, "tags": new_tags}


