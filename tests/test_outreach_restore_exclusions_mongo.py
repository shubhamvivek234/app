"""Actual cross-collection deletion-denial recovery, ordering and rollback."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import shutil
import socket
import subprocess
import uuid
import pytest
from outreach.core import restore_exclusions as ex, erasure, suppression, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_restore_exclusions import source, apply, IDENTITY

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def test_external_selected_source_reinstates_denials_in_older_database(real_restore):
    db = real_restore; await prepare(db)
    uid = 'synthetic-deleted-uid'; identity = canonical_hash(['firebase_identity', uid])
    original = db.client['test_restore_exclusion_source_' + uuid.uuid4().hex]
    try:
        date = datetime(2026, 1, 2, 3, 4, 5, 123000, tzinfo=timezone.utc)
        await original.outreach_suppression_guards.insert_one({**suppression.guard_scope('w'),
            'erasure_state': 'erased', 'erasure_requested_at': date, 'erasure_completed_at': date})
        await original.account_erasure_tombstones.insert_one({'_id': identity, 'requested_at': date})
        raw = json.dumps(await ex.export_manifest(original, 'w', [identity])).encode()
        assert not await erasure.identity_is_erased(db, uid)
        assert await erasure.workspace_is_open(db, 'w')
        before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
        result = await apply(db, raw)
        assert result['applied'] and not result['purged'] and not result['activation_allowed']
        assert await erasure.identity_is_erased(db, uid)
        assert not await erasure.workspace_is_open(db, 'w')
        guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))
        assert guard['erasure_state'] == 'restore_excluded' and 'erasure_completed_at' not in guard
        row = await db.account_erasure_tombstones.find_one({'_id': identity})
        assert row['requested_at'] == date.replace(tzinfo=None)
        assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
        assert await db.outreach_accounts.count_documents({'workspace_id': 'w'}) == 0
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
    finally:
        await db.client.drop_database(original.name)


async def test_concurrent_import_and_saved_retry_preserve_original_records(real_restore):
    db = real_restore; await prepare(db)
    view = await ex.RestoreExclusions(db).inspect('w', source())
    results = await asyncio.gather(apply(db, view=view), apply(db, view=view))
    assert sum(r['recovered'] for r in results) == 1
    assert await db.outreach_restore_exclusions.count_documents({}) == 1
    assert await db.account_erasure_tombstones.count_documents({}) == 1
    await db.account_erasure_tombstones.update_one({'_id': IDENTITY}, {'$set': {'later_evidence': True}})
    before = await db.account_erasure_tombstones.find_one({'_id': IDENTITY})
    assert (await apply(db, view=view))['recovered']
    assert await db.account_erasure_tombstones.find_one({'_id': IDENTITY}) == before


async def test_committed_import_with_lost_ack_recovers_without_reinstallation(real_restore, monkeypatch):
    db = real_restore; await prepare(db)
    view = await ex.RestoreExclusions(db).inspect('w', source())
    original = erasure._control; calls = 0
    async def lose_ack(*args, **kwargs):
        nonlocal calls
        result = await original(*args, **kwargs); calls += 1
        if calls == 1: raise RuntimeError('Synthetic lost commit acknowledgement')
        return result
    monkeypatch.setattr(erasure, '_control', lose_ack)
    with pytest.raises(RuntimeError): await apply(db, view=view)
    await db.account_erasure_tombstones.update_one({'_id': IDENTITY}, {'$set': {'replacement_metadata': True}})
    before = await db.account_erasure_tombstones.find_one({'_id': IDENTITY})
    journal = await db.outreach_restore_exclusions.find_one({})
    assert (await apply(db, view=view))['recovered']
    assert await db.account_erasure_tombstones.find_one({'_id': IDENTITY}) == before
    after = await db.outreach_restore_exclusions.find_one({})
    assert epoch.stable(after) == epoch.stable(journal)
    assert await db.outreach_restore_exclusions.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['journal', 'epoch_after_write', 'flag_after_write'])
async def test_failure_rolls_back_global_identity_guard_and_journal(real_restore, monkeypatch, fault):
    db = real_restore; await prepare(db)
    guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))
    original = suppression.SuppressionCollection.insert_one
    async def fail(self, *args, **kwargs):
        if self.collection.name != 'outreach_restore_exclusions':
            return await original(self, *args, **kwargs)
        if fault == 'journal': raise RuntimeError('Synthetic journal interruption')
        result = await original(self, *args, **kwargs)
        if fault == 'epoch_after_write': monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', 'e' * 64)
        else: monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED', 'true')
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'insert_one', fail)
    with pytest.raises((RuntimeError, ValueError)): await apply(db)
    assert not await db.account_erasure_tombstones.find_one({})
    assert not await db.outreach_restore_exclusions.find_one({})
    assert await db.outreach_suppression_guards.find_one(suppression.guard_scope('w')) == guard


async def test_existing_stronger_unknown_closure_and_tombstone_are_preserved(real_restore):
    db = real_restore; await prepare(db)
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {
        'erasure_state': 'legacy_unknown_closed', 'erasure_completed_at': epoch.now()}})
    row = {'_id': IDENTITY, 'requested_at': datetime(2025, 1, 1), 'original_evidence': True}
    await db.account_erasure_tombstones.insert_one(row)
    before = await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))
    await apply(db)
    assert await db.account_erasure_tombstones.find_one({'_id': IDENTITY}) == row
    after = await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))
    assert ex.review_guard(after) == ex.review_guard(before)


@pytest.mark.parametrize('fault', ['root', 'inspection', 'malformed_tombstone'])
async def test_changed_or_unproven_data_does_not_install_exclusions(real_restore, fault):
    db = real_restore; await prepare(db); view = await ex.RestoreExclusions(db).inspect('w', source())
    if fault == 'root': await db.outreach_execution_epochs.delete_many({})
    else: await db.account_erasure_tombstones.insert_one({'_id': IDENTITY,
        'requested_at': 'unproven' if fault == 'malformed_tombstone' else datetime(2025, 1, 1)})
    with pytest.raises(ValueError): await apply(db, view=view)
    assert not await db.outreach_restore_exclusions.find_one({})
    assert not (await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))).get('erasure_state')


@pytest.mark.parametrize('target', ['identity', 'closure'])
async def test_journal_cannot_report_success_when_exclusions_were_removed(real_restore, target):
    db = real_restore; await prepare(db); view = await ex.RestoreExclusions(db).inspect('w', source())
    await apply(db, view=view)
    if target == 'identity': await db.account_erasure_tombstones.delete_many({})
    else: await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$unset': {'erasure_state': ''}})
    with pytest.raises(ValueError): await apply(db, view=view)
    assert await db.outreach_restore_exclusions.count_documents({}) == 1


async def test_ttl_removal_strict_index_and_minimal_erasure_provenance(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db = real_restore; await prepare(db)
    for name in ('outreach_restore_exclusions', 'account_erasure_tombstones', 'outreach_suppression_guards'):
        await db[name].create_index('unsafe_expiry', expireAfterSeconds=9999)
    await remove_other_evidence_ttls(db); await ensure_integration_indexes(db)
    await apply(db)
    for name in ('outreach_restore_exclusions', 'account_erasure_tombstones', 'outreach_suppression_guards'):
        assert all('expireAfterSeconds' not in i for i in (await db[name].index_information()).values())
    row = await db.outreach_restore_exclusions.find_one({})
    with pytest.raises(Exception): await db.outreach_restore_exclusions.insert_one({**row, '_id': 'duplicate'})
    async def archive(current): await erasure.OutreachErasure(db)._archive(current, 'outreach_restore_exclusions', 'w', row)
    await erasure._control(db, 'w', archive)
    held = await db.outreach_erasure_holds.find_one({'kind': 'restore_exclusion_provenance'})
    assert held and not held['purged'] and not held['activation_allowed'] and IDENTITY not in json.dumps(held, default=str)
    assert 'outreach_restore_exclusions' in erasure.DATA_COLLECTIONS


async def test_standalone_denies_before_identity_or_workspace_install(real_restore, tmp_path):
    from motor.motor_asyncio import AsyncIOMotorClient
    await prepare(real_restore)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    storage = tmp_path / 'mongo'; storage.mkdir()
    with (tmp_path / 'mongo.log').open('w') as log:
        process = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(storage), '--bind_ip',
            '127.0.0.1', '--port', str(port)], stdout=log, stderr=log)
        client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=1000)
        db = client['test_exclusion_standalone_' + uuid.uuid4().hex]
        try:
            for attempt in range(20):
                try:
                    await client.admin.command('ping'); break
                except Exception:
                    if attempt == 19: raise
                    await asyncio.sleep(.2)
            for name in ('outreach_execution_epochs', 'outreach_suppression_guards'):
                rows = await real_restore[name].find({}).to_list(length=10)
                if rows: await db[name].insert_many(rows)
            with pytest.raises(suppression.SuppressionUnavailable): await apply(db)
            assert not await db.account_erasure_tombstones.find_one({})
            assert not await db.outreach_restore_exclusions.find_one({})
            assert not (await db.outreach_suppression_guards.find_one(suppression.guard_scope('w'))).get('erasure_state')
        finally:
            try:
                await client.drop_database(db.name)
            finally:
                client.close(); process.terminate(); process.wait(timeout=10); shutil.rmtree(storage)


async def test_root_rotation_waits_for_old_import_then_preserves_stopped_epoch(real_restore, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db = real_restore; await prepare(db)
    view = await ex.RestoreExclusions(db).inspect('w', source())
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityCollection.find_one
    async def pause(self, query, *args, **kwargs):
        row = await original(self, query, *args, **kwargs)
        if (self.database.request_id == 'restore_exclusion_import'
                and self.name == 'outreach_execution_epochs' and query.get('kind') == 'root'):
            seen.set(); await release.wait()
        return row
    monkeypatch.setattr(AuthorityCollection, 'find_one', pause)
    task = asyncio.create_task(apply(db, view=view))
    rotation = None
    try:
        await asyncio.wait_for(seen.wait(), 5)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', 'f' * 64)
        rotation = asyncio.create_task(prepare(db))
        await asyncio.sleep(.15)
        assert not rotation.done()
        release.set()
        with pytest.raises(epoch.EpochUnavailable): await asyncio.wait_for(task, 5)
        assert (await asyncio.wait_for(rotation, 5))['prepared']
        assert not await db.account_erasure_tombstones.find_one({})
        assert not await db.outreach_restore_exclusions.find_one({})
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
    finally:
        release.set()
        for item in (task, rotation):
            if item and not item.done(): item.cancel()
        await asyncio.gather(*(item for item in (task, rotation) if item), return_exceptions=True)
