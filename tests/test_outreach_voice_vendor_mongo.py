"""Real snapshot/majority transactions, receipt races, indexes and erasure."""
import asyncio
from datetime import timedelta
import os
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError, PyMongoError
from db.indexes import ensure_voice_studio_indexes
from outreach.core import suppression, voice_key_custody
from outreach.core.voice_studio import now
from outreach.core.voice_source_review import VoiceSourceReview, PreviousKey
from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
from outreach.core.voice_studio_review import VoiceStudioReview
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_voice_studio_review_mongo import review_db
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_source_mongo import ready
from tests.test_outreach_voice_vendor_evidence import METADATA, EVIDENCE, KEY

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


async def prepared(db, monkeypatch):
    profile, prior = await ready(db, monkeypatch)
    source = VoiceSourceReview(db); view = await source.inspect('w', profile['id'])
    await source.migrate('w', profile['id'], 'operator', EVIDENCE, view['review_digest'], workers_drained=True,
        previous_key=PreviousKey(prior.storage, prior.policy[0], prior.generation))
    return await db.outreach_voices.find_one({'id': profile['id']})


async def capture(db, profile, provider=None, digest=None):
    service = VoiceVendorEvidence(db)
    digest = digest or (await service.inspect('w', profile['id']))['review_digest']
    return await service.capture('w', profile['id'], 'operator', EVIDENCE, digest, workers_drained=True,
        provider=provider or AsyncMock(return_value=METADATA))


async def release(db, profile, job_id, digest=None):
    service = VoiceVendorEvidence(db)
    digest = digest or (await service.inspect('w', profile['id'], job_id))['review_digest']
    return await service.release('w', profile['id'], job_id, 'operator', EVIDENCE, digest, workers_drained=True)


async def test_real_capture_and_release_keep_original_receipts_and_unrelated_tokens(review_db, scoped, monkeypatch):
    db = review_db; profile = await prepared(db, monkeypatch)
    original = await db.outreach_voice_studio_jobs.find_one({})
    job = await capture(db, profile)
    saved = await db.outreach_voice_vendor_reads.find_one({'_id': job['job_id']})
    assert saved['receipt']['received_at'].tzinfo is None and not saved['mutation']
    result = await release(db, profile, job['job_id'])
    assert result['current_matches'] and not result['activation_allowed']
    after = await db.outreach_voices.find_one({'id': profile['id']})
    assert after['status'] == 'active' and not after['studio_review_required'] and after['revision'] == profile['revision'] + 1
    assert after['consent'] == profile['consent']
    execution = await db.outreach_sender_execution.find_one({'workspace_id': 'w'})
    assert execution['physical_request_token'] == 'held' and execution['permission']['latched']
    assert (await db.outreach_voice_studio_jobs.find_one({}))['receipt'] == original['receipt']


async def test_concurrent_capture_and_release_each_commit_once(review_db, scoped, monkeypatch):
    db = review_db; profile = await prepared(db, monkeypatch); service = VoiceVendorEvidence(db)
    provider = AsyncMock(return_value=METADATA)
    digest = (await service.inspect('w', profile['id']))['review_digest']
    jobs = await asyncio.gather(*(capture(db, profile, provider, digest) for _ in range(4)))
    assert len({job['job_id'] for job in jobs}) == 1 and provider.await_count == 1
    job_id = jobs[0]['job_id']; digest = (await service.inspect('w', profile['id'], job_id))['review_digest']
    results = await asyncio.gather(*(release(db, profile, job_id, digest) for _ in range(4)))
    assert all(result == results[0] for result in results)
    assert (await db.outreach_voices.find_one({'id': profile['id']}))['revision'] == profile['revision'] + 1


