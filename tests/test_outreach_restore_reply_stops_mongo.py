"""Real transactional sender/negative fences, no history, and safe retention."""
import asyncio
from datetime import datetime
import json
import os
import shutil
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock
import httpx
import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, OperationFailure
from outreach.core import restore_reply_stops as rs, suppression, erasure, restore_epoch as epoch
from outreach.tasks.sequence_executor import _recipient_has_reply
from outreach.core.request_guard import RequestDenied
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_restore_reply_stops import source, apply, SENDER, RECIPIENT, URL
from tests.test_outreach_dispatch_authority import ready_db, dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def prepare_sender(db):
    await db.outreach_accounts.insert_one({'_id': 'sender-row', 'workspace_id': 'w', 'id': 'sender',
                                         'linkedin_urn': SENDER, 'credential_generation': 1})
    await prepare(db)


async def test_actual_original_source_to_backup_reaches_only_sender_negative_gate(real_restore):
    db = real_restore; await prepare_sender(db)
    original = db.client['test_reply_source_' + uuid.uuid4().hex]
    try:
        await original.outreach_accounts.insert_one({'workspace_id': 'w', 'id': 'sender', 'linkedin_urn': SENDER})
        oid = ObjectId(); date = datetime(2026, 1, 2, 3, 4, 5, 123000)
        await original.outreach_inbox_threads.insert_one({'_id': oid, 'workspace_id': 'w', 'account_id': 'sender',
            'lead_urn': RECIPIENT, 'lead_profile_url': URL, 'has_lead_reply': True,
            'messages': [{'sender_type': 'lead', 'timestamp': date, 'body': 'private-reply'}]})
        doc = await rs.export_manifest(original, 'w', [str(oid)], workers_drained=True)
        raw = json.dumps(doc).encode(); before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
        assert not await _recipient_has_reply(db, 'w', 'sender', {'linkedin_urn': RECIPIENT})
        assert (await apply(db, raw))['applied']
        for candidate in ({'linkedin_urn': RECIPIENT}, {'identifiers': {'normalized_url': URL.replace('www.', '')}}):
            assert await _recipient_has_reply(db, 'w', 'sender', candidate)
            assert not await _recipient_has_reply(db, 'w', 'other', candidate)
            assert not await _recipient_has_reply(db, 'other', 'sender', candidate)
        assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
        assert (await db.outreach_reply_stops.find_one({}))['created_at'] == date
        for name in ('outreach_inbox_threads', 'outreach_leads', 'outreach_event_outbox'):
            assert await db[name].count_documents({}) == 0
        with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
        # Two different _id types with the same printable reference are ambiguous.
        await original.outreach_inbox_threads.insert_one({'_id': str(oid), 'workspace_id': 'w'})
        with pytest.raises(ValueError): await rs.export_manifest(original, 'w', [str(oid)], workers_drained=True)
    finally:
        await db.client.drop_database(original.name)


async def test_concurrent_install_and_actual_commit_then_raise_simulated_ack_loss(real_restore, monkeypatch):
    db = real_restore; await prepare_sender(db); view = await rs.RestoreReplyStops(db).inspect('w', source())
    original = suppression.mutate_suppression; raised = False
    async def lose_ack(*args, **kwargs):
        nonlocal raised
        result = await original(*args, **kwargs)
        if not raised and not result['recovered']:
            raised = True; raise RuntimeError('Simulated acknowledgement loss after actual commit')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lose_ack)
    outcomes = await asyncio.gather(apply(db, view=view), apply(db, view=view), return_exceptions=True)
    assert sum(isinstance(x, RuntimeError) for x in outcomes) == 1
    assert sum(isinstance(x, dict) and x['recovered'] for x in outcomes) == 1
    await db.outreach_accounts.update_one({'workspace_id': 'w', 'id': 'sender'}, {'$set': {'credential_generation': 2}})
    await db.outreach_reply_stops.update_many({'workspace_id': 'w'}, {'$set': {'later_metadata': True}})
    before = await db.outreach_reply_stops.find({}).to_list(length=10)
    assert (await apply(db, view=view))['recovered']
    assert epoch.stable(await db.outreach_reply_stops.find({}).to_list(length=10)) == epoch.stable(before)
    assert await db.outreach_restore_reply_stops.count_documents({}) == 1


