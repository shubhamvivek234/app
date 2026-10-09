"""Actual legacy adoption transactions, default BSON and isolated standalone denial."""
import asyncio
from contextvars import ContextVar
from datetime import timedelta
from datetime import datetime, timezone
import os
import shutil
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, OperationFailure
import pytest
import pytest_asyncio

from outreach.core import proxy_adoption as adoption, suppression
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityCollection
from outreach.core.erasure import OutreachErasure
from outreach.core.webshare_provisioning import managed_webshare_valid
from tests.test_outreach_proxy_adoption import ASSET, EVIDENCE, adopt
from tests.test_outreach_webshare_migration_mongo import real_webshare, scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback Mongo is opt-in')]


@pytest_asyncio.fixture
async def real_legacy(real_webshare):
    await real_webshare.outreach_proxy_inventory.update_one({'_id':ASSET}, {'$unset':{
        field:'' for field in ('managed_webshare_version','import_basis_digest','request_digest')}})
    await real_webshare.account_proxy_ip_guards.delete_many({})
    return real_webshare


async def test_default_bson_atomic_adoption_key_outside_transaction_and_strict_indexes(real_legacy, monkeypatch):
    db = real_legacy
    original = await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert original['verified_at'].tzinfo is None
    inside = ContextVar('adoption_transaction', default=False)
    mutate, seal = suppression.mutate_suppression, adoption.seal_proxy_password
    async def guarded(database, workspace, callback):
        async def execute(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await mutate(database, workspace, execute)
    async def key(*args, **kwargs):
        assert not inside.get()
        return await seal(*args, **kwargs)
    monkeypatch.setattr(suppression, 'mutate_suppression', guarded)
    monkeypatch.setattr(adoption, 'seal_proxy_password', key)
    assert (await adopt(db))['current_matches']
    row = await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    account = await db.outreach_accounts.find_one({'workspace_id':'w'})
    assert row['expires_at'] == original['expires_at'] and row['credential_generation'] == original['credential_generation']
    assert account['proxy']['password_enc'] == account['proxy_config']['password_enc'] == row['password_enc']
    assert account['status'] == 'paused' and account['credential_generation'] == 'cookie-original'
    assert await managed_webshare_valid(db, row, 'w')
    from db.indexes import create_all_indexes
    await db.outreach_proxy_adoptions.create_index('at', expireAfterSeconds=1, name='unsafe_ttl')
    monkeypatch.setenv('DB_NAME', db.name)
    await create_all_indexes(db.client)
    info = await db.outreach_proxy_adoptions.index_information()
    assert info['proxy_adoption_asset_v1']['unique'] and all('expireAfterSeconds' not in value for value in info.values())
    receipt = await db.outreach_proxy_adoptions.find_one({'workspace_id':'w'})
    with pytest.raises(DuplicateKeyError): await db.outreach_proxy_adoptions.insert_one({**receipt, '_id':'duplicate'})
    for secret in ('191.116.125.248','private-password','gAAAAA','uc1:','cookie-original'):
        assert secret not in str(receipt)


async def test_native_alias_timestamp_precision_roundtrips_through_actual_bson(real_legacy):
    db = real_legacy
    metadata = {'status':'healthy','assigned_at':datetime.now(timezone.utc),'last_health_check':datetime.now(timezone.utc)}
    await db.outreach_accounts.update_one({'workspace_id':'w'}, {'$set':{f'proxy.{field}':value for field,value in metadata.items()}})
    original = (await db.outreach_accounts.find_one({'workspace_id':'w'}))['proxy']
    assert original['assigned_at'].microsecond % 1000 == 0
    assert (await adopt(db))['current_matches']
    row = (await db.outreach_accounts.find_one({'workspace_id':'w'}))['proxy']
    assert all(row[field] == original[field] for field in metadata)


@pytest.mark.parametrize('target', ['outreach_proxy_inventory', 'outreach_accounts', 'outreach_proxy_adoptions'])
async def test_install_failure_rolls_back_inventory_aliases_journal_but_retains_claim(real_legacy, monkeypatch, target):
    from outreach.core.suppression import SuppressionCollection
    update, insert, authority_update = SuppressionCollection.update_one, SuppressionCollection.insert_one, AuthorityCollection.update_one
    async def update_failure(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('Owned projection failure')
        return await update(self, *args, **kwargs)
    async def insert_failure(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('Owned receipt failure')
        return await insert(self, *args, **kwargs)
    async def authority_failure(self, *args, **kwargs):
        if self.name == target and args[1].get('$set', {}).get('managed_webshare_version') == 1:
            raise RuntimeError('Owned inventory failure')
        return await authority_update(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', update_failure)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', insert_failure)
    monkeypatch.setattr(AuthorityCollection, 'update_one', authority_failure)
    with pytest.raises(RuntimeError): await adopt(real_legacy)
    row = await real_legacy.outreach_proxy_inventory.find_one({'_id':ASSET})
    account = await real_legacy.outreach_accounts.find_one({'workspace_id':'w'})
    assert 'managed_webshare_version' not in row and row['password_enc'].startswith('gAAAAA')
    assert account['proxy']['password_enc'] == account['proxy_config']['password_enc'] == row['password_enc']
    assert not await real_legacy.outreach_proxy_adoptions.find_one({'workspace_id':'w'})
    assert await real_legacy.account_proxy_ip_guards.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['owner','order','alias','permission','lease','foreign_account','guard','policy','erasure','physical'])
async def test_change_while_sealing_never_installs_over_replacement(real_legacy, monkeypatch, fault):
    db, seal = real_legacy, adoption.seal_proxy_password
    async def changed(*args, **kwargs):
        result = await seal(*args, **kwargs)
        if fault == 'owner': await db.outreach_proxy_inventory.update_one({'_id':ASSET}, {'$set':{'workspace_id':'other'}})
        if fault == 'order': await db.outreach_proxy_inventory.update_one({'_id':ASSET}, {'$set':{'provider_order_id':'replacement'}})
        if fault == 'alias': await db.outreach_accounts.update_one({'workspace_id':'w'}, {'$set':{'proxy.username':'replacement'}})
        if fault == 'permission': await db.outreach_sender_execution.update_one({'workspace_id':'w'}, {'$set':{'permission.latched':False}})
        if fault == 'lease': await db.outreach_proxy_leases.update_one({'_id':ASSET}, {'$set':{'country_code':'US'}})
        if fault == 'foreign_account': await db.outreach_accounts.insert_one({'workspace_id':'other','id':'foreign','proxy':{'host':'191.116.125.248'}})
        if fault == 'guard': await db.account_proxy_ip_guards.update_one({}, {'$set':{'binding_digest':'replacement'}})
        if fault == 'policy': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault == 'erasure':
            async def stop(current):
                await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set':{'erasure_state':'stopped'}})
            await suppression.mutate_suppression(db, 'w', stop)
        if fault == 'physical': await db.outreach_physical_requests.insert_one({'workspace_id':'w','sender_id':'a','status':'unknown_outcome'})
        return result
    monkeypatch.setattr(adoption, 'seal_proxy_password', changed)
    with pytest.raises((CustodyUnavailable, suppression.SuppressionUnavailable)): await adopt(db)
    assert not await db.outreach_proxy_adoptions.find_one({'workspace_id':'w'})
    assert (await db.outreach_proxy_inventory.find_one({'_id':ASSET}))['password_enc'].startswith('gAAAAA')


@pytest.mark.parametrize('fault', ['policy', 'flag', 'expiry'])
async def test_final_awaited_readback_change_rolls_back_before_commit(real_legacy, monkeypatch, fault):
    saved = adoption.ProxyAdoption._saved
    expiry = adoption._time((await real_legacy.outreach_proxy_inventory.find_one({'_id':ASSET}))['expires_at'])
    async def changed(self, *args, **kwargs):
        result = await saved(self, *args, **kwargs)
        if fault == 'policy': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if fault == 'flag': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        if fault == 'expiry': monkeypatch.setattr(adoption, 'datetime', SimpleNamespace(now=lambda tz:expiry+timedelta(seconds=1)))
        return result
    monkeypatch.setattr(adoption.ProxyAdoption, '_saved', changed)
    with pytest.raises(CustodyUnavailable): await adopt(real_legacy)
    row = await real_legacy.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert 'managed_webshare_version' not in row and not await real_legacy.outreach_proxy_adoptions.find_one({'workspace_id':'w'})


async def test_lost_final_ack_receipt_repeats_no_key_work(real_legacy, monkeypatch):
    db = real_legacy
    view = await adoption.ProxyAdoption(db).inspect('w', ASSET)
    mutate = suppression.mutate_suppression
    calls = 0
    async def lost(database, workspace, callback):
        nonlocal calls
        calls += 1
        result = await mutate(database, workspace, callback)
        if calls == 2: raise RuntimeError('Owned final acknowledgement loss')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    with pytest.raises(RuntimeError): await adopt(db, view)
    monkeypatch.setattr(adoption, 'decrypt_strict', lambda *args: (_ for _ in ()).throw(AssertionError('No opening')))
    monkeypatch.setattr(adoption, 'seal_proxy_password', AsyncMock(side_effect=AssertionError('No key work')))
    assert (await adopt(db, view))['current_matches']
    assert await db.outreach_proxy_adoptions.count_documents({'workspace_id':'w'}) == 1


async def test_guarded_concurrent_receipt_wins_before_original_open(real_legacy, monkeypatch):
    db = real_legacy
    view = await adoption.ProxyAdoption(db).inspect('w',ASSET)
    mutate, seal = suppression.mutate_suppression, adoption.seal_proxy_password
    arrived, release = asyncio.Event(), asyncio.Event()
    delayed = False
    calls = 0
    async def paused(database,workspace,callback):
        nonlocal delayed
        if not delayed:
            delayed=True; arrived.set(); await release.wait()
        return await mutate(database,workspace,callback)
    async def key(*args,**kwargs):
        nonlocal calls
        calls += 1
        return await seal(*args,**kwargs)
    monkeypatch.setattr(suppression,'mutate_suppression',paused)
    monkeypatch.setattr(adoption,'seal_proxy_password',key)
    late=asyncio.create_task(adopt(db,view))
    try:
        await asyncio.wait_for(arrived.wait(),5)
        first=await adopt(db,view)
        release.set()
        assert await asyncio.wait_for(late,5) == first and calls == 1
    finally:
        release.set()
        if not late.done(): late.cancel(); await asyncio.gather(late,return_exceptions=True)


async def test_late_prepared_ciphertext_is_discarded_after_concurrent_completion(real_legacy, monkeypatch):
    from outreach.core.proxy_identity import identity
    db = real_legacy
    row = await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    await db.account_proxy_ip_guards.insert_one(identity(row['host'],'w',ASSET,row['provider']))
    view = await adoption.ProxyAdoption(db).inspect('w',ASSET)
    seal = adoption.seal_proxy_password
    arrived, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def paused(*args,**kwargs):
        nonlocal calls
        calls += 1
        result = await seal(*args,**kwargs)
        if calls == 1: arrived.set(); await release.wait()
        return result
    monkeypatch.setattr(adoption,'seal_proxy_password',paused)
    late=asyncio.create_task(adopt(db,view))
    try:
        await asyncio.wait_for(arrived.wait(),5)
        first=await adopt(db,view)
        installed=(await db.outreach_proxy_inventory.find_one({'_id':ASSET}))['password_enc']
        release.set()
        assert await asyncio.wait_for(late,5) == first and calls == 2
        assert (await db.outreach_proxy_inventory.find_one({'_id':ASSET}))['password_enc'] == installed
        assert await db.outreach_proxy_adoptions.count_documents({'workspace_id':'w'}) == 1
    finally:
        release.set()
        if not late.done(): late.cancel(); await asyncio.gather(late,return_exceptions=True)


async def test_erasure_retains_only_minimal_adoption_facts_and_closed_retry_denies(real_legacy):
    db = real_legacy
    view = await adoption.ProxyAdoption(db).inspect('w', ASSET)
    await adopt(db, view)
    erasure = OutreachErasure(db)
    await erasure.request('w', 'human')
    inspected = await erasure.inspect('w')
    await erasure.finish('w', 'operator', 'All writers and caches drained for local fixture.',
        workers_drained=True, expected_digest=inspected['review_digest'])
    hold = await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'proxy_legacy_adoption'})
    assert hold and not hold['activation_allowed'] and hold['original_evidence_digest']
    for secret in ('191.116.125.248','private-password','gAAAAA','uc1:','cookie-original'):
        assert secret not in str(hold)
    assert not await db.outreach_proxy_adoptions.find_one({'workspace_id':'w'})
    with pytest.raises((CustodyUnavailable, suppression.SuppressionUnavailable)): await adopt(db, view)


