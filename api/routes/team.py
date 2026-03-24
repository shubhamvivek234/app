"""Workspace team members — list, invite, remove, change role."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["team"])

VALID_ROLES = {"owner", "admin", "editor", "viewer", "client"}


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "editor"


class RoleUpdate(BaseModel):
    role: str


@router.get("/workspace/members")
async def list_members(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.workspace_members.find({"workspace_id": workspace_id}, {"_id": 0})
    members = await cursor.to_list(None)
    # Enrich with user display names
    for m in members:
        user = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0, "display_name": 1, "email": 1, "avatar_url": 1})
        if user:
            m["display_name"] = user.get("display_name")
            m["email"] = user.get("email")
            m["avatar_url"] = user.get("avatar_url")
    return members


@router.post("/workspace/members/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(body: InviteRequest, current_user: CurrentUser, db: DB):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role. Must be one of {sorted(VALID_ROLES)}")
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    # Check if already a member
    existing_user = await db.users.find_one({"email": body.email}, {"_id": 0, "user_id": 1})
    if existing_user:
        already = await db.workspace_members.find_one(
            {"workspace_id": workspace_id, "user_id": existing_user["user_id"]}
        )
        if already:
            raise HTTPException(status_code=409, detail="User is already a workspace member")

    token = secrets.token_urlsafe(32)
    invite_doc = {
        "invite_id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "invited_by": current_user["user_id"],
        "email": body.email,
        "role": body.role,
        "token": token,
        "status": "pending",
        "created_at": now,
        "expires_at": (now + timedelta(days=7)).isoformat(),
    }
    await db.workspace_invites.insert_one(invite_doc)
    invite_doc.pop("_id", None)
    logger.info("Workspace invite sent: workspace=%s email=%s role=%s", workspace_id, body.email, body.role)
    return {"invited": True, "email": body.email, "role": body.role, "token": token}


@router.delete("/workspace/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    # Prevent self-removal of owner
    if member_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the workspace")
    result = await db.workspace_members.delete_one({"workspace_id": workspace_id, "user_id": member_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")


@router.patch("/workspace/members/{member_id}/role")
async def update_member_role(member_id: str, body: RoleUpdate, current_user: CurrentUser, db: DB):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role")
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.workspace_members.find_one_and_update(
        {"workspace_id": workspace_id, "user_id": member_id},
        {"$set": {"role": body.role, "updated_at": datetime.now(timezone.utc)}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")
    return result


@router.get("/workspace/invite/{token}")
async def get_invite_details(token: str, db: DB):
    invite = await db.workspace_invites.find_one({"token": token, "status": "pending"}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    workspace = await db.workspaces.find_one({"workspace_id": invite["workspace_id"]}, {"_id": 0, "name": 1})
    return {
        "email": invite["email"],
        "role": invite["role"],
        "workspace_name": workspace.get("name") if workspace else "Workspace",
        "expires_at": invite.get("expires_at"),
    }


@router.post("/workspace/invite/{token}/accept")
async def accept_invite(token: str, current_user: CurrentUser, db: DB):
    invite = await db.workspace_invites.find_one({"token": token, "status": "pending"}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    workspace_id = invite["workspace_id"]
    now = datetime.now(timezone.utc)

    # Add to workspace_members
    await db.workspace_members.update_one(
        {"workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {"$setOnInsert": {"workspace_id": workspace_id, "user_id": current_user["user_id"], "role": invite["role"], "joined_at": now}},
        upsert=True,
    )
    # Update user's workspace_ids
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$addToSet": {"workspace_ids": workspace_id}},
    )
    # Mark invite used
    await db.workspace_invites.update_one({"token": token}, {"$set": {"status": "accepted", "accepted_at": now}})
    return {"accepted": True, "workspace_id": workspace_id}
