import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from bson import ObjectId

from api.main import create_app
from api.routes.user_webhooks import (
    _format_slack_payload,
    _format_discord_payload,
    _is_slack_webhook,
    _is_discord_webhook,
    dispatch_webhook_event,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_slack_discord_formatters():
    sample_payload = {
        "post_id": "p_123",
        "title": "My Exciting Announcement",
        "platforms": ["twitter", "linkedin"],
        "status": "published",
    }
    slack_blocks = _format_slack_payload("post.published", sample_payload)
    assert "blocks" in slack_blocks
    assert len(slack_blocks["blocks"]) >= 2
    assert "Unravler: post.published" in slack_blocks["blocks"][0]["text"]["text"]

    discord_embeds = _format_discord_payload("post.published", sample_payload)
    assert "embeds" in discord_embeds
    assert discord_embeds["embeds"][0]["color"] == 0x10B981

    assert _is_slack_webhook("https://hooks.slack.com/services/T00/B00/XXXX") is True
    assert _is_discord_webhook("https://discord.com/api/webhooks/12345/abcdef") is True
    assert _is_slack_webhook("https://api.mybrand.com/webhook") is False


@pytest.mark.asyncio
async def test_webhook_crud_and_dispatch(test_db):
    user_id = "test_user_wh"
    workspace_id = "ws_test_wh"

    # Seed user & workspace
    await test_db.users.insert_one({
        "user_id": user_id,
        "email": "wh_tester@example.com",
        "default_workspace_id": workspace_id,
        "email_verified": True,
        "is_active": True,
    })

    # Register endpoint directly in collection
    secret = "whsec_1234567890abcdef"
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    endpoint_id = ObjectId()

    await test_db.webhook_endpoints.insert_one({
        "_id": endpoint_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "url": "https://httpbin.org/post",
        "events": ["post.published", "post.failed"],
        "description": "Test endpoint",
        "signing_secret_hash": secret_hash,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    })

    # Verify listing finds it
    endpoints = await test_db.webhook_endpoints.find({"workspace_id": workspace_id, "active": True}).to_list(length=10)
    assert len(endpoints) == 1
    assert endpoints[0]["url"] == "https://httpbin.org/post"

    # Test dispatching with no exception
    await dispatch_webhook_event(
        test_db,
        workspace_id=workspace_id,
        event="post.published",
        payload={"post_id": "p_test", "title": "Test dispatch", "status": "published"}
    )
