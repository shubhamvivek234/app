"""Actual recipient-block restore transactions, closure, rollback and retention."""
import asyncio
from datetime import datetime
import json
import os
import shutil
import socket
import subprocess
import uuid
import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, OperationFailure
from outreach.core import restore_suppressions as rs, suppression, erasure, restore_epoch as epoch
from outreach.core.email_finder import is_lead_email_available
from outreach.core.lead_importer import check_compound_suppression
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_restore_suppressions import source, apply, EMAIL

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def test_actual_source_to_older_backup_restores_only_selected_blocks(real_restore):
    db = real_restore; await prepare(db)
    original = db.client['test_suppression_source_' + uuid.uuid4().hex]
    try:
        date = datetime(2026, 1, 2, 3, 4, 5, 123000)
        oid = ObjectId()
        await original.outreach_email_suppressions.insert_one({'_id': oid, 'workspace_id': 'w', 'email': EMAIL,
            'reason': 'reply', 'created_at': date})
        await original.outreach_do_not_contact.insert_one({'_id': 'original-dnc', 'workspace_id': 'w',
            'created_at': date, 'vanity_name': 'current', 'identifiers': {'vanity_name': 'old'},
            'email': 'alias@example.com', 'reason': 'private-original-reason'})
        doc = await rs.export_manifest(original, 'w', ['original-dnc'], [str(oid)], workers_drained=True)
        raw = json.dumps(doc).encode()
        before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
        assert await is_lead_email_available(db, 'w', {'email': EMAIL})
        result = await apply(db, raw)
        assert result['applied'] and not result['activation_allowed'] and not result['reply_history_restored']
        assert not await is_lead_email_available(db, 'w', {'email': EMAIL})
        for alias in ('current', 'old'):
            assert await check_compound_suppression('w', [{'linkedin_url': f'https://www.linkedin.com/in/{alias}'}], db)
        assert not await check_compound_suppression('other', [{'vanity_name': 'old'}], db)
        row = await db.outreach_email_suppressions.find_one({'workspace_id': 'w'})
        assert row['created_at'] == date and row['reason'] != 'reply'
        assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
        for name in ('outreach_inbox_threads', 'outreach_leads', 'outreach_event_outbox'):
            assert await db[name].count_documents({}) == 0
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
        with pytest.raises(ValueError): await rs.export_manifest(db, 'w', [], [str(row['_id'])], workers_drained=True)
    finally:
        await db.client.drop_database(original.name)


async def test_ambiguous_native_and_string_source_id_deny(real_restore):
    db = real_restore; oid = ObjectId()
    for ident in (oid, str(oid)):
        await db.outreach_email_suppressions.insert_one({'_id': ident, 'workspace_id': 'w', 'email': EMAIL,
            'created_at': epoch.now()})
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', [], [str(oid)], workers_drained=True)


async def test_concurrent_import_and_commit_then_raise_recover_preserving_metadata(real_restore, monkeypatch):
    db = real_restore; await prepare(db)
    view = await rs.RestoreSuppressions(db).inspect('w', source())
    original = suppression.mutate_suppression; raised = False
    async def lose_ack(*args, **kwargs):
        nonlocal raised
        result = await original(*args, **kwargs)
        if not raised and not result['recovered']:
            raised = True; raise RuntimeError('Simulated acknowledgement loss after actual commit')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lose_ack)
    outcomes = await asyncio.gather(apply(db, view=view), apply(db, view=view), return_exceptions=True)
    assert sum(isinstance(item, RuntimeError) for item in outcomes) == 1
    assert sum(isinstance(item, dict) and item['recovered'] for item in outcomes) == 1
    assert await db.outreach_restore_suppressions.count_documents({}) == 1
    await db.outreach_email_suppressions.update_one({'workspace_id': 'w'}, {'$set': {'later': True}})
    before = await db.outreach_email_suppressions.find_one({'workspace_id': 'w'})
    assert (await apply(db, view=view))['recovered']
    assert epoch.stable(await db.outreach_email_suppressions.find_one({'workspace_id': 'w'})) == epoch.stable(before)
    assert await db.outreach_do_not_contact.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['journal', 'epoch', 'flag'])
