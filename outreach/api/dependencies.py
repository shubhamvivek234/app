"""One resolved tenant for outreach permission, erasure and handler admission."""
from typing import Any
import logging

from fastapi import Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import require_permission
from db.mongo import get_db
from outreach.core.erasure import require_open_workspace

logger = logging.getLogger(__name__)


def workspace_id(user: dict) -> str:
    """Reject ambiguous context instead of substituting a creator UID."""
    value = (
        user.get("default_workspace_id")
        or user.get("current_workspace_id")
        or user.get("workspace_id")
    )
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=403, detail="No workspace context")
    return value


def require_outreach_permission(permission: str) -> Any:
    """Pass the context actually authorized by the role check to the handler."""
    async def authorized(
        current_user: dict = require_permission(permission),
        db: AsyncIOMotorDatabase = Depends(get_db),
    ) -> dict:
        resolved = {**current_user, "default_workspace_id": workspace_id(current_user)}
        await require_open_workspace(resolved, db)
        return resolved

    return Depends(authorized)


async def get_outreach_user(
    current_user: dict = require_outreach_permission("workspace:read"),
) -> dict:
    """Ordinary reads use the same resolved, open workspace contract."""
    return current_user
