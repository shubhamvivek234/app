"""Media asset Pydantic models."""
from datetime import datetime
from enum import Enum
from typing import Any, Literal
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


class MediaSourceStage(str, Enum):
    FETCHING = "fetching"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaAssetKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


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
    asset_kind: MediaAssetKind | None = None
    file_size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool | None = None
    created_at: datetime
    processed_at: datetime | None = None
    error_message: str | None = None
    parent_media_id: str | None = None
    render_job_id: str | None = None
    audio_mix: dict[str, Any] | None = None
    source_provider: str | None = None
    source_item_id: str | None = None
    source_label: str | None = None
    source_attribution: dict[str, Any] | None = None
    source_stage: MediaSourceStage | None = None


class RemoteMediaImportItem(BaseModel):
    provider: Literal["unsplash", "dropbox", "google_drive", "google_photos", "onedrive", "canva"]
    download_url: str
    name: str
    source_item_id: str | None = None
    source_label: str | None = None
    source_attribution: dict[str, Any] | None = None
    file_size_bytes: int | None = Field(default=None, gt=0)
    content_type: str | None = None
    auth_bearer_token: str | None = None
    tracking_url: str | None = None


class RemoteMediaImportRequest(BaseModel):
    items: list[RemoteMediaImportItem] = Field(min_length=1, max_length=10)


class RemoteMediaImportResult(BaseModel):
    media_job_id: str
    provider: str
    name: str


class RemoteMediaImportResponse(BaseModel):
    imports: list[RemoteMediaImportResult]


class CanvaAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class CanvaCallbackRequest(BaseModel):
    code: str
    state: str


class CanvaCallbackResponse(BaseModel):
    session_id: str
    expires_at: datetime


class CanvaDesignResponse(BaseModel):
    id: str
    title: str | None = None
    thumbnail_url: str | None = None
    updated_at: datetime | None = None
    edit_url: str | None = None


class CanvaDesignListResponse(BaseModel):
    designs: list[CanvaDesignResponse]
    continuation: str | None = None


class CanvaExportRequest(BaseModel):
    session_id: str
    design_id: str
    file_type: Literal["png", "jpg", "mp4"]


class CanvaExportResponse(BaseModel):
    export_id: str
    status: str
    download_urls: list[str] = Field(default_factory=list)


class AudioMixSettings(BaseModel):
    audio_media_id: str
    trim_start_ms: int = Field(default=0, ge=0)
    trim_end_ms: int | None = Field(default=None, gt=0)
    video_offset_ms: int = Field(default=0, ge=0)
    loop_to_video_end: bool = True
    fade_in_ms: int = Field(default=0, ge=0, le=10_000)
    fade_out_ms: int = Field(default=0, ge=0, le=10_000)
    original_volume: float = Field(default=1.0, ge=0.0, le=2.0)
    selected_volume: float = Field(default=1.0, ge=0.0, le=2.0)
    mute_original: bool = False
    normalize_audio: bool = True


class AudioRenderRequest(BaseModel):
    mix: AudioMixSettings


class AudioRenderResponse(BaseModel):
    render_job_id: str
    media_job_id: str
    status: MediaStatus
    message: str = "Audio render queued"
