"""Notifications — list, mark read, delete."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    message: str
    is_read: bool = False
    metadata: dict = {}
    created_at: datetime


@router.get("/notifications")
async def list_notifications(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
):
    user_id = current_user["user_id"]
    query: dict = {"user_id": user_id}
    if unread_only:
        query["is_read"] = False
    cursor = db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(None)
    # Normalize id field
    for d in docs:
        if "notification_id" in d and "id" not in d:
            d["id"] = d["notification_id"]
        d.setdefault("id", str(d.get("_id", "")))
        d.setdefault("type", "info")
        d.setdefault("message", "")
        d.setdefault("metadata", {})
        d.setdefault("is_read", False)
    return docs


@router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    db: DB,
):
    user_id = current_user["user_id"]
    result = await db.notifications.update_one(
        {"$or": [{"notification_id": notification_id}, {"id": notification_id}], "user_id": user_id},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}},
    )
    return {"updated": result.modified_count > 0}


@router.patch("/notifications/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(current_user: CurrentUser, db: DB):
    user_id = current_user["user_id"]
    result = await db.notifications.update_many(
        {"user_id": user_id, "is_read": False},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}},
    )
    return {"updated": result.modified_count}


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: CurrentUser,
    db: DB,
):
    user_id = current_user["user_id"]
    await db.notifications.delete_one(
        {"$or": [{"notification_id": notification_id}, {"id": notification_id}], "user_id": user_id},
    )
