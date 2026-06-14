"""Notifications — list, mark read, delete."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from bson import ObjectId
from pydantic import BaseModel

from api.deps import CurrentUser, DB
from utils.notifications import IMPORTANT_NOTIFICATION_EVENTS, IMPORTANT_NOTIFICATION_TYPES

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


def _in_app_notification_query(user_id: str) -> dict:
    return {
        "$and": [
            {
                "user_id": user_id,
                "$or": [
                    {"channel": {"$exists": False}},
                    {"channel": {"$ne": "email"}},
                ],
            },
            {
                "$or": [
                    {"event": {"$in": list(IMPORTANT_NOTIFICATION_EVENTS)}},
                    {"type": {"$in": list(IMPORTANT_NOTIFICATION_TYPES)}},
                ]
            },
        ],
    }


def _unread_query() -> dict:
    return {
        "$or": [
            {"is_read": False},
            {"is_read": {"$exists": False}, "read": {"$ne": True}},
        ],
    }


def _notification_identity_query(notification_id: str) -> dict:
    identities: list[dict] = [
        {"notification_id": notification_id},
        {"id": notification_id},
    ]
    if ObjectId.is_valid(notification_id):
        identities.append({"_id": ObjectId(notification_id)})
    return {"$or": identities}


def _normalize_notification(doc: dict) -> dict:
    object_id = doc.pop("_id", None)
    if "notification_id" in doc and "id" not in doc:
        doc["id"] = doc["notification_id"]
    if not doc.get("id") and object_id is not None:
        doc["id"] = str(object_id)
    doc.setdefault("notification_id", doc.get("id"))
    doc.setdefault("type", "info")
    doc.setdefault("event", doc.get("type", "info"))
    doc.setdefault("title", "")
    doc.setdefault("message", "")
    doc.setdefault("metadata", {})
    doc.setdefault("severity", "low")
    doc.setdefault("target_path", "/dashboard")
    if "is_read" not in doc:
        doc["is_read"] = bool(doc.get("read", False))
    doc["read"] = bool(doc.get("is_read"))
    return doc


@router.get("/notifications")
async def list_notifications(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
):
    user_id = current_user["user_id"]
    query: dict = _in_app_notification_query(user_id)
    if unread_only:
        query = {"$and": [query, _unread_query()]}
    cursor = db.notifications.find(query).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(None)
    return [_normalize_notification(d) for d in docs]


@router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    db: DB,
):
    user_id = current_user["user_id"]
    result = await db.notifications.update_one(
        {
            "$and": [
                _in_app_notification_query(user_id),
                _notification_identity_query(notification_id),
            ]
        },
        {"$set": {"is_read": True, "read": True, "read_at": datetime.now(timezone.utc)}},
    )
    return {"updated": result.modified_count > 0}


@router.patch("/notifications/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(current_user: CurrentUser, db: DB):
    user_id = current_user["user_id"]
    result = await db.notifications.update_many(
        {"$and": [_in_app_notification_query(user_id), _unread_query()]},
        {"$set": {"is_read": True, "read": True, "read_at": datetime.now(timezone.utc)}},
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
        {
            "$and": [
                _in_app_notification_query(user_id),
                _notification_identity_query(notification_id),
            ]
        },
    )
