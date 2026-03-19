"""
Phase 9.5.2 -- Platform Sandbox / Test Account Configuration.

Loads sandbox credentials from environment variables. Each platform has
a dedicated configuration dataclass. Tests skip gracefully when credentials
are not available.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class InstagramSandboxConfig:
    """Instagram Graph API test user configuration."""

    access_token: str
    user_id: str
    page_id: str
    api_version: str = "v18.0"
    base_url: str = "https://graph.facebook.com"

    @property
    def graph_url(self) -> str:
        return f"{self.base_url}/{self.api_version}"

    @classmethod
    def from_env(cls) -> InstagramSandboxConfig | None:
        token = os.environ.get("SANDBOX_INSTAGRAM_ACCESS_TOKEN")
        user_id = os.environ.get("SANDBOX_INSTAGRAM_USER_ID")
        page_id = os.environ.get("SANDBOX_INSTAGRAM_PAGE_ID")
        if not all([token, user_id, page_id]):
            return None
        return cls(access_token=token, user_id=user_id, page_id=page_id)


@dataclass(frozen=True)
class FacebookSandboxConfig:
    """Facebook test page with test app configuration."""

    page_access_token: str
    page_id: str
    app_id: str
    app_secret: str
    api_version: str = "v18.0"
    base_url: str = "https://graph.facebook.com"

    @property
    def graph_url(self) -> str:
        return f"{self.base_url}/{self.api_version}"

    @classmethod
    def from_env(cls) -> FacebookSandboxConfig | None:
        token = os.environ.get("SANDBOX_FACEBOOK_PAGE_TOKEN")
        page_id = os.environ.get("SANDBOX_FACEBOOK_PAGE_ID")
        app_id = os.environ.get("SANDBOX_FACEBOOK_APP_ID")
        app_secret = os.environ.get("SANDBOX_FACEBOOK_APP_SECRET")
        if not all([token, page_id, app_id, app_secret]):
            return None
        return cls(
            page_access_token=token,
            page_id=page_id,
            app_id=app_id,
            app_secret=app_secret,
        )


@dataclass(frozen=True)
class YouTubeSandboxConfig:
    """YouTube OAuth playground configuration."""

    client_id: str
    client_secret: str
    refresh_token: str
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"
    token_url: str = "https://oauth2.googleapis.com/token"
    upload_url: str = "https://www.googleapis.com/upload/youtube/v3/videos"
    api_url: str = "https://www.googleapis.com/youtube/v3"

    @classmethod
    def from_env(cls) -> YouTubeSandboxConfig | None:
        client_id = os.environ.get("SANDBOX_YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("SANDBOX_YOUTUBE_CLIENT_SECRET")
        refresh_token = os.environ.get("SANDBOX_YOUTUBE_REFRESH_TOKEN")
        if not all([client_id, client_secret, refresh_token]):
            return None
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )


@dataclass(frozen=True)
class TwitterSandboxConfig:
    """Twitter/X sandbox app credentials (OAuth 2.0 with PKCE or OAuth 1.0a)."""

    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    bearer_token: str
    api_url: str = "https://api.twitter.com/2"

    @classmethod
    def from_env(cls) -> TwitterSandboxConfig | None:
        api_key = os.environ.get("SANDBOX_TWITTER_API_KEY")
        api_secret = os.environ.get("SANDBOX_TWITTER_API_SECRET")
        access_token = os.environ.get("SANDBOX_TWITTER_ACCESS_TOKEN")
        access_secret = os.environ.get("SANDBOX_TWITTER_ACCESS_TOKEN_SECRET")
        bearer = os.environ.get("SANDBOX_TWITTER_BEARER_TOKEN")
        if not all([api_key, api_secret, access_token, access_secret, bearer]):
            return None
        return cls(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            bearer_token=bearer,
        )


@dataclass(frozen=True)
class LinkedInSandboxConfig:
    """LinkedIn developer test organization configuration."""

    access_token: str
    organization_id: str
    person_urn: str
    api_url: str = "https://api.linkedin.com/v2"

    @classmethod
    def from_env(cls) -> LinkedInSandboxConfig | None:
        token = os.environ.get("SANDBOX_LINKEDIN_ACCESS_TOKEN")
        org_id = os.environ.get("SANDBOX_LINKEDIN_ORG_ID")
        person = os.environ.get("SANDBOX_LINKEDIN_PERSON_URN")
        if not all([token, org_id, person]):
            return None
        return cls(access_token=token, organization_id=org_id, person_urn=person)


@dataclass(frozen=True)
class TikTokSandboxConfig:
    """TikTok sandbox environment configuration."""

    access_token: str
    open_id: str
    api_url: str = "https://open.tiktokapis.com/v2"

    @classmethod
    def from_env(cls) -> TikTokSandboxConfig | None:
        token = os.environ.get("SANDBOX_TIKTOK_ACCESS_TOKEN")
        open_id = os.environ.get("SANDBOX_TIKTOK_OPEN_ID")
        if not all([token, open_id]):
            return None
        return cls(access_token=token, open_id=open_id)


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

ALL_PLATFORMS = {
    "instagram": InstagramSandboxConfig,
    "facebook": FacebookSandboxConfig,
    "youtube": YouTubeSandboxConfig,
    "twitter": TwitterSandboxConfig,
    "linkedin": LinkedInSandboxConfig,
    "tiktok": TikTokSandboxConfig,
}


def load_sandbox_config(platform: str):
    """Load sandbox config for a platform. Returns None if credentials missing."""
    config_cls = ALL_PLATFORMS.get(platform)
    if config_cls is None:
        raise ValueError(f"Unknown platform: {platform}")
    return config_cls.from_env()
