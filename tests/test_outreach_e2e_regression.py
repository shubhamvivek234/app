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

pytestmark = pytest.mark.usefixtures("outreach_paid_gate_stub")
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
from outreach.core.crypto import encrypt_secret


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
async def test_custom_templates_lifecycle(monkeypatch):
    """Isolate route persistence; actual authority/transactions have native tests."""
    from bson import ObjectId
    from outreach.api.sequences import DeleteTemplateRequest
    from outreach.core.template_governance import deletion_precondition
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

    async def persist_create(db, workspace, actor, doc, **kwargs):
        saved = {**doc, "_id": ObjectId(), "template_revision": 1}
        await db.outreach_templates.insert_one(saved)
        return {key: value for key, value in saved.items() if key != "_id"}

    async def persist_delete(db, workspace, actor, template_id, revision, review_digest, identity_digest, **kwargs):
        saved = next(item for item in saved_templates if item['id'] == template_id)
        query = deletion_precondition(saved, workspace, revision, review_digest)
        await db.outreach_templates.delete_one(query)
        return {"contract_version": 1, "status": "deleted", "template_id": template_id,
            "workspace_id": workspace, "revision": revision, "review_digest": review_digest,
            "identity_digest": identity_digest, "scope_digest": kwargs['scope_digest']}

    monkeypatch.setattr('outreach.api.sequences.create_template', persist_create)
    monkeypatch.setattr('outreach.api.sequences.delete_template', persist_delete)
    user = {"user_id": "test_user_regression", "workspace_id": "ws_regression", "firebase_uid": "synthetic-uid"}
    from tests.template_access_fixtures import seed_catalog_access
    seed_catalog_access(mock_db, user['user_id'], user['workspace_id'], user['firebase_uid'])

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
        tree=[
            {"id": "n1", "type": "visit_profile", "delay_days": 0},
            {"id": "n2", "type": "connection_request", "delay_days": 0},
        ],
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
    review=custom_entry['deletion_review']
    request=DeleteTemplateRequest(**{key:review[key] for key in ('contract_version','workspace_id','revision','review_digest','identity_digest','scope_digest')})
    del_res = await delete_custom_template(template_id=tpl_id, req=request, current_user=user, db=mock_db)
    assert del_res["status"] == "deleted"

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

    async def mock_insert_camp(doc):
        campaigns_store[doc["id"]] = dict(doc)
        return AsyncMock(inserted_id=doc["id"])

    mock_db.outreach_campaigns.insert_one = mock_insert_camp

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
async def test_campaign_launch_and_lead_queueing(monkeypatch):
    from tests.campaign_readiness_fixtures import admission_database
    template = DAGCompiler.get_prebuilt_templates()[0]
    db = admission_database(monkeypatch, 'ws_launch', 'camp_test_launch', 'acc_sender_1', leads=5, nodes=template['nodes'])
    await db.outreach_sequences.update_one({}, {'$set': {'edges': template['edges']}})
    request = LaunchCampaignRequest(sender_account_ids=['acc_sender_1'], daily_limits={'connection_invites': 25})
    result = await launch_campaign('camp_test_launch', req=request, current_user={'user_id': 'u_launch', 'workspace_id': 'ws_launch'}, db=db)
    assert result['status'] == 'launched' and result['allocated_leads_count'] == 5
    root = DAGCompiler.validate_and_compile(template['nodes'], template['edges'])['root_node_ids'][0]
    leads = await db.outreach_leads.find({}).to_list(length=5)
    assert all(lead['current_node_id'] == root and lead['execution_state'] == LeadExecutionState.QUEUED for lead in leads)
    assert all(lead['assigned_account_id'] == 'acc_sender_1' for lead in leads)


@pytest.mark.asyncio
async def test_inbox_synchronization_and_campaign_kpi_impact():
    """Verify InboxSynchronizer sets lead has_replied=True and increments campaign reply metrics."""
    mock_db = AsyncMock()

    account = {
        "id": "acc_sync_1",
        "workspace_id": "ws_sync",
        "user_id": "u_sync",
        "status": "active",
        "session_cookie_enc": encrypt_secret("mock_cookie"),
        "jsession_id": "ajax:12345",
        "proxy_config": {"host": "1.2.3.4", "port": 8080},
    }
    mock_db.outreach_accounts.find_one = AsyncMock(return_value=account)
    mock_db.outreach_inbox_threads.find_one = AsyncMock(return_value=None)
    mock_db.outreach_inbox_threads.count_documents = AsyncMock(return_value=1)

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
    async def mock_lead_update_one(q, u):
        lead_updates.append((q, u))
        res = AsyncMock()
        res.modified_count = 1
        return res
    mock_db.outreach_leads.update_one = mock_lead_update_one

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
            "lead_urn": "urn:li:fsd_profile:alexrivers",
            "lead_profile_url": "https://linkedin.com/in/alexrivers",
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
        assert update_doc["$set"]["pause_reason"] == "Lead replied to outreach"
        mock_db.outreach_tasks.update_many.assert_awaited_once()

        # Verify campaign KPIs incremented
        assert len(campaign_kpi_increments) > 0
        q, inc_u = campaign_kpi_increments[0]
        assert q["id"] == "camp_e2e_target"
        assert inc_u["$inc"]["replies_count"] == 1
        assert campaign_kpi_increments[1][1]["$set"]["interested_count"] == 1
