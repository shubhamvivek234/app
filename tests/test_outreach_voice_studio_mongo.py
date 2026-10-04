"""Actual majority transactions, indexes, acknowledgement loss and erasure."""
import asyncio
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from db.indexes import ensure_voice_studio_indexes
from outreach.core import suppression
from outreach.core.voice_studio import VoiceStudio, now, publish_studio_jobs
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_voice_studio import studio_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]

@pytest_asyncio.fixture
async def real_studio(studio_db):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client['test_unravler_studio_' + uuid.uuid4().hex]
    for name, source in studio_db.collections.items():
        if source.docs: await db[name].insert_many(source.docs)
    await ensure_voice_studio_indexes(db)
    try: yield db
    finally:
        await client.drop_database(db.name)
        client.close()


async def queued(db, request='request-1'):
    return await VoiceStudio(db).queue('w', 'actor', 'clone', request, name='My voice',
        audio=generate_mock_voice_wav(duration_s=20), consent=True)


async def test_concurrent_same_request_and_workers_have_one_call(real_studio):
    db = real_studio; service = VoiceStudio(db)
    jobs = await asyncio.gather(*(queued(db) for _ in range(5)))
    assert len({j['_id'] for j in jobs}) == 1
    assert await db.outreach_voices.count_documents({}) == 1
    provider = AsyncMock(return_value={'voice_id': 'remote'})
    await asyncio.gather(*(service.run('w', jobs[0]['_id'], provider=provider) for _ in range(5)))
    provider.assert_awaited_once()
    profile = await db.outreach_voices.find_one({})
    assert profile['status'] == 'active' and not profile.get('studio_job_id')
    assert (await db.outreach_voice_studio_jobs.find_one({}))['status'] == 'completed'


async def test_concurrent_quota_is_atomic(real_studio):
    results = await asyncio.gather(*(queued(real_studio, 'request-' + str(i)) for i in range(7)), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 5
    assert await real_studio.outreach_voices.count_documents({}) == 5


async def test_possible_crash_marker_holds_without_http(real_studio):
    job = await queued(real_studio)
    await real_studio.outreach_voice_studio_jobs.update_one({'_id': job['_id']}, {'$set': {
        'status': 'possible', 'owner': 'old', 'lease_until': now() - timedelta(seconds=1)}})
    provider = AsyncMock()
    assert (await VoiceStudio(real_studio).run('w', job['_id'], provider=provider))['status'] == 'held_outcome'
    provider.assert_not_awaited()
    assert await real_studio.outreach_voices.count_documents({}) == 1


async def test_lost_insert_ack_returns_same_durable_job(real_studio, monkeypatch):
    original = suppression.mutate_suppression
    async def lost(db, ws, callback):
        value = await original(db, ws, callback)
        if callback.__name__ == 'save': raise RuntimeError('lost acknowledgement')
        return value
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    first = await queued(real_studio)
    assert (await queued(real_studio))['_id'] == first['_id']
    assert await real_studio.outreach_voices.count_documents({}) == 1


async def test_saved_receipt_recovers_without_provider(real_studio, monkeypatch):
    service = VoiceStudio(real_studio); job = await queued(real_studio)
    original = service._finish
    monkeypatch.setattr(service, '_finish', AsyncMock(side_effect=RuntimeError('crash after receipt')))
    provider = AsyncMock(return_value={'voice_id': 'remote'})
    with pytest.raises(RuntimeError): await service.run('w', job['_id'], provider=provider)
    assert (await real_studio.outreach_voice_studio_jobs.find_one({}))['status'] == 'received'
    monkeypatch.setattr(service, '_finish', original)
    assert (await service.run('w', job['_id'], provider=provider))['status'] == 'completed'
    provider.assert_awaited_once()


async def test_strict_indexes_have_no_ttl_and_unique_active_owner(real_studio):
    job = await queued(real_studio)
    assert all('expireAfterSeconds' not in v for v in (await real_studio.outreach_voice_studio_jobs.index_information()).values())
    with pytest.raises(DuplicateKeyError): await real_studio.outreach_voice_studio_jobs.insert_one({**job, '_id': 'other'})
    await VoiceStudio(real_studio).cancel('w', job['_id'], 'actor')
    await queued(real_studio, 'request-2')


async def test_stopped_erasure_scrubs_content_and_retains_remote_cleanup(real_studio):
    db = real_studio; service = VoiceStudio(db); job = await queued(db)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = await db.outreach_voices.find_one({})
    preview = await service.queue('w', 'actor', 'preview', 'preview-1', voice_id=profile['id'], script='Hi')
    await service.run('w', preview['_id'], provider=AsyncMock(return_value={'audio': generate_mock_voice_wav()}))
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'actor'})
    erasure = OutreachErasure(db)
    await erasure.request('w', 'actor')
    assert not (await db.outreach_voice_studio_jobs.find_one({'_id': preview['_id']})).get('result_enc')
    inspection = await erasure.inspect('w')
    await erasure.finish('w', 'operator', 'All test workspace writers drained', workers_drained=True, expected_digest=inspection['review_digest'])
    holds = await db.outreach_erasure_holds.find({}).to_list(100)
    assert any(h.get('provider_voice_id') == 'remote' and h['kind'] == 'remote_voice_cleanup' for h in holds)
    assert not await db.outreach_voice_studio_jobs.count_documents({})
    assert not any('input_enc' in h or 'result_enc' in h or 'My voice' in str(h) for h in holds)


