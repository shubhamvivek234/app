"""Actual transaction rollback, receipt recovery and managed-use lineage checks."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import os
from unittest.mock import AsyncMock, Mock

from pymongo.errors import DuplicateKeyError
import pytest

from outreach.core import proxy_lifecycle as lifecycle, suppression
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityCollection
from outreach.core.erasure import OutreachErasure
from outreach.core.webshare_provisioning import managed_webshare_valid
from tests.test_outreach_webshare_migration import scoped, ASSET, EVIDENCE, convert
from tests.test_outreach_webshare_migration_mongo import real_webshare
from tests.test_outreach_proxy_lifecycle import change

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned loopback replica set is opt-in')]


@pytest.mark.parametrize('operation',['renew','rotate'])
async def test_real_bson_change_atomic_current_proof_and_no_key_in_callback(real_webshare,monkeypatch,operation):
    db=real_webshare;await convert(db);before=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    inside=ContextVar('proxy_lifecycle_transaction',default=False);mutate=suppression.mutate_suppression;seal=lifecycle.seal_proxy_password
    async def guarded(db,workspace,callback):
        async def run(current):
            token=inside.set(True)
            try:return await callback(current)
            finally:inside.reset(token)
        return await mutate(db,workspace,run)
    async def key(*args,**kwargs):
        assert not inside.get();return await seal(*args,**kwargs)
    monkeypatch.setattr(suppression,'mutate_suppression',guarded);monkeypatch.setattr(lifecycle,'seal_proxy_password',key)
    assert (await change(db,operation))['current_matches']
    after=await db.outreach_proxy_inventory.find_one({'_id':ASSET});account=await db.outreach_accounts.find_one({'workspace_id':'w'})
    assert after['expires_at'].tzinfo is None and after['root_import_basis_digest']==before['import_basis_digest']
    assert await managed_webshare_valid(db,after,'w') and account['status']=='paused'
    assert account['credential_generation']=='cookie-original'
    if operation=='rotate':assert account['proxy']['password_enc']==account['proxy_config']['password_enc']==after['password_enc']
    else:assert after['password_enc']==before['password_enc']
    from db.indexes import create_all_indexes
    await db.outreach_proxy_lifecycle_reviews.create_index('at',expireAfterSeconds=1,name='old_unsafe_ttl')
    monkeypatch.setenv('DB_NAME',db.name);await create_all_indexes(db.client)
    info=await db.outreach_proxy_lifecycle_reviews.index_information()
    assert info['proxy_lifecycle_revision_v1']['unique'] and all('expireAfterSeconds' not in row for row in info.values())
    receipt=await db.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})
    for private in ('191.116.125.248','private-password','uc1:','gAAAAA','cookie-original'):
        assert private not in str(receipt)
    with pytest.raises(DuplicateKeyError):
        await db.outreach_proxy_lifecycle_reviews.insert_one({**receipt,'_id':'duplicate'})


@pytest.mark.parametrize('target',['outreach_proxy_inventory','outreach_accounts','outreach_proxy_lifecycle_reviews'])
async def test_rotation_projection_failure_rolls_back_whole_change(real_webshare,monkeypatch,target):
    db=real_webshare;await convert(db);before=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    from outreach.core.suppression import SuppressionCollection
    update,insert=SuppressionCollection.update_one,SuppressionCollection.insert_one
    from outreach.core.dispatch_authority import AuthorityCollection
    authority_update=AuthorityCollection.update_one
    async def fail_update(self,*args,**kwargs):
        if self.collection.name==target:raise RuntimeError('Owned projection failure')
        return await update(self,*args,**kwargs)
    async def fail_authority(self,*args,**kwargs):
        if self.name==target:raise RuntimeError('Owned inventory failure')
        return await authority_update(self,*args,**kwargs)
    async def fail_insert(self,*args,**kwargs):
        if self.collection.name==target:raise RuntimeError('Owned journal failure')
        return await insert(self,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',fail_update)
    monkeypatch.setattr(SuppressionCollection,'insert_one',fail_insert)
    monkeypatch.setattr(AuthorityCollection,'update_one',fail_authority)
    with pytest.raises(RuntimeError):await change(db,'rotate')
    after=await db.outreach_proxy_inventory.find_one({'_id':ASSET});account=await db.outreach_accounts.find_one({'workspace_id':'w'})
    assert after['password_enc']==before['password_enc'] and 'root_import_basis_digest' not in after
    assert account['proxy']['password_enc']==account['proxy_config']['password_enc']==before['password_enc']
    assert not await db.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})


@pytest.mark.parametrize('fault',['owner','alias','lease','permission','basis','policy','erasure'])
async def test_change_while_sealing_cannot_install_over_replacement(real_webshare,monkeypatch,fault):
    db=real_webshare;await convert(db);seal=lifecycle.seal_proxy_password
    async def changed(*args,**kwargs):
        result=await seal(*args,**kwargs)
        if fault=='owner':await db.outreach_proxy_inventory.update_one({'_id':ASSET},{'$set':{'workspace_id':'other'}})
        if fault=='basis':await db.outreach_proxy_inventory.update_one({'_id':ASSET},{'$set':{'provider_order_id':'replacement'}})
        if fault=='alias':await db.outreach_accounts.update_one({'workspace_id':'w'},{'$set':{'proxy.username':'replacement'}})
        if fault=='lease':await db.outreach_proxy_leases.update_one({'_id':ASSET},{'$set':{'sender_id':'replacement'}})
        if fault=='permission':await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$set':{'permission.latched':False}})
        if fault=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault=='erasure':
            async def stopped(current):
                await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'),{'$set':{'erasure_state':'requested'}})
            await suppression.mutate_suppression(db,'w',stopped)
        return result
    monkeypatch.setattr(lifecycle,'seal_proxy_password',changed)
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):await change(db,'rotate')
    assert not await db.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})


async def test_guarded_exact_concurrent_receipt_precedes_second_password_read(real_webshare,monkeypatch):
    db=real_webshare;await convert(db);view=await lifecycle.ProxyLifecycle(db).inspect('w',ASSET,'rotate')
    mutate=suppression.mutate_suppression;arrived,release=asyncio.Event(),asyncio.Event();paused=False
    supplier=Mock(return_value='changed-private-password')
    async def delayed(db,workspace,callback):
        nonlocal paused
        if not paused:paused=True;arrived.set();await release.wait()
        return await mutate(db,workspace,callback)
    monkeypatch.setattr(suppression,'mutate_suppression',delayed)
    late=asyncio.create_task(change(db,'rotate',view,password_supplier=supplier));await asyncio.wait_for(arrived.wait(),5)
    first=await change(db,'rotate',view,password_supplier=supplier);release.set()
    assert await asyncio.wait_for(late,5)==first;supplier.assert_called_once()
    assert await db.outreach_proxy_lifecycle_reviews.count_documents({'workspace_id':'w'})==1


async def test_lost_final_ack_recovers_metadata_without_password_or_key_work(real_webshare,monkeypatch):
    db=real_webshare;await convert(db);view=await lifecycle.ProxyLifecycle(db).inspect('w',ASSET,'rotate')
    mutate=suppression.mutate_suppression;calls=0
    async def lost(db,workspace,callback):
        nonlocal calls
        calls+=1;result=await mutate(db,workspace,callback)
        if calls==2:raise RuntimeError('Owned lost final acknowledgement')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError):await change(db,'rotate',view)
    supplier=Mock(side_effect=AssertionError('No password replay'))
    monkeypatch.setattr(lifecycle,'seal_proxy_password',AsyncMock(side_effect=AssertionError('No key replay')))
    assert (await change(db,'rotate',view,password_supplier=supplier))['current_matches'];supplier.assert_not_called()


async def test_missing_latest_journal_blocks_reconnect_and_paid_capacity(real_webshare,monkeypatch):
    from outreach.core.managed_proxy import reserve_sender_proxy, ManagedProxyUnavailable
    from outreach.core.paid_access import record_verified_payment
    db=real_webshare;await convert(db);await change(db)
    await db.outreach_proxy_lifecycle_reviews.delete_many({'workspace_id':'w'})
    row=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert not await managed_webshare_valid(db,row,'w')
    with pytest.raises(ManagedProxyUnavailable):await reserve_sender_proxy(db,'w','a','IN')
    with pytest.raises(ValueError):
        await record_verified_payment(db,'w',invoice_id='invoice',verified_by='operator',seats=1,
            paid_through=datetime.now(timezone.utc)+timedelta(days=1))


async def test_erasure_retains_minimal_current_term_change_and_closed_retry_cannot_recreate(real_webshare,monkeypatch):
    db=real_webshare;await convert(db);view=await lifecycle.ProxyLifecycle(db).inspect('w',ASSET,'rotate')
    await change(db,'rotate',view);service=OutreachErasure(db);await service.request('w','human')
    review=await service.inspect('w')
    await service.finish('w','operator','All actual workspace writers and caches were paused and drained.',
        workers_drained=True,expected_digest=review['review_digest'])
    assert not await db.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'proxy_lifecycle_review'})
    assert hold['evidence_digest']==EVIDENCE and hold['activation_allowed'] is False
    for private in ('private-password','191.116.125.248','uc1:','gAAAAA','cookie-original','provider-change-1'):
        assert private not in str(hold)
    supplier=Mock(side_effect=AssertionError('No input'))
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):
        await change(db,'rotate',view,password_supplier=supplier)
    supplier.assert_not_called()


async def test_retention_precedes_strict_duplicate_revision_failure(real_webshare,monkeypatch):
    from db.indexes import create_all_indexes
    db=real_webshare
    await db.outreach_proxy_lifecycle_reviews.insert_many([{'_id':str(i),'workspace_id':'w','proxy_id':ASSET,'revision':1} for i in range(2)])
    await db.outreach_proxy_lifecycle_reviews.create_index('at',expireAfterSeconds=1,name='unsafe_ttl')
    monkeypatch.setenv('DB_NAME',db.name)
    with pytest.raises(DuplicateKeyError):await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in row for row in (await db.outreach_proxy_lifecycle_reviews.index_information()).values())


@pytest.mark.parametrize('drift',['policy','flag','expiry'])
async def test_final_readback_drift_rolls_back_inventory_aliases_and_new_journal(real_webshare,monkeypatch,drift):
    db=real_webshare;await convert(db);before=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    original=lifecycle.ProxyLifecycle._saved
    async def changed(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        if drift=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if drift=='flag':monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','true')
        if drift=='expiry':monkeypatch.setattr(lifecycle,'now',lambda:datetime.now(timezone.utc)+timedelta(days=400))
        return result
    monkeypatch.setattr(lifecycle.ProxyLifecycle,'_saved',changed)
    with pytest.raises(CustodyUnavailable):await change(db,'rotate')
    after=await db.outreach_proxy_inventory.find_one({'_id':ASSET});account=await db.outreach_accounts.find_one({'workspace_id':'w'})
    assert after['password_enc']==before['password_enc'] and after['import_basis_digest']==before['import_basis_digest']
    assert account['proxy']['password_enc']==account['proxy_config']['password_enc']==before['password_enc']
    assert not await db.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})


async def test_removed_markers_with_saved_journal_denies_use_before_password_input(real_webshare,monkeypatch):
    db=real_webshare;await convert(db);await change(db)
    await db.outreach_proxy_inventory.update_one({'_id':ASSET},{'$unset':{key:'' for key in (
        'root_import_basis_digest','proxy_lifecycle_revision','proxy_lifecycle_review_id')}})
    row=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert not await managed_webshare_valid(db,row,'w')
    supplier=Mock(side_effect=AssertionError('No input'))
    with pytest.raises(CustodyUnavailable):await change(db,'rotate',password_supplier=supplier)
    supplier.assert_not_called()


@pytest.mark.parametrize('operation',['renew','rotate'])
async def test_standalone_denies_changes_before_password_input_or_key_call(real_webshare,monkeypatch,tmp_path,operation):
    import shutil,socket,subprocess
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import PyMongoError
    binary=shutil.which('mongod')
    if not binary:pytest.skip('Local mongod unavailable')
    db=real_webshare;await convert(db)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    storage=tmp_path/'owned-standalone';storage.mkdir()
    process=subprocess.Popen([binary,'--dbpath',str(storage),'--port',str(port),'--bind_ip','127.0.0.1',
        '--logpath',str(tmp_path/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}',serverSelectionTimeoutMS=300)
    target=client['test_proxy_lifecycle_standalone']
    try:
        for _ in range(50):
            try:await client.admin.command('ping');break
            except PyMongoError:await asyncio.sleep(.1)
        else:raise RuntimeError('Owned standalone failed to start')
        for name in await db.list_collection_names():
            rows=await db[name].find({}).to_list(length=100)
            if rows:await target[name].insert_many(rows)
        service=lifecycle.ProxyLifecycle(target);view=await service.inspect('w',ASSET,operation)
        assert not view['blockers']
        supplier=Mock(side_effect=AssertionError('No hidden input'))
        seal=AsyncMock(side_effect=AssertionError('No key call'));monkeypatch.setattr(lifecycle,'seal_proxy_password',seal)
        kwargs={'expires_at':datetime.now(timezone.utc)+timedelta(days=60)} if operation=='renew' else {'password_supplier':supplier}
        with pytest.raises(suppression.SuppressionUnavailable):
            await service.apply('w',ASSET,operation,'operator',EVIDENCE,'provider-change-1',view['digest'],workers_drained=True,**kwargs)
        supplier.assert_not_called();seal.assert_not_awaited()
        assert not await target.outreach_proxy_lifecycle_reviews.find_one({'workspace_id':'w'})
    finally:
        try:await client.drop_database(target.name)
        finally:
            client.close();process.terminate();process.wait(timeout=10)
            shutil.rmtree(storage)
