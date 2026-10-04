"""Real snapshot/majority OAuth stop and read/cursor fault cases; loopback only."""
import asyncio
from datetime import timedelta
import os
import uuid
from unittest.mock import AsyncMock

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import pytest
import pytest_asyncio

from tests.test_outreach_durable_mailbox_sync import sync_db, http_reads
from tests.test_outreach_mailbox_job_lifecycle import lifecycle
from tests.test_outreach_oauth_hold_review import seed_review
from outreach.core import mailbox_sync_jobs as jobs, suppression

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable replica set is opt-in')]


@pytest_asyncio.fixture
async def sync_mongo(sync_db):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client['test_unravler_sync_' + uuid.uuid4().hex]
    await db.outreach_mailboxes.insert_one(sync_db.outreach_mailboxes.docs[0])
    try: yield db
    finally: await client.drop_database(db.name); client.close()


async def test_actual_received_response_and_cursor_ack_recover_without_http(sync_mongo, monkeypatch):
    db = sync_mongo
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ in {'receipt', 'finish'}: raise TimeoutError('local lost acknowledgement')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'healthy'
    assert (await db.outreach_mailboxes.find_one({}))['history_id'] == '101'
    assert (await db.outreach_mailbox_sync_reads.find_one({}))['status'] == 'received'
    client.get.assert_awaited_once()


async def test_actual_crash_read_is_charged_again_after_lease_recovery(sync_mongo, monkeypatch):
    db = sync_mongo
    client = http_reads(monkeypatch, fail=asyncio.CancelledError())
    job = await jobs.ensure_job(db, 'w', 'a')
    with pytest.raises(asyncio.CancelledError): await jobs.execute_job(db, 'w', job['_id'])
    await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'lease_until': jobs.now() - timedelta(seconds=1)}})
    assert (await jobs.recover_due(db))['recovered'] == 1
    client.get.side_effect = None
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'healthy'
    assert (await db.outreach_mailbox_read_budgets.find_one({}))['used'] == 2
    assert await db.outreach_mailbox_sync_reads.count_documents({'status': 'read_interrupted'}) == 1


async def test_actual_possible_ack_loss_calls_no_http_and_keeps_charge(sync_mongo, monkeypatch):
    db = sync_mongo
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == 'authorize': raise TimeoutError('local lost permit')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'
    client.get.assert_not_awaited()
    assert (await db.outreach_mailbox_read_budgets.find_one({}))['used'] == 1
    assert (await db.outreach_mailbox_sync_reads.find_one({}))['status'] == 'read_interrupted'


async def test_actual_projection_rollback_retains_old_cursor_and_received_read(sync_mongo, monkeypatch):
    from outreach.core.suppression import SuppressionCollection
    from outreach.core import mailbox_sync as sync
    db = sync_mongo
    http_reads(monkeypatch)
    message = {'id': 'inbound', 'from': 'lead@example.com', 'received_at': jobs.now()}
    monkeypatch.setattr(sync, '_gmail_messages', AsyncMock(return_value=([message], '101')))
    async def mark(current, mailbox, message):
        await current.outreach_email_suppressions.insert_one({'workspace_id': 'w', '_id': 'stop'})
        return {'status': 'reply'}
    monkeypatch.setattr(sync, '_mark_inbound', mark)
    update = SuppressionCollection.update_one
    async def fail(self, query, changes, **kw):
        if self.collection.name == 'outreach_mailbox_sync_jobs' and changes.get('$inc', {}).get('projected'):
            raise RuntimeError('local projection interruption')
        return await update(self, query, changes, **kw)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail)
    job = await jobs.ensure_job(db, 'w', 'a')
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'
    assert not await db.outreach_email_suppressions.find_one({})
    assert (await db.outreach_mailboxes.find_one({}))['history_id'] == '100'
    assert (await db.outreach_mailbox_sync_jobs.find_one({}))['projected'] == 0


async def test_actual_concurrent_duplicate_workers_read_once(sync_mongo, monkeypatch):
    db = sync_mongo
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    results = await asyncio.gather(*(jobs.execute_job(db, 'w', job['_id']) for _ in range(2)))
    assert {r['status'] for r in results} == {'healthy', 'already_claimed'}
    client.get.assert_awaited_once()


