"""Models for third-party OAuth2 Applications in Developer Settings."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class OAuthAppCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80, description="Application display name")
    redirect_uris: List[str] = Field(..., min_length=1, max_length=10, description="Authorized redirect URIs")
    description: Optional[str] = Field(default="", max_length=300)
    homepage_url: Optional[str] = Field(default="", max_length=200)
    logo_url: Optional[str] = Field(default="", max_length=500)


class OAuthAppUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    redirect_uris: Optional[List[str]] = Field(default=None, min_length=1, max_length=10)
    description: Optional[str] = Field(default=None, max_length=300)
    homepage_url: Optional[str] = Field(default=None, max_length=200)
    logo_url: Optional[str] = Field(default=None, max_length=500)


class OAuthAppResponse(BaseModel):
    id: str
    name: str
    client_id: str
    client_secret: Optional[str] = None  # returned only upon creation / rotation
    redirect_uris: List[str]
    description: str = ""
    homepage_url: str = ""
    logo_url: str = ""
    created_at: datetime
    is_active: bool = True
