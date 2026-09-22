"""
Unit tests for Outreach Campaigns Auto-Drafting, Forensic Detail, and Reversible Deletion.
"""
import pytest
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
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if isinstance(v, dict):
                    if "$ne" in v:
                        if item.get(k) == v["$ne"]:
                            match = False
                            break
                    if "$in" in v:
                        if item.get(k) not in v["$in"]:
                            match = False
                            break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))
        return MockCursor(matched)

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
        for item in self.items:
            match = all(item.get(k) == v for k, v in query.items())
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return True
        return False


class MockDB:
    def __init__(self):
        self.outreach_campaigns = MockCollection()
        self.outreach_leads = MockCollection()
        self.outreach_accounts = MockCollection()
        self.outreach_sequences = MockCollection()


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
async def test_get_campaign_detail_with_metrics_and_senders():
    """Verify get_campaign calculates leads and retrieves senders and sequence."""
    db = MockDB()
    user = {"user_id": "usr_test_2", "default_workspace_id": "ws_2"}

    # Seed an account
    acc_doc = {
        "id": "acc_sender_1",
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
        "campaign_id": "camp_det_1",
        "execution_state": "invited",
    })
    await db.outreach_leads.insert_one({
        "id": "lead_2",
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

    # Check initially listed
    initial_list = await list_campaigns(current_user=user, db=db)
    assert len(initial_list) == 1

    # Soft delete
    del_res = await delete_campaign(campaign_id="camp_del_1", current_user=user, db=db)
    assert del_res["status"] == "deleted"

    # Listed should be empty now
    after_del_list = await list_campaigns(current_user=user, db=db)
    assert len(after_del_list) == 0

    # Restore (Undo)
    restore_res = await restore_campaign(campaign_id="camp_del_1", current_user=user, db=db)
    assert restore_res["status"] == "restored"

    # Listed should have campaign back
    restored_list = await list_campaigns(current_user=user, db=db)
    assert len(restored_list) == 1
    assert restored_list[0]["name"] == "Profile warm-up"
