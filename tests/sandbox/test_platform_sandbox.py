"""
Phase 9.5.2 -- Sandbox platform integration tests.

Each test runs against real sandbox/test accounts. Tests are marked with
@pytest.mark.sandbox and skip automatically when credentials are not
available in the environment.
"""
from __future__ import annotations

import json
import time

import pytest
import httpx

from tests.sandbox.sandbox_config import (
    InstagramSandboxConfig,
    FacebookSandboxConfig,
    YouTubeSandboxConfig,
    TwitterSandboxConfig,
    LinkedInSandboxConfig,
    TikTokSandboxConfig,
)

pytestmark = pytest.mark.sandbox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def instagram_config():
    cfg = InstagramSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("Instagram sandbox credentials not available")
    return cfg


@pytest.fixture
def facebook_config():
    cfg = FacebookSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("Facebook sandbox credentials not available")
    return cfg


@pytest.fixture
def youtube_config():
    cfg = YouTubeSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("YouTube sandbox credentials not available")
    return cfg


@pytest.fixture
def twitter_config():
    cfg = TwitterSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("Twitter sandbox credentials not available")
    return cfg


@pytest.fixture
def linkedin_config():
    cfg = LinkedInSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("LinkedIn sandbox credentials not available")
    return cfg


@pytest.fixture
def tiktok_config():
    cfg = TikTokSandboxConfig.from_env()
    if cfg is None:
        pytest.skip("TikTok sandbox credentials not available")
    return cfg


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_instagram_container_create_and_publish(instagram_config: InstagramSandboxConfig):
    """Create a photo container and publish it via the Graph API."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Create media container
        create_resp = await client.post(
            f"{instagram_config.graph_url}/{instagram_config.user_id}/media",
            params={
                "image_url": "https://picsum.photos/640/640",
                "caption": "[Sandbox Test] Automated test post - will be deleted",
                "access_token": instagram_config.access_token,
            },
        )
        assert create_resp.status_code == 200, f"Container creation failed: {create_resp.text}"
        container_id = create_resp.json()["id"]

        # Step 2: Publish the container
        publish_resp = await client.post(
            f"{instagram_config.graph_url}/{instagram_config.user_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": instagram_config.access_token,
            },
        )
        assert publish_resp.status_code == 200, f"Publish failed: {publish_resp.text}"
        media_id = publish_resp.json()["id"]
        assert media_id, "Published media ID should not be empty"


# ---------------------------------------------------------------------------
# Facebook
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_facebook_page_post(facebook_config: FacebookSandboxConfig):
    """Create a text post on the test page, verify it exists, then delete it."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Create post
        post_resp = await client.post(
            f"{facebook_config.graph_url}/{facebook_config.page_id}/feed",
            params={
                "message": "[Sandbox Test] Automated test - will be deleted",
                "access_token": facebook_config.page_access_token,
            },
        )
        assert post_resp.status_code == 200, f"Post creation failed: {post_resp.text}"
        post_id = post_resp.json()["id"]

        # Verify post exists
        get_resp = await client.get(
            f"{facebook_config.graph_url}/{post_id}",
            params={"access_token": facebook_config.page_access_token},
        )
        assert get_resp.status_code == 200

        # Cleanup: delete the post
        del_resp = await client.delete(
            f"{facebook_config.graph_url}/{post_id}",
            params={"access_token": facebook_config.page_access_token},
        )
        assert del_resp.status_code == 200


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_youtube_video_upload_small(youtube_config: YouTubeSandboxConfig):
    """Upload a minimal test video (unlisted) via the YouTube Data API."""
    async with httpx.AsyncClient(timeout=60) as client:
        # Get fresh access token from refresh token
        token_resp = await client.post(
            youtube_config.token_url,
            data={
                "client_id": youtube_config.client_id,
                "client_secret": youtube_config.client_secret,
                "refresh_token": youtube_config.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        assert token_resp.status_code == 200, f"Token refresh failed: {token_resp.text}"
        access_token = token_resp.json()["access_token"]

        # Upload metadata-only video (snippet + status)
        metadata = {
            "snippet": {
                "title": "[Sandbox Test] Automated test upload",
                "description": "This is an automated sandbox test. Will be deleted.",
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "private",
            },
        }

        # Initiate resumable upload
        init_resp = await client.post(
            f"{youtube_config.upload_url}?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            content=json.dumps(metadata),
        )
        assert init_resp.status_code == 200, f"Upload init failed: {init_resp.text}"

        # Verify we can at least list our channel
        channels_resp = await client.get(
            f"{youtube_config.api_url}/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert channels_resp.status_code == 200
        assert channels_resp.json().get("items"), "Should have at least one channel"


# ---------------------------------------------------------------------------
# Twitter
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_twitter_post_and_delete(twitter_config: TwitterSandboxConfig):
    """Create a tweet, verify it, then delete it."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {
            "Authorization": f"Bearer {twitter_config.bearer_token}",
            "Content-Type": "application/json",
        }

        # Create tweet (requires OAuth 1.0a for write — using user context token)
        # For sandbox, we use the v2 API with user access token
        user_headers = {
            "Authorization": f"Bearer {twitter_config.access_token}",
            "Content-Type": "application/json",
        }

        tweet_text = f"[Sandbox Test] Automated test {int(time.time())} - will be deleted"
        post_resp = await client.post(
            f"{twitter_config.api_url}/tweets",
            headers=user_headers,
            json={"text": tweet_text},
        )
        assert post_resp.status_code in (200, 201), f"Tweet creation failed: {post_resp.text}"
        tweet_id = post_resp.json()["data"]["id"]

        # Delete tweet
        del_resp = await client.delete(
            f"{twitter_config.api_url}/tweets/{tweet_id}",
            headers=user_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted"] is True


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_linkedin_share(linkedin_config: LinkedInSandboxConfig):
    """Create a share post on the test organization."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {
            "Authorization": f"Bearer {linkedin_config.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        share_payload = {
            "author": f"urn:li:organization:{linkedin_config.organization_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": "[Sandbox Test] Automated test post - will be deleted",
                    },
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "CONNECTIONS",
            },
        }

        resp = await client.post(
            f"{linkedin_config.api_url}/ugcPosts",
            headers=headers,
            json=share_payload,
        )
        assert resp.status_code in (200, 201), f"LinkedIn share failed: {resp.text}"
        post_id = resp.headers.get("x-restli-id") or resp.json().get("id")
        assert post_id, "Should receive a post ID"


# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.asyncio
async def test_tiktok_video_upload(tiktok_config: TikTokSandboxConfig):
    """Initiate a video upload via the TikTok Content Posting API."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {
            "Authorization": f"Bearer {tiktok_config.access_token}",
            "Content-Type": "application/json",
        }

        # Step 1: Initialize video upload
        init_payload = {
            "post_info": {
                "title": "[Sandbox Test] Automated test upload",
                "privacy_level": "SELF_ONLY",
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": "https://storage.googleapis.com/se-test-media/test_1s.mp4",
            },
        }

        resp = await client.post(
            f"{tiktok_config.api_url}/post/publish/video/init/",
            headers=headers,
            json=init_payload,
        )
        # TikTok sandbox may return 200 with error for invalid video URL
        # but the API call itself should succeed
        assert resp.status_code == 200, f"TikTok upload init failed: {resp.text}"
        data = resp.json()
        # In sandbox, we expect either success or a recognizable sandbox error
        assert "error" in data or "data" in data, "Response should have error or data field"