async def test_actual_strict_unique_active_and_received_indexes(sync_mongo):
    from db.indexes import ensure_mailbox_sync_indexes
    db = sync_mongo
    await ensure_mailbox_sync_indexes(db)
    job = await jobs.ensure_job(db, 'w', 'a')
    with pytest.raises(DuplicateKeyError): await db.outreach_mailbox_sync_jobs.insert_one({**job, '_id': 'replacement'})
    read = {'_id': 'one', 'workspace_id': 'w', 'job_id': job['_id'], 'request_index': 0, 'status': 'received'}
    await db.outreach_mailbox_sync_reads.insert_one(read)
    with pytest.raises(DuplicateKeyError): await db.outreach_mailbox_sync_reads.insert_one({**read, '_id': 'two'})
    assert not any('expireAfterSeconds' in r for r in (await db.outreach_mailbox_sync_reads.index_information()).values())


async def test_actual_oauth_review_receipt_ack_is_atomic_and_retry_preserves_replacement(sync_mongo, lifecycle, monkeypatch):
    from outreach.core.oauth_hold_review import OAuthHoldReview
    db = sync_mongo
    lifecycle.outreach_mailboxes.docs.clear(); seed_review(lifecycle)
    await db.outreach_mailboxes.delete_many({})
    for name in ('outreach_accounts', 'outreach_mailboxes', 'outreach_mailbox_connection_jobs', 'outreach_campaigns'):
        for row in getattr(lifecycle, name).docs: await getattr(db, name).insert_one(row)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    service = OAuthHoldReview(db); view = await service.inspect('w', 'job')
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == 'apply': raise TimeoutError('local lost review ack')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    with pytest.raises(TimeoutError): await service.stop('w', 'job', 'operator', 'All OAuth writers drained; local authority stopped.',
        expected_digest=view['review_digest'], workers_drained=True)
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))['exchange_state'] == 'unknown'
    assert not (await db.outreach_mailboxes.find_one({})).get('access_token_enc')
    await db.outreach_mailboxes.update_one({}, {'$set': {'access_token_enc': 'replacement', 'connection_job_id': 'new'}})
    assert (await service.stop('w', 'job', 'operator', 'All OAuth writers drained; local authority stopped.',
        expected_digest=view['review_digest'], workers_drained=True))['status'] == 'review_stopped'
    assert (await db.outreach_mailboxes.find_one({}))['access_token_enc'] == 'replacement'


