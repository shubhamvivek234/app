"""Actual replica-set transactions for proxy custody and reference-only storage closure."""
import asyncio
import os
import uuid
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from outreach.core import suppression
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.proxy_migration import ProxyMigration
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.connection_storage_repair import ConnectionStorageRepair
from outreach.core.dispatch_authority import AuthorityCollection
from tests.test_outreach_proxy_migration import proxy_db
from tests.test_outreach_connection_storage_repair import storage_db
from tests.test_outreach_session_custody import scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable local replica set is opt-in')]

async def copy_to_mongo(source):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client['test_unravler_proxy_storage_' + uuid.uuid4().hex]
    for name, collection in source.collections.items():
        if collection.docs: await db[name].insert_many(collection.docs)
    await db.outreach_connection_jobs.create_index([('workspace_id', 1), ('id', 1)], unique=True)
    return client, db

@pytest_asyncio.fixture
async def real_proxy(proxy_db):
    client, db = await copy_to_mongo(proxy_db)
    try: yield db
    finally:
        await client.drop_database(db.name); client.close()

@pytest_asyncio.fixture
async def real_storage(storage_db):
    client, db = await copy_to_mongo(storage_db)
    try: yield db
    finally:
        await client.drop_database(db.name); client.close()

async def test_proxy_inventory_and_aliases_commit_together_and_actual_indexes(real_proxy, monkeypatch):
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
    assert not view['blockers']
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    inventory = await db.outreach_proxy_inventory.find_one({})
    account = await db.outreach_accounts.find_one({})
    prepared = await prepare_proxy(account['proxy'], 'w')
    assert prepared.matches(inventory, 'w') and prepared.matches(account['proxy_config'], 'w')
    assert account['credential_generation'] == 'cookie-generation' and account['status'] == 'paused'
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME', db.name); await create_all_indexes(db.client)
    indexes = await db.outreach_credential_migrations.index_information()
    assert any(row['key'] == [('workspace_id', 1), ('proxy_id', 1), ('at', -1)] for row in indexes.values())
    assert not any('expireAfterSeconds' in row for row in indexes.values())
    receipt = await db.outreach_credential_migrations.find_one({})
    assert 'private-password' not in str(receipt) and 'uc1:' not in str(receipt)

@pytest.mark.parametrize('target', ['outreach_accounts', 'outreach_credential_migrations'])
async def test_failed_migration_projection_rolls_back_inventory_and_aliases(real_proxy, monkeypatch, target):
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
    original_account = await db.outreach_accounts.find_one({})
    from outreach.core.suppression import SuppressionCollection
    update, insert = SuppressionCollection.update_one, SuppressionCollection.insert_one
    async def fail_update(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('local projection interrupted')
        return await update(self, *args, **kwargs)
    async def fail_insert(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('local receipt interrupted')
        return await insert(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail_update)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail_insert)
    with pytest.raises(RuntimeError): await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    assert (await db.outreach_proxy_inventory.find_one({}))['password_enc'].startswith('gAAAAA')
    assert (await db.outreach_accounts.find_one({}))['proxy'] == original_account['proxy']
    assert not await db.outreach_credential_migrations.find_one({})

@pytest.mark.parametrize('change', ['inventory', 'alias', 'lease', 'permission', 'campaign', 'orphan', 'erasure', 'mode'])
async def test_change_while_kms_opens_refuses_install(real_proxy, monkeypatch, change):
    from outreach.core import proxy_migration
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p'); seal = proxy_migration.seal_proxy_password
    async def changed(*args, **kwargs):
        result = await seal(*args, **kwargs)
        if change == 'inventory': await db.outreach_proxy_inventory.update_one({}, {'$set': {'credential_generation': 'replacement'}})
        if change == 'alias': await db.outreach_accounts.update_one({}, {'$set': {'proxy_config.host': '8.8.8.8'}})
        if change == 'lease': await db.outreach_proxy_leases.update_one({}, {'$set': {'sender_id': 'replacement'}})
        if change == 'permission': await db.outreach_sender_execution.update_one({}, {'$set': {'permission.latched': False}})
        if change == 'mode': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
        if change in {'campaign', 'orphan', 'erasure'}:
            async def write(current):
                if change == 'campaign': await current.outreach_campaigns.insert_one({'workspace_id': 'w', 'sender_account_ids': ['a'], 'status': 'active'})
                if change == 'orphan': await current.outreach_connection_locks.insert_one({'workspace_id': 'w', '_id': 'a', 'job_id': 'orphan'})
                if change == 'erasure': await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'requested'}})
            await suppression.mutate_suppression(db, 'w', write)
        return result
    monkeypatch.setattr(proxy_migration, 'seal_proxy_password', changed)
    with pytest.raises((CustodyUnavailable, suppression.SuppressionUnavailable)):
        await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    assert (await db.outreach_proxy_inventory.find_one({}))['password_enc'].startswith('gAAAAA')
    assert not await db.outreach_credential_migrations.find_one({})

