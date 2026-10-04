"""Actual standalone Mongo must reject OAuth ownership before secret opening."""
import asyncio
import os
import shutil
import socket
import subprocess
from unittest.mock import AsyncMock, MagicMock

from motor.motor_asyncio import AsyncIOMotorClient
import pytest

from outreach.core import mailbox_connection as connection, suppression
from tests.test_outreach_mailbox_job_lifecycle import lifecycle

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable local services are opt-in")]


async def test_standalone_denies_oauth_exchange_before_secret_or_transport(lifecycle, monkeypatch, tmp_path):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.close()
    storage = tmp_path / 'standalone'
    storage.mkdir()
    process = subprocess.Popen([shutil.which('mongod'), '--bind_ip', '127.0.0.1', '--port', str(port),
        '--dbpath', str(storage), '--logpath', str(storage / 'mongo.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', tz_aware=True, serverSelectionTimeoutMS=200)
    db = client['test_unravler_mailbox_standalone']
    opening = AsyncMock(side_effect=AssertionError('No key service'))
    transport = MagicMock(side_effect=AssertionError('No provider'))
    monkeypatch.setattr(connection, 'open_oauth_secret', opening)
    monkeypatch.setattr(connection.httpx, 'AsyncClient', transport)
    try:
        for _ in range(50):
            try:
                await client.admin.command('ping')
                break
            except Exception:
                if process.poll() is not None: raise RuntimeError('Disposable standalone failed to start')
                await asyncio.sleep(.1)
        else: raise RuntimeError('Disposable standalone did not become ready')
        await db.outreach_mailbox_connection_jobs.insert_one(lifecycle.outreach_mailbox_connection_jobs.docs[0])
        with pytest.raises(suppression.SuppressionUnavailable):
            await connection.complete_connection_job(db, 'w', 'job')
        opening.assert_not_awaited()
        transport.assert_not_called()
        assert (await db.outreach_mailbox_connection_jobs.find_one({}))['status'] == 'queued'
        assert not await db.outreach_mailbox_exchange_budgets.find_one({})
    finally:
        try: await client.drop_database(db.name)
        finally:
            client.close()
            process.terminate()
            await asyncio.to_thread(process.wait, 10)
