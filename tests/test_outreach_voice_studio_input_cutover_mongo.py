"""Real snapshot/majority Studio input closure and permanent evidence."""
import asyncio
from datetime import timedelta
import os
import shutil
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
import pytest
import pytest_asyncio

from outreach.core import suppression, voice_studio_input_cutover as cutover
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.erasure import OutreachErasure
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_studio import VoiceStudio, now
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_voice_studio_input_cutover import FLAGS, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local replica set is opt-in')]


@pytest_asyncio.fixture
async def real_pending(studio_db, monkeypatch):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_studio_input_cutover_' + uuid.uuid4().hex]
    try:
        for name, source in studio_db.collections.items():
            if source.docs: await db[name].insert_many(source.docs)
        await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'actor'})
        await VoiceStudio(db).queue('w', 'actor', 'clone', 'request-1', name='My voice',
            audio=generate_mock_voice_wav(duration_s=20), consent=True)
        await db.outreach_accounts.insert_one({'_id': 'account', 'id': 'sender', 'workspace_id': 'w',
            'status': 'connected', 'credential_generation': 'original-cookie'})
        await db.outreach_campaigns.insert_one({'_id': 'campaign', 'workspace_id': 'w', 'status': 'active',
            'authorization_revision': 3, 'auto_launch_enabled': True})
        for flag in FLAGS: monkeypatch.setenv(flag, 'false')
        yield db
    finally:
        await client.drop_database(db.name); client.close()


async def job(db):
    return await db.outreach_voice_studio_jobs.find_one({'workspace_id': 'w', 'status': {'$in': ['queued', 'preparing', 'review_stopped']}})


async def inspect(db):
    original = await job(db)
    return await cutover.VoiceStudioInputCutover(db).inspect('w', original['_id'])


async def stop(db, view=None):
    view = view or await inspect(db)
    return await cutover.VoiceStudioInputCutover(db).stop('w', view['job_id'], 'operator', EVIDENCE,
        view['digest'], workers_drained=True)


@pytest.mark.parametrize('state', ['queued', 'preparing'])
async def test_native_bson_stop_preserves_tokens_budget_and_idempotent_job(real_pending, state):
    db = real_pending; original = await job(db)
    if state == 'preparing':
        stamp = now() - timedelta(minutes=4)
        changes = {field: original[field] - timedelta(minutes=4) for field in
            ('created_at', 'updated_at', 'next_publish_at', 'next_recovery_at', 'authorization_expires_at')}
        changes.update(status='preparing', owner='original-owner', lease_until=stamp + timedelta(minutes=2),
            **{'consent.asserted_at': changes['created_at']})
        await db.outreach_voice_studio_jobs.update_one({'workspace_id': 'w', '_id': original['_id']}, {'$set': changes})
        await db.outreach_voices.update_one({'workspace_id': 'w'}, {'$set': {'created_at': changes['created_at'],
            'updated_at': changes['created_at'], 'consent.asserted_at': changes['created_at']}})
        from outreach.core.voice_studio import profile_identity
        await db.outreach_voice_studio_jobs.update_one({'workspace_id': 'w', '_id': original['_id']}, {'$set': {
            'profile_identity': profile_identity(await db.outreach_voices.find_one({'workspace_id': 'w'}))}})
    await db.outreach_sender_execution.insert_one({'workspace_id': 'w', '_id': 'execution', 'sender_id': 'sender',
        'status': 'held', 'owner_token': 'unknown-owner', 'physical_request_token': 'unknown-physical',
        'expires_at': now()-timedelta(minutes=1)})
    await db.outreach_voice_studio_budgets.insert_one({'workspace_id': 'w', '_id': 'budget', 'calls': 4})
    assert (await job(db))['created_at'].tzinfo is None
    from db.indexes import create_all_indexes
    monkey_db_name = os.environ.get('DB_NAME')
    os.environ['DB_NAME'] = db.name
    try: await create_all_indexes(db.client)
    finally:
        if monkey_db_name is None: os.environ.pop('DB_NAME', None)
        else: os.environ['DB_NAME'] = monkey_db_name
    view = await inspect(db); assert not view['blockers']
    assert (await stop(db, view))['current_matches']
    assert not await db.outreach_voices.find_one({'workspace_id': 'w'})
    execution = await db.outreach_sender_execution.find_one({'workspace_id': 'w'})
    assert execution['physical_request_token'] == 'unknown-physical' and execution['owner_token'] == 'unknown-owner'
    assert execution['permission']['latched'] and (await db.outreach_voice_studio_budgets.find_one({'workspace_id':'w'}))['calls'] == 4
    assert (await stop(db, view))['current_matches']
    provider = AsyncMock()
    await VoiceStudio(db).run('w', view['job_id'], provider=provider)
    provider.assert_not_awaited()
    indexes = await db.outreach_credential_migrations.index_information()
    assert indexes['voice_studio_input_stop_original_v1']['unique']
    assert all('expireAfterSeconds' not in row for row in indexes.values())


