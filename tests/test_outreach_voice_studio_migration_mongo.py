"""Actual Studio result conversion transactions, replacement and closure proof."""
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

from outreach.core import suppression, voice_studio_migration as migration
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.erasure import OutreachErasure
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_studio import VoiceStudio
from outreach.core.voice_studio_custody import open_blob
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_studio import studio_db

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned local replica set is opt-in')]
EVIDENCE='a'*64


@pytest_asyncio.fixture
async def real_preview(studio_db, scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27028',serverSelectionTimeoutMS=2000)
    db=client['test_studio_result_migration_'+uuid.uuid4().hex]
    try:
        for name,source in studio_db.collections.items():
            if source.docs:await db[name].insert_many(source.docs)
        await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
        service=VoiceStudio(db)
        first=await service.queue('w','actor','clone','request-1',name='My voice',
            audio=generate_mock_voice_wav(duration_s=20),consent=True)
        assert (await service.run('w',first['_id'],provider=AsyncMock(return_value={'voice_id':'vendor_voice'})))['status']=='completed'
        queued=await service.queue('w','actor','preview','preview-1',voice_id=first['voice_id'],script='Hello')
        assert (await service.run('w',queued['_id'],provider=AsyncMock(return_value={'audio':generate_mock_voice_wav()})))['status']=='completed'
        job=await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w','_id':queued['_id']})
        dates={key:job[key]-timedelta(minutes=5) for key in ('created_at','updated_at','lease_until',
            'possible_at','authorization_expires_at','result_expires_at')}
        dates['receipt.received_at']=job['receipt']['received_at']-timedelta(minutes=5)
        await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w','_id':job['_id']},{'$set':dates})
        await db.outreach_accounts.insert_one({'_id':'account','id':'sender','workspace_id':'w','status':'connected',
            'credential_generation':'original-cookie-generation'})
        await db.outreach_campaigns.insert_one({'_id':'campaign','workspace_id':'w','status':'active',
            'authorization_revision':3,'auto_launch_enabled':True})
        for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_INTEGRATIONS_ENABLED',
                     'OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED'):
            monkeypatch.setenv(flag,'false')
        monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
        yield db
    finally:
        await client.drop_database(db.name);client.close()


async def original_job(db):
    return await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w','operation':'preview'})


async def inspection(db):
    job=await original_job(db)
    return await migration.VoiceStudioMigration(db).inspect('w',job['_id'])


async def convert(db,view=None):
    view=view or await inspection(db)
    return await migration.VoiceStudioMigration(db).migrate('w',view['job_id'],'operator',EVIDENCE,
        view['digest'],workers_drained=True)


async def test_native_bson_stop_before_open_and_key_work_outside_transactions(real_preview,monkeypatch):
    db=real_preview; original=await original_job(db)
    assert original['result_expires_at'].tzinfo is None
    profile=await db.outreach_voices.find_one({'workspace_id':'w'})
    budgets=await db.outreach_voice_studio_budgets.find({'workspace_id':'w'}).to_list(length=10)
    inside=ContextVar('inside',default=False)
    mutate=suppression.mutate_suppression;opening=migration.open_legacy_result;sealing=migration.seal_blob
    async def tracked(database,workspace,callback):
        async def entered(current):
            token=inside.set(True)
            try:return await callback(current)
            finally:inside.reset(token)
        return await mutate(database,workspace,entered)
    async def opened(*args):
        assert not inside.get()
        assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status']=='paused'
        assert (await db.outreach_sender_execution.find_one({'workspace_id':'w'}))['permission']['latched']
        return await opening(*args)
    async def sealed(*args):
        assert not inside.get()
        return await sealing(*args)
    monkeypatch.setattr(suppression,'mutate_suppression',tracked)
    monkeypatch.setattr(migration,'open_legacy_result',opened);monkeypatch.setattr(migration,'seal_blob',sealed)
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME',db.name)
    await create_all_indexes(db.client)
    assert (await convert(db))['current_matches']
    current=await original_job(db)
    assert {k:v for k,v in current.items() if k not in {'result_enc','dispatch_fence_revision'}}=={
        k:v for k,v in original.items() if k not in {'result_enc','dispatch_fence_revision'}}
    assert await open_blob(current['result_enc'],current,'result')==generate_mock_voice_wav()
    assert migration.stable(await db.outreach_voices.find_one({'workspace_id':'w'}))==migration.stable(profile)
    assert await db.outreach_voice_studio_budgets.find({'workspace_id':'w'}).to_list(length=10)==budgets
    indexes=await db.outreach_credential_migrations.index_information()
    assert indexes['voice_studio_result_migration_original_v1']['unique']
    assert all('expireAfterSeconds' not in row for row in indexes.values())


