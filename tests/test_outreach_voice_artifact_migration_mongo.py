"""Actual stopped clip transactions, BSON, race/ack recovery and standalone denial."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
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

from outreach.core import suppression, voice_artifact_migration as migration, voice_key_custody
from outreach.core.content_approval import ContentApproval
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.erasure import OutreachErasure
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_preparation import voice_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local replica set is opt-in')]
EVIDENCE = 'a' * 64


@pytest_asyncio.fixture
async def real_old(voice_db, scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    voice_db.outreach_voices.docs[0]['provider_source_digest'] = voice_key_custody.source_digest()
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_voice_artifact_migration_' + uuid.uuid4().hex]
    try:
        for name, source in voice_db.collections.items():
            if source.docs: await db[name].insert_many(source.docs)
        await db.workspaces.insert_one({'workspace_id':'w','owner_id':'human'})
        job = await VoicePreparation(db).queue('w','l','human')
        assert (await VoicePreparation(db).run('w',job['_id'],generator=AsyncMock(return_value=generate_mock_voice_wav())))['status'] == 'prepared'
        approval = await db.outreach_content_approvals.find_one({'workspace_id':'w'})
        await ContentApproval(db).decide('w',approval['_id'],'human','approve',revision=1)
        for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_INTEGRATIONS_ENABLED',
                     'OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED'):
            monkeypatch.setenv(flag,'false')
        monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
        yield db
    finally:
        await client.drop_database(db.name); client.close()


async def inspection(db):
    row = await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})
    return await migration.VoiceArtifactMigration(db).inspect('w',row['_id'])


async def convert(db, view=None):
    view = view or await inspection(db)
    return await migration.VoiceArtifactMigration(db).migrate('w',view['artifact_id'],'operator',EVIDENCE,
        view['digest'],workers_drained=True)


async def test_bson_original_identity_receipt_indexes_and_key_work_after_committed_stop(real_old, scoped, monkeypatch):
    db = real_old
    original = await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})
    job = migration.stable(await db.outreach_voice_preparation_jobs.find_one({'workspace_id':'w'}))
    assert original['prepared_at'].tzinfo is None
    inside = ContextVar('artifact_migration_transaction',default=False)
    mutate, opening, seal = suppression.mutate_suppression, migration.open_legacy_audio, scoped.seal
    async def guarded(database,workspace,callback):
        async def apply(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await mutate(database,workspace,apply)
    async def opened(*args,**kwargs):
        assert not inside.get()
        assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status'] == 'paused'
        assert (await db.outreach_content_approvals.find_one({'workspace_id':'w'}))['status'] == 'pending'
        return await opening(*args,**kwargs)
    async def sealed(*args,**kwargs):
        assert not inside.get(); return await seal(*args,**kwargs)
    monkeypatch.setattr(suppression,'mutate_suppression',guarded)
    monkeypatch.setattr(migration,'open_legacy_audio',opened)
    monkeypatch.setattr(scoped,'seal',sealed)
    assert (await convert(db))['current_matches']
    current = migration.stable(await db.outreach_voice_artifacts.find_one({'workspace_id':'w'}))
    before = migration.stable(original)
    assert {key:value for key,value in before.items() if key!='audio_enc'} == {key:value for key,value in current.items() if key!='audio_enc'}
    assert await VoiceArtifacts(db).load('w',original['_id']) == generate_mock_voice_wav()
    assert migration.stable(await db.outreach_voice_preparation_jobs.find_one({'workspace_id':'w'})) == job
    from db.indexes import create_all_indexes
    await db.outreach_credential_migrations.create_index('at',expireAfterSeconds=60,name='unsafe_ttl')
    monkeypatch.setenv('DB_NAME',db.name); await create_all_indexes(db.client)
    indexes = await db.outreach_credential_migrations.index_information()
    assert indexes['voice_artifact_migration_generation_v1']['unique']
    assert all('expireAfterSeconds' not in row for row in indexes.values())


async def test_failed_key_keeps_committed_stop_and_original_record(real_old, monkeypatch):
    db = real_old
    original = await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})
    monkeypatch.setattr(migration,'seal_audio',AsyncMock(side_effect=CustodyUnavailable('Unavailable')))
    with pytest.raises(CustodyUnavailable): await convert(db)
    assert migration.stable(await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})) == migration.stable(original)
    assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status']=='paused'
    assert (await db.outreach_content_approvals.find_one({'workspace_id':'w'}))['status']=='pending'
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})


@pytest.mark.parametrize('target',['artifact','receipt','stop_projection'])
async def test_atomic_projection_failure_never_leaves_partial_ciphertext_or_receipt(real_old, monkeypatch,target):
    from outreach.core.suppression import SuppressionCollection
    update,insert = SuppressionCollection.update_one,SuppressionCollection.insert_one
    async def failed_update(self,*args,**kwargs):
        if (target=='artifact' and self.collection.name=='outreach_voice_artifacts'
                or target=='stop_projection' and self.collection.name=='outreach_content_approvals'):
            raise RuntimeError('Owned projection failure')
        return await update(self,*args,**kwargs)
    async def failed_insert(self,*args,**kwargs):
        if target=='receipt' and self.collection.name=='outreach_credential_migrations':
            raise RuntimeError('Owned receipt failure')
        return await insert(self,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',failed_update)
    monkeypatch.setattr(SuppressionCollection,'insert_one',failed_insert)
    with pytest.raises(RuntimeError): await convert(real_old)
    assert (await real_old.outreach_voice_artifacts.find_one({'workspace_id':'w'}))['audio_enc'].startswith('gAAAAA')
    assert not await real_old.outreach_credential_migrations.find_one({'workspace_id':'w'})
    expected = 'approved' if target=='stop_projection' else 'pending'
    assert (await real_old.outreach_content_approvals.find_one({'workspace_id':'w'}))['status']==expected


@pytest.mark.parametrize('fault',['artifact','job','permission','active_campaign','expiry','erasure','policy','gate','content_binding'])
async def test_change_during_seal_denies_overwrite_of_replacement_authority(real_old,monkeypatch,fault):
    db,seal = real_old,migration.seal_audio
    async def changed(*args,**kwargs):
        result = await seal(*args,**kwargs)
        if fault=='artifact': await db.outreach_voice_artifacts.update_one({'workspace_id':'w'},{'$set':{'generation_id':'replacement'}})
        if fault=='job': await db.outreach_voice_preparation_jobs.update_one({'workspace_id':'w'},{'$set':{'owner':'replacement'}})
        if fault=='permission': await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$set':{'permission.latched':False}})
        if fault=='active_campaign': await db.outreach_campaigns.update_one({'workspace_id':'w'},{'$set':{'status':'active'}})
        if fault=='expiry': await db.outreach_voice_artifacts.update_one({'workspace_id':'w'},{'$set':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}})
        if fault=='erasure': await OutreachErasure(db).request('w','human')
        if fault=='policy': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault=='gate': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        if fault=='content_binding': await db.outreach_content_approvals.update_one({'workspace_id':'w'},{'$set':{'binding.content.body':'replacement'}})
        return result
    monkeypatch.setattr(migration,'seal_audio',changed)
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)): await convert(db)
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    assert not (await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})).get('audio_enc','').startswith('va1:')


@pytest.mark.parametrize('fault',['policy','gate','expiry'])
async def test_late_awaited_saved_readback_rolls_back_before_commit(real_old,monkeypatch,fault):
    saved = migration.VoiceArtifactMigration._saved
    expiry = (await real_old.outreach_voice_artifacts.find_one({'workspace_id':'w'}))['expires_at'].replace(tzinfo=timezone.utc)
    async def changed(self,*args,**kwargs):
        result = await saved(self,*args,**kwargs)
        if fault=='policy': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault=='gate': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        if fault=='expiry': monkeypatch.setattr(migration,'now',lambda:expiry+timedelta(seconds=1))
        return result
    monkeypatch.setattr(migration.VoiceArtifactMigration,'_saved',changed)
    with pytest.raises(CustodyUnavailable): await convert(real_old)
    assert (await real_old.outreach_voice_artifacts.find_one({'workspace_id':'w'}))['audio_enc'].startswith('gAAAAA')
    assert not await real_old.outreach_credential_migrations.find_one({'workspace_id':'w'})


async def test_lost_final_ack_uses_receipt_without_open_seal_or_repeat_stop(real_old,monkeypatch):
    db = real_old; view = await inspection(db); mutate = suppression.mutate_suppression; calls = 0
    async def lost(*args,**kwargs):
        nonlocal calls
        calls += 1; result = await mutate(*args,**kwargs)
        if calls==2: raise RuntimeError('Owned final acknowledgement loss')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError): await convert(db,view)
    execution = await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    monkeypatch.setattr(migration,'open_legacy_audio',AsyncMock(side_effect=AssertionError('No opening')))
    monkeypatch.setattr(migration,'seal_audio',AsyncMock(side_effect=AssertionError('No sealing')))
    assert (await convert(db,view))['current_matches']
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'}) == execution


async def test_lost_stop_ack_requires_fresh_review_before_any_key_work(real_old,monkeypatch):
    db = real_old; view = await inspection(db); mutate = suppression.mutate_suppression
    async def lost(*args,**kwargs):
        await mutate(*args,**kwargs); raise RuntimeError('Owned stop acknowledgement loss')
    opening = AsyncMock(wraps=migration.open_legacy_audio)
    monkeypatch.setattr(migration,'open_legacy_audio',opening)
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError): await convert(db,view)
    opening.assert_not_awaited()
    monkeypatch.setattr(suppression,'mutate_suppression',mutate)
    with pytest.raises(CustodyUnavailable): await convert(db,view)
    assert (await convert(db))['current_matches']
    opening.assert_awaited_once()


async def test_guarded_concurrent_exact_receipt_precedes_old_source_and_key(real_old,monkeypatch):
    db = real_old; view = await inspection(db); mutate = suppression.mutate_suppression
    arrived,release = asyncio.Event(),asyncio.Event(); paused = False
    async def delayed(*args,**kwargs):
        nonlocal paused
        if not paused:
            paused=True;arrived.set();await release.wait()
        return await mutate(*args,**kwargs)
    opening = AsyncMock(wraps=migration.open_legacy_audio)
    monkeypatch.setattr(migration,'open_legacy_audio',opening)
    monkeypatch.setattr(suppression,'mutate_suppression',delayed)
    first = asyncio.create_task(convert(db,view))
    try:
        await asyncio.wait_for(arrived.wait(),5)
        winner = await convert(db,view)
    finally: release.set()
    assert await first == winner
    opening.assert_awaited_once()
    assert await db.outreach_credential_migrations.count_documents({'workspace_id':'w'})==1


async def test_ttl_style_removal_during_key_work_never_recreates_record(real_old,monkeypatch):
    seal = migration.seal_audio
    async def removed(*args,**kwargs):
        result = await seal(*args,**kwargs)
        await real_old.outreach_voice_artifacts.delete_many({'workspace_id':'w'})
        return result
    monkeypatch.setattr(migration,'seal_audio',removed)
    with pytest.raises(CustodyUnavailable): await convert(real_old)
    assert not await real_old.outreach_voice_artifacts.find_one({'workspace_id':'w'})
    assert not await real_old.outreach_credential_migrations.find_one({'workspace_id':'w'})


async def test_erasure_retains_only_minimal_migration_evidence_and_closed_tenant_cannot_reinstall(real_old,monkeypatch):
    db=real_old; view=await inspection(db)
    assert (await convert(db,view))['current_matches']
    deletion=OutreachErasure(db); await deletion.request('w','human')
    inspected=await deletion.inspect('w')
    await deletion.finish('w','operator','All writers and caches drained for local fixture.',
        workers_drained=True,expected_digest=inspected['review_digest'])
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'voice_artifact_custody_migration'})
    assert hold and not hold['activation_allowed'] and hold['provenance']=='strict_fernet_voice_artifact_conversion'
    for secret in ('gAAAAA','va1:','Hello','cookie'):
        assert secret not in str(hold)
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    monkeypatch.setattr(migration,'open_legacy_audio',AsyncMock(side_effect=AssertionError('No opening')))
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)): await convert(db,view)


async def test_retention_first_strict_duplicate_generation_denies_startup(real_old,monkeypatch):
    db=real_old; artifact=await db.outreach_voice_artifacts.find_one({'workspace_id':'w'})
    record={'workspace_id':'w','kind':'voice_artifact','artifact_id':artifact['_id'],'generation_digest':'a'*64}
    await db.outreach_credential_migrations.insert_many([dict(record),dict(record)])
    await db.outreach_credential_migrations.create_index('at',expireAfterSeconds=60)
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME',db.name)
    with pytest.raises(OperationFailure): await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in row for row in (await db.outreach_credential_migrations.index_information()).values())


async def test_actual_standalone_denies_before_stop_open_or_seal(real_old,monkeypatch,tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port',str(port),
        '--bind_ip','127.0.0.1','--logpath',str(tmp_path/'standalone.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}/?directConnection=true',serverSelectionTimeoutMS=200)
    db=client['test_v231_standalone']
    try:
        for _ in range(50):
            try: await client.admin.command('ping');break
            except Exception: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone did not start')
        for name in await real_old.list_collection_names():
            rows=await real_old[name].find({}).to_list(length=100)
            if rows: await db[name].insert_many(rows)
        view=await inspection(db);assert not view['blockers']
        monkeypatch.setattr(migration,'open_legacy_audio',AsyncMock(side_effect=AssertionError('No opening')))
        monkeypatch.setattr(migration,'seal_audio',AsyncMock(side_effect=AssertionError('No sealing')))
        with pytest.raises(suppression.SuppressionUnavailable): await convert(db,view)
        assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status']=='active'
    finally:
        try: await client.drop_database(db.name)
        finally:
            client.close();process.terminate();process.wait(timeout=10);shutil.rmtree(root)
