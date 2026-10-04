"""Private drained review closes local work without replay/adoption/activation."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock
import json
import pytest

from outreach.core.voice_studio import VoiceStudio, now, require_profile
from outreach.core.sender_execution import SenderExecution
from outreach.core.execution_permission import ExecutionPermission
from tests.test_outreach_voice_studio import studio_db, clone

EVIDENCE = 'Inspected original provider outcome after all workspace writers and caches were drained.'


async def held(db, monkeypatch, operation='clone', receipt=False):
    service = VoiceStudio(db)
    job = await clone(service)
    if operation != 'clone':
        await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
        profile = db.outreach_voices.docs[0]
        await service.queue('w', 'actor', operation, 'request-review', voice_id=profile['id'], script='Hi')
        job = db.outreach_voice_studio_jobs.docs[-1]
    await service.run('w', job['_id'], provider=AsyncMock(side_effect=TimeoutError()))
    job['lease_until'] = now() - timedelta(seconds=1)
    if receipt:
        job.update(status='held_received', receipt={'received_at': now(), **(
            {'voice_id': 'remote', 'requires_verification': False} if operation == 'clone' else
            {'deleted': True} if operation == 'delete' else {'audio_digest': 'a' * 64, 'content_unavailable': True})})
    db.outreach_accounts.docs.append({'_id': 'account-a', 'workspace_id': 'w', 'id': 'a', 'status': 'active'})
    db.outreach_campaigns.docs.append({'_id': 'campaign-c', 'workspace_id': 'w', 'id': 'c',
        'status': 'active', 'authorization_revision': 3, 'sender_account_ids': ['a']})
    db.outreach_sender_execution.docs.append({**SenderExecution.scope('w', 'a'), 'status': 'in_flight',
        'owner_token': 'physical-owner', 'physical_request_token': 'physical-held', 'permission': {'latched': False}})
    db.outreach_execution_permissions.docs.append({**ExecutionPermission.scope('w', 'a'), 'latched': False})
    for name in ['OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED', 'OUTREACH_LIVE_ACTIONS_ENABLED']:
        monkeypatch.setenv(name, 'false')
    return job


async def resolve(service, job, decision='stop_local', **kw):
    view = await service.inspect('w', job['_id'])
    return await service.resolve('w', job['_id'], decision, 'operator', EVIDENCE,
        expected_digest=view['review_digest'], workers_drained=True, **kw)


@pytest.mark.asyncio
async def test_unknown_local_stop_preserves_evidence_and_stops_before_unlock(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    service = VoiceStudioReview(studio_db)
    before = deepcopy(job)
    view = await service.inspect('w', job['_id'])
    assert 'input_enc' not in json.dumps(view, default=str) and 'provider_source_digest' not in view
    result = await service.resolve('w', job['_id'], 'stop_local', 'operator', EVIDENCE,
        workers_drained=True, expected_digest=view['review_digest'])
    assert result['status'] == 'review_stopped' and result['outcome_at_review'] == 'unknown'
    assert job['owner'] == before['owner'] and job['possible_at'] == before['possible_at']
    assert job['provider_source_digest'] == before['provider_source_digest']
    assert not job.get('input_enc') and not job.get('result_enc')
    assert len(studio_db.outreach_voices.docs) == 1  # unknown clone keeps quota/cleanup custody
    profile = studio_db.outreach_voices.docs[0]
    assert profile['studio_review_required'] is True and not profile.get('studio_job_id')
    with pytest.raises(ValueError): require_profile(profile)
    execution = studio_db.outreach_sender_execution.docs[0]
    assert execution['permission']['latched'] is True and execution['physical_request_token'] == 'physical-held'
    assert execution['owner_token'] == 'physical-owner'
    assert studio_db.outreach_execution_permissions.docs[0]['latched'] is True
    assert studio_db.outreach_campaigns.docs[0]['status'] == 'paused'
    assert studio_db.outreach_campaigns.docs[0]['authorization_revision'] == 4
    assert await service.resolve('w', job['_id'], 'stop_local', 'operator', EVIDENCE,
        workers_drained=True, expected_digest=view['review_digest']) == result
    assert studio_db.outreach_campaigns.docs[0]['authorization_revision'] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['clone', 'preview', 'delete'])
async def test_saved_receipt_repairs_without_decryption_provider_or_reactivation(studio_db, monkeypatch, operation):
    from outreach.core import voice_studio, voice_key_custody
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch, operation, receipt=True)
    receipt = deepcopy(job['receipt'])
    monkeypatch.setattr(voice_studio, 'prepare_key', AsyncMock(side_effect=AssertionError('No key opening')))
    monkeypatch.setattr(voice_studio, 'open_blob', AsyncMock(side_effect=AssertionError('No content opening')))
    result = await resolve(VoiceStudioReview(studio_db), job, 'use_receipt')
    assert result['status'] == 'review_completed' and job['receipt'] == receipt
    assert job['review']['provenance'] == 'saved_provider_receipt'
    if operation == 'delete': assert not studio_db.outreach_voices.docs
    else:
        profile = studio_db.outreach_voices.docs[0]
        assert profile['studio_review_required'] is True
        assert not profile.get('studio_job_id')
        if operation == 'clone': assert profile['elevenlabs_voice_id'] == 'remote'
        with pytest.raises(ValueError): require_profile(profile)
    provider = AsyncMock()
    await VoiceStudio(studio_db).run('w', job['_id'], provider=provider)
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_preparing_non_call_releases_only_original_placeholder(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    job.update(status='preparing'); job.pop('possible_at')
    result = await resolve(VoiceStudioReview(studio_db), job)
    assert result['outcome_at_review'] == 'not_called'
    assert not studio_db.outreach_voices.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['owner', 'receipt', 'profile_source', 'remote', 'profile_revision', 'profile_lock',
    'account', 'campaign', 'execution', 'new_job', 'new_preparation', 'config'])
async def test_stale_review_denies_every_authority_change(studio_db, monkeypatch, change):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    service = VoiceStudioReview(studio_db); view = await service.inspect('w', job['_id'])
    if change == 'owner': job['owner'] = 'replacement'
    if change == 'receipt': job['receipt'] = {'received_at': now(), 'voice_id': 'new', 'requires_verification': False}
    if change == 'profile_source': studio_db.outreach_voices.docs[0]['provider_source_digest'] = 'new'
    if change == 'remote': studio_db.outreach_voices.docs[0]['elevenlabs_voice_id'] = 'replacement'
    if change == 'profile_revision': studio_db.outreach_voices.docs[0]['revision'] += 1
    if change == 'profile_lock': studio_db.outreach_voices.docs[0]['studio_job_id'] = 'new-owner'
    if change == 'account': studio_db.outreach_accounts.docs[0]['credential_generation'] = 'replacement'
    if change == 'campaign': studio_db.outreach_campaigns.docs[0]['authorization_revision'] += 1
    if change == 'execution': studio_db.outreach_sender_execution.docs[0]['owner_token'] = 'new'
    if change == 'new_job': studio_db.outreach_voice_studio_jobs.docs.append({'_id': 'new', 'workspace_id': 'w', 'status': 'queued'})
    if change == 'new_preparation': studio_db.outreach_voice_preparation_jobs.docs.append({'_id': 'new', 'workspace_id': 'w', 'status': 'claimed'})
    if change == 'config': monkeypatch.setenv('ELEVENLABS_API_KEY', 'new-key')
    with pytest.raises(ValueError):
        await service.resolve('w', job['_id'], 'stop_local', 'operator', EVIDENCE,
            workers_drained=True, expected_digest=view['review_digest'])
    assert not job.get('review') and studio_db.outreach_campaigns.docs[0]['status'] == 'active'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['drain', 'live', 'studio', 'generation', 'lease', 'missing_owner', 'no_receipt', 'malformed_receipt', 'capacity'])
async def test_review_fails_closed(studio_db, monkeypatch, failure):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    if failure == 'live': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if failure == 'studio': monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    if failure == 'generation': monkeypatch.setenv('OUTREACH_VOICE_PREPARATION_ENABLED', 'true')
    if failure == 'lease': job['lease_until'] = now() + timedelta(minutes=1)
    if failure == 'missing_owner': job.pop('owner')
    if failure == 'malformed_receipt': job['receipt'] = {'voice_id': 'remote', 'received_at': now(), 'requires_verification': 'false'}
    if failure == 'capacity': studio_db.outreach_accounts.docs.extend({'_id': str(i), 'workspace_id': 'w', 'id': str(i)} for i in range(101))
    service = VoiceStudioReview(studio_db); view = await service.inspect('w', job['_id'])
    with pytest.raises(ValueError):
        await service.resolve('w', job['_id'], 'use_receipt' if failure == 'no_receipt' else 'stop_local', 'operator', EVIDENCE,
            workers_drained=failure != 'drain', expected_digest=view['review_digest'])
    assert not job.get('review')


@pytest.mark.asyncio
async def test_withdrawn_consent_stays_withdrawn_and_cannot_clear_review_latch(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    from outreach.api.voice import update_consent, ConsentRequest
    job = await held(studio_db, monkeypatch, 'preview', receipt=True)
    user = {'user_id': 'actor', 'default_workspace_id': 'w'}
    await update_consent(job['voice_id'], ConsentRequest(consent=False), user, studio_db)
    await resolve(VoiceStudioReview(studio_db), job, 'use_receipt')
    profile = studio_db.outreach_voices.docs[0]
    assert not profile['consent'] and profile['studio_review_required'] is True
    await update_consent(job['voice_id'], ConsentRequest(consent=False), user, studio_db)
    with pytest.raises(Exception) as error:
        await update_consent(job['voice_id'], ConsentRequest(consent=True), user, studio_db)
    assert getattr(error.value, 'status_code', None) == 409
    with pytest.raises(ValueError): require_profile(profile)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['preview', 'delete'])
async def test_review_latch_blocks_new_work_even_after_status_change(studio_db, monkeypatch, operation):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch, 'preview')
    await resolve(VoiceStudioReview(studio_db), job)
    profile = studio_db.outreach_voices.docs[0]; profile['status'] = 'active'
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    with pytest.raises(ValueError):
        await VoiceStudio(studio_db).queue('w', 'actor', operation, 'replacement-request', voice_id=profile['id'], script='Hi')


@pytest.mark.asyncio
async def test_exact_saved_review_cannot_be_relabelled(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    service = VoiceStudioReview(studio_db); view = await service.inspect('w', job['_id'])
    await service.resolve('w', job['_id'], 'stop_local', 'operator', EVIDENCE, workers_drained=True, expected_digest=view['review_digest'])
    for operator, evidence, digest, decision in [('other', EVIDENCE, view['review_digest'], 'stop_local'),
        ('operator', EVIDENCE+' changed', view['review_digest'], 'stop_local'),
        ('operator', EVIDENCE, 'a'*64, 'stop_local'), ('operator', EVIDENCE, view['review_digest'], 'use_receipt')]:
        with pytest.raises(ValueError):
            await service.resolve('w', job['_id'], decision, operator, evidence, workers_drained=True, expected_digest=digest)


@pytest.mark.asyncio
@pytest.mark.parametrize('received', [False, True])
async def test_erasure_keeps_minimal_review_and_original_outcome(studio_db, monkeypatch, received):
    from outreach.core.voice_studio_review import VoiceStudioReview
    from outreach.core.erasure import OutreachErasure
    job = await held(studio_db, monkeypatch, receipt=received)
    await resolve(VoiceStudioReview(studio_db), job, 'use_receipt' if received else 'stop_local')
    await OutreachErasure(studio_db)._archive(studio_db, 'outreach_voice_studio_jobs', 'w', job)
    retained = studio_db.outreach_erasure_holds.docs[0]
    assert retained['kind'] == ('submission_receipt' if received else 'unresolved_submission')
    assert retained['review_provenance'] == job['review']['provenance']
    assert retained['original_outcome'] == ('received' if received else 'unknown')
    assert EVIDENCE not in str(retained) and 'input_enc' not in retained and 'review' not in retained


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['audio_digest', 'voice_id', 'deleted', 'received_at'])
async def test_malformed_receipt_types_never_crash_inspection(studio_db, monkeypatch, field):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch, 'preview' if field == 'audio_digest' else 'delete' if field == 'deleted' else 'clone', receipt=True)
    job['receipt'][field] = {'untrusted': True}
    view = await VoiceStudioReview(studio_db).inspect('w', job['_id'])
    assert 'unusable_saved_receipt' in view['blockers']


@pytest.mark.asyncio
async def test_pending_voice_jobs_cancel_without_clearing_physical_tokens(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    studio_db.outreach_voice_preparation_jobs.docs.append({'_id': 'queued', 'workspace_id': 'w', 'status': 'queued', 'binding': {'private': 'script'}})
    await resolve(VoiceStudioReview(studio_db), job)
    preparation = studio_db.outreach_voice_preparation_jobs.docs[0]
    assert preparation['status'] == 'cancelled' and not preparation.get('binding')


@pytest.mark.asyncio
async def test_unavailable_key_can_still_stop_without_source_adoption(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    original = job['provider_source_digest']
    monkeypatch.delenv('ELEVENLABS_API_KEY')
    await resolve(VoiceStudioReview(studio_db), job)
    assert studio_db.outreach_voices.docs[0]['provider_source_digest'] == original


@pytest.mark.asyncio
async def test_list_hides_private_review_but_exposes_required_followup(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    from outreach.api.voice import list_voices
    job = await held(studio_db, monkeypatch)
    await resolve(VoiceStudioReview(studio_db), job)
    view = await list_voices({'default_workspace_id': 'w'}, studio_db)
    assert view['voices'][0]['operator_review_required'] is True
    assert EVIDENCE not in str(view) and 'review_digest' not in str(view)


@pytest.mark.asyncio
async def test_closed_workspace_local_stop_does_not_create_authorities_or_install(studio_db, monkeypatch):
    from outreach.core.voice_studio_review import VoiceStudioReview
    from outreach.core.suppression import guard_scope
    job = await held(studio_db, monkeypatch, receipt=True)
    studio_db.outreach_suppression_guards.docs.append({**guard_scope('w'), 'erasure_state': 'stopped'})
    from outreach.core import erasure
    async def is_open(db, workspace):
        row = await db.outreach_suppression_guards.find_one(guard_scope(workspace))
        return not row or not row.get('erasure_state')
    monkeypatch.setattr(erasure, 'workspace_is_open', is_open)
    studio_db.outreach_execution_permissions.docs.clear(); studio_db.outreach_sender_execution.docs.clear()
    service = VoiceStudioReview(studio_db)
    with pytest.raises(ValueError): await resolve(service, job, 'use_receipt')
    await resolve(service, job)
    assert not studio_db.outreach_execution_permissions.docs and not studio_db.outreach_sender_execution.docs
    assert not studio_db.outreach_voices.docs[0].get('elevenlabs_voice_id')
    assert studio_db.outreach_suppression_guards.docs[0]['erasure_state'] == 'stopped'


@pytest.mark.asyncio
@pytest.mark.parametrize('verification', [False, True])
async def test_clone_receipt_never_overwrites_withdrawn_consent_status(studio_db, monkeypatch, verification):
    from outreach.core.voice_studio_review import VoiceStudioReview
    from outreach.api.voice import update_consent, ConsentRequest
    job = await held(studio_db, monkeypatch, receipt=True)
    job['receipt']['requires_verification'] = verification
    await update_consent(job['voice_id'], ConsentRequest(consent=False),
        {'user_id': 'actor', 'default_workspace_id': 'w'}, studio_db)
    await resolve(VoiceStudioReview(studio_db), job, 'use_receipt')
    profile = studio_db.outreach_voices.docs[0]
    assert profile['status'] == 'consent_revoked' and not profile['consent']
    assert profile['studio_review_required'] and job['receipt']['requires_verification'] is verification
