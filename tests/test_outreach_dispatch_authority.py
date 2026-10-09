"""Real replica-set ordering between dispatch and existing authority writes."""
import asyncio
import os
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from outreach.core.content_approval import ContentApproval
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.manual_actions import ManualActions
from outreach.core.request_guard import RequestDenied, request_parent
from outreach.core.sender_execution import SenderExecution
from tests.test_outreach_physical_crashes import seed

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable local replica set is opt-in")]


@pytest_asyncio.fixture
async def ready_db(monkeypatch):
    from utils import encryption
    key = Fernet.generate_key()
    monkeypatch.setattr(encryption, "_fernet", Fernet(key))
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    name = "test_unravler_authority_" + uuid.uuid4().hex
    db = client[name]
    try:
        await seed(db, "manual", key)
        job = await db.outreach_manual_actions.find_one({"_id": "j"})
        await db.outreach_manual_actions.update_one({"_id": "j"}, {"$set": {"status": "in_flight", "owner": "owner"}})
        guard = SenderExecution(db)
        await guard.acquire("w", "a", "owner")
        await guard.begin("w", "a", "owner")
        yield db, job
    finally:
        await client.drop_database(name)
        client.close()


async def dispatch(db, job, factory, *, extra_validation=None):
    service = ManualActions(db)
    account = await db.outreach_accounts.find_one({"workspace_id": "w", "id": "a"})
    envelope = (await service.client(job, account)).request_envelope
    async def validate(current):
        reason = await ManualActions(current).validate(job, "owner")
        if reason or not extra_validation:
            return reason
        return await extra_validation(current)
    with request_parent("owner", lambda: service.validate(job, "owner"), approval_binding=job["binding"],
            transaction_validator=validate):
        return await envelope.call("POST", "/voyager/api/feed/reactions", factory, action="like")


async def stop(db, job, authority):
    if authority == "permission":
        await ExecutionPermission(db).revoke("w", "a", "operator", "test_stop")
    elif authority == "approval":
        record = await db.outreach_content_approvals.find_one({})
        await ContentApproval(db).decide("w", record["_id"], "human", "revoke", revision=record["revision"])
    elif authority == "lease":
        await db.outreach_proxy_leases.delete_one({"_id": "local-ip", "workspace_id": "w"})
    else:
        collection, query, changes = {
            "paid": ("outreach_entitlements", {"workspace_id": "w"}, {"is_revoked": True}),
            "sender": ("outreach_accounts", {"workspace_id": "w", "id": "a"}, {"credential_generation": "new-generation"}),
            "inventory": ("outreach_proxy_inventory", {"_id": "local-ip", "last_workspace_id": "w"}, {"status": "expired"}),
            "job": ("outreach_manual_actions", {"workspace_id": "w", "_id": "j"}, {"status": "cancelled"}),
            "target": ("outreach_engage_posts", {"workspace_id": "w", "id": "p"}, {"action_id": "replacement"}),
        }[authority]
        await db[collection].update_one(query, {"$set": changes})


AUTHORITIES = {"permission": "outreach_sender_execution", "approval": "outreach_content_approvals",
    "lease": "outreach_proxy_leases", "paid": "outreach_entitlements", "sender": "outreach_accounts",
    "inventory": "outreach_proxy_inventory", "job": "outreach_manual_actions", "target": "outreach_engage_posts"}


@pytest.mark.parametrize("authority", list(AUTHORITIES))
async def test_stop_after_snapshot_read_before_write_fence_wins_and_no_factory(ready_db, monkeypatch, authority):
    from outreach.core.dispatch_authority import AuthorityCollection
    db, job = ready_db
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityCollection.fence
    triggered = False
    async def pause(self, document, query):
        nonlocal triggered
        if self.name == AUTHORITIES[authority] and not triggered:
            triggered = True
            seen.set()
            await release.wait()
        return await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, "fence", pause)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    task = asyncio.create_task(dispatch(db, job, factory))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await asyncio.wait_for(stop(db, job, authority), 5)
        release.set()
        with pytest.raises(RequestDenied):
            await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
        physical = await db.outreach_physical_requests.find_one({})
        assert physical["status"] == "not_submitted" and not physical.get("dispatch_authorization")
        sender = await db.outreach_sender_execution.find_one({})
        assert not sender.get("physical_request_token")
        assert not (await db.outreach_content_approvals.find_one({})).get("authorized_submissions")
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_committed_dispatch_is_distinct_from_a_later_stop(ready_db):
    db, job = ready_db
    async def response():
        physical = await db.outreach_physical_requests.find_one({})
        assert physical["dispatch_authorization"]["mode"] == "transaction"
        await ExecutionPermission(db).revoke("w", "a", "operator", "stop_after_authorization")
        return httpx.Response(201, json={})
    factory = AsyncMock(side_effect=response)
    await dispatch(db, job, factory)
    factory.assert_awaited_once()
    sender = await db.outreach_sender_execution.find_one({})
    assert sender["permission"]["latched"]
    assert (await db.outreach_physical_requests.find_one({}))["status"] == "response_received"
    with pytest.raises(RequestDenied):
        await dispatch(db, job, factory)
    factory.assert_awaited_once()


