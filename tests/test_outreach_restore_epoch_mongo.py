"""Actual majority restore preparation, rollback, post-commit denial and indexes."""
import asyncio
from copy import deepcopy
import os
import shutil
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
import pytest
import pytest_asyncio
from outreach.core import restore_epoch as epoch, suppression
from outreach.core.dispatch_authority import DispatchAuthority
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.erasure import OutreachErasure
from outreach.core.request_guard import RequestDenied
from tests.test_outreach_restore_epoch import restored_db, prepare, EVIDENCE, ANCHOR
from tests.test_outreach_dispatch_authority import ready_db, dispatch
pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned local Mongo is opt-in')]

@pytest_asyncio.fixture
async def real_restore(restored_db):
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27028',serverSelectionTimeoutMS=2000)
    db=client['test_restore_epoch_'+uuid.uuid4().hex]
    try:
        for name,collection in restored_db.collections.items():
            if collection.docs:await db[name].insert_many(collection.docs)
        await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
        yield db
    finally:await client.drop_database(db.name);client.close()

async def test_native_bson_prepare_and_exact_lost_ack_retry(real_restore,monkeypatch):
    db=real_restore;service=epoch.RestoreEpoch(db);view=await service.inspect('w')
    result=await prepare(db,view);assert result['prepared']
    root=await db.outreach_execution_epochs.find_one(epoch.root_scope('w'));assert root['prepared_at'].tzinfo is None
    proof=await epoch.require(db,'w');assert proof.digest==result['execution_epoch']
    # Simulate caller losing acknowledgement, then a new local stop/replacement.
    await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$set':{'permission.stop_reason':'replacement'},'$inc':{'permission_revision':1}})
    before=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    assert (await prepare(db,view))['recovered']
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==before
    with pytest.raises(epoch.EpochUnavailable):await ExecutionPermission(db).grant('w','new','g',['sequence'],'operator',clear_latch=True)
    unknown=await db.outreach_manual_actions.find_one({'_id':'unknown'})
    assert unknown['status']=='unknown_outcome' and unknown['owner']=='original-owner' and unknown['receipt']

@pytest.mark.parametrize('target',['stop','root','journal','final_config'])
async def test_prepare_failure_rolls_back_stop_root_and_journal(real_restore,monkeypatch,target):
    db=real_restore;view=await epoch.RestoreEpoch(db).inspect('w')
    original=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    from outreach.core.dispatch_authority import AuthorityCollection
    method=AuthorityCollection.update_one
    async def failed_stop(self,*args,**kwargs):
        if self.name=='outreach_sender_execution':raise RuntimeError('Owned failure')
        return await method(self,*args,**kwargs)
    if target=='stop':monkeypatch.setattr(AuthorityCollection,'update_one',failed_stop)
    update=suppression.SuppressionCollection.update_one;insert=suppression.SuppressionCollection.insert_one
    async def fail_root(self,*args,**kwargs):
        if self.collection.name=='outreach_execution_epochs':raise RuntimeError('Owned root failure')
        return await update(self,*args,**kwargs)
    async def fail_journal(self,*args,**kwargs):
        if self.collection.name=='outreach_execution_epochs':
            if target=='journal':raise RuntimeError('Owned journal failure')
            result=await insert(self,*args,**kwargs);monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','c'*64);return result
        return await insert(self,*args,**kwargs)
    if target=='root':monkeypatch.setattr(suppression.SuppressionCollection,'update_one',fail_root)
    if target in {'journal','final_config'}:monkeypatch.setattr(suppression.SuppressionCollection,'insert_one',fail_journal)
    with pytest.raises((ValueError,RuntimeError)):await prepare(db,view)
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==original
    assert not await db.outreach_execution_epochs.find_one({})

async def test_concurrent_prepare_commits_one_permanent_journal(real_restore):
    db=real_restore;view=await epoch.RestoreEpoch(db).inspect('w')
    results=await asyncio.gather(prepare(db,view),prepare(db,view))
    assert all(item['prepared'] for item in results)
    assert await db.outreach_execution_epochs.count_documents({'kind':'journal'})==1
    assert (await db.outreach_sender_execution.find_one({'workspace_id':'w'}))['permission_revision']==4

@pytest.mark.parametrize('fault',['capacity','closed','changed_snapshot'])
async def test_preflight_denies_without_authority_changes(real_restore,fault):
    db=real_restore;view=await epoch.RestoreEpoch(db).inspect('w')
    original=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    if fault=='capacity':await db.outreach_campaigns.insert_many([{'_id':str(i),'workspace_id':'w','status':'active'} for i in range(101)])
    if fault=='closed':await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'),{'$set':{'erasure_state':'closed'}},upsert=True)
    if fault=='changed_snapshot':await db.outreach_campaigns.update_one({'workspace_id':'w'},{'$inc':{'authorization_revision':1}})
    with pytest.raises(Exception):await prepare(db,view)
    assert not await db.outreach_execution_epochs.find_one({})
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==original