@pytest.mark.parametrize('authority', ['outreach_proxy_inventory', 'outreach_proxy_leases', 'outreach_accounts', 'outreach_sender_execution'])
async def test_proxy_existing_authority_edit_after_read_retries_before_kms(real_proxy, monkeypatch, authority):
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
    seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.fence; paused = False
    async def pause(self, document, query):
        nonlocal paused
        if self.name == authority and not paused:
            paused = True; seen.set(); await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    seal = AsyncMock(side_effect=AssertionError('Must deny before KMS'))
    monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', seal)
    task = asyncio.create_task(service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        changes = {'operator_revision': 'replacement'}
        await db[authority].update_one({}, {'$set': changes})
    finally: release.set()
    with pytest.raises(CustodyUnavailable): await task
    seal.assert_not_awaited()

async def test_proxy_lost_commit_ack_replays_only_metadata_receipt(real_proxy, monkeypatch):
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p'); mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == 'apply': raise TimeoutError('local commit response loss')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    with pytest.raises(TimeoutError): await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', AsyncMock(side_effect=AssertionError('No replay')))
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    assert await db.outreach_credential_migrations.count_documents({}) == 1

async def test_storage_closure_is_atomic_and_ttl_free_with_late_insertion_rejected(real_storage):
    db = real_storage; service = ConnectionStorageRepair(db); view = await service.inspect('w', 'job')
    assert (await service.resolve('w', 'job', 'operator', 'All actual connection writers drained before exact inspection.', view['digest'], workers_drained=True))['status'] == 'storage_stopped'
    row = await db.outreach_connection_jobs.find_one({})
    assert 'created_at' not in row and row['storage_closure']['review_digest'] == view['digest']
    assert not await db.outreach_proxy_leases.find_one({}) and not await db.outreach_sender_slots.find_one({})
    assert not await db.outreach_connection_locks.find_one({})
    assert (await db.outreach_sender_execution.find_one({}))['permission']['latched']
    with pytest.raises(DuplicateKeyError): await db.outreach_connection_jobs.insert_one({'id': 'job', 'workspace_id': 'w', 'sender_id': 'a', 'status': 'queued'})
    # The participating API also cannot read its former lock after closure.
    async def late(current):
        assert not await current.outreach_connection_locks.find_one({'workspace_id': 'w', '_id': 'a', 'job_id': 'job'})
    await suppression.mutate_suppression(db, 'w', late)

