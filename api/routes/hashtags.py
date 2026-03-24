"""Hashtag groups — CRUD."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hashtags"])


class HashtagGroupCreate(BaseModel):
    name: str
    hashtags: list[str] = []
    category: str = "general"


class HashtagGroupResponse(BaseModel):
    id: str
    name: str
    hashtags: list[str] = []
    category: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime


@router.get("/hashtag-groups")
async def list_hashtag_groups(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.hashtag_groups.find({"workspace_id": workspace_id}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("group_id", ""))
    return docs


@router.post("/hashtag-groups", status_code=status.HTTP_201_CREATED)
async def create_hashtag_group(body: HashtagGroupCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    group_id = str(uuid.uuid4())
    doc = {
        "group_id": group_id,
        "id": group_id,
        "name": body.name,
        "hashtags": body.hashtags,
        "category": body.category,
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.hashtag_groups.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/hashtag-groups/{group_id}")
async def update_hashtag_group(group_id: str, body: HashtagGroupCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    result = await db.hashtag_groups.find_one_and_update(
        {"$or": [{"group_id": group_id}, {"id": group_id}], "workspace_id": workspace_id},
        {"$set": {"name": body.name, "hashtags": body.hashtags, "category": body.category, "updated_at": now}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Hashtag group not found")
    result.setdefault("id", result.get("group_id", group_id))
    return result


@router.delete("/hashtag-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hashtag_group(group_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.hashtag_groups.delete_one(
        {"$or": [{"group_id": group_id}, {"id": group_id}], "workspace_id": workspace_id},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Hashtag group not found")