async def test_final_write_failure_rolls_back_all_blocks(real_restore, monkeypatch, fault):
    db = real_restore; await prepare(db)
    before = await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))
    original = suppression.SuppressionCollection.insert_one
    async def late(self, *args, **kwargs):
        if self.collection.name != 'outreach_restore_suppressions': return await original(self, *args, **kwargs)
        if fault == 'journal': raise RuntimeError('Journal interruption')
        result = await original(self, *args, **kwargs)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH' if fault == 'epoch' else 'OUTREACH_HEALTH_MONITOR_ENABLED',
                           'f' * 64 if fault == 'epoch' else 'true')
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'insert_one', late)
    with pytest.raises((RuntimeError, ValueError)): await apply(db)
    for name in ('outreach_email_suppressions', 'outreach_do_not_contact', 'outreach_restore_suppressions'):
        assert await db[name].count_documents({}) == 0
    assert await db.outreach_suppression_guards.find_one(suppression.guard_scope('w')) == before


@pytest.mark.parametrize('fault', ['closed', 'closed_retry', 'missing_saved', 'root_missing', 'collision'])
async def test_closed_or_changed_targets_never_install_or_fabricate_success(real_restore, fault):
    db = real_restore; await prepare(db)
    view = await rs.RestoreSuppressions(db).inspect('w', source())
    if fault in {'closed_retry', 'missing_saved'}: await apply(db, view=view)
    if fault.startswith('closed'):
        await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    if fault == 'missing_saved': await db.outreach_email_suppressions.delete_many({})
    if fault == 'root_missing': await db.outreach_execution_epochs.delete_one(epoch.root_scope('w'))
    if fault == 'collision':
        fact = next(f for f in rs.parse(source()).facts if f.kind == 'dnc')
        await db.outreach_do_not_contact.insert_one({**rs.dnc_scope('w', fact), 'created_at': epoch.now(),
            'identifiers': {'vanity_name': 'different'}, 'restore_provenance': 'selected_negative'})
    with pytest.raises((ValueError, suppression.SuppressionUnavailable)): await apply(db, view=view)
    if fault not in {'closed_retry', 'missing_saved'}:
        assert await db.outreach_restore_suppressions.count_documents({}) == 0


async def test_existing_email_and_normal_dnc_rows_remain_intact(real_restore):
    db = real_restore; await prepare(db)
    await db.outreach_email_suppressions.insert_one({'workspace_id': 'w', 'email': EMAIL,
        'created_at': datetime(2025, 1, 1), 'reason': 'original', 'original_metadata': True})
    await db.outreach_do_not_contact.insert_one({'workspace_id': 'w', 'vanity_name': 'recipient',
        'created_at': datetime(2025, 1, 1), 'reason': 'original', 'original_metadata': True})
    before = await db.outreach_email_suppressions.find_one({}); dnc = await db.outreach_do_not_contact.find_one({})
    await apply(db)
    after = await db.outreach_email_suppressions.find_one({})
    assert epoch.stable(after) == epoch.stable(before)
    assert await db.outreach_do_not_contact.find_one({'_id': dnc['_id']}) == dnc


