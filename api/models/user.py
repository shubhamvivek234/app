"""User and workspace Pydantic models with strict validation."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr, Field, ConfigDict, computed_field


class SubscriptionStatus(str, Enum):
    FREE = "free"
    ACTIVE = "active"
    GRACE = "grace"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Plan(str, Enum):
    STARTER = "starter"
    PRO = "pro"
    AGENCY = "agency"


class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str
    email: EmailStr
    display_name: str | None = None
    avatar_url: str | None = None
    plan: Plan = Plan.STARTER
    subscription_status: SubscriptionStatus = SubscriptionStatus.FREE
    subscription_end_date: datetime | None = None
    subscription_grace_period_end: datetime | None = None
    subscription_reactivated_at: datetime | None = None
    subscription_cleanup_date: datetime | None = None
    timezone: str = "UTC"
    created_at: datetime
    mfa_enabled: bool = False
    role: str = "user"
    onboarding_completed: bool = False

    @computed_field  # FE-2: alias for frontend compatibility
    @property
    def name(self) -> str | None:
        return self.display_name


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    CLIENT = "client"


class WorkspaceMember(BaseModel):
    user_id: str
    role: WorkspaceRole
    joined_at: datetime


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    name: str
    owner_id: str
    members: list[WorkspaceMember] = Field(default_factory=list)
    created_at: datetime
