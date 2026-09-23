"""
End-to-End Regression Test Suite for LinkedIn Outbound Automation.
Covers:
- Winning sequence templates compilation and parity.
- Custom templates lifecycle (save, list, delete).
- Auto-drafting, sequence compilation, and persistence.
- Lead ingestion, initialization, and campaign launch pooling.
- Execution engine state progression.
- Unified Inbox synchronization, intent classification, and campaign KPI updates.
"""
import os
from datetime import datetime, timezone
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock, patch

from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.models import SequenceNodeType, LeadExecutionState
from outreach.api.sequences import (
    get_sequence_templates,
    save_custom_template,
    delete_custom_template,
    get_campaign_sequence,
    save_campaign_sequence,
    SaveTemplateRequest,
    SaveSequenceRequest,
)
from outreach.api.campaigns import (
    launch_campaign,
    auto_draft_campaign,
    AutoDraftRequest,
    LaunchCampaignRequest,
)
from outreach.engine.inbox_sync import InboxSynchronizer


def test_winning_templates_dag_compilation():
    """Verify all 4 winning prebuilt templates compile into valid DAG graphs."""
    templates = DAGCompiler.get_prebuilt_templates()
    assert len(templates) >= 4

    names = [t["name"] for t in templates]
    assert "Connect and follow up" in names
    assert "Profile warm-up" in names
    assert "Voice note outreach" in names
    assert "Multi-touch InMail & engage" in names

    for tpl in templates:
        assert "nodes" in tpl and len(tpl["nodes"]) > 0
        assert "tree" in tpl and len(tpl["tree"]) > 0
        compiled = DAGCompiler.validate_and_compile(tpl["nodes"], tpl["edges"])
        assert len(compiled["root_node_ids"]) >= 1
        for root_id in compiled["root_node_ids"]:
            assert root_id in compiled["nodes"]


@pytest.mark.asyncio
async def test_custom_templates_lifecycle():
    """Verify saving, listing, and deleting custom outreach templates."""
    mock_db = AsyncMock()
    saved_templates = []

    async def mock_insert_one(doc):
        saved_templates.append(doc)
        return AsyncMock(inserted_id="mock_id")

    mock_db.outreach_templates.insert_one = mock_insert_one

    def mock_find(query):
        cursor = AsyncMock()
        cursor.sort = lambda field, dir: cursor
        cursor.to_list = AsyncMock(return_value=[dict(t) for t in saved_templates])
        return cursor

    mock_db.outreach_templates.find = mock_find

    async def mock_delete_one(query):
        nonlocal saved_templates
        before = len(saved_templates)
        saved_templates = [t for t in saved_templates if t["id"] != query.get("id")]
        res = AsyncMock()
        res.deleted_count = 1 if len(saved_templates) < before else 0
        return res

    mock_db.outreach_templates.delete_one = mock_delete_one

    user = {"user_id": "test_user_regression", "workspace_id": "ws_regression"}

    # 1. List templates (initially only prebuilt)
    initial_tpls = await get_sequence_templates(current_user=user, db=mock_db)
    assert len(initial_tpls) == 4

    # 2. Save a custom template
    save_req = SaveTemplateRequest(
        name="Custom Founder Outreach",
        description="Personalized 3-touch sequence for series A founders",
        nodes=[
            {"id": "n1", "type": SequenceNodeType.VISIT_PROFILE, "title": "Visit", "delay_hours": 0},
            {"id": "n2", "type": SequenceNodeType.CONNECTION_REQUEST, "title": "Invite", "delay_hours": 0},
        ],
        edges=[{"id": "e1", "source": "n1", "target": "n2"}],
        tree=[{"id": "n1", "type": "visit_profile", "delay_days": 0}],
    )
    save_res = await save_custom_template(req=save_req, current_user=user, db=mock_db)
    assert save_res["status"] == "success"
    tpl_id = save_res["template"]["id"]
    assert tpl_id.startswith("tpl_custom_")

    # 3. List templates again (should now have 4 prebuilt + 1 custom)
    updated_tpls = await get_sequence_templates(current_user=user, db=mock_db)
    assert len(updated_tpls) == 5
    custom_entry = next((t for t in updated_tpls if t["id"] == tpl_id), None)
    assert custom_entry is not None
    assert custom_entry["name"] == "Custom Founder Outreach"
    assert custom_entry["is_custom"] is True

    # 4. Delete the custom template
    del_res = await delete_custom_template(template_id=tpl_id, current_user=user, db=mock_db)
    assert del_res["status"] == "success"

    # 5. List templates after deletion (should be back to 4)
    after_del_tpls = await get_sequence_templates(current_user=user, db=mock_db)
    assert len(after_del_tpls) == 4


