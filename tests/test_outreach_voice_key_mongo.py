"""Scoped voice workers through actual majority Mongo transactions and indexes."""
import asyncio
from contextvars import ContextVar
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock
import httpx
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db.indexes import ensure_voice_studio_indexes
from outreach.core import suppression, voice_key_custody
from outreach.core.voice_studio import VoiceStudio, now
from outreach.core.voice_preparation import VoicePreparation
from outreach.core.voice_cloner import generate_mock_voice_wav
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_voice_preparation import voice_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_key_custody import installed
from tests.test_outreach_voice_studio_provider import Stream

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


@pytest_asyncio.fixture
async def key_db(studio_db, voice_db, scoped, monkeypatch, request):
    await installed(monkeypatch)
    path = request.param
    source = studio_db if path == 'studio' else voice_db
    if path == 'campaign': source.outreach_voices.docs[0]['provider_source_digest'] = voice_key_custody.source_digest()
    # Deliberately use production-default naive UTC BSON timestamp decoding.
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_unravler_voice_key_' + uuid.uuid4().hex]
    for name, collection in source.collections.items():
        if collection.docs: await db[name].insert_many(collection.docs)
    await ensure_voice_studio_indexes(db)
    try: yield db, path
    finally:
        await client.drop_database(db.name)
        client.close()


async def queued(db, path):
    if path == 'studio':
        return await VoiceStudio(db).queue('w', 'actor', 'clone', 'request-1', name='Voice',
            audio=generate_mock_voice_wav(duration_s=20), consent=True)
    return await VoicePreparation(db).queue('w', 'l', 'human')


def service(db, path):
    return VoiceStudio(db) if path == 'studio' else VoicePreparation(db)


@pytest.mark.parametrize('key_db', ['studio', 'campaign'], indirect=True)
async def test_concurrent_workers_open_outside_transactions_and_send_once(key_db, scoped, monkeypatch):
    db, path = key_db
    inside = ContextVar('inside_voice_transaction', default=False)
    original = suppression.mutate_suppression
    async def transaction(database, workspace, callback):
        async def marked(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await original(database, workspace, marked)
    monkeypatch.setattr(suppression, 'mutate_suppression', transaction)
    original_open, original_seal = scoped.open, scoped.seal
    async def open_key(*args):
        assert not inside.get()
        return await original_open(*args)
    async def seal_key(*args):
        assert not inside.get()
        return await original_seal(*args)
    monkeypatch.setattr(scoped, 'open', open_key)
    monkeypatch.setattr(scoped, 'seal', seal_key)
    jobs = await asyncio.gather(*(queued(db, path) for _ in range(4)))
    assert len({job['_id'] for job in jobs}) == 1
    seen = []
    def handle(request):
        assert not inside.get()
        seen.append(request)
        body = b'{"voice_id":"remote","requires_verification":false}' if path == 'studio' else bytes(32000)
        return httpx.Response(200, headers={'content-type': 'application/json' if path == 'studio' else 'audio/pcm'}, stream=Stream(body))
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_client(**kw, transport=httpx.MockTransport(handle)))
    await asyncio.gather(*(service(db, path).run('w', jobs[0]['_id']) for _ in range(4)))
    assert len(seen) == 1 and seen[0].headers['xi-api-key'] == 'private-voice-key'
    collection = db.outreach_voice_studio_jobs if path == 'studio' else db.outreach_voice_preparation_jobs
    assert (await collection.find_one({}))['status'] == ('completed' if path == 'studio' else 'prepared')


@pytest.mark.parametrize('key_db', ['studio', 'campaign'], indirect=True)
async def test_rotation_during_decryption_has_no_budget_or_submission(key_db, scoped, monkeypatch):
    db, path = key_db; job = await queued(db, path)
    original = scoped.open
    async def rotated(envelope, context):
        value = await original(envelope, context)
        if context.purpose == 'voice_provider_key': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'replacement')
        return value
    monkeypatch.setattr(scoped, 'open', rotated)
    provider = AsyncMock()
    result = await service(db, path).run('w', job['_id'], **({'provider': provider} if path == 'studio' else {'generator': provider}))
    assert result['status'] in {'stopped', 'blocked'}
    provider.assert_not_awaited()
    assert await db.outreach_voice_studio_budgets.count_documents({}) == 0
    assert await db.outreach_voice_preparation_budgets.count_documents({}) == 0


@pytest.mark.parametrize('key_db', ['studio', 'campaign'], indirect=True)
async def test_unknown_marker_recovery_never_opens_key_or_calls(key_db, scoped, monkeypatch):
    db, path = key_db; job = await queued(db, path)
    collection = db.outreach_voice_studio_jobs if path == 'studio' else db.outreach_voice_preparation_jobs
    await collection.update_one({'_id': job['_id']}, {'$set': {'status': 'possible' if path == 'studio' else 'generating',
        'owner': 'interrupted', 'lease_until': now() - timedelta(seconds=1), 'claim_expires_at': now() - timedelta(seconds=1)}})
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    provider = AsyncMock()
    assert (await service(db, path).run('w', job['_id'], **({'provider': provider} if path == 'studio' else {'generator': provider})))['status'] == 'held_outcome'
    spy.assert_not_awaited(); provider.assert_not_awaited()


@pytest.mark.parametrize('key_db', ['studio', 'campaign'], indirect=True)
async def test_rotation_after_receipt_never_adopts_new_source_or_resends(key_db, scoped, monkeypatch):
    db, path = key_db; job = await queued(db, path)
    calls = []
    async def provider(request):
        calls.append(request)
        monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'new-generation')
        return {'voice_id': 'remote'} if path == 'studio' else generate_mock_voice_wav()
    result = await service(db, path).run('w', job['_id'], **({'provider': provider} if path == 'studio' else {'generator': provider}))
    assert result['status'] == ('held_received' if path == 'studio' else 'superseded')
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    await service(db, path).run('w', job['_id'], **({'provider': provider} if path == 'studio' else {'generator': provider}))
    assert len(calls) == 1
    spy.assert_not_awaited()
    if path == 'studio':
        saved = await db.outreach_voice_studio_jobs.find_one({})
        assert saved['receipt']['voice_id'] == 'remote'
        assert (await db.outreach_voices.find_one({}))['status'] != 'active'
    else:
        assert await db.outreach_voice_artifacts.count_documents({}) == 0
