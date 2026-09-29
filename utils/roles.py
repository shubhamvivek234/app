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
    "approval:read": WorkspaceRole.VIEWER,
    "approval:decide": WorkspaceRole.CLIENT,

    # Social account management
    "account:connect": WorkspaceRole.ADMIN,
    "account:disconnect": WorkspaceRole.ADMIN,
    "account:delete": WorkspaceRole.ADMIN,
    "account:read": WorkspaceRole.VIEWER,

    # Workspace management
    "workspace:read": WorkspaceRole.VIEWER,
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

    # Campaigns & Sequences
    "campaign:create": WorkspaceRole.EDITOR,
    "campaign:update": WorkspaceRole.EDITOR,
    "campaign:delete": WorkspaceRole.ADMIN,
    "campaign:read": WorkspaceRole.VIEWER,
    "sequence:create": WorkspaceRole.EDITOR,
    "sequence:update": WorkspaceRole.EDITOR,
    "sequence:delete": WorkspaceRole.ADMIN,
    "sequence:read": WorkspaceRole.VIEWER,

    # Leads
    "lead:create": WorkspaceRole.EDITOR,
    "lead:update": WorkspaceRole.EDITOR,
    "lead:delete": WorkspaceRole.EDITOR,
    "lead:read": WorkspaceRole.VIEWER,

    # Inbox
    "inbox:read": WorkspaceRole.VIEWER,
    "inbox:reply": WorkspaceRole.EDITOR,
    "inbox:manage": WorkspaceRole.EDITOR,

    # Engage
    "engage:read": WorkspaceRole.VIEWER,
    "engage:manage": WorkspaceRole.EDITOR,
    "engage:delete": WorkspaceRole.ADMIN,

    # Voice & Content
    "voice:manage": WorkspaceRole.EDITOR,
    "content:manage": WorkspaceRole.EDITOR,

    # Outreach Engine Management
    "outreach:manage": WorkspaceRole.ADMIN,

    # Media upload
    "media:read": WorkspaceRole.VIEWER,
    "media:upload": WorkspaceRole.EDITOR,

    # Admin
    "admin:read": WorkspaceRole.ADMIN,
    "admin:manage": WorkspaceRole.OWNER,
}

_ROLE_RANK: dict[WorkspaceRole, int] = {
    WorkspaceRole.OWNER: 5,
    WorkspaceRole.ADMIN: 4,
    WorkspaceRole.EDITOR: 3,
    WorkspaceRole.CLIENT: 2,
    WorkspaceRole.VIEWER: 1,
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
