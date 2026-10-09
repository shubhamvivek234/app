"""Scoped campaign WAV authority through real disposable Mongo transactions."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import os
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from outreach.core import suppression, voice_key_custody
from outreach.core.authorization import authorization_snapshot
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.dispatch_authority import AuthorityDatabase, AuthorityCollection
from outreach.core.erasure import OutreachErasure
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_key_custody import installed
from tests.test_outreach_voice_preparation import voice_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


@pytest_asyncio.fixture
async def artifact_db(voice_db, scoped, monkeypatch):
    await installed(monkeypatch)
    voice_db.outreach_voices.docs[0]['provider_source_digest'] = voice_key_custody.source_digest()
    # Default codec deliberately returns naive UTC BSON datetimes.
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_voice_artifact_' + uuid.uuid4().hex]
    try:
        for name, source in voice_db.collections.items():
            if source.docs: await db[name].insert_many(source.docs)
        await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'human'})
        yield db
    finally:
        await client.drop_database(db.name)
        client.close()


async def prepared(db):
    job = await VoicePreparation(db).queue('w', 'l', 'human')
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    assert (await VoicePreparation(db).run('w', job['_id'], generator=generator))['status'] == 'prepared'
    clip = await VoiceArtifacts(db).prepare_load('w', job['_id'])
    return job, clip, generator


async def require_clip(db, clip):
    lead = await db.outreach_leads.find_one({'workspace_id': 'w', 'id': 'l'})
    campaign = await db.outreach_campaigns.find_one({'workspace_id': 'w', 'id': 'c'})
    account = await db.outreach_accounts.find_one({'workspace_id': 'w', 'id': 'a'})
    sequence = await db.outreach_sequences.find_one({'workspace_id': 'w', 'campaign_id': 'c'})
    expected = authorization_snapshot(campaign, account, sequence)
    base = await sequence_binding(db, 'w', 'l')
    content = {**base['content'], 'audio_digest': clip.document['audio_digest'],
               'voice_artifact_id': clip.document['_id'], 'voice_artifact_generation': clip.document['generation_id']}
    async def apply(current):
        authority = AuthorityDatabase(current.database, current.session, 'voice-artifact-test')
        result = await ContentApproval(authority).require_sequence(lead, expected, 'voice_note', content, voice_clip=clip)
        return result, authority.checks, authority.deadlines
    return await suppression.mutate_suppression(db, 'w', apply)


async def test_concurrent_generation_seals_once_outside_transaction_and_preserves_bson_identity(artifact_db, scoped, monkeypatch):
    inside = ContextVar('artifact_mongo_callback', default=False)
    original = suppression.mutate_suppression
    async def transact(db, workspace, callback):
        async def run(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await original(db, workspace, run)
    monkeypatch.setattr(suppression, 'mutate_suppression', transact)
    calls = []
    for operation in ('open', 'seal'):
        original_key = getattr(scoped, operation)
        async def keys(value, context, original_key=original_key):
            assert not inside.get()
            calls.append(context.purpose)
            return await original_key(value, context)
        monkeypatch.setattr(scoped, operation, keys)
    jobs = await asyncio.gather(*(VoicePreparation(artifact_db).queue('w', 'l', 'human') for _ in range(4)))
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    await asyncio.gather(*(VoicePreparation(artifact_db).run('w', jobs[0]['_id'], generator=generator) for _ in range(4)))
    generator.assert_awaited_once()
    assert calls.count('voice_artifact_key') == 1
    clip = await VoiceArtifacts(artifact_db).prepare_load('w', jobs[0]['_id'])
    assert clip.audio == generator.return_value and clip.matches(clip.document)
    assert (await VoicePreparation(artifact_db).queue('w', 'l', 'human'))['status'] == 'prepared'
    assert calls.count('voice_artifact_key') == 2


@pytest.mark.parametrize('change', ['generation', 'ciphertext', 'expiry'])
async def test_artifact_change_after_snapshot_read_orders_before_final_authority(artifact_db, scoped, monkeypatch, change):
    job, clip, _ = await prepared(artifact_db)
    original = AuthorityCollection.fence
    seen, release = asyncio.Event(), asyncio.Event()
    paused = False
    async def pause(self, doc, query):
        nonlocal paused
        if self.name == 'outreach_voice_artifacts' and not paused:
            paused = True; seen.set(); await release.wait()
        return await original(self, doc, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No KMS in authorization')))
    running = asyncio.create_task(require_clip(artifact_db, clip))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        edits = {'generation': {'generation_id': 'replacement'}, 'ciphertext': {'audio_enc': clip.document['audio_enc'] + 'bad'},
                 'expiry': {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}}
        await artifact_db.outreach_voice_artifacts.update_one({'_id': job['_id'], 'workspace_id': 'w'}, {'$set': edits[change]})
    finally: release.set()
    with pytest.raises(ValueError): await running
    scoped.open.assert_not_awaited()


async def test_database_only_authority_returns_exact_deadline_and_post_commit_policy_check(artifact_db, scoped, monkeypatch):
    _, clip, _ = await prepared(artifact_db)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No second open')))
    binding, checks, deadlines = await require_clip(artifact_db, clip)
    assert binding['context']['voice_artifact_generation'] == clip.document['generation_id']
    now = datetime.now(timezone.utc)
    assert checks and all(check(now) for check in checks)
    assert clip.document['expires_at'].replace(tzinfo=timezone.utc) in deadlines
    monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'changed-after-commit')
    assert not all(check(now) for check in checks)
    scoped.open.assert_not_awaited()


async def test_projection_failure_rolls_back_audio_and_never_repeats_paid_or_key_calls(artifact_db, scoped, monkeypatch):
    service = VoicePreparation(artifact_db)
    job = await service.queue('w', 'l', 'human')
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    seal = AsyncMock(wraps=scoped.seal)
    monkeypatch.setattr(scoped, 'seal', seal)
    original = ContentApproval.ensure
    monkeypatch.setattr(ContentApproval, 'ensure', AsyncMock(side_effect=RuntimeError('Interrupted local projection')))
    with pytest.raises(RuntimeError): await service.run('w', job['_id'], generator=generator)
    assert not await artifact_db.outreach_voice_artifacts.find_one({'workspace_id': 'w'})
    monkeypatch.setattr(ContentApproval, 'ensure', original)
    await artifact_db.outreach_voice_preparation_jobs.update_one({'_id': job['_id'], 'workspace_id': 'w'},
        {'$set': {'claim_expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert (await service.run('w', job['_id'], generator=generator))['status'] == 'held_outcome'
    generator.assert_awaited_once()
    assert len([call for call in seal.await_args_list if call.args[1].purpose == 'voice_artifact_key']) == 1


async def test_erasure_during_open_scrubs_ciphertext_and_denies_cached_audio(artifact_db, scoped, monkeypatch):
    job, _, _ = await prepared(artifact_db)
    original = scoped.open
    async def erase(value, context):
        result = await original(value, context)
        if context.purpose == 'voice_artifact_key': await OutreachErasure(artifact_db).request('w', 'human')
        return result
    monkeypatch.setattr(scoped, 'open', erase)
    with pytest.raises(ValueError): await VoiceArtifacts(artifact_db).load('w', job['_id'])
    row = await artifact_db.outreach_voice_artifacts.find_one({'workspace_id': 'w'})
    assert row['status'] == 'failed' and 'audio_enc' not in row


async def test_erasure_during_sealing_blocks_install_and_keeps_paid_job_evidence(artifact_db, scoped, monkeypatch):
    service = VoicePreparation(artifact_db)
    job = await service.queue('w', 'l', 'human')
    original = scoped.seal
    async def erase(value, context):
        result = await original(value, context)
        if context.purpose == 'voice_artifact_key': await OutreachErasure(artifact_db).request('w', 'human')
        return result
    monkeypatch.setattr(scoped, 'seal', erase)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    with pytest.raises(suppression.SuppressionUnavailable): await service.run('w', job['_id'], generator=generator)
    assert not await artifact_db.outreach_voice_artifacts.find_one({'workspace_id': 'w'})
    assert (await artifact_db.outreach_voice_preparation_jobs.find_one({'workspace_id': 'w'}))['status'] == 'generating'
    generator.assert_awaited_once()
