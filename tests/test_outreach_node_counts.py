"""
Tests for Phase 4: Sequence Canvas Lead Counters endpoint.
GET /api/v1/outreach/campaigns/{campaign_id}/node-counts
"""
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock
from outreach.api.campaigns import get_campaign_node_counts


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def _matches(self, item, query):
        if not query:
            return True
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(item, sub) for sub in value):
                    return False
            elif key == "$ne":
                pass
            elif isinstance(value, dict):
                if "$ne" in value:
                    if item.get(key) == value["$ne"]:
                        return False
                if "$in" in value:
                    if item.get(key) not in value["$in"]:
                        return False
            elif item.get(key) != value:
                return False
        return True

    def find(self, query=None, *args, **kwargs):
        return MockCursor(dict(item) for item in self.items if self._matches(item, query))

    async def find_one(self, query=None, *args, **kwargs):
        cursor = self.find(query)
        items = await cursor.to_list(1)
        return dict(items[0]) if items else None

    async def count_documents(self, query=None):
        cursor = self.find(query)
        items = await cursor.to_list()
        return len(items)

    def aggregate(self, pipeline):
        current_items = list(self.items)
        for stage in pipeline:
            if "$match" in stage:
                match_q = stage["$match"]
                current_items = [it for it in current_items if self._matches(it, match_q)]
            elif "$group" in stage:
                grp = stage["$group"]
                group_key_field = grp.get("_id", "").replace("$", "")
                groups = {}
                for it in current_items:
                    k = it.get(group_key_field)
                    if k is not None:
                        groups[k] = groups.get(k, 0) + 1
                current_items = [{"_id": k, "count": cnt} for k, cnt in groups.items()]
        return MockCursor(current_items)


class MockDB:
    def __init__(self):
        self.outreach_campaigns = MockCollection()
        self.outreach_leads = MockCollection()


@pytest.fixture
def current_user():
    return {
        "user_id": "usr-1",
        "default_workspace_id": "ws-1",
    }


@pytest.mark.asyncio
async def test_get_campaign_node_counts_distribution(current_user):
    db = MockDB()
    db.outreach_campaigns.items.append({
        "id": "camp-123",
        "workspace_id": "ws-1",
        "user_id": "usr-1",
        "name": "Q4 Outbound",
        "status": "active",
        "is_deleted": False,
    })

    # Add 34 leads in_progress at node-invite
    for i in range(34):
        db.outreach_leads.items.append({
            "id": f"lead-inv-{i}",
            "campaign_id": "camp-123",
            "workspace_id": "ws-1",
            "execution_state": "in_progress",
            "current_node_id": "node-invite",
        })

    # Add 15 leads in_progress at node-msg-1
    for i in range(15):
        db.outreach_leads.items.append({
            "id": f"lead-msg1-{i}",
            "campaign_id": "camp-123",
            "workspace_id": "ws-1",
            "execution_state": "in_progress",
            "current_node_id": "node-msg-1",
        })

    # Add 4 leads in_progress at node-msg-2
    for i in range(4):
        db.outreach_leads.items.append({
            "id": f"lead-msg2-{i}",
            "campaign_id": "camp-123",
            "workspace_id": "ws-1",
            "execution_state": "in_progress",
            "current_node_id": "node-msg-2",
        })

    # Add 100 queued leads (e.g. waiting for root node)
    for i in range(100):
        db.outreach_leads.items.append({
            "id": f"lead-q-{i}",
            "campaign_id": "camp-123",
            "workspace_id": "ws-1",
            "execution_state": "queued",
            "current_node_id": "node-invite",
        })

    # Add 20 completed leads
    for i in range(20):
        db.outreach_leads.items.append({
            "id": f"lead-c-{i}",
            "campaign_id": "camp-123",
            "workspace_id": "ws-1",
            "execution_state": "completed",
            "current_node_id": None,
        })

    res = await get_campaign_node_counts(
        campaign_id="camp-123",
        current_user=current_user,
        db=db,
    )

    assert res["campaign_id"] == "camp-123"
    assert res["node_counts"]["node-invite"] == 34
    assert res["node_counts"]["node-msg-1"] == 15
    assert res["node_counts"]["node-msg-2"] == 4

    # waiting_node_counts includes queued leads for root node
    assert res["waiting_node_counts"]["node-invite"] == 134
    assert res["waiting_node_counts"]["node-msg-1"] == 15

    # Execution state breakdown
    assert res["execution_state_counts"]["in_progress"] == 53
    assert res["execution_state_counts"]["queued"] == 100
    assert res["execution_state_counts"]["completed"] == 20
    assert res["total_leads"] == 173


@pytest.mark.asyncio
async def test_get_campaign_node_counts_empty_campaign(current_user):
    db = MockDB()
    db.outreach_campaigns.items.append({
        "id": "camp-empty",
        "workspace_id": "ws-1",
        "user_id": "usr-1",
        "name": "Empty Draft",
        "status": "draft",
        "is_deleted": False,
    })

    res = await get_campaign_node_counts(
        campaign_id="camp-empty",
        current_user=current_user,
        db=db,
    )

    assert res["campaign_id"] == "camp-empty"
    assert res["node_counts"] == {}
    assert res["waiting_node_counts"] == {}
    assert res["execution_state_counts"] == {}
    assert res["total_leads"] == 0


@pytest.mark.asyncio
async def test_get_campaign_node_counts_not_found(current_user):
    db = MockDB()
    with pytest.raises(HTTPException) as exc_info:
        await get_campaign_node_counts(
            campaign_id="non-existent",
            current_user=current_user,
            db=db,
        )
    assert exc_info.value.status_code == 404
