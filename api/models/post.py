"""
Phase 0.13 + Phase 1.9 — Post Pydantic models with full v2.9 schema.
All fields validated. response_model used on all endpoints to prevent field leakage.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ConfigDict


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    PROCESSING = "processing"
    PUBLISHED = "published"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PreUploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"


class PlatformStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    RETRYING = "retrying"


class StatusHistoryEntry(BaseModel):
    status: str
    timestamp: datetime
    actor: str = "system"
    message: str | None = None


class PlatformResult(BaseModel):
    status: PlatformStatus = PlatformStatus.PENDING
    error: str | None = None
    retry_count: int = 0
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    post_url: str | None = None
    platform_post_id: str | None = None
    published_at: datetime | None = None


class CreatePostRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(..., min_length=1, max_length=10000)
    platforms: list[str] = Field(..., min_length=1, max_length=10)
    scheduled_time: datetime | None = None
    media_ids: list[str] = Field(default_factory=list, max_length=10)
    post_type: str = Field(default="text", max_length=50)
    workspace_id: str | None = Field(None, max_length=100)
    timezone: str = Field(default="UTC", max_length=100)

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"instagram", "facebook", "youtube", "twitter", "linkedin", "tiktok"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unsupported platforms: {invalid}")
        return [p.lower() for p in v]

    @field_validator("scheduled_time")
    @classmethod
    def validate_scheduled_time(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        # Make v timezone-aware for comparison if it's naive
        if v.tzinfo is None:
            from datetime import timezone as _tz
            v = v.replace(tzinfo=_tz.utc)
        # EC19: Reject past times (> 5 minutes ago)
        if (now - v).total_seconds() > 300:
            raise ValueError("scheduled_time cannot be more than 5 minutes in the past")
        # EC19: Max 365 days in future
        max_future = now.replace(year=now.year + 1)
        if v > max_future:
            raise ValueError("scheduled_time cannot be more than 365 days in the future")
        return v


class BulkPostItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = Field(..., min_length=1, max_length=10000)
    scheduled_time: datetime | None = None
    media_urls: list[str] = Field(default_factory=list, max_length=10)


class BulkCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    platforms: list[str] = Field(..., min_length=1, max_length=10)
    posts: list[BulkPostItem] = Field(..., min_length=1, max_length=100)
    workspace_id: str | None = Field(None, max_length=100)
    timezone: str = Field(default="UTC", max_length=100)

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"instagram", "facebook", "youtube", "twitter", "linkedin", "tiktok"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unsupported platforms: {invalid}")
        return [p.lower() for p in v]


class BulkCreateResponse(BaseModel):
    created: int
    skipped: int
    errors: list[dict]


class UpdatePostRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str | None = Field(None, min_length=1, max_length=10000)
    scheduled_time: datetime | None = None
    platforms: list[str] | None = Field(None, max_length=10)
    version: int = Field(..., description="Optimistic lock version — must match current DB version")

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        allowed = {"instagram", "facebook", "youtube", "twitter", "linkedin", "tiktok"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unsupported platforms: {invalid}")
        return [p.lower() for p in v]


class PostResponse(BaseModel):
    """Safe response model — never includes internal fields."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    user_id: str
    workspace_id: str | None = None
    content: str
    platforms: list[str]
    status: PostStatus
    scheduled_time: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # v2.9 fields
    platform_results: dict[str, PlatformResult] = Field(default_factory=dict)
    platform_post_urls: dict[str, str] = Field(default_factory=dict)
    status_history: list[StatusHistoryEntry] = Field(default_factory=list)
    thumbnail_urls: list[str] = Field(default_factory=list)
    pre_upload_status: PreUploadStatus | None = None
    queue_job_id: str | None = None
    jitter_seconds: int | None = None
    version: int = 1
    dlq_reason: str | None = None
