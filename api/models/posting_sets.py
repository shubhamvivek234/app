"""
Pydantic models for Posting Sets (saved account groups for quick 1-click selection in Composer).
"""
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class PostingSetCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    account_ids: List[str] = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(default="indigo", max_length=30)
    icon: Optional[str] = Field(default=None, max_length=30)
    workspace_id: Optional[str] = Field(default=None, max_length=100)


class PostingSetUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    account_ids: Optional[List[str]] = Field(default=None, min_length=1, max_length=50)
    color: Optional[str] = Field(default=None, max_length=30)
    icon: Optional[str] = Field(default=None, max_length=30)


class PostingSetResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    name: str
    account_ids: List[str]
    color: str = "indigo"
    icon: Optional[str] = None
    created_at: datetime
    updated_at: datetime
