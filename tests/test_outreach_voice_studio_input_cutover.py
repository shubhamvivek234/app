"""Pending input cutover stops only proven unsubmitted protocol jobs."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import erasure, voice_studio_input_cutover as cutover
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.voice_studio import VoiceStudio, now
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_studio import studio_db, clone

pytestmark = pytest.mark.asyncio
EVIDENCE = 'a' * 64
FLAGS = ('OUTREACH_LIVE_ACTIONS_ENABLED', 'OUTREACH_INTEGRATIONS_ENABLED',
         'OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED')


@pytest_asyncio.fixture(params=['clone', 'preview'])
async def pending(studio_db, monkeypatch, request):
    # The shared fake implements scalar membership for every array predicate;
    # full-document CAS needs Mongo's exact literal-array equality here.
    from tests import outreach_memory
    matches = outreach_memory.matches
    def exact_arrays(doc, query):
        return (all(outreach_memory.value(doc, key) == value for key, value in query.items() if isinstance(value, list))
            and matches(doc, {key: value for key, value in query.items() if not isinstance(value, list)}))
    monkeypatch.setattr(outreach_memory, 'matches', exact_arrays)
    service = VoiceStudio(studio_db)
    first = await clone(service)
    job = first
    if request.param == 'preview':
        await service.run('w', first['_id'], provider=AsyncMock(return_value={'voice_id': 'vendor_voice'}))
        queued = await service.queue('w', 'actor', 'preview', 'preview-1', voice_id=first['voice_id'], script='Hello private text')
        job = next(row for row in studio_db.outreach_voice_studio_jobs.docs if row['_id'] == queued['_id'])
    studio_db.outreach_accounts.docs.append({'_id': 'account', 'id': 'sender', 'workspace_id': 'w',
        'status': 'connected', 'credential_generation': 'original-cookie'})
    studio_db.outreach_campaigns.docs.append({'_id': 'campaign', 'workspace_id': 'w', 'status': 'active',
        'authorization_revision': 3, 'auto_launch_enabled': True})
    for name, collection in studio_db.collections.items():
        for index, row in enumerate(collection.docs):
            row.setdefault('_id', name + ':' + str(index))
            row.update(cutover.stable(row))
    for flag in FLAGS: monkeypatch.setenv(flag, 'false')
    return studio_db, job


async def stop(db, job, view=None, **changes):
    service = cutover.VoiceStudioInputCutover(db)
    view = view or await service.inspect('w', job['_id'])
    return await service.stop('w', job['_id'], changes.get('operator', 'operator'),
        changes.get('evidence', EVIDENCE), view['digest'], workers_drained=changes.get('drained', True))


async def test_database_only_stop_scrubs_input_and_keeps_original_authority_history(pending, monkeypatch):
    db, job = pending; original = deepcopy(job); profile = deepcopy(db.outreach_voices.docs[0])
    budgets = deepcopy(db.outreach_voice_studio_budgets.docs)
    from outreach.core import voice_studio, voice_studio_custody
    opening = AsyncMock(side_effect=AssertionError('No input opening'))
    monkeypatch.setattr(voice_studio, 'open_blob', opening)
    monkeypatch.setattr(voice_studio_custody, 'open_blob', opening)
    view = await cutover.VoiceStudioInputCutover(db).inspect('w', job['_id'])
    assert not view['blockers'] and 'Hello' not in str(view) and 'gAAAAA' not in str(view)
    result = await stop(db, job, view)
    assert result['current_matches'] and result['status'] == 'review_stopped' and not result['activation_allowed']
    assert job['status'] == 'review_stopped' and 'input_enc' not in job
    assert all(job[key] == value for key, value in original.items() if key not in {'status', 'input_enc', 'updated_at'})
    if job['operation'] == 'clone': assert not db.outreach_voices.docs
    else:
        current = db.outreach_voices.docs[0]
        assert current['studio_review_required'] and 'studio_job_id' not in current
        assert current['revision'] == profile['revision'] + 1
        for key in ('consent', 'status', 'provider_source_digest', 'elevenlabs_voice_id', 'assigned_account_ids'):
            assert current.get(key) == profile.get(key)
    assert db.outreach_voice_studio_budgets.docs == budgets
    assert db.outreach_accounts.docs[0]['status'] == db.outreach_campaigns.docs[0]['status'] == 'paused'
    assert db.outreach_accounts.docs[0]['credential_generation'] == 'original-cookie'
    assert db.outreach_sender_execution.docs[0]['permission']['latched']
    receipt = db.outreach_credential_migrations.docs[0]
    assert receipt['provenance'] == 'unsubmitted_studio_input_stop' and receipt['original_status'] == 'queued'
    for private in ('gAAAAA', 'vs1:', 'Hello', 'original-cookie', 'vendor_voice', 'operator'):
        assert private not in str({k: v for k, v in receipt.items() if k != 'operator_digest'})
    opening.assert_not_awaited()
    provider = AsyncMock()
    assert (await VoiceStudio(db).run('w', job['_id'], provider=provider))['status'] == 'review_stopped'
    provider.assert_not_awaited()


@pytest.mark.parametrize('minutes', [3, 20])
async def test_expired_preparing_owner_can_stop_without_refunding_budget(pending, minutes):
    db, job = pending
    stamp = now() - timedelta(minutes=minutes)
    job['created_at'] = job['updated_at'] = job['next_publish_at'] = stamp
    job['authorization_expires_at'] = job['next_recovery_at'] = stamp + timedelta(minutes=15)
    job.update(status='preparing', owner='original-owner', lease_until=stamp + timedelta(minutes=2))
    # Clone consent and placeholder were recorded at original creation; retain that equality.
    if job['operation'] == 'clone':
        job['consent']['asserted_at'] = stamp
        profile = db.outreach_voices.docs[0]; profile['consent'] = deepcopy(job['consent'])
        profile['created_at'] = profile['updated_at'] = stamp
        from outreach.core.voice_studio import profile_identity
        job['profile_identity'] = profile_identity(profile)
    db.outreach_voice_studio_budgets.docs.append({'workspace_id': 'w', '_id': 'budget', 'calls': 4})
    assert (await stop(db, job))['current_matches']
    assert job['owner'] == 'original-owner' and job['lease_until'] == stamp + timedelta(minutes=2)
    assert db.outreach_voice_studio_budgets.docs[-1]['calls'] == 4


@pytest.mark.parametrize('fault', ['possible', 'receipt', 'unknown', 'owner', 'lease', 'plaintext', 'extra',
    'date', 'deadline', 'identity', 'slot', 'resource', 'revision', 'closed', 'worker', 'capacity', 'drain',
    'preparation', 'other_live', 'other_unknown'])
async def test_unproven_or_live_work_is_retained(pending, monkeypatch, fault):
    db, job = pending; profile = db.outreach_voices.docs[0]
    if fault == 'possible': job['possible_at'] = now()
    if fault == 'receipt': job['receipt'] = {}
    if fault == 'unknown': job['status'] = 'held_outcome'
    if fault == 'owner': job['owner'] = 'unproven-owner'
    if fault == 'lease': job.update(status='preparing', owner='owner', lease_until=now()+timedelta(minutes=1))
    if fault == 'plaintext': job['input_enc'] = 'private text'
    if fault == 'extra': job['old_plaintext_sample'] = 'private text'
    if fault == 'date': job['created_at'] = job['created_at'].isoformat()
    if fault == 'deadline': job['authorization_expires_at'] += timedelta(hours=1)
    if fault == 'identity': job['profile_identity'] = 'b'*64
    if fault == 'slot': profile['studio_job_id'] = 'replacement'
    if fault == 'resource': profile['elevenlabs_voice_id'] = 'replacement'
    if fault == 'revision': profile['revision'] += 1
    if fault == 'closed': monkeypatch.setattr(erasure, 'workspace_is_open', AsyncMock(return_value=False))
    if fault == 'worker': db.outreach_sender_execution.docs.append({'workspace_id':'w','_id':'execution','status':'in_flight'})
    if fault == 'capacity': db.outreach_accounts.docs.extend({'workspace_id':'w','_id':str(i),'id':str(i)} for i in range(101))
    if fault == 'preparation': db.outreach_voice_preparation_jobs.docs.append({'workspace_id':'w','_id':'preparation','status':'generating'})
    if fault in {'other_live', 'other_unknown'}:
        other = {'workspace_id':'w','_id':'b'*64,'status':'held_outcome'}
        if fault == 'other_live': other['lease_until'] = now()+timedelta(minutes=1)
        db.outreach_voice_studio_jobs.docs.append(other)
    original = deepcopy(job); old_profile = deepcopy(profile)
    with pytest.raises(CustodyUnavailable): await stop(db, job, drained=fault != 'drain')
    assert job == original and profile == old_profile and not db.outreach_credential_migrations.docs


@pytest.mark.parametrize('flag', FLAGS)
async def test_every_gate_denies_mutation(pending, monkeypatch, flag):
    db, job = pending; monkeypatch.setenv(flag, 'true')
    with pytest.raises(CustodyUnavailable): await stop(db, job)
    assert 'input_enc' in job


async def test_exact_saved_retry_preserves_replacement_and_requires_same_evidence(pending, monkeypatch):
    db, job = pending
    view = await cutover.VoiceStudioInputCutover(db).inspect('w', job['_id'])
    await stop(db, job, view)
    db.outreach_accounts.docs[0]['status'] = 'replacement-state'
    job['owner'] = 'replacement-owner'
    monkeypatch.setattr(cutover.VoiceStudioInputCutover, '_snapshot', AsyncMock(side_effect=AssertionError('No second stop')))
    assert not (await stop(db, job, view))['current_matches']
    assert db.outreach_accounts.docs[0]['status'] == 'replacement-state'
    with pytest.raises(CustodyUnavailable): await stop(db, job, view, evidence='c'*64)
    assert len(db.outreach_credential_migrations.docs) == 1


async def test_erasure_retains_digest_only_local_stop_provenance(pending):
    db, job = pending; await stop(db, job)
    receipt = db.outreach_credential_migrations.docs[0]
    await erasure.OutreachErasure(db)._archive(db, 'outreach_credential_migrations', 'w', receipt)
    hold = db.outreach_erasure_holds.docs[0]
    assert hold['kind'] == 'voice_studio_input_stop' and hold['provenance'] == 'unsubmitted_studio_input_stop'
    assert hold['original_status'] == 'queued' and not hold['activation_allowed']
    assert hold['job_id_digest'] == canonical_hash(job['_id'])
    assert all(private not in str(hold) for private in ('Hello', 'gAAAAA', 'vs1:', 'vendor_voice', 'original-cookie'))


async def test_scoped_input_is_scrubbed_without_key_opening(pending, scoped, monkeypatch):
    from outreach.core import voice_studio_custody
    from outreach.core.voice_cloner import generate_mock_voice_wav
    db, job = pending
    raw = generate_mock_voice_wav(duration_s=20) if job['operation'] == 'clone' else b'Hello private text'
    job['input_enc'] = await voice_studio_custody.seal_blob(raw, job, 'input')
    assert job['input_enc'].startswith('vs1:')
    opening = AsyncMock(side_effect=AssertionError('No key opening'))
    monkeypatch.setattr(scoped, 'open', opening)
    assert (await stop(db, job))['current_matches']
    opening.assert_not_awaited()


async def test_other_expired_unknown_hold_keeps_evidence(pending):
    db, job = pending
    held = {'workspace_id':'w','_id':'b'*64,'status':'held_outcome', 'owner':'unknown-owner',
        'lease_until': now()-timedelta(minutes=1), 'possible_at':now()-timedelta(minutes=2), 'input_enc':'original-unknown-input'}
    db.outreach_voice_studio_jobs.docs.append(deepcopy(held))
    await stop(db, job)
    assert db.outreach_voice_studio_jobs.docs[-1] == held
