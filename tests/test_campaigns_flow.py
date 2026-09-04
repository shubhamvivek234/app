"""
Unit tests for Campaigns Hub end-to-end features:
- POST /campaigns creates campaign with full metadata
- GET /campaigns lists campaigns with status counts, short link clicks, and CPC/CPE calculations
- GET /campaigns/{id} provides status breakdown, platform breakdown, short links, and engagement metrics
- POST /campaigns/{id}/blueprint generates 5-stage marketing blueprint with deterministic fallback
- Short link campaign_id association and filtering
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from api.routes.campaigns import (
    CampaignCreate,
    CampaignUpdate,
    BlueprintRequest,
    create_campaign,
    list_campaigns,
    get_campaign_detail,
    update_campaign,
    delete_campaign,
    generate_campaign_blueprint,
)
from api.routes.short_links import ShortLinkCreate, create_short_link, list_short_links


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

    async def update_one(self, query, update):
        for item in self.items:
            match = all(item.get(k) == v for k, v in query.items())
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return True
        return False

    async def delete_one(self, query):
        initial_len = len(self.items)
        self.items = [item for item in self.items if not all(item.get(k) == v for k, v in query.items())]
        mock_res = AsyncMock()
        mock_res.deleted_count = initial_len - len(self.items)
        return mock_res

    async def count_documents(self, query=None):
        cursor = self.find(query)
        items = await cursor.to_list(None)
        return len(items)

    async def update_many(self, query, update):
        for item in self.items:
            match = all(item.get(k) == v for k, v in query.items())
            if match and "$set" in update:
                item.update(update["$set"])
        return True


class FakeDB:
    def __init__(self):
        self.campaigns = FakeCollection()
        self.posts = FakeCollection()
        self.short_links = FakeCollection()


@pytest.mark.asyncio
async def test_campaign_creation_and_listing_metrics():
    db = FakeDB()
    user = {"user_id": "usr_100", "default_workspace_id": "ws_alpha"}

    # 1. Create campaign
    create_body = CampaignCreate(
        name="Summer Launch 2026",
        description="Major product rollout across Twitter and LinkedIn",
        color="#10b981",
        budget=1000.0,
        target_platforms=["twitter", "linkedin"],
        tags=["launch", "saas"],
    )
    res = await create_campaign(body=create_body, current_user=user, db=db)
    assert res.id.startswith("cmp_")
    assert res.name == "Summer Launch 2026"
    assert res.budget == 1000.0
    assert res.post_count == 0

    # 2. Add posts associated with this campaign
    await db.posts.insert_one({
        "id": "post_1",
        "workspace_id": "ws_alpha",
        "campaign_id": res.id,
        "status": "published",
        "platforms": ["twitter"],
        "metrics": {"impressions": 5000, "likes": 200, "retweets": 50},
        "created_at": datetime.now(timezone.utc),
    })
    await db.posts.insert_one({
        "id": "post_2",
        "workspace_id": "ws_alpha",
        "campaign_id": res.id,
        "status": "scheduled",
        "platforms": ["linkedin"],
        "metrics": {},
        "created_at": datetime.now(timezone.utc),
    })
    await db.posts.insert_one({
        "id": "post_3",
        "workspace_id": "ws_alpha",
        "campaign_id": res.id,
        "status": "draft",
        "platforms": ["twitter"],
        "metrics": {},
        "created_at": datetime.now(timezone.utc),
    })

    # 3. Add short link associated with this campaign
    await db.short_links.insert_one({
        "id": "sl_1",
        "workspace_id": "ws_alpha",
        "campaign_id": res.id,
        "code": "launch26",
        "clicks_count": 250,
    })

    # 4. List campaigns and check computed metrics
    listed = await list_campaigns(current_user=user, db=db)
    assert len(listed) == 1
    cmp_item = listed[0]
    assert cmp_item.post_count == 3
    assert cmp_item.published_count == 1
    assert cmp_item.scheduled_count == 1
    assert cmp_item.draft_count == 1
    assert cmp_item.total_clicks == 250
    assert cmp_item.total_impressions == 5000
    assert cmp_item.total_engagements == 250
    # CPC = 1000 / 250 = 4.0
    assert cmp_item.cpc == 4.0
    # CPE = 1000 / 250 = 4.0
    assert cmp_item.cpe == 4.0


@pytest.mark.asyncio
async def test_campaign_detail_breakdown():
    db = FakeDB()
    user = {"user_id": "usr_100", "default_workspace_id": "ws_alpha"}

    # Seed campaign
    cmp_doc = {
        "id": "cmp_test_detail",
        "workspace_id": "ws_alpha",
        "user_id": "usr_100",
        "name": "Black Friday Sale",
        "description": "Flash discounts and promos",
        "color": "#ef4444",
        "budget": 500.0,
        "target_platforms": ["twitter", "facebook"],
        "tags": ["promo"],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.campaigns.insert_one(cmp_doc)

    await db.posts.insert_one({
        "id": "p1",
        "workspace_id": "ws_alpha",
        "campaign_id": "cmp_test_detail",
        "status": "published",
        "platforms": ["twitter", "facebook"],
        "metrics": {"impressions": 1000, "likes": 50},
        "created_at": datetime.now(timezone.utc),
    })

    await db.short_links.insert_one({
        "id": "link_1",
        "workspace_id": "ws_alpha",
        "campaign_id": "cmp_test_detail",
        "code": "bfsale",
        "original_url": "https://example.com/sale",
        "final_url": "https://example.com/sale?utm_campaign=Black%20Friday%20Sale",
        "clicks_count": 100,
    })

    detail = await get_campaign_detail(campaign_id="cmp_test_detail", current_user=user, db=db)
    assert detail["campaign"]["name"] == "Black Friday Sale"
    assert detail["post_count"] == 1
    assert detail["status_breakdown"] == {"published": 1, "scheduled": 0, "draft": 0, "failed": 0}
    assert detail["platform_breakdown"]["twitter"] == 1
    assert detail["platform_breakdown"]["facebook"] == 1
    assert len(detail["short_links"]) == 1
    assert detail["short_links"][0]["code"] == "bfsale"
    assert detail["metrics"]["total_clicks"] == 100
    assert detail["metrics"]["total_impressions"] == 1000
    assert detail["metrics"]["total_engagements"] == 50
    assert detail["metrics"]["cpc"] == 5.0
    assert detail["metrics"]["cpe"] == 10.0


@pytest.mark.asyncio
async def test_ai_campaign_blueprint_generation():
    db = FakeDB()
    user = {"user_id": "usr_100", "default_workspace_id": "ws_alpha"}

    cmp_doc = {
        "id": "cmp_ai_gen",
        "workspace_id": "ws_alpha",
        "user_id": "usr_100",
        "name": "AI Video Studio",
        "description": "Generate viral shorts from long videos automatically",
        "target_platforms": ["twitter", "linkedin", "youtube"],
        "tags": ["video", "creator", "ai"],
        "color": "#6366f1",
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.campaigns.insert_one(cmp_doc)

    req = BlueprintRequest(themes=["creator economy", "productivity"])
    bp = await generate_campaign_blueprint(campaign_id="cmp_ai_gen", body=req, current_user=user, db=db)
    assert bp.campaign_id == "cmp_ai_gen"
    assert bp.campaign_name == "AI Video Studio"
    assert len(bp.posts) == 5
    stages = [p.stage.lower() for p in bp.posts]
    assert any("teaser" in s for s in stages)
    assert any("reveal" in s or "launch" in s for s in stages)
    assert any("deep dive" in s or "value" in s for s in stages)
    assert any("social proof" in s or "transformation" in s for s in stages)
    assert any("urgency" in s or "last call" in s for s in stages)


@pytest.mark.asyncio
async def test_short_link_campaign_association():
    db = FakeDB()
    user = {"user_id": "usr_100", "default_workspace_id": "ws_alpha"}

    sl_req = ShortLinkCreate(
        original_url="https://myapp.com/checkout",
        custom_slug="summer26",
        campaign_id="cmp_123",
        utm_campaign="Summer Promo",
        utm_source="twitter",
        utm_medium="social",
    )
    sl = await create_short_link(payload=sl_req, current_user=user, db=db)
    assert sl.code == "summer26"
    assert sl.campaign_id == "cmp_123"
    assert "utm_campaign=Summer+Promo" in sl.final_url

    filtered_links = await list_short_links(current_user=user, db=db, campaign_id="cmp_123")
    assert len(filtered_links) == 1
    assert filtered_links[0].campaign_id == "cmp_123"
