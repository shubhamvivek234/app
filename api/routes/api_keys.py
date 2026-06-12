"""Developer credential management for REST and MCP integrations."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, require_permission
from utils.developer_tokens import (
    PERSONAL_TOKEN_TYPE,
    WORKSPACE_TOKEN_TYPE,
    PUBLIC_SCOPES_IN_ORDER,
    allowed_public_scopes_for_role,
    generate_developer_token,
    hash_developer_token,
    normalize_requested_scopes,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api-keys"])


class DeveloperTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[str] | None = None


class WorkspaceApiKeyCreate(DeveloperTokenCreate):
    scopes: list[str] | None = None


class DeveloperTokenResponse(BaseModel):
    id: str
    name: str
    token_type: str
    scopes: list[str]
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    workspace_id: str


def _workspace_id_for(current_user: dict) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


async def _workspace_role_for(db: DB, current_user: dict, workspace_id: str) -> str:
    membership = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {"_id": 0, "role": 1},
    )
    if membership and membership.get("role"):
        return membership["role"]

    workspace = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "owner_id": 1},
    )
    if workspace and workspace.get("owner_id") == current_user["user_id"]:
        return "owner"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Active workspace membership is required",
    )


def _serialize_credential(doc: dict) -> dict:
    return {
        "id": doc.get("id") or doc.get("key_id"),
        "name": doc.get("name", "Developer token"),
        "token_type": doc.get("token_type") or WORKSPACE_TOKEN_TYPE,
        "scopes": list(doc.get("scopes") or []),
        "key_prefix": doc.get("key_prefix", ""),
        "created_at": doc.get("created_at"),
        "last_used_at": doc.get("last_used_at"),
        "workspace_id": doc.get("workspace_id", ""),
    }


async def _create_credential(
    *,
    db: DB,
    current_user: dict,
    token_type: str,
    name: str,
    requested_scopes: list[str] | None,
    allow_wildcard: bool,
) -> dict:
    workspace_id = _workspace_id_for(current_user)
    workspace_role = await _workspace_role_for(db, current_user, workspace_id)
    allowed_scopes = allowed_public_scopes_for_role(workspace_role)

    try:
        scopes = normalize_requested_scopes(
            requested_scopes,
            allowed_scopes=allowed_scopes,
            allow_wildcard=allow_wildcard,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    raw_key = generate_developer_token()
    now = datetime.now(timezone.utc)
    key_id = str(uuid.uuid4())
    doc = {
        "key_id": key_id,
        "id": key_id,
        "name": name.strip(),
        "token_type": token_type,
        "scopes": scopes,
        "key_hash": hash_developer_token(raw_key),
        "key_prefix": raw_key[:12],
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "created_by_user_id": current_user["user_id"],
        "revoked": False,
        "created_at": now,
        "last_used_at": None,
    }
    await db.api_keys.insert_one(doc)
    return {
        **_serialize_credential(doc),
        "raw_key": raw_key,
    }


@router.get("/developer/scopes")
async def list_developer_scopes(current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    workspace_role = await _workspace_role_for(db, current_user, workspace_id)
    allowed_scopes = allowed_public_scopes_for_role(workspace_role)
    return {
        "workspace_id": workspace_id,
        "workspace_role": workspace_role,
        "allowed_scopes": allowed_scopes,
        "all_scopes": PUBLIC_SCOPES_IN_ORDER,
        "default_personal_scopes": allowed_scopes,
        "default_workspace_scopes": allowed_scopes,
    }


@router.get("/developer/personal-tokens")
async def list_personal_tokens(current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    cursor = db.api_keys.find(
        {
            "workspace_id": workspace_id,
            "user_id": current_user["user_id"],
            "token_type": PERSONAL_TOKEN_TYPE,
            "revoked": {"$ne": True},
        },
        {"_id": 0, "key_hash": 0},
    ).sort("created_at", -1)
    docs = await cursor.to_list(None)
    return [_serialize_credential(doc) for doc in docs]


@router.post("/developer/personal-tokens", status_code=status.HTTP_201_CREATED)
async def create_personal_token(body: DeveloperTokenCreate, current_user: CurrentUser, db: DB):
    return await _create_credential(
        db=db,
        current_user=current_user,
        token_type=PERSONAL_TOKEN_TYPE,
        name=body.name,
        requested_scopes=body.scopes,
        allow_wildcard=False,
    )


@router.delete("/developer/personal-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_token(token_id: str, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    result = await db.api_keys.update_one(
        {
            "$or": [{"key_id": token_id}, {"id": token_id}],
            "workspace_id": workspace_id,
            "user_id": current_user["user_id"],
            "token_type": PERSONAL_TOKEN_TYPE,
        },
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personal token not found")


@router.get("/api-keys", dependencies=[require_permission("api_key:manage")])
async def list_api_keys(current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    cursor = db.api_keys.find(
        {
            "workspace_id": workspace_id,
            "token_type": {"$ne": PERSONAL_TOKEN_TYPE},
            "revoked": {"$ne": True},
        },
        {"_id": 0, "key_hash": 0},
    ).sort("created_at", -1)
    docs = await cursor.to_list(None)
    return [_serialize_credential(doc) for doc in docs]


@router.post(
    "/api-keys",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("api_key:manage")],
)
async def create_api_key(body: WorkspaceApiKeyCreate, current_user: CurrentUser, db: DB):
    return await _create_credential(
        db=db,
        current_user=current_user,
        token_type=WORKSPACE_TOKEN_TYPE,
        name=body.name,
        requested_scopes=body.scopes,
        allow_wildcard=True,
    )


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("api_key:manage")],
)
async def delete_api_key(key_id: str, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    result = await db.api_keys.update_one(
        {
            "$or": [{"key_id": key_id}, {"id": key_id}],
            "workspace_id": workspace_id,
            "token_type": {"$ne": PERSONAL_TOKEN_TYPE},
        },
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
