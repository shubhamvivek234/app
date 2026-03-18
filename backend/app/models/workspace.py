"""
Workspace model — Stage 5.9
Multi-tenant team support. Each workspace has members with roles.
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


class WorkspaceMember(BaseModel):
    user_id: str
    email: str
    name: str
    role: str = "viewer"  # owner | admin | editor | viewer
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    invited_by: Optional[str] = None


class Workspace(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str  # URL-safe workspace identifier
    owner_id: str
    members: List[WorkspaceMember] = []
    plan: str = "starter"  # starter | pro | agency | enterprise
    subscription_status: str = "free"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    settings: dict = Field(default_factory=dict)
    # Limits per plan
    max_members: int = 1        # starter=1, pro=3, agency=10, enterprise=unlimited
    max_accounts: int = 5       # starter=5, pro=10, agency=25, enterprise=unlimited
    max_scheduled_posts: int = 30  # per month


class WorkspaceInvite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    workspace_name: str
    invited_email: str
    invited_by_id: str
    invited_by_name: str
    role: str = "viewer"
    token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expires_at: datetime
    accepted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Role permissions
ROLE_PERMISSIONS = {
    "owner":  {"create_post", "edit_post", "delete_post", "publish", "manage_accounts",
               "manage_members", "manage_billing", "view_analytics"},
    "admin":  {"create_post", "edit_post", "delete_post", "publish", "manage_accounts",
               "manage_members", "view_analytics"},
    "editor": {"create_post", "edit_post", "publish", "view_analytics"},
    "viewer": {"view_analytics"},
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
