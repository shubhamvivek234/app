"""Pydantic schemas for the Video Clipping Engine."""
from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ClippingRequest(BaseModel):
    youtube_url: str = Field(..., description="YouTube video URL or Shorts URL to clip")
    num_clips: int = Field(default=3, ge=1, le=10, description="Number of viral shorts to extract (1-10)")
    fit_mode: str = Field(default="blur", description="'blur' for blurred background pad, 'crop' for center crop")
    target_account_ids: list[str] = Field(default_factory=list, description="Target connected social account IDs")
    target_platforms: list[str] = Field(default_factory=list, description="Target platforms e.g. tiktok, instagram, youtube")
    burn_subtitles: bool = Field(default=True, description="Whether to burn animated karaoke-style subtitles")
    subtitle_style: str = Field(default="viral_yellow", description="'viral_yellow', 'clean_white', or 'modern_cyan'")
    min_clip_sec: int = Field(default=15, ge=10, le=120, description="Minimum clip duration in seconds")
    max_clip_sec: int = Field(default=60, ge=15, le=180, description="Maximum clip duration in seconds")
    auto_create_drafts: bool = Field(default=True, description="Automatically create draft calendar posts with the clips")


class ClipItem(BaseModel):
    clip_id: str
    title: str
    start_time: float
    end_time: float
    duration_sec: float
    viral_score: int = Field(default=85, description="Viral hook score 1-100")
    hook: str = ""
    summary: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    post_id: Optional[str] = None


class ClippingJobResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    youtube_url: str
    video_title: str
    status: str = Field(default="queued", description="'queued', 'downloading', 'transcribing', 'analyzing', 'rendering', 'completed', 'failed'")
    progress: int = Field(default=0, ge=0, le=100)
    current_step: str = "Queued for processing"
    error_message: Optional[str] = None
    fit_mode: str = "blur"
    burn_subtitles: bool = True
    clips: list[ClipItem] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