@pytest.mark.parametrize('target', ['outreach_connection_jobs', 'outreach_proxy_leases', 'outreach_connection_locks'])
async def test_storage_failure_rolls_back_stop_closure_and_all_resources(real_storage, monkeypatch, target):
    from outreach.core.suppression import SuppressionCollection
    db = real_storage; service = ConnectionStorageRepair(db); view = await service.inspect('w', 'job')
    insert, delete = SuppressionCollection.insert_one, SuppressionCollection.delete_one
    async def fail_insert(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('local interrupted write')
        return await insert(self, *args, **kwargs)
    async def fail_delete(self, *args, **kwargs):
        if self.collection.name == target: raise RuntimeError('local interrupted cleanup')
        return await delete(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail_insert); monkeypatch.setattr(SuppressionCollection, 'delete_one', fail_delete)
    with pytest.raises(RuntimeError): await service.resolve('w', 'job', 'operator', 'All storage writers stopped for exact drained repair.', view['digest'], workers_drained=True)
    assert await db.outreach_connection_locks.count_documents({}) == 1 and await db.outreach_sender_slots.count_documents({}) == 1
    assert await db.outreach_proxy_leases.count_documents({}) == 1 and not await db.outreach_connection_jobs.find_one({})
    assert not await db.outreach_sender_execution.find_one({})

@pytest.mark.parametrize('authority', ['outreach_connection_locks', 'outreach_sender_slots', 'outreach_proxy_leases'])
async def test_storage_reference_replacement_after_read_cannot_release_new_owner(real_storage, monkeypatch, authority):
    db = real_storage; service = ConnectionStorageRepair(db); view = await service.inspect('w', 'job')
    seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.fence; paused = False
    async def pause(self, document, query):
        nonlocal paused
        if self.name == authority and not paused:
            paused = True; seen.set(); await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    task = asyncio.create_task(service.resolve('w', 'job', 'operator', 'Full drained inspection of exact reservation generations.', view['digest'], workers_drained=True))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await db[authority].update_one({}, {'$set': {'replacement_revision': 'new'}})
    finally: release.set()
    with pytest.raises(CustodyUnavailable): await task
    assert await db.outreach_proxy_leases.count_documents({}) == 1 and await db.outreach_sender_slots.count_documents({}) == 1
    assert not await db.outreach_connection_jobs.find_one({})

async def test_storage_lost_ack_and_erasure_do_not_repeat_cleanup_or_reopen(real_storage, monkeypatch):
    db = real_storage; service = ConnectionStorageRepair(db); view = await service.inspect('w', 'job'); mutate = suppression.mutate_suppression
    async def lost(*args):
        await mutate(*args); raise TimeoutError('local repair commit response loss')
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    with pytest.raises(TimeoutError): await service.resolve('w', 'job', 'operator', 'Drained all connection writers before reviewing absent storage.', view['digest'], workers_drained=True)
    monkeypatch.setattr(suppression, 'mutate_suppression', mutate)
    await db.outreach_proxy_leases.insert_one({'_id': 'replacement', 'workspace_id': 'w', 'sender_id': 'a'})
    assert (await service.resolve('w', 'job', 'operator', 'Reviewed saved committed stop closure after complete drain.', view['digest'], workers_drained=True))['status'] == 'storage_stopped'
    assert await db.outreach_proxy_leases.find_one({'_id': 'replacement'})
    # Erasure may purge the ordinary closure metadata only after permanently
    # closing this workspace. There is no reinsert/reopen after that guard.
    from outreach.core.erasure import OutreachErasure
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'u'})
    erasure = OutreachErasure(db); await erasure.request('w', 'u')
    review = await erasure.inspect('w')
    await erasure.finish('w', 'operator', 'All workspace writers drained after permanent erasure stop.', workers_drained=True, expected_digest=review['review_digest'])
    assert not await db.outreach_connection_jobs.find_one({})
    with pytest.raises(suppression.SuppressionUnavailable): await suppression.mutate_suppression(db, 'w', lambda current: current.outreach_connection_jobs.insert_one({'workspace_id': 'w', 'id': 'job', 'status': 'queued'}))

async def test_proxy_erasure_scrubs_inventory_and_migration_receipts(real_proxy):
    from outreach.core.erasure import OutreachErasure
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
    await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'u'})
    erasure = OutreachErasure(db); await erasure.request('w', 'u')
    assert not (await db.outreach_proxy_inventory.find_one({})).get('password_enc')
    review = await erasure.inspect('w')
    await erasure.finish('w', 'operator', 'All workspace writers drained after permanent erasure stop.', workers_drained=True, expected_digest=review['review_digest'])
    assert not await db.outreach_credential_migrations.find_one({})
    assert not await db.outreach_accounts.find_one({})

