"""
Unit tests for Outreach Campaigns Auto-Drafting, Forensic Detail, and Reversible Deletion.
"""
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock
from outreach.models import (
    CampaignStatus,
    DailyLimits,
    OutreachCampaign,
    WorkingSchedule,
)
from outreach.api.campaigns import (
    AutoDraftRequest,
    auto_draft_campaign,
    get_campaign,
    delete_campaign,
    restore_campaign,
    list_campaigns,
    duplicate_campaign,
)


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query=None, *args, **kwargs):
        return MockCursor(dict(item) for item in self.items if self._matches(item, query))

    async def find_one(self, query=None, *args, **kwargs):
        cursor = self.find(query)
        items = await cursor.to_list(1)
        return dict(items[0]) if items else None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return True

    async def count_documents(self, query=None):
        cursor = self.find(query)
        items = await cursor.to_list()
        return len(items)

    async def update_one(self, query, update):
        matched_ids = {id(item) for item in self.items if self._matches(item, query)}
        for item in self.items:
            if id(item) in matched_ids:
                if "$set" in update:
                    item.update(update["$set"])
                return True
        return False

    @staticmethod
    def _matches(item, query):
        for key, value in (query or {}).items():
            if key == "$or":
                if not any(MockCollection._matches(item, branch) for branch in value):
                    return False
                continue
            if isinstance(value, dict):
                if "$ne" in value and item.get(key) == value["$ne"]:
                    return False
                if "$in" in value and item.get(key) not in value["$in"]:
                    return False
            elif item.get(key) != value:
                return False
        return True

    def aggregate(self, pipeline):
        match = pipeline[0]["$match"]
        grouped = {}
        for item in self.items:
            if not self._matches(item, match):
                continue
            campaign_id = item.get("campaign_id")
            counts = grouped.setdefault(campaign_id, {"_id": campaign_id, "leads_count": 0, "leads_contacted": 0, "acceptances_count": 0, "replies_count": 0})
            counts["leads_count"] += 1
            counts["leads_contacted"] += int(item.get("execution_state") in {"invited", "connected", "messaged", "completed", "accepted", "replied"} or bool(item.get("last_action_at")))
            counts["acceptances_count"] += int(item.get("execution_state") in {"connected", "accepted"} or bool(item.get("is_connected")))
            counts["replies_count"] += int(item.get("execution_state") == "replied" or bool(item.get("has_replied")))
        return MockCursor(grouped.values())

    async def update_many(self, query, update):
        count = 0
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    or_matched = False
                    for subq in v:
                        if all(item.get(sk) == sv for sk, sv in subq.items()):
                            or_matched = True
                            break
                    if not or_matched:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$in" in v and item.get(k) not in v["$in"]:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                if "$unset" in update:
                    for un_k in update["$unset"]:
                        item.pop(un_k, None)
                count += 1
        return count


class MockDB:
    def __init__(self):
        self.outreach_campaigns = MockCollection()
        self.outreach_leads = MockCollection()
        self.outreach_accounts = MockCollection()
        self.outreach_sequences = MockCollection()
        self.outreach_tasks = MockCollection()


@pytest.mark.asyncio
async def test_auto_draft_campaign_creation_and_update():
    """Verify auto_draft_campaign creates a draft and later updates it seamlessly."""
    db = MockDB()
    user = {"user_id": "usr_test_1", "default_workspace_id": "ws_1"}

    # 1. Create a draft campaign
    req1 = AutoDraftRequest(
        name="test1",
        draft_step=2,
        draft_progress=40,
        next_step_label="Next: add your leads",
    )
    draft1 = await auto_draft_campaign(req=req1, current_user=user, db=db)
    assert draft1["id"] is not None
    assert draft1["name"] == "test1"
    assert draft1["status"] == CampaignStatus.DRAFT
    assert draft1["draft_progress"] == 40
    assert draft1["draft_step"] == 2
    assert draft1["next_step_label"] == "Next: add your leads"

    campaign_id = draft1["id"]

    # 2. Update the same draft campaign
    req2 = AutoDraftRequest(
        campaign_id=campaign_id,
        name="test1-updated",
        draft_step=3,
        draft_progress=80,
        next_step_label="Next: review and launch",
    )
    draft2 = await auto_draft_campaign(req=req2, current_user=user, db=db)
    assert draft2["id"] == campaign_id
    assert draft2["name"] == "test1-updated"
    assert draft2["draft_progress"] == 80
    assert draft2["draft_step"] == 3