@pytest.mark.parametrize('boundary', ['possible', 'received'])
async def test_sigkill_loopback_read_recovery_preserves_saved_or_unknown_evidence(sync_mongo, boundary):
    import subprocess
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    db = sync_mongo
    await db.outreach_entitlements.insert_one({'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': jobs.now() + timedelta(days=30)})
    await db.outreach_accounts.insert_one({'workspace_id': 'w', 'id': 'a', 'status': 'active'})
    await db.outreach_sender_slots.insert_one({'workspace_id': 'w', 'sender_id': 'a'})
    reached = threading.Event(); release = threading.Event(); calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            calls.append(self.path); reached.set()
            if boundary == 'possible' and len(calls) == 1: release.wait(15)
            try:
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(b'{"historyId":"101"}')
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    job = await jobs.ensure_job(db, 'w', 'a')
    environment = {**os.environ, 'OUTREACH_DRILL_DB': db.name, 'OUTREACH_DRILL_JOB': job['_id'],
        'OUTREACH_DRILL_SYNC_URL': f'http://127.0.0.1:{server.server_port}/history',
        'OUTREACH_DRILL_SYNC_PAUSE': boundary, 'OUTREACH_CREDENTIAL_CUSTODY_MODE': 'legacy_fernet',
        'OUTREACH_MAILBOX_CONNECTION_ENABLED': 'true', 'OUTREACH_EMAIL_SYNC_ENABLED': 'true',
        'OUTREACH_MAILBOX_PILOT_WORKSPACES': 'w'}
    command = [sys.executable, '-m', 'tests.outreach_mailbox_sync_harness']
    child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert await asyncio.to_thread(reached.wait, 15), 'Loopback request was not reached'
        if boundary == 'received':
            for _ in range(100):
                if await db.outreach_mailbox_sync_reads.find_one({'status': 'received'}): break
                await asyncio.sleep(.05)
            else: raise AssertionError('Receipt not saved')
        child.kill(); await asyncio.to_thread(child.wait, 5)
        await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'lease_until': jobs.now() - timedelta(seconds=1)}})
        assert (await jobs.recover_due(db))['recovered'] == 1
        release.set()
        environment['OUTREACH_DRILL_SYNC_PAUSE'] = ''
        duplicate = await asyncio.to_thread(subprocess.run, command, cwd=Path(__file__).resolve().parents[1], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        assert duplicate.returncode == 0, duplicate.stderr.decode()
        assert duplicate.stdout.strip() == b'healthy'
        assert len(calls) == (1 if boundary == 'received' else 2)
        assert (await db.outreach_mailbox_read_budgets.find_one({}))['used'] == len(calls)
        assert await db.outreach_mailbox_sync_reads.count_documents({'status': 'read_interrupted'}) == (boundary == 'possible')
        assert (await db.outreach_mailboxes.find_one({}))['history_id'] == '101'
    finally:
        if child.poll() is None: child.kill(); await asyncio.to_thread(child.wait, 5)
        child.communicate(); release.set()
        await asyncio.to_thread(server.shutdown); server.server_close(); thread.join(timeout=2)


async def test_actual_erasure_scrubs_cached_content_and_keeps_only_read_metadata(sync_mongo, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    db = sync_mongo; http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    monkeypatch.setattr(jobs, 'finish_job', AsyncMock(side_effect=RuntimeError('local pending projection')))
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'
    assert (await db.outreach_mailbox_sync_reads.find_one({})).get('response_enc')
    service = OutreachErasure(db)
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'owner-hash'})
    await service.request('w', 'owner-hash')
    assert not (await db.outreach_mailbox_sync_reads.find_one({})).get('response_enc')
    row = await db.outreach_mailbox_sync_reads.find_one({})
    async def archive(current): await service._archive(current, 'outreach_mailbox_sync_reads', 'w', row)
    from outreach.core.erasure import _control
    await _control(db, 'w', archive)
    hold = await db.outreach_erasure_holds.find_one({})
    assert hold['mutation'] is False and hold['operation_kind'] == 'mailbox_read'
    assert not any(name in hold for name in ('response_enc', 'owner', 'recipient', 'token', 'sender_account_id'))
    await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'status': 'queued'}})
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'


@pytest.mark.parametrize('scheduler', ['publish', 'recover'])
async def test_closed_workspace_due_prefix_backoff_cannot_starve_open_jobs(sync_mongo, monkeypatch, scheduler):
    from outreach.core.erasure import _control
    db = sync_mongo; job = await jobs.ensure_job(db, 'w', 'a')
    for i in range(50):
        row = {**job, '_id': 'closed-' + str(i), 'workspace_id': 'closed-' + str(i),
            'next_publish_at': jobs.now() - timedelta(minutes=1), 'next_recovery_at': jobs.now() - timedelta(minutes=1)}
        if scheduler == 'recover': row.update(status='running', owner='old', lease_until=jobs.now() - timedelta(seconds=1))
        await db.outreach_mailbox_sync_jobs.insert_one(row)
        async def close(current):
            await current.outreach_suppression_guards.update_one(suppression.guard_scope(row['workspace_id']), {'$set': {'erasure_state': 'stopped'}})
        await _control(db, row['workspace_id'], close)
    if scheduler == 'recover':
        await db.outreach_mailbox_sync_jobs.update_one({'_id': job['_id']}, {'$set': {'status': 'running', 'owner': 'old',
            'lease_until': jobs.now() - timedelta(seconds=1), 'next_recovery_at': jobs.now()}})
        assert (await jobs.recover_due(db))['recovered'] == 0
        assert (await jobs.recover_due(db))['recovered'] == 1
    else:
        sent = []
        await jobs.publish_due(db, lambda *args: sent.append(args))
        assert sent == []
        await jobs.publish_due(db, lambda *args: sent.append(args))
        assert sent == [(job['_id'], 'w')]