async def test_preview_cleanup_latches_profile_without_changing_consent_or_vendor_resource(real_pending, monkeypatch):
    db = real_pending; first = await job(db); monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    service = VoiceStudio(db)
    await service.run('w', first['_id'], provider=AsyncMock(return_value={'voice_id': 'vendor_voice'}))
    await service.queue('w', 'actor', 'preview', 'preview-1', voice_id=first['voice_id'], script='Hello private text')
    profile = await db.outreach_voices.find_one({'workspace_id': 'w'})
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'false')
    assert (await stop(db))['current_matches']
    current = await db.outreach_voices.find_one({'workspace_id': 'w'})
    assert current['studio_review_required'] and current['consent'] == profile['consent']
    assert current['status'] == 'active' and current['elevenlabs_voice_id'] == profile['elevenlabs_voice_id']
    assert current['revision'] == profile['revision'] + 1 and 'studio_job_id' not in current


@pytest.mark.parametrize('target', ['profile', 'job', 'receipt', 'stop'])
async def test_projection_failure_rolls_back_stop_scrub_and_profile_cleanup(real_pending, monkeypatch, target):
    from outreach.core.suppression import SuppressionCollection
    update, insert, delete = SuppressionCollection.update_one, SuppressionCollection.insert_one, SuppressionCollection.delete_one
    async def failed_update(self, *args, **kwargs):
        if (target == 'job' and self.collection.name == 'outreach_voice_studio_jobs'
                or target == 'stop' and self.collection.name == 'outreach_campaigns'): raise RuntimeError('Owned failure')
        return await update(self, *args, **kwargs)
    async def failed_insert(self, *args, **kwargs):
        if target == 'receipt' and self.collection.name == 'outreach_credential_migrations': raise RuntimeError('Owned failure')
        return await insert(self, *args, **kwargs)
    async def failed_delete(self, *args, **kwargs):
        if target == 'profile' and self.collection.name == 'outreach_voices': raise RuntimeError('Owned failure')
        return await delete(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', failed_update)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', failed_insert)
    monkeypatch.setattr(SuppressionCollection, 'delete_one', failed_delete)
    with pytest.raises(RuntimeError): await stop(real_pending)
    assert (await job(real_pending))['input_enc'].startswith('gAAAAA')
    assert await real_pending.outreach_voices.find_one({'workspace_id': 'w'})
    assert (await real_pending.outreach_campaigns.find_one({'workspace_id': 'w'}))['status'] == 'active'
    assert not await real_pending.outreach_credential_migrations.find_one({'workspace_id': 'w'})


@pytest.mark.parametrize('fault', ['profile', 'owner', 'receipt', 'campaign'])
async def test_stale_inspection_preserves_newer_state(real_pending, fault):
    db = real_pending; view = await inspect(db)
    if fault == 'profile': await db.outreach_voices.update_one({'workspace_id':'w'}, {'$set': {'assigned_account_ids':['replacement']}})
    if fault == 'owner': await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w'}, {'$set': {'owner':'replacement'}})
    if fault == 'receipt': await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w'}, {'$set': {'receipt':{'unproven':True}}})
    if fault == 'campaign': await db.outreach_campaigns.update_one({'workspace_id':'w'}, {'$inc': {'authorization_revision':1}})
    with pytest.raises(CustodyUnavailable): await stop(db, view)
    assert 'input_enc' in await job(db) and not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})


@pytest.mark.parametrize('change', ['gate', 'policy'])
async def test_final_await_configuration_change_rolls_back(real_pending, monkeypatch, change):
    saved = cutover.VoiceStudioInputCutover._saved
    async def changed(*args):
        result = await saved(*args)
        monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED' if change == 'gate' else 'OUTREACH_CUSTODY_ENVIRONMENT_ID',
            'true' if change == 'gate' else 'replacement')
        return result
    monkeypatch.setattr(cutover.VoiceStudioInputCutover, '_saved', changed)
    with pytest.raises(CustodyUnavailable): await stop(real_pending)
    assert 'input_enc' in await job(real_pending)
    assert (await real_pending.outreach_campaigns.find_one({'workspace_id':'w'}))['status'] == 'active'
    assert not await real_pending.outreach_credential_migrations.find_one({'workspace_id':'w'})