async def test_failed_key_keeps_stop_original_receipt_and_result(real_preview,monkeypatch):
    original=migration.stable(await original_job(real_preview))
    monkeypatch.setattr(migration,'seal_blob',AsyncMock(side_effect=ValueError('private-key-error')))
    with pytest.raises(ValueError):await convert(real_preview)
    assert migration.stable(await original_job(real_preview))==original
    assert (await real_preview.outreach_accounts.find_one({'workspace_id':'w'}))['status']=='paused'
    assert not await real_preview.outreach_credential_migrations.find_one({'workspace_id':'w'})


@pytest.mark.parametrize('target',['result','receipt','stop'])
async def test_atomic_projection_rollback(real_preview,monkeypatch,target):
    from outreach.core.suppression import SuppressionCollection
    update,insert=SuppressionCollection.update_one,SuppressionCollection.insert_one
    async def failed_update(self,*args,**kwargs):
        if (target=='result' and self.collection.name=='outreach_voice_studio_jobs'
                or target=='stop' and self.collection.name=='outreach_campaigns'):
            raise RuntimeError('Owned projection failure')
        return await update(self,*args,**kwargs)
    async def failed_insert(self,*args,**kwargs):
        if target=='receipt' and self.collection.name=='outreach_credential_migrations':
            raise RuntimeError('Owned receipt failure')
        return await insert(self,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',failed_update)
    monkeypatch.setattr(SuppressionCollection,'insert_one',failed_insert)
    with pytest.raises(RuntimeError):await convert(real_preview)
    assert (await original_job(real_preview))['result_enc'].startswith('gAAAAA')
    assert not await real_preview.outreach_credential_migrations.find_one({'workspace_id':'w'})
    assert (await real_preview.outreach_campaigns.find_one({'workspace_id':'w'}))['status']==('active' if target=='stop' else 'paused')


@pytest.mark.parametrize('fault',['owner','receipt','profile','permission','campaign','expiry','erasure','policy','gate'])
async def test_seal_time_changes_deny_overwrite_of_new_authority(real_preview,monkeypatch,fault):
    db=real_preview;seal=migration.seal_blob
    async def changed(*args):
        result=await seal(*args)
        if fault=='owner':await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w','operation':'preview'},{'$set':{'owner':'replacement'}})
        if fault=='receipt':await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w','operation':'preview'},{'$set':{'receipt.audio_digest':'b'*64}})
        if fault=='profile':await db.outreach_voices.update_one({'workspace_id':'w'},{'$inc':{'revision':1}})
        if fault=='permission':await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$set':{'permission.latched':False}})
        if fault=='campaign':await db.outreach_campaigns.update_one({'workspace_id':'w'},{'$set':{'status':'active'}})
        if fault=='expiry':await db.outreach_voice_studio_jobs.update_one({'workspace_id':'w','operation':'preview'},{'$set':{'result_expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}})
        if fault=='erasure':await OutreachErasure(db).request('w','actor')
        if fault=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault=='gate':monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        return result
    monkeypatch.setattr(migration,'seal_blob',changed)
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):await convert(db)
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    assert not (await original_job(db)).get('result_enc','').startswith('vs1:')


@pytest.mark.parametrize('fault',['policy','gate','expiry'])
async def test_late_awaited_final_readback_denies_commit(real_preview,monkeypatch,fault):
    saved=migration.VoiceStudioMigration._saved
    expiry=(await original_job(real_preview))['result_expires_at'].replace(tzinfo=timezone.utc)
    async def changed(self,*args):
        result=await saved(self,*args)
        if fault=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault=='gate':monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        if fault=='expiry':monkeypatch.setattr(migration,'now',lambda:expiry+timedelta(seconds=1))
        return result
    monkeypatch.setattr(migration.VoiceStudioMigration,'_saved',changed)
    with pytest.raises(CustodyUnavailable):await convert(real_preview)
    assert (await original_job(real_preview))['result_enc'].startswith('gAAAAA')
    assert not await real_preview.outreach_credential_migrations.find_one({'workspace_id':'w'})


async def test_lost_final_ack_receipt_retry_opens_nothing_and_never_stops_again(real_preview,monkeypatch):
    db=real_preview;view=await inspection(db);mutate=suppression.mutate_suppression;calls=0
    async def lost(*args):
        nonlocal calls
        calls+=1;result=await mutate(*args)
        if calls==2:raise RuntimeError('Owned final acknowledgement loss')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError):await convert(db,view)
    execution=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    monkeypatch.setattr(migration,'open_legacy_result',AsyncMock(side_effect=AssertionError('No opening')))
    monkeypatch.setattr(migration,'seal_blob',AsyncMock(side_effect=AssertionError('No key work')))
    assert (await convert(db,view))['current_matches']
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==execution


async def test_lost_stop_ack_opens_nothing_and_requires_new_inspection(real_preview,monkeypatch):
    db=real_preview;view=await inspection(db);mutate=suppression.mutate_suppression
    async def lost(*args):
        await mutate(*args);raise RuntimeError('Owned stop acknowledgement loss')
    opening=AsyncMock(wraps=migration.open_legacy_result)
    monkeypatch.setattr(migration,'open_legacy_result',opening);monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError):await convert(db,view)
    opening.assert_not_awaited()
    monkeypatch.setattr(suppression,'mutate_suppression',mutate)
    with pytest.raises(CustodyUnavailable):await convert(db,view)
    assert (await convert(db))['current_matches']
    opening.assert_awaited_once()


async def test_guarded_concurrent_saved_receipt_precedes_original_opening(real_preview,monkeypatch):
    db=real_preview;view=await inspection(db);mutate=suppression.mutate_suppression
    arrived,release=asyncio.Event(),asyncio.Event();paused=False
    async def delayed(*args):
        nonlocal paused
        if not paused:paused=True;arrived.set();await release.wait()
        return await mutate(*args)
    opening=AsyncMock(wraps=migration.open_legacy_result)
    monkeypatch.setattr(migration,'open_legacy_result',opening);monkeypatch.setattr(suppression,'mutate_suppression',delayed)
    first=asyncio.create_task(convert(db,view))
    try:
        await asyncio.wait_for(arrived.wait(),5);winner=await convert(db,view)
    finally:release.set()
    assert await first==winner
    opening.assert_awaited_once()
    assert await db.outreach_credential_migrations.count_documents({'workspace_id':'w'})==1


async def test_expiry_cleanup_during_seal_does_not_restore_audio(real_preview,monkeypatch):
    seal=migration.seal_blob
    async def removed(*args):
        result=await seal(*args)
        await real_preview.outreach_voice_studio_jobs.update_one({'workspace_id':'w','operation':'preview'},
            {'$unset':{'result_enc':''}})
        return result
    monkeypatch.setattr(migration,'seal_blob',removed)
    with pytest.raises(CustodyUnavailable):await convert(real_preview)
    assert 'result_enc' not in await original_job(real_preview)
    assert not await real_preview.outreach_credential_migrations.find_one({'workspace_id':'w'})


async def test_erasure_retains_minimal_conversion_history_and_closed_tenant_denies(real_preview,monkeypatch):
    db=real_preview;view=await inspection(db);await convert(db,view)
    deletion=OutreachErasure(db);await deletion.request('w','actor');inspected=await deletion.inspect('w')
    await deletion.finish('w','operator','All writers and caches drained for the owned local fixture.',
        workers_drained=True,expected_digest=inspected['review_digest'])
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'voice_studio_result_custody_migration'})
    assert hold and not hold['activation_allowed'] and hold['provenance']=='strict_fernet_studio_result_conversion'
    for secret in ('gAAAAA','vs1:','Hello','cookie','vendor_voice'):assert secret not in str(hold)
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    monkeypatch.setattr(migration,'open_legacy_result',AsyncMock(side_effect=AssertionError('No opening')))
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):await convert(db,view)


