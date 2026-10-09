"""Outside-backup identity denies restored authorization, without provider calls."""
from copy import deepcopy
from datetime import timedelta
import pytest
from outreach.core import restore_epoch as epoch
from outreach.core.execution_permission import ExecutionPermission
from tests.outreach_memory import Database

pytestmark=[pytest.mark.asyncio,pytest.mark.restore_epoch]
FLAGS=('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_INTEGRATIONS_ENABLED','OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED','OUTREACH_HEALTH_MONITOR_ENABLED')
ANCHOR='a'*64
EVIDENCE='b'*64

@pytest.fixture
def restored_db(monkeypatch):
    for flag in FLAGS:monkeypatch.setenv(flag,'false')
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','true');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
    return Database(outreach_sender_execution=[{**ExecutionPermission.scope('w','sender'),'status':'held',
        'physical_request_token':'unknown-token','owner_token':'unknown-owner','permission_revision':3,
        'permission':{'credential_generation':'g','sources':['sequence'],'latched':False}}],
        outreach_campaigns=[{'_id':'campaign','workspace_id':'w','status':'active','authorization_revision':2,'auto_launch_enabled':True}],
        outreach_manual_actions=[{'_id':'queued','workspace_id':'w','status':'awaiting_approval','stages':{'reply':{'status':'pending'}}},
            {'_id':'unknown','workspace_id':'w','status':'unknown_outcome','owner':'original-owner','receipt':{'accepted_at':epoch.now()}}],
        outreach_health_controls=[{'_id':'control','workspace_id':'w','status':'armed'}],
        outreach_mailboxes=[{'_id':'mailbox','workspace_id':'w','status':'active','refresh_state':'unknown','refresh_token_enc':'retained'}],
        outreach_voices=[{'_id':'voice','workspace_id':'w','status':'consent_revoked','consent':{'asserted':False},'revision':3}],
        outreach_webhooks=[{'_id':'hook','workspace_id':'w','active':True}],
        outreach_physical_requests=[{'_id':'receipt','workspace_id':'w','status':'unknown_outcome','mutation':True}])

async def prepare(db,view=None):
    service=epoch.RestoreEpoch(db);view=view or await service.inspect('w')
    return await service.prepare('w','operator',EVIDENCE,view['digest'],workers_drained=True)

async def test_prepare_stops_preserves_uncertainty_and_retries_without_restopping(restored_db):
    db=restored_db;view=await epoch.RestoreEpoch(db).inspect('w');unknown=deepcopy(db.outreach_manual_actions.docs[1])
    result=await prepare(db,view)
    assert result['prepared'] and not result['activation_allowed']
    state=db.outreach_sender_execution.docs[0]
    assert state['physical_request_token']=='unknown-token' and state['owner_token']=='unknown-owner' and state['permission']['latched']
    assert db.outreach_campaigns.docs[0]['status']=='paused' and not db.outreach_webhooks.docs[0]['active']
    assert db.outreach_manual_actions.docs[0]['status']=='cancelled' and db.outreach_manual_actions.docs[1]==unknown
    assert db.outreach_mailboxes.docs[0]['refresh_state']=='unknown' and db.outreach_mailboxes.docs[0]['refresh_token_enc']=='retained'
    assert db.outreach_voices.docs[0]['status']=='consent_revoked' and db.outreach_voices.docs[0]['consent']=={'asserted':False}
    before=deepcopy(state);assert (await prepare(db,view))['prepared'];assert state==before
    proof=await epoch.require(db,'w');assert proof.live() and proof.fields()['execution_epoch']==proof.digest

@pytest.mark.parametrize('fault',['missing_root','different_anchor','disabled','blank_anchor','malformed_anchor','malformed_flag','missing_journal','changed_journal','wrong_workspace'])
async def test_restored_or_malformed_authority_denies(restored_db,monkeypatch,fault):
    db=restored_db;await prepare(db)
    if fault=='missing_root':db.outreach_execution_epochs.docs=[row for row in db.outreach_execution_epochs.docs if row['kind']!='root']
    if fault=='different_anchor':monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','c'*64)
    if fault=='disabled':monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false')
    if fault=='blank_anchor':monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    if fault=='malformed_anchor':monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','invalid')
    if fault=='malformed_flag':monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','yes')
    if fault=='missing_journal':db.outreach_execution_epochs.docs=[row for row in db.outreach_execution_epochs.docs if row['kind']!='journal']
    if fault=='changed_journal':next(row for row in db.outreach_execution_epochs.docs if row['kind']=='journal')['after_digest']='d'*64
    with pytest.raises(epoch.EpochUnavailable):await epoch.require(db,'other' if fault=='wrong_workspace' else 'w')

