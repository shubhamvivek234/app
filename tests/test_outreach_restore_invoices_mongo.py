"""Actual invoice exclusion and final payment transactions; no external calls."""
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
from pymongo.errors import DuplicateKeyError
from outreach.core import restore_invoices as ri, suppression, erasure, restore_epoch as epoch, paid_access
from outreach.core.authorization import canonical_hash
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_restore_invoices import source, apply, INVOICE, BINDING

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def test_actual_original_digest_export_to_backup_preserves_only_negative_authority(real_restore):
    db = real_restore; await prepare(db)
    original = db.client['test_invoice_source_' + uuid.uuid4().hex]
    try:
        await original.account_invoice_guards.insert_one({'_id': INVOICE, 'binding_digest': BINDING})
        doc = await ri.export_manifest(original, 'w', [INVOICE], workers_drained=True)
        before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
        assert (await apply(db, json.dumps(doc).encode()))['applied']
        row = await db.account_invoice_guards.find_one({'_id': INVOICE})
        assert row['binding_digest'] == BINDING and row['restore_reuse_blocked'] is True
        assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
        for name in ('outreach_payment_receipts', 'outreach_entitlements', 'outreach_access_requests'):
            assert await db[name].count_documents({}) == 0
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
        with pytest.raises(ValueError): await ri.export_manifest(db, 'w', [INVOICE], workers_drained=True)
    finally: await db.client.drop_database(original.name)


async def test_concurrent_install_and_actual_commit_then_raise_ack_simulation(real_restore, monkeypatch):
    db = real_restore; await prepare(db); view = await ri.RestoreInvoices(db).inspect('w', source())
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
    await db.account_invoice_guards.update_one({'_id': INVOICE}, {'$set': {'later_metadata': True}})
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    before = await db.account_invoice_guards.find_one({})
    assert (await apply(db, view=view))['recovered']
    assert epoch.stable(await db.account_invoice_guards.find_one({})) == epoch.stable(before)
    assert await db.outreach_restore_invoices.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['journal', 'epoch', 'flag'])
async def test_late_failure_rolls_back_global_block_and_journal(real_restore, monkeypatch, fault):
    db = real_restore; await prepare(db)
    await db.account_invoice_guards.insert_one({'_id': INVOICE, 'binding_digest': BINDING, 'original': True})
    before = await db.account_invoice_guards.find_one({})
    original = suppression.SuppressionCollection.insert_one
    async def late(self, *args, **kwargs):
        if self.collection.name != 'outreach_restore_invoices': return await original(self, *args, **kwargs)
        if fault == 'journal': raise RuntimeError('Journal interruption')
        result = await original(self, *args, **kwargs)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH' if fault == 'epoch' else 'OUTREACH_HEALTH_MONITOR_ENABLED',
                           'f' * 64 if fault == 'epoch' else 'true')
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'insert_one', late)
    with pytest.raises((RuntimeError, ValueError)): await apply(db)
    assert await db.account_invoice_guards.find_one({}) == before
    assert await db.outreach_restore_invoices.count_documents({}) == 0


@pytest.mark.parametrize('fault', ['binding', 'missing_saved', 'latch_saved', 'root_missing'])
async def test_current_binding_block_and_root_must_remain_proven(real_restore, fault):
    db = real_restore; await prepare(db); view = await ri.RestoreInvoices(db).inspect('w', source())
    if fault in {'missing_saved', 'latch_saved'}: await apply(db, view=view)
    if fault == 'binding': await db.account_invoice_guards.insert_one({'_id': INVOICE, 'binding_digest': 'f' * 64})
    if fault == 'missing_saved': await db.account_invoice_guards.delete_one({'_id': INVOICE})
    if fault == 'latch_saved': await db.account_invoice_guards.update_one({'_id': INVOICE}, {'$unset': {'restore_reuse_blocked': ''}})
    if fault == 'root_missing': await db.outreach_execution_epochs.delete_one(epoch.root_scope('w'))
    with pytest.raises(ValueError): await apply(db, view=view)


