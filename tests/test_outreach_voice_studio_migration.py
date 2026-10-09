"""Stopped preview custody conversion never regenerates or extends a receipt."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import voice_studio_migration as migration
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_studio import VoiceStudio
from outreach.core.voice_studio_custody import open_blob
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_studio import studio_db, clone

pytestmark = pytest.mark.asyncio
EVIDENCE = 'a' * 64


@pytest_asyncio.fixture
async def old_preview(studio_db, scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    service = VoiceStudio(studio_db)
    first = await clone(service)
    await service.run('w', first['_id'], provider=AsyncMock(return_value={'voice_id': 'vendor_voice'}))
    profile = studio_db.outreach_voices.docs[0]
    queued = await service.queue('w', 'actor', 'preview', 'preview-1', voice_id=profile['id'], script='Hello')
    await service.run('w', queued['_id'], provider=AsyncMock(return_value={'audio': generate_mock_voice_wav()}))
    job = next(row for row in studio_db.outreach_voice_studio_jobs.docs if row['_id'] == queued['_id'])
    for field in ('created_at', 'updated_at', 'lease_until', 'possible_at', 'authorization_expires_at', 'result_expires_at'):
        job[field] -= timedelta(minutes=5)
    job['receipt']['received_at'] -= timedelta(minutes=5)
    studio_db.outreach_accounts.docs.append({'_id':'account', 'id':'sender', 'workspace_id':'w', 'status':'connected',
        'credential_generation':'original-cookie-generation'})
    studio_db.outreach_campaigns.docs.append({'_id':'campaign', 'workspace_id':'w', 'status':'active',
        'authorization_revision':3, 'auto_launch_enabled':True})
    for name, collection in studio_db.collections.items():
        for index, row in enumerate(collection.docs):
            row.setdefault('_id', name + ':' + str(index))
            row.update(migration.stable(row))
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED', 'OUTREACH_INTEGRATIONS_ENABLED',
                 'OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag, 'false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    return studio_db


def preview_job(db):
    return next(row for row in db.outreach_voice_studio_jobs.docs if row['operation'] == 'preview')


async def convert(db, view=None, **options):
    job = preview_job(db)
    service = migration.VoiceStudioMigration(db)
    view = view or await service.inspect('w', job['_id'])
    return await service.migrate('w', job['_id'], 'operator', EVIDENCE, view['digest'],
        workers_drained=options.get('workers_drained', True))


async def test_original_receipt_audio_lifetime_profile_and_budget_preserved(old_preview, monkeypatch):
    db = old_preview
    original = deepcopy(preview_job(db)); profile = deepcopy(db.outreach_voices.docs[0])
    budgets = deepcopy(db.outreach_voice_studio_budgets.docs)
    view = await migration.VoiceStudioMigration(db).inspect('w', original['_id'])
    assert not view['blockers'] and not view['activation_allowed']
    result = await convert(db, view)
    current = preview_job(db)
    assert result['current_matches'] and result['configuration_matches'] and not result['activation_allowed']
    assert current['result_enc'].startswith('vs1:')
    assert {k:v for k,v in current.items() if k != 'result_enc'} == {k:v for k,v in original.items() if k != 'result_enc'}
    assert await open_blob(current['result_enc'], current, 'result') == generate_mock_voice_wav()
    assert db.outreach_voices.docs[0] == profile and db.outreach_voice_studio_budgets.docs == budgets
    assert db.outreach_accounts.docs[0]['status'] == db.outreach_campaigns.docs[0]['status'] == 'paused'
    assert db.outreach_accounts.docs[0]['credential_generation'] == 'original-cookie-generation'
    assert db.outreach_sender_execution.docs[0]['permission']['latched']
    receipt = db.outreach_credential_migrations.docs[0]
    assert receipt['kind'] == 'voice_studio_result' and receipt['audio_digest'] == original['receipt']['audio_digest']
    for secret in ('gAAAAA', 'vs1:', 'Hello', original['owner'], 'original-cookie-generation'):
        assert secret not in str(receipt)
    # Storage conversion leaves the old execution configuration unchanged.
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    with pytest.raises(ValueError): await VoiceStudio(db).preview('w', original['_id'], 'actor')


@pytest.mark.parametrize('fault', ['not_completed', 'input', 'receipt', 'mutation', 'plaintext', 'scoped',
    'unknown_secret', 'date_text', 'expired', 'extended', 'lease', 'identity', 'resource', 'profile_slot',
    'closed', 'flags', 'live_worker', 'unproven_worker', 'studio_writer', 'preparation_writer', 'capacity', 'drain'])
async def test_unproven_pending_or_live_sources_deny_before_open_and_seal(old_preview, monkeypatch, fault):
    db=old_preview; job=preview_job(db)
    if fault == 'not_completed': job['status']='held_received'
    if fault == 'input': job['input_enc']='unexpected-content'
    if fault == 'receipt': job['receipt'].pop('audio_digest')
    if fault == 'mutation': job['mutation']=True
    if fault == 'plaintext': job['result_enc']='private-audio'
    if fault == 'scoped': job['result_enc']='vs1:wrong'
    if fault == 'unknown_secret': job['audio']='private-audio'
    if fault == 'date_text': job['result_expires_at']=job['result_expires_at'].isoformat()
    if fault == 'expired': job['result_expires_at']=migration.now()-timedelta(seconds=1)
    if fault == 'extended': job['result_expires_at']+=timedelta(days=1)
    if fault == 'lease': job['lease_until']=migration.now()+timedelta(minutes=1)
    if fault == 'identity': job['payload_digest']='unproven'
    if fault == 'resource': db.outreach_voices.docs[0]['elevenlabs_voice_id']='replacement'
    if fault == 'profile_slot': db.outreach_voices.docs[0]['studio_job_id']='other-job'
    if fault == 'closed': monkeypatch.setattr(migration.erasure, 'workspace_is_open', AsyncMock(return_value=False))
    if fault == 'flags': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
    if fault in {'live_worker','unproven_worker'}:
        db.outreach_sender_execution.docs.append({'_id':'worker','workspace_id':'w','sender_id':'sender',
            'status':'held','physical_request_token':'unknown',
            **({'expires_at':migration.now()+timedelta(minutes=1)} if fault=='live_worker' else {})})
    if fault == 'studio_writer': db.outreach_voice_studio_jobs.docs.append({'_id':'pending','workspace_id':'w','status':'queued'})
    if fault == 'preparation_writer': db.outreach_voice_preparation_jobs.docs.append({'_id':'preparing','workspace_id':'w','status':'generating'})
    if fault == 'capacity': db.outreach_accounts.docs.extend({'_id':str(i),'id':str(i),'workspace_id':'w'} for i in range(100))
    opening=AsyncMock(); sealing=AsyncMock()
    monkeypatch.setattr(migration,'open_legacy_result',opening); monkeypatch.setattr(migration,'seal_blob',sealing)
    with pytest.raises(CustodyUnavailable): await convert(db,workers_drained=fault!='drain')
    opening.assert_not_awaited(); sealing.assert_not_awaited()
    assert not db.outreach_credential_migrations.docs


async def test_key_failure_preserves_committed_stop_and_original_preview(old_preview, monkeypatch):
    db=old_preview; original=deepcopy(preview_job(db))
    monkeypatch.setattr(migration,'seal_blob',AsyncMock(side_effect=ValueError('private-key-error')))
    with pytest.raises(Exception): await convert(db)
    assert preview_job(db)==original and not db.outreach_credential_migrations.docs
    assert db.outreach_accounts.docs[0]['status']==db.outreach_campaigns.docs[0]['status']=='paused'


async def test_sealer_cannot_change_the_captured_original_job_identity(old_preview, monkeypatch):
    db=old_preview; original=deepcopy(preview_job(db)); seal=migration.seal_blob
    async def changed(audio,job,kind):
        result=await seal(audio,job,kind)
        job['payload_digest']='b'*64
        return result
    monkeypatch.setattr(migration,'seal_blob',changed)
    with pytest.raises(CustodyUnavailable): await convert(db)
    assert preview_job(db)==original and not db.outreach_credential_migrations.docs


async def test_exact_receipt_retry_skips_audio_keys_stops_and_replacements(old_preview, monkeypatch):
    db=old_preview; service=migration.VoiceStudioMigration(db); job=preview_job(db)
    view=await service.inspect('w',job['_id']); await convert(db,view)
    db.outreach_campaigns.docs[0]['status']='active'; job['result_enc']='replacement'
    monkeypatch.setattr(migration,'open_legacy_result',AsyncMock(side_effect=AssertionError('No opening')))
    monkeypatch.setattr(migration,'seal_blob',AsyncMock(side_effect=AssertionError('No key work')))
    result=await convert(db,view)
    assert not result['current_matches'] and db.outreach_campaigns.docs[0]['status']=='active'
    with pytest.raises(CustodyUnavailable):
        await service.migrate('w',job['_id'],'different-operator',EVIDENCE,view['digest'],workers_drained=True)


@pytest.mark.parametrize('boundary',['commit','opening'])
async def test_late_policy_change_denies_before_following_secret_operation(old_preview, monkeypatch, boundary):
    original_control=migration.suppression.mutate_suppression
    original_open=migration.open_legacy_result
    opening=AsyncMock(wraps=original_open); sealing=AsyncMock()
    if boundary=='commit':
        async def changed(*args,**kwargs):
            result=await original_control(*args,**kwargs)
            monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','replacement')
            return result
        monkeypatch.setattr(migration.suppression,'mutate_suppression',changed)
    else:
        async def changed_open(*args):
            result=await original_open(*args)
            monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','replacement')
            return result
        opening=AsyncMock(side_effect=changed_open)
    monkeypatch.setattr(migration,'open_legacy_result',opening); monkeypatch.setattr(migration,'seal_blob',sealing)
    with pytest.raises(CustodyUnavailable): await convert(old_preview)
    assert opening.await_count==(0 if boundary=='commit' else 1)
    sealing.assert_not_awaited()


@pytest.mark.parametrize('fault',['scope','digest','malformed','duplicate','alternate'])
async def test_strict_original_envelope_and_audio_receipt_required_before_key_work(old_preview, monkeypatch, fault):
    import base64, json
    from utils.encryption import encrypt
    from outreach.core.voice_studio_custody import scope
    db=old_preview; job=preview_job(db)
    body={'scope':scope(job,'result'),'value':base64.b64encode(generate_mock_voice_wav()).decode()}
    if fault=='scope': body['scope']['workspace']='other'
    if fault=='digest': job['receipt']['audio_digest']='b'*64
    if fault=='malformed': body['value']=base64.b64encode(b'not-a-wav').decode()
    if fault=='alternate': body['audio']='plaintext-copy'
    raw=json.dumps(body)
    if fault=='duplicate': raw=raw[:-1]+',"value":"invalid"}'
    job['result_enc']=encrypt(raw)
    sealing=AsyncMock();monkeypatch.setattr(migration,'seal_blob',sealing)
    with pytest.raises(CustodyUnavailable): await convert(db)
    sealing.assert_not_awaited()


async def test_revoked_consent_unknown_holds_and_queued_preparation_preserved_or_stopped(old_preview):
    db=old_preview
    db.outreach_voices.docs[0]['status']='consent_revoked'; db.outreach_voices.docs[0]['revision']+=1
    profile=deepcopy(db.outreach_voices.docs[0])
    db.outreach_sender_execution.docs.append({'_id':'worker','workspace_id':'w','sender_id':'sender','status':'held',
        'owner_token':'original-owner','physical_request_token':'unknown','expires_at':migration.now()-timedelta(seconds=1)})
    db.outreach_voice_preparation_jobs.docs.append({'_id':'queued','workspace_id':'w','status':'queued','binding':{'private':'script'}})
    await convert(db)
    assert db.outreach_voices.docs[0]==profile
    assert db.outreach_sender_execution.docs[0]['physical_request_token']=='unknown'
    assert db.outreach_sender_execution.docs[0]['owner_token']=='original-owner'
    assert db.outreach_voice_preparation_jobs.docs[0]['status']=='cancelled'
    assert 'binding' not in db.outreach_voice_preparation_jobs.docs[0]
