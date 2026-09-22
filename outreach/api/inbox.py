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


@router.get("")
async def list_inbox_threads(
    account_id: str | None = Query(None, description="Filter by sender account id or null for All"),
    search: str | None = Query(None, description="Search prospect name or message snippet"),
    intent: str | None = Query(None, description="Filter by intent tag"),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of inbox threads matching Part 3, Image 1.
    """
    user_id = current_user.get("user_id")
    filter_q: dict[str, Any] = {"workspace_id": user_id}

    if account_id and account_id not in ("all", "All", ""):
        filter_q["account_id"] = account_id

    if intent and intent not in ("all", "All"):
        filter_q["intent_tag"] = intent

    if search and search.strip():
        term = search.strip()
        filter_q["$or"] = [
            {"lead_name": {"$regex": term, "$options": "i"}},
            {"last_message_snippet": {"$regex": term, "$options": "i"}},
        ]

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
    thread = await db.outreach_inbox_threads.find_one({"id": thread_id, "workspace_id": user_id})
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
    thread = await db.outreach_inbox_threads.find_one({"id": thread_id, "workspace_id": user_id})
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    account_id = thread.get("account_id")
    account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": user_id})
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The assigned sender account for this thread is no longer available.",
        )

    proxy_url = None
    if account.get("proxy_config"):
        proxy_url = JITProxyManager.format_proxy_url(account["proxy_config"])

    client = VoyagerClient(
        session_cookie_enc=account.get("encrypted_session_cookie", ""),
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
        sender_name=account.get("name", "You"),
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
    syncer = InboxSynchronizer(db=db, workspace_id=user_id)

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
    Updates the intent classification tag for a lead conversation.
    """
    user_id = current_user.get("user_id")
    res = await db.outreach_inbox_threads.update_one(
        {"id": thread_id, "workspace_id": user_id},
        {"$set": {"intent_tag": req.intent_tag}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return {"status": "updated", "thread_id": thread_id, "intent_tag": req.intent_tag}