async def test_ttl_removal_strict_indexes_and_erasure_hashes(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db = real_restore; await prepare(db)
    names = ('outreach_restore_suppressions', 'outreach_do_not_contact', 'outreach_email_suppressions')
    for name in names: await db[name].create_index('unsafe_expiry', expireAfterSeconds=9999)
    await remove_other_evidence_ttls(db); await ensure_integration_indexes(db); await apply(db)
    for name in names: assert all('expireAfterSeconds' not in d for d in (await db[name].index_information()).values())
    row = await db.outreach_restore_suppressions.find_one({})
    with pytest.raises(DuplicateKeyError): await db.outreach_restore_suppressions.insert_one({**row, '_id': 'duplicate'})
    with pytest.raises(DuplicateKeyError): await db.outreach_email_suppressions.insert_one({'workspace_id': 'w', 'email': EMAIL})
    async def archive(current): await erasure.OutreachErasure(db)._archive(current, 'outreach_restore_suppressions', 'w', row)
    await erasure._control(db, 'w', archive)
    held = await db.outreach_erasure_holds.find_one({'kind': 'restore_suppression_provenance'})
    assert held and EMAIL not in json.dumps(held, default=str) and 'recipient' not in json.dumps(held, default=str)
    assert not held['activation_allowed'] and not held['reply_history_restored']
    assert 'outreach_restore_suppressions' in erasure.DATA_COLLECTIONS


async def test_duplicate_email_rows_fail_strict_index_cutover(real_restore):
    from db.indexes import ensure_integration_indexes
    for _ in range(2): await real_restore.outreach_email_suppressions.insert_one({'workspace_id': 'w', 'email': EMAIL})
    with pytest.raises(OperationFailure): await ensure_integration_indexes(real_restore)


async def test_erasure_purges_recipient_facts_and_retains_only_hashed_source_review(real_restore):
    db = real_restore; await prepare(db); await apply(db)
    service = erasure.OutreachErasure(db)
    await service.request('w', 'actor')
    inspected = await service.inspect('w')
    result = await service.finish('w', 'operator', 'All tenant writers and caches are drained for erasure.',
        workers_drained=True, expected_digest=inspected['review_digest'])
    assert result['status'] == 'erased'
    for name in ('outreach_restore_suppressions', 'outreach_do_not_contact', 'outreach_email_suppressions'):
        assert await db[name].count_documents({'workspace_id': 'w'}) == 0
    holds = await db.outreach_erasure_holds.find({'workspace_id': 'w'}).to_list(length=100)
    assert any(row['kind'] == 'restore_suppression_provenance' for row in holds)
    assert EMAIL not in json.dumps(holds, default=str) and 'recipient' not in json.dumps(holds, default=str)
    with pytest.raises(ValueError): await rs.RestoreSuppressions(db).inspect('w', source())


async def test_standalone_has_no_block_install_fallback(real_restore, tmp_path):
    from motor.motor_asyncio import AsyncIOMotorClient
    await prepare(real_restore)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    storage = tmp_path / 'mongo'; storage.mkdir()
    with (tmp_path / 'mongo.log').open('w') as log:
        process = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(storage), '--bind_ip',
            '127.0.0.1', '--port', str(port)], stdout=log, stderr=log)
        client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=1000)
        db = client['test_rs_standalone_' + uuid.uuid4().hex]
        try:
            for attempt in range(20):
                try: await client.admin.command('ping'); break
                except Exception:
                    if attempt == 19: raise
                    await asyncio.sleep(.2)
            for name in ('outreach_execution_epochs', 'outreach_suppression_guards'):
                rows = await real_restore[name].find({}).to_list(length=10)
                if rows: await db[name].insert_many(rows)
            with pytest.raises(suppression.SuppressionUnavailable): await apply(db)
            for name in ('outreach_restore_suppressions', 'outreach_do_not_contact', 'outreach_email_suppressions'):
                assert await db[name].count_documents({}) == 0
        finally:
            try: await client.drop_database(db.name)
            finally:
                client.close(); process.terminate(); process.wait(timeout=10); shutil.rmtree(storage)


async def test_erasure_waits_for_import_guard_then_closes_receipt_retry(real_restore, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db = real_restore; await prepare(db); view = await rs.RestoreSuppressions(db).inspect('w', source())
    seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.find_one
    async def pause(self, query, *args, **kwargs):
        row = await original(self, query, *args, **kwargs)
        if self.database.request_id == 'restore_suppression_import' and self.name == 'outreach_execution_epochs' and query.get('kind') == 'root':
            seen.set(); await release.wait()
        return row
    monkeypatch.setattr(AuthorityCollection, 'find_one', pause)
    task = asyncio.create_task(apply(db, view=view)); close = None
    async def stop(current):
        await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'stopped'}})
    try:
        await asyncio.wait_for(seen.wait(), 5)
        close = asyncio.create_task(erasure._control(db, 'w', stop))
        await asyncio.sleep(.15); assert not close.done()
        release.set(); assert (await asyncio.wait_for(task, 5))['applied']; await asyncio.wait_for(close, 5)
        with pytest.raises((ValueError, suppression.SuppressionUnavailable)): await apply(db, view=view)
    finally:
        release.set()
        for item in (task, close):
            if item and not item.done(): item.cancel()
        await asyncio.gather(*(item for item in (task, close) if item), return_exceptions=True)
