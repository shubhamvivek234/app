"""Same-key storage continuity must not infer vendor identity or enable a voice."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock
import json
import pytest

from outreach.core import voice_key_custody, session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.voice_studio import VoiceStudio, now, require_profile
from outreach.core.sender_execution import SenderExecution
from outreach.core.execution_permission import ExecutionPermission
from tests.test_outreach_voice_studio import studio_db, clone
from tests.test_outreach_session_custody import scoped

KEY = 'local-provider-key'
EVIDENCE = 'Original key continuity and all workspace writers/caches inspected and drained.'


async def ready(db, monkeypatch, kind='legacy_fernet', verification=False):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', kind)
    monkeypatch.delenv('OUTREACH_ELEVENLABS_API_KEY_ENC', raising=False)
    monkeypatch.delenv('OUTREACH_ELEVENLABS_KEY_GENERATION', raising=False)
    monkeypatch.setenv('ELEVENLABS_API_KEY', KEY if kind == 'legacy_fernet' else '')
    if kind == 'kms_v1':
        envelope = await voice_key_custody.seal_key(KEY, 'g1')
        monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC', envelope)
        monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g1')
    prior = voice_key_custody.capture_configuration()
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    job = await clone(VoiceStudio(db))
    await VoiceStudio(db).run('w', job['_id'], provider=AsyncMock(return_value={
        'voice_id': 'original-remote', 'requires_verification': verification}))
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    monkeypatch.setenv('ELEVENLABS_API_KEY', '')
    envelope = await voice_key_custody.seal_key(KEY, 'g2')
    monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC', envelope)
    monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g2')
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag,'false')
    db.outreach_accounts.docs.append({'_id':'a','id':'a','workspace_id':'w','status':'active'})
    db.outreach_campaigns.docs.append({'_id':'c','id':'c','workspace_id':'w','status':'active','authorization_revision':3})
    db.outreach_sender_execution.docs.append({**SenderExecution.scope('w','a'),'status':'in_flight',
        'physical_request_token':'unrelated-held','owner_token':'original-owner','permission':{'latched':False}})
    db.outreach_execution_permissions.docs.append({**ExecutionPermission.scope('w','a'),'latched':False})
    return db.outreach_voices.docs[0], job, prior


async def migrate(db, profile, prior, **kwargs):
    from outreach.core.voice_source_review import VoiceSourceReview, PreviousKey
    service=VoiceSourceReview(db);view=await service.inspect('w',profile['id'])
    return await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],
        workers_drained=True,previous_key=PreviousKey(prior.storage,prior.policy[0],prior.generation),**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['legacy_fernet','kms_v1'])
async def test_same_key_migration_stops_authority_and_keeps_review_hold(studio_db,scoped,monkeypatch,kind):
    from outreach.core.voice_source_review import VoiceSourceReview
    profile,job,prior=await ready(studio_db,monkeypatch,kind)
    before=deepcopy(job);consent=deepcopy(profile['consent']);revision=profile['revision']
    view=await VoiceSourceReview(studio_db).inspect('w',profile['id'])
    assert not any(value in json.dumps(view,default=str) for value in (KEY,prior.source,prior.storage,'original-remote'))
    result=await migrate(studio_db,profile,prior)
    assert result['status']=='completed' and result['activation_allowed'] is False and result['current_matches']
    assert profile['provider_source_digest']==voice_key_custody.source_digest()
    assert profile['consent']==consent and profile['revision']==revision+1
    assert profile['studio_review_required'] and profile['status']=='review_required'
    with pytest.raises(ValueError): require_profile(profile)
    assert job==before
    assert studio_db.outreach_campaigns.docs[0]['status']=='paused' and studio_db.outreach_campaigns.docs[0]['authorization_revision']==4
    execution=studio_db.outreach_sender_execution.docs[0]
    assert execution['permission']['latched'] and execution['physical_request_token']=='unrelated-held'
    assert execution['owner_token']=='original-owner'
    assert studio_db.outreach_execution_permissions.docs[0]['latched']
    receipt=studio_db.outreach_voice_source_migrations.docs[0]
    assert receipt['provenance']=='same_key_continuity' and receipt['before_source']==prior.source
    assert not any(value in str(receipt) for value in (KEY,prior.storage if kind=='kms_v1' else KEY,'original-remote'))


@pytest.mark.asyncio
@pytest.mark.parametrize('state',['revoked','verification','review'])
async def test_source_rotation_never_clears_consent_verification_or_review(studio_db,scoped,monkeypatch,state):
    profile,job,prior=await ready(studio_db,monkeypatch,verification=state=='verification')
    if state=='revoked': profile.update(consent={},status='consent_revoked')
    if state=='review': profile.update(status='review_required',studio_review_required=True)
    await migrate(studio_db,profile,prior)
    assert profile['status']==('consent_revoked' if state=='revoked' else 'needs_vendor_verification' if state=='verification' else 'review_required')
    assert profile['studio_review_required'] is True
    if state=='revoked': assert not profile['consent']


@pytest.mark.asyncio
async def test_saved_retry_does_not_read_or_open_secrets_or_pause_again(studio_db,scoped,monkeypatch):
    from outreach.core.voice_source_review import VoiceSourceReview,PreviousKey
    profile,job,prior=await ready(studio_db,monkeypatch)
    service=VoiceSourceReview(studio_db);view=await service.inspect('w',profile['id'])
    result=await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=True,
        previous_key=PreviousKey(prior.storage))
    monkeypatch.setattr(scoped,'open',AsyncMock(side_effect=AssertionError('No reopening')))
    assert await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=True,
        previous_key=lambda: pytest.fail('No input reread'))==result
    assert studio_db.outreach_campaigns.docs[0]['authorization_revision']==4
    profile['revision']+=1
    assert not (await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=True))['current_matches']
    with pytest.raises(ValueError):
        await service.migrate('w',profile['id'],'other',EVIDENCE,view['review_digest'],workers_drained=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['remote','revision','consent','receipt','source','owner','new_job','new_preparation','new_sender','config'])
async def test_changed_inspection_denies_before_old_key_read(studio_db,scoped,monkeypatch,change):
    from outreach.core.voice_source_review import VoiceSourceReview
    profile,job,prior=await ready(studio_db,monkeypatch)
    service=VoiceSourceReview(studio_db);view=await service.inspect('w',profile['id'])
    if change=='remote': profile['elevenlabs_voice_id']='replacement'
    if change=='revision': profile['revision']+=1
    if change=='consent': profile['consent']={}
    if change=='receipt': job['receipt']['requires_verification']=True
    if change=='source': profile['provider_source_digest']='a'*64
    if change=='owner': job['owner']='replacement'
    if change=='new_job': studio_db.outreach_voice_studio_jobs.docs.append({'_id':'new','workspace_id':'w','status':'queued'})
    if change=='new_preparation': studio_db.outreach_voice_preparation_jobs.docs.append({'_id':'new','workspace_id':'w','status':'queued'})
    if change=='new_sender': studio_db.outreach_accounts.docs.append({'_id':'new','id':'new','workspace_id':'w'})
    if change=='config': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION','replacement')
    with pytest.raises(ValueError):
        await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=True,
            previous_key=lambda: pytest.fail('Old key must not be read'))
    assert not studio_db.outreach_voice_source_migrations.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['live','studio','generation','drain','missing_source','missing_clone','malformed_receipt',
    'mock_remote','profile_lock','pending_studio','preparing_campaign','capacity','live_sender','unknown_deleted','received_deleted'])
async def test_unproven_or_pending_authorities_deny(studio_db,scoped,monkeypatch,failure):
    from outreach.core.voice_source_review import VoiceSourceReview,PreviousKey
    profile,job,prior=await ready(studio_db,monkeypatch)
    if failure in {'live','studio','generation'}:
        monkeypatch.setenv({'live':'OUTREACH_LIVE_ACTIONS_ENABLED','studio':'OUTREACH_VOICE_STUDIO_ENABLED','generation':'OUTREACH_VOICE_PREPARATION_ENABLED'}[failure],'true')
    if failure=='missing_source': profile.pop('provider_source_digest')
    if failure=='missing_clone': studio_db.outreach_voice_studio_jobs.docs.clear()
    if failure=='malformed_receipt': job['receipt']['requires_verification']='false'
    if failure=='mock_remote': profile['elevenlabs_voice_id']='voice_mock_x'
    if failure=='profile_lock': profile['studio_job_id']='new-lock'
    if failure=='pending_studio': studio_db.outreach_voice_studio_jobs.docs.append({'_id':'new','workspace_id':'w','status':'possible'})
    if failure=='preparing_campaign': studio_db.outreach_voice_preparation_jobs.docs.append({'_id':'new','workspace_id':'w','status':'claimed'})
    if failure=='capacity': studio_db.outreach_accounts.docs.extend({'_id':str(i),'id':str(i),'workspace_id':'w'} for i in range(101))
    if failure=='live_sender': studio_db.outreach_sender_execution.docs[0]['expires_at']=now()+timedelta(minutes=1)
    if failure in {'unknown_deleted','received_deleted'}:
        old=deepcopy(job);old.update(_id='old-delete',operation='delete',status='review_stopped',provider_voice_id='original-remote')
        old['receipt']= {'deleted':True,'received_at':now()} if failure=='received_deleted' else None
        old['review']={'outcome_at_review':'received' if failure=='received_deleted' else 'unknown'}
        studio_db.outreach_voice_studio_jobs.docs.append(old)
    service=VoiceSourceReview(studio_db);view=await service.inspect('w',profile['id'])
    with pytest.raises(ValueError):
        await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=failure!='drain',
            previous_key=PreviousKey(prior.storage))
    assert not studio_db.outreach_voice_source_migrations.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['wrong_old_key','different_new_key','kms','environment','generation'])
async def test_continuity_is_exact_and_cannot_adopt_different_key(studio_db,scoped,monkeypatch,failure):
    from outreach.core.voice_source_review import PreviousKey
    profile,job,prior=await ready(studio_db,monkeypatch,kind='kms_v1' if failure in {'environment','generation'} else 'legacy_fernet')
    if failure=='different_new_key':
        envelope=await voice_key_custody.seal_key('different-account-key','g2')
        monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC',envelope)
    if failure=='kms': monkeypatch.setattr(scoped,'open',AsyncMock(side_effect=ValueError('private failure')))
    if failure=='environment': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','different-environment')
    if failure=='generation':
        from dataclasses import replace
        prior=replace(prior,generation='wrong')
    if failure=='wrong_old_key':
        from dataclasses import replace
        prior=replace(prior,storage='wrong-key')
    with pytest.raises(ValueError): await migrate(studio_db,profile,prior)
    assert profile['provider_source_digest']!=voice_key_custody.source_digest()
    assert not studio_db.outreach_voice_source_migrations.docs


@pytest.mark.asyncio
async def test_multiple_envelope_rotations_keep_original_clone_lineage(studio_db,scoped,monkeypatch):
    profile,job,prior=await ready(studio_db,monkeypatch,kind='kms_v1')
    await migrate(studio_db,profile,prior)
    prior=voice_key_custody.capture_configuration()
    envelope=await voice_key_custody.seal_key(KEY,'g3')
    monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC',envelope)
    monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION','g3')
    await migrate(studio_db,profile,prior)
    receipts=studio_db.outreach_voice_source_migrations.docs
    assert len(receipts)==2 and receipts[0]['root_clone_digest']==receipts[1]['root_clone_digest']
    assert receipts[1]['before_source']==receipts[0]['after_source']
    assert profile['studio_review_required'] and profile['status']=='review_required'


@pytest.mark.asyncio
async def test_queued_campaign_work_cancels_but_original_artifacts_and_budgets_stay(studio_db,scoped,monkeypatch):
    profile,job,prior=await ready(studio_db,monkeypatch)
    studio_db.outreach_voice_preparation_jobs.docs.append({'_id':'q','workspace_id':'w','status':'queued','binding':{'old':'private'}})
    studio_db.outreach_voice_artifacts.docs.append({'_id':'artifact','workspace_id':'w','payload_enc':'old-ciphertext'})
    budgets=deepcopy(studio_db.outreach_voice_studio_budgets.docs)
    await migrate(studio_db,profile,prior)
    assert studio_db.outreach_voice_preparation_jobs.docs[0]['status']=='cancelled'
    assert not studio_db.outreach_voice_preparation_jobs.docs[0].get('binding')
    assert studio_db.outreach_voice_studio_budgets.docs==budgets
    assert studio_db.outreach_voice_artifacts.docs[0]['payload_enc']=='old-ciphertext'


@pytest.mark.asyncio
async def test_erasure_retains_only_minimal_continuity_provenance(studio_db,scoped,monkeypatch):
    from outreach.core.erasure import OutreachErasure,DATA_COLLECTIONS
    profile,job,prior=await ready(studio_db,monkeypatch)
    await migrate(studio_db,profile,prior)
    assert 'outreach_voice_source_migrations' in DATA_COLLECTIONS
    receipt=studio_db.outreach_voice_source_migrations.docs[0]
    await OutreachErasure(studio_db)._archive(studio_db,'outreach_voice_source_migrations','w',receipt)
    hold=studio_db.outreach_erasure_holds.docs[0]
    assert hold['kind']=='voice_source_continuity' and hold['provenance']=='same_key_continuity'
    assert hold['root_clone_digest']==receipt['root_clone_digest']
    assert not any(private in str(hold) for private in (KEY,EVIDENCE,'original-remote'))


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('decision','stop_local'),('outcome_at_review','unknown')])
async def test_reviewed_clone_requires_exact_saved_receipt_decision(studio_db,scoped,monkeypatch,field,value):
    profile,job,prior=await ready(studio_db,monkeypatch)
    job.update(status='review_completed',review={'provenance':'saved_provider_receipt','decision':'use_receipt','outcome_at_review':'received'})
    job['review'][field]=value
    with pytest.raises(ValueError): await migrate(studio_db,profile,prior)


@pytest.mark.asyncio
async def test_original_verification_receipt_cannot_be_overridden_by_display_status(studio_db,scoped,monkeypatch):
    profile,job,prior=await ready(studio_db,monkeypatch,verification=True)
    profile['status']='active'
    await migrate(studio_db,profile,prior)
    assert profile['status']=='needs_vendor_verification' and profile['studio_review_required']


@pytest.mark.asyncio
async def test_changed_owner_during_key_open_denies_source_install(studio_db,scoped,monkeypatch):
    profile,job,prior=await ready(studio_db,monkeypatch)
    opening=scoped.open
    async def changed(*args):
        result=await opening(*args)
        profile['elevenlabs_voice_id']='replacement'
        return result
    monkeypatch.setattr(scoped,'open',changed)
    with pytest.raises(ValueError): await migrate(studio_db,profile,prior)
    assert profile['provider_source_digest']==prior.source and not studio_db.outreach_voice_source_migrations.docs


@pytest.mark.asyncio
async def test_closed_workspace_denies_before_reading_original_key(studio_db,scoped,monkeypatch):
    from outreach.core import erasure
    from outreach.core.voice_source_review import VoiceSourceReview
    profile,job,prior=await ready(studio_db,monkeypatch)
    monkeypatch.setattr(erasure,'workspace_is_open',AsyncMock(return_value=False))
    service=VoiceSourceReview(studio_db);view=await service.inspect('w',profile['id'])
    assert 'workspace_closed' in view['blockers']
    with pytest.raises(ValueError):
        await service.migrate('w',profile['id'],'operator',EVIDENCE,view['review_digest'],workers_drained=True,
            previous_key=lambda: pytest.fail('No secret read for closed workspace'))


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['owner','consent','status'])
async def test_malformed_stored_binding_denies_before_key_open(studio_db,scoped,monkeypatch,field):
    profile,job,prior=await ready(studio_db,monkeypatch)
    if field=='owner':job['owner']={'unproven':'owner'}
    elif field=='consent':profile['consent']=True
    else:profile['status']={'unproven':'state'}
    opening=AsyncMock(side_effect=AssertionError('No opening for malformed binding'))
    monkeypatch.setattr(scoped,'open',opening)
    with pytest.raises(ValueError):await migrate(studio_db,profile,prior)
    opening.assert_not_awaited()
    assert profile['provider_source_digest']==prior.source and not studio_db.outreach_voice_source_migrations.docs
