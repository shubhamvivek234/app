"""
Unit tests for Cluster D (Automation Layer) features:
- Automation Rule CRUD (/automations)
- Preset Recipes catalog (/automations/recipes)
- Dry-run test endpoint (/automations/{id}/test)
- Audit Execution Logs (/automations/logs)
- Dispatch Event Engine: reactive trigger to action handling
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from api.routes.automations import (
    AutomationCreate,
    AutomationUpdate,
    TestAutomationRequest,
    list_automations,
    get_preset_recipes,
    create_automation,
    update_automation,
    delete_automation,
    simulate_automation_test,
    get_automation_logs,
    dispatch_automation_event,
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

    async def find_one_and_update(self, filter_query, update_query, return_document=True):
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
                return dict(it)
        return None

    async def delete_one(self, filter_query):
        for idx, it in enumerate(self.items):
            match = True
            for k, v in filter_query.items():
                if it.get(k) != v:
                    match = False
                    break
            if match:
                self.items.pop(idx)
                mock_result = AsyncMock()
                mock_result.deleted_count = 1
                return mock_result
        mock_result = AsyncMock()
        mock_result.deleted_count = 0
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
        self.automations = FakeCollection()
        self.automation_logs = FakeCollection()
        self.deals = FakeCollection()
        self.workspace_leads = FakeCollection()
        self.users = FakeCollection()


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def fake_user():
    return {
        "_id": ObjectId(),
        "id": "user_d_test",
        "email": "automation_admin@unravler.com",
        "name": "Jordan Bell",
        "current_workspace_id": "ws_cluster_d",
    }


@pytest.mark.asyncio
async def test_automation_crud(fake_db, fake_user):
    """Test creating, listing, updating, and deleting an automation rule."""
    # 1. Create
    rule_data = AutomationCreate(
        name="Welcome New Subscribers",
        description="Send email on new lead",
        trigger_type="lead.created",
        action_type="send_email",
        action_config={"subject": "Welcome!", "body": "Hey {{name}}!"},
    )
    created = await create_automation(rule_data, current_user=fake_user, db=fake_db)
    assert created["ok"] is True
    assert created["automation"]["name"] == "Welcome New Subscribers"
    rule_id = created["automation"]["id"]

    # 2. List
    rules_list = await list_automations(current_user=fake_user, db=fake_db)
    assert len(rules_list["automations"]) == 1
    assert rules_list["automations"][0]["id"] == rule_id

    # 3. Update
    update_data = AutomationUpdate(name="Welcome VIP Subscribers", is_active=False)
    updated = await update_automation(rule_id, update_data, current_user=fake_user, db=fake_db)
    assert updated["ok"] is True
    assert updated["automation"]["name"] == "Welcome VIP Subscribers"
    assert updated["automation"]["is_active"] is False

    # 4. Delete
    del_res = await delete_automation(rule_id, current_user=fake_user, db=fake_db)
    assert del_res["ok"] is True
    assert len(fake_db.automations.items) == 0


@pytest.mark.asyncio
async def test_get_automation_recipes():
    """Test retrieving pre-built recipe catalog."""
    res = await get_preset_recipes()
    assert "recipes" in res
    assert len(res["recipes"]) >= 5
    recipe_ids = [r["id"] for r in res["recipes"]]
    assert "welcome_email_on_lead" in recipe_ids
    assert "lead_to_deal_pipeline" in recipe_ids
    assert "vip_tag_on_5star_rating" in recipe_ids


@pytest.mark.asyncio
async def test_test_automation_dry_run(fake_db, fake_user):
    """Test dry-run simulation of an automation rule."""
    rule_doc = {
        "_id": ObjectId(),
        "workspace_id": fake_user["current_workspace_id"],
        "name": "Test CRM Deal Creation",
        "trigger_type": "lead.created",
        "trigger_config": {},
        "action_type": "create_deal",
        "action_config": {"title": "Test Lead: {{name}}", "stage": "lead", "value": 100},
        "is_active": True,
        "execution_count": 0,
    }
    fake_db.automations.items.append(rule_doc)

    req = TestAutomationRequest(sample_payload={"name": "DryRun User", "email": "dryrun@test.com"})
    res = await simulate_automation_test(str(rule_doc["_id"]), req, current_user=fake_user, db=fake_db)

    assert res["ok"] is True
    assert res["dry_run"] is True
    assert len(fake_db.automation_logs.items) == 1
    log = fake_db.automation_logs.items[0]
    assert log["status"] == "success"
    assert log["is_dry_run"] is True


@pytest.mark.asyncio
async def test_dispatch_automation_event_engine(fake_db):
    """Test asynchronous event dispatch engine executing actions."""
    ws_id = "ws_test_engine"

    # Rule 1: lead.created -> create_deal
    rule_deal = {
        "_id": ObjectId(),
        "workspace_id": ws_id,
        "name": "Auto Deal Creator",
        "trigger_type": "lead.created",
        "trigger_config": {},
        "action_type": "create_deal",
        "action_config": {"title": "Inbound: {{name}}", "stage": "lead", "value": 500.0, "currency": "INR"},
        "is_active": True,
        "execution_count": 0,
    }
    # Rule 2: feedback.received -> tag_lead
    rule_tag = {
        "_id": ObjectId(),
        "workspace_id": ws_id,
        "name": "VIP Promoter Tagger",
        "trigger_type": "feedback.received",
        "trigger_config": {"min_score": 4},
        "action_type": "tag_lead",
        "action_config": {"target_tag": "vip"},
        "is_active": True,
        "execution_count": 0,
    }
    fake_db.automations.items.extend([rule_deal, rule_tag])

    # Insert a lead to be tagged
    fake_db.workspace_leads.items.append({
        "_id": ObjectId(),
        "workspace_id": ws_id,
        "email": "promoter@example.com",
        "tag": "subscriber",
    })

    # Dispatch Event 1: lead.created
    await dispatch_automation_event(
        event_type="lead.created",
        workspace_id=ws_id,
        payload={"name": "Alice Wonderland", "email": "alice@wonder.com"},
        db=fake_db,
    )

    # Verify Deal created in CRM
    assert len(fake_db.deals.items) == 1
    deal = fake_db.deals.items[0]
    assert deal["title"] == "Inbound: Alice Wonderland"
    assert deal["value"] == 500.0

    # Dispatch Event 2: feedback.received with score 5
    await dispatch_automation_event(
        event_type="feedback.received",
        workspace_id=ws_id,
        payload={"score": 5, "email": "promoter@example.com"},
        db=fake_db,
    )

    # Verify Lead promoted to VIP tag
    lead = fake_db.workspace_leads.items[0]
    assert lead["tag"] == "vip"
