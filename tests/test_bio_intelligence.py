"""
Unit tests for Cluster C (Bio Intelligence) features:
- Interactive Quick Poll voting (/public/bio/{handle}/poll/{block_id})
- NPS / Star Rating feedback submission (/public/bio/{handle}/feedback)
- Extended Lead Capture with custom tags & phone (/public/bio/{handle}/subscribe)
- Conversion Funnel & Heatmap click density analytics (/bio-pages/analytics)
- A/B Testing Variant management & traffic router (/bio-pages/variants)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from starlette.requests import Request

from api.routes.public_bio import (
    vote_bio_poll,
    submit_bio_feedback,
    subscribe_to_bio_newsletter,
    get_public_bio_page,
)
from api.routes.bio_pages import (
    get_bio_analytics,
    save_bio_variant,
    toggle_bio_variant,
    delete_bio_variant,
)
from api.models.bio import (
    BioPollVoteRequest,
    BioFeedbackRequest,
    BioLeadSubscribeRequest,
    BioVariant,
)


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
    def __init__(self, items=None):
        self.items = items if items is not None else []

    async def find_one(self, filter_query, *args, **kwargs):
        for it in self.items:
            match = True
            for k, v in filter_query.items():
                if k == "$or" and isinstance(v, list):
                    or_matched = any(
                        all(it.get(ok) == ov for ok, ov in cond.items()) for cond in v
                    )
                    if not or_matched:
                        match = False
                        break
                elif it.get(k) != v:
                    match = False
                    break
            if match:
                return it
        return None

    def find(self, filter_query=None, *args, **kwargs):
        if not filter_query:
            return FakeCursor(self.items)
        results = []
        for it in self.items:
            match = True
            for k, v in filter_query.items():
                if k == "$or" and isinstance(v, list):
                    or_matched = any(
                        all(it.get(ok) == ov for ok, ov in cond.items()) for cond in v
                    )
                    if not or_matched:
                        match = False
                        break
                elif it.get(k) != v:
                    match = False
                    break
            if match:
                results.append(it)
        return FakeCursor(results)

    async def insert_one(self, doc):
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.items.append(doc)
        mock_result = AsyncMock()
        mock_result.inserted_id = doc["_id"]
        return mock_result

    async def update_one(self, filter_query, update_query):
        for it in self.items:
            match = True
            for k, v in filter_query.items():
                if it.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update_query:
                    it.update(update_query["$set"])
                if "$inc" in update_query:
                    for ik, iv in update_query["$inc"].items():
                        it[ik] = it.get(ik, 0) + iv
                mock_result = AsyncMock()
                mock_result.matched_count = 1
                mock_result.modified_count = 1
                return mock_result
        mock_result = AsyncMock()
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        return mock_result

    def aggregate(self, pipeline=None):
        if pipeline and any("$group" in step for step in pipeline):
            results = []
            score_counts = {}
            for it in self.items:
                if it.get("event_type") == "nps_rating":
                    sc = it.get("score")
                    score_counts[sc] = score_counts.get(sc, 0) + 1
            for sc, cnt in score_counts.items():
                results.append({"_id": sc, "count": cnt})
            return FakeCursor(results)
        return FakeCursor([])

    async def update_many(self, filter_query, update_query):
        matched = 0
        for it in self.items:
            match = True
            for k, v in filter_query.items():
                if it.get(k) != v:
                    match = False
                    break
            if match:
                matched += 1
                if "$set" in update_query:
                    it.update(update_query["$set"])
                if "$inc" in update_query:
                    for ik, iv in update_query["$inc"].items():
                        it[ik] = it.get(ik, 0) + iv
        mock_result = AsyncMock()
        mock_result.matched_count = matched
        mock_result.modified_count = matched
        return mock_result

    async def count_documents(self, filter_query):
        count = 0
        for it in self.items:
            match = True
            for k, v in filter_query.items():
                if it.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count


class FakeDB:
    def __init__(self):
        self.bio_pages = FakeCollection()
        self.bio_polls = FakeCollection()
        self.bio_feedback = FakeCollection()
        self.workspace_leads = FakeCollection()
        self.bio_analytics = FakeCollection()
        self.bio_events = FakeCollection()
        self.automations = FakeCollection()
        self.automation_logs = FakeCollection()
        self.deals = FakeCollection()


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def fake_user():
    return {
        "_id": ObjectId(),
        "id": "user_c_test",
        "email": "creator@unravler.com",
        "name": "Sarah Connor",
        "current_workspace_id": "ws_cluster_c",
    }


def make_request(headers=None, client_host="127.0.0.1"):
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in headers.items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_vote_bio_poll(fake_db):
    """Test voting on a Quick Poll with vote tally incrementation."""
    bio_page = {
        "_id": ObjectId(),
        "handle": "techcreator",
        "user_id": "user_1",
        "workspace_id": "ws_1",
        "blocks": [
            {
                "id": "poll_block_1",
                "type": "poll",
                "poll_question": "Which language do you use most?",
                "poll_options": [
                    {"id": "opt_py", "text": "Python", "votes": 10},
                    {"id": "opt_js", "text": "JavaScript", "votes": 5},
                ],
            }
        ],
    }
    fake_db.bio_pages.items.append(bio_page)

    vote_payload = BioPollVoteRequest(option_id="opt_py")

    res = await vote_bio_poll("techcreator", "poll_block_1", vote_payload, db=fake_db)

    assert res["success"] is True
    assert res["total_votes"] == 16
    assert any(opt["id"] == "opt_py" and opt["votes"] == 11 for opt in res["options"])
    assert len(fake_db.bio_analytics.items) == 1
    assert fake_db.bio_analytics.items[0]["event_type"] == "poll_vote"


@pytest.mark.asyncio
async def test_submit_bio_feedback(fake_db):
    """Test submitting 5-star rating on Smart Bio."""
    bio_page = {
        "_id": ObjectId(),
        "handle": "artisan",
        "user_id": "user_2",
        "workspace_id": "ws_2",
        "blocks": [],
    }
    fake_db.bio_pages.items.append(bio_page)

    feedback_payload = BioFeedbackRequest(score=5, feedback="Loved your curated links!")

    res = await submit_bio_feedback("artisan", feedback_payload, db=fake_db)

    assert res["success"] is True
    assert len(fake_db.bio_analytics.items) == 1
    assert fake_db.bio_analytics.items[0]["event_type"] == "nps_rating"
    assert fake_db.bio_analytics.items[0]["score"] == 5
    assert fake_db.bio_analytics.items[0]["feedback"] == "Loved your curated links!"


@pytest.mark.asyncio
async def test_extended_lead_capture_with_phone_and_tag(fake_db):
    """Test lead subscription with extended fields: name, phone, custom tag."""
    bio_page = {
        "_id": ObjectId(),
        "handle": "fitnesspro",
        "user_id": "user_3",
        "workspace_id": "ws_3",
        "blocks": [
            {
                "id": "lead_block_1",
                "type": "lead_capture",
                "lead_tag": "vip",
            }
        ],
    }
    fake_db.bio_pages.items.append(bio_page)

    sub_payload = BioLeadSubscribeRequest(
        email="client@example.com",
        name="Alex Mercer",
        phone="+1 555-0199",
        tag="vip",
        source_block_id="lead_block_1",
    )

    res = await subscribe_to_bio_newsletter("fitnesspro", sub_payload, db=fake_db)

    assert res["success"] is True
    assert len(fake_db.workspace_leads.items) == 1
    lead = fake_db.workspace_leads.items[0]
    assert lead["email"] == "client@example.com"
    assert lead["name"] == "Alex Mercer"
    assert lead["phone"] == "+1 555-0199"
    assert lead["tag"] == "vip"


@pytest.mark.asyncio
async def test_bio_analytics_funnel_and_heatmap(fake_db, fake_user):
    """Test funnel calculation, heatmap density tiers, and NPS aggregates in get_bio_analytics."""
    bio_page = {
        "_id": ObjectId(),
        "handle": "datahero",
        "user_id": fake_user["id"],
        "workspace_id": fake_user["current_workspace_id"],
        "total_views": 200,
        "total_clicks": 100,
        "blocks": [
            {"id": "b1", "title": "Free Ebook", "click_count": 80},
            {"id": "b2", "title": "Portfolio", "click_count": 20},
        ],
    }
    fake_db.bio_pages.items.append(bio_page)

    # Add 100 bio events: 200 views, 100 clicks
    for _ in range(200):
        fake_db.bio_events.items.append({"workspace_id": fake_user["current_workspace_id"], "event_type": "view"})
    for _ in range(100):
        fake_db.bio_events.items.append({"workspace_id": fake_user["current_workspace_id"], "event_type": "click"})

    # Add 10 leads
    for i in range(10):
        fake_db.workspace_leads.items.append({
            "workspace_id": fake_user["current_workspace_id"],
            "email": f"lead{i}@test.com",
            "tag": "subscriber",
        })

    # Add 2 feedback responses in bio_analytics: 5 stars and 4 stars
    fake_db.bio_analytics.items.append({"workspace_id": fake_user["current_workspace_id"], "event_type": "nps_rating", "score": 5})
    fake_db.bio_analytics.items.append({"workspace_id": fake_user["current_workspace_id"], "event_type": "nps_rating", "score": 4})

    analytics = await get_bio_analytics(current_user=fake_user, db=fake_db)

    # Check Funnel
    assert "funnel_steps" in analytics
    assert len(analytics["funnel_steps"]) == 3
    assert analytics["funnel_steps"][0]["step"] == "Total Views"
    assert analytics["funnel_steps"][1]["step"] == "Block Clicks"
    assert analytics["funnel_steps"][2]["step"] == "Conversions"

    # Check Heatmap
    assert "heatmap_blocks" in analytics
    assert len(analytics["heatmap_blocks"]) == 2
    b1_heatmap = next(b for b in analytics["heatmap_blocks"] if b["id"] == "b1")
    assert b1_heatmap["heat_tier"] == "hot"
    assert b1_heatmap["click_share"] == 80.0

    # Check NPS
    assert "nps_stats" in analytics
    assert analytics["nps_stats"]["total_responses"] == 2
    assert analytics["nps_stats"]["average_score"] == 4.5


@pytest.mark.asyncio
async def test_ab_testing_variant_management(fake_db, fake_user):
    """Test creating, toggling, and deleting A/B test variants."""
    bio_page = {
        "_id": ObjectId(),
        "handle": "splitcreator",
        "user_id": fake_user["id"],
        "workspace_id": fake_user["current_workspace_id"],
        "variants": [],
        "ab_testing_enabled": False,
    }
    fake_db.bio_pages.items.append(bio_page)

    # 1. Create Variant
    variant_data = BioVariant(
        id="var_dark_mode",
        name="Dark Minimalist Variant",
        traffic_pct=50,
        is_active=True,
    )
    save_res = await save_bio_variant(variant_data, current_user=fake_user, db=fake_db)
    assert save_res["ok"] is True
    assert save_res["variant"]["id"] == "var_dark_mode"

    # 2. Toggle Variant
    toggle_res = await toggle_bio_variant("var_dark_mode", current_user=fake_user, db=fake_db)
    assert toggle_res["ok"] is True
    assert toggle_res["variant"]["is_active"] is False

    # 3. Delete Variant
    del_res = await delete_bio_variant("var_dark_mode", current_user=fake_user, db=fake_db)
    assert del_res["ok"] is True
    assert len(fake_db.bio_pages.items[0]["variants"]) == 0