@pytest.mark.parametrize('change', [False, True])
async def test_final_physical_authorization_fences_current_proxy_ciphertext_without_kms(real_proxy, monkeypatch, scoped, change):
    import httpx
    from datetime import datetime, timedelta, timezone
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    db = real_proxy; service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
    await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    account = await db.outreach_accounts.find_one({})
    prepared = await prepare_proxy(account['proxy'], 'w')
    await db.outreach_accounts.update_one({}, {'$set': {'status': 'active', 'country_code': 'IN'}})
    await db.outreach_entitlements.insert_one({'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': datetime.now(timezone.utc) + timedelta(days=1)})
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    await ExecutionPermission(db).grant('w', 'a', 'cookie-generation', ['sync'], 'operator', clear_latch=True)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No KMS inside transaction')))
    envelope = RequestEnvelope(db, 'w', 'a', 'cookie-generation', 'sync', prepared.url, prepared_proxy=prepared)
    factory = AsyncMock(return_value=httpx.Response(200, json={'elements': []}))
    if not change:
        assert (await envelope.call('GET', '/voyager/api/messaging', factory)).status_code == 200
        factory.assert_awaited_once()
        assert (await db.outreach_physical_requests.find_one({})).get('dispatch_authorization')
        return
    original = AuthorityCollection.fence; seen, release = asyncio.Event(), asyncio.Event(); paused = False
    async def pause(self, document, query):
        nonlocal paused
        if self.name == 'outreach_proxy_inventory' and not paused:
            paused = True; seen.set(); await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    task = asyncio.create_task(envelope.call('GET', '/voyager/api/messaging', factory))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await db.outreach_proxy_inventory.update_one({}, {'$set': {'password_enc': 'replacement'}})
    finally: release.set()
    with pytest.raises(RequestDenied): await task
    factory.assert_not_awaited()

async def test_actual_standalone_denies_migration_and_storage_cleanup_before_key_calls(proxy_db, storage_db, monkeypatch, tmp_path):
    import shutil, socket, subprocess
    from pymongo.errors import PyMongoError
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    storage = tmp_path / 'standalone'; storage.mkdir()
    process = subprocess.Popen([shutil.which('mongod'), '--bind_ip', '127.0.0.1', '--port', str(port), '--dbpath', str(storage),
        '--logpath', str(storage / 'mongo.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', tz_aware=True, serverSelectionTimeoutMS=200)
    try:
        async with asyncio.timeout(10):
            while True:
                assert process.poll() is None
                try: await client.admin.command('ping'); break
                except PyMongoError: await asyncio.sleep(0.1)
        for source, name, kind in ((proxy_db, 'test_proxy_standalone', 'proxy'), (storage_db, 'test_storage_standalone', 'storage')):
            db = client[name]
            for collection, rows in source.collections.items():
                if rows.docs: await db[collection].insert_many(rows.docs)
            if kind == 'proxy':
                service = ProxyMigration(db); view = await service.inspect('w', 'iproyal:p')
                key_call = AsyncMock(side_effect=AssertionError('No key calls'))
                monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', key_call)
                with pytest.raises(suppression.SuppressionUnavailable): await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
                key_call.assert_not_awaited()
                assert (await db.outreach_proxy_inventory.find_one({}))['password_enc'].startswith('gAAAAA')
            else:
                service = ConnectionStorageRepair(db); view = await service.inspect('w', 'job')
                with pytest.raises(suppression.SuppressionUnavailable): await service.resolve('w', 'job', 'operator', 'Full writer drain for exact standalone storage inspection.', view['digest'], workers_drained=True)
                assert await db.outreach_connection_locks.find_one({}) and await db.outreach_proxy_leases.find_one({})
                assert not await db.outreach_connection_jobs.find_one({})
            await client.drop_database(name)
    finally:
        client.close(); process.terminate()
        await asyncio.to_thread(process.wait, 10)