async def test_anchor_without_flag_or_root_is_sticky_deny(monkeypatch):
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
    with pytest.raises(epoch.EpochUnavailable):await epoch.require(Database(),'w')

async def test_legacy_compatibility_requires_no_root_anchor_or_stamp(monkeypatch):
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH',raising=False)
    db=Database();proof=await epoch.require(db,'w');assert proof.fields()=={} and proof.live()
    with pytest.raises(epoch.EpochUnavailable):await epoch.require(db,'w',record={'execution_epoch':'d'*64})

async def test_old_jobs_cannot_be_relabelled_by_new_permission_or_proof(restored_db):
    db=restored_db;await prepare(db);proof=await epoch.require(db,'w')
    for row in ({},{'execution_epoch':'c'*64}):
        with pytest.raises(epoch.EpochUnavailable):await epoch.require(db,'w',record=row)
    assert (await epoch.require(db,'w',record=proof.fields())).live()

@pytest.mark.parametrize('fault',['flag','drain','digest','operator','capacity','changed_snapshot'])
async def test_invalid_prepare_does_not_stop_or_create_root(restored_db,monkeypatch,fault):
    db=restored_db;view=await epoch.RestoreEpoch(db).inspect('w')
    if fault=='flag':monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','true')
    if fault=='capacity':db.outreach_campaigns.docs.extend([{'_id':str(i),'workspace_id':'w','status':'active'} for i in range(101)])
    if fault=='changed_snapshot':db.outreach_campaigns.docs[0]['authorization_revision']+=1
    with pytest.raises(ValueError):await epoch.RestoreEpoch(db).prepare('w','' if fault=='operator' else 'operator',EVIDENCE,
        'invalid' if fault=='digest' else view['digest'],workers_drained=fault!='drain')
    assert not db.outreach_execution_epochs.docs and not db.outreach_sender_execution.docs[0]['permission']['latched']

async def test_prepare_never_reuses_a_historical_anchor(restored_db,monkeypatch):
    db=restored_db;first=await epoch.RestoreEpoch(db).inspect('w');await prepare(db,first)
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','c'*64);await prepare(db)
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
    assert not (await prepare(db,first))['prepared']
    with pytest.raises(epoch.EpochUnavailable):await epoch.require(db,'w')

async def test_correctly_prepared_root_cannot_grant_or_activate(restored_db):
    await prepare(restored_db)
    with pytest.raises(epoch.EpochUnavailable):await epoch.positive(restored_db,'w')
    with pytest.raises(epoch.EpochUnavailable):await ExecutionPermission(restored_db).grant('w','new','g',['sequence'],'operator',clear_latch=True)
    assert not await ExecutionPermission(restored_db).allowed('w','sender','g','sequence')

@pytest.mark.parametrize('row',[
    {'stages':{'react':{'status':'accepted','receipt':{'accepted_at':'retained'}}}},
    {'stages':{'reply':{'status':'possible_submission'}}},
    {'exchange_state':'possible'}, {'exchange_submitted_at':epoch.now()},
    {'attempt':1}, {'receipt_digest':'a'*64}, {'owner_token':'original'}, {'installation_receipt':{'generation':'original'}}])
async def test_queued_rows_with_partial_or_possible_evidence_remain_held(restored_db,row):
    doc={'_id':'partial','workspace_id':'w','status':'queued',**row}
    restored_db.outreach_manual_actions.docs.append(deepcopy(doc));await prepare(restored_db)
    assert next(d for d in restored_db.outreach_manual_actions.docs if d['_id']=='partial')==doc

async def test_unproven_original_root_shape_denies_before_stops(restored_db):
    restored_db.outreach_execution_epochs.docs.append({**epoch.root_scope('w'),'unexpected':'retained'})
    view=await epoch.RestoreEpoch(restored_db).inspect('w');assert 'original_root_shape_unproven' in view['blockers']
    with pytest.raises(ValueError):await prepare(restored_db,view)
    assert not restored_db.outreach_sender_execution.docs[0]['permission']['latched']

