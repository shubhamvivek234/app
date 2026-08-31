import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import AsyncMock, patch

from api.routes.user_webhooks import (
    _format_slack_payload,
    _format_discord_payload,
    _is_slack_webhook,
    _is_discord_webhook,
    dispatch_webhook_event,
    register_webhook,
    WebhookEndpointCreate,
)


class _FakeCollection:
    def __init__(self, items=None):
        self.items = items or []
        self.inserted = []

    async def find_one(self, query):
        for item in self.items:
            if all(item.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return item
        return None

    def find(self, query, projection=None):
        return self

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=20):
        return self.items

    async def count_documents(self, query):
        return len(self.items)

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.items.append(doc)
        return type("Result", (), {"inserted_id": doc.get("_id", ObjectId())})()

    async def update_one(self, query, update, upsert=False):
        return type("Result", (), {"matched_count": 1, "modified_count": 1})()


class _FakeDB:
    def __init__(self):
        self.webhook_endpoints = _FakeCollection()
        self.webhook_deliveries = _FakeCollection()
        self.users = _FakeCollection()


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
async def test_webhook_register_and_dispatch():
    db = _FakeDB()
    user = {"user_id": "usr_123", "default_workspace_id": "ws_123"}

    # Mock ssrf_guard.is_safe_url to return True for test URLs
    with patch("api.routes.user_webhooks.is_safe_url", return_value=True):
        body = WebhookEndpointCreate(
            url="https://example.com/social-webhook",
            events=["post.published", "post.failed"],
            description="Production CRM Webhook",
        )
        resp = await register_webhook(body, current_user=user, db=db)

        assert resp.url == "https://example.com/social-webhook"
        assert resp.signing_secret is not None
        assert resp.signing_secret.startswith("whsec_")
        assert len(db.webhook_endpoints.items) == 1

        # Test dispatching event
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = type("Resp", (), {"status_code": 200, "text": "ok"})()
            await dispatch_webhook_event(
                db,
                workspace_id="ws_123",
                event="post.published",
                payload={"post_id": "p_test", "title": "Published post", "status": "published"}
            )
            assert mock_post.called