@pytest.mark.asyncio
async def test_unnamed_first_draft_gets_a_user_facing_name():
    db = MockDB()
    user = {"user_id": "usr_test_1", "default_workspace_id": "ws_1"}
    draft = await auto_draft_campaign(req=AutoDraftRequest(name=None), current_user=user, db=db)
    assert draft["name"] == "Campaign 1"


@pytest.mark.asyncio
async def test_get_campaign_detail_with_metrics_and_senders():
    """Verify get_campaign calculates leads and retrieves senders and sequence."""
    db = MockDB()
    user = {"user_id": "usr_test_2", "default_workspace_id": "ws_2"}

    # Seed an account
    acc_doc = {
        "id": "acc_sender_1",
        "workspace_id": "ws_2",
        "account_name": "Jack Growth",
        "vanity_name": "jackgrowth",
        "avatar_url": "https://example.com/avatar.jpg",
    }
    await db.outreach_accounts.insert_one(acc_doc)

    # Seed a campaign
    camp_doc = {
        "id": "camp_det_1",
        "user_id": "usr_test_2",
        "workspace_id": "ws_2",
        "name": "Outreach Alpha",
        "status": CampaignStatus.DRAFT,
        "sender_account_ids": ["acc_sender_1"],
        "is_deleted": False,
    }
    await db.outreach_campaigns.insert_one(camp_doc)

    # Seed leads
    await db.outreach_leads.insert_one({
        "id": "lead_1",
        "workspace_id": "ws_2",
        "campaign_id": "camp_det_1",
        "execution_state": "invited",
    })
    await db.outreach_leads.insert_one({
        "id": "lead_2",
        "workspace_id": "ws_2",
        "campaign_id": "camp_det_1",
        "execution_state": "queued",
    })

    detail = await get_campaign(campaign_id="camp_det_1", current_user=user, db=db)
    assert detail["id"] == "camp_det_1"
    assert detail["leads_count"] == 2
    assert detail["leads_contacted"] == 1
    assert len(detail["senders"]) == 1
    assert detail["senders"][0]["account_name"] == "Jack Growth"


@pytest.mark.asyncio
async def test_soft_delete_and_restore_campaign():
    """Verify delete_campaign soft-deletes and restore_campaign brings it back."""
    db = MockDB()
    user = {"user_id": "usr_test_3", "default_workspace_id": "ws_3"}

    camp_doc = {
        "id": "camp_del_1",
        "user_id": "usr_test_3",
        "workspace_id": "ws_3",
        "name": "Profile warm-up",
        "status": CampaignStatus.DRAFT,
        "is_deleted": False,
    }
    await db.outreach_campaigns.insert_one(camp_doc)

    task_doc = {
        "id": "task_1",
        "workspace_id": "ws_3",
        "campaign_id": "camp_del_1",
        "status": "queued",
    }
    await db.outreach_tasks.insert_one(task_doc)

    lead_doc = {
        "id": "lead_1",
        "workspace_id": "ws_3",
        "campaign_id": "camp_del_1",
        "user_id": "usr_test_3",
        "pipeline_stage": "enrolled",
    }
    await db.outreach_leads.insert_one(lead_doc)

    # Check initially listed
    initial_list = await list_campaigns(current_user=user, db=db)
    assert len(initial_list) == 1

    # Soft delete (triggers cascade cancellation of tasks and unenrolls leads)
    del_res = await delete_campaign(campaign_id="camp_del_1", current_user=user, db=db)
    assert del_res["status"] == "deleted"

    # Listed should be empty now
    after_del_list = await list_campaigns(current_user=user, db=db)
    assert len(after_del_list) == 0

    # Task should be cancelled
    t = await db.outreach_tasks.find_one({"id": "task_1"})
    assert t["status"] == "cancelled"

    # Lead should be unassigned
    ld = await db.outreach_leads.find_one({"id": "lead_1"})
    assert ld["pipeline_stage"] == "unassigned"
    assert ld["campaign_id"] is None

    # Restore (Undo)
    restore_res = await restore_campaign(campaign_id="camp_del_1", current_user=user, db=db)
    assert restore_res["status"] == "restored"

    # Listed should have campaign back
    restored_list = await list_campaigns(current_user=user, db=db)
    assert len(restored_list) == 1
    assert restored_list[0]["name"] == "Profile warm-up"

    # Task should be restored to queued
    t_restored = await db.outreach_tasks.find_one({"id": "task_1"})
    assert t_restored["status"] == "queued"

    # Lead should be re-enrolled
    ld_restored = await db.outreach_leads.find_one({"id": "lead_1"})
    assert ld_restored["pipeline_stage"] == "enrolled"
    assert ld_restored["campaign_id"] == "camp_del_1"


