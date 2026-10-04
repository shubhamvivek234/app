"""SIGKILL/redelivery through production adapters; HTTP is confined to loopback."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from celery import Celery
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient
from redis import Redis

from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.manual_actions import ManualActions
from outreach.core.provider_boundary import provider_generation
from outreach.tasks import sequence_dispatch
from tests.test_outreach_execution_broker import wait_for
from tests.test_outreach_execution_outbox import execution_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(os.getenv("OUTREACH_TEST_LOCAL_BROKER") != "1",
    reason="Disposable local Redis/Mongo/HTTP process-kill drill is opt-in")]


class LocalProvider:
    """Survives worker death; counts every request, with no provider deduplication."""
    def __init__(self, kind, block=False):
        self.kind, self.block = kind, block
        self._calls = 0
        self.lock = threading.Lock()
        self.received = threading.Event()
        self.release = threading.Event()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Never log headers, tokens, bodies or query strings.

            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                with provider.lock:
                    provider._calls += 1
                provider.received.set()
                if provider.block:
                    provider.release.wait(20)
                status, body = (201, {}) if provider.kind == "manual" else (200, {"id": "local-message"})
                if provider.kind == "graph":
                    status, body = 202, None
                if provider.kind == "hunter":
                    body = {"data": {"email": "found@example.com", "source_type": "found", "verification": {"status": "valid"}}}
                payload = json.dumps(body).encode() if body is not None else b""
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Expected after SIGKILL of the requesting worker.

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def calls(self):
        with self.lock:
            return self._calls

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    async def close(self):
        self.release.set()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        await asyncio.to_thread(self.thread.join, 5)


async def seed(db, kind, key):
    now = datetime.now(timezone.utc)
    cipher = Fernet(key)
    encrypt = lambda value: cipher.encrypt(value.encode()).decode()
    for collection, values in execution_db().collections.items():
        if values.docs:
            await db[collection].insert_many(values.docs)
    await db.outreach_accounts.update_one({"id": "a"}, {"$set": {
        "country_code": "US", "session_cookie_enc": encrypt("local-only-session"), "jsession_id": "ajax:local",
        "proxy": {"proxy_id": "local-ip", "host": "127.0.0.1", "port": 9,
                  "username": "local", "password_enc": encrypt("local-only-password")}}})
    await db.outreach_entitlements.insert_one({"workspace_id": "w", "status": "active", "seats": 1,
        "paid_through": now + timedelta(days=1), "payment_source": "manual_verified_invoice"})
    await db.outreach_sender_slots.insert_one({"workspace_id": "w", "sender_id": "a"})
    await db.outreach_proxy_leases.insert_one({"_id": "local-ip", "workspace_id": "w", "sender_id": "a"})
    await db.outreach_proxy_inventory.insert_one({"_id": "local-ip", "status": "available", "last_workspace_id": "w",
        "country_code": "US", "expires_at": now + timedelta(days=1), "provider": "iproyal_static"})
    if kind == "manual":
        await db.outreach_engage_lists.insert_one({"id": "list", "workspace_id": "w"})
        await db.outreach_engage_posts.insert_one({"id": "p", "workspace_id": "w", "list_id": "list", "status": "pending", "post_urn": "urn:post", "action_id": "j"})
        await ManualActions(db).queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "local-reviewer")
        generation, source, job_id = "g", "engage", "j"
    else:
        await db.outreach_campaigns.update_one({"id": "c"}, {"$set": {"schedule": {
            "timezone": "UTC", "days": list(range(7)), "start_time": "00:00", "end_time": "23:59"}}})
        node = {"id": "n", "type": "find_email" if kind == "hunter" else "send_email", "config": {"subject": "Hello", "body": "Reviewed body"}}
        await db.outreach_sequences.update_one({"campaign_id": "c"}, {"$set": {"compiled_dag.nodes.n": node}})
        resource = {"workspace_id": "w", "sender_account_id": "a", "provider": "microsoft" if kind == "graph" else "gmail",
            "provider_user_id": "local-user", "email": "sender@example.com", "connection_job_id": "local-mailbox",
            "status": "active", "sync_status": "healthy", "last_sync_at": now,
            "access_token_enc": encrypt("local-only-access"), "refresh_token_enc": encrypt("local-only-refresh"),
            "token_expires_at": now + timedelta(hours=1)}
        await db.outreach_mailboxes.insert_one(resource)
        if kind == "hunter":
            resource = {"workspace_id": "w", "api_key_enc": encrypt("local-only-hunter")}
            await db.outreach_hunter_credentials.insert_one(resource)
        else:
            await db.outreach_leads.update_one({"id": "l"}, {"$set": {"email": "lead@example.com"}})
            binding = await sequence_binding(db, "w", "l")
            approval = await ContentApproval(db).ensure(binding)
            await ContentApproval(db).decide("w", approval["_id"], "local-reviewer", "approve", revision=approval["revision"])
        source = "email_find" if kind == "hunter" else "email_send"
        generation = provider_generation(await db.outreach_accounts.find_one({"id": "a"}), resource, source)
        await sequence_dispatch.prepare_due(db)
        job_id = (await db.outreach_sequence_jobs.find_one({}))["_id"]
    await ExecutionPermission(db).grant("w", "a", generation, [source], "local-test-operator")
    return job_id


CASES = [("manual", stage) for stage in ("job_preparing", "physical_preparing", "physical_possible", "physical_token",
    "during_transport", "http_response", "physical_receipt", "physical_token_cleared", "manual_projection", "manual_completed")]
CASES += [(kind, stage) for kind in ("gmail", "graph", "hunter") for stage in (
    "physical_token", "during_transport", "http_response", "physical_receipt", "physical_token_cleared", "provider_result", "logical_result")]
CASES += [(kind, "transaction_token_written") for kind in ("manual", "gmail", "graph", "hunter")]


@pytest.mark.parametrize("kind,stage", CASES)
async def test_physical_request_sigkill_redelivery_and_database_recovery(monkeypatch, tmp_path, kind, stage):
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    name, queue = "test_unravler_physical_" + uuid.uuid4().hex, "unravler_physical_" + uuid.uuid4().hex
    db = client[name]
    provider = LocalProvider(kind, block=stage == "during_transport")
    app = Celery("physical_publisher", broker="redis://127.0.0.1:6389/15")
    app.conf.broker_transport_options = {"visibility_timeout": 3, "global_keyprefix": queue + ":"}
    key = Fernet.generate_key()
    processes, handles = [], []
    flags = {"OUTREACH_LIVE_ACTIONS_ENABLED": "true", "OUTREACH_MAILBOX_CONNECTION_ENABLED": "true", "OUTREACH_EMAIL_SEND_ENABLED": "true",
             "OUTREACH_EMAIL_SYNC_ENABLED": "true", "OUTREACH_HUNTER_ENABLED": "true"}
    for flag, value in flags.items():
        monkeypatch.setenv(flag, value)
    def start_worker():
        env = {"PATH": os.environ["PATH"], "PYTHONUNBUFFERED": "1", "UNRAVLER_PHYSICAL_DRILL": "1",
            "UNRAVLER_DRILL_DB": name, "UNRAVLER_DRILL_QUEUE": queue, "UNRAVLER_DRILL_ENDPOINT": provider.url,
            "ENCRYPTION_KEY": key.decode(), **flags}
        handle = (tmp_path / f"physical-worker-{len(processes)}.log").open("w")
        handles.append(handle)
        process = subprocess.Popen([sys.executable, "-m", "celery", "-A", "tests.outreach_physical_harness:app", "worker",
            "--pool=solo", "--loglevel=WARNING", "--without-heartbeat", "--without-gossip", "--without-mingle", "-Q", queue],
            cwd=Path(__file__).resolve().parents[1], env=env, stdout=handle, stderr=subprocess.STDOUT)
        processes.append(process)
    try:
        job_id = await seed(db, kind, key)
        await db.drill_controls.insert_one({"_id": "run", "halt_at": stage, "kind": kind, "deliveries": 0})
        read = lambda: db.drill_controls.find_one({"_id": "run"})
        start_worker()
        app.send_task("tests.outreach_physical_harness.execute", args=["w", job_id], queue=queue)
        if stage == "during_transport":
            assert await asyncio.to_thread(provider.received.wait, 20)
        else:
            await wait_for(read, lambda value: value.get("checkpoint") == stage, timeout=25)
        processes[0].kill()
        await asyncio.to_thread(processes[0].wait, 5)
        provider.release.set()
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.drill_controls.update_one({"_id": "run"}, {"$set": {"resume": True}})
        for collection in ("outreach_manual_actions", "outreach_sequence_jobs", "outreach_intents", "outreach_tasks"):
            await db[collection].update_many({}, {"$set": {"claim_expires_at": past}})
        await db.outreach_leads.update_many({}, {"$set": {"execution_claimed_at": past}})
        await db.outreach_sender_execution.update_many({}, {"$set": {"expires_at": past}})
        await asyncio.sleep(4)
        start_worker()
        await wait_for(read, lambda value: value.get("deliveries", 0) >= 2 and value.get("redelivered") and value.get("finished"), timeout=35)
        completed = stage in {"job_preparing", "physical_receipt", "physical_token_cleared", "manual_projection", "manual_completed", "provider_result", "logical_result"}
        assert provider.calls == (0 if stage in {"physical_preparing", "physical_possible", "physical_token", "transaction_token_written"} else 1)
        physical = await db.outreach_physical_requests.find_one({})
        sender = await db.outreach_sender_execution.find_one({})
        if completed:
            assert physical["status"] == "response_received"
            assert sender["status"] == "idle" and not sender.get("physical_request_token")
        else:
            assert physical["status"] in {"preparing", "in_flight", "unknown_outcome"}
            assert sender["status"] == "in_flight"
            if stage not in {"physical_preparing", "physical_possible", "transaction_token_written"}:
                assert sender["physical_request_token"] == physical["_id"]
            if stage == "transaction_token_written":
                assert not sender.get("physical_request_token")
                assert not physical.get("dispatch_authorization")
            with pytest.raises(ValueError):
                await ExecutionPermission(db).grant("w", "a", "g", ["engage"], "local-test-operator", clear_latch=True)
        if kind == "manual":
            job = await db.outreach_manual_actions.find_one({"_id": job_id})
            assert job["status"] == ("completed" if completed else "unknown_outcome")
            post = await db.outreach_engage_posts.find_one({"id": "p"})
            assert post.get("reactions_count", 0) == int(completed)
            if stage == "physical_preparing":
                from outreach.core.manual_resolution import ManualResolution
                service = ManualResolution(db)
                view = await service.inspect("w", job_id)
                await service.resolve("w", job_id, {"like": "not_sent_stop"}, "local-test-operator",
                    "Killed and drained the isolated worker before physical submission.", workers_drained=True, expected_digest=view["review_digest"])
                assert (await db.outreach_physical_requests.find_one({}))["original_status"] == "preparing"
        else:
            intent = await db.outreach_intents.find_one({})
            assert intent["status"] == ("executed" if completed else "unknown_outcome")
            operation = await db["outreach_email_discoveries" if kind == "hunter" else "outreach_email_operations"].find_one({})
            if completed:
                assert operation["status"] == ("found" if kind == "hunter" else "accepted")
                if kind != "hunter":
                    assert operation.get("provider_message_id") == ("local-message" if kind == "gmail" else None)
                else:
                    assert (await db.outreach_leads.find_one({"id": "l"}))["email"] == "found@example.com"
        # Recovery is repeatable, including when a replacement owner now holds
        # a different request. The old completed job must not release that hold.
        if completed:
            await db.outreach_sender_execution.update_one({"_id": sender["_id"]}, {"$set": {
                "status": "in_flight", "owner_token": "replacement", "physical_request_token": "replacement-request"}})
            if kind == "manual":
                await ManualActions(db).recover("w", job_id)
            else:
                from outreach.core.execution_recovery import recover_intent
                await recover_intent(db, await db.outreach_intents.find_one({}))
            replacement = await db.outreach_sender_execution.find_one({})
            assert replacement["owner_token"] == "replacement" and replacement["physical_request_token"] == "replacement-request"
            assert provider.calls == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(process.wait, 5)
        for handle in handles:
            handle.close()
        redis = Redis(host="127.0.0.1", port=6389, db=15)
        keys = list(redis.scan_iter(match=queue + ":*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        app.close()
        await provider.close()
        await client.drop_database(name)
        client.close()
