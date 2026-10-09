"""Stopped installed-clip conversion preserves original audio and paid receipts."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import voice_artifact_migration as migration
from outreach.core.content_approval import ContentApproval
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_preparation import voice_db

pytestmark = pytest.mark.asyncio
EVIDENCE = 'a' * 64


@pytest_asyncio.fixture
async def old_clip(voice_db, scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    service = VoicePreparation(voice_db)
    job = await service.queue('w', 'l', 'human')
    assert (await service.run('w', job['_id'], generator=AsyncMock(return_value=generate_mock_voice_wav())))['status'] == 'prepared'
    approval = voice_db.outreach_content_approvals.docs[0]
    await ContentApproval(voice_db).decide('w', approval['_id'], 'human', 'approve', revision=1)
    for name, collection in voice_db.collections.items():
        for index, row in enumerate(collection.docs):
            row.setdefault('_id', name + ':' + str(index))
            row.update(migration.stable(row))
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED', 'OUTREACH_INTEGRATIONS_ENABLED',
                 'OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag, 'false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    return voice_db


async def convert(db, view=None, **changes):
    artifact = db.outreach_voice_artifacts.docs[0]
    service = migration.VoiceArtifactMigration(db)
    view = view or await service.inspect('w', artifact['_id'])
    options = {'workers_drained': True}; options.update(changes)
    return await service.migrate('w', artifact['_id'], 'operator', EVIDENCE, view['digest'], **options)


async def test_same_clip_generation_expiry_and_receipt_survive_but_review_is_revoked(old_clip):
    db = old_clip
    original = deepcopy(db.outreach_voice_artifacts.docs[0])
    job = deepcopy(db.outreach_voice_preparation_jobs.docs[0])
    account = deepcopy(db.outreach_accounts.docs[0])
    budget = deepcopy(db.outreach_voice_preparation_budgets.docs)
    view = await migration.VoiceArtifactMigration(db).inspect('w', original['_id'])
    assert not view['blockers'] and not view['activation_allowed']
    result = await convert(db, view)
    assert result['current_matches'] and result['configuration_matches'] and not result['activation_allowed']
    current = db.outreach_voice_artifacts.docs[0]
    assert current['audio_enc'].startswith('va1:')
    assert {key:value for key,value in current.items() if key != 'audio_enc'} == {key:value for key,value in original.items() if key != 'audio_enc'}
    assert await VoiceArtifacts(db).load('w', original['_id']) == generate_mock_voice_wav()
    assert db.outreach_voice_preparation_jobs.docs[0] == job and db.outreach_voice_preparation_budgets.docs == budget
    assert db.outreach_accounts.docs[0]['credential_generation'] == account['credential_generation']
    assert db.outreach_accounts.docs[0]['status'] == db.outreach_campaigns.docs[0]['status'] == 'paused'
    assert db.outreach_sender_execution.docs[0]['permission']['latched']
    assert db.outreach_content_approvals.docs[0]['status'] == 'pending'
    assert not await ContentApproval(db).allowed(db.outreach_content_approvals.docs[0]['binding'])
    receipt = db.outreach_credential_migrations.docs[0]
    assert receipt['kind'] == 'voice_artifact' and receipt['provenance'] == 'strict_fernet_voice_artifact_conversion'
    for secret in ('gAAAAA', 'va1:', 'Hello', 'cookie', original['generation_id']):
        assert secret not in str(receipt)


@pytest.mark.parametrize('fault', ['receipt', 'owner', 'audio_digest', 'mutation', 'started', 'generation',
    'expired', 'date_text', 'plaintext', 'scoped', 'unknown_secret', 'closed', 'flags', 'live_worker',
    'unproven_worker', 'studio_writer', 'preparation_writer', 'approvals_capacity', 'drain'])
async def test_unproven_or_live_source_denies_before_open_and_seal(old_clip, monkeypatch, fault):
    db = old_clip; row = db.outreach_voice_artifacts.docs[0]; job = db.outreach_voice_preparation_jobs.docs[0]
    if fault == 'receipt': job.pop('generation_result')
    if fault == 'owner': job['owner'] = 'replacement'
    if fault == 'audio_digest': job['audio_digest'] = 'b' * 64
    if fault == 'mutation': job['mutation'] = False
    if fault == 'started': job.pop('generation_started_at')
    if fault == 'generation': row['generation_id'] = 'replacement'
    if fault == 'expired': row['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    if fault == 'date_text': row['prepared_at'] = row['prepared_at'].isoformat()
    if fault in ('plaintext', 'scoped'): row['audio_enc'] = 'private-audio' if fault == 'plaintext' else 'va1:unproven'
    if fault == 'unknown_secret': row['raw_audio'] = 'private-audio'
    if fault == 'closed': monkeypatch.setattr(migration.erasure, 'workspace_is_open', AsyncMock(return_value=False))
    if fault == 'flags': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED', 'true')
    if fault in ('live_worker', 'unproven_worker'):
        db.outreach_sender_execution.docs.append({'_id':'w:a','workspace_id':'w','sender_id':'a','status':'in_flight',
            **({'expires_at':datetime.now(timezone.utc)+timedelta(minutes=1)} if fault=='live_worker' else {})})
    if fault == 'studio_writer': db.outreach_voice_studio_jobs.docs.append({'_id':'writer','workspace_id':'w','status':'possible'})
    if fault == 'preparation_writer': db.outreach_voice_preparation_jobs.docs.append({'_id':'writer','workspace_id':'w','status':'generating'})
    if fault == 'approvals_capacity':
        db.outreach_content_approvals.docs.extend([{**deepcopy(db.outreach_content_approvals.docs[0]),'_id':str(index)} for index in range(100)])
    opening = AsyncMock(side_effect=AssertionError('No opening')); sealing = AsyncMock(side_effect=AssertionError('No sealing'))
    monkeypatch.setattr(migration, 'open_legacy_audio', opening); monkeypatch.setattr(migration, 'seal_audio', sealing)
    with pytest.raises(CustodyUnavailable): await convert(db, workers_drained=fault != 'drain')
    opening.assert_not_awaited(); sealing.assert_not_awaited()
    assert not db.outreach_credential_migrations.docs


async def test_key_failure_leaves_stopped_authority_and_original_clip(old_clip, monkeypatch):
    row = deepcopy(old_clip.outreach_voice_artifacts.docs[0])
    monkeypatch.setattr(migration, 'seal_audio', AsyncMock(side_effect=CustodyUnavailable('Unavailable')))
    with pytest.raises(CustodyUnavailable): await convert(old_clip)
    assert old_clip.outreach_voice_artifacts.docs[0] == row
    assert old_clip.outreach_campaigns.docs[0]['status'] == 'paused'
    assert old_clip.outreach_content_approvals.docs[0]['status'] == 'pending'
    assert not old_clip.outreach_credential_migrations.docs


async def test_exact_saved_retry_preserves_later_authority_and_never_opens_or_installs(old_clip, monkeypatch):
    db = old_clip; asset = db.outreach_voice_artifacts.docs[0]['_id']
    view = await migration.VoiceArtifactMigration(db).inspect('w', asset)
    result = await convert(db, view)
    db.outreach_campaigns.docs[0]['status'] = 'draft'
    monkeypatch.setattr(migration, 'open_legacy_audio', AsyncMock(side_effect=AssertionError('No opening')))
    monkeypatch.setattr(migration, 'seal_audio', AsyncMock(side_effect=AssertionError('No sealing')))
    assert await convert(db, view) == result and db.outreach_campaigns.docs[0]['status'] == 'draft'
    with pytest.raises(CustodyUnavailable):
        await migration.VoiceArtifactMigration(db).migrate('w', asset, 'other', EVIDENCE, view['digest'], workers_drained=True)
    db.outreach_voice_artifacts.docs[0]['audio_enc'] = 'replacement'
    assert not (await convert(db, view))['current_matches']


async def test_queued_work_cancels_but_unrelated_unknown_tokens_and_budgets_stay(old_clip):
    db = old_clip
    db.outreach_voice_preparation_jobs.docs.append({'_id':'queued','workspace_id':'w','status':'queued','binding':{'secret':'unused'}})
    db.outreach_sender_execution.docs.append({'_id':'w:a','workspace_id':'w','sender_id':'a','status':'unknown_outcome',
        'expires_at':datetime.now(timezone.utc)-timedelta(minutes=1),'physical_request_token':'held','owner_token':'original',
        'permission':{'latched':True}})
    assert (await convert(db))['current_matches']
    assert db.outreach_voice_preparation_jobs.docs[1]['status'] == 'cancelled' and 'binding' not in db.outreach_voice_preparation_jobs.docs[1]
    assert db.outreach_sender_execution.docs[0]['physical_request_token'] == 'held'
    assert db.outreach_sender_execution.docs[0]['owner_token'] == 'original'


@pytest.mark.parametrize('boundary', ['commit', 'opening'])
async def test_policy_change_after_stop_denies_before_following_secret_operation(old_clip, monkeypatch, boundary):
    mutate, opening = migration.suppression.mutate_suppression, migration.open_legacy_audio
    async def committed(*args, **kwargs):
        result = await mutate(*args, **kwargs)
        if boundary == 'commit': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'replacement')
        return result
    async def opened(*args, **kwargs):
        result = await opening(*args, **kwargs)
        if boundary == 'opening': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'replacement')
        return result
    open_spy = AsyncMock(side_effect=opened)
    seal_spy = AsyncMock(side_effect=AssertionError('No sealing'))
    monkeypatch.setattr(migration.suppression, 'mutate_suppression', committed)
    monkeypatch.setattr(migration, 'open_legacy_audio', open_spy)
    monkeypatch.setattr(migration, 'seal_audio', seal_spy)
    with pytest.raises(CustodyUnavailable): await convert(old_clip)
    assert open_spy.await_count == (0 if boundary == 'commit' else 1)
    seal_spy.assert_not_awaited()
    assert old_clip.outreach_accounts.docs[0]['status'] == 'paused'


@pytest.mark.parametrize('fault', ['missing', 'workspace', 'body', 'generation'])
async def test_retained_original_content_binding_is_required_before_opening(old_clip, monkeypatch, fault):
    review = old_clip.outreach_content_approvals.docs[0]
    if fault == 'missing': old_clip.outreach_content_approvals.docs.clear()
    if fault == 'workspace': review['binding']['workspace_id'] = 'other'
    if fault == 'body': review['binding']['content']['body'] = 'replacement script'
    if fault == 'generation': review['binding']['context']['voice_artifact_generation'] = 'replacement'
    opening = AsyncMock(side_effect=AssertionError('No opening'))
    monkeypatch.setattr(migration, 'open_legacy_audio', opening)
    with pytest.raises(CustodyUnavailable): await convert(old_clip)
    opening.assert_not_awaited()


@pytest.mark.parametrize('decision', ['reject', 'revoke'])
async def test_conversion_preserves_existing_human_rejection_or_revocation(old_clip, decision):
    review=old_clip.outreach_content_approvals.docs[0]
    await ContentApproval(old_clip).decide('w',review['_id'],'human',decision,revision=review['revision'])
    status=review['status']
    assert (await convert(old_clip))['current_matches']
    assert review['status']==status and not await ContentApproval(old_clip).allowed(review['binding'])


@pytest.mark.parametrize('fault', ['unreadable', 'wrong_audio', 'invalid_audio'])
async def test_failed_strict_original_open_never_seals_or_replaces_audio(old_clip, monkeypatch, fault):
    import base64
    from utils.encryption import encrypt
    row=old_clip.outreach_voice_artifacts.docs[0]
    if fault=='unreadable': row['audio_enc']='gAAAAAunreadable'
    if fault=='wrong_audio': row['audio_enc']=encrypt(base64.b64encode(generate_mock_voice_wav()+b'different').decode())
    if fault=='invalid_audio': row['audio_enc']=encrypt(base64.b64encode(b'not-wave').decode())
    original=row['audio_enc']; seal=AsyncMock(side_effect=AssertionError('No sealing'))
    monkeypatch.setattr(migration,'seal_audio',seal)
    with pytest.raises(CustodyUnavailable): await convert(old_clip)
    seal.assert_not_awaited()
    assert row['audio_enc']==original and old_clip.outreach_accounts.docs[0]['status']=='paused'