@pytest.mark.parametrize('change',['anchor','flag'])
async def test_actual_dispatch_factory_denies_config_change_after_commit(ready_db,monkeypatch,change):
    db,job=ready_db;factory=AsyncMock(return_value=httpx.Response(200,json={}))
    original=DispatchAuthority.authorize
    async def changed(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        if change=='anchor':monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
        else:monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','true')
        return result
    monkeypatch.setattr(DispatchAuthority,'authorize',changed)
    with pytest.raises(RequestDenied):await dispatch(db,job,factory)
    factory.assert_not_awaited()
    request=await db.outreach_physical_requests.find_one({})
    assert request['status']=='not_submitted'

async def test_installed_root_survives_configuration_downgrade_and_old_backup(real_restore,monkeypatch):
    db=real_restore;await prepare(db)
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    with pytest.raises(epoch.EpochUnavailable):await epoch.positive(db,'w')
    await db.outreach_execution_epochs.delete_many({})
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','c'*64)
    with pytest.raises(epoch.EpochUnavailable):await epoch.positive(db,'w')

async def test_erasure_classifies_epoch_and_keeps_minimal_digest_provenance(real_restore):
    db=real_restore;await prepare(db);row=await db.outreach_execution_epochs.find_one({'kind':'journal'})
    async def apply(current):await OutreachErasure(db)._archive(current,'outreach_execution_epochs','w',row)
    await suppression.mutate_suppression(db,'w',apply)
    hold=await db.outreach_erasure_holds.find_one({'kind':'restore_epoch_provenance'})
    assert hold and hold['execution_epoch']==row['execution_epoch'] and not hold['activation_allowed']
    assert 'operator' not in hold and hold['operator_digest']

async def test_retention_first_actual_unique_indexes_preserve_journals(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db=real_restore
    await db.outreach_execution_epochs.create_index('expires_at',expireAfterSeconds=9999,name='unsafe_epoch_ttl')
    await remove_other_evidence_ttls(db);await ensure_integration_indexes(db)
    assert all('expireAfterSeconds' not in spec for spec in (await db.outreach_execution_epochs.index_information()).values())
    await prepare(db);saved=await db.outreach_execution_epochs.find_one({'kind':'journal'})
    with pytest.raises(Exception):await db.outreach_execution_epochs.insert_one({**saved,'_id':'duplicate'})
    assert await db.outreach_execution_epochs.count_documents({'kind':'journal'})==1

async def test_standalone_denies_prepare_before_any_stop(real_restore,tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    path=tmp_path/'mongo';path.mkdir()
    with (tmp_path/'mongo.log').open('w') as log:
        process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(path),'--bind_ip','127.0.0.1','--port',str(port)],stdout=log,stderr=log)
        client=AsyncIOMotorClient('mongodb://127.0.0.1:'+str(port),serverSelectionTimeoutMS=1000)
        db=client['test_restore_standalone_'+uuid.uuid4().hex]
        try:
            for attempt in range(20):
                try:await client.admin.command('ping');break
                except Exception:
                    if attempt==19:raise
                    await asyncio.sleep(.2)
            for name in await real_restore.list_collection_names():
                rows=await real_restore[name].find({}).to_list(length=200)
                if rows:await db[name].insert_many(rows)
            view=await epoch.RestoreEpoch(db).inspect('w')
            with pytest.raises(Exception):await prepare(db,view)
            assert not await db.outreach_execution_epochs.find_one({})
            assert not (await db.outreach_sender_execution.find_one({}))['permission']['latched']
        finally:
            await client.drop_database(db.name);client.close();process.terminate();process.wait(timeout=10);shutil.rmtree(path)

@pytest.mark.parametrize('kind',['grant','installation'])
async def test_current_epoch_change_at_last_write_rolls_back_positive_authority(real_restore,monkeypatch,kind):
    """Admission and write share the guard; final config check rolls back writes."""
    db=real_restore;monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    original=suppression.SuppressionCollection.update_one
    async def change_at_write(self,query,update,**kwargs):
        result=await original(self,query,update,**kwargs)
        values=update.get('$set',{})
        if ('permission' in values and kind=='grant') or (values.get('connection_finalization.state')=='installed' and kind=='installation'):
            monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
        return result
    monkeypatch.setattr(suppression.SuppressionCollection,'update_one',change_at_write)
    if kind=='grant':
        with pytest.raises(epoch.EpochUnavailable):await ExecutionPermission(db).grant('w','new','g',['sequence'],'operator',clear_latch=True)
        assert not await db.outreach_sender_execution.find_one({'sender_id':'new'})
        assert not await db.outreach_execution_permissions.find_one({'sender_id':'new'})
    else:
        from tests.test_outreach_connection_repair import database,prepared,NOW
        source=database()
        for name,collection in source.collections.items():
            await db[name].delete_many({})
            if collection.docs:await db[name].insert_many(collection.docs)
        service,job=await prepared(db)
        before=await db.outreach_accounts.find_one({'workspace_id':'w'})
        with pytest.raises(epoch.EpochUnavailable):await service.install(job,'owner','g',{'session_cookie_enc':'dummy','status':'active'},now=NOW)
        assert await db.outreach_accounts.find_one({'workspace_id':'w'})==before

@pytest.mark.parametrize('kind',['grant','installation'])
async def test_guard_orders_restore_behind_in_progress_positive_write(real_restore,monkeypatch,kind):
    db=real_restore;monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    if kind=='installation':
        from tests.test_outreach_connection_repair import database,prepared,NOW
        source=database()
        for name,collection in source.collections.items():
            await db[name].delete_many({})
            if collection.docs:await db[name].insert_many(collection.docs)
        service,job=await prepared(db)
    entered=asyncio.Event();release=asyncio.Event();original=suppression.SuppressionCollection.update_one
    async def paused(self,query,update,**kwargs):
        values=update.get('$set',{})
        if ('permission' in values and kind=='grant') or (values.get('connection_finalization.state')=='installed' and kind=='installation'):
            entered.set();await release.wait()
        return await original(self,query,update,**kwargs)
    monkeypatch.setattr(suppression.SuppressionCollection,'update_one',paused)
    work=asyncio.create_task(ExecutionPermission(db).grant('w','new','g',['sequence'],'operator',clear_latch=True)
        if kind=='grant' else service.install(job,'owner','g',{'session_cookie_enc':'dummy','status':'active'},now=NOW))
    restoring=None
    try:
        await asyncio.wait_for(entered.wait(),3)
        monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','true');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR)
        view=await epoch.RestoreEpoch(db).inspect('w');restoring=asyncio.create_task(prepare(db,view))
        # The restore cannot commit around a positive operation owning the guard.
        await asyncio.sleep(.1);assert not restoring.done()
        release.set()
        with pytest.raises(epoch.EpochUnavailable):await work
        assert (await restoring)['prepared']
        if kind=='grant':assert not await db.outreach_sender_execution.find_one({'sender_id':'new'})
        else:assert not (await db.outreach_accounts.find_one({'workspace_id':'w'})).get('session_cookie_enc')
    finally:
        release.set()
        for task in (work,restoring):
            if task is not None and not task.done():task.cancel()
        await asyncio.gather(*[task for task in (work,restoring) if task is not None],return_exceptions=True)

async def test_legacy_existing_sender_grant_is_transactionally_compatible(real_restore,monkeypatch):
    db=real_restore;monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED','false');monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH','')
    scope=ExecutionPermission.scope('w','existing')
    await db.outreach_sender_execution.insert_one({**scope,'status':'idle','permission_revision':3,'permission':{'latched':True}})
    grant=await ExecutionPermission(db).grant('w','existing','g',['sequence'],'operator',clear_latch=True)
    assert grant['revision']==4 and not grant['latched']
    assert await ExecutionPermission(db).allowed('w','existing','g','sequence')
    assert (await ExecutionPermission(db).grant('w','existing','g',['sequence'],'operator'))['revision']==5

from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_voice_studio_mongo import real_studio,queued

async def test_received_studio_result_cannot_activate_after_late_epoch_change(real_studio,monkeypatch):
    from outreach.core.voice_studio import VoiceStudio
    db=real_studio;job=await queued(db)
    await db.outreach_voice_studio_jobs.update_one({'_id':job['_id']},{'$set':{'status':'received','owner':'owner',
        'receipt':{'voice_id':'original-remote','received_at':epoch.now()}}})
    original=VoiceStudio._validate
    async def changed(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH',ANCHOR);return result
    monkeypatch.setattr(VoiceStudio,'_validate',changed)
    with pytest.raises(epoch.EpochUnavailable):await VoiceStudio(db)._finish('w',job['_id'],'owner')
    saved=await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})
    assert saved['status']=='received' and saved['receipt']['voice_id']=='original-remote'
    profile=await db.outreach_voices.find_one({'id':job['voice_id']})
    assert profile['status']!='active' and not profile.get('elevenlabs_voice_id')
