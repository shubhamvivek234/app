"""
Unit tests for Cluster A (Audience Hub) features:
- Leads CRM: CRUD, filtering, stats, CSV export, CSV import
- Deals Pipeline: CRUD, stage transitions, stats calculation
- AI Lead Summary: endpoint generates summary using interaction history
- Smart Bio Leads integration & analytics bug fix verification
"""
import io
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from starlette.requests import Request

from api.routes.leads import (
    LeadCreate,
    LeadUpdate,
    create_lead,
    list_leads,
    update_lead,
    delete_lead,
    get_lead_stats,
    export_leads_csv,
    import_leads_csv,
)
from api.routes.deals import (
    DealCreate,
    DealUpdate,
    create_deal,
    list_deals,
    update_deal,
    delete_deal,
    get_deal_stats,
)
from api.routes.ai import (
    LeadSummaryRequest,
    generate_lead_summary,
)
from api.routes.bio_pages import (
    get_bio_analytics,
    get_bio_leads,
    export_bio_leads_csv,
    subscribe_to_bio_newsletter,
    BioLeadSubscribeRequest,
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
                        branch_match = True
                        for bk, bv in branch.items():
                            if isinstance(bv, dict) and "$regex" in bv:
                                pattern = bv["$regex"].lower()
                                if pattern not in str(item.get(bk, "")).lower():
                                    branch_match = False
                                    break
                            elif item.get(bk) != bv:
                                branch_match = False
                                break
                        if branch_match:
                            or_matched = True
                            break
                    if not or_matched:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$ne" in v and item.get(k) == v["$ne"]:
                        match = False
                        break
                    if "$exists" in v and (k in item) != v["$exists"]:
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
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.items.append(d)
        return True

    async def update_one(self, query, update, upsert=False):
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                if "$inc" in update:
                    for ik, iv in update["$inc"].items():
                        item[ik] = item.get(ik, 0) + iv
                return True
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            await self.insert_one(new_doc)
            return True
        return False

    async def delete_one(self, query):
        initial_len = len(self.items)
        new_items = []
        deleted = False
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match and not deleted:
                deleted = True
            else:
                new_items.append(item)
        self.items = new_items
        mock_res = AsyncMock()
        mock_res.deleted_count = initial_len - len(self.items)
        return mock_res

    async def count_documents(self, query=None):
        cursor = self.find(query)
        items = await cursor.to_list(None)
        return len(items)

    def aggregate(self, pipeline):
        # Simple pipeline support for $match and $group
        results = list(self.items)
        for stage in pipeline:
            if "$match" in stage:
                match_q = stage["$match"]
                results = [i for i in results if all(i.get(k) == v for k, v in match_q.items())]
            elif "$group" in stage:
                group_spec = stage["$group"]
                group_field = group_spec["_id"].lstrip("$")
                groups = {}
                for item in results:
                    key = item.get(group_field)
                    if key not in groups:
                        groups[key] = {"_id": key, "count": 0, "total_value": 0}
                    groups[key]["count"] += 1
                    if "total_value" in group_spec:
                        val_field = group_spec["total_value"]["$sum"].lstrip("$")
                        groups[key]["total_value"] += item.get(val_field, 0)
                results = list(groups.values())
        return FakeCursor(results)


class FakeDB:
    def __init__(self):
        self.workspace_leads = FakeCollection()
        self.deals = FakeCollection()
        self.bio_pages = FakeCollection()
        self.bio_analytics = FakeCollection()
        self.inbox_messages = FakeCollection()
        self.posts = FakeCollection()
        self.brand_voices = FakeCollection()
        self.users = FakeCollection()


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def current_user():
    return {
        "user_id": "usr_test123",
        "default_workspace_id": "ws_test_cluster_a",
        "email": "creator@unravler.com",
        "name": "Alex Creator",
    }


# ── 1. Leads CRM Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_leads(fake_db, current_user):
    lead_input = LeadCreate(
        email="client@brand.com",
        name="Sarah Connor",
        phone="+919876543210",
        tag="client",
        notes="High value brand partnership",
        source="manual",
    )
    created = await create_lead(body=lead_input, current_user=current_user, db=fake_db)
    assert created["email"] == "client@brand.com"
    assert created["name"] == "Sarah Connor"
    assert created["tag"] == "client"
    assert created["source"] == "manual"

    # List leads
    listed = await list_leads(current_user=current_user, db=fake_db)
    assert listed["total"] == 1
    assert len(listed["leads"]) == 1
    assert listed["leads"][0]["name"] == "Sarah Connor"


@pytest.mark.asyncio
async def test_lead_tag_filtering_and_search(fake_db, current_user):
    # Seed leads
    for i in range(5):
        await fake_db.workspace_leads.insert_one({
            "workspace_id": "ws_test_cluster_a",
            "email": f"subscriber_{i}@test.com",
            "name": f"Sub {i}",
            "tag": "subscriber",
            "created_at": datetime.now(timezone.utc),
        })
    await fake_db.workspace_leads.insert_one({
        "workspace_id": "ws_test_cluster_a",
        "email": "vip_deal@luxury.com",
        "name": "Victoria VIP",
        "tag": "vip",
        "created_at": datetime.now(timezone.utc),
    })

    # Filter by tag
    vips = await list_leads(current_user=current_user, db=fake_db, tag="vip")
    assert vips["total"] == 1
    assert vips["leads"][0]["name"] == "Victoria VIP"

    # Search by name/email
    search_res = await list_leads(current_user=current_user, db=fake_db, q="luxury")
    assert search_res["total"] == 1
    assert search_res["leads"][0]["email"] == "vip_deal@luxury.com"


@pytest.mark.asyncio
async def test_lead_update_and_delete(fake_db, current_user):
    doc = {
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "email": "lead@growth.com",
        "name": "Tom",
        "tag": "lead",
        "notes": "Initial contact",
        "created_at": datetime.now(timezone.utc),
    }
    await fake_db.workspace_leads.insert_one(doc)
    lead_id = str(doc["_id"])

    # Update tag and notes
    updated = await update_lead(
        lead_id=lead_id,
        body=LeadUpdate(tag="client", notes="Contract signed!"),
        current_user=current_user,
        db=fake_db,
    )
    assert updated["tag"] == "client"
    assert updated["notes"] == "Contract signed!"

    # Delete lead
    res = await delete_lead(lead_id=lead_id, current_user=current_user, db=fake_db)
    assert res["ok"] is True
    assert await fake_db.workspace_leads.count_documents({"workspace_id": "ws_test_cluster_a"}) == 0


@pytest.mark.asyncio
async def test_lead_stats_breakdown(fake_db, current_user):
    for _ in range(3):
        await fake_db.workspace_leads.insert_one({"workspace_id": "ws_test_cluster_a", "tag": "subscriber"})
    for _ in range(2):
        await fake_db.workspace_leads.insert_one({"workspace_id": "ws_test_cluster_a", "tag": "client"})
    await fake_db.workspace_leads.insert_one({"workspace_id": "ws_test_cluster_a", "tag": "vip"})

    stats = await get_lead_stats(current_user=current_user, db=fake_db)
    assert stats["subscriber"] == 3
    assert stats["client"] == 2
    assert stats["vip"] == 1
    assert stats["total"] == 6


@pytest.mark.asyncio
async def test_lead_csv_export(fake_db, current_user):
    await fake_db.workspace_leads.insert_one({
        "workspace_id": "ws_test_cluster_a",
        "email": "export_test@agency.com",
        "name": "John Doe",
        "phone": "+123456789",
        "tag": "lead",
        "source": "bio",
        "notes": "Met at VidCon",
        "created_at": datetime.now(timezone.utc),
    })

    resp = await export_leads_csv(current_user=current_user, db=fake_db)
    csv_text = resp.body.decode("utf-8")
    assert "export_test@agency.com" in csv_text
    assert "John Doe" in csv_text
    assert "Name,Email,Phone,Tag,Source,Notes,Created At" in csv_text


# ── 2. Deals Pipeline Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_deals(fake_db, current_user):
    deal_input = DealCreate(
        title="Nike Summer Reel Collaboration",
        contact_name="Mark Smith",
        contact_email="mark@nike.com",
        value=75000,
        currency="INR",
        stage="lead",
        priority="high",
        notes="Deliverables: 1 Reel + 2 Stories",
        tags=["nike", "fashion", "reel"],
    )
    deal = await create_deal(body=deal_input, current_user=current_user, db=fake_db)
    assert deal["title"] == "Nike Summer Reel Collaboration"
    assert deal["contact_name"] == "Mark Smith"
    assert deal["contact_email"] == "mark@nike.com"
    assert deal["value"] == 75000
    assert deal["stage"] == "lead"
    assert deal["priority"] == "high"

    # List deals
    res = await list_deals(current_user=current_user, db=fake_db)
    assert res["total"] == 1
    assert res["deals"][0]["title"] == "Nike Summer Reel Collaboration"


@pytest.mark.asyncio
async def test_deal_stage_transition_and_stats(fake_db, current_user):
    # Create 2 deals
    d1 = await fake_db.deals.insert_one({
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "title": "Deal One",
        "value": 50000,
        "stage": "lead",
        "currency": "INR",
        "updated_at": datetime.now(timezone.utc),
    })
    deal1_id = str(fake_db.deals.items[0]["_id"])

    # Update stage from lead -> negotiation -> won
    await update_deal(deal_id=deal1_id, body=DealUpdate(stage="negotiation"), current_user=current_user, db=fake_db)
    updated = await fake_db.deals.find_one({"_id": ObjectId(deal1_id)})
    assert updated["stage"] == "negotiation"

    await update_deal(deal_id=deal1_id, body=DealUpdate(stage="won"), current_user=current_user, db=fake_db)
    won = await fake_db.deals.find_one({"_id": ObjectId(deal1_id)})
    assert won["stage"] == "won"

    # Deal stats
    stats = await get_deal_stats(current_user=current_user, db=fake_db)
    assert stats["total_deals"] == 1
    assert stats["total_pipeline_value"] == 50000
    assert stats["won_value"] == 50000


@pytest.mark.asyncio
async def test_delete_deal(fake_db, current_user):
    doc = {
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "title": "Cancelled Deal",
        "stage": "lost",
        "value": 10000,
    }
    await fake_db.deals.insert_one(doc)
    deal_id = str(doc["_id"])

    res = await delete_deal(deal_id=deal_id, current_user=current_user, db=fake_db)
    assert res["ok"] is True
    assert await fake_db.deals.count_documents({"workspace_id": "ws_test_cluster_a"}) == 0


# ── 3. AI Lead Summary Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_lead_summary_generation(fake_db, current_user):
    lead_doc = {
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "email": "partner@creatorbrand.co",
        "name": "Elena Rostova",
        "tag": "vip",
        "notes": "Interested in 6-month agency retainer",
        "source": "bio",
        "created_at": datetime.now(timezone.utc),
    }
    await fake_db.workspace_leads.insert_one(lead_doc)
    lead_id = str(lead_doc["_id"])

    # Add related deal
    await fake_db.deals.insert_one({
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "contact_email": "partner@creatorbrand.co",
        "title": "Annual Retainer",
        "value": 120000,
        "currency": "INR",
        "stage": "proposal",
        "updated_at": datetime.now(timezone.utc),
    })

    # Mock free_llm.generate_text
    with patch("api.routes.ai.free_llm.generate_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (
            "Elena Rostova is a VIP contact actively discussing an Annual Retainer proposal worth ₹120,000. She expressed strong interest in a 6-month retainer and represents a high-priority closing opportunity.",
            "gemini",
            "gemini-2.5-flash",
        )

        req = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/ai/lead-summary",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 1234),
        })
        summary_res = await generate_lead_summary(
            request=req,
            body=LeadSummaryRequest(lead_id=lead_id),
            current_user=current_user,
            db=fake_db,
        )

        assert "Elena Rostova is a VIP contact" in summary_res["summary"]
        assert summary_res["lead_id"] == lead_id
        assert summary_res["provider"] == "gemini"
        mock_llm.assert_called_once()