@pytest.mark.asyncio
async def test_campaign_autodraft_and_sequence_flow():
    """Verify auto-drafting from template and persisting sequence with tree."""
    mock_db = AsyncMock()
    campaigns_store = {}
    sequences_store = {}

    async def mock_camp_update(query, update, upsert=False):
        camp_id = query["id"]
        if camp_id not in campaigns_store:
            campaigns_store[camp_id] = {"id": camp_id}
        if "$set" in update:
            campaigns_store[camp_id].update(update["$set"])
        return AsyncMock(upserted_id=camp_id)

    async def mock_find_camp(q):
        return campaigns_store.get(q.get("id"))
    mock_db.outreach_campaigns.find_one = mock_find_camp

    async def mock_seq_update(query, update, upsert=False):
        c_id = query["campaign_id"]
        if "$set" in update:
            sequences_store[c_id] = dict(update["$set"])
        return AsyncMock()

    mock_db.outreach_sequences.update_one = mock_seq_update

    async def mock_find_seq(q):
        return sequences_store.get(q.get("campaign_id"))
    mock_db.outreach_sequences.find_one = mock_find_seq

    user = {"user_id": "test_user_reg", "workspace_id": "ws_reg"}

    # 1. Auto-draft campaign
    draft_req = AutoDraftRequest(
        name="Connect and follow up",
        draft_step=2,
        draft_progress=60,
    )
    draft_res = await auto_draft_campaign(req=draft_req, current_user=user, db=mock_db)
    campaign_id = draft_res["id"]
    assert isinstance(campaign_id, str) and len(campaign_id) > 0

    # 2. Save sequence with nodes, edges, and tree
    prebuilts = DAGCompiler.get_prebuilt_templates()
    conn_tpl = prebuilts[0]  # Connect and follow up
    seq_req = SaveSequenceRequest(
        campaign_id=campaign_id,
        nodes=conn_tpl["nodes"],
        edges=conn_tpl["edges"],
        tree=conn_tpl["tree"],
    )
    save_seq_res = await save_campaign_sequence(req=seq_req, current_user=user, db=mock_db)
    assert save_seq_res["status"] == "success"

    # 3. Retrieve sequence
    fetched_seq = await get_campaign_sequence(campaign_id, current_user=user, db=mock_db)
    assert fetched_seq["campaign_id"] == campaign_id
    assert len(fetched_seq["nodes"]) == 2
    assert "tree" in fetched_seq
    assert fetched_seq["tree"][0]["type"] == "connection_request"


