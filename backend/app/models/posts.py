from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class CreatePostCommand(BaseModel):
    user_id: str
    content: str
    post_type: str
    platforms: List[str]
    media_urls: Optional[List[str]] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    subscription_status: str

class UpdatePostCommand(BaseModel):
    post_id: str
    user_id: str
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None

class DeletePostCommand(BaseModel):
    post_id: str
    user_id: str

class GetPostsQuery(BaseModel):
    user_id: str
    status: Optional[str] = None

class GetPostQuery(BaseModel):
    post_id: str
    user_id: str
