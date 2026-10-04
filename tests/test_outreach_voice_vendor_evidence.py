"""Vendor metadata cannot release stale, unowned, unverified or revoked voices."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock
import json
import pytest

from outreach.core import voice_key_custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.voice_studio import now, require_profile
from outreach.core.voice_source_review import VoiceSourceReview, PreviousKey
from tests.test_outreach_voice_source_review import studio_db, scoped, ready, KEY, EVIDENCE

pytestmark = pytest.mark.asyncio

METADATA = {'voice_id': 'original-remote', 'category': 'cloned', 'is_owner': True,
    'permission_on_resource': 'admin', 'is_legacy': False, 'is_mixed': False,
    'safety_control': 'NONE', 'voice_verification': {'requires_verification': False, 'is_verified': True}}


async def prepared(db, monkeypatch, verification=False):
    profile, clone, prior = await ready(db, monkeypatch, verification=verification)
    service = VoiceSourceReview(db)
    view = await service.inspect('w', profile['id'])
    await service.migrate('w', profile['id'], 'operator', EVIDENCE, view['review_digest'], workers_drained=True,
        previous_key=PreviousKey(prior.storage, prior.policy[0], prior.generation))
    return profile, clone


async def capture(db, profile, provider=None, digest=None):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    service = VoiceVendorEvidence(db)
    digest = digest or (await service.inspect('w', profile['id']))['review_digest']
    return await service.capture('w', profile['id'], 'operator', EVIDENCE, digest,
        workers_drained=True, provider=provider or AsyncMock(return_value=deepcopy(METADATA)))


async def release(db, profile, job_id, digest=None):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    service = VoiceVendorEvidence(db)
    digest = digest or (await service.inspect('w', profile['id'], job_id))['review_digest']
    return await service.release('w', profile['id'], job_id, 'operator', EVIDENCE, digest, workers_drained=True)


async def test_capture_is_bounded_read_and_release_stops_authority_without_http(studio_db, scoped, monkeypatch):
    profile, clone = await prepared(studio_db, monkeypatch, verification=True)
    original = deepcopy(clone); consent = deepcopy(profile['consent']); revision = profile['revision']
    async def provider(request):
        assert request['allowed']() and request['voice_id'] == 'original-remote'
        job = studio_db.outreach_voice_vendor_reads.docs[0]
        assert job['status'] == 'possible' and job['mutation'] is False
        assert studio_db.outreach_voice_studio_budgets.docs[-1]['calls'] == 1
        return {**deepcopy(METADATA), 'description': 'private narrative', 'samples': ['private sample']}
    job = await capture(studio_db, profile, provider)
    assert job['status'] == 'received' and not job['activation_allowed']
    assert profile['studio_review_required'] and profile['revision'] == revision
    saved = studio_db.outreach_voice_vendor_reads.docs[0]
    assert KEY not in str(saved) and 'private narrative' not in str(saved) and 'samples' not in str(saved)
    monkeypatch.setattr(voice_key_custody, 'prepare_key', AsyncMock(side_effect=AssertionError('No key open on release')))
    result = await release(studio_db, profile, job['job_id'])
    assert result['status'] == 'released' and result['current_matches'] and not result['activation_allowed']
    require_profile(profile)
    assert profile['consent'] == consent and profile['revision'] == revision + 1 and clone == original
    assert studio_db.outreach_accounts.docs[0]['status'] == 'paused'
    assert studio_db.outreach_campaigns.docs[0]['status'] == 'paused'
    execution = studio_db.outreach_sender_execution.docs[0]
    assert execution['physical_request_token'] == 'unrelated-held' and execution['permission']['latched']
    assert studio_db.outreach_execution_permissions.docs[0]['latched']


@pytest.mark.parametrize('field,value', [('is_owner', False), ('is_owner', None), ('is_owner', 1),
    ('category', 'professional'), ('permission_on_resource', 'viewer'), ('permission_on_resource', None),
    ('safety_control', 'CAPTCHA'), ('is_legacy', True), ('is_mixed', True), ('voice_id', 'other-remote')])
async def test_vendor_denials_preserve_hold(studio_db, scoped, monkeypatch, field, value):
    profile, _ = await prepared(studio_db, monkeypatch)
    metadata = {**deepcopy(METADATA), field: value}
    job = await capture(studio_db, profile, AsyncMock(return_value=metadata))
    with pytest.raises(ValueError): await release(studio_db, profile, job['job_id'])
    assert profile['studio_review_required']


@pytest.mark.parametrize('verification', [None, {}, {'requires_verification': True, 'is_verified': True},
    {'requires_verification': False, 'is_verified': False}, {'requires_verification': 0, 'is_verified': True}])
async def test_required_verification_is_never_inferred(studio_db, scoped, monkeypatch, verification):
    profile, _ = await prepared(studio_db, monkeypatch, verification=True)
    job = await capture(studio_db, profile, AsyncMock(return_value={**deepcopy(METADATA), 'voice_verification': verification}))
    with pytest.raises(ValueError): await release(studio_db, profile, job['job_id'])
    assert profile['status'] == 'needs_vendor_verification'


async def test_original_no_verification_clone_accepts_explicit_not_required(studio_db, scoped, monkeypatch):
    profile, _ = await prepared(studio_db, monkeypatch)
    metadata = {**deepcopy(METADATA), 'voice_verification': {'requires_verification': False, 'is_verified': False}}
    job = await capture(studio_db, profile, AsyncMock(return_value=metadata))
    assert (await release(studio_db, profile, job['job_id']))['current_matches']


@pytest.mark.parametrize('change', ['consent', 'remote', 'revision', 'source', 'root', 'config', 'expired', 'closed', 'flags'])
async def test_changed_authority_or_stale_receipt_denies_release(studio_db, scoped, monkeypatch, change):
    profile, clone = await prepared(studio_db, monkeypatch, verification=True)
    job = await capture(studio_db, profile)
    if change == 'consent': profile.update(consent={}, status='consent_revoked')
    elif change == 'remote': profile['elevenlabs_voice_id'] = 'replacement'
    elif change == 'revision': profile['revision'] += 1
    elif change == 'source': profile['provider_source_digest'] = 'a' * 64
    elif change == 'root': clone['receipt']['requires_verification'] = False
    elif change == 'config': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'replacement')
    elif change == 'expired':
        saved = studio_db.outreach_voice_vendor_reads.docs[0]
        saved['receipt']['received_at'] = now() - timedelta(minutes=16)
        saved['possible_at'] = saved['receipt']['received_at'] - timedelta(seconds=1)
        from outreach.core.voice_vendor_evidence import digest
        saved['receipt_digest'] = digest(saved['receipt'])
    elif change == 'closed':
        from outreach.core import erasure
        monkeypatch.setattr(erasure, 'workspace_is_open', AsyncMock(return_value=False))
    else: monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    with pytest.raises((ValueError, suppression.SuppressionUnavailable)): await release(studio_db, profile, job['job_id'])
    assert profile['studio_review_required']


async def test_capture_retry_and_release_retry_never_repeat_http_or_stop(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch)
    service = VoiceVendorEvidence(studio_db); digest = (await service.inspect('w', profile['id']))['review_digest']
    provider = AsyncMock(return_value=deepcopy(METADATA))
    job = await capture(studio_db, profile, provider, digest)
    assert await capture(studio_db, profile, provider, digest) == job
    assert provider.await_count == 1
    inspected = await service.inspect('w', profile['id'], job['job_id'])
    result = await release(studio_db, profile, job['job_id'], inspected['review_digest'])
    campaign = deepcopy(studio_db.outreach_campaigns.docs[0])
    assert await release(studio_db, profile, job['job_id'], inspected['review_digest']) == result
    assert studio_db.outreach_campaigns.docs[0] == campaign
    profile['elevenlabs_voice_id'] = 'replacement'
    assert not (await release(studio_db, profile, job['job_id'], inspected['review_digest']))['current_matches']


async def test_unknown_read_is_not_replayed_and_requires_drained_expired_close(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch)
    service = VoiceVendorEvidence(studio_db); digest = (await service.inspect('w', profile['id']))['review_digest']
    provider = AsyncMock(side_effect=TimeoutError('private vendor failure'))
    job = await capture(studio_db, profile, provider, digest)
    assert job['status'] == 'possible'
    assert (await capture(studio_db, profile, provider, digest)) == job and provider.await_count == 1
    view = await service.inspect('w', profile['id'], job['job_id'])
    with pytest.raises(ValueError): await service.close_read('w', profile['id'], job['job_id'], 'operator', EVIDENCE,
        view['review_digest'], workers_drained=True)
    saved = studio_db.outreach_voice_vendor_reads.docs[0]; saved['authorization_expires_at'] = now() - timedelta(seconds=1)
    view = await service.inspect('w', profile['id'], job['job_id'])
    result = await service.close_read('w', profile['id'], job['job_id'], 'operator', EVIDENCE,
        view['review_digest'], workers_drained=True)
    assert result['status'] == 'read_interrupted' and profile['studio_review_required']
    next_job = await capture(studio_db, profile)
    assert next_job['job_id'] != job['job_id'] and next_job['status'] == 'received'
    assert studio_db.outreach_voice_studio_budgets.docs[-1]['calls'] == 2


@pytest.mark.parametrize('change', ['profile', 'new_sender', 'config', 'flags'])
async def test_key_open_race_denies_before_http(studio_db, scoped, monkeypatch, change):
    profile, _ = await prepared(studio_db, monkeypatch)
    opening = voice_key_custody.prepare_key
    async def changed(*args, **kwargs):
        key = await opening(*args, **kwargs)
        if change == 'profile': profile['revision'] += 1
        elif change == 'new_sender': studio_db.outreach_accounts.docs.append({'_id': 'new', 'id': 'new', 'workspace_id': 'w'})
        elif change == 'config': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g3')
        else: monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
        return key
    monkeypatch.setattr(voice_key_custody, 'prepare_key', changed)
    provider = AsyncMock(return_value=deepcopy(METADATA))
    job = await capture(studio_db, profile, provider)
    assert job['status'] == 'stopped' and profile['studio_review_required']
    provider.assert_not_awaited()


async def test_private_inspection_projects_no_vendor_or_secret_identity(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch)
    job = await capture(studio_db, profile)
    view = await VoiceVendorEvidence(studio_db).inspect('w', profile['id'], job['job_id'])
    encoded = json.dumps(view)
    assert view['release_available']
    assert not any(item in encoded for item in (KEY, 'original-remote', 'admin', EVIDENCE))


@pytest.mark.parametrize('change', ['drain', 'digest', 'operator', 'evidence', 'flags', 'unscoped', 'unproven', 'consent'])
async def test_capture_prerequisites_deny_before_key_or_get(studio_db, scoped, monkeypatch, change):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, clone = await prepared(studio_db, monkeypatch); service = VoiceVendorEvidence(studio_db)
    digest = (await service.inspect('w', profile['id']))['review_digest']
    values = {'operator': 'operator', 'evidence': EVIDENCE, 'workers_drained': True, 'expected_digest': digest}
    if change == 'drain': values['workers_drained'] = False
    elif change == 'digest': values['expected_digest'] = 'invalid'
    elif change == 'operator': values['operator'] = ''
    elif change == 'evidence': values['evidence'] = 'short'
    elif change == 'flags': monkeypatch.setenv('OUTREACH_VOICE_PREPARATION_ENABLED', 'true')
    elif change == 'unscoped': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    elif change == 'unproven': clone['receipt'] = None
    else: profile['consent'] = ['malformed']
    opening = AsyncMock(side_effect=AssertionError('No key')); provider = AsyncMock()
    monkeypatch.setattr(voice_key_custody, 'prepare_key', opening)
    with pytest.raises(ValueError): await service.capture('w', profile['id'], provider=provider, **values)
    opening.assert_not_awaited(); provider.assert_not_awaited()


async def test_daily_budget_blocks_before_get_and_never_refunds_possible(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import READ_LIMIT
    profile, _ = await prepared(studio_db, monkeypatch)
    await capture(studio_db, profile)
    budget = studio_db.outreach_voice_studio_budgets.docs[-1]; budget['calls'] = READ_LIMIT
    provider = AsyncMock(return_value=METADATA)
    assert (await capture(studio_db, profile, provider))['status'] == 'stopped'
    provider.assert_not_awaited(); assert budget['calls'] == READ_LIMIT


async def test_configuration_changed_during_get_saves_receipt_but_cannot_release(studio_db, scoped, monkeypatch):
    profile, _ = await prepared(studio_db, monkeypatch)
    async def changed(request):
        monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g3'); return METADATA
    job = await capture(studio_db, profile, changed)
    assert job['status'] == 'received'
    with pytest.raises(ValueError): await release(studio_db, profile, job['job_id'])
    assert profile['studio_review_required']


async def test_different_retry_actor_or_evidence_denies_without_get(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch); service = VoiceVendorEvidence(studio_db)
    digest = (await service.inspect('w', profile['id']))['review_digest']; await capture(studio_db, profile, digest=digest)
    with pytest.raises(ValueError): await service.capture('w', profile['id'], 'other-operator', EVIDENCE, digest, workers_drained=True)
    job = studio_db.outreach_voice_vendor_reads.docs[0]
    view = await service.inspect('w', profile['id'], job['_id'])
    await release(studio_db, profile, job['_id'], view['review_digest'])
    with pytest.raises(ValueError): await service.release('w', profile['id'], job['_id'], 'operator', EVIDENCE + ' Changed.',
        view['review_digest'], workers_drained=True)


async def test_saved_read_closure_reuses_provenance_without_repeated_stops(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch); service = VoiceVendorEvidence(studio_db)
    job = await capture(studio_db, profile, AsyncMock(side_effect=TimeoutError()))
    studio_db.outreach_voice_vendor_reads.docs[0]['authorization_expires_at'] = now() - timedelta(seconds=1)
    view = await service.inspect('w', profile['id'], job['job_id'])
    result = await service.close_read('w', profile['id'], job['job_id'], 'operator', EVIDENCE,
        view['review_digest'], workers_drained=True)
    assert await service.close_read('w', profile['id'], job['job_id'], 'operator', EVIDENCE,
        view['review_digest'], workers_drained=True) == result
    with pytest.raises(ValueError): await service.close_read('w', profile['id'], job['job_id'], 'other', EVIDENCE,
        view['review_digest'], workers_drained=True)


async def test_capture_capacity_preserves_last_receipts_reviewability(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence, LIMIT
    profile, _ = await prepared(studio_db, monkeypatch)
    job = await capture(studio_db, profile)
    saved = studio_db.outreach_voice_vendor_reads.docs[0]
    for index in range(LIMIT - 1):
        studio_db.outreach_voice_vendor_reads.docs.append({**deepcopy(saved), '_id': canonical_hash(index), 'status': 'stopped'})
    service = VoiceVendorEvidence(studio_db)
    view = await service.inspect('w', profile['id'])
    assert not view['capture_available'] and 'vendor_read_capacity_exceeded' in view['blockers']
    with pytest.raises(ValueError): await capture(studio_db, profile)
    assert (await release(studio_db, profile, job['job_id']))['current_matches']


@pytest.mark.parametrize('job_id', [{'\u0024ne': None}, [], '', 'unbounded-id'])
async def test_job_reference_cannot_be_a_query_or_unbound_identity(studio_db, scoped, monkeypatch, job_id):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch); service = VoiceVendorEvidence(studio_db)
    with pytest.raises(ValueError): await service.inspect('w', profile['id'], job_id)
    with pytest.raises(ValueError): await service.release('w', profile['id'], job_id, 'operator', EVIDENCE, 'a' * 64, workers_drained=True)
    with pytest.raises(ValueError): await service.close_read('w', profile['id'], job_id, 'operator', EVIDENCE, 'a' * 64, workers_drained=True)


async def test_malformed_historical_read_status_is_not_echoed(studio_db, scoped, monkeypatch):
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    profile, _ = await prepared(studio_db, monkeypatch)
    studio_db.outreach_voice_vendor_reads.docs.append({'_id': 'private-identifier', 'workspace_id': 'w',
        'voice_id': profile['id'], 'status': 'private-vendor-header'})
    view = await VoiceVendorEvidence(studio_db).inspect('w', profile['id'])
    assert 'private-' not in json.dumps(view) and view['reads'][0]['status'] == 'review_required'