@pytest.mark.parametrize('stage', ['prepare', 'authorize', 'save', 'release'])
async def test_committed_ack_loss_never_reopens_keys_or_repeats_get(review_db, scoped, monkeypatch, stage):
    db = review_db; profile = await prepared(db, monkeypatch); service = VoiceVendorEvidence(db)
    original = suppression.mutate_suppression; lost = False
    async def control(database, workspace, operation):
        nonlocal lost
        result = await original(database, workspace, operation)
        name = 'apply' if stage == 'release' else stage
        if operation.__name__ == name and not lost:
            lost = True; raise RuntimeError('Lost acknowledgement')
        return result
    if stage != 'release': monkeypatch.setattr(suppression, 'mutate_suppression', control)
    digest = (await service.inspect('w', profile['id']))['review_digest']; provider = AsyncMock(return_value=METADATA)
    if stage == 'prepare':
        with pytest.raises(RuntimeError): await capture(db, profile, provider, digest)
    else: await capture(db, profile, provider, digest)
    saved = await db.outreach_voice_vendor_reads.find_one({})
    assert saved['status'] == ('preparing' if stage == 'prepare' else 'possible' if stage == 'authorize' else 'received')
    if stage == 'release':
        digest = (await service.inspect('w', profile['id'], saved['_id']))['review_digest']
        monkeypatch.setattr(suppression, 'mutate_suppression', control)
        with pytest.raises(RuntimeError): await release(db, profile, saved['_id'], digest)
        assert (await release(db, profile, saved['_id'], digest))['current_matches']
    else:
        monkeypatch.setattr(voice_key_custody, 'prepare_key', AsyncMock(side_effect=AssertionError('No re-open')))
        assert (await capture(db, profile, provider, digest))['status'] == saved['status']
    assert provider.await_count == (0 if stage in {'prepare', 'authorize'} else 1)


@pytest.mark.parametrize('change', ['expired', 'config', 'flags'])
async def test_final_release_deadline_and_configuration_changes_roll_back(review_db, scoped, monkeypatch, change):
    import outreach.core.voice_vendor_evidence as module
    db = review_db; profile = await prepared(db, monkeypatch); job = await capture(db, profile)
    original = VoiceStudioReview._stop_authority; before = now()
    async def delayed(*args, **kwargs):
        await original(*args, **kwargs)
        if change == 'expired': monkeypatch.setattr(module, 'now', lambda: before + timedelta(minutes=16))
        elif change == 'config': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g3')
        else: monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setattr(VoiceStudioReview, '_stop_authority', delayed)
    with pytest.raises(ValueError): await release(db, profile, job['job_id'])
    after = await db.outreach_voices.find_one({'id': profile['id']})
    assert after['studio_review_required'] and after['revision'] == profile['revision']
    assert (await db.outreach_voice_vendor_reads.find_one({}))['status'] == 'received'


async def test_failed_release_journal_rolls_back_profile_and_stops(review_db, scoped, monkeypatch):
    db = review_db; profile = await prepared(db, monkeypatch); job = await capture(db, profile)
    await db.outreach_accounts.update_one({'_id': 'a'}, {'$set': {'status': 'active'}})
    await db.outreach_campaigns.update_one({'_id': 'c'}, {'$set': {'status': 'active'}})
    original = AsyncIOMotorCollection.update_one
    async def failed(collection, query, update, **kwargs):
        if collection.name == 'outreach_voice_vendor_reads' and update.get('$set', {}).get('status') == 'released':
            raise ValueError('Abort journal')
        return await original(collection, query, update, **kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection, 'update_one', failed)
    with pytest.raises(ValueError): await release(db, profile, job['job_id'])
    assert (await db.outreach_voices.find_one({'id': profile['id']}))['studio_review_required']
    assert (await db.outreach_accounts.find_one({'_id': 'a'}))['status'] == 'active'
    assert (await db.outreach_campaigns.find_one({'_id': 'c'}))['status'] == 'active'


