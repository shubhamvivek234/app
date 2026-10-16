"""Owned replica-set decisions, authority stops, retry and receipt recovery."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pymongo.results import UpdateResult

from outreach.core.authorization import credential_generation, canonical_hash
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.sequence_conditions import decide
from outreach.core.dispatch_authority import AuthorityCollection
from outreach.tasks.sequence_dispatch import prepare_due, execute_job, dispatch_context, lead_stamp
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_campaign_readiness_mongo import seed as seed_readiness
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401
from tests.test_outreach_field_conditions import config

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned native Mongo opt-in')]
WS='workspace'


async def seed(db, monkeypatch, *, value='ready', condition=None):
    await seed_readiness(db)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','false')
    monkeypatch.setenv('OUTREACH_HUNTER_ENABLED','true')
    nodes=[{'id':'check','type':'has_data_in_column','config':condition or config()},
        {'id':'yes','type':'has_data_in_column','delay_hours':12,'config':config()},
        {'id':'no','type':'has_data_in_column','config':config()}]
    edges=[{'source':'check','target':'yes','label':'yes'},{'source':'check','target':'no','label':'no'}]
    compiled=DAGCompiler.validate_and_compile(nodes,edges)
    await db.outreach_sequence_versions.insert_one({'_id':'version','workspace_id':WS,'campaign_id':'campaign','version':1,
        'nodes':nodes,'edges':edges,'compiled_dag':compiled})
    await db.outreach_campaigns.update_one({}, {'$set':{'status':'active','authorization_revision':1,'sequence_version_id':'version',
        'schedule':{'timezone':'UTC','start_time':'00:00','end_time':'23:59','days':list(range(7))}}})
    await db.outreach_leads.update_one({}, {'$set':{'assigned_account_id':'sender','enrollment_id':'enrollment','authorized_revision':1,
        'sequence_version':1,'current_node_id':'check','execution_state':'queued','custom_variables':{'score':value}}})
    await db.outreach_accounts.update_one({}, {'$unset':{'proxy':'','session_cookie_enc':''}})
    account=await db.outreach_accounts.find_one({})
    await ExecutionPermission(db).grant(WS,'sender',credential_generation(account),['sequence'],'local-test',ttl_seconds=60)
    assert (await prepare_due(db))['prepared']==1
    return await db.outreach_sequence_jobs.find_one({})


@pytest.mark.parametrize('value,target',[('ready','yes'),('', 'no'),(False,'yes'),(0,'yes')])
async def test_data_only_decision_without_credentials_transport_intents_or_budget(replica_db,monkeypatch,value,target):
    from outreach.core import session_custody, proxy_custody
    cookie=AsyncMock(side_effect=AssertionError('must not open cookies'));proxy=AsyncMock(side_effect=AssertionError('must not open proxy'))
    monkeypatch.setattr(session_custody,'account_session',cookie)
    monkeypatch.setattr(proxy_custody,'prepare_proxy',proxy)
    job=await seed(replica_db,monkeypatch,value=value)
    result=await execute_job(replica_db,WS,job['_id'])
    assert result['status']=='branch_advanced',result
    lead=await replica_db.outreach_leads.find_one({}); saved=await replica_db.outreach_sequence_jobs.find_one({})
    assert lead['current_node_id']==target and saved['status']=='completed'
    assert saved['condition_decision']['next_action_due_at']==lead['next_action_due_at']
    assert not any(lead.get(k) for k in ['is_connected','last_action_at','email_verified'])
    for name in ['outreach_intents','outreach_physical_requests','outreach_request_budgets']:
        assert await replica_db[name].count_documents({})==0
    cookie.assert_not_awaited();proxy.assert_not_awaited()


@pytest.mark.parametrize('value',[[], {}, None])
async def test_unknown_comparison_is_durable_sanitized_hold(replica_db,monkeypatch,value):
    job=await seed(replica_db,monkeypatch,value=value,condition=config(operator='not_equals',value_type='text',value='private-copy'))
    result=await execute_job(replica_db,WS,job['_id'])
    assert result['status']=='condition_review_required',result
    lead=await replica_db.outreach_leads.find_one({});saved=await replica_db.outreach_sequence_jobs.find_one({})
    assert lead['execution_state']=='waiting_trigger' and lead['next_action_due_at'] is None
    assert 'private-copy' not in str(saved['condition_decision'])
    assert (await execute_job(replica_db,WS,job['_id']))['recovered'] is True
    assert (await prepare_due(replica_db))['prepared']==0


async def test_redelivery_preserves_original_decision_and_delay_after_field_changes(replica_db,monkeypatch):
    job=await seed(replica_db,monkeypatch)
    assert (await execute_job(replica_db,WS,job['_id']))['condition_met'] is True
    before=await replica_db.outreach_leads.find_one({})
    await replica_db.outreach_leads.update_one({}, {'$set':{'custom_variables.score':''}})
    result=await execute_job(replica_db,WS,job['_id'])
    assert result=={'status':'branch_advanced','condition_met':True,'recovered':True}
    assert (await replica_db.outreach_leads.find_one({}))['next_action_due_at']==before['next_action_due_at']


@pytest.mark.parametrize('fault',['lead','campaign','sender','sequence','unstamped','bool_marker','copied_key','bad_enrollment','bool_revision'])
async def test_native_replacement_and_legacy_jobs_do_not_choose_branch(replica_db,monkeypatch,fault):
    job=await seed(replica_db,monkeypatch)
    if fault=='bool_marker':await replica_db.outreach_sequence_jobs.update_one({}, {'$set':{'stamp.field_condition_contract_version':True}})
    elif fault=='copied_key':
        row=await replica_db.outreach_sequence_jobs.find_one({});await replica_db.outreach_sequence_jobs.delete_many({})
        row['_id']='copied-key';await replica_db.outreach_sequence_jobs.insert_one(row);job=row
    elif fault=='bad_enrollment':await replica_db.outreach_sequence_jobs.update_one({}, {'$set':{'stamp.enrollment_id':['enrollment']}})
    elif fault=='bool_revision':await replica_db.outreach_sequence_jobs.update_one({}, {'$set':{'stamp.authorization_revision':True}})
    elif fault=='unstamped':
        await replica_db.outreach_sequence_jobs.update_one({}, {'$unset':{'stamp.field_condition_contract_version':'','stamp.condition_native_ids':''}})
    else:
        name={'lead':'outreach_leads','campaign':'outreach_campaigns','sender':'outreach_accounts','sequence':'outreach_sequence_versions'}[fault]
        row=await replica_db[name].find_one({});old=row.pop('_id');await replica_db[name].delete_one({'_id':old})
        if fault=='sequence':
            row['_id']='replacement-version'
            await replica_db.outreach_campaigns.update_one({}, {'$set':{'sequence_version_id':'replacement-version'}})
        await replica_db[name].insert_one(row)
    assert (await execute_job(replica_db,WS,job['_id']))['status']=='stale_job'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='check'


@pytest.mark.parametrize('value',[[],{},0,False])
@pytest.mark.parametrize('field',['email','phone'])
async def test_malformed_recipient_identity_gets_durable_hold_without_branch(replica_db,monkeypatch,value,field):
    job=await seed(replica_db,monkeypatch)
    await replica_db.outreach_leads.update_one({}, {'$set':{field:value}})
    result=await execute_job(replica_db,WS,job['_id'])
    assert result=={'status':'condition_review_required','condition_met':None},result
    lead=await replica_db.outreach_leads.find_one({});saved=await replica_db.outreach_sequence_jobs.find_one({})
    assert lead['current_node_id']=='check' and lead['execution_state']=='waiting_trigger'
    assert saved['condition_decision']['reason']=='identity_unavailable'


async def test_native_large_numeric_target_is_executable_after_reload(replica_db,monkeypatch):
    job=await seed(replica_db,monkeypatch,value=2**53-1,condition=config(operator='equals',value_type='number',value=2**53-1))
    assert (await execute_job(replica_db,WS,job['_id']))=={'status':'branch_advanced','condition_met':True}


@pytest.mark.parametrize('fault',['reply','dnc','paid','permission','epoch','campaign','generation','disabled'])
async def test_current_authority_denies_decision(replica_db,monkeypatch,fault):
    job=await seed(replica_db,monkeypatch)
    if fault=='reply':await replica_db.outreach_leads.update_one({}, {'$set':{'has_replied':True}})
    elif fault=='dnc':await replica_db.outreach_leads.update_one({}, {'$set':{'do_not_contact':True}})
    elif fault=='paid':await replica_db.outreach_entitlements.update_one({}, {'$set':{'status':'expired'}})
    elif fault=='permission':await ExecutionPermission(replica_db).revoke(WS,'sender','tester','stop')
    elif fault=='epoch':monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','true')
    elif fault=='campaign':await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'paused'}})
    elif fault=='generation':await replica_db.outreach_accounts.update_one({}, {'$set':{'credential_generation':'replacement'}})
    else:monkeypatch.setenv('OUTREACH_HUNTER_ENABLED','false')
    result=await execute_job(replica_db,WS,job['_id'])
    assert result['status']!='branch_advanced',result
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='check'
    assert 'condition_decision' not in await replica_db.outreach_sequence_jobs.find_one({})


async def test_field_write_conflict_retries_with_current_value(replica_db,monkeypatch):
    job=await seed(replica_db,monkeypatch)
    original=AuthorityCollection.fence;changed=False
    async def interleave(self,document,query):
        nonlocal changed
        if self.name=='outreach_leads' and not changed:
            changed=True
            await replica_db.outreach_leads.update_one({}, {'$set':{'custom_variables.score':''}})
        return await original(self,document,query)
    monkeypatch.setattr(AuthorityCollection,'fence',interleave)
    result=await execute_job(replica_db,WS,job['_id'])
    assert result=={'status':'branch_advanced','condition_met':False},result
    assert changed and (await replica_db.outreach_leads.find_one({}))['current_node_id']=='no'


@pytest.mark.parametrize('fault',['cas','deadline'])
async def test_receipt_failure_rolls_back_lead_decision(replica_db,monkeypatch,fault):
    job=await seed(replica_db,monkeypatch)
    original=AuthorityCollection.update_one
    async def fail(self,query,update,**kwargs):
        if self.name=='outreach_sequence_jobs' and 'condition_decision' in update.get('$set',{}):
            if fault=='cas':return UpdateResult({'n':0,'nModified':0},True)
            result=await original(self,query,update,**kwargs)
            self.database.deadlines.append(datetime.now(timezone.utc)-timedelta(seconds=1))
            return result
        return await original(self,query,update,**kwargs)
    monkeypatch.setattr(AuthorityCollection,'update_one',fail)
    result=await execute_job(replica_db,WS,job['_id'])
    assert result['status']=='condition_authority_unavailable',result
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='check'
    assert 'condition_decision' not in await replica_db.outreach_sequence_jobs.find_one({})


async def test_existing_recipient_reply_blocks_data_advancement(replica_db,monkeypatch):
    job=await seed(replica_db,monkeypatch)
    await replica_db.outreach_inbox_threads.insert_one({'workspace_id':WS,'account_id':'sender',
        'lead_profile_url':'https://www.linkedin.com/in/synthetic','has_lead_reply':True})
    assert (await execute_job(replica_db,WS,job['_id']))['status']=='lead_suppressed'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='check'


async def test_restore_reply_stop_blocks_unreplied_lead(replica_db,monkeypatch):
    job=await seed(replica_db,monkeypatch)
    await replica_db.outreach_reply_stops.insert_one({'workspace_id':WS,'sender_id':'sender',
        'field':'normalized_url','value':'https://www.linkedin.com/in/synthetic'})
    assert (await execute_job(replica_db,WS,job['_id']))['status']=='lead_suppressed'


async def test_missing_enrollment_is_not_silently_adopted(replica_db,monkeypatch):
    await seed(replica_db,monkeypatch)
    await replica_db.outreach_sequence_jobs.delete_many({})
    await replica_db.outreach_leads.update_one({}, {'$unset':{'enrollment_id':''}})
    assert (await prepare_due(replica_db))['prepared']==0


@pytest.mark.parametrize('fault',['array_status','bool_version','wrong_node','branch_missing_value'])
async def test_corrupted_receipt_does_not_fabricate_recovery(replica_db,monkeypatch,fault):
    job=await seed(replica_db,monkeypatch)
    assert (await execute_job(replica_db,WS,job['_id']))['status']=='branch_advanced'
    change={'array_status':{'condition_decision.status':[]},'bool_version':{'condition_decision.version':True},
        'wrong_node':{'condition_decision.node_id':'other'},'branch_missing_value':{'condition_decision.condition_met':None}}[fault]
    await replica_db.outreach_sequence_jobs.update_one({}, {'$set':change})
    assert (await execute_job(replica_db,WS,job['_id']))=={'status':'already_claimed'}


async def test_data_only_launch_and_readiness_do_not_open_linkedin_material(replica_db,monkeypatch):
    from outreach.api import campaigns
    from outreach.core import session_custody, proxy_custody
    await seed(replica_db,monkeypatch)
    await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'draft','authorization_revision':0}})
    opener=AsyncMock(side_effect=AssertionError('must not open transport material'))
    monkeypatch.setattr(session_custody,'account_session',opener);monkeypatch.setattr(proxy_custody,'prepare_proxy',opener)
    user={'user_id':'actor','default_workspace_id':WS}
    report=await campaigns.get_campaign_preflight('campaign',user,replica_db)
    assert report['can_launch'] is True,report
    result=await campaigns._launch_campaign_impl('campaign',None,user,replica_db)
    assert result['status']=='launched',result
    opener.assert_not_awaited()


@pytest.mark.parametrize('rollback',[False,True])
async def test_saved_original_acceptance_outranks_field_decision_and_nested_failure_rolls_back(replica_db,monkeypatch,rollback):
    from tests.test_outreach_connection_waits_mongo import seed as seed_connection, negative, record
    from outreach.core.connection_waits import ConnectionWaitUnavailable
    from outreach.core import sequence_conditions
    await seed_connection(replica_db)
    sequence=await replica_db.outreach_sequence_versions.find_one({})
    sequence['nodes'][1].update(type='has_data_in_column',config=config())
    # Old linear edge is replaced with an explicit condition branch.
    sequence['edges'][1]['label']='yes'
    compiled=DAGCompiler.validate_and_compile(sequence['nodes'],sequence['edges'])
    await replica_db.outreach_sequence_versions.update_one({}, {'$set':{'nodes':sequence['nodes'],'edges':sequence['edges'],'compiled_dag':compiled}})
    scope=await negative(replica_db)
    await record(replica_db,True)
    lead=await replica_db.outreach_leads.find_one({});campaign=await replica_db.outreach_campaigns.find_one({})
    account=await replica_db.outreach_accounts.find_one({});sequence=await replica_db.outreach_sequence_versions.find_one({})
    stamp=lead_stamp(lead,campaign,sequence,account)
    key=canonical_hash([WS,stamp])
    job={'_id':key,'workspace_id':WS,'stamp':stamp,'status':'processing','owner':'negative-owner',
        'claim_expires_at':datetime.now(timezone.utc)+timedelta(seconds=60)}
    await replica_db.outreach_sequence_jobs.insert_one(job)
    if rollback:
        original=sequence_conditions.apply_observation
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise ConnectionWaitUnavailable('injected_after_nested_writes')
        monkeypatch.setattr(sequence_conditions,'apply_observation',fail)
    with dispatch_context(replica_db,job,'negative-owner'):
        result=await decide(replica_db,lead)
    current=await replica_db.outreach_leads.find_one({});saved=await replica_db.outreach_sequence_jobs.find_one({'_id':key})
    assert result['status']==('condition_authority_unavailable' if rollback else 'connection_redirected'),result
    assert current['current_node_id']==('no' if rollback else 'yes')
    assert saved['status']==('processing' if rollback else 'superseded')
    assert 'condition_decision' not in saved
    if rollback:assert (await replica_db.outreach_connection_waits.find_one({}))['revision']==scope['revision']


async def test_worker_finally_preserves_job_superseded_by_late_acceptance(replica_db,monkeypatch):
    from tests.test_outreach_connection_waits_mongo import seed as seed_connection, negative, record
    from outreach.tasks import connection_recheck
    await seed_connection(replica_db)
    sequence=await replica_db.outreach_sequence_versions.find_one({})
    sequence['nodes'][1].update(type='has_data_in_column',config=config())
    sequence['edges'][1]['label']='yes'
    compiled=DAGCompiler.validate_and_compile(sequence['nodes'],sequence['edges'])
    await replica_db.outreach_sequence_versions.update_one({}, {'$set':{'nodes':sequence['nodes'],'edges':sequence['edges'],'compiled_dag':compiled}})
    await negative(replica_db)
    assert (await prepare_due(replica_db))['prepared']==1
    job=await replica_db.outreach_sequence_jobs.find_one({})
    async def publish_after_prior_check(*args,**kwargs):
        await record(replica_db,True)
        return None
    monkeypatch.setattr(connection_recheck,'recheck_connection',publish_after_prior_check)
    result=await execute_job(replica_db,WS,job['_id'])
    assert result['status']=='connection_redirected',result
    current=await replica_db.outreach_sequence_jobs.find_one({'_id':job['_id']})
    assert current['status']=='superseded' and 'condition_decision' not in current
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='yes'
