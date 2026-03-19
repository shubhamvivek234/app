"""
Phase 6 — Workspace team role definitions and permission checks.
Roles: Owner > Admin > Editor > Viewer > Client
"""
from __future__ import annotations

from enum import Enum


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    CLIENT = "client"


# Permission → minimum role required
_ROLE_PERMISSIONS: dict[str, WorkspaceRole] = {
    # Post actions
    "post:create": WorkspaceRole.EDITOR,
    "post:update": WorkspaceRole.EDITOR,
    "post:delete": WorkspaceRole.EDITOR,
    "post:read": WorkspaceRole.VIEWER,

    # Social account management
    "account:connect": WorkspaceRole.ADMIN,
    "account:disconnect": WorkspaceRole.ADMIN,
    "account:read": WorkspaceRole.VIEWER,

    # Workspace management
    "workspace:invite": WorkspaceRole.ADMIN,
    "workspace:remove_member": WorkspaceRole.ADMIN,
    "workspace:update": WorkspaceRole.ADMIN,
    "workspace:delete": WorkspaceRole.OWNER,

    # Analytics
    "analytics:read": WorkspaceRole.VIEWER,

    # Billing
    "billing:manage": WorkspaceRole.OWNER,

    # API keys
    "api_key:manage": WorkspaceRole.ADMIN,

    # Webhooks
    "webhook:manage": WorkspaceRole.ADMIN,
}

_ROLE_RANK: dict[WorkspaceRole, int] = {
    WorkspaceRole.OWNER: 5,
    WorkspaceRole.ADMIN: 4,
    WorkspaceRole.EDITOR: 3,
    WorkspaceRole.VIEWER: 2,
    WorkspaceRole.CLIENT: 1,
}


def has_permission(user_role: str | WorkspaceRole, permission: str) -> bool:
    """
    Returns True if user_role has the required rank for `permission`.
    Raises KeyError if permission is unknown.
    """
    role = WorkspaceRole(user_role) if isinstance(user_role, str) else user_role
    required = _ROLE_PERMISSIONS.get(permission)
    if required is None:
        raise KeyError(f"Unknown permission: {permission}")
    return _ROLE_RANK[role] >= _ROLE_RANK[required]


def require_permission(user_role: str | WorkspaceRole, permission: str) -> None:
    """
    Raise PermissionError if the user does not have the required permission.
    Use in route handlers before performing the action.
    """
    if not has_permission(user_role, permission):
        raise PermissionError(
            f"Role '{user_role}' does not have permission '{permission}'"
        )
