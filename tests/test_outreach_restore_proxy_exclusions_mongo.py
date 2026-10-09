"""Actual physical-IP exclusion transactions and transport guards; no external calls."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import os
import shutil
import socket
import subprocess
import uuid
import pytest
import pytest_asyncio
from pymongo.errors import DuplicateKeyError, PyMongoError
from outreach.core import restore_proxy_exclusions as ri, suppression, erasure, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_dispatch_authority import ready_db
from tests.test_outreach_restore_proxy_exclusions import source, apply, IP, BINDING

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def test_actual_original_digest_export_to_backup_preserves_only_negative_authority(real_restore):
    db = real_restore; await prepare(db)
    original = db.client['test_proxy_source_' + uuid.uuid4().hex]
    try:
        await original.account_proxy_ip_guards.insert_one({'_id': IP, 'binding_digest': BINDING})
        doc = await ri.export_manifest(original, 'w', [IP], workers_drained=True)
        before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
        assert (await apply(db, json.dumps(doc).encode()))['applied']
        row = await db.account_proxy_ip_guards.find_one({'_id': IP})
        assert row['binding_digest'] == BINDING and row['restore_reuse_blocked'] is True
        assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
        for name in ('outreach_payment_receipts', 'outreach_entitlements', 'outreach_access_requests'):
            assert await db[name].count_documents({}) == 0
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
        with pytest.raises(ValueError): await ri.export_manifest(db, 'w', [IP], workers_drained=True)
    finally: await db.client.drop_database(original.name)


async def test_concurrent_install_and_actual_commit_then_raise_ack_simulation(real_restore, monkeypatch):
    db = real_restore; await prepare(db); view = await ri.RestoreProxyExclusions(db).inspect('w', source())
    original = erasure._control; raised = False
    async def lose_ack(*args, **kwargs):
        nonlocal raised
        result = await original(*args, **kwargs)
        if not raised and not result['recovered']:
            raised = True; raise RuntimeError('Simulated acknowledgement loss after actual commit')
        return result
    monkeypatch.setattr(erasure, '_control', lose_ack)
    outcomes = await asyncio.gather(apply(db, view=view), apply(db, view=view), return_exceptions=True)
    assert sum(isinstance(x, RuntimeError) for x in outcomes) == 1
    assert sum(isinstance(x, dict) and x['recovered'] for x in outcomes) == 1
    await db.account_proxy_ip_guards.update_one({'_id': IP}, {'$set': {'later_metadata': True}})
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    before = await db.account_proxy_ip_guards.find_one({})
    assert (await apply(db, view=view))['recovered']
    assert epoch.stable(await db.account_proxy_ip_guards.find_one({})) == epoch.stable(before)
    assert await db.outreach_restore_proxy_exclusions.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['journal', 'epoch', 'flag'])
async def test_late_failure_rolls_back_global_block_and_journal(real_restore, monkeypatch, fault):
    db = real_restore; await prepare(db)
    await db.account_proxy_ip_guards.insert_one({'_id': IP, 'binding_digest': BINDING, 'original': True})
    before = await db.account_proxy_ip_guards.find_one({})
    original = suppression.SuppressionCollection.insert_one
    async def late(self, *args, **kwargs):
        if self.collection.name != 'outreach_restore_proxy_exclusions': return await original(self, *args, **kwargs)
        if fault == 'journal': raise RuntimeError('Journal interruption')
        result = await original(self, *args, **kwargs)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH' if fault == 'epoch' else 'OUTREACH_HEALTH_MONITOR_ENABLED',
                           'f' * 64 if fault == 'epoch' else 'true')
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'insert_one', late)
    with pytest.raises((RuntimeError, ValueError)): await apply(db)
    assert await db.account_proxy_ip_guards.find_one({}) == before
    assert await db.outreach_restore_proxy_exclusions.count_documents({}) == 0


@pytest.mark.parametrize('fault', ['binding', 'missing_saved', 'latch_saved', 'root_missing'])
async def test_current_binding_block_and_root_must_remain_proven(real_restore, fault):
    db = real_restore; await prepare(db); view = await ri.RestoreProxyExclusions(db).inspect('w', source())
    if fault in {'missing_saved', 'latch_saved'}: await apply(db, view=view)
    if fault == 'binding': await db.account_proxy_ip_guards.insert_one({'_id': IP, 'binding_digest': 'f' * 64})
    if fault == 'missing_saved': await db.account_proxy_ip_guards.delete_one({'_id': IP})
    if fault == 'latch_saved': await db.account_proxy_ip_guards.update_one({'_id': IP}, {'$unset': {'restore_reuse_blocked': ''}})
    if fault == 'root_missing': await db.outreach_execution_epochs.delete_one(epoch.root_scope('w'))
    with pytest.raises(ValueError): await apply(db, view=view)


async def test_ttl_free_strict_journal_and_full_erasure_preserve_global_negatives(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db = real_restore; await prepare(db)
    for name in ('account_proxy_ip_guards', 'account_proxy_ip_restore_fences', 'outreach_restore_proxy_exclusions'):
        await db[name].create_index('unsafe_expiry', expireAfterSeconds=9999)
    await remove_other_evidence_ttls(db); await ensure_integration_indexes(db); await apply(db)
    for name in ('account_proxy_ip_guards', 'account_proxy_ip_restore_fences', 'outreach_restore_proxy_exclusions'):
        assert all('expireAfterSeconds' not in d for d in (await db[name].index_information()).values())
    journal = await db.outreach_restore_proxy_exclusions.find_one({})
    with pytest.raises(DuplicateKeyError): await db.outreach_restore_proxy_exclusions.insert_one({**journal, '_id': 'duplicate'})
    before = await db.account_proxy_ip_guards.find_one({})
    service = erasure.OutreachErasure(db); await service.request('w', 'actor'); inspected = await service.inspect('w')
    assert (await service.finish('w', 'operator', 'All tenant writers and caches drained for erasure.',
        workers_drained=True, expected_digest=inspected['review_digest']))['status'] == 'erased'
    assert await db.outreach_restore_proxy_exclusions.count_documents({}) == 0
    assert await db.account_proxy_ip_guards.find_one({}) == before
    holds = await db.outreach_erasure_holds.find({'kind': 'restore_proxy_exclusion_provenance'}).to_list(length=10)
    assert len(holds) == 1 and not holds[0]['assets_restored'] and not holds[0]['activation_allowed']
    assert '191.116.125.248' not in json.dumps(holds, default=str)
    with pytest.raises(epoch.EpochUnavailable): await ri.RestoreProxyExclusions(db).inspect('w', source())



async def test_closed_hash_only_import_requires_existing_matching_root(real_restore):
    db = real_restore; await prepare(db)
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    assert (await apply(db))['applied']
    await db.outreach_execution_epochs.delete_one(epoch.root_scope('w'))
    with pytest.raises(epoch.EpochUnavailable): await ri.RestoreProxyExclusions(db).inspect('w', source())


async def test_cross_workspace_missing_global_guard_and_fence_order_import_before_read(real_restore, monkeypatch):
    from outreach.core import proxy_identity
    from pymongo.errors import PyMongoError
    db = real_restore; await prepare(db)
    assert await db.account_proxy_ip_guards.count_documents({}) == 0
    assert await db.account_proxy_ip_restore_fences.count_documents({}) == 0
    seen, release = asyncio.Event(), asyncio.Event(); original = proxy_identity.touch_restore_fence; once = False
    async def pause(raw, key, **options):
        nonlocal once
        if asyncio.current_task().get_name() == 'negative-check' and not once:
            once = True; seen.set(); await release.wait()
        return await original(raw, key, **options)
    monkeypatch.setattr(proxy_identity, 'touch_restore_fence', pause)
    async def check(current):
        if not await proxy_identity.restore_ip_allowed(current, '191.116.125.248'):
            raise ValueError('Selected IP blocked before admission')
        await current.outreach_probe_admissions.insert_one({'workspace_id': 'other', '_id': 'synthetic-only'})
    task = asyncio.create_task(suppression.mutate_suppression(db, 'other', check), name='negative-check')
    try:
        await asyncio.wait_for(seen.wait(), 5)
        assert (await apply(db))['applied']
        release.set()
        with pytest.raises((ValueError, PyMongoError, suppression.SuppressionUnavailable)): await asyncio.wait_for(task, 5)
        assert await db.outreach_probe_admissions.count_documents({}) == 0
        with pytest.raises(ValueError): await suppression.mutate_suppression(db, 'other', check)
        assert await db.account_proxy_ip_restore_fences.count_documents({}) == 1
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_concurrent_initial_fence_checks_never_invent_original_binding(real_restore):
    from outreach.core.proxy_identity import restore_ip_allowed
    from pymongo.errors import PyMongoError
    db = real_restore
    async def check(current): return await restore_ip_allowed(current, '191.116.125.248')
    results = await asyncio.gather(*(suppression.mutate_suppression(db, workspace, check)
        for workspace in ['first', 'second']), return_exceptions=True)
    assert any(result is True for result in results)
    assert all(result is True or isinstance(result, (PyMongoError, suppression.SuppressionUnavailable)) for result in results)
    assert await db.account_proxy_ip_guards.count_documents({}) == 0
    assert await db.account_proxy_ip_restore_fences.count_documents({}) == 1


@pytest.mark.parametrize('blocked_host', ['actual', 'inventory'])
async def test_actual_dispatch_checks_mismatched_legacy_transport_and_inventory(ready_db, blocked_host):
    from tests.test_outreach_dispatch_authority import dispatch
    from outreach.core.request_guard import RequestDenied
    from outreach.core.authorization import canonical_hash
    from unittest.mock import AsyncMock
    import httpx
    db, job = ready_db
    inventory_host = '191.116.125.248'
    await db.outreach_proxy_inventory.update_one({'_id': 'local-ip'}, {'$set': {'host': inventory_host}})
    host = '127.0.0.1' if blocked_host == 'actual' else inventory_host
    await db.account_proxy_ip_guards.insert_one({'_id': canonical_hash(['managed-proxy-ip-v1', host]),
        'binding_digest': BINDING, 'restore_reuse_blocked': True})
    factory = AsyncMock(return_value=httpx.Response(200, json={}))
    with pytest.raises(RequestDenied): await dispatch(db, job, factory)
    factory.assert_not_awaited()


async def test_saved_negative_read_write_fence_denies_concurrent_dispatch(ready_db, monkeypatch):
    from outreach.core import proxy_identity
    from tests.test_outreach_dispatch_authority import dispatch
    from outreach.core.request_guard import RequestDenied
    from outreach.core.authorization import canonical_hash
    from unittest.mock import AsyncMock
    import httpx
    db, job = ready_db; seen, release = asyncio.Event(), asyncio.Event(); original = proxy_identity.touch_restore_fence; once = False
    key = canonical_hash(['managed-proxy-ip-v1', '127.0.0.1'])
    async def pause(raw, identity, **options):
        nonlocal once
        if options and not once:
            once = True; seen.set(); await release.wait()
        return await original(raw, identity, **options)
    monkeypatch.setattr(proxy_identity, 'touch_restore_fence', pause)
    factory = AsyncMock(return_value=httpx.Response(200, json={}))
    task = asyncio.create_task(dispatch(db, job, factory))
    async def block(current):
        await original(current.database, key, session=current.session)
        await current.database.account_proxy_ip_guards.update_one({'_id': key},
            {'$set': {'binding_digest': BINDING, 'restore_reuse_blocked': True}}, upsert=True, session=current.session)
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await suppression.mutate_suppression(db, 'different-workspace', block)
        release.set()
        with pytest.raises((RequestDenied, PyMongoError, suppression.SuppressionUnavailable)): await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)

@pytest.mark.parametrize('operation', ['import', 'negative_admission'])
async def test_standalone_denies_import_and_guarded_health_admission(real_restore, tmp_path, monkeypatch, operation):
    from motor.motor_asyncio import AsyncIOMotorClient
    from outreach.core.proxy_identity import check_restore_ips
    await prepare(real_restore)
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    storage = tmp_path / 'mongo'; storage.mkdir()
    with (tmp_path / 'mongo.log').open('w') as log:
        proc = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(storage), '--bind_ip',
            '127.0.0.1', '--port', str(port)], stdout=log, stderr=log)
        client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=1000)
        db = client['test_proxy_standalone_' + uuid.uuid4().hex]
        try:
            for attempt in range(20):
                try: await client.admin.command('ping'); break
                except Exception:
                    if attempt == 19: raise
                    await asyncio.sleep(.2)
            if operation == 'import':
                for name in ('outreach_execution_epochs', 'outreach_suppression_guards'):
                    rows = await real_restore[name].find({}).to_list(length=10)
                    if rows: await db[name].insert_many(rows)
                with pytest.raises(suppression.SuppressionUnavailable): await apply(db)
            else:
                monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false'); monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '')
                with pytest.raises(suppression.SuppressionUnavailable): await check_restore_ips(db, 'w', ['191.116.125.248'])
            for name in ('outreach_restore_proxy_exclusions', 'account_proxy_ip_guards', 'account_proxy_ip_restore_fences'):
                assert await db[name].count_documents({}) == 0
        finally:
            try: await client.drop_database(db.name)
            finally: client.close(); proc.terminate(); proc.wait(timeout=10); shutil.rmtree(storage)

async def test_explicit_first_fence_duplicate_abort_is_wrapped_and_denies_without_fallback(real_restore, monkeypatch):
    from outreach.core import proxy_identity
    db = real_restore
    async def duplicate(*args, **kwargs): raise DuplicateKeyError('Synthetic first-upsert abort')
    monkeypatch.setattr(proxy_identity, 'touch_restore_fence', duplicate)
    async def check(current): return await proxy_identity.restore_ip_allowed(current, '191.116.125.248')
    with pytest.raises(suppression.SuppressionUnavailable):
        await suppression.mutate_suppression(db, 'other', check)
    assert await db.account_proxy_ip_guards.count_documents({}) == 0
    assert await db.account_proxy_ip_restore_fences.count_documents({}) == 0


async def test_actual_iproyal_install_preserves_prepared_account_when_blocked(real_restore, monkeypatch):
    from tests.test_outreach_connection_worker import make_db
    from outreach.core.connection_repair import ConnectionRepair
    from outreach.core.managed_proxy import _proxy_from_inventory
    db = real_restore
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false'); monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '')
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    memory = make_db()
    memory.outreach_connection_jobs.docs[0].update(status='running', verification_owner_token='owner')
    for name, collection in memory.collections.items():
        if collection.docs: await db[name].insert_many(collection.docs)
    job = await db.outreach_connection_jobs.find_one({'id': 'job-1', 'workspace_id': 'ws-1'})
    repair = ConnectionRepair(db)
    await repair.prepare(job, 'owner', 'generation', {'account_name': 'Pilot', 'linkedin_urn': 'urn:li:person:one'})
    await db.outreach_connection_jobs.update_one({'id': 'job-1', 'workspace_id': 'ws-1'},
        {'$set': {'status': 'finalizing', 'credential_generation': 'generation'}})
    inventory = await db.outreach_proxy_inventory.find_one({'_id': 'iproyal:one'})
    await db.account_proxy_ip_guards.insert_one({'_id': IP, 'binding_digest': BINDING, 'restore_reuse_blocked': True})
    before = await db.outreach_accounts.find_one({'workspace_id': 'ws-1'})
    assert not await repair.install(job, 'owner', 'generation', {'proxy': _proxy_from_inventory(inventory).model_dump(),
        'status': 'active', 'session_cookie_enc': 'unused-test-ciphertext'})
    after = await db.outreach_accounts.find_one({'workspace_id': 'ws-1'})
    assert epoch.stable(after) == epoch.stable(before)
    assert not after.get('session_cookie_enc') and after['connection_finalization']['state'] == 'prepared'