# ── 4. Smart Bio Leads Analytics Bugfix & Integration Tests ────────────────────

@pytest.mark.asyncio
async def test_bio_analytics_queries_workspace_leads(fake_db, current_user):
    """Verify that get_bio_analytics queries db.workspace_leads rather than db.bio_leads."""
    bio_page_doc = {
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "user_id": "usr_test123",
        "handle": "alextest",
        "total_views": 100,
        "total_clicks": 25,
        "blocks": [],
    }
    await fake_db.bio_pages.insert_one(bio_page_doc)

    # Insert into workspace_leads
    for i in range(4):
        await fake_db.workspace_leads.insert_one({
            "workspace_id": "ws_test_cluster_a",
            "email": f"sub{i}@gmail.com",
            "created_at": datetime.now(timezone.utc),
        })

    analytics = await get_bio_analytics(current_user=current_user, db=fake_db)
    assert analytics["total_leads"] == 4
    assert analytics["views"] == 100
    assert analytics["clicks"] == 25


@pytest.mark.asyncio
async def test_bio_subscribe_inserts_complete_crm_fields(fake_db):
    bio_page_doc = {
        "_id": ObjectId(),
        "workspace_id": "ws_test_cluster_a",
        "handle": "creatorhub",
        "is_published": True,
    }
    await fake_db.bio_pages.insert_one(bio_page_doc)

    # Visitor subscribes from public bio page
    sub_res = await subscribe_to_bio_newsletter(
        handle="creatorhub",
        body=BioLeadSubscribeRequest(email="fan@youtube.com", source_block_id="blk_newsletter"),
        db=fake_db,
    )
    assert sub_res["ok"] is True

    # Check document in workspace_leads has tag='subscriber' and source='bio'
    lead = await fake_db.workspace_leads.find_one({"email": "fan@youtube.com"})
    assert lead is not None
    assert lead["workspace_id"] == "ws_test_cluster_a"
    assert lead["tag"] == "subscriber"
    assert lead["source"] == "bio"
    assert lead["source_block_id"] == "blk_newsletter"