async def test_membership_change_during_open_blocks_http(real_studio, monkeypatch):
    from outreach.core import voice_studio
    service = VoiceStudio(real_studio); job = await queued(real_studio)
    opening = voice_studio.open_blob
    async def changed(*args):
        raw = await opening(*args)
        await real_studio.workspace_members.update_one({'workspace_id': 'w'}, {'$set': {'role': 'viewer'}})
        return raw
    monkeypatch.setattr(voice_studio, 'open_blob', changed)
    provider = AsyncMock()
    assert (await service.run('w', job['_id'], provider=provider))['status'] == 'stopped'
    provider.assert_not_awaited()


@pytest.mark.parametrize('stage', ['after_response', 'after_receipt'])
async def test_sigkill_after_real_loopback_call_never_replays(real_studio, stage):
    import base64
    import subprocess
    import threading
    import sys
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from utils import encryption
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            calls.append(self.path)
            body = b'{"voice_id":"remote","requires_verification":false}'
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    job = await queued(real_studio)
    env = {**os.environ, 'UNRAVLER_STUDIO_DRILL': '1',
        'UNRAVLER_STUDIO_ENDPOINT': f'http://127.0.0.1:{server.server_port}/clone',
        'ENCRYPTION_KEY': base64.urlsafe_b64encode(encryption._fernet._signing_key + encryption._fernet._encryption_key).decode()}
    proc = subprocess.Popen([sys.executable, '-m', 'tests.outreach_voice_studio_harness', real_studio.name, job['_id'], stage], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            control = await real_studio.drill_controls.find_one({'_id': job['_id']})
            if control and control.get('checkpoint') == stage: break
            if proc.poll() is not None: pytest.fail('Isolated Studio worker exited before checkpoint')
            await asyncio.sleep(.05)
        else: pytest.fail('Isolated Studio worker did not reach checkpoint')
        proc.kill(); await asyncio.to_thread(proc.wait, timeout=5)
        assert calls == ['/clone']
        await real_studio.outreach_voice_studio_jobs.update_one({'_id': job['_id']}, {'$set': {'lease_until': now() - timedelta(seconds=1)}})
        provider = AsyncMock()
        result = await VoiceStudio(real_studio).run('w', job['_id'], provider=provider)
        assert result['status'] == ('held_outcome' if stage == 'after_response' else 'completed')
        provider.assert_not_awaited()
        assert calls == ['/clone']
    finally:
        if proc.poll() is None: proc.kill(); await asyncio.to_thread(proc.wait, timeout=5)
        await asyncio.to_thread(server.shutdown); server.server_close(); thread.join(timeout=2)


async def test_production_default_datetime_codec_preserves_clone_and_preview(studio_db):
    # Production db/mongo.py uses the default naive UTC codec, not tz_aware=True.
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_unravler_studio_codec_' + uuid.uuid4().hex]
    try:
        for name, source in studio_db.collections.items():
            if source.docs: await db[name].insert_many(source.docs)
        await ensure_voice_studio_indexes(db)
        service = VoiceStudio(db); job = await queued(db)
        profile = await db.outreach_voices.find_one({})
        assert profile['consent']['asserted_at'].tzinfo is None
        provider = AsyncMock(return_value={'voice_id': 'remote'})
        assert (await service.run('w', job['_id'], provider=provider))['status'] == 'completed'
        provider.assert_awaited_once()
        preview = await service.queue('w', 'actor', 'preview', 'preview-codec', voice_id=profile['id'], script='Hi')
        audio = generate_mock_voice_wav()
        assert (await service.run('w', preview['_id'], provider=AsyncMock(return_value={'audio': audio})))['status'] == 'completed'
        assert await service.preview('w', preview['_id'], 'actor') == audio
    finally:
        await client.drop_database(db.name); client.close()