async def test_retention_first_strict_original_index_rejects_duplicate_history(real_preview,monkeypatch):
    db=real_preview;job=await original_job(db)
    row={'workspace_id':'w','kind':'voice_studio_result','job_id':job['_id']}
    await db.outreach_credential_migrations.insert_many([dict(row),dict(row)])
    await db.outreach_credential_migrations.create_index('at',expireAfterSeconds=60)
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME',db.name)
    with pytest.raises(OperationFailure):await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in value for value in (await db.outreach_credential_migrations.index_information()).values())


async def test_actual_standalone_denies_before_stop_or_key_work(real_preview,monkeypatch,tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port',str(port),
        '--bind_ip','127.0.0.1','--logpath',str(tmp_path/'standalone.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}/?directConnection=true',serverSelectionTimeoutMS=200)
    db=client['test_v232_standalone']
    try:
        for _ in range(50):
            try:await client.admin.command('ping');break
            except Exception:await asyncio.sleep(.1)
        else:raise AssertionError('Owned standalone did not start')
        for name in await real_preview.list_collection_names():
            rows=await real_preview[name].find({}).to_list(length=100)
            if rows:await db[name].insert_many(rows)
        view=await inspection(db);assert not view['blockers']
        opening=AsyncMock();monkeypatch.setattr(migration,'open_legacy_result',opening)
        with pytest.raises(suppression.SuppressionUnavailable):await convert(db,view)
        opening.assert_not_awaited()
        assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['status']=='connected'
    finally:
        try:await client.drop_database(db.name)
        finally:client.close();process.terminate();process.wait(timeout=10);shutil.rmtree(root)