async def test_ttl_free_strict_journal_and_full_erasure_preserve_global_negatives(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db = real_restore; await prepare(db)
    for name in ('account_invoice_guards', 'outreach_restore_invoices'):
        await db[name].create_index('unsafe_expiry', expireAfterSeconds=9999)
    await remove_other_evidence_ttls(db); await ensure_integration_indexes(db); await apply(db)
    for name in ('account_invoice_guards', 'outreach_restore_invoices'):
        assert all('expireAfterSeconds' not in d for d in (await db[name].index_information()).values())
    journal = await db.outreach_restore_invoices.find_one({})
    with pytest.raises(DuplicateKeyError): await db.outreach_restore_invoices.insert_one({**journal, '_id': 'duplicate'})
    before = await db.account_invoice_guards.find_one({})
    service = erasure.OutreachErasure(db); await service.request('w', 'actor'); inspected = await service.inspect('w')
    assert (await service.finish('w', 'operator', 'All tenant writers and caches drained for erasure.',
        workers_drained=True, expected_digest=inspected['review_digest']))['status'] == 'erased'
    assert await db.outreach_restore_invoices.count_documents({}) == 0
    assert await db.account_invoice_guards.find_one({}) == before
    holds = await db.outreach_erasure_holds.find({'kind': 'restore_invoice_provenance'}).to_list(length=10)
    assert len(holds) == 1 and not holds[0]['payment_restored'] and not holds[0]['activation_allowed']
    assert 'private-invoice' not in json.dumps(holds, default=str)
    with pytest.raises(epoch.EpochUnavailable): await ri.RestoreInvoices(db).inspect('w', source())


@pytest_asyncio.fixture
async def legacy_payment(real_restore, monkeypatch):
    db = real_restore
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false'); monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '')
    term = epoch.now() + timedelta(days=30)
    await db.outreach_access_requests.insert_one({'_id': 'request', 'workspace_id': 'w', 'country_code': 'IN', 'seats': 1})
    await db.outreach_proxy_inventory.insert_one({'_id': 'ip', 'last_workspace_id': 'w', 'country_code': 'IN',
        'status': 'available', 'provider': 'iproyal_static', 'expires_at': term + timedelta(days=1)})
    return db, term


async def pay(db, term):
    return await paid_access.record_verified_payment(db, 'w', 'private-invoice', 'operator', 1, term)


async def test_actual_payment_commits_once_and_exact_retry_preserves_revoked_state(legacy_payment):
    db, term = legacy_payment
    results = await asyncio.gather(pay(db, term), pay(db, term))
    assert all(result['status'] == 'active' for result in results)
    assert await db.outreach_payment_receipts.count_documents({}) == 1
    assert await db.outreach_entitlements.count_documents({}) == 1
    assert (await db.outreach_access_requests.find_one({}))['status'] == 'fulfilled'
    await db.outreach_entitlements.update_one({'workspace_id': 'w'}, {'$set': {'status': 'expired', 'is_revoked': True}})
    before = await db.outreach_entitlements.find_one({})
    assert (await pay(db, term))['is_revoked']
    assert epoch.stable(await db.outreach_entitlements.find_one({})) == epoch.stable(before)


async def test_consumed_guard_denies_exact_terms_but_remains_archivable(legacy_payment):
    db, term = legacy_payment
    await paid_access.claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
    await db.account_invoice_guards.update_one({'_id': INVOICE}, {'$set': {'restore_reuse_blocked': True}})
    await paid_access.claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
    with pytest.raises(ValueError, match='restore-blocked'): await pay(db, term)
    for name in ('outreach_payment_receipts', 'outreach_entitlements'): assert await db[name].count_documents({}) == 0


@pytest.mark.parametrize('fault', ['entitlement_write', 'request_write', 'late_epoch'])
async def test_payment_finalization_fault_rolls_back_every_financial_write(legacy_payment, monkeypatch, fault):
    db, term = legacy_payment; original = suppression.SuppressionCollection.update_one
    before = await db.outreach_access_requests.find_one({})
    async def fail(self, *args, **kwargs):
        name = self.collection.name
        if fault == 'entitlement_write' and name == 'outreach_entitlements': raise RuntimeError('Interrupted entitlement')
        if fault == 'request_write' and name == 'outreach_access_requests': raise RuntimeError('Interrupted request')
        result = await original(self, *args, **kwargs)
        if fault == 'late_epoch' and name == 'outreach_access_requests': monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', 'f' * 64)
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'update_one', fail)
    with pytest.raises((RuntimeError, ValueError)): await pay(db, term)
    for name in ('account_invoice_guards', 'outreach_payment_receipts', 'outreach_entitlements'):
        assert await db[name].count_documents({}) == 0
    assert await db.outreach_access_requests.find_one({}) == before


async def test_stopped_epoch_cannot_finalize_paid_access(real_restore):
    db = real_restore; term = epoch.now() + timedelta(days=30)
    await db.outreach_access_requests.insert_one({'workspace_id': 'w', 'country_code': 'IN', 'seats': 1})
    await db.outreach_proxy_inventory.insert_one({'last_workspace_id': 'w', 'country_code': 'IN',
        'status': 'available', 'provider': 'iproyal_static', 'expires_at': term + timedelta(days=1)})
    await prepare(db)
    with pytest.raises(epoch.EpochUnavailable): await pay(db, term)
    assert await db.outreach_payment_receipts.count_documents({}) == 0


