"""Inbox — social comments/DMs stub (read-only, data from social sync)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inbox"])


@router.get("/inbox")
async def list_inbox(
    current_user: CurrentUser,
    db: DB,
    platform: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    query: dict = {"workspace_id": workspace_id}
    if platform:
        query["platform"] = platform
    if status:
        query["status"] = status
    cursor = db.inbox_messages.find(query, {"_id": 0}).sort("received_at", -1).limit(limit)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("message_id", ""))
    return docs


@router.get("/inbox/stats")
async def inbox_stats(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    import asyncio
    async def _count(q):
        return await db.inbox_messages.count_documents(q)
    total, unread, comments, dms = await asyncio.gather(
        _count({"workspace_id": workspace_id}),
        _count({"workspace_id": workspace_id, "is_read": False}),
        _count({"workspace_id": workspace_id, "type": "comment"}),
        _count({"workspace_id": workspace_id, "type": "dm"}),
    )
    return {"total": total, "unread": unread, "comments": comments, "dms": dms}


@router.patch("/inbox/{message_id}")
async def update_inbox_message(message_id: str, body: dict, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    allowed = {k: v for k, v in body.items() if k in {"is_read", "status", "assigned_to"}}
    if not allowed:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    allowed["updated_at"] = datetime.now(timezone.utc)
    result = await db.inbox_messages.find_one_and_update(
        {"$or": [{"message_id": message_id}, {"id": message_id}], "workspace_id": workspace_id},
        {"$set": allowed},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.delete("/inbox/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbox_message(message_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    await db.inbox_messages.delete_one(
        {"$or": [{"message_id": message_id}, {"id": message_id}], "workspace_id": workspace_id}
    )


@router.post("/inbox")
async def create_inbox_message(body: dict, current_user: CurrentUser, db: DB):
    """Manual message creation (for testing)."""
    import uuid
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    message_id = str(uuid.uuid4())
    doc = {
        "message_id": message_id,
        "id": message_id,
        "workspace_id": workspace_id,
        **{k: v for k, v in body.items() if k not in {"workspace_id", "id", "message_id"}},
        "received_at": now.isoformat(),
        "is_read": False,
    }
    await db.inbox_messages.insert_one(doc)
    doc.pop("_id", None)
    return doc
