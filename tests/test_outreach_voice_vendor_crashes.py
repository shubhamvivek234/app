"""SIGKILL over production metadata GET/state machine, with no external egress."""
import asyncio
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

import pytest
from outreach.core import voice_key_custody
from outreach.core.oauth_app_custody import KMS_SETTINGS
from outreach.core.voice_studio import now
from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
from tests.test_outreach_voice_vendor_mongo import review_db, studio_db, scoped, prepared, capture, release
from tests.test_outreach_voice_vendor_evidence import METADATA, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback process drill is opt-in')]


@pytest.mark.parametrize('stage,calls,status', [('after_prepare', 0, 'preparing'), ('after_possible', 0, 'possible'),
    ('after_response', 1, 'possible'), ('after_receipt', 1, 'received')])
async def test_sigkill_never_replays_metadata_or_releases_without_receipt(review_db, scoped, monkeypatch, tmp_path, stage, calls, status):
    db = review_db; profile = await prepared(db, monkeypatch); service = VoiceVendorEvidence(db)
    digest = (await service.inspect('w', profile['id']))['review_digest']; requests = []
    class Provider(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path); body = json.dumps(METADATA).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    names = ('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'OUTREACH_CUSTODY_ENVIRONMENT_ID',
        'OUTREACH_ELEVENLABS_API_KEY_ENC', 'OUTREACH_ELEVENLABS_KEY_GENERATION', *KMS_SETTINGS)
    env = {name: os.environ[name] for name in names if name in os.environ}
    env.update({'PATH': os.environ['PATH'], 'UNRAVLER_VENDOR_DRILL': '1', 'ELEVENLABS_API_KEY': '',
        'UNRAVLER_VENDOR_ENDPOINT': f'http://127.0.0.1:{server.server_port}/metadata',
        'OUTREACH_LIVE_ACTIONS_ENABLED': 'false', 'OUTREACH_VOICE_STUDIO_ENABLED': 'false',
        'OUTREACH_VOICE_PREPARATION_ENABLED': 'false', 'PYTHONUNBUFFERED': '1'})
    checkpoint = uuid.uuid4().hex; process = None
    try:
        with (tmp_path / 'vendor.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'tests.outreach_voice_vendor_harness', db.name,
                profile['id'], digest, stage, checkpoint], cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(200):
                row = await db.drill_controls.find_one({'_id': checkpoint})
                if row and row.get('checkpoint') == stage: break
                if process.poll() is not None: pytest.fail((tmp_path / 'vendor.log').read_text())
                await asyncio.sleep(.1)
            else: pytest.fail('Owned worker failed to reach checkpoint')
            process.kill(); await asyncio.to_thread(process.wait, timeout=5)
        assert len(requests) == calls
        key = voice_key_custody.prepare_key
        async def no_open(**kwargs): pytest.fail('Saved retry does not reopen custody')
        monkeypatch.setattr(voice_key_custody, 'prepare_key', no_open)
        job = await capture(db, profile, digest=digest)
        assert job['status'] == status and len(requests) == calls
        monkeypatch.setattr(voice_key_custody, 'prepare_key', key)
        if status == 'received':
            assert (await release(db, profile, job['job_id']))['current_matches']
        else:
            with pytest.raises(ValueError): await release(db, profile, job['job_id'])
            await db.outreach_voice_vendor_reads.update_one({'_id': job['job_id']}, {'$set': {
                'authorization_expires_at': now() - timedelta(seconds=1)}})
            view = await service.inspect('w', profile['id'], job['job_id'])
            closed = await service.close_read('w', profile['id'], job['job_id'], 'operator', EVIDENCE,
                view['review_digest'], workers_drained=True)
            assert closed['status'] == ('stopped' if status == 'preparing' else 'read_interrupted')
            assert (await db.outreach_voices.find_one({'id': profile['id']}))['studio_review_required']
        assert len(requests) == calls
    finally:
        if process and process.poll() is None:
            process.kill(); await asyncio.to_thread(process.wait, timeout=5)
        await asyncio.to_thread(server.shutdown); server.server_close(); thread.join(timeout=5)
