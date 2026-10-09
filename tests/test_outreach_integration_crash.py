"""SIGKILL through the production adapter over owned loopback TCP, with real Mongo."""
import asyncio
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import signal
import subprocess
import sys
import threading
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet
import pytest
from outreach.core import integration_custody as custody
from outreach.core.integration_delivery import IntegrationDelivery, now
from tests.test_outreach_integration_mongo import real_db
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback Mongo/TCP crash test is opt-in')]

CHILD = '''
import asyncio, os
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from outreach.core import safe_transport
from outreach.core.integration_delivery import IntegrationDelivery
from utils import encryption

encryption._fernet = None
original = safe_transport.create_safe_client
class LocalRoute(httpx.AsyncBaseTransport):
    def __init__(self, preflight): self.inner = safe_transport.SafeAsyncHTTPTransport(allow_private_for_tests=True, preflight=preflight)
    async def handle_async_request(self, request):
        local = httpx.Request(request.method, 'http://127.0.0.1:' + os.environ['TEST_HTTP_PORT'],
            headers=request.headers, content=await request.aread())
        return await self.inner.handle_async_request(local)
    async def aclose(self): await self.inner.aclose()
safe_transport.create_safe_client = lambda **kw: httpx.AsyncClient(transport=LocalRoute(kw.get('preflight')), trust_env=False)
class Worker(IntegrationDelivery):
    async def _finish(self, job):
        if os.environ['TEST_KILL_STAGE'] == 'received':
            await asyncio.Event().wait()
        return await super()._finish(job)
async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    try: await Worker(client[os.environ['TEST_DB']]).run('w', os.environ['TEST_JOB'])
    finally: client.close()
asyncio.run(main())
'''

@pytest.mark.parametrize('stage', ['possible', 'received'])
async def test_process_death_keeps_unknown_or_repairs_saved_receipt_without_resend(real_db, monkeypatch, tmp_path, stage):
    from utils import encryption
    db = real_db
    key = Fernet.generate_key(); monkeypatch.setattr(encryption, '_fernet', Fernet(key))
    monkeypatch.setenv('ENCRYPTION_KEY', key.decode())
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    row = await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'})
    row.update(await custody.seal('loopback-secret', row, 'w', 'webhook'))
    await db.outreach_webhooks.update_one({'workspace_id': 'w', 'id': 'hook'}, {'$set': {
        field: row[field] for field in ['secret_enc', 'credential_generation', 'custody_workspace_id']}})
    job = await queue(db)
    seen = threading.Event(); release = threading.Event(); calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers['Content-Length'])))
            seen.set()
            if stage == 'possible': release.wait(10)
            try:
                self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
            except (BrokenPipeError, ConnectionResetError): pass
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    source = tmp_path / 'worker.py'; source.write_text(CHILD)
    env = {**os.environ, 'PYTHONPATH': os.getcwd(), 'TEST_DB': db.name, 'TEST_JOB': job['id'],
        'TEST_KILL_STAGE': stage, 'TEST_HTTP_PORT': str(server.server_port)}
    process = subprocess.Popen([sys.executable, str(source)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            saved = await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w', 'id': job['id']})
            if seen.is_set() and saved['status'] == stage: break
            if process.poll() is not None: raise AssertionError('Child failed before kill boundary')
            await asyncio.sleep(.02)
        else: raise AssertionError('Child did not reach physical boundary')
        process.send_signal(signal.SIGKILL); process.wait(timeout=5)
        assert len(calls) == 1
        await db.outreach_webhook_deliveries.update_one({'workspace_id': 'w', 'id': job['id']},
            {'$set': {'leased_until': now() - timedelta(seconds=1)}})
        provider = AsyncMock()
        result = await IntegrationDelivery(db).run('w', job['id'], provider=provider)
        assert result['status'] == ('review_required' if stage == 'possible' else 'delivered')
        await IntegrationDelivery(db).run('w', job['id'], provider=provider)
        provider.assert_not_awaited()
        saved = await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w', 'id': job['id']})
        assert saved['attempt'] == 1
        if stage == 'received': assert saved['receipt']['status_code'] == 200
    finally:
        release.set()
        if process.poll() is None: process.kill(); process.wait(timeout=5)
        await asyncio.to_thread(server.shutdown)
        server.server_close(); thread.join(timeout=5)