async def test_real_key_open_and_get_are_outside_retryable_callbacks(review_db, scoped, monkeypatch):
    db = review_db; profile = await prepared(db, monkeypatch)
    original = suppression.mutate_suppression; opening = scoped.open; inside = False
    async def control(database, workspace, operation):
        async def callback(current):
            nonlocal inside
            inside = True
            try: return await operation(current)
            finally: inside = False
        return await original(database, workspace, callback)
    async def open_key(*args):
        assert not inside; return await opening(*args)
    async def provider(request):
        assert not inside and request['allowed'](); return METADATA
    monkeypatch.setattr(suppression, 'mutate_suppression', control)
    monkeypatch.setattr(scoped, 'open', open_key)
    assert (await capture(db, profile, provider))['status'] == 'received'


async def test_actual_unique_indexes_remove_ttl_before_strict_failure(review_db, scoped, monkeypatch):
    db = review_db
    await db.outreach_voice_vendor_reads.create_index('created_at', expireAfterSeconds=1, name='unsafe_ttl')
    rows = [{'_id': str(i), 'workspace_id': 'w', 'voice_id': 'v', 'inspection_digest': str(i), 'status': 'possible'} for i in range(2)]
    await db.outreach_voice_vendor_reads.drop_index('voice_vendor_active_v1')
    await db.outreach_voice_vendor_reads.insert_many(rows)
    with pytest.raises(DuplicateKeyError): await ensure_voice_studio_indexes(db)
    assert not any('expireAfterSeconds' in info for info in (await db.outreach_voice_vendor_reads.index_information()).values())


@pytest.mark.parametrize('received', [True, False])
async def test_erasure_keeps_only_minimal_vendor_evidence_and_read_uncertainty(review_db, scoped, monkeypatch, received):
    db = review_db; profile = await prepared(db, monkeypatch)
    provider = AsyncMock(return_value=METADATA) if received else AsyncMock(side_effect=TimeoutError('private metadata'))
    await capture(db, profile, provider)
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'actor'})
    service = OutreachErasure(db); await service.request('w', 'actor'); view = await service.inspect('w')
    await service.finish('w', 'operator', EVIDENCE, workers_drained=True, expected_digest=view['review_digest'])
    assert await db.outreach_voice_vendor_reads.count_documents({}) == 0
    hold = await db.outreach_erasure_holds.find_one({'source_collection': 'outreach_voice_vendor_reads'})
    assert hold['mutation'] is False and hold['activation_allowed'] is False
    assert hold['kind'] == ('voice_vendor_evidence' if received else 'unresolved_submission')
    assert all(value not in str(hold) for value in (KEY, 'original-remote', EVIDENCE, 'voice_verification', 'admin'))


async def test_actual_standalone_denies_capture_without_key_or_http(review_db, scoped, monkeypatch, tmp_path):
    db = review_db; profile = await prepared(db, monkeypatch)
    with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1', 27029)) != 0, 'Preserve existing service'
    root = tmp_path / 'standalone'; root.mkdir()
    process = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(root), '--port', '27029', '--bind_ip', '127.0.0.1',
        '--logpath', str(root / 'mongo.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true', serverSelectionTimeoutMS=500)
    target = client['test_unravler_vendor_sa_' + uuid.uuid4().hex]
    try:
        for _ in range(40):
            try: await client.admin.command('ping'); break
            except PyMongoError: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone failed to start')
        for name in await db.list_collection_names():
            rows = await db[name].find({}).to_list(length=200)
            if rows: await target[name].insert_many(rows)
        await ensure_voice_studio_indexes(target)
        monkeypatch.setattr(voice_key_custody, 'prepare_key', AsyncMock(side_effect=AssertionError('No key')))
        with pytest.raises(suppression.SuppressionUnavailable): await capture(target, profile)
        assert await target.outreach_voice_vendor_reads.count_documents({}) == 0
    finally:
        try: await client.drop_database(target.name)
        finally:
            client.close(); process.terminate(); process.wait(timeout=10)
