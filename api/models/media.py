"""Media asset Pydantic models."""
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class MediaStatus(str, Enum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADING = "uploading"
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


class MediaUploadSessionRequest(BaseModel):
    filename: str
    file_size_bytes: int = Field(gt=0)
    content_type: str


class MediaUploadPartResponse(BaseModel):
    part_number: int
    url: str


class MediaUploadSessionPayload(BaseModel):
    mode: Literal["single", "multipart"]
    object_key: str
    content_type: str
    expires_in_seconds: int
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    upload_id: str | None = None
    part_size_bytes: int | None = None
    parts: list[MediaUploadPartResponse] = Field(default_factory=list)


class MediaUploadSessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    media_job_id: str
    status: MediaStatus = MediaStatus.PENDING_UPLOAD
    message: str = "Upload session created"
    upload: MediaUploadSessionPayload


class CompletedUploadPart(BaseModel):
    part_number: int = Field(alias="PartNumber")
    etag: str = Field(alias="ETag")


class MediaUploadCompleteRequest(BaseModel):
    media_job_id: str
    upload_id: str | None = None
    parts: list[CompletedUploadPart] = Field(default_factory=list)


class MediaUploadAbortRequest(BaseModel):
    reason: str | None = None


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
