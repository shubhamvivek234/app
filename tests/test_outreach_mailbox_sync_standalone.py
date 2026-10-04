"""Actual standalone denies sync transport and drained OAuth mutation."""
import asyncio
import os
import shutil
import socket
import subprocess
from unittest.mock import AsyncMock, MagicMock
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from tests.test_outreach_durable_mailbox_sync import sync_db
from tests.test_outreach_mailbox_job_lifecycle import lifecycle

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable standalone is opt-in')]


async def test_standalone_denies_sync_before_key_and_oauth_stop_before_write(sync_db, monkeypatch, tmp_path):
    from outreach.core import mailbox_sync_jobs as jobs, suppression
    from outreach.core.oauth_hold_review import OAuthHoldReview
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]; listener.close()
    storage = tmp_path / 'standalone'; storage.mkdir()
    process = subprocess.Popen([shutil.which('mongod'), '--bind_ip', '127.0.0.1', '--port', str(port),
        '--dbpath', str(storage), '--logpath', str(storage / 'mongo.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', tz_aware=True, serverSelectionTimeoutMS=200)
    db = client['test_unravler_sync_standalone']
    opening = AsyncMock(side_effect=AssertionError('No keys'))
    transport = MagicMock(side_effect=AssertionError('No provider'))
    monkeypatch.setattr(jobs, 'prepare_mailbox_access', opening); monkeypatch.setattr(jobs.sync.httpx, 'AsyncClient', transport)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    try:
        for _ in range(50):
            try: await client.admin.command('ping'); break
            except Exception:
                if process.poll() is not None: raise RuntimeError('Standalone failed to start')
                await asyncio.sleep(.1)
        else: raise RuntimeError('Standalone not ready')
        await db.outreach_mailboxes.insert_one(sync_db.outreach_mailboxes.docs[0])
        # An existing reference cannot fall back to a non-transactional claim.
        await db.outreach_mailbox_sync_jobs.insert_one({'_id': 'sync', 'workspace_id': 'w', 'sender_account_id': 'a',
            'status': 'queued', 'basis': jobs.basis(sync_db.outreach_mailboxes.docs[0]), 'deadline': jobs.now()})
        assert (await jobs.execute_job(db, 'w', 'sync'))['status'] == 'stale'
        opening.assert_not_awaited(); transport.assert_not_called()
        assert not await db.outreach_mailbox_sync_reads.find_one({})
        job = sync_db.outreach_mailbox_connection_jobs.docs[0]; job.update(status='review_required', exchange_state='unknown')
        await db.outreach_mailbox_connection_jobs.insert_one(job)
        service = OAuthHoldReview(db); view = await service.inspect('w', 'job')
        with pytest.raises(suppression.SuppressionUnavailable): await service.stop('w', 'job', 'operator',
            'All OAuth and sender writers drained before local stop.', workers_drained=True, expected_digest=view['review_digest'])
        assert (await db.outreach_mailbox_connection_jobs.find_one({}))['status'] == 'review_required'
        assert (await db.outreach_mailboxes.find_one({})).get('access_token_enc')
    finally:
        try: await client.drop_database(db.name)
        finally:
            client.close(); process.terminate(); await asyncio.to_thread(process.wait, 10)
