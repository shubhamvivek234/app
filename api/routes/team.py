"""Workspace team members, invites, and role management."""
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from api.deps import CurrentUser, DB, VerifiedUser, require_permission
from utils.roles import has_permission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["team"])

VALID_ROLES = {"owner", "admin", "editor", "viewer", "client"}
ROLE_ORDER = {
    "owner": 5,
    "admin": 4,
    "editor": 3,
    "viewer": 2,
    "client": 1,
}


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "editor"


class RoleUpdate(BaseModel):
    role: str


def _workspace_id_for(current_user: dict) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


def _frontend_base_url() -> str:
    return os.environ.get("FRONTEND_URL", "").strip() or "https://www.unravler.com"


def _build_invite_url(token: str) -> str:
    return f"{_frontend_base_url().rstrip('/')}/accept-invite/{token}"


def _parse_timestamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _is_expired(invite: dict, now: datetime) -> bool:
    expires_at = _parse_timestamp(invite.get("expires_at"))
    return bool(expires_at and expires_at <= now)


def _permission_flags(role: str) -> dict:
    return {
        "can_invite": has_permission(role, "workspace:invite"),
        "can_remove_member": has_permission(role, "workspace:remove_member"),
        "can_update_member_role": has_permission(role, "workspace:update"),
    }


async def _enrich_member(db: DB, member: dict) -> dict:
    enriched = dict(member)
    user = await db.users.find_one(
        {"user_id": member["user_id"]},
        {"_id": 0, "display_name": 1, "email": 1, "avatar_url": 1},
    )
    if user:
        enriched["display_name"] = user.get("display_name")
        enriched["email"] = user.get("email")
        enriched["avatar_url"] = user.get("avatar_url")
    return enriched


async def _serialize_invite(db: DB, invite: dict, workspace_name: str | None = None) -> dict:
    inviter = await db.users.find_one(
        {"user_id": invite.get("invited_by")},
        {"_id": 0, "display_name": 1, "email": 1},
    )
    return {
        "invite_id": invite["invite_id"],
        "email": invite["email"],
        "role": invite["role"],
        "status": invite.get("status", "pending"),
        "created_at": _parse_timestamp(invite.get("created_at")),
        "expires_at": _parse_timestamp(invite.get("expires_at")),
        "invite_url": _build_invite_url(invite["token"]),
        "workspace_id": invite.get("workspace_id"),
        "workspace_name": workspace_name,
        "invited_by": invite.get("invited_by"),
        "invited_by_name": (inviter or {}).get("display_name") or (inviter or {}).get("email"),
    }


@router.get("/workspace/members", dependencies=[require_permission("workspace:read")])
async def list_members(current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    workspace = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "name": 1},
    )
    membership = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {"_id": 0, "role": 1},
    )
    current_role = (membership or {}).get("role", "viewer")
    permissions = _permission_flags(current_role)

    members = await db.workspace_members.find(
        {"workspace_id": workspace_id},
        {"_id": 0},
    ).to_list(None)
    enriched_members = [await _enrich_member(db, member) for member in members]
    enriched_members.sort(
        key=lambda member: (
            -ROLE_ORDER.get(member.get("role", "viewer"), 0),
            member.get("display_name") or member.get("email") or member.get("user_id"),
        )
    )

    pending_invites = await db.workspace_invites.find(
        {"workspace_id": workspace_id, "status": "pending"},
        {"_id": 0},
    ).to_list(None)
    now = datetime.now(timezone.utc)
    active_invites = []
    for invite in pending_invites:
        if _is_expired(invite, now):
            await db.workspace_invites.update_one(
                {"invite_id": invite["invite_id"]},
                {"$set": {"status": "expired", "updated_at": now}},
            )
            continue
        active_invites.append(
            await _serialize_invite(db, invite, (workspace or {}).get("name") or "Workspace")
        )
    active_invites.sort(key=lambda invite: invite.get("created_at") or now, reverse=True)

    return {
        "workspace_id": workspace_id,
        "workspace_name": (workspace or {}).get("name") or "Workspace",
        "current_user_role": current_role,
        "permissions": permissions,
        "members": enriched_members,
        "pending_invites": active_invites,
    }


