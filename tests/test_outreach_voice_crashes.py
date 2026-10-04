"""SIGKILL + real Redis redelivery through production offline TTS state machine."""
import asyncio
import base64
import os
import subprocess
import sys
import threading
import uuid
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from celery import Celery

from outreach.core.voice_preparation import VoicePreparation, utcnow
from tests.test_outreach_execution_broker import wait_for
from tests.test_outreach_voice_preparation_mongo import real_voice_db, voice_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_BROKER") != "1", reason="Loopback Mongo/Redis process drill is opt-in")]


@pytest.mark.parametrize("stage,expected_calls,expected_status", [
    ("after_claim", 1, "prepared"), ("before_call", 0, "held_outcome"),
    ("after_call", 1, "held_outcome"), ("after_commit", 1, "prepared")])
async def test_killed_voice_worker_redelivery_never_repeats_paid_call(real_voice_db, tmp_path, stage, expected_calls, expected_status):
    from utils import encryption
    db = real_voice_db
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            audio = bytes(32000)
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    queue = "unravler_voice_" + uuid.uuid4().hex
    app = Celery("voice_publisher", broker="redis://127.0.0.1:6389/15")
    app.conf.broker_transport_options = {"visibility_timeout": 3, "global_keyprefix": queue + ":"}
    job = await VoicePreparation(db).queue("w", "l", "human")
    await db.drill_controls.insert_one({"_id": job["_id"], "halt_at": stage, "deliveries": 0})
    read = lambda: db.drill_controls.find_one({"_id": job["_id"]})
    key = base64.urlsafe_b64encode(encryption._fernet._signing_key + encryption._fernet._encryption_key).decode()
    processes, handles = [], []
    def start():
        env = {"PATH": os.environ["PATH"], "UNRAVLER_VOICE_DRILL": "1", "UNRAVLER_DRILL_DB": db.name,
            "UNRAVLER_DRILL_QUEUE": queue, "UNRAVLER_DRILL_ENDPOINT": "http://127.0.0.1:" + str(server.server_port),
            "OUTREACH_VOICE_PREPARATION_ENABLED": "true", "ELEVENLABS_API_KEY": "test-offline-credential",
            "OUTREACH_LIVE_ACTIONS_ENABLED": "false", "ENCRYPTION_KEY": key, "PYTHONUNBUFFERED": "1"}
        handle = (tmp_path / ("voice-" + str(len(processes)) + ".log")).open("w")
        handles.append(handle)
        processes.append(subprocess.Popen([sys.executable, "-m", "celery", "-A", "tests.outreach_voice_harness:app", "worker",
            "--pool=solo", "--loglevel=WARNING", "--without-heartbeat", "--without-gossip", "--without-mingle", "-Q", queue],
            cwd=Path(__file__).resolve().parents[1], env=env, stdout=handle, stderr=subprocess.STDOUT))
    try:
        start()
        app.send_task("voice_drill.prepare", args=[job["_id"], "w"], queue=queue)
        await wait_for(read, lambda row: row.get("checkpoint") == stage)
        processes[0].kill()
        await asyncio.to_thread(processes[0].wait, timeout=5)
        await db.drill_controls.update_one({"_id": job["_id"]}, {"$unset": {"halt_at": ""}})
        await db.outreach_voice_preparation_jobs.update_one({"_id": job["_id"]}, {"$set": {"claim_expires_at": utcnow() - timedelta(seconds=1)}})
        await asyncio.sleep(4)  # Expire visibility before the new consumer's first restore.
        start()
        await wait_for(read, lambda row: row.get("deliveries", 0) >= 2 and row.get("result") == expected_status)
        assert len(calls) == expected_calls
        stored = await db.outreach_voice_preparation_jobs.find_one({"_id": job["_id"]})
        assert stored["status"] == expected_status
        assert bool(await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})) == (expected_status == "prepared")
    finally:
        for process in processes:
            if process.poll() is None: process.kill()
            await asyncio.to_thread(process.wait, timeout=10)
        for handle in handles: handle.close()
        server.shutdown()
        server.server_close()
        app.close()
        from redis import Redis
        redis = Redis(host="127.0.0.1", port=6389, db=15)
        keys = list(redis.scan_iter(match=queue + ":*"))
        if keys: redis.delete(*keys)
        redis.close()