async def test_retention_removal_precedes_strict_adoption_duplicate_failure(real_legacy, monkeypatch):
    db = real_legacy
    await db.outreach_proxy_adoptions.insert_many([{'workspace_id':'w','proxy_id':ASSET}, {'workspace_id':'w','proxy_id':ASSET}])
    await db.outreach_proxy_adoptions.create_index('at',expireAfterSeconds=60)
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME',db.name)
    with pytest.raises(OperationFailure): await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in row for row in (await db.outreach_proxy_adoptions.index_information()).values())


async def test_actual_standalone_denies_before_opening_or_sealing(real_legacy, monkeypatch, tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    root = tmp_path/'standalone'; root.mkdir()
    process = subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port',str(port),
        '--bind_ip','127.0.0.1','--logpath',str(tmp_path/'standalone.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}/?directConnection=true',serverSelectionTimeoutMS=200)
    db = client['test_v230_standalone']
    try:
        for _ in range(50):
            try: await client.admin.command('ping'); break
            except Exception: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone did not start')
        for name in await real_legacy.list_collection_names():
            rows = await real_legacy[name].find({}).to_list(length=100)
            if rows: await db[name].insert_many(rows)
        view = await adoption.ProxyAdoption(db).inspect('w',ASSET)
        assert not view['blockers']
        monkeypatch.setattr(adoption, 'decrypt_strict', lambda *args: (_ for _ in ()).throw(AssertionError('No opening')))
        seal = AsyncMock(side_effect=AssertionError('No key work'))
        monkeypatch.setattr(adoption, 'seal_proxy_password',seal)
        with pytest.raises(suppression.SuppressionUnavailable): await adopt(db,view)
        seal.assert_not_awaited()
    finally:
        try: await client.drop_database(db.name)
        finally:
            client.close()
            process.terminate(); process.wait(timeout=10)
            shutil.rmtree(root)