async def test_request_replacement_before_fence_denies_financial_writes(legacy_payment, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db, term = legacy_payment; seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.fence; once = False
    async def pause(self, document, query):
        nonlocal once
        if self.name == 'outreach_access_requests' and not once:
            once = True; seen.set(); await release.wait()
        return await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    task = asyncio.create_task(pay(db, term))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await db.outreach_access_requests.update_one({'workspace_id': 'w'}, {'$set': {'country_code': 'US'}})
        release.set()
        with pytest.raises(ValueError, match='changed'): await asyncio.wait_for(task, 5)
        assert await db.outreach_payment_receipts.count_documents({}) == 0
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_cross_workspace_consumed_writer_before_global_fence_blocks_payment(legacy_payment, monkeypatch):
    db, term = legacy_payment
    await paid_access.claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
    seen, release = asyncio.Event(), asyncio.Event(); original = paid_access.claim_invoice_reference; once = False
    async def pause(*args, **kwargs):
        nonlocal once
        if kwargs.get('reject_restore_blocked') and not once:
            once = True; seen.set(); await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(paid_access, 'claim_invoice_reference', pause)
    task = asyncio.create_task(pay(db, term))
    async def block(current):
        await current.database.account_invoice_guards.update_one({'_id': INVOICE},
            {'$set': {'restore_reuse_blocked': True}, '$inc': {'dispatch_fence_revision': 1}}, session=current.session)
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await erasure._control(db, 'different-review-workspace', block); release.set()
        with pytest.raises(ValueError, match='restore-blocked'): await asyncio.wait_for(task, 5)
        assert await db.outreach_payment_receipts.count_documents({}) == 0
        assert await db.outreach_entitlements.count_documents({}) == 0
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('operation', ['import', 'payment'])
async def test_standalone_has_no_invoice_or_payment_fallback(real_restore, tmp_path, monkeypatch, operation):
    from motor.motor_asyncio import AsyncIOMotorClient
    await prepare(real_restore)
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    storage = tmp_path / 'mongo'; storage.mkdir()
    with (tmp_path / 'mongo.log').open('w') as log:
        proc = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(storage), '--bind_ip',
            '127.0.0.1', '--port', str(port)], stdout=log, stderr=log)
        client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=1000)
        db = client['test_invoice_standalone_' + uuid.uuid4().hex]
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
                term = epoch.now() + timedelta(days=30)
                await db.outreach_access_requests.insert_one({'workspace_id': 'w', 'country_code': 'IN', 'seats': 1})
                await db.outreach_proxy_inventory.insert_one({'last_workspace_id': 'w', 'country_code': 'IN',
                    'status': 'available', 'provider': 'iproyal_static', 'expires_at': term + timedelta(days=1)})
                with pytest.raises(suppression.SuppressionUnavailable): await pay(db, term)
            for name in ('outreach_restore_invoices', 'account_invoice_guards', 'outreach_payment_receipts', 'outreach_entitlements'):
                assert await db[name].count_documents({}) == 0
        finally:
            try: await client.drop_database(db.name)
            finally: client.close(); proc.terminate(); proc.wait(timeout=10); shutil.rmtree(storage)


async def test_closed_target_accepts_only_hash_negative_with_matching_stopped_root(real_restore):
    db = real_restore; await prepare(db)
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    assert (await apply(db))['applied']
    assert (await db.outreach_suppression_guards.find_one(suppression.guard_scope('w')))['erasure_state'] == 'erased'
    assert await db.outreach_entitlements.count_documents({}) == 0


@pytest.mark.parametrize('late', [False, True])
async def test_actual_final_deadline_denial_rolls_back_all_money_projection(legacy_payment, monkeypatch, late):
    from datetime import datetime
    db, term = legacy_payment; initial = epoch.now(); calls = 0
    before = await db.outreach_access_requests.find_one({})
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            calls += 1
            return initial if calls < (3 if late else 2) else term + timedelta(seconds=1)
    monkeypatch.setattr(paid_access, 'datetime', Clock)
    with pytest.raises(ValueError, match='expired before finalization'): await pay(db, term)
    for name in ('account_invoice_guards', 'outreach_payment_receipts', 'outreach_entitlements'):
        assert await db[name].count_documents({}) == 0
    assert await db.outreach_access_requests.find_one({}) == before
