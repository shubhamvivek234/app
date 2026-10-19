"""Actual API/version/launch/admission checks; never real provider requests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import uuid
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.sequences import router, SaveSequenceRequest, save_campaign_sequence, preview_scope
from outreach.core import session_custody
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.suppression import guard_scope
from outreach.core.lead_importer import LeadImporter
from outreach.tasks.sequence_executor import SequenceExecutor
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_campaign_readiness_mongo import seed as seed_readiness
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned native Mongo opt-in')]
USER={'user_id':'actor','firebase_uid':'uid','default_workspace_id':'workspace'}


def graph(delay=0):
    return [{'id':'root','type':'visit_profile','delay_hours':delay,'config':{}}],[]


async def client(db,role='admin'):
    await db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'actor','role':role})
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:USER
    app.dependency_overrides[get_db]=lambda:db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')


async def gallery_client(db, role='admin'):
    """Seed the authenticated identity required by the gallery access contract."""
    await db.users.insert_one({'user_id': 'actor', 'firebase_uid': 'uid', 'status': 'active'})
    return await client(db, role)


@pytest.mark.parametrize('role,expected',[('admin',200),('editor',200),('viewer',403)])
async def test_preview_permissions_without_real_record_lookup_or_mutation(replica_db,role,expected):
    nodes,edges=graph()
    async with await client(replica_db,role) as api:
        result=await api.post('/sequences/preview',json={'request_id':str(uuid.uuid4()),'request_scope':preview_scope(USER),'nodes':nodes,'edges':edges})
    assert result.status_code==expected,result.text
    if expected==200:
        assert result.json()['execution_authorized'] is False and result.json()['ending']=='await_action_outcome'
    assert set(await replica_db.list_collection_names())<= {'workspace_members','outreach_account_deletions','outreach_suppression_guards'}


async def test_preview_denies_revocation_and_stopped_workspace(replica_db):
    nodes,edges=graph();body={'request_id':str(uuid.uuid4()),'request_scope':preview_scope(USER),'nodes':nodes,'edges':edges}
    async with await client(replica_db) as api:
        await replica_db.workspace_members.delete_many({})
        assert (await api.post('/sequences/preview',json=body)).status_code==403
        await replica_db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'actor','role':'admin'})
        await replica_db.outreach_suppression_guards.insert_one({**guard_scope('workspace'),'erasure_state':'stopped'})
        assert (await api.post('/sequences/preview',json=body)).status_code==409


@pytest.mark.parametrize('role', ['admin', 'viewer'])
async def test_gallery_reads_scoped_email_without_mutating_native_template_or_granting_execution(replica_db, role):
    from tests.test_outreach_template_gallery import template
    row=template();row.pop('_id')
    await replica_db.outreach_templates.insert_one(row)
    await replica_db.outreach_templates.insert_one({**row,'_id':'other-native','id':'other-template','workspace_id':'other'})
    before=await replica_db.outreach_templates.find({}).to_list(10)
    async with await gallery_client(replica_db,role) as api:
        result=await api.get('/sequences/templates')
    assert result.status_code==200,result.text
    custom=[item for item in result.json() if item['id']=='custom-email']
    assert len(custom)==1 and custom[0]['compatibility']['configuration_available'] is True
    assert custom[0]['compatibility']['execution_authorized'] is False
    assert all(item['id']!='other-template' for item in result.json())
    assert await replica_db.outreach_templates.find({}).to_list(10)==before
    assert await replica_db.outreach_tasks.count_documents({})==0
    assert await replica_db.outreach_campaigns.count_documents({})==0


async def test_gallery_existing_resolution_excludes_revoked_workspace_and_denies_stopped_workspace(replica_db):
    from tests.test_outreach_template_gallery import template
    row=template();row.pop('_id')
    await replica_db.outreach_templates.insert_one(row)
    async with await gallery_client(replica_db) as api:
        await replica_db.workspace_members.delete_many({})
        # Existing authentication may create/select a personal workspace.
        # It must not expose templates from the workspace just revoked.
        result=await api.get('/sequences/templates')
        assert result.status_code==200
        assert all(item['id']!='custom-email' for item in result.json())
        await replica_db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'actor','role':'admin'})
        await replica_db.outreach_suppression_guards.insert_one({**guard_scope('workspace'),'erasure_state':'stopped'})
        assert (await api.get('/sequences/templates')).status_code==409


async def test_new_authoring_revision_preserves_original_snapshot_and_stopped_authority(replica_db):
    await seed_readiness(replica_db)
    nodes,edges=graph()
    await save_campaign_sequence(SaveSequenceRequest(campaign_id='campaign',nodes=nodes,edges=edges),USER,replica_db)
    first=await replica_db.outreach_sequence_versions.find_one({})
    nodes2,edges2=graph(12)
    await save_campaign_sequence(SaveSequenceRequest(campaign_id='campaign',nodes=nodes2,edges=edges2),USER,replica_db)
    assert await replica_db.outreach_sequence_versions.find_one({'_id':first['_id']})==first
    campaign=await replica_db.outreach_campaigns.find_one({})
    newest=await replica_db.outreach_sequence_versions.find_one({'_id':campaign['sequence_version_id']})
    assert newest['version']==2 and newest['compiler_contract_version']==1 and newest['compiled_dag']['nodes']['root']['delay_hours']==12
    assert campaign['status']=='draft' and await replica_db.outreach_execution_permissions.count_documents({})==0


@pytest.mark.parametrize('fault',['delay','branch','unsupported','tree','config'])
async def test_invalid_authoring_cannot_publish_or_change_campaign(replica_db,fault):
    await seed_readiness(replica_db);before=await replica_db.outreach_campaigns.find_one({})
    nodes,edges=graph();tree=None
    if fault=='delay':nodes[0]['delay_hours']=True
    elif fault=='branch':
        nodes=[{'id':'root','type':'if_connected'},{'id':'message','type':'send_message','config':{'body':'Hello'}}]
        edges=[{'source':'root','target':'message','label':'no'}]
    elif fault=='unsupported':nodes[0]['type']='inmail'
    elif fault=='tree':tree=[{'id':'different','type':'visit_profile'}]
    elif fault=='config':nodes[0]['config']=[]
    with pytest.raises(HTTPException) as failure:await save_campaign_sequence(SaveSequenceRequest(campaign_id='campaign',nodes=nodes,edges=edges,tree=tree),USER,replica_db)
    assert failure.value.status_code==400
    assert await replica_db.outreach_sequence_versions.count_documents({})==0
    assert await replica_db.outreach_campaigns.find_one({})==before


async def test_readiness_rejects_old_invalid_sequence_without_opening_credentials(replica_db,monkeypatch):
    from outreach.api import campaigns
    await seed_readiness(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set':{'nodes.0.delay_hours':True}})
    opening=AsyncMock(side_effect=AssertionError('must not open credentials'))
    monkeypatch.setattr(session_custody,'account_session',opening)
    report=await campaigns.get_campaign_preflight('campaign',USER,replica_db)
    assert report['can_launch'] is False
    with pytest.raises(HTTPException):await campaigns._launch_campaign_impl('campaign',None,USER,replica_db)
    opening.assert_not_awaited()


async def test_root_delay_starts_after_warmup_and_is_not_restarted_on_resume(replica_db,monkeypatch):
    from outreach.api import campaigns
    await seed_readiness(replica_db);nodes,edges=graph(12)
    await replica_db.outreach_sequences.update_one({}, {'$set':{'nodes':nodes,'edges':edges,'compiled_dag':DAGCompiler.validate_and_compile(nodes,edges)}})
    monkeypatch.setattr(session_custody,'account_session',AsyncMock(return_value={'session_cookie_enc':'synthetic'}))
    policy = await campaigns._evaluate_warmup('campaign','workspace',replica_db)
    warmup = datetime.now(timezone.utc)+timedelta(hours=24)
    monkeypatch.setattr(campaigns,'_evaluate_warmup',AsyncMock(return_value={**policy,'ready_at':warmup}))
    before=datetime.now(timezone.utc)-timedelta(milliseconds=2)
    await campaigns._launch_campaign_impl('campaign',None,USER,replica_db)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});due=lead['next_action_due_at']
    assert due>=warmup+timedelta(hours=12)-timedelta(milliseconds=2)
    await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'paused'}})
    await campaigns._launch_campaign_impl('campaign',None,USER,replica_db)
    assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['next_action_due_at']==due


async def test_active_import_binds_new_root_delay_with_same_authorization(replica_db,monkeypatch):
    from outreach.api import campaigns
    await seed_readiness(replica_db);nodes,edges=graph(8)
    await replica_db.outreach_sequences.update_one({}, {'$set':{'nodes':nodes,'edges':edges,'compiled_dag':DAGCompiler.validate_and_compile(nodes,edges)}})
    monkeypatch.setattr(session_custody,'account_session',AsyncMock(return_value={'session_cookie_enc':'synthetic'}))
    await campaigns._launch_campaign_impl('campaign',None,USER,replica_db)
    before=datetime.now(timezone.utc)-timedelta(milliseconds=2)
    result=await LeadImporter.ingest_leads([{'linkedin_url':'https://linkedin.com/in/synthetic-new','first_name':'Example'}],'campaign','workspace',replica_db)
    lead=await replica_db.outreach_leads.find_one({'id':result['lead_ids'][0]})
    assert lead['next_action_due_at']>=before+timedelta(hours=8) and lead['current_node_id']=='root'
    assert lead['assigned_account_id']=='sender' and lead['authorized_revision']==1


@pytest.mark.parametrize('fault',['config','source_mismatch','future_due','compiled_array','nodes_array','row_array','type_array','current_array','current_empty','current_missing_target','max_age','skip_bool'])
async def test_old_pinned_fault_cannot_prepare_or_send_and_does_not_clear_evidence(replica_db,monkeypatch,fault):
    await seed_readiness(replica_db)
    nodes,edges=graph();compiled=DAGCompiler.validate_and_compile(nodes,edges)
    await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag':compiled}})
    await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'active','authorization_revision':1}})
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'assigned_account_id':'sender','current_node_id':'root','authorized_revision':1,'sequence_version':1}})
    if fault=='config':await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes.root.config':[]}})
    elif fault in {'max_age','skip_bool'}:await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes.root.type':'like_last_post','compiled_dag.nodes.root.config':{'max_post_age_days':[]} if fault=='max_age' else {'skip_if_no_posts':'false'}}})
    elif fault=='source_mismatch':await replica_db.outreach_sequences.update_one({}, {'$set':{'nodes.0.delay_hours':12}})
    elif fault=='compiled_array':await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag':[]}})
    elif fault=='nodes_array':await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes':[]}})
    elif fault=='row_array':await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes.root':[]}})
    elif fault=='type_array':await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes.root.type':[]}})
    elif fault=='current_array':await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':[]}})
    elif fault=='current_empty':await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':''}})
    elif fault=='current_missing_target':await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':'absent'}})
    else:await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'next_action_due_at':datetime.now(timezone.utc)+timedelta(hours=1)}})
    before=await replica_db.outreach_tasks.find({}).to_list(100)
    opening=AsyncMock(side_effect=AssertionError('no custody/provider preparation'))
    monkeypatch.setattr(session_custody,'account_session',opening)
    monkeypatch.setattr('outreach.tasks.sequence_executor.account_session',opening)
    monkeypatch.setattr('outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours',lambda *args:True)
    monkeypatch.setattr('outreach.tasks.sequence_executor.VoyagerClient',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('no transport')))
    result=await SequenceExecutor.execute_lead_step('lead',replica_db,workspace_id='workspace')
    assert result['status'] in {'sequence_review_required','not_due'},result
    opening.assert_not_awaited()
    assert await replica_db.outreach_tasks.find({}).to_list(100)==before
    assert await replica_db.outreach_execution_permissions.count_documents({})==0


@pytest.mark.parametrize('fault',['raw_type','compiled_row'])
async def test_readiness_reports_malformed_graph_without_raising(replica_db,monkeypatch,fault):
    from outreach.api import campaigns
    await seed_readiness(replica_db)
    if fault=='raw_type':await replica_db.outreach_sequences.update_one({}, {'$set':{'nodes.0.type':[]}})
    else:await replica_db.outreach_sequences.update_one({}, {'$set':{'compiled_dag.nodes.root':[]}})
    opening=AsyncMock(side_effect=AssertionError('no custody for invalid graph'))
    monkeypatch.setattr(session_custody,'account_session',opening)
    result=await campaigns.get_campaign_preflight('campaign',USER,replica_db)
    assert result['can_launch'] is False
    assert next(row for row in result['checklist'] if row['id']=='sequence')['passed'] is False
    opening.assert_not_awaited()


@pytest.mark.parametrize('current',['',[],0])
async def test_launch_does_not_reset_malformed_current_step(replica_db,monkeypatch,current):
    from outreach.api import campaigns
    await seed_readiness(replica_db)
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':current}})
    monkeypatch.setattr(session_custody,'account_session',AsyncMock(return_value={'session_cookie_enc':'synthetic'}))
    await campaigns._launch_campaign_impl('campaign',None,USER,replica_db)
    assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['current_node_id']==current


@pytest.mark.parametrize('fault',['missing_tree','tree_mismatch','compiled_mismatch'])
async def test_legacy_editor_holds_without_replacing_saved_graph(replica_db,fault):
    from outreach.api.sequences import get_campaign_sequence
    await seed_readiness(replica_db)
    nodes,edges=graph();tree=[{'id':'root','type':'visit_profile','config':{}}]
    update={'tree':tree,'compiled_dag':DAGCompiler.validate_and_compile(nodes,edges)}
    if fault=='missing_tree':update['tree']=None
    elif fault=='tree_mismatch':update['tree'][0]['id']='other'
    else:update['compiled_dag']['nodes']['root']['delay_hours']=1
    await replica_db.outreach_sequences.update_one({}, {'$set':update})
    before=await replica_db.outreach_sequences.find_one({})
    result=await get_campaign_sequence('campaign',USER,replica_db)
    assert result['editor_error'] and result['tree'] is None and not result['nodes']
    assert await replica_db.outreach_sequences.find_one({})==before


@pytest.mark.parametrize('fault',['compiled_array','delay_array','warmup_text','missing_version'])
async def test_invalid_active_intake_graph_or_timing_rolls_back_admission(replica_db,fault):
    from tests.test_outreach_lead_admission_mongo import campaign as active_campaign
    await active_campaign(replica_db)
    if fault=='missing_version':await replica_db.outreach_sequence_versions.delete_many({})
    elif fault=='compiled_array':await replica_db.outreach_sequence_versions.update_one({}, {'$set':{'compiled_dag':[]}})
    elif fault=='delay_array':await replica_db.outreach_sequence_versions.update_one({}, {'$set':{'compiled_dag.nodes.root.delay_hours':[]}})
    else:await replica_db.outreach_campaigns.update_one({}, {'$set':{'warmup_until':'unproven'}})
    before=await replica_db.outreach_campaigns.find_one({})
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([{'linkedin_url':'https://linkedin.com/in/no-admission'}],'campaign','workspace',replica_db)
    assert failure.value.status_code==409
    assert await replica_db.outreach_leads.count_documents({})==0
    assert await replica_db.outreach_campaigns.find_one({})==before