async def test_proof_configuration_change_after_await_and_pure_entry_denies(monkeypatch):
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH',raising=False)
    db=Database();proof=await epoch.positive(db,'w');assert proof.live()
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR);assert not proof.live()
    with pytest.raises(epoch.EpochUnavailable):await epoch.positive(db,'w',captured=proof.captured)

@pytest.mark.parametrize('kind',['studio','preparation','oauth','refresh','sync','verification','integration'])
async def test_restored_workers_deny_before_keys_calls_or_claims(restored_db,monkeypatch,kind):
    from unittest.mock import AsyncMock
    await prepare(restored_db)
    provider=AsyncMock(side_effect=AssertionError('Provider must not run'))
    if kind=='studio':
        from outreach.core.voice_studio import VoiceStudio
        call=lambda:VoiceStudio(restored_db).run('w','old',provider=provider)
    elif kind=='preparation':
        from outreach.core.voice_preparation import VoicePreparation
        monkeypatch.setenv('OUTREACH_VOICE_PREPARATION_ENABLED','true')
        call=lambda:VoicePreparation(restored_db).run('w','old',generator=provider)
    elif kind=='oauth':
        from outreach.core.mailbox_connection import complete_connection_job
        call=lambda:complete_connection_job(restored_db,'w','old')
    elif kind=='refresh':
        from outreach.core.mailbox_refresh import get_access
        call=lambda:get_access(restored_db,{'workspace_id':'w','sender_account_id':'sender'})
    elif kind=='sync':
        from outreach.core.mailbox_sync_jobs import execute_job
        call=lambda:execute_job(restored_db,'w','old')
    elif kind=='verification':
        from celery_workers.tasks.outreach import _verify_sender_connection
        result=await _verify_sender_connection('old','w','trace',db=restored_db)
        assert result['status']=='restore_epoch_required';return
    else:
        from outreach.core.integration_delivery import IntegrationDelivery
        restored_db.outreach_webhook_deliveries.docs.append({'_id':'old','id':'old','workspace_id':'w','status':'pending','custody_protocol_version':2,'next_retry_at':epoch.now(),'next_attempt_at':epoch.now()})
        call=lambda:IntegrationDelivery(restored_db).run('w','old',provider=provider)
    with pytest.raises(epoch.EpochUnavailable):await call()
    provider.assert_not_awaited()

async def test_legacy_connection_health_pure_entry_blocks_changed_epoch(monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.core.proxy_manager import JITProxyManager
    from outreach.models import ProxyConfig
    import outreach.core.proxy_manager as module
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH',raising=False)
    proof=await epoch.positive(Database(),'w')
    transport=AsyncMock()
    class Client:
        async def __aenter__(self):monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR);return transport
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kwargs:Client())
    proxy=ProxyConfig(proxy_id='p',host='example.com',port=8000,username='u',password_enc='unused',country_code='US',provider='iproyal')
    assert not await JITProxyManager().test_proxy_health(proxy,prepared_proxy=type('Proxy',(),{'url':'http://unused','scoped':False})(),allowed=proof.live)
    transport.get.assert_not_awaited()

async def test_oauth_post_denies_epoch_change_during_client_entry(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from outreach.core import mailbox_connection as connection
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH',raising=False)
    proof=await epoch.positive(Database(),'w')
    monkeypatch.setattr(connection,'prepare_app_secret',AsyncMock(return_value=SimpleNamespace(value='dummy',matches=lambda:True)))
    monkeypatch.setattr(connection,'open_oauth_secret',AsyncMock(return_value='dummy'))
    monkeypatch.setattr(connection,'_control_allowed',lambda workspace:True)
    transport=AsyncMock()
    class Client:
        async def __aenter__(self):monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR);return transport
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **kwargs:Client())
    async def preflight():assert proof.live();return []
    config=SimpleNamespace(provider='gmail',client_id='dummy',redirect_uri='https://example.test/callback',token_url='https://example.test/token')
    with pytest.raises(connection.MailboxUnavailable):await connection._token_exchange(config,
        {'workspace_id':'w','sender_account_id':'sender','authorization_code_enc':'dummy','code_verifier_enc':'dummy'},preflight=preflight)
    transport.post.assert_not_awaited()

async def test_assert_live_denies_changed_captured_policy(monkeypatch):
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    proof=await epoch.positive(Database(),'w');proof.assert_live()
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
    with pytest.raises(epoch.EpochUnavailable):proof.assert_live()