@router.post(
    "/workspace/members/invite",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("workspace:invite")],
)
async def invite_member(body: InviteRequest, current_user: VerifiedUser, db: DB):
    if body.role not in VALID_ROLES or body.role == "owner":
        raise HTTPException(status_code=422, detail=f"Invalid role. Must be one of {sorted(VALID_ROLES - {'owner'})}")

    workspace_id = _workspace_id_for(current_user)
    workspace = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "name": 1},
    )
    email = body.email.strip().lower()
    now = datetime.now(timezone.utc)

    existing_user = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if existing_user:
        already = await db.workspace_members.find_one(
            {"workspace_id": workspace_id, "user_id": existing_user["user_id"]}
        )
        if already:
            raise HTTPException(status_code=409, detail="User is already a workspace member")

    existing_invite = await db.workspace_invites.find_one(
        {"workspace_id": workspace_id, "email": email, "status": "pending"},
        {"_id": 0},
    )
    if existing_invite:
        if _is_expired(existing_invite, now):
            await db.workspace_invites.update_one(
                {"invite_id": existing_invite["invite_id"]},
                {"$set": {"status": "expired", "updated_at": now}},
            )
        else:
            raise HTTPException(status_code=409, detail="A pending invite already exists for this email")

    token = secrets.token_urlsafe(32)
    invite_doc = {
        "invite_id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "invited_by": current_user["user_id"],
        "email": email,
        "role": body.role,
        "token": token,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=7),
    }
    await db.workspace_invites.insert_one(invite_doc)
    logger.info("Workspace invite created: workspace=%s email=%s role=%s", workspace_id, email, body.role)

    return {
        "invited": True,
        "message": "Invite created",
        "invite": await _serialize_invite(db, invite_doc, (workspace or {}).get("name") or "Workspace"),
    }


@router.delete(
    "/workspace/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("workspace:invite")],
)
async def revoke_invite(invite_id: str, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    result = await db.workspace_invites.update_one(
        {"workspace_id": workspace_id, "invite_id": invite_id, "status": "pending"},
        {"$set": {"status": "revoked", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")


@router.delete(
    "/workspace/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("workspace:remove_member")],
)
async def remove_member(member_id: str, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id_for(current_user)
    if member_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the workspace")

    target_member = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": member_id},
        {"_id": 0, "role": 1},
    )
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_member.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")

    result = await db.workspace_members.delete_one({"workspace_id": workspace_id, "user_id": member_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")


@router.patch(
    "/workspace/members/{member_id}/role",
    dependencies=[require_permission("workspace:update")],
)
async def update_member_role(member_id: str, body: RoleUpdate, current_user: CurrentUser, db: DB):
    if body.role not in VALID_ROLES or body.role == "owner":
        raise HTTPException(status_code=422, detail="Invalid role")

    workspace_id = _workspace_id_for(current_user)
    if member_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    target_member = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": member_id},
        {"_id": 0, "role": 1},
    )
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_member.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the workspace owner role")

    result = await db.workspace_members.find_one_and_update(
        {"workspace_id": workspace_id, "user_id": member_id},
        {"$set": {"role": body.role, "updated_at": datetime.now(timezone.utc)}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")
    return await _enrich_member(db, result)


@router.get("/workspace/invite/{token}")
async def get_invite_details(token: str, db: DB):
    invite = await db.workspace_invites.find_one({"token": token, "status": "pending"}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    now = datetime.now(timezone.utc)
    if _is_expired(invite, now):
        await db.workspace_invites.update_one(
            {"invite_id": invite["invite_id"]},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    workspace = await db.workspaces.find_one(
        {"workspace_id": invite["workspace_id"]},
        {"_id": 0, "name": 1},
    )
    inviter = await db.users.find_one(
        {"user_id": invite["invited_by"]},
        {"_id": 0, "display_name": 1, "email": 1},
    )
    existing_user = await db.users.find_one({"email": invite["email"]}, {"_id": 0, "user_id": 1})
    return {
        "email": invite["email"],
        "invited_email": invite["email"],
        "role": invite["role"],
        "workspace_name": (workspace or {}).get("name") or "Workspace",
        "expires_at": _parse_timestamp(invite.get("expires_at")),
        "user_exists": existing_user is not None,
        "invited_by_name": (inviter or {}).get("display_name") or (inviter or {}).get("email"),
        "invite_url": _build_invite_url(token),
    }


@router.post("/workspace/invite/{token}/accept")
async def accept_invite(token: str, current_user: CurrentUser, db: DB):
    invite = await db.workspace_invites.find_one({"token": token, "status": "pending"}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    now = datetime.now(timezone.utc)
    if _is_expired(invite, now):
        await db.workspace_invites.update_one(
            {"invite_id": invite["invite_id"]},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    current_email = (current_user.get("email") or "").strip().lower()
    invited_email = (invite.get("email") or "").strip().lower()
    if current_email != invited_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invite is for {invited_email}. Sign in with the invited email address to continue.",
        )
    if not current_user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before joining this workspace.",
        )

    workspace_id = invite["workspace_id"]
    workspace = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "name": 1},
    )

    await db.workspace_members.update_one(
        {"workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {
            "$setOnInsert": {
                "workspace_id": workspace_id,
                "user_id": current_user["user_id"],
                "role": invite["role"],
                "joined_at": now,
            }
        },
        upsert=True,
    )
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {
            "$addToSet": {"workspace_ids": workspace_id},
            "$set": {"default_workspace_id": workspace_id},
        },
    )
    await db.workspace_invites.update_one(
        {"token": token},
        {"$set": {"status": "accepted", "accepted_at": now, "updated_at": now}},
    )
    return {
        "accepted": True,
        "workspace_id": workspace_id,
        "workspace_name": (workspace or {}).get("name") or "Workspace",
        "role": invite["role"],
    }