async def test_lost_ack_retry_uses_receipt_without_stopping_replacement(real_pending, monkeypatch):
    db = real_pending; view = await inspect(db); mutate = suppression.mutate_suppression
    async def lost(*args):
        await mutate(*args)
        raise TimeoutError('Owned acknowledgement loss')
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    with pytest.raises(TimeoutError): await stop(db, view)
    await db.outreach_accounts.update_one({'workspace_id':'w'}, {'$set': {'status':'replacement-state'}})
    assert (await stop(db, view))['current_matches']
    assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status'] == 'replacement-state'


async def test_guarded_concurrent_receipt_precedes_second_snapshot(real_pending, monkeypatch):
    db = real_pending; view = await inspect(db); mutate = suppression.mutate_suppression
    arrived, release = asyncio.Event(), asyncio.Event(); paused = False
    async def delayed(*args):
        nonlocal paused
        if not paused: paused = True; arrived.set(); await release.wait()
        return await mutate(*args)
    monkeypatch.setattr(suppression, 'mutate_suppression', delayed)
    first = asyncio.create_task(stop(db, view))
    try:
        await asyncio.wait_for(arrived.wait(), 5); winner = await stop(db, view)
    finally: release.set()
    assert await first == winner
    assert await db.outreach_credential_migrations.count_documents({'workspace_id':'w'}) == 1
    assert (await db.outreach_campaigns.find_one({'workspace_id':'w'}))['authorization_revision'] == 4


async def test_other_proven_queued_input_can_be_stopped_separately(real_pending, monkeypatch):
    db = real_pending; first = await job(db)
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    second = await VoiceStudio(db).queue('w', 'actor', 'clone', 'request-2', name='Other voice',
        audio=generate_mock_voice_wav(duration_s=20), consent=True)
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'false')
    await stop(db)
    remaining = await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w','_id':second['_id']})
    assert remaining['status'] == 'queued' and remaining['input_enc']
    view = await cutover.VoiceStudioInputCutover(db).inspect('w', second['_id'])
    await stop(db, view)
    assert (await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w','_id':first['_id']}))['status'] == 'review_stopped'


async def test_erasure_retains_minimal_history_and_closed_workspace_cannot_recreate_job(real_pending):
    db = real_pending; view = await inspect(db); await stop(db, view)
    deletion = OutreachErasure(db); await deletion.request('w','actor'); inspected = await deletion.inspect('w')
    await deletion.finish('w','operator','All workspace writers and caches drained for the owned local fixture.',
        workers_drained=True, expected_digest=inspected['review_digest'])
    hold = await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'voice_studio_input_stop'})
    assert hold and hold['provenance'] == 'unsubmitted_studio_input_stop' and not hold['activation_allowed']
    assert all(private not in str(hold) for private in ('Hello', 'gAAAAA', 'vs1:', 'original-cookie', 'vendor_voice'))
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    with pytest.raises((CustodyUnavailable, suppression.SuppressionUnavailable)): await stop(db, view)
    assert not await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w'})


async def test_retention_first_strict_index_denies_duplicate_original_stops(real_pending, monkeypatch):
    db = real_pending; original = await job(db)
    row = {'workspace_id':'w','kind':'voice_studio_input_stop','job_id':original['_id']}
    await db.outreach_credential_migrations.insert_many([dict(row),dict(row)])
    await db.outreach_credential_migrations.create_index('at',expireAfterSeconds=60)
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME', db.name)
    with pytest.raises(OperationFailure): await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in value for value in (await db.outreach_credential_migrations.index_information()).values())


async def test_actual_standalone_denies_before_stop_or_scrub(real_pending, tmp_path):
    with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    root = tmp_path/'standalone'; root.mkdir()
    process = subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port',str(port),
        '--bind_ip','127.0.0.1','--logpath',str(tmp_path/'standalone.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}/?directConnection=true',serverSelectionTimeoutMS=200)
    db = client['test_v233_standalone']
    try:
        for _ in range(50):
            try: await client.admin.command('ping'); break
            except Exception: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone did not start')
        for name in await real_pending.list_collection_names():
            rows = await real_pending[name].find({}).to_list(length=100)
            if rows: await db[name].insert_many(rows)
        view = await inspect(db); assert not view['blockers']
        with pytest.raises(suppression.SuppressionUnavailable): await stop(db, view)
        assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status'] == 'connected'
        assert 'input_enc' in await job(db)
    finally:
        try: await client.drop_database(db.name)
        finally: client.close(); process.terminate(); process.wait(timeout=10); shutil.rmtree(root)
