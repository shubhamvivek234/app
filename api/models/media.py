"""Media asset Pydantic models."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class MediaStatus(str, Enum):
    QUARANTINE = "quarantine"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CLEANED = "cleaned"
    ARCHIVED = "archived"


class MediaUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    media_job_id: str
    status: MediaStatus = MediaStatus.QUARANTINE
    message: str = "Upload received, processing started"


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    media_id: str
    user_id: str
    status: MediaStatus
    media_url: str | None = None
    thumbnail_url: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime
    processed_at: datetime | None = None
    error_message: str | None = None