async def test_scheduled_selection_backoff_orders_closed_tenants_without_stale_write(sync_mongo):
    from celery_workers.tasks.mailbox import _sync_replies
    from outreach.core.erasure import _control
    db = sync_mongo
    original = await db.outreach_mailboxes.find_one({})
    for i in range(50):
        workspace = 'closed-' + str(i)
        await db.outreach_mailboxes.insert_one({**original, '_id': workspace, 'workspace_id': workspace,
            'next_sync_at': jobs.now() - timedelta(minutes=1)})
        async def close(current):
            await current.outreach_suppression_guards.update_one(suppression.guard_scope(workspace), {'$set': {'erasure_state': 'stopped'}})
        await _control(db, workspace, close)
    await db.outreach_mailboxes.update_one({'workspace_id': 'w'}, {'$set': {'next_sync_at': jobs.now()}})
    assert (await _sync_replies(db))['queued'] == 0
    assert (await _sync_replies(db))['queued'] == 1
    assert await db.outreach_mailbox_sync_jobs.count_documents({}) == 1
    assert (await db.outreach_mailboxes.find_one({'workspace_id': 'w'}))['sync_status'] == 'healthy'


@pytest.mark.parametrize('change', ['owner', 'mailbox', 'lease'])
async def test_old_projection_and_failure_cleanup_cannot_touch_replacement(sync_mongo, monkeypatch, change):
    db = sync_mongo; client = http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    async def changed(*args, **kw):
        if change == 'mailbox':
            await db.outreach_mailboxes.update_one({}, {'$set': {'connection_job_id': 'replacement'}})
        elif change == 'owner':
            await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'owner': 'replacement'}})
        else:
            await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'lease_until': jobs.now() - timedelta(seconds=1)}})
        import httpx
        return httpx.Response(200, json={'historyId': '101'})
    client.get.side_effect = changed
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'
    assert (await db.outreach_mailboxes.find_one({}))['history_id'] == '100'
    if change in {'owner', 'mailbox'}:
        assert (await db.outreach_mailboxes.find_one({}))['sync_status'] == 'healthy'


async def test_oauth_review_failure_rolls_back_all_authority_and_does_not_close_slot(sync_mongo, lifecycle, monkeypatch):
    from outreach.core.oauth_hold_review import OAuthHoldReview
    from outreach.core.suppression import SuppressionCollection
    db = sync_mongo; lifecycle.outreach_mailboxes.docs.clear(); seed_review(lifecycle)
    await db.outreach_mailboxes.delete_many({})
    for name in ('outreach_accounts', 'outreach_mailboxes', 'outreach_mailbox_connection_jobs', 'outreach_campaigns'):
        for row in getattr(lifecycle, name).docs: await getattr(db, name).insert_one(row)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    service = OAuthHoldReview(db); view = await service.inspect('w', 'job')
    update = SuppressionCollection.update_one
    async def fail(self, query, changes, **kw):
        if changes.get('$set', {}).get('status') == 'review_stopped': raise RuntimeError('local review save failure')
        return await update(self, query, changes, **kw)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail)
    with pytest.raises(RuntimeError): await service.stop('w', 'job', 'operator', 'All OAuth and sender writers drained for local stop.',
        expected_digest=view['review_digest'], workers_drained=True)
    assert (await db.outreach_accounts.find_one({}))['status'] == 'active'
    assert (await db.outreach_mailboxes.find_one({}))['access_token_enc'] == 'private-access'
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))['status'] == 'review_required'
    assert not await db.outreach_sender_execution.find_one({})


async def test_terminal_cache_cleanup_is_due_fenced_and_keeps_received_metadata(sync_mongo, monkeypatch):
    db = sync_mongo; http_reads(monkeypatch)
    job = await jobs.ensure_job(db, 'w', 'a')
    monkeypatch.setattr(jobs, 'finish_job', AsyncMock(side_effect=RuntimeError('local down')))
    assert (await jobs.execute_job(db, 'w', job['_id']))['status'] == 'stale'
    assert (await db.outreach_mailbox_sync_reads.find_one({})).get('response_enc')
    await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'status': 'failed'}})
    assert (await jobs.cleanup_due(db))['cleaned'] == 0
    await db.outreach_mailbox_sync_jobs.update_one({}, {'$set': {'deadline': jobs.now() - timedelta(seconds=1),
        'next_cleanup_at': jobs.now() - timedelta(seconds=1)}})
    assert (await jobs.cleanup_due(db))['cleaned'] == 1
    row = await db.outreach_mailbox_sync_reads.find_one({})
    assert row['status'] == 'received' and row['response_digest'] and not row.get('response_enc')
    assert (await jobs.cleanup_due(db))['cleaned'] == 0
