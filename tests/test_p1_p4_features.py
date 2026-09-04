"""
Unit tests for Postpeer-inspired features (P1–P4):
- P1: Public API Campaign & Calendar endpoints (GET /campaigns, GET /campaigns/{id}, GET /calendar)
- P2: Granular retry isolation & failure deep-linking
- P3: Webhook payload formatting for post.partial_failed with error diagnostics
- P4: Google Business Profile (GBP) integration (Adapter, Post Models, Direct Connect)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from api.routes import public_api as public_route
from api.routes import user_webhooks as webhook_route
from api.routes import accounts as accounts_route
from api.models.post import CreatePostRequest, PlatformOverride, PostResponse
from platform_adapters.google_business import GoogleBusinessAdapter
from platform_adapters import get_adapter


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, length):
        self.items = self.items[:length]
        return self

    def skip(self, offset):
        self.items = self.items[offset:]
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, initial=None):
        self.items = list(initial or [])

    def find(self, query=None, projection=None, *args, **kwargs):
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    or_matched = False
                    for branch in v:
                        if all(item.get(bk) == bv for bk, bv in branch.items()):
                            or_matched = True
                            break
                    if not or_matched:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$in" in v:
                        if item.get(k) not in v["$in"]:
                            match = False
                            break
                    if "$exists" in v:
                        exists = k in item
                        if exists != v["$exists"]:
                            match = False
                            break
                    if "$gte" in v or "$lte" in v:
                        val = item.get(k)
                        if isinstance(val, str):
                            try:
                                val = datetime.fromisoformat(val.replace("Z", "+00:00"))
                            except ValueError:
                                pass
                        if "$gte" in v and val < v["$gte"]:
                            match = False
                            break
                        if "$lte" in v and val > v["$lte"]:
                            match = False
                            break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))
        return FakeCursor(matched)

    async def find_one(self, query=None, projection=None, *args, **kwargs):
        cursor = self.find(query, projection)
        items = await cursor.to_list(1)
        return items[0] if items else None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return True

    async def update_one(self, query, update, upsert=False):
        for item in self.items:
            match = all(item.get(k) == v for k, v in query.items())
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return True
        if upsert:
            new_item = dict(query)
            if "$set" in update:
                new_item.update(update["$set"])
            self.items.append(new_item)
            return True
        return False


class FakeDB:
    def __init__(self):
        self.campaigns = FakeCollection()
        self.posts = FakeCollection()
        self.social_accounts = FakeCollection()
        self.short_links = FakeCollection()


# ── P1: Public API Campaign & Calendar Endpoints ──────────────────────────────

@pytest.mark.asyncio
async def test_p1_public_api_campaigns_and_calendar():
    db = FakeDB()
    user_id = "user_p1_test"
    auth_ctx = {"user_id": user_id, "token_name": "MCP Server"}

    # Seed campaign
    camp_doc = {
        "campaign_id": "camp_fall_2026",
        "id": "camp_fall_2026",
        "user_id": user_id,
        "workspace_id": user_id,
        "name": "Fall Launch 2026",
        "description": "Global seasonal promo",
        "color": "#3B82F6",
        "status": "active",
        "start_date": "2026-09-01T00:00:00Z",
        "end_date": "2026-09-30T23:59:59Z",
        "target_channels": ["twitter", "linkedin", "google_business"],
        "total_budget": 500.0,
        "created_at": datetime.now(timezone.utc),
    }
    await db.campaigns.insert_one(camp_doc)

    # Seed posts
    post1 = {
        "id": "post_p1_1",
        "user_id": user_id,
        "workspace_id": user_id,
        "campaign_id": "camp_fall_2026",
        "content": "Exciting news coming soon!",
        "status": "published",
        "platforms": ["twitter"],
        "scheduled_time": "2026-09-05T10:00:00Z",
        "analytics": {"impressions": 1500, "clicks": 250, "engagements": 300},
    }
    post2 = {
        "id": "post_p1_2",
        "user_id": user_id,
        "workspace_id": user_id,
        "campaign_id": "camp_fall_2026",
        "content": "Special offer on Google Maps!",
        "status": "scheduled",
        "platforms": ["google_business"],
        "scheduled_time": "2026-09-10T14:00:00Z",
    }
    await db.posts.insert_one(post1)
    await db.posts.insert_one(post2)

    from starlette.requests import Request as StarletteRequest

    fake_request = StarletteRequest({
        "type": "http",
        "method": "GET",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "path": "/api/v1/campaigns",
    })

    with patch("api.routes.public_api._resolve_public_principal", new_callable=AsyncMock) as mock_principal:
        mock_principal.return_value = ({"token_name": "MCP"}, {"user_id": user_id})

        # Test public_list_campaigns
        camp_list = await public_route.public_list_campaigns(request=fake_request, db=db)
        assert len(camp_list) == 1
        assert camp_list[0].name == "Fall Launch 2026"
        assert camp_list[0].post_count == 2
        assert camp_list[0].published_count == 1
        assert camp_list[0].scheduled_count == 1

        # Test public_get_campaign
        camp_detail = await public_route.public_get_campaign(
            request=fake_request,
            campaign_id="camp_fall_2026",
            db=db,
        )
        assert camp_detail["campaign"]["id"] == "camp_fall_2026"
        assert camp_detail["status_breakdown"]["published"] == 1
        assert camp_detail["status_breakdown"]["scheduled"] == 1
        assert len(camp_detail["posts"]) == 2

        # Test public_get_calendar
        calendar_res = await public_route.public_get_calendar(
            request=fake_request,
            db=db,
            start_date="2026-09-01T00:00:00Z",
            end_date="2026-09-30T23:59:59Z",
        )
        assert len(calendar_res) == 2
        assert calendar_res[0]["campaign_id"] == "camp_fall_2026"


# ── P2: Granular Error Diagnostics & Retry Deep Linking ───────────────────────

@pytest.mark.asyncio
async def test_p2_deep_link_notification_and_retry_behavior():
    from celery_workers.tasks.publish import _emit_aggregate_publish_notification

    fake_db = FakeDB()
    user_id = "user_p2_notif"
    post_id = "post_12345"

    post_doc = {
        "id": post_id,
        "user_id": user_id,
        "content": "Test lifecycle notification",
        "platforms": ["twitter", "instagram"],
    }
    result_entries = {
        "twitter": {"status": "published", "platform": "twitter"},
        "instagram": {"status": "failed", "platform": "instagram", "error": "Aspect ratio invalid"},
    }

    with patch("utils.notifications.emit_notification", new_callable=AsyncMock) as mock_emit:
        await _emit_aggregate_publish_notification(
            fake_db,
            post=post_doc,
            aggregate_status="partial",
            result_entries=result_entries,
            created_at=datetime.now(timezone.utc),
        )
        assert mock_emit.called
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["notification_type"] == "post.partial_failed"
        assert f"highlightPost={post_id}" in kwargs["target_path"]
        assert kwargs["user_id"] == user_id


# ── P3: Webhooks post.partial_failed and Error Diagnostics ────────────────────

def test_p3_webhook_partial_failed_payload_diagnostics():
    payload = {
        "post_id": "post_p3_test",
        "content": "Announcing our new feature suite!",
        "status": "partial",
        "platforms": ["twitter", "linkedin", "instagram"],
        "failed_platforms": ["instagram"],
        "media_urls": ["https://example.com/banner.png"],
    }

    # Slack formatted payload
    slack_payload = webhook_route._format_slack_payload(
        event="post.partial_failed",
        payload=payload,
    )
    assert "Unravler: post.partial_failed" in slack_payload["blocks"][0]["text"]["text"]
    section_text = slack_payload["blocks"][1]["text"]["text"]
    assert "instagram" in section_text
    assert "Failed Targets" in section_text

    # Discord formatted payload
    discord_payload = webhook_route._format_discord_payload(
        event="post.partial_failed",
        payload=payload,
    )
    embed = discord_payload["embeds"][0]
    assert "post.partial_failed" in embed["title"]
    assert "instagram" in embed["description"]
    assert "Failed Targets" in embed["description"]


# ── P4: Google Business Profile (GBP) Integration ─────────────────────────────

@pytest.mark.asyncio
async def test_p4_google_business_adapter_and_model():
    # Verify adapter registration
    adapter = get_adapter("google_business")
    assert isinstance(adapter, GoogleBusinessAdapter)

    gbp_adapter = get_adapter("gbp")
    assert isinstance(gbp_adapter, GoogleBusinessAdapter)

    # Test publish method (fallback / sandbox mode)
    account_doc = {
        "account_id": "gbp_acc_1",
        "platform": "google_business",
        "platform_user_id": "locations/10987654321",
        "platform_username": "Downtown Cafe",
    }
    post_doc = {
        "id": "post_gbp_1",
        "content": "Fresh artisan roast is here! Stop by or order online.",
        "media_urls": ["https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb"],
        "platform_overrides": {
            "google_business": {
                "topic_type": "STANDARD",
                "call_to_action": "ORDER",
                "action_url": "https://example.com/menu",
            }
        },
    }

    result = await adapter.publish(post_doc, account_doc)
    assert result["platform_post_id"].startswith("gbp_")
    assert "maps.google.com" in result["post_url"]
    assert "published_at" in result

    # Test Pydantic CreatePostRequest with google_business
    create_req = CreatePostRequest(
        content="Testing GBP post validation",
        platforms=["google_business"],
        platform_overrides={
            "google_business": PlatformOverride(
                google_business_topic_type="STANDARD",
                google_business_call_to_action="BOOK",
                google_business_action_url="https://example.com/book",
            )
        }
    )
    assert "google_business" in create_req.platforms
    assert create_req.platform_overrides["google_business"].google_business_call_to_action == "BOOK"


@pytest.mark.asyncio
async def test_p4_direct_connect_google_business_endpoint():
    db = FakeDB()
    user_id = "user_gbp_connect"
    current_user = {"user_id": user_id, "email": "store@example.com"}

    body = accounts_route.GoogleBusinessConnectRequest(
        location_id="locations/99887766",
        location_name="Midtown Coffee Hub",
    )

    with patch("api.routes.accounts.encrypt", side_effect=lambda x: f"enc_{x}"):
        res = await accounts_route.connect_google_business(body, current_user, db)

    assert res["connected"] is True
    assert res["location_id"] == "locations/99887766"
    assert res["location_name"] == "Midtown Coffee Hub"

    saved_account = await db.social_accounts.find_one({"user_id": user_id, "platform": "google_business"})
    assert saved_account is not None
    assert saved_account["platform_user_id"] == "locations/99887766"
    assert saved_account["platform_username"] == "Midtown Coffee Hub"
    assert saved_account["is_active"] is True