@pytest.mark.parametrize('fault', ['journal', 'epoch', 'flag'])
async def test_late_failure_rolls_back_stops_journal_and_sender_fence(real_restore, monkeypatch, fault):
    db = real_restore; await prepare_sender(db)
    sender = await db.outreach_accounts.find_one({}); guard = await db.outreach_suppression_guards.find_one({})
    original = suppression.SuppressionCollection.insert_one
    async def late(self, *args, **kwargs):
        if self.collection.name != 'outreach_restore_reply_stops': return await original(self, *args, **kwargs)
        if fault == 'journal': raise RuntimeError('Journal interruption')
        result = await original(self, *args, **kwargs)
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH' if fault == 'epoch' else 'OUTREACH_HEALTH_MONITOR_ENABLED',
                           'f' * 64 if fault == 'epoch' else 'true')
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, 'insert_one', late)
    with pytest.raises((RuntimeError, ValueError)): await apply(db)
    for name in ('outreach_reply_stops', 'outreach_restore_reply_stops'): assert await db[name].count_documents({}) == 0
    assert await db.outreach_accounts.find_one({}) == sender
    assert await db.outreach_suppression_guards.find_one({}) == guard


@pytest.mark.parametrize('fault', ['sender_replaced', 'missing_saved', 'closed_saved', 'epoch_missing', 'collision'])
async def test_retries_never_hide_removed_or_changed_authorities(real_restore, fault):
    db = real_restore; await prepare_sender(db); view = await rs.RestoreReplyStops(db).inspect('w', source())
    if fault in {'sender_replaced', 'missing_saved', 'closed_saved'}: await apply(db, view=view)
    if fault == 'sender_replaced':
        await db.outreach_accounts.update_one({'workspace_id': 'w'}, {'$set': {'linkedin_urn': 'urn:li:member:Other'}})
    if fault == 'missing_saved': await db.outreach_reply_stops.delete_many({})
    if fault == 'closed_saved':
        await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'erased'}})
    if fault == 'epoch_missing': await db.outreach_execution_epochs.delete_one(epoch.root_scope('w'))
    if fault == 'collision':
        await db.outreach_reply_stops.insert_one({**rs.scope('w', rs.parse(source()).facts[0]), 'value': 'other',
            'created_at': epoch.now()})
    with pytest.raises((ValueError, suppression.SuppressionUnavailable)): await apply(db, view=view)
    if fault == 'sender_replaced': assert await _recipient_has_reply(db, 'w', 'sender', {'linkedin_urn': RECIPIENT})


async def test_ttl_free_strict_identity_and_source_indexes_and_erasure(real_restore):
    from db.indexes import remove_other_evidence_ttls, ensure_integration_indexes
    db = real_restore; await prepare_sender(db)
    for name in ('outreach_reply_stops', 'outreach_restore_reply_stops'):
        await db[name].create_index('unsafe_expiry', expireAfterSeconds=9999)
    await remove_other_evidence_ttls(db); await ensure_integration_indexes(db); await apply(db)
    for name in ('outreach_reply_stops', 'outreach_restore_reply_stops'):
        assert all('expireAfterSeconds' not in d for d in (await db[name].index_information()).values())
        row = await db[name].find_one({})
        with pytest.raises(DuplicateKeyError): await db[name].insert_one({**row, '_id': 'duplicate'})
    service = erasure.OutreachErasure(db); await service.request('w', 'actor'); inspected = await service.inspect('w')
    result = await service.finish('w', 'operator', 'All tenant writers and caches are drained for erasure.',
        workers_drained=True, expected_digest=inspected['review_digest'])
    assert result['status'] == 'erased'
    for name in ('outreach_reply_stops', 'outreach_restore_reply_stops'):
        assert await db[name].count_documents({'workspace_id': 'w'}) == 0
    holds = await db.outreach_erasure_holds.find({'workspace_id': 'w'}).to_list(length=100)
    assert any(row['kind'] == 'restore_reply_stop_provenance' for row in holds)
    assert RECIPIENT not in json.dumps(holds, default=str) and URL not in json.dumps(holds, default=str)
    with pytest.raises(ValueError): await rs.RestoreReplyStops(db).inspect('w', source())