async def test_standalone_database_denies_before_transport(ready_db, monkeypatch, tmp_path):
    from utils import encryption
    executable = shutil.which("mongod")
    assert executable, "This opt-in integration suite requires a local mongod"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    storage = tmp_path / "standalone"
    storage.mkdir()
    process = subprocess.Popen([executable, "--bind_ip", "127.0.0.1", "--port", str(port),
        "--dbpath", str(storage), "--logpath", str(storage / "mongo.log")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient(f"mongodb://127.0.0.1:{port}", tz_aware=True, serverSelectionTimeoutMS=200)
    # Normal grants now require transactions. Copy granted fixture evidence
    # from the replica set while preserving its configured dummy encryption key.
    replica, _ = ready_db
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    try:
        async with asyncio.timeout(10):
            while True:
                assert process.poll() is None, "Disposable standalone Mongo failed to start"
                try:
                    await client.admin.command("ping")
                    break
                except PyMongoError:
                    await asyncio.sleep(0.1)
        db = client["test_unravler_standalone_" + uuid.uuid4().hex]
        for name in await replica.list_collection_names():
            rows = await replica[name].find({}).to_list(length=100)
            if rows: await db[name].insert_many(rows)
        job = await db.outreach_manual_actions.find_one({"_id": "j"})
        await db.outreach_manual_actions.update_one({"_id": "j"}, {"$set": {"status": "in_flight", "owner": "owner"}})
        await SenderExecution(db).acquire("w", "a", "owner")
        await SenderExecution(db).begin("w", "a", "owner")
        factory = AsyncMock(return_value=httpx.Response(201, json={}))
        with pytest.raises(RequestDenied, match="dispatch_authority_unavailable"):
            await dispatch(db, job, factory)
        factory.assert_not_awaited()
        physical = await db.outreach_physical_requests.find_one({})
        assert physical["status"] == "not_submitted" and not physical.get("dispatch_authorization")
        assert not (await db.outreach_sender_execution.find_one({})).get("physical_request_token")
        from fastapi import HTTPException
        from outreach.api.leads import add_do_not_contact, DoNotContactRequest
        from outreach.core.email_finder import suppress_email
        from outreach.core.suppression import SuppressionUnavailable
        with pytest.raises(SuppressionUnavailable):
            await suppress_email(db, workspace_id="w", email="lead@example.com", reason="test")
        assert not await db.outreach_email_suppressions.find_one({"workspace_id": "w"})
        from outreach.core.erasure import OutreachErasure
        with pytest.raises(SuppressionUnavailable):
            await OutreachErasure(db).request("w", "u")
        assert not await db.outreach_erasure_requests.find_one({"workspace_id": "w"})
        with pytest.raises(HTTPException) as failed:
            await add_do_not_contact(DoNotContactRequest(email="lead@example.com"), current_user={"user_id": "w"}, db=db)
        assert failed.value.status_code == 503
        assert not await db.outreach_do_not_contact.find_one({"workspace_id": "w"})
        from outreach.core.credential_migration import CredentialMigration
        monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
        monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
        custody = CredentialMigration(db)
        view = await custody.inspect("w", "a")
        keys = AsyncMock(side_effect=AssertionError("Standalone must deny before KMS"))
        monkeypatch.setattr("outreach.core.credential_migration.seal_installed", keys)
        with pytest.raises(SuppressionUnavailable):
            await custody.migrate("w", "a", "local-operator", view["digest"], workers_drained=True)
        keys.assert_not_awaited()
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
        await asyncio.to_thread(process.wait, 10)


async def test_transaction_write_failure_rolls_back_token_and_content_authorization(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    db, job = ready_db
    original = AuthorityCollection.update_one
    async def fail_receipt(self, query, update, **kwargs):
        if self.name == "outreach_physical_requests" and "dispatch_authorization" in update.get("$set", {}):
            raise RuntimeError("isolated write failure before transaction commit")
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(AuthorityCollection, "update_one", fail_receipt)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RuntimeError):
        await dispatch(db, job, factory)
    factory.assert_not_awaited()
    assert not (await db.outreach_sender_execution.find_one({})).get("physical_request_token")
    assert not (await db.outreach_content_approvals.find_one({})).get("authorized_submissions")


async def test_expiry_crossed_after_commit_before_factory_is_proven_non_call(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import DispatchAuthority
    db, job = ready_db
    original = DispatchAuthority.authorize
    async def delayed(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        result["deadlines"].append(datetime.now(timezone.utc) - timedelta(seconds=1))
        return result
    monkeypatch.setattr(DispatchAuthority, "authorize", delayed)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RequestDenied, match="dispatch_authority_expired"):
        await dispatch(db, job, factory)
    factory.assert_not_awaited()
    assert (await db.outreach_physical_requests.find_one({}))["status"] == "not_submitted"


async def test_inbox_freshness_deadline_survives_commit_delay(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import DispatchAuthority
    from outreach.core.inbox_freshness import MAX_FRESHNESS_SECONDS, require_fresh_inbox
    db, job = ready_db
    now = datetime.now(timezone.utc)
    await db.outreach_accounts.update_one({"id": "a", "workspace_id": "w"}, {"$set": {
        "inbox_sync.coverage_started_at": now - timedelta(seconds=MAX_FRESHNESS_SECONDS - 1),
        "inbox_sync.completed_at": now}})
    original = DispatchAuthority.authorize
    async def delayed(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        await asyncio.sleep(1.1)
        return result
    monkeypatch.setattr(DispatchAuthority, "authorize", delayed)
    async def freshness(current):
        account = await current.outreach_accounts.find_one({"id": "a", "workspace_id": "w"})
        return await require_fresh_inbox(current, "w", account)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RequestDenied, match="dispatch_authority_expired"):
        await dispatch(db, job, factory, extra_validation=freshness)
    factory.assert_not_awaited()


async def test_working_window_is_rechecked_synchronously_after_commit(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import DispatchAuthority
    from outreach.core.rate_limiter import OutboundRateLimiter
    db, job = ready_db
    within = True
    monkeypatch.setattr(OutboundRateLimiter, "is_within_working_hours", lambda *args, **kwargs: within)
    original = DispatchAuthority.authorize
    async def cross_window(self, *args, **kwargs):
        nonlocal within
        result = await original(self, *args, **kwargs)
        within = False
        return result
    monkeypatch.setattr(DispatchAuthority, "authorize", cross_window)
    async def schedule(current):
        campaign = await current.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"})
        current.note_schedule(campaign.get("schedule") or {})
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RequestDenied, match="outside_working_hours"):
        await dispatch(db, job, factory, extra_validation=schedule)
    factory.assert_not_awaited()


async def test_existing_thread_reply_committed_before_fence_blocks_dispatch(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityCollection
    from outreach.tasks.sequence_executor import _recipient_has_reply
    db, job = ready_db
    await db.outreach_inbox_threads.insert_one({"_id": "thread", "workspace_id": "w", "account_id": "a",
        "lead_profile_url": "https://www.linkedin.com/in/person", "messages": []})
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityCollection.fence
    triggered = False
    async def pause(self, document, query):
        nonlocal triggered
        if self.name == "outreach_inbox_threads" and not triggered:
            triggered = True
            seen.set()
            await release.wait()
        return await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, "fence", pause)
    async def reply_check(current):
        lead = await current.outreach_leads.find_one({"workspace_id": "w", "id": "l"})
        return "lead_suppressed" if await _recipient_has_reply(current, "w", "a", lead) else None
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    task = asyncio.create_task(dispatch(db, job, factory, extra_validation=reply_check))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await db.outreach_inbox_threads.update_one({"_id": "thread", "workspace_id": "w"}, {
            "$set": {"has_lead_reply": True}, "$push": {"messages": {"sender_type": "lead"}}})
        release.set()
        with pytest.raises(RequestDenied):
            await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("kind,authority,collection", [
    ("gmail", "campaign", "outreach_campaigns"), ("gmail", "sequence", "outreach_sequences"),
    ("gmail", "mailbox", "outreach_mailboxes"), ("hunter", "finder", "outreach_hunter_credentials"),
    ("gmail", "lead", "outreach_leads"), ("gmail", "job", "outreach_sequence_jobs"),
    ("gmail", "intent", "outreach_intents"), ("gmail", "slot", "outreach_sender_slots")])
async def test_sequence_authority_revocation_before_fence_blocks_original_provider(monkeypatch, kind, authority, collection):
    from utils import encryption
    from outreach.core.authorization import authorization_snapshot
    from outreach.core.dispatch_authority import AuthorityCollection
    from outreach.core.execution_outbox import ExecutionOutbox
    from outreach.core.content_approval import sequence_binding
    from outreach.core.provider_boundary import ProviderEnvelope
    from outreach.core.email_finder import _linkedin_handle
    from outreach.tasks import sequence_dispatch
    from outreach.tasks.sequence_executor import _preflight_dispatch
    key = Fernet.generate_key()
    monkeypatch.setattr(encryption, "_fernet", Fernet(key))
    for flag in ("OUTREACH_LIVE_ACTIONS_ENABLED", "OUTREACH_EMAIL_SEND_ENABLED", "OUTREACH_EMAIL_SYNC_ENABLED", "OUTREACH_HUNTER_ENABLED"):
        monkeypatch.setenv(flag, "true")
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True)
    name = "test_unravler_authority_" + uuid.uuid4().hex
    db = client[name]
    seen, release = asyncio.Event(), asyncio.Event()
    task = None
    try:
        job_id = await seed(db, kind, key)
        await db.outreach_sequence_jobs.update_one({"_id": job_id}, {"$set": {"status": "processing", "owner": "job-owner",
            "claim_expires_at": datetime.now(timezone.utc) + timedelta(minutes=2)}})
        await db.outreach_leads.update_one({"id": "l"}, {"$set": {"execution_claim_token": "job-owner"}})
        job = await db.outreach_sequence_jobs.find_one({"_id": job_id})
        await ExecutionOutbox(db).claim("w", job["intent_id"], "owner")
        await ExecutionOutbox(db).begin_submission("w", job["intent_id"], "owner")
        await SenderExecution(db).acquire("w", "a", "owner")
        await SenderExecution(db).begin("w", "a", "owner")
        lead = await db.outreach_leads.find_one({"id": "l", "workspace_id": "w"})
        account = await db.outreach_accounts.find_one({"id": "a", "workspace_id": "w"})
        campaign = await db.outreach_campaigns.find_one({"id": "c", "workspace_id": "w"})
        sequence = await db.outreach_sequences.find_one({"campaign_id": "c", "workspace_id": "w"})
        expected = authorization_snapshot(campaign, account, sequence)
        source = "email_find" if kind == "hunter" else "email_send"
        resource = await db["outreach_hunter_credentials" if kind == "hunter" else "outreach_mailboxes"].find_one({"workspace_id": "w"})
        envelope = ProviderEnvelope(db, "w", "a", account, source, resource, operation_id="l:n", lead_id="l")
        envelope.finder_handle = _linkedin_handle(lead["linkedin_url"])
        binding = await sequence_binding(db, "w", "l") if kind == "gmail" else None
        original = AuthorityCollection.fence
        triggered = False
        async def pause(self, document, query):
            nonlocal triggered
            if self.name == collection and not triggered:
                triggered = True
                seen.set()
                await release.wait()
            return await original(self, document, query)
        monkeypatch.setattr(AuthorityCollection, "fence", pause)
        factory = AsyncMock(return_value=httpx.Response(200, json={"id": "local-message"}))
        async def run():
            node_type = "find_email" if kind == "hunter" else "send_email"
            with sequence_dispatch.dispatch_context(db, job, "job-owner"):
                with request_parent("owner", lambda: _preflight_dispatch(db, lead, expected, node_type), approval_binding=binding,
                        transaction_validator=lambda current: _preflight_dispatch(current, lead, expected, node_type, authorizing=True)):
                    return await envelope.call("GET" if kind == "hunter" else "POST", envelope.endpoint, factory,
                        action="finder" if kind == "hunter" else "email")
        task = asyncio.create_task(run())
        await asyncio.wait_for(seen.wait(), 5)
        query = {"workspace_id": "w"}
        changes = {"campaign": {"status": "paused"}, "sequence": {"version": 2}, "mailbox": {"connection_job_id": "replacement"},
            "finder": {"api_key_enc": "replacement"}, "lead": {"has_replied": True}, "job": {"status": "cancelled"},
            "intent": {"status": "unknown_outcome"}}
        if authority == "slot":
            await db[collection].delete_one(query)
        else:
            await db[collection].update_one(query, {"$set": changes[authority]})
        release.set()
        with pytest.raises(RequestDenied):
            await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
        assert not (await db.outreach_physical_requests.find_one({})).get("dispatch_authorization")
    finally:
        release.set()
        if task and not task.done():
            task.cancel()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        await client.drop_database(name)
        client.close()
