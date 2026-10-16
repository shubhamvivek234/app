"""Owned replica-set original wait/redirection races; synthetic receipts only."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import asyncio
import os
import uuid
import pytest
from outreach.core.authorization import canonical_hash
from outreach.core.connection_waits import begin_wait, apply_observation, read_operation, read_context, scope_guard, ConnectionWaitUnavailable, native
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.execution_outbox import ExecutionOutbox
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.inbox_freshness import credential_generation
from outreach.core.sequence_versions import load_sequence
from outreach.tasks.sequence_dispatch import lead_stamp
from tests.outreach_native import replica_server,replica_db  # noqa:F401
from tests.test_outreach_campaign_readiness_mongo import seed as seed_readiness
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa:F401

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned Mongo opt-in')]
WS='workspace';TARGET='urn:li:fsd_profile:original'


async def seed(db,*,expired=True,positive=True,merge=False,negative_kind="visit_profile"):
    await seed_readiness(db)
    nodes=[{'id':'invite','type':'connection_request','config':{'timeout_days':1}},
        {'id':'no','type':negative_kind,'delay_hours':12}, {'id':'no2','type':'visit_profile'}]
    edges=[{'source':'invite','target':'no','label':'not accepted'},{'source':'no','target':'no2'}]
    if positive:
        nodes.append({'id':'yes','type':'visit_profile','delay_hours':24});edges.append({'source':'invite','target':'yes','label':'accepted'})
    if merge:
        nodes.append({'id':'merge','type':'visit_profile'});edges.extend([{'source':'no2','target':'merge'},{'source':'yes','target':'merge'}])
    compiled=DAGCompiler.validate_and_compile(nodes,edges)
    await db.outreach_sequence_versions.insert_one({'_id':'version','workspace_id':WS,'campaign_id':'campaign','version':1,'nodes':nodes,'edges':edges,'compiled_dag':compiled})
    await db.outreach_campaigns.update_one({}, {'$set':{'status':'active','authorization_revision':1,'sequence_version_id':'version','schedule':{'timezone':'UTC','start_time':'00:00','end_time':'23:59','days':list(range(7))}}})
    await db.outreach_leads.update_one({'id':'lead'},{'$set':{'assigned_account_id':'sender','enrollment_id':'enrollment','authorized_revision':1,
        'sequence_version':1,'current_node_id':'invite','execution_claim_token':'original-worker','execution_state':'queued'}})
    account=await db.outreach_accounts.find_one({});generation=credential_generation(account)
    now=datetime.now(timezone.utc)
    await ExecutionPermission(db).grant(WS,'sender',generation,['sequence'],'local-test',ttl_seconds=60)
    outbox=ExecutionOutbox(db)
    at=now-timedelta(days=2) if expired else now-timedelta(minutes=1)
    intent=await outbox.ensure(workspace_id=WS,campaign_id='campaign',lead_id='lead',sender_id='sender',node_id='invite',action_kind='connection_request',
        sequence_version=1,authorization_revision=1,credential_generation=generation,legacy_operation_id='lead:invite',enrollment_id='enrollment',now=at)
    assert await outbox.claim(WS,intent['_id'],'invite-owner',now=at)
    assert await outbox.begin_submission(WS,intent['_id'],'invite-owner',now=at)
    await outbox.finish(WS,intent['_id'],'invite-owner','provider_accepted',provider_result_status='invite_sent',provider_recipient_urn=TARGET,provider_request_id='invite-receipt',now=at)
    refs=[]
    for collection,query in (('outreach_leads',{'id':'lead'}),('outreach_campaigns',{'id':'campaign'}),('outreach_accounts',{'id':'sender'})):
        original=await db[collection].find_one(query)
        refs.append({'collection':collection,'id_hash':canonical_hash(original['_id']),'native_hash':native(original)})
    await db.outreach_physical_requests.insert_one({'_id':'invite-receipt','workspace_id':WS,'sender_id':'sender','credential_generation':generation,
        'source':'sequence','owner_token':'invite-owner','action':'invite','mutation':True,'status':'response_received','http_status':201,
        'logical_operation_id':intent['_id'],
        'endpoint_digest':canonical_hash(['POST','/voyager/api/growth/normInvitations']),'completed_at':at,
        'dispatch_authorization':{'mode':'transaction','authority_refs':refs},'connection_fact':{'version':1,'kind':'invite_target','recipient_urn':TARGET,'connected':None,'observed_at':at}})
    return intent


async def record(db,connected,*,change=None,now=None):
    lead=await db.outreach_leads.find_one({'id':'lead'});scope=await db.outreach_connection_waits.find_one({'_id':lead['connection_wait_id']})
    now=now or datetime.now(timezone.utc);key=str(uuid.uuid4())
    row={'_id':key,'workspace_id':WS,'sender_id':'sender','credential_generation':scope['credential_generation'],'source':'sequence',
        'owner_token':'read-owner','action':'read','mutation':False,'status':'response_received','http_status':200,'completed_at':now,
        'logical_operation_id':read_operation(scope,lead),'connection_wait_context':read_context(scope,lead),
        'endpoint_digest':canonical_hash(['GET','/voyager/api/relationships/connections']),
        'dispatch_authorization':{'mode':'transaction'},'connection_fact':{'version':1,'kind':'observed_connection','recipient_urn':TARGET,'connected':connected,'observed_at':now}}
    if change:change(row)
    await db.outreach_physical_requests.insert_one(row)
    return key


async def negative(db):
    scope=await begin_wait(db,WS,'lead')
    result=await apply_observation(db,WS,'lead',scope['_id'],await record(db,False))
    assert result['status']=='branch_advanced',result
    await db.outreach_leads.update_one({'id':'lead'},{'$set':{'execution_claim_token':'negative-owner','next_action_due_at':datetime.now(timezone.utc)}})
    return await db.outreach_connection_waits.find_one({'_id':scope['_id']})


async def pending(db,*,claim=False):
    lead=await db.outreach_leads.find_one({'id':'lead'});campaign=await db.outreach_campaigns.find_one({});account=await db.outreach_accounts.find_one({});sequence=await load_sequence(db,WS,'campaign',campaign=campaign)
    outbox=ExecutionOutbox(db)
    intent=await outbox.ensure(workspace_id=WS,campaign_id='campaign',lead_id='lead',sender_id='sender',node_id='no',action_kind='visit_profile',
        sequence_version=1,authorization_revision=1,credential_generation=credential_generation(account),legacy_operation_id='lead:no',enrollment_id='enrollment')
    if claim:
        assert await outbox.claim(WS,intent['_id'],'negative-owner')
        await db.outreach_tasks.insert_one({'id':'lead:no','workspace_id':WS,'lead_id':'lead','campaign_id':'campaign','account_id':'sender',
            'owner_token':'negative-owner','intent_id':intent['_id'],'task_type':'visit_profile','status':'preparing'})
    stamp=lead_stamp(lead,campaign,sequence,account)
    await db.outreach_sequence_jobs.insert_one({'_id':canonical_hash([WS,stamp]),'workspace_id':WS,'stamp':stamp,'intent_id':intent['_id'],'status':'queued'})
    return intent


async def test_original_scope_preserves_confirmed_wait_time_and_duplicate_creation(replica_db):
    intent=await seed(replica_db)
    scope=await begin_wait(replica_db,WS,'lead')
    again=await begin_wait(replica_db,WS,'lead')
    original=await replica_db.outreach_intents.find_one({'_id':intent['_id']})
    assert scope['wait_started_at']==original['attempt']['completed_at']==again['wait_started_at']
    assert await replica_db.outreach_connection_waits.count_documents({})==1
    assert scope['recipient_urn']==TARGET and scope['wait_deadline_at']==scope['wait_started_at']+timedelta(days=1)


@pytest.mark.parametrize('fault',['missing_target','human','owner','wrong_action','receipt_error','receipt_target','receipt_mode'])
async def test_legacy_or_malformed_original_invite_never_gets_late_authority(replica_db,fault):
    intent=await seed(replica_db)
    if fault=='missing_target':await replica_db.outreach_intents.update_one({'_id':intent['_id']},{'$unset':{'attempt.provider_recipient_urn':''}})
    elif fault=='human':await replica_db.outreach_intents.update_one({'_id':intent['_id']},{'$set':{'resolution':{'source':'human'}}})
    elif fault=='owner':await replica_db.outreach_intents.update_one({'_id':intent['_id']},{'$set':{'attempt.owner_token':'other'}})
    elif fault=='wrong_action':await replica_db.outreach_intents.update_one({'_id':intent['_id']},{'$set':{'action_kind':'send_message'}})
    elif fault=='receipt_error':await replica_db.outreach_physical_requests.update_one({}, {'$set':{'status':'unknown_outcome'}})
    elif fault=='receipt_target':await replica_db.outreach_physical_requests.update_one({}, {'$set':{'connection_fact.recipient_urn':'urn:li:fsd_profile:other'}})
    else:await replica_db.outreach_physical_requests.update_one({}, {'$set':{'dispatch_authorization':[]}})
    with pytest.raises(ConnectionWaitUnavailable):await begin_wait(replica_db,WS,'lead')
    assert await replica_db.outreach_connection_waits.count_documents({})==0
    assert not (await replica_db.outreach_leads.find_one({})).get('connection_wait_required')


async def test_deadline_negative_transition_applies_saved_delay_without_reset(replica_db):
    await seed(replica_db);scope=await negative(replica_db)
    lead=await replica_db.outreach_leads.find_one({})
    assert scope['status']=='negative_active' and scope['revision']==2 and lead['current_node_id']=='no'
    assert 'waiting_for_connection_at' not in lead


@pytest.mark.parametrize('claim',[False,True])
async def test_late_connected_atomically_redirects_and_fences_only_pending_work(replica_db,claim):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=claim)
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_redirected',result
    lead=await replica_db.outreach_leads.find_one({})
    assert lead['current_node_id']=='yes' and lead['is_connected'] is True and lead['connection_wait_revision']==3
    assert lead['next_action_due_at']==result['receipt']['next_action_due_at']
    assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='canceled'
    assert (await replica_db.outreach_sequence_jobs.find_one({}))['status']=='superseded'
    if claim:assert (await replica_db.outreach_tasks.find_one({'id':'lead:no'}))['status']=='cancelled'
    again=await apply_observation(replica_db,WS,'lead',scope['_id'],None,now=datetime.now(timezone.utc)+timedelta(hours=1))
    assert again['receipt']==result['receipt'] and again['recovered'] is True
    assert (await replica_db.outreach_leads.find_one({}))['next_action_due_at']==lead['next_action_due_at']


@pytest.mark.parametrize('outcome',['in_flight','executed','unknown_outcome','legacy_task','physical'])
async def test_possibly_submitted_negative_work_is_retained_and_held(replica_db,outcome):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True)
    if outcome in {'in_flight','executed','unknown_outcome'}:
        assert await ExecutionOutbox(replica_db).begin_submission(WS,intent['_id'],'negative-owner')
        if outcome=='executed':await ExecutionOutbox(replica_db).finish(WS,intent['_id'],'negative-owner','request_observed',provider_result_status='viewed')
        elif outcome=='unknown_outcome':await ExecutionOutbox(replica_db).finish(WS,intent['_id'],'negative-owner','unknown_outcome')
    elif outcome=='legacy_task':await replica_db.outreach_tasks.update_one({'id':'lead:no'}, {'$set':{'status':'dispatching'}})
    else:await replica_db.outreach_physical_requests.insert_one({'workspace_id':WS,'sender_id':'sender','owner_token':'negative-owner','mutation':True,'status':'response_received'})
    original=await replica_db.outreach_intents.find_one({'_id':intent['_id']});task=await replica_db.outreach_tasks.find_one({'id':'lead:no'})
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_wait_review_required',result
    current=await replica_db.outreach_intents.find_one({'_id':intent['_id']});current.pop('dispatch_fence_revision',None);original.pop('dispatch_fence_revision',None)
    actual_task=await replica_db.outreach_tasks.find_one({'id':'lead:no'});actual_task.pop('dispatch_fence_revision',None);task.pop('dispatch_fence_revision',None)
    assert current==original and actual_task==task
    assert (await replica_db.outreach_connection_waits.find_one({}))['status']=='held'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='no'


@pytest.mark.parametrize('fault',['enrollment','recipient','sender_generation','revision','native_lead','native_campaign','sequence'])
async def test_old_scope_cannot_adopt_replacement_or_changed_authority(replica_db,fault):
    await seed(replica_db);scope=await negative(replica_db);request=await record(replica_db,True)
    if fault=='enrollment':await replica_db.outreach_leads.update_one({}, {'$set':{'enrollment_id':'replacement'}})
    elif fault=='recipient':await replica_db.outreach_leads.update_one({}, {'$set':{'linkedin_url':'https://linkedin.com/in/replacement'}})
    elif fault=='sender_generation':await replica_db.outreach_accounts.update_one({}, {'$set':{'credential_generation':'replacement'}})
    elif fault=='revision':await replica_db.outreach_campaigns.update_one({}, {'$inc':{'authorization_revision':1}})
    elif fault.startswith('native'):
        col=replica_db.outreach_leads if fault=='native_lead' else replica_db.outreach_campaigns
        row=await col.find_one({});await col.delete_one({'_id':row['_id']});row.pop('_id');await col.insert_one(row)
    else:await replica_db.outreach_sequence_versions.update_one({}, {'$set':{'compiled_dag.nodes.no.delay_hours':1}})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='no'


@pytest.mark.parametrize('connected',[None,False])
async def test_unknown_never_becomes_negative_or_redirect_authority(replica_db,connected):
    await seed(replica_db,expired=False);scope=await begin_wait(replica_db,WS,'lead')
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,connected))
    assert result['status']==('condition_unknown' if connected is None else 'waiting_for_condition')
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='invite'


async def test_unavailable_late_observation_holds_without_inventing_negative(replica_db):
    await seed(replica_db);scope=await negative(replica_db)
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],None)
    assert result['status']=='connection_wait_review_required'
    lead=await replica_db.outreach_leads.find_one({});assert lead['current_node_id']=='no' and lead['execution_state']=='waiting_trigger'


@pytest.mark.parametrize('fault',['target','stale','future','operation','mode','source','generation','ownerless_kind'])
async def test_read_fact_must_match_original_request_context(replica_db,fault):
    await seed(replica_db);scope=await negative(replica_db)
    def change(row):
        if fault=='target':row['connection_fact']['recipient_urn']='urn:li:fsd_profile:other'
        elif fault in {'stale','future'}:
            at=datetime.now(timezone.utc)+timedelta(minutes=-2 if fault=='stale' else 2);row['completed_at']=at;row['connection_fact']['observed_at']=at
        elif fault=='operation':row['logical_operation_id']='other'
        elif fault=='mode':row['dispatch_authorization']=[]
        elif fault=='source':row['source']='sync'
        elif fault=='generation':row['credential_generation']='other'
        else:row['connection_fact']['kind']='human'
    request=await record(replica_db,True,change=change)
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id']=='no'


async def test_two_observations_commit_one_redirect_and_original_due(replica_db):
    await seed(replica_db);scope=await negative(replica_db);await pending(replica_db)
    one=await record(replica_db,True);two=await record(replica_db,True)
    results=await asyncio.gather(*(apply_observation(replica_db,WS,'lead',scope['_id'],key) for key in (one,two)))
    assert all(row['status']=='connection_redirected' for row in results),results
    assert results[0]['receipt']==results[1]['receipt']
    assert (await replica_db.outreach_connection_waits.find_one({}))['revision']==3


async def test_outbox_possible_submission_races_redirect_without_replay(replica_db):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True);read=await record(replica_db,True)
    sent,redirect=await asyncio.gather(ExecutionOutbox(replica_db).begin_submission(WS,intent['_id'],'negative-owner'),apply_observation(replica_db,WS,'lead',scope['_id'],read))
    current=await replica_db.outreach_intents.find_one({'_id':intent['_id']})
    assert (sent and redirect['status']=='connection_wait_review_required' and current['status']=='in_flight') or (
        not sent and redirect['status']=='connection_redirected' and current['status']=='canceled'),(sent,redirect,current)


async def test_merge_and_finished_leads_are_not_reopened(replica_db):
    await seed(replica_db,merge=True);scope=await negative(replica_db)
    await replica_db.outreach_leads.update_one({}, {'$set':{'current_node_id':'merge'}})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True)))['status']=='connection_scope_not_eligible'
    await replica_db.outreach_leads.update_one({}, {'$set':{'execution_state':'finished'}})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],None))['status']=='connection_wait_review_required'


async def test_missing_positive_branch_finishes_once_without_reopening(replica_db):
    await seed(replica_db,positive=False);scope=await negative(replica_db)
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_redirected' and result['receipt']['next_node_id'] is None
    assert (await replica_db.outreach_leads.find_one({}))['execution_state']=='finished'
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],None))['receipt']==result['receipt']

async def test_older_invite_without_any_modern_contract_retains_ordinary_wait(replica_db):
    intent=await seed(replica_db)
    await replica_db.outreach_intents.update_one({'_id':intent['_id']},{'$unset':{
        'attempt.invite_contract_version':'','attempt.provider_recipient_urn':'','attempt.provider_request_id':''}})
    assert await begin_wait(replica_db,WS,'lead') is None
    assert not await replica_db.outreach_connection_waits.count_documents({})


@pytest.mark.parametrize('fault',['recipient','invite_attempt','invite_request','start','scope_id','bool_revision','original_receipt'])
async def test_retained_scope_cannot_replace_its_original_proof(replica_db,fault):
    await seed(replica_db);scope=await negative(replica_db);request=await record(replica_db,True)
    if fault=='recipient':values={'recipient_urn':'urn:li:fsd_profile:other'}
    elif fault=='invite_attempt':values={'invite_attempt_id':'other'}
    elif fault=='invite_request':values={'invite_request_id':'other'}
    elif fault=='start':values={'wait_started_at':scope['wait_started_at']-timedelta(days=1),'wait_deadline_at':scope['wait_deadline_at']-timedelta(days=1)}
    elif fault=='bool_revision':values={'revision':True}
    elif fault=='scope_id':
        await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'connection_wait_id':'0'*64}})
        values={}
    else:
        await replica_db.outreach_physical_requests.update_one({'_id':'invite-receipt'},{'$set':{'connection_fact.recipient_urn':'urn:li:fsd_profile:other'}})
        values={}
    if values:await replica_db.outreach_connection_waits.update_one({'_id':scope['_id']},{'$set':values})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['current_node_id']=='no'


@pytest.mark.parametrize('collection,field',[('outreach_intents','node_id'),('outreach_intents','lead_id'),('outreach_intents','enrollment_id'),
    ('outreach_intents','logical_dedup_key'),('outreach_tasks','id'),('outreach_tasks','intent_id'),
    ('outreach_sequence_jobs','stamp.connection_wait_id'),('outreach_sequence_jobs','stamp.connection_wait_revision')])
async def test_array_shaped_matching_rows_hold_without_cancellation(replica_db,collection,field):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True)
    col=replica_db[collection];query={'_id':intent['_id']} if collection=='outreach_intents' else {'id':'lead:no'} if collection=='outreach_tasks' else {}
    row=await col.find_one(query);value=row
    for key in field.split('.'):value=value[key]
    await col.update_one(query,{'$set':{field:[value]}})
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_wait_review_required',result
    assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='claimed'


async def test_completed_noncommunication_predecessor_is_preserved(replica_db):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True)
    outbox=ExecutionOutbox(replica_db)
    assert await outbox.begin_submission(WS,intent['_id'],'negative-owner')
    assert await outbox.finish(WS,intent['_id'],'negative-owner','request_observed',provider_result_status='viewed')
    await replica_db.outreach_tasks.update_one({'id':'lead:no'},{'$set':{'status':'completed'}})
    await replica_db.outreach_sequence_jobs.update_one({}, {'$set':{'status':'completed'}})
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':'no2'}})
    original=await replica_db.outreach_intents.find_one({'_id':intent['_id']})
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_redirected',result
    current=await replica_db.outreach_intents.find_one({'_id':intent['_id']})
    original.pop('dispatch_fence_revision',None);current.pop('dispatch_fence_revision',None)
    assert current==original and (await replica_db.outreach_tasks.find_one({'id':'lead:no'}))['status']=='completed'


@pytest.mark.parametrize('fault',['paused','dnc','reply','permission','live','deleted','expired'])
async def test_current_stops_outrank_received_acceptance(replica_db,monkeypatch,fault):
    await seed(replica_db);scope=await negative(replica_db);request=await record(replica_db,True)
    if fault=='paused':await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'paused'}})
    elif fault in {'dnc','reply'}:await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'do_not_contact' if fault=='dnc' else 'has_replied':True}})
    elif fault=='permission':await replica_db.outreach_sender_execution.update_many({}, {'$set':{'permission.latched':True}})
    elif fault=='live':monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','false')
    elif fault=='deleted':await replica_db.outreach_campaigns.update_one({}, {'$set':{'is_deleted':True}})
    else:await replica_db.outreach_entitlements.update_many({}, {'$set':{'paid_through':datetime.now(timezone.utc)-timedelta(days=1)}})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['current_node_id']=='no'


async def test_positive_receipt_survives_worker_replacement_and_blocks_fresh_negative(replica_db):
    from outreach.core.connection_observations import saved_positive
    await seed(replica_db);scope=await negative(replica_db);saved=await record(replica_db,True)
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'execution_claim_token':'new-worker'}})
    lead=await replica_db.outreach_leads.find_one({'id':'lead'})
    assert await saved_positive(replica_db,scope,lead,datetime.now(timezone.utc))==saved
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],saved))['status']=='connection_redirected'


async def test_saved_positive_cannot_be_overwritten_by_later_negative_action_authority(replica_db):
    await seed(replica_db);scope=await negative(replica_db)
    false=await record(replica_db,False)
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],false))['status']=='connection_negative_confirmed'
    await record(replica_db,True)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});campaign=await replica_db.outreach_campaigns.find_one({})
    sequence=await load_sequence(replica_db,WS,'campaign',campaign=campaign);account=await replica_db.outreach_accounts.find_one({})
    assert await scope_guard(replica_db,lead,campaign,sequence,account)=='connection_recheck_required'


async def test_actual_scope_indexes_and_erasure_collection(replica_db):
    from db.indexes import ensure_connection_wait_indexes
    from outreach.core.erasure import DATA_COLLECTIONS
    from pymongo.errors import DuplicateKeyError
    await seed(replica_db);scope=await begin_wait(replica_db,WS,'lead')
    await ensure_connection_wait_indexes(replica_db)
    copy={**scope,'_id':'other'}
    with pytest.raises(DuplicateKeyError):await replica_db.outreach_connection_waits.insert_one(copy)
    indexes=await replica_db.outreach_connection_waits.index_information()
    assert not any('expireAfterSeconds' in value for value in indexes.values())
    assert 'outreach_connection_waits' in DATA_COLLECTIONS

async def test_saved_positive_beats_competing_false_at_deadline(replica_db):
    await seed(replica_db);scope=await begin_wait(replica_db,WS,'lead')
    positive=await record(replica_db,True);negative_read=await record(replica_db,False)
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],negative_read)
    assert result['status']=='connection_redirected' and result['receipt']['request_id']==positive


async def test_original_wait_positive_arriving_after_negative_exit_is_not_lost(replica_db):
    from outreach.core.connection_observations import saved_positive
    await seed(replica_db);scope=await begin_wait(replica_db,WS,'lead')
    read=await record(replica_db,True)
    receipt=await replica_db.outreach_physical_requests.find_one({'_id':read})
    # The GET was authorized on the original wait; its recorded fact commits
    # only after a competing false observation exits that wait.
    await replica_db.outreach_physical_requests.delete_one({'_id':read})
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,False)))['status']=='branch_advanced'
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'execution_claim_token':'replacement'}})
    await replica_db.outreach_physical_requests.insert_one(receipt)
    current=await replica_db.outreach_connection_waits.find_one({'_id':scope['_id']});lead=await replica_db.outreach_leads.find_one({'id':'lead'})
    assert await saved_positive(replica_db,current,lead,datetime.now(timezone.utc))==read
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],read))['status']=='connection_redirected'


async def test_url_only_original_cannot_authorize_new_linkedin_transport(replica_db):
    await seed(replica_db);scope=await negative(replica_db)
    request=await record(replica_db,False)
    await apply_observation(replica_db,WS,'lead',scope['_id'],request)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});campaign=await replica_db.outreach_campaigns.find_one({})
    sequence=await load_sequence(replica_db,WS,'campaign',campaign=campaign);account=await replica_db.outreach_accounts.find_one({})
    # visit_profile is the actual retained frozen step; no URL/URN enrichment.
    assert await scope_guard(replica_db,lead,campaign,sequence,account)=='original_recipient_transport_required'

async def fresh_sender(db):
    from outreach.core.inbox_freshness import PARSER_VERSION
    now=datetime.now(timezone.utc)
    await db.outreach_accounts.update_one({'id':'sender'},{'$set':{'inbox_sync':{'status':'complete','credential_generation':'original',
        'coverage_started_at':now,'completed_at':now,'parser_version':PARSER_VERSION}}})


@pytest.mark.parametrize('connected',[True,False,None])
async def test_due_recheck_runs_real_guarded_adapter_with_synthetic_http(replica_db,monkeypatch,connected):
    import httpx
    from outreach.tasks.connection_recheck import recheck_connection
    await seed(replica_db);scope=await negative(replica_db);await fresh_sender(replica_db)
    requests=[];original=httpx.AsyncClient
    async def response(request):
        requests.append(request)
        assert request.method=='GET' and request.url.path=='/voyager/api/relationships/connections'
        data={'elements':[{'profileUrn':TARGET}] if connected else [],'paging':{'start':0,'count':1000,'total':1 if connected else 0}}
        if connected is None:data={'errors':[]}
        return httpx.Response(200,json=data)
    class SyntheticClient(original):
        def __init__(self,*args,**kwargs):
            kwargs.pop('proxy',None);kwargs['transport']=httpx.MockTransport(response);super().__init__(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',SyntheticClient)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});campaign=await replica_db.outreach_campaigns.find_one({})
    sequence=await load_sequence(replica_db,WS,'campaign',campaign=campaign);account=await replica_db.outreach_accounts.find_one({})
    result=await recheck_connection(replica_db,lead,campaign,sequence,account,'visit_profile')
    assert len(requests)==1
    assert (result or {}).get('status')==('connection_redirected' if connected is True else 'connection_wait_review_required' if connected is None else None),result
    receipt=await replica_db.outreach_physical_requests.find_one({'action':'read','connection_wait_context.scope_revision':scope['revision']})
    assert receipt['dispatch_authorization']['mode']=='transaction' and receipt['connection_fact']['connected'] is connected
    assert receipt['connection_wait_context']['scope_id']==scope['_id']


async def test_original_urn_action_has_a_synchronous_connection_freshness_deadline(replica_db,monkeypatch):
    import httpx
    from outreach.core.dispatch_authority import DispatchAuthority
    from outreach.core.request_guard import RequestEnvelope,RequestDenied
    from outreach.core.proxy_custody import prepare_proxy
    from outreach.core import request_guard
    await seed(replica_db,negative_kind='like_last_post')
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'linkedin_urn':TARGET}})
    scope=await negative(replica_db);now=datetime.now(timezone.utc)
    request=await record(replica_db,False,now=now-timedelta(seconds=59))
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_negative_confirmed'
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});campaign=await replica_db.outreach_campaigns.find_one({})
    sequence=await load_sequence(replica_db,WS,'campaign',campaign=campaign);account=await replica_db.outreach_accounts.find_one({})
    assert await scope_guard(replica_db,lead,campaign,sequence,account) is None
    jumped=False;authorize=DispatchAuthority.authorize
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.now(tz)+(timedelta(seconds=2) if jumped else timedelta())
    async def later(self,*args,**kwargs):
        nonlocal jumped
        result=await authorize(self,*args,**kwargs)
        assert any(abs((value-(now+timedelta(seconds=1))).total_seconds())<.1 for value in result['deadlines'])
        jumped=True;return result
    monkeypatch.setattr(request_guard,'datetime',Clock);monkeypatch.setattr(DispatchAuthority,'authorize',later)
    proxy=await prepare_proxy(account['proxy'],WS)
    async def validate(current):return await scope_guard(current,lead,campaign,sequence,account)
    envelope=RequestEnvelope(replica_db,WS,'sender','original','sequence',proxy.url,prepared_proxy=proxy,
        authority_validator=lambda:validate(replica_db),transaction_validator=validate)
    calls=[]
    async def factory():calls.append(True);return httpx.Response(200,json={})
    with pytest.raises(RequestDenied,match='dispatch_authority_expired'):await envelope.call('GET','/voyager/api/test',factory)
    assert not calls

@pytest.mark.parametrize('contradictory',[False,True])
async def test_real_physical_completed_like_ancestor_is_retained_on_redirect(replica_db,contradictory):
    import httpx
    from outreach.core.request_guard import RequestEnvelope,request_parent
    from outreach.core.proxy_custody import prepare_proxy
    from outreach.core.sender_execution import SenderExecution
    await seed(replica_db,negative_kind='like_last_post')
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'linkedin_urn':TARGET}})
    scope=await negative(replica_db)
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,False)))['status']=='connection_negative_confirmed'
    outbox=ExecutionOutbox(replica_db)
    intent=await outbox.ensure(workspace_id=WS,campaign_id='campaign',lead_id='lead',sender_id='sender',node_id='no',action_kind='like_last_post',
        sequence_version=1,authorization_revision=1,credential_generation='original',legacy_operation_id='lead:no',enrollment_id='enrollment')
    owner='completed-like-owner'
    assert await outbox.claim(WS,intent['_id'],owner)
    assert await outbox.begin_submission(WS,intent['_id'],owner)
    guard=SenderExecution(replica_db);assert await guard.acquire(WS,'sender',owner);assert await guard.begin(WS,'sender',owner)
    account=await replica_db.outreach_accounts.find_one({'id':'sender'});proxy=await prepare_proxy(account['proxy'],WS)
    envelope=RequestEnvelope(replica_db,WS,'sender','original','sequence',proxy.url,prepared_proxy=proxy,operation_id=intent['_id'])
    async def validate(current):return None
    async def response():return httpx.Response(201,json={})
    with request_parent(owner,lambda:validate(replica_db),transaction_validator=validate):
        await envelope.call('POST','/voyager/api/feed/reactions',response,action='like')
    await guard.release(WS,'sender',owner)
    assert await outbox.finish(WS,intent['_id'],owner,'provider_accepted',provider_result_status='liked')
    await replica_db.outreach_tasks.insert_one({'id':'lead:no','workspace_id':WS,'lead_id':'lead','campaign_id':'campaign','account_id':'sender',
        'owner_token':owner,'intent_id':intent['_id'],'task_type':'like_last_post','status':'completed'})
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'current_node_id':'no2'}})
    if contradictory:await replica_db.outreach_physical_requests.update_one({'owner_token':owner},{'$set':{'http_status':500}})
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']==('connection_wait_review_required' if contradictory else 'connection_redirected'),result
    receipt=await replica_db.outreach_physical_requests.find_one({'owner_token':owner})
    assert receipt['logical_operation_id']==intent['_id'] and receipt['status']=='response_received'
    assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='executed'

async def test_default_lease_duration_stale_positive_requires_review_even_with_new_permission(replica_db):
    from outreach.core.connection_observations import saved_positive
    await seed(replica_db);scope=await negative(replica_db);request=await record(replica_db,True)
    future=datetime.now(timezone.utc)+timedelta(seconds=121)
    await ExecutionPermission(replica_db).grant(WS,'sender','original',['sequence'],'synthetic-new-permission',ttl_seconds=60,now=future)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'})
    with pytest.raises(ConnectionWaitUnavailable):await saved_positive(replica_db,scope,lead,future)
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],request,now=future)
    assert result['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['current_node_id']=='no'
    assert (await replica_db.outreach_physical_requests.find_one({'_id':request}))['connection_fact']['connected'] is True


async def test_guarded_erasure_removes_wait_and_scrubs_new_recipient_metadata_from_holds(replica_db):
    from outreach.core.erasure import OutreachErasure,_control
    await seed(replica_db);scope=await negative(replica_db);await record(replica_db,True)
    intent=await pending(replica_db,claim=True)
    await ExecutionOutbox(replica_db).begin_submission(WS,intent['_id'],'negative-owner')
    await replica_db.outreach_connection_waits.insert_one({'_id':'foreign-wait','workspace_id':'other','recipient_urn':'foreign-person'})
    for name in ('outreach_connection_waits','outreach_physical_requests','outreach_intents'):
        async def erase(current):return await OutreachErasure(replica_db)._erase_batch(current,WS,name)
        assert await _control(replica_db,WS,erase)
        assert await replica_db[name].count_documents({'workspace_id':WS})==0
    holds=await replica_db.outreach_erasure_holds.find({'workspace_id':WS}).to_list(length=100)
    assert holds and any(row['source_collection']=='outreach_intents' for row in holds)
    serialized=repr(holds)
    assert TARGET not in serialized and 'connection_fact' not in serialized and 'connection_wait_context' not in serialized
    assert await replica_db.outreach_connection_waits.count_documents({'workspace_id':'other'})==1

@pytest.mark.parametrize('fault',['deleted','target','missing_reference','wrong_time'])
async def test_negative_projection_alone_never_authorizes_next_action(replica_db,fault):
    await seed(replica_db,negative_kind='like_last_post')
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'linkedin_urn':TARGET}})
    scope=await negative(replica_db);request=await record(replica_db,False)
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],request))['status']=='connection_negative_confirmed'
    if fault=='deleted':await replica_db.outreach_physical_requests.delete_one({'_id':request})
    elif fault=='target':await replica_db.outreach_physical_requests.update_one({'_id':request},{'$set':{'connection_fact.recipient_urn':'urn:li:fsd_profile:other'}})
    elif fault=='missing_reference':await replica_db.outreach_connection_waits.update_one({'_id':scope['_id']},{'$unset':{'last_read.request_id':''}})
    else:await replica_db.outreach_connection_waits.update_one({'_id':scope['_id']},{'$set':{'last_read.observed_at':datetime.now(timezone.utc)-timedelta(seconds=5)}})
    lead=await replica_db.outreach_leads.find_one({'id':'lead'});campaign=await replica_db.outreach_campaigns.find_one({})
    sequence=await load_sequence(replica_db,WS,'campaign',campaign=campaign);account=await replica_db.outreach_accounts.find_one({})
    assert await scope_guard(replica_db,lead,campaign,sequence,account) in {'connection_recheck_required','connection_wait_review_required'}

@pytest.mark.parametrize('collection,query',[('outreach_leads',{'id':'lead'}),('outreach_campaigns',{'id':'campaign'}),('outreach_accounts',{'id':'sender'})])
@pytest.mark.parametrize('same_text_type_change',[False,True])
async def test_replacement_after_invite_before_wait_cannot_adopt_original_receipt(replica_db,collection,query,same_text_type_change):
    await seed(replica_db)
    row=await replica_db[collection].find_one(query);original_id=row.pop('_id')
    await replica_db[collection].delete_one({'_id':original_id})
    if same_text_type_change:row['_id']=str(original_id)
    await replica_db[collection].insert_one(row)
    with pytest.raises(ConnectionWaitUnavailable):await begin_wait(replica_db,WS,'lead')
    assert await replica_db.outreach_connection_waits.count_documents({})==0

@pytest.mark.parametrize('order',['fact_first','authorization_first'])
async def test_fact_publication_and_actual_negative_physical_authorization_commit_orders(replica_db,monkeypatch,order):
    import httpx
    from outreach.core.dispatch_authority import DispatchAuthority
    from outreach.core.request_guard import RequestEnvelope,RequestDenied,request_parent
    from outreach.core.proxy_custody import prepare_proxy
    from outreach.core.sender_execution import SenderExecution
    from outreach.core.connection_waits import context
    await seed(replica_db,negative_kind='like_last_post')
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'linkedin_urn':TARGET}})
    scope=await negative(replica_db)
    assert (await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,False)))['status']=='connection_negative_confirmed'
    outbox=ExecutionOutbox(replica_db)
    intent=await outbox.ensure(workspace_id=WS,campaign_id='campaign',lead_id='lead',sender_id='sender',node_id='no',action_kind='like_last_post',
        sequence_version=1,authorization_revision=1,credential_generation='original',legacy_operation_id='lead:no',enrollment_id='enrollment')
    owner='negative-owner';assert await outbox.claim(WS,intent['_id'],owner);assert await outbox.begin_submission(WS,intent['_id'],owner)
    await replica_db.outreach_tasks.insert_one({'workspace_id':WS,'id':'lead:no','lead_id':'lead','campaign_id':'campaign',
        'account_id':'sender','intent_id':intent['_id'],'owner_token':owner,'task_type':'like_last_post','status':'dispatching'})
    positive=await record(replica_db,True)
    received=await replica_db.outreach_physical_requests.find_one({'_id':positive})
    await replica_db.outreach_physical_requests.update_one({'_id':positive},{'$unset':{'connection_fact':''}})
    account=await replica_db.outreach_accounts.find_one({'id':'sender'});proxy=await prepare_proxy(account['proxy'],WS)
    read_envelope=RequestEnvelope(replica_db,WS,'sender','original','sequence',proxy.url,prepared_proxy=proxy)
    read_envelope.received_receipt=received
    guard=SenderExecution(replica_db);assert await guard.acquire(WS,'sender',owner);assert await guard.begin(WS,'sender',owner)
    async def validate(current):
        lead,campaign,sequence,sender=await context(current,WS,'lead')
        return await scope_guard(current,lead,campaign,sequence,sender)
    envelope=RequestEnvelope(replica_db,WS,'sender','original','sequence',proxy.url,prepared_proxy=proxy,operation_id=intent['_id'])
    entered,release=asyncio.Event(),asyncio.Event();authorize=DispatchAuthority.authorize
    async def pause(self,*args,**kwargs):
        if order=='fact_first':entered.set();await release.wait();return await authorize(self,*args,**kwargs)
        result=await authorize(self,*args,**kwargs);entered.set();await release.wait();return result
    monkeypatch.setattr(DispatchAuthority,'authorize',pause)
    calls=[]
    async def response():calls.append(True);return httpx.Response(201,json={})
    async def dispatch():
        with request_parent(owner,lambda:validate(replica_db),transaction_validator=validate):
            return await envelope.call('POST','/voyager/api/feed/reactions',response,action='like')
    task=asyncio.create_task(dispatch())
    try:
        await asyncio.wait_for(entered.wait(),5)
        assert await read_envelope.record_connection_fact(TARGET,kind='observed_connection',connected=True)==positive
        release.set()
        if order=='fact_first':
            with pytest.raises(RequestDenied):await asyncio.wait_for(task,5)
            assert not calls
            assert await outbox.abort_before_call(WS,intent['_id'],owner,'connection_recheck_required')
            await replica_db.outreach_tasks.update_one({'id':'lead:no'},{'$set':{'status':'not_submitted'}})
        else:
            await asyncio.wait_for(task,5);assert len(calls)==1
            assert await outbox.finish(WS,intent['_id'],owner,'provider_accepted',provider_result_status='liked')
            await replica_db.outreach_tasks.update_one({'id':'lead:no'},{'$set':{'status':'completed'}})
        await guard.release(WS,'sender',owner)
        result=await apply_observation(replica_db,WS,'lead',scope['_id'],positive)
        assert result['status']==('connection_redirected' if order=='fact_first' else 'connection_wait_review_required'),result
        physical=await replica_db.outreach_physical_requests.find_one({'owner_token':owner,'mutation':True})
        assert physical['status']==('not_submitted' if order=='fact_first' else 'response_received')
        if order=='authorization_first':assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='executed'
    finally:
        release.set()
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)

async def test_actual_invite_worker_creates_original_scope_from_its_transaction_receipt(replica_db,monkeypatch):
    import httpx
    from outreach.core.content_approval import ContentApproval,sequence_binding
    from outreach.tasks import sequence_dispatch
    await seed(replica_db,expired=False)
    await replica_db.outreach_intents.delete_many({});await replica_db.outreach_physical_requests.delete_many({})
    await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'linkedin_urn':TARGET}})
    approval=ContentApproval(replica_db);binding=await sequence_binding(replica_db,WS,'lead')
    review=await approval.ensure(binding)
    await approval.decide(WS,review['_id'],'synthetic-reviewer','approve',revision=review['revision'])
    original=httpx.AsyncClient;requests=[]
    async def response(request):
        requests.append(request)
        assert request.method=='POST' and request.url.path=='/voyager/api/growth/normInvitations'
        return httpx.Response(201,json={})
    class SyntheticClient(original):
        def __init__(self,*args,**kwargs):
            kwargs.pop('proxy',None);kwargs['transport']=httpx.MockTransport(response);super().__init__(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',SyntheticClient)
    assert (await sequence_dispatch.prepare_due(replica_db))['prepared']==1
    job=await replica_db.outreach_sequence_jobs.find_one({})
    result=await sequence_dispatch.execute_job(replica_db,WS,job['_id'])
    assert result['status']=='success',result
    scope=await replica_db.outreach_connection_waits.find_one({})
    assert scope['recipient_urn']==TARGET and len(requests)==1
    physical=await replica_db.outreach_physical_requests.find_one({'action':'invite'})
    assert scope['invite_request_id']==physical['_id'] and physical['logical_operation_id']==job['intent_id']
    assert len(physical['dispatch_authorization']['authority_refs'])>=3
    assert scope['wait_started_at']==(await replica_db.outreach_intents.find_one({'_id':job['intent_id']}))['attempt']['completed_at']

@pytest.mark.parametrize('history',[None,[{'status':'unknown_outcome'}],[{'status':'response_received'}],[None],False])
async def test_unknown_or_malformed_physical_noncall_history_cannot_be_discarded(replica_db,history):
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True)
    await replica_db.outreach_physical_requests.insert_one({'workspace_id':WS,'sender_id':'sender','source':'sequence',
        'owner_token':'negative-owner','mutation':True,'status':'not_submitted','logical_operation_id':intent['_id'],
        'non_call_history':history})
    result=await apply_observation(replica_db,WS,'lead',scope['_id'],await record(replica_db,True))
    assert result['status']=='connection_wait_review_required'
    assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='claimed'


async def test_standalone_cannot_create_original_wait_without_transaction(replica_db,tmp_path):
    import shutil,socket,subprocess
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import PyMongoError
    from outreach.core.suppression import SuppressionUnavailable
    await seed(replica_db)
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    process=subprocess.Popen([shutil.which('mongod'),'--dbpath',str(tmp_path),'--bind_ip','127.0.0.1','--port',str(port),
        '--nounixsocket','--logpath',str(tmp_path/'mongo.log'),'--setParameter','diagnosticDataCollectionEnabled=false'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}',tz_aware=True,serverSelectionTimeoutMS=200)
    db=client['test_owned_standalone_'+uuid.uuid4().hex]
    try:
        async with asyncio.timeout(10):
            while True:
                try:await client.admin.command('ping');break
                except PyMongoError:await asyncio.sleep(.05)
        for name in await replica_db.list_collection_names():
            rows=await replica_db[name].find({}).to_list(length=100)
            if rows:await db[name].insert_many(rows)
        with pytest.raises(SuppressionUnavailable):await begin_wait(db,WS,'lead')
        assert not await db.outreach_connection_waits.count_documents({})
        assert not (await db.outreach_leads.find_one({'id':'lead'})).get('connection_wait_required')
    finally:
        await client.drop_database(db.name);client.close()
        if process.poll() is None:process.terminate()
        await asyncio.to_thread(process.wait,5)

@pytest.mark.parametrize('with_positive',[False,True])
async def test_recorded_positive_prevents_actual_email_condition_from_escaping_to_shared_join(replica_db,monkeypatch,with_positive):
    import httpx
    from outreach.tasks import sequence_dispatch,sequence_executor
    from outreach.core.request_guard import RequestEnvelope
    from outreach.core.proxy_custody import prepare_proxy
    await seed(replica_db)
    nodes=[{'id':'invite','type':'connection_request','config':{'timeout_days':1}},
        {'id':'no','type':'if_email_available'},{'id':'yes','type':'visit_profile','delay_hours':24},{'id':'merge','type':'visit_profile'}]
    edges=[{'source':'invite','target':'yes','label':'accepted'},{'source':'invite','target':'no','label':'not accepted'},
        {'source':'no','target':'merge','label':'email unavailable'},{'source':'yes','target':'merge'}]
    compiled=DAGCompiler.validate_and_compile(nodes,edges)
    await replica_db.outreach_sequence_versions.update_one({'_id':'version'},{'$set':{'nodes':nodes,'edges':edges,'compiled_dag':compiled}})
    scope=await negative(replica_db);await fresh_sender(replica_db)
    original_client=httpx.AsyncClient;requests=[]
    async def response(request):
        requests.append(request);assert request.method=='GET'
        return httpx.Response(200,json={'elements':[],'paging':{'start':0,'count':1000,'total':0}})
    class SyntheticClient(original_client):
        def __init__(self,*args,**kwargs):
            kwargs.pop('proxy',None);kwargs['transport']=httpx.MockTransport(response);super().__init__(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',SyntheticClient)
    advance=sequence_executor._advance_lead;published=[]
    async def before_advance(db,lead,updates,**kwargs):
        if not with_positive:return await advance(db,lead,updates,**kwargs)
        positive=await record(db,True);received=await db.outreach_physical_requests.find_one({'_id':positive})
        await db.outreach_physical_requests.update_one({'_id':positive},{'$unset':{'connection_fact':''}})
        account=await db.outreach_accounts.find_one({'id':'sender'});proxy=await prepare_proxy(account['proxy'],WS)
        envelope=RequestEnvelope(db,WS,'sender','original','sequence',proxy.url,prepared_proxy=proxy)
        envelope.received_receipt=received
        published.append(await envelope.record_connection_fact(TARGET,kind='observed_connection',connected=True))
        return await advance(db,lead,updates,**kwargs)
    monkeypatch.setattr(sequence_executor,'_advance_lead',before_advance)
    assert (await sequence_dispatch.prepare_due(replica_db))['prepared']==1
    job=await replica_db.outreach_sequence_jobs.find_one({})
    result=await sequence_dispatch.execute_job(replica_db,WS,job['_id'])
    assert result['status']==('lead_changed' if with_positive else 'branch_advanced') and len(published)==int(with_positive) and len(requests)==1,result
    lead=await replica_db.outreach_leads.find_one({'id':'lead'})
    retained=await replica_db.outreach_connection_waits.find_one({'_id':scope['_id']})
    assert lead['current_node_id']==('yes' if with_positive else 'merge')
    if with_positive:assert retained['redirect_receipt']['request_id']==published[0]
    assert (await replica_db.outreach_sequence_jobs.find_one({'_id':job['_id']}))['status']==('superseded' if with_positive else 'completed')

async def test_nested_positive_redirect_failure_rolls_back_all_cancellation_and_scope_writes(replica_db,monkeypatch):
    from types import SimpleNamespace
    from outreach.core.dispatch_authority import AuthorityCollection
    from outreach.tasks.sequence_executor import _advance_lead
    await seed(replica_db);scope=await negative(replica_db);intent=await pending(replica_db,claim=True)
    await record(replica_db,True)
    lead=await replica_db.outreach_leads.find_one({'id':'lead'})
    originals={name:await replica_db[name].find({}).to_list(length=100) for name in
        ('outreach_leads','outreach_intents','outreach_tasks','outreach_sequence_jobs','outreach_connection_waits')}
    update=AuthorityCollection.update_one
    async def lose_lead_cas(self,query,changes,**kwargs):
        if self.name=='outreach_leads' and 'connection_wait_revision' in changes.get('$set',{}):return SimpleNamespace(matched_count=0)
        return await update(self,query,changes,**kwargs)
    monkeypatch.setattr(AuthorityCollection,'update_one',lose_lead_cas)
    assert await _advance_lead(replica_db,lead,{'current_node_id':'no2','execution_state':'queued'}) is False
    for name,before in originals.items():assert await replica_db[name].find({}).to_list(length=100)==before,name
    assert (await replica_db.outreach_intents.find_one({'_id':intent['_id']}))['status']=='claimed'

async def test_every_new_invite_attempt_has_contract_even_without_result_metadata(replica_db):
    await seed(replica_db)
    await replica_db.outreach_intents.delete_many({})
    outbox=ExecutionOutbox(replica_db)
    intent=await outbox.ensure(workspace_id=WS,campaign_id='campaign',lead_id='lead',sender_id='sender',node_id='invite',action_kind='connection_request',
        sequence_version=1,authorization_revision=1,credential_generation='original',legacy_operation_id='lead:invite',enrollment_id='enrollment')
    assert await outbox.claim(WS,intent['_id'],'new-invite-owner')
    assert await outbox.begin_submission(WS,intent['_id'],'new-invite-owner')
    possible=await replica_db.outreach_intents.find_one({'_id':intent['_id']})
    assert possible['attempt']['invite_contract_version']==1
    assert await outbox.finish(WS,intent['_id'],'new-invite-owner','provider_accepted',provider_result_status='invite_sent')
    with pytest.raises(ConnectionWaitUnavailable):await begin_wait(replica_db,WS,'lead')
    assert not await replica_db.outreach_connection_waits.count_documents({})
