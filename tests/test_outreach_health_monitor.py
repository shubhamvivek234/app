"""Evidence-based renewal never turns a status label into health permission."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from outreach.core import health_monitor as health, erasure
from outreach.core.authorization import canonical_hash
from outreach.core.execution_permission import ExecutionPermission
from tests.outreach_memory import Database

pytestmark = pytest.mark.asyncio
EVIDENCE = 'a'*64


@pytest.fixture
def healthy_db(monkeypatch):
    monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','true')
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH','false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    stamp = health.now()
    proxy = {'proxy_id':'asset','provider':'iproyal_static','host':'8.8.8.8','port':80,
        'username':'private-user','password_enc':'gAAAAA-private','country_code':'US'}
    account = {'_id':'account','id':'sender','workspace_id':'w','status':'active','country_code':'US',
        'credential_generation':'generation','linkedin_urn':'urn:li:member:1','session_cookie_enc':'gAAAAA-cookie',
        'jsession_id':'gAAAAA-jsession',
        'proxy':proxy,'connection_finalization':{'job_id':'job','generation':'generation','owner_token':'install-owner',
        'state':'closed','completion':'verified_install','ever_installed':True}}
    from outreach.core.connection_repair import installed_digest
    account['connection_finalization'].update(expected_linkedin_urn=account['linkedin_urn'],
        installed_credential_digest=installed_digest(account))
    evidence = health.connection_evidence('job','generation',account,stamp)
    account['execution_health'] = evidence
    permission = {'credential_generation':'generation','sources':['sequence','sync'],'latched':False,
        'operator':'original-operator','issued_at':stamp,'expires_at':stamp+timedelta(seconds=60),'stop_reason':None}
    return Database(outreach_accounts=[account], outreach_entitlements=[{'_id':'paid','workspace_id':'w','status':'active',
        'seats':1,'payment_source':'manual_verified_invoice','paid_through':stamp+timedelta(days=1)}],
        outreach_sender_execution=[{**ExecutionPermission.scope('w','sender'),'status':'idle',
            'permission_revision':3,'permission':permission}],
        outreach_connection_jobs=[{'_id':'connection','workspace_id':'w','id':'job','sender_id':'sender','status':'completed',
            'credential_generation':'generation','expected_linkedin_urn':account['linkedin_urn']}],
        outreach_physical_requests=[{'_id':'read','workspace_id':'w','sender_id':'sender','credential_generation':'pending:job',
            'source':'verify','action':'read','mutation':False,'status':'response_received','http_status':200,
            'completed_at':stamp,'dispatch_authorization':{'mode':'transaction'}}],
        outreach_proxy_inventory=[{'_id':'asset','workspace_id':'w','last_workspace_id':'w','status':'available',
            'provider':'iproyal_static','host':proxy['host'],'port':80,'username':proxy['username'],
            'password_enc':proxy['password_enc'],'country_code':'US','expires_at':stamp+timedelta(days=1)}],
        outreach_proxy_leases=[{'_id':'asset','workspace_id':'w','sender_id':'sender','country_code':'US'}],
        outreach_sender_slots=[{'_id':'slot','workspace_id':'w','sender_id':'sender'}],
        outreach_campaigns=[{'_id':'campaign','workspace_id':'w','status':'active','sender_account_ids':['sender'],
            'authorization_revision':1,'auto_launch_enabled':True}])


async def arm(db, view=None, **changes):
    service = health.HealthMonitor(db)
    view = view or await service.inspect('w','sender')
    return await service.arm('w','sender','operator',EVIDENCE,view['digest'],
        window_seconds=changes.get('window',300))


async def test_arm_does_not_grant_and_tick_caps_every_deadline(healthy_db):
    db=healthy_db; original=deepcopy(db.outreach_sender_execution.docs[0]); view=await health.HealthMonitor(db).inspect('w','sender')
    assert not view['blockers'] and 'cookie' not in str(view) and 'private-user' not in str(view)
    control=await arm(db,view)
    assert db.outreach_sender_execution.docs[0]==original
    result=await health.HealthMonitor(db).tick('w',control['control_id'])
    assert result['status']=='renewed' and not result['campaigns_resumed']
    current=db.outreach_sender_execution.docs[0]; permission=current['permission']
    assert current['permission_revision']==4 and permission['sources']==['sequence','sync']
    assert permission['health_control_id']==control['control_id'] and not permission['latched']
    assert 0<(permission['expires_at']-permission['issued_at']).total_seconds()<=60
    assert permission['expires_at']<=db.outreach_accounts.docs[0]['execution_health']['observed_at']+timedelta(seconds=90)
    assert await ExecutionPermission(db).allowed('w','sender','generation','sequence')
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='not_due'
    assert current['permission_revision']==4


@pytest.mark.parametrize('fault',['no_evidence','stale','future','label_only','resource','generation','receipt',
    'mock','paid','proxy','lease','slot','latched','source','owner','unknown','finalizing','manual','closed','gate','window'])
async def test_missing_or_unproven_authority_cannot_arm(healthy_db, monkeypatch, fault):
    db=healthy_db; account=db.outreach_accounts.docs[0]; state=db.outreach_sender_execution.docs[0]
    if fault in {'no_evidence','label_only'}:
        account.pop('execution_health');account['session_health_status']='healthy';account['last_health_check']=health.now()
    if fault=='stale':account['execution_health']['observed_at']-=timedelta(minutes=3)
    if fault=='future':account['execution_health']['observed_at']+=timedelta(minutes=1)
    if fault=='resource':account['proxy']['password_enc']='replacement'
    if fault=='generation':account['credential_generation']='replacement'
    if fault=='receipt':db.outreach_physical_requests.docs.clear()
    if fault=='mock':monkeypatch.setenv('OUTREACH_MOCK_AUTH','true')
    if fault=='paid':db.outreach_entitlements.docs.clear()
    if fault=='proxy':db.outreach_proxy_inventory.docs[0]['expires_at']=health.now()-timedelta(seconds=1)
    if fault=='lease':db.outreach_proxy_leases.docs.clear()
    if fault=='slot':db.outreach_sender_slots.docs.clear()
    if fault=='latched':state['permission']['latched']=True
    if fault=='source':state['permission']['sources']=['email_send']
    if fault=='owner':state.update(status='in_flight',owner_token='physical-owner',physical_request_token='token')
    if fault=='unknown':db.outreach_physical_requests.docs.append({'_id':'unknown','workspace_id':'w','sender_id':'sender','status':'unknown_outcome','mutation':True})
    if fault=='finalizing':db.outreach_connection_jobs.docs[0]['status']='finalizing'
    if fault=='manual':db.outreach_manual_actions.docs.append({'_id':'manual','workspace_id':'w','account_id':'sender','status':'unknown_outcome'})
    if fault=='closed':monkeypatch.setattr(erasure,'workspace_is_open',AsyncMock(return_value=False))
    if fault=='gate':monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
    with pytest.raises(ValueError):await arm(db,window=901 if fault=='window' else 300)
    assert not db.outreach_health_controls.docs


@pytest.mark.parametrize('fault',['stale','flag','paid','challenge','unknown'])
async def test_monitor_stop_preserves_tokens_and_never_resumes(healthy_db,monkeypatch,fault):
    db=healthy_db; control=await arm(db); state=db.outreach_sender_execution.docs[0]
    if fault=='stale':db.outreach_accounts.docs[0]['execution_health']['observed_at']-=timedelta(minutes=3)
    if fault=='flag':monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
    if fault=='paid':db.outreach_entitlements.docs.clear()
    if fault=='challenge':db.outreach_accounts.docs[0].update(status='checkpoint_detected',stop_reason='checkpoint_captcha')
    if fault=='unknown':state.update(status='in_flight',owner_token='unknown-owner',physical_request_token='unknown-token',expires_at=health.now()-timedelta(seconds=1))
    result=await health.HealthMonitor(db).tick('w',control['control_id'])
    assert result['status']=='stopped' and state['permission']['latched']
    assert db.outreach_campaigns.docs[0]['status']=='paused'
    if fault=='unknown':assert state['physical_request_token']=='unknown-token' and state['owner_token']=='unknown-owner'
    assert not await ExecutionPermission(db).allowed('w','sender','generation','sequence')
    db.outreach_accounts.docs[0]['execution_health']['observed_at']=health.now()
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='stopped'


@pytest.mark.parametrize('replacement',['generation','permission'])
async def test_old_control_cannot_stop_or_renew_replacement(healthy_db,replacement):
    db=healthy_db; control=await arm(db); state=db.outreach_sender_execution.docs[0]
    if replacement=='generation':db.outreach_accounts.docs[0]['credential_generation']='replacement'
    else:state['permission_revision']+=1
    original=deepcopy(state)
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='obsolete'
    assert state==original and db.outreach_campaigns.docs[0]['status']=='active'


async def test_live_owner_defers_without_clearing_or_extending(healthy_db):
    db=healthy_db; control=await arm(db); state=db.outreach_sender_execution.docs[0]
    state.update(status='in_flight',owner_token='live-owner',physical_request_token='live-token',expires_at=health.now()+timedelta(seconds=30))
    original=deepcopy(state)
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='busy'
    assert state==original


async def test_control_stop_and_gate_disable_immediately_deny_allowed(healthy_db,monkeypatch):
    db=healthy_db; control=await arm(db); await health.HealthMonitor(db).tick('w',control['control_id'])
    monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
    assert not await ExecutionPermission(db).allowed('w','sender','generation','sequence')
    monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','true')
    await health.HealthMonitor(db).stop('w',control['control_id'],'operator',EVIDENCE)
    assert not await ExecutionPermission(db).allowed('w','sender','generation','sequence')


async def test_saved_arm_is_historical_and_stale_inspection_is_rejected(healthy_db):
    db=healthy_db; view=await health.HealthMonitor(db).inspect('w','sender'); result=await arm(db,view)
    await health.HealthMonitor(db).stop('w',result['control_id'],'operator',EVIDENCE)
    assert (await arm(db,view))['status']=='stopped' and db.outreach_sender_execution.docs[0]['permission']['latched']
    fresh=await health.HealthMonitor(db).inspect('w','sender')
    db.outreach_sender_execution.docs[0]['permission_revision']+=1
    with pytest.raises(ValueError):await arm(db,fresh)


@pytest.mark.parametrize('field',['paid','proxy','window','health'])
async def test_renewal_never_outlives_captured_deadline(healthy_db, field):
    db=healthy_db; stamp=health.now(); deadline=stamp+timedelta(seconds=8)
    if field=='paid':db.outreach_entitlements.docs[0]['paid_through']=deadline
    if field=='proxy':db.outreach_proxy_inventory.docs[0]['expires_at']=deadline
    if field=='health':db.outreach_accounts.docs[0]['execution_health']['observed_at']=deadline-timedelta(seconds=90)
    if field=='health':db.outreach_physical_requests.docs[0]['completed_at']=deadline-timedelta(seconds=90)
    control=await arm(db,window=8 if field=='window' else 300)
    await health.HealthMonitor(db).tick('w',control['control_id'])
    assert db.outreach_sender_execution.docs[0]['permission']['expires_at']<=deadline+timedelta(seconds=1)


@pytest.mark.parametrize('fault',['credential_digest','fence_identity','missing_cookie','missing_jsession',
    'receipt_mock','receipt_status','receipt_time','lease_country','task','intent','orphan_physical','capacity'])
async def test_additional_original_proof_and_hold_failures_deny(healthy_db,fault):
    db=healthy_db; account=db.outreach_accounts.docs[0]
    if fault=='credential_digest':account['connection_finalization']['installed_credential_digest']='b'*64
    if fault=='fence_identity':account['connection_finalization']['expected_linkedin_urn']='other'
    if fault=='missing_cookie':account.pop('session_cookie_enc')
    if fault=='missing_jsession':account.pop('jsession_id')
    if fault=='receipt_mock':db.outreach_physical_requests.docs[0]['dispatch_authorization']['mode']='mock'
    if fault=='receipt_status':db.outreach_physical_requests.docs[0]['http_status']=403
    if fault=='receipt_time':db.outreach_physical_requests.docs[0]['completed_at']-=timedelta(seconds=20)
    if fault=='lease_country':db.outreach_proxy_leases.docs[0]['country_code']='IN'
    if fault=='task':db.outreach_tasks.docs.append({'_id':'held','workspace_id':'w','account_id':'sender','status':'uncertain'})
    if fault=='intent':db.outreach_intents.docs.append({'_id':'held','workspace_id':'w','sender_id':'sender','status':'unknown_outcome'})
    if fault=='orphan_physical':db.outreach_physical_requests.docs.append({'_id':'held','workspace_id':'w','sender_id':'sender','status':'in_flight'})
    if fault=='capacity':db.outreach_campaigns.docs.extend([{'_id':str(i),'workspace_id':'w','status':'active','sender_account_ids':['sender']} for i in range(101)])
    with pytest.raises(ValueError):await arm(db)


@pytest.mark.parametrize('field',['sources','credential_generation'])
async def test_explicit_stop_preserves_changed_permission_identity(healthy_db,field):
    db=healthy_db; control=await arm(db); state=db.outreach_sender_execution.docs[0]
    state['permission'][field]=['search'] if field=='sources' else 'replacement'
    original=deepcopy(state)
    assert (await health.HealthMonitor(db).stop('w',control['control_id'],'operator',EVIDENCE))['status']=='obsolete'
    assert state==original


async def test_current_inflight_receipt_defers_but_orphan_stops(healthy_db):
    db=healthy_db; control=await arm(db); state=db.outreach_sender_execution.docs[0]
    state.update(status='in_flight',owner_token='owner',physical_request_token='call',expires_at=health.now()+timedelta(seconds=40))
    db.outreach_physical_requests.docs.append({'_id':'call','workspace_id':'w','sender_id':'sender','status':'in_flight','owner_token':'owner'})
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='busy'
    db.outreach_physical_requests.docs[-1]['owner_token']='different'
    assert (await health.HealthMonitor(db).tick('w',control['control_id']))['status']=='stopped'
    assert state['physical_request_token']=='call'


async def test_due_scan_backs_off_failed_roots_without_private_errors(healthy_db,monkeypatch,caplog):
    db=healthy_db; control=await arm(db); service=health.HealthMonitor(db)
    monkeypatch.setattr(service,'tick',AsyncMock(side_effect=ValueError('private-cookie')))
    assert await service.sweep()=={'processed':0,'failed':1}
    root=db.outreach_health_controls.docs[0]
    assert root['next_check_at']>health.now() and root['scan_error']=='review_required'
    assert 'private-cookie' not in caplog.text
    with pytest.raises(ValueError):await service.sweep(limit=101)


async def test_task_is_reference_only_and_shutdown_does_not_open_database(monkeypatch):
    from celery_workers.tasks import outreach as worker
    assert worker.celery_app.conf.beat_schedule['monitor-verified-sender-health']['schedule']==30
    monkeypatch.setattr(worker,'is_shutting_down',lambda:True)
    opening=AsyncMock();monkeypatch.setattr(worker,'_inbox_db',opening)
    assert await worker._monitor_sender_health()=={'status':'shutting_down'}
    opening.assert_not_awaited()
    monkeypatch.setattr(worker,'is_shutting_down',lambda:False)
    scan=AsyncMock(return_value={'processed':0,'failed':0})
    monkeypatch.setattr(health.HealthMonitor,'sweep',scan)
    assert await worker._monitor_sender_health(db=object())=={'processed':0,'failed':0}
    monkeypatch.setattr(worker,'run_async',lambda coro:(coro.close(),{'processed':0})[1])
    assert worker.monitor_sender_health()=={'processed':0}


async def test_flag_revocation_during_root_lookup_denies(healthy_db,monkeypatch):
    db=healthy_db; control=await arm(db);await health.HealthMonitor(db).tick('w',control['control_id'])
    original=db.outreach_health_controls.find_one
    async def changed(*args,**kwargs):
        result=await original(*args,**kwargs)
        monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
        return result
    monkeypatch.setattr(db.outreach_health_controls,'find_one',changed)
    assert not await ExecutionPermission(db).allowed('w','sender','generation','sequence')


async def test_normal_worker_installs_generation_bound_evidence_without_grant(monkeypatch):
    from celery_workers.tasks import outreach as worker
    from tests.test_outreach_connection_worker import make_db
    db=make_db();monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH','false');monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    observed=health.now();monkeypatch.setattr(worker,'health_now',lambda:observed)
    monkeypatch.setattr(worker.JITProxyManager,'test_proxy_health',AsyncMock(return_value=True))
    monkeypatch.setattr(worker.SessionAuthenticator,'validate_session_cookie',AsyncMock(return_value={'linkedin_urn':'urn:li:person:one'}))
    monkeypatch.setattr(worker.ExecutionPermission,'allowed',AsyncMock(return_value=True))
    assert (await worker._verify_sender_connection('job-1','ws-1','local',db=db))['status']=='completed'
    account=db.outreach_accounts.docs[0];evidence=account['execution_health']
    assert evidence['job_id']=='job-1' and evidence['credential_generation']==account['credential_generation']
    assert evidence['binding_digest']==health.binding(account) and evidence['observed_at']==observed
    assert not db.outreach_health_controls.docs and not db.outreach_sender_execution.docs


async def test_failed_prefix_does_not_starve_later_due_control(healthy_db,monkeypatch):
    db=healthy_db;control=await arm(db);original=db.outreach_health_controls.docs[0]
    later={**deepcopy(original),'_id':'f'*64,'next_check_at':original['next_check_at']+timedelta(milliseconds=1)}
    db.outreach_health_controls.docs.append(later)
    monkeypatch.setattr(health,'now',lambda:later['next_check_at']+timedelta(milliseconds=1))
    service=health.HealthMonitor(db)
    async def tick(workspace,key):
        if key==control['control_id']:raise ValueError('closed workspace')
        await db.outreach_health_controls.update_one({'_id':key,'workspace_id':workspace},{'$set':{'status':'stopped'}})
    monkeypatch.setattr(service,'tick',tick)
    assert (await service.sweep(limit=1))['failed']==1
    assert (await service.sweep(limit=1))['processed']==1
    assert later['status']=='stopped'
