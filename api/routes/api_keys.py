"""API key management for dashboard users."""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["read"]


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    scopes: list[str]
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


@router.get("/api-keys")
async def list_api_keys(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.api_keys.find(
        {"workspace_id": workspace_id, "revoked": {"$ne": True}},
        {"_id": 0, "key_hash": 0},
    ).sort("created_at", -1)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("key_id", ""))
    return docs


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(body: ApiKeyCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    raw_key = f"se_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())

    doc = {
        "key_id": key_id,
        "id": key_id,
        "name": body.name,
        "scopes": body.scopes,
        "key_hash": key_hash,
        "key_prefix": raw_key[:8],
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "revoked": False,
        "created_at": now,
        "last_used_at": None,
    }
    await db.api_keys.insert_one(doc)

    return {
        "id": key_id,
        "name": body.name,
        "scopes": body.scopes,
        "key_prefix": raw_key[:8],
        "raw_key": raw_key,  # Only returned once
        "created_at": now,
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.api_keys.update_one(
        {"$or": [{"key_id": key_id}, {"id": key_id}], "workspace_id": workspace_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="API key not found")