@pytest.mark.asyncio
async def test_restoring_deleted_warmup_never_reauthorizes_auto_launch():
    db = MockDB()
    user = {"user_id": "owner", "default_workspace_id": "workspace_1"}
    await db.outreach_campaigns.insert_one({
        "id": "armed_1", "user_id": "owner", "workspace_id": "workspace_1",
        "name": "Armed campaign", "status": "warming_up", "auto_launch_enabled": True,
        "is_deleted": False,
    })
    await delete_campaign("armed_1", current_user=user, db=db)
    await restore_campaign("armed_1", current_user=user, db=db)
    restored = await db.outreach_campaigns.find_one({"id": "armed_1"})
    assert restored["status"] == "paused"
    assert restored["auto_launch_enabled"] is False


@pytest.mark.asyncio
async def test_duplicate_campaign():
    user = {"user_id": "usr_dup_test", "default_workspace_id": "ws_1"}
    original_campaign = {
        "id": "camp_source_1",
        "user_id": "usr_dup_test",
        "workspace_id": "ws_1",
        "name": "Q4 Enterprise Founders",
        "status": "active",
        "sender_account_ids": ["acc_1", "acc_2"],
        "schedule": {"timezone": "America/New_York", "days": []},
        "limits": {"connection_invites": 25, "messages": 30},
        "leads_count": 50,
        "leads_contacted": 30,
        "acceptances_count": 15,
        "replies_count": 8,
        "interested_count": 3,
        "is_deleted": False,
    }
    original_sequence = {
        "campaign_id": "camp_source_1",
        "workspace_id": "ws_1",
        "nodes": [{"id": "n1", "type": "connection_request"}],
        "edges": [],
        "tree": [{"id": "n1"}],
        "compiled_dag": {"root_node_ids": ["n1"]},
    }
    db = MockDB()
    db.outreach_campaigns = MockCollection([original_campaign])
    db.outreach_sequences = MockCollection([original_sequence])

    duplicated = await duplicate_campaign(campaign_id="camp_source_1", current_user=user, db=db)

    assert duplicated["id"] != "camp_source_1"
    assert duplicated["name"] == "Q4 Enterprise Founders (Copy)"
    assert duplicated["status"] == "draft"
    assert duplicated["draft_step"] == 1
    assert duplicated["sender_account_ids"] == ["acc_1", "acc_2"]
    assert duplicated["limits"]["connection_invites"] == 25
    assert duplicated["leads_count"] == 0
    assert duplicated["leads_contacted"] == 0
    assert duplicated["acceptances_count"] == 0

    # Ensure sequence was also duplicated
    cloned_seq = await db.outreach_sequences.find_one({"campaign_id": duplicated["id"]})
    assert cloned_seq is not None
    assert len(cloned_seq["nodes"]) == 1
    assert cloned_seq["nodes"][0]["type"] == "connection_request"


@pytest.mark.asyncio
async def test_campaign_cascades_are_workspace_scoped():
    from unittest.mock import MagicMock

    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_a", "name": "Campaign A", "workspace_id": "ws_a", "status": "draft",
    })
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_tasks.update_many = AsyncMock()
    db.outreach_leads.update_many = AsyncMock()
    db.outreach_sequences.update_one = AsyncMock()
    user = {"user_id": "user_a", "default_workspace_id": "ws_a"}
    await delete_campaign("camp_a", current_user=user, db=db)
    assert db.outreach_tasks.update_many.call_args.args[0]["workspace_id"] == "ws_a"
    assert db.outreach_leads.update_many.call_args.args[0]["workspace_id"] == "ws_a"
    assert db.outreach_sequences.update_one.call_args.args[0]["workspace_id"] == "ws_a"


@pytest.mark.asyncio
async def test_auto_draft_rejects_unknown_custom_id():
    user = {"user_id": "usr_draft_test", "default_workspace_id": "ws_1"}
    db = MockDB()
    custom_id = "camp_custom_fallback_123"

    req = AutoDraftRequest(
        campaign_id=custom_id,
        name="Fallback Draft",
        draft_step=1,
    )
    with pytest.raises(HTTPException) as exc:
        await auto_draft_campaign(req=req, current_user=user, db=db)
    assert exc.value.status_code == 404
