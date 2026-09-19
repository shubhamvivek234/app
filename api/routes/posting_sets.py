"""
Posting Sets API Routes.
Enables users to organize social accounts into named presets (e.g. "Personal Brand", "B2B Outreach")
for 1-click account selection in the Post Composer.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import CurrentUser, DB
from api.models.posting_sets import (
    PostingSetCreate,
    PostingSetResponse,
    PostingSetUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posting-sets", tags=["posting-sets"])


def _resolve_workspace_id(current_user: dict, requested_ws: Optional[str] = None) -> str:
    if isinstance(requested_ws, str) and requested_ws.strip():
        return requested_ws.strip()
    ws = current_user.get("default_workspace_id") or current_user.get("workspace_id")
    if not ws:
        ws = str(current_user.get("user_id") or "")
    return ws


@router.get("", response_model=List[PostingSetResponse])
async def list_posting_sets(
    current_user: CurrentUser,
    db: DB,
    workspace_id: Optional[str] = Query(None),
) -> List[PostingSetResponse]:
    """List all posting sets for the active workspace."""
    ws_id = _resolve_workspace_id(current_user, workspace_id)
    cursor = db.posting_sets.find(
        {"workspace_id": ws_id},
        {"_id": 0},
    ).sort("created_at", 1)

    docs = await cursor.to_list(length=100)
    return [PostingSetResponse(**doc) for doc in docs]


@router.post("", response_model=PostingSetResponse, status_code=status.HTTP_201_CREATED)
async def create_posting_set(
    body: PostingSetCreate,
    current_user: CurrentUser,
    db: DB,
) -> PostingSetResponse:
    """Create a new posting set of accounts."""
    ws_id = _resolve_workspace_id(current_user, body.workspace_id)
    user_id = str(current_user["user_id"])
    now = datetime.now(timezone.utc)

    # Validate that accounts belong to this workspace or user
    valid_accounts = await db.social_accounts.find(
        {
            "$and": [
                {"$or": [{"workspace_id": ws_id}, {"user_id": user_id}]},
                {"$or": [{"account_id": {"$in": body.account_ids}}, {"id": {"$in": body.account_ids}}]},
            ]
        },
        {"_id": 0, "account_id": 1, "id": 1},
    ).to_list(length=100)

    valid_ids = {a.get("account_id") or a.get("id") for a in valid_accounts if a.get("account_id") or a.get("id")}
    filtered_ids = [aid for aid in body.account_ids if aid in valid_ids] if valid_ids else body.account_ids

    if not filtered_ids:
        filtered_ids = body.account_ids

    set_id = f"pset_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": set_id,
        "workspace_id": ws_id,
        "user_id": user_id,
        "name": body.name,
        "account_ids": filtered_ids,
        "color": body.color or "indigo",
        "icon": body.icon,
        "created_at": now,
        "updated_at": now,
    }

    await db.posting_sets.insert_one(doc)
    doc.pop("_id", None)
    return PostingSetResponse(**doc)


@router.put("/{set_id}", response_model=PostingSetResponse)
async def update_posting_set(
    set_id: str,
    body: PostingSetUpdate,
    current_user: CurrentUser,
    db: DB,
) -> PostingSetResponse:
    """Update an existing posting set."""
    ws_id = _resolve_workspace_id(current_user)
    user_id = str(current_user["user_id"])

    existing = await db.posting_sets.find_one(
        {
            "id": set_id,
            "$or": [{"workspace_id": ws_id}, {"user_id": user_id}],
        },
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting set not found")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.account_ids is not None:
        updates["account_ids"] = body.account_ids
    if body.color is not None:
        updates["color"] = body.color
    if body.icon is not None:
        updates["icon"] = body.icon

    updates["updated_at"] = datetime.now(timezone.utc)

    await db.posting_sets.update_one({"id": set_id}, {"$set": updates})
    existing.update(updates)
    return PostingSetResponse(**existing)


@router.delete("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_posting_set(
    set_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete a posting set."""
    ws_id = _resolve_workspace_id(current_user)
    user_id = str(current_user["user_id"])

    res = await db.posting_sets.delete_one(
        {
            "id": set_id,
            "$or": [{"workspace_id": ws_id}, {"user_id": user_id}],
        }
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posting set not found")