@pytest.mark.asyncio
async def test_campaign_launch_and_lead_queueing():
    """Verify launching a campaign sets status to active, DAG compiled, and leads queued."""
    mock_db = AsyncMock()
    camp_doc = {
        "id": "camp_test_launch",
        "workspace_id": "ws_launch",
        "user_id": "u_launch",
        "name": "Q3 Enterprise Warmup",
        "status": "draft",
        "sender_account_ids": ["acc_sender_1"],
    }
    mock_db.outreach_campaigns.find_one = AsyncMock(return_value=camp_doc)
    mock_db.outreach_campaigns.update_one = AsyncMock()

    # Prebuilt sequence exists
    prebuilts = DAGCompiler.get_prebuilt_templates()
    seq_doc = {
        "campaign_id": "camp_test_launch",
        "nodes": prebuilts[0]["nodes"],
        "edges": prebuilts[0]["edges"],
        "tree": prebuilts[0]["tree"],
    }
    mock_db.outreach_sequences.find_one = AsyncMock(return_value=seq_doc)
    mock_db.outreach_sequences.update_one = AsyncMock()

    # Unassigned leads to be pooled and queued
    leads_list = [{"id": f"lead_{i}", "current_node_id": None} for i in range(5)]
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=leads_list)
    mock_db.outreach_leads.find = lambda q: mock_cursor

    lead_updates = []
    async def mock_lead_update_one(filter_q, update_q):
        lead_updates.append((filter_q, update_q))
        return AsyncMock()
    mock_db.outreach_leads.update_one = mock_lead_update_one

    user = {"user_id": "u_launch", "workspace_id": "ws_launch"}
    launch_req = LaunchCampaignRequest(
        sender_account_ids=["acc_sender_1"],
        daily_limits={"connection_invites": 25},
    )

    result = await launch_campaign("camp_test_launch", req=launch_req, current_user=user, db=mock_db)
    assert result["status"] in ("launched", "success")
    assert result["campaign_id"] == "camp_test_launch"
    assert result["allocated_leads_count"] == 5

    # Verify update_one was called with root node
    assert len(lead_updates) == 5
    filter_q, update_q = lead_updates[0]
    assert filter_q["id"] == "lead_0"
    assert update_q["$set"]["current_node_id"] == "step_connect_root"
    assert update_q["$set"]["execution_state"] == LeadExecutionState.QUEUED


@pytest.mark.asyncio
async def test_inbox_synchronization_and_campaign_kpi_impact():
    """Verify InboxSynchronizer sets lead has_replied=True and increments campaign reply metrics."""
    mock_db = AsyncMock()

    account = {
        "id": "acc_sync_1",
        "workspace_id": "ws_sync",
        "user_id": "u_sync",
        "session_cookie_enc": Fernet(os.environ["ENCRYPTION_KEY"].encode()).encrypt(b"mock_cookie").decode(),
        "jsession_id": "ajax:12345",
        "proxy_config": {"host": "1.2.3.4", "port": 8080},
    }
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=account)

    # Lead document in CRM
    lead_doc = {
        "id": "lead_alex",
        "workspace_id": "ws_sync",
        "first_name": "Alex",
        "last_name": "Rivers",
        "linkedin_url": "https://linkedin.com/in/alexrivers",
        "campaign_id": "camp_e2e_target",
        "has_replied": False,
    }
    mock_db.outreach_leads.find_one = AsyncMock(return_value=lead_doc)

    lead_updates = []
    async def mock_lead_update_many(q, u):
        lead_updates.append((q, u))
        res = AsyncMock()
        res.modified_count = 1
        return res
    mock_db.outreach_leads.update_many = mock_lead_update_many

    mock_db.outreach_threads.update_one = AsyncMock()

    campaign_kpi_increments = []
    async def mock_camp_update(q, u):
        campaign_kpi_increments.append((q, u))
        return AsyncMock()
    mock_db.outreach_campaigns.update_one = mock_camp_update

    # Mock Voyager client conversations
    mock_conversations = [
        {
            "thread_urn": "urn:li:fs_conversation:998877",
            "lead_name": "Alex Rivers",
            "lead_headline": "VP of Growth @ Acme",
            "messages": [
                {
                    "sender_type": "lead",
                    "sender_name": "Alex Rivers",
                    "text": "Sounds very interesting! Let us set up a demo next Tuesday.",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
    ]

    with patch("outreach.engine.inbox_sync.VoyagerClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_conversations = AsyncMock(return_value=mock_conversations)

        syncer = InboxSynchronizer(db=mock_db, workspace_id="ws_sync", user_id="u_sync")
        summary = await syncer.sync_account_inbox("acc_sync_1")

        assert summary["synced_threads"] == 1
        assert summary["new_replies_detected"] == 1

        # Verify lead CRM status updated
        assert len(lead_updates) > 0
        _, update_doc = lead_updates[0]
        assert update_doc["$set"]["has_replied"] is True
        assert update_doc["$set"]["execution_state"] in (LeadExecutionState.REPLIED, "replied")

        # Verify campaign KPIs incremented
        assert len(campaign_kpi_increments) > 0
        q, inc_u = campaign_kpi_increments[0]
        assert q["id"] == "camp_e2e_target"
        assert inc_u["$inc"]["replies_count"] == 1
        assert inc_u["$inc"]["interested_count"] == 1
