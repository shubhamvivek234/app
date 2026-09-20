"""Pydantic models for the AI Agent Hub."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentActionCard(BaseModel):
    card_type: str = Field(..., description="'draft_post', 'clipping_job', 'image_generation', 'calendar_slot'")
    title: str
    summary: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    actions: List[Dict[str, str]] = Field(default_factory=list)


class AgentMessage(BaseModel):
    id: str
    session_id: str
    sender: str = Field(..., description="'user', 'assistant', or 'system'")
    text: str
    cards: List[AgentActionCard] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentSessionCreate(BaseModel):
    title: Optional[str] = None
    channel_ids: List[str] = Field(default_factory=list)


class AgentSessionResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    title: str
    channel_ids: List[str] = Field(default_factory=list)
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    channel_ids: List[str] = Field(default_factory=list)
    media_urls: List[str] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    session_id: str
    reply: str
    cards: List[AgentActionCard] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
