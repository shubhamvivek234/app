"""Actual OAuth job transactions, retention indexes and current-authority races."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from outreach.core import mailbox_connection as connection, mailbox_jobs, suppression
from tests.test_outreach_mailbox_job_lifecycle import lifecycle, http_context, job_row

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable replica set is opt-in")]


@pytest_asyncio.fixture
async def jobs_mongo(lifecycle):
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client["test_unravler_mailbox_jobs_" + uuid.uuid4().hex]
    await db.outreach_mailbox_connection_jobs.insert_many(lifecycle.outreach_mailbox_connection_jobs.docs)
    try: yield db
    finally: await client.drop_database(db.name); client.close()


async def test_atomic_install_receipt_survives_lost_ack_without_token_replay(jobs_mongo, monkeypatch):
    db = jobs_mongo
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == "install": raise TimeoutError("local lost ack")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", lost)
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "connected"}
    row = await db.outreach_mailbox_connection_jobs.find_one({"workspace_id": "w"})
    mailbox = await db.outreach_mailboxes.find_one({"workspace_id": "w"})
    from outreach.core.provider_custody import material_digest
    assert row["exchange_state"] == "installed" and row["installed_generation"] == mailbox["custody_generation"]
    assert row["installed_material_digest"] == material_digest(mailbox, "mailbox")
    assert not row.get("authorization_code_enc") and mailbox["sync_status"] == "initializing"
    await connection.complete_connection_job(db, "w", "job")
    http.post.assert_awaited_once()
    assert (await db.outreach_mailbox_exchange_budgets.find_one({}))["used"] == 1


@pytest.mark.parametrize("phase", ["authorize", "install"])
async def test_receipt_or_possible_commit_failure_never_fabricates_noncall(jobs_mongo, monkeypatch, phase):
    from outreach.core.suppression import SuppressionCollection
    db = jobs_mongo
    http = http_context(monkeypatch)
    update = SuppressionCollection.update_one
    async def failed(self, query, changes, **kwargs):
        if self.collection.name == "outreach_mailbox_connection_jobs" and (
                phase == "authorize" and changes.get("$set", {}).get("exchange_state") == "possible"
                or phase == "install" and changes.get("$set", {}).get("exchange_state") == "installed"):
            raise RuntimeError("local database interruption")
        return await update(self, query, changes, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", failed)
    assert (await connection.complete_connection_job(db, "w", "job"))["status"] == ("failed" if phase == "authorize" else "review_required")
    assert not await db.outreach_mailboxes.find_one({})
    if phase == "authorize":
        http.post.assert_not_awaited()
        assert not await db.outreach_mailbox_exchange_budgets.find_one({})
    else:
        http.post.assert_awaited_once()
        assert (await db.outreach_mailbox_connection_jobs.find_one({}))["exchange_state"] == "unknown"


async def test_lost_possible_ack_is_held_even_if_no_http_was_started(jobs_mongo, monkeypatch):
    db = jobs_mongo
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        row = await db.outreach_mailbox_connection_jobs.find_one({})
        if args[-1].__name__ == "check" and row["exchange_state"] == "possible": raise TimeoutError("local lost permit")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", lost)
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "review_required"}
    http.post.assert_not_awaited()
    assert (await db.outreach_mailbox_exchange_budgets.find_one({}))["used"] == 1
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))["exchange_state"] == "unknown"


@pytest.mark.parametrize("stage", ["preparing", "possible", "unknown", None])
async def test_lease_expiry_only_reclaims_proven_noncall(jobs_mongo, stage):
    db = jobs_mongo
    await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {"status": "running", "connection_owner": "old",
        "exchange_state": stage, "lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert (await mailbox_jobs.recover_due_jobs(db))["recovered"] == 1
    row = await db.outreach_mailbox_connection_jobs.find_one({})
    assert row["status"] == ("queued" if stage == "preparing" else "review_required")
    if stage != "preparing": assert not row.get("authorization_code_enc")


async def test_actual_index_cutover_removes_ttl_and_denies_second_active_slot(jobs_mongo):
    from db.indexes import ensure_mailbox_job_indexes
    db = jobs_mongo
    await db.outreach_mailbox_connection_jobs.create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db.outreach_mailbox_connection_jobs.create_index([("workspace_id", 1), ("sender_account_id", 1)], unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "queued", "running"]}})
    await ensure_mailbox_job_indexes(db)
    indexes = await db.outreach_mailbox_connection_jobs.index_information()
    assert not any("expireAfterSeconds" in definition for definition in indexes.values())
    assert indexes["mailbox_active_connection_v2"]["unique"]
    await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {"status": "review_required"}})
    with pytest.raises(DuplicateKeyError): await db.outreach_mailbox_connection_jobs.insert_one(job_row(id="replacement"))
    await ensure_mailbox_job_indexes(db)


async def test_duplicate_slot_migration_failure_preserves_retention_first(jobs_mongo):
    from db.indexes import ensure_mailbox_job_indexes
    db = jobs_mongo
    await db.outreach_mailbox_connection_jobs.create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {"status": "running"}, "$unset": {"protocol_version": ""}})
    await db.outreach_mailbox_connection_jobs.insert_one(job_row(id="held", status="review_required"))
    with pytest.raises(DuplicateKeyError): await ensure_mailbox_job_indexes(db)
    assert not any("expireAfterSeconds" in row for row in (await db.outreach_mailbox_connection_jobs.index_information()).values())
    assert await db.outreach_mailbox_connection_jobs.count_documents({"status": "review_required"}) == 2


async def test_repeated_index_setup_preserves_live_v2_exchange_after_cutover(jobs_mongo):
    from db.indexes import ensure_mailbox_job_indexes
    db = jobs_mongo
    await ensure_mailbox_job_indexes(db)
    await db.outreach_mailbox_connection_jobs.update_one({}, {'$set': {'status': 'running', 'exchange_state': 'possible'}})
    await ensure_mailbox_job_indexes(db)
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))['status'] == 'running'


@pytest.mark.parametrize("scheduler", ["publish", "recover"])
async def test_closed_tenant_prefix_backoff_is_ordered_without_reopening(jobs_mongo, monkeypatch, scheduler):
    from outreach.core.erasure import _control
    db = jobs_mongo
    await db.outreach_mailbox_connection_jobs.delete_many({})
    rows = [job_row(id=f"stopped-{i}", workspace_id=f"stopped-{i}", next_recovery_at=datetime.now(timezone.utc)) for i in range(50)]
    rows.append(job_row(id="good", next_recovery_at=datetime.now(timezone.utc)))
    if scheduler == "recover":
        for row in rows: row.update(status="running", exchange_state="preparing", connection_owner="old",
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    await db.outreach_mailbox_connection_jobs.insert_many(rows)
    for row in rows[:-1]:
        workspace = row["workspace_id"]
        async def stop(current):
            await current.outreach_suppression_guards.update_one(suppression.guard_scope(workspace), {"$set": {"erasure_state": "requested"}})
        await _control(db, workspace, stop)
    if scheduler == "publish":
        calls = []
        await mailbox_jobs.publish_due_jobs(db, lambda *args: calls.append(args))
        await mailbox_jobs.publish_due_jobs(db, lambda *args: calls.append(args))
        assert calls == [("good", "w")]
    else:
        assert (await mailbox_jobs.recover_due_jobs(db))["recovered"] == 0
        assert (await mailbox_jobs.recover_due_jobs(db))["recovered"] == 1
    assert await db.outreach_suppression_guards.count_documents({"erasure_state": "requested"}) == 50
    assert await db.outreach_mailbox_connection_jobs.count_documents({"workspace_id": {"$ne": "w"}, "status": rows[0]["status"]}) == 50


@pytest.mark.parametrize("change", ["owner", "cipher", "provider", "sender", "erasure", "paid"])
async def test_existing_authority_change_during_open_prevents_http(jobs_mongo, monkeypatch, change):
    from outreach.core.erasure import _control
    db = jobs_mongo
    http = http_context(monkeypatch)
    opening = connection.open_oauth_secret
    changed = False
    async def modify(*args):
        nonlocal changed
        value = await opening(*args)
        if not changed:
            changed = True
            if change in {"owner", "cipher", "provider", "sender"}:
                field, value2 = {"owner": ("connection_owner", "replacement"), "cipher": ("authorization_code_enc", "replacement"),
                    "provider": ("provider", "microsoft"), "sender": ("sender_account_id", "replacement")}[change]
                await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {field: value2}})
            elif change == "paid": monkeypatch.setattr(connection, "_paid_sender", AsyncMock(return_value=False))
            else:
                async def stop(current):
                    await current.outreach_suppression_guards.update_one(suppression.guard_scope("w"), {"$set": {"erasure_state": "requested"}})
                await _control(db, "w", stop)
        return value
    monkeypatch.setattr(connection, "open_oauth_secret", modify)
    try: await connection.complete_connection_job(db, "w", "job")
    except suppression.SuppressionUnavailable: assert change == "erasure"
    http.post.assert_not_awaited()


async def test_paid_cleanup_reactivation_keeps_permanent_exchange_hold(jobs_mongo):
    from outreach.core.paid_access import expire_due_entitlements
    db = jobs_mongo
    await db.outreach_entitlements.insert_one({"workspace_id": "w", "status": "active", "paid_through": datetime.now(timezone.utc) - timedelta(seconds=1)})
    await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {"status": "running", "exchange_state": "possible"}})
    assert await expire_due_entitlements(db) == 1
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))["status"] == "review_required"
    await db.outreach_entitlements.update_one({}, {"$set": {"status": "active", "paid_through": datetime.now(timezone.utc) + timedelta(days=30)}})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied: await connection.start_mailbox_connection(db, "w", "user", "a", "gmail")
    assert denied.value.status_code == 409


async def test_new_paid_term_before_mailbox_stop_preserves_new_oauth_state(jobs_mongo, monkeypatch):
    from outreach.core.paid_access import expire_due_entitlements
    db = jobs_mongo
    await db.outreach_entitlements.insert_one({"workspace_id": "w", "status": "active", "paid_through": datetime.now(timezone.utc) - timedelta(seconds=1)})
    await db.outreach_mailbox_oauth_states.insert_one({"_id": "new-state", "workspace_id": "w", "code_verifier_enc": "encrypted-new"})
    mutate = suppression.mutate_suppression
    async def renew(*args):
        if args[-1].__name__ == "stop_mailboxes":
            await db.outreach_entitlements.update_one({}, {"$set": {"status": "active", "paid_through": datetime.now(timezone.utc) + timedelta(days=30)}})
        return await mutate(*args)
    monkeypatch.setattr(suppression, "mutate_suppression", renew)
    assert await expire_due_entitlements(db) == 1
    assert (await db.outreach_mailbox_oauth_states.find_one({"_id": "new-state"}))["code_verifier_enc"] == "encrypted-new"
    assert (await db.outreach_mailbox_connection_jobs.find_one({}))["status"] == "queued"


@pytest.mark.parametrize('state', ['unknown', 'installed'])
async def test_erasure_scrubs_code_and_archives_minimal_exchange_evidence(jobs_mongo, state):
    from outreach.core.erasure import OutreachErasure, _control
    db = jobs_mongo
    await db.outreach_mailbox_connection_jobs.update_one({}, {"$set": {"status": "review_required" if state == 'unknown' else 'connected', "exchange_state": state}})
    await db.outreach_mailbox_exchange_budgets.insert_one({"workspace_id": "w", "used": 1, "sender_account_id": "a"})
    service = OutreachErasure(db)
    async def scrub(current):
        await service._stop(current, "w", datetime.now(timezone.utc))
        await service._erase_batch(current, "w", "outreach_mailbox_connection_jobs")
        await service._erase_batch(current, "w", "outreach_mailbox_exchange_budgets")
    await _control(db, "w", scrub)
    hold = await db.outreach_erasure_holds.find_one({})
    assert hold["kind"] == ("unresolved_submission" if state == 'unknown' else 'submission_receipt')
    assert hold["operation_kind"] == "oauth_exchange" and hold["outcome_state"] == state
    assert not await db.outreach_mailbox_connection_jobs.find_one({}) and not await db.outreach_mailbox_exchange_budgets.find_one({})
    assert not any(name in str(hold) for name in ("authorization_code_enc", "code_verifier_enc", "private-code", "connection_owner"))


async def test_concurrent_duplicate_delivery_makes_only_one_token_exchange(jobs_mongo, monkeypatch):
    db = jobs_mongo
    http = http_context(monkeypatch)
    first, second = await asyncio.gather(connection.complete_connection_job(db, "w", "job"), connection.complete_connection_job(db, "w", "job"))
    assert sorted([first["status"], second["status"]]) == ["already_claimed", "connected"]
    http.post.assert_awaited_once()


async def test_sigkill_after_loopback_oauth_request_cannot_replay_on_redelivery(jobs_mongo, monkeypatch):
    """Run production ownership/HTTP in a fresh process, then kill before response."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    import subprocess
    import threading
    import sys
    db = jobs_mongo
    reached, release = threading.Event(), threading.Event()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            calls.append(self.path)
            reached.set()
            release.wait(20)
            try:
                self.send_response(500)
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    await db.outreach_entitlements.insert_one({'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': datetime.now(timezone.utc) + timedelta(days=30)})
    await db.outreach_accounts.insert_one({'workspace_id': 'w', 'id': 'a', 'status': 'active'})
    await db.outreach_sender_slots.insert_one({'workspace_id': 'w', 'sender_id': 'a'})
    environment = {**os.environ, 'OUTREACH_DRILL_OAUTH_URL': f'http://127.0.0.1:{server.server_port}/token',
        'OUTREACH_DRILL_DB': db.name, 'OUTREACH_CREDENTIAL_CUSTODY_MODE': 'legacy_fernet',
        'OUTREACH_MAILBOX_CONNECTION_ENABLED': 'true', 'OUTREACH_MAILBOX_PILOT_WORKSPACES': 'w'}
    command = [sys.executable, '-m', 'tests.outreach_mailbox_job_harness']
    child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert await asyncio.to_thread(reached.wait, 15), 'Loopback request was not reached'
        row = await db.outreach_mailbox_connection_jobs.find_one({})
        assert row['exchange_state'] == 'possible' and row['connection_owner']
        child.kill()
        await asyncio.to_thread(child.wait, 5)
        assert child.returncode < 0
        await db.outreach_mailbox_connection_jobs.update_one({}, {'$set': {'lease_until': datetime.now(timezone.utc) - timedelta(seconds=1),
            'next_recovery_at': datetime.now(timezone.utc)}})
        assert (await mailbox_jobs.recover_due_jobs(db))['recovered'] == 1
        redelivery = await asyncio.to_thread(subprocess.run, command, cwd=Path(__file__).resolve().parents[1], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        assert redelivery.returncode == 0 and redelivery.stdout.strip() == b'already_claimed'
        assert calls == ['/token']
        assert (await db.outreach_mailbox_connection_jobs.find_one({}))['status'] == 'review_required'
        assert (await db.outreach_mailbox_exchange_budgets.find_one({}))['used'] == 1
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 5)
        child.communicate()
        release.set()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