async def test_duplicate_semantic_stops_deny_index_cutover(real_restore):
    from db.indexes import ensure_integration_indexes
    for _ in range(2):
        await real_restore.outreach_reply_stops.insert_one({'workspace_id': 'w', 'sender_id': 'sender',
                                                          'field': 'member_urn', 'value': RECIPIENT})
    with pytest.raises(OperationFailure): await ensure_integration_indexes(real_restore)


async def test_sender_replacement_after_snapshot_conflicts_and_cannot_install(real_restore, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db = real_restore; await prepare_sender(db); view = await rs.RestoreReplyStops(db).inspect('w', source())
    seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.fence; once = False
    async def pause(self, document, query):
        nonlocal once
        if self.name == 'outreach_accounts' and not once:
            once = True; seen.set(); await release.wait()
        return await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    task = asyncio.create_task(apply(db, view=view))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await db.outreach_accounts.update_one({'workspace_id': 'w', 'id': 'sender'}, {'$set': {'linkedin_urn': 'urn:li:member:Other'}})
        release.set()
        with pytest.raises(ValueError): await asyncio.wait_for(task, 5)
        assert await db.outreach_reply_stops.count_documents({}) == 0
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_negative_lookup_blocks_actual_dispatch_factory(ready_db):
    db, job = ready_db
    await db.outreach_reply_stops.insert_one({'workspace_id': 'w', 'sender_id': 'a',
        'field': 'normalized_url', 'value': 'https://www.linkedin.com/in/person'})
    async def check(current):
        lead = await current.outreach_leads.find_one({'workspace_id': 'w', 'id': 'l'})
        return 'lead_suppressed' if await _recipient_has_reply(current, 'w', 'a', lead) else None
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RequestDenied, match='lead_suppressed'): await dispatch(db, job, factory, extra_validation=check)
    factory.assert_not_awaited()


async def test_negative_insert_before_guard_fence_conflicts_and_blocks_dispatch(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityDatabase
    db, job = ready_db; seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityDatabase.fence_suppression
    once = False
    async def pause(self, workspace):
        nonlocal once
        if not once:
            once = True
            await self.database.outreach_accounts.find_one({'workspace_id': workspace, 'id': 'a'}, session=self.session)
            seen.set(); await release.wait()
        return await original(self, workspace)
    monkeypatch.setattr(AuthorityDatabase, 'fence_suppression', pause)
    async def check(current):
        lead = await current.outreach_leads.find_one({'workspace_id': 'w', 'id': 'l'})
        return 'lead_suppressed' if await _recipient_has_reply(current, 'w', 'a', lead) else None
    async def write(current):
        await current.outreach_reply_stops.insert_one({'workspace_id': 'w', 'sender_id': 'a',
            'field': 'normalized_url', 'value': 'https://www.linkedin.com/in/person'})
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    task = asyncio.create_task(dispatch(db, job, factory, extra_validation=check))
    try:
        await asyncio.wait_for(seen.wait(), 5); await suppression.mutate_suppression(db, 'w', write); release.set()
        with pytest.raises(RequestDenied, match='lead_suppressed'): await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
    finally:
        release.set()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_standalone_has_no_block_install_fallback(real_restore, tmp_path):
    from motor.motor_asyncio import AsyncIOMotorClient
    await prepare_sender(real_restore)
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
            for name in ('outreach_execution_epochs', 'outreach_suppression_guards', 'outreach_accounts'):
                rows = await real_restore[name].find({}).to_list(length=10)
                if rows: await db[name].insert_many(rows)
            with pytest.raises(suppression.SuppressionUnavailable): await apply(db)
            for name in ('outreach_restore_reply_stops', 'outreach_reply_stops'):
                assert await db[name].count_documents({}) == 0
        finally:
            try: await client.drop_database(db.name)
            finally:
                client.close(); process.terminate(); process.wait(timeout=10); shutil.rmtree(storage)


async def test_erasure_waits_for_import_guard_then_closes_receipt_retry(real_restore, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db = real_restore; await prepare_sender(db); view = await rs.RestoreReplyStops(db).inspect('w', source())
    seen, release = asyncio.Event(), asyncio.Event(); original = AuthorityCollection.find_one
    async def pause(self, query, *args, **kwargs):
        row = await original(self, query, *args, **kwargs)
        if self.database.request_id == 'restore_reply_stop_import' and self.name == 'outreach_execution_epochs' and query.get('kind') == 'root':
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
