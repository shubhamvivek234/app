"""Unit tests for channel/account scoped outbound webhooks."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from api.routes.user_webhooks import dispatch_webhook_event


@pytest.mark.asyncio
async def test_dispatch_webhook_scoped_filtering():
    db = MagicMock()
    db.webhook_deliveries = MagicMock()
    db.webhook_deliveries.insert_one = AsyncMock()

    # Endpoint 1: scoped to acc_twitter only
    endpoint_1 = {
        "_id": ObjectId(),
        "workspace_id": "ws_test",
        "url": "https://example.com/webhook/twitter",
        "events": ["post.published"],
        "scoped_account_ids": ["acc_twitter"],
        "signing_secret_hash": "secret_1",
    }

    # Endpoint 2: scoped to acc_linkedin only
    endpoint_2 = {
        "_id": ObjectId(),
        "workspace_id": "ws_test",
        "url": "https://example.com/webhook/linkedin",
        "events": ["post.published"],
        "scoped_account_ids": ["acc_linkedin"],
        "signing_secret_hash": "secret_2",
    }

    # Endpoint 3: all channels (empty scope)
    endpoint_3 = {
        "_id": ObjectId(),
        "workspace_id": "ws_test",
        "url": "https://example.com/webhook/all",
        "events": ["post.published"],
        "scoped_account_ids": [],
        "signing_secret_hash": "secret_3",
    }

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[endpoint_1, endpoint_2, endpoint_3])
    db.webhook_endpoints.find = MagicMock(return_value=mock_cursor)

    # Post event published only for acc_twitter
    payload = {
        "post_id": "p_123",
        "content": "Hello Twitter!",
        "account_ids": ["acc_twitter"],
        "platforms": ["twitter"],
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        await dispatch_webhook_event(db, "ws_test", "post.published", payload)

        # Expected: called for endpoint_1 (acc_twitter) and endpoint_3 (all), but NOT endpoint_2 (acc_linkedin)
        called_urls = [call.args[0] for call in mock_post.call_args_list]
        assert "https://example.com/webhook/twitter" in called_urls
        assert "https://example.com/webhook/all" in called_urls
        assert "https://example.com/webhook/linkedin" not in called_urls
