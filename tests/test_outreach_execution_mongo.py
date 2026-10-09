"""Opt-in real MongoDB concurrency/fault tests, isolated from application data.

Run a disposable mongod on 127.0.0.1:27028 and set
OUTREACH_TEST_LOCAL_MONGO=1. Each test creates and drops its own random database.
Provider transport stays fake; no LinkedIn calls are made.
"""
import asyncio
import os
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from outreach.core.execution_outbox import ExecutionOutbox
from outreach.core.execution_recovery import recover_intent
from outreach.core.sequence_versions import load_sequence, publish_sequence
from outreach.core.sender_execution import SenderExecution
from tests.test_outreach_execution_outbox import intent, NOW, execution_db, stub_transport

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable local MongoDB test is opt-in")]


@pytest_asyncio.fixture
async def mongo_db():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    await client.admin.command("ping")
    name = "test_unravler_execution_" + uuid.uuid4().hex
    db = client[name]
    await db.outreach_tasks.create_index([("workspace_id", 1), ("id", 1)], unique=True)
    try:
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def test_real_mongo_duplicate_publication_and_atomic_claim(mongo_db):
    docs = await asyncio.gather(*(intent(mongo_db) for _ in range(24)))
    assert len({d["_id"] for d in docs}) == 1
    outbox = ExecutionOutbox(mongo_db)
    claims = await asyncio.gather(*(outbox.claim("w", docs[0]["_id"], str(n), now=NOW) for n in range(24)))
    assert sum(claims) == 1
    assert await mongo_db.outreach_intents.count_documents({}) == 1


async def test_real_mongo_sender_ownership_and_crash_latch(mongo_db):
    guard = SenderExecution(mongo_db)
    claims = await asyncio.gather(*(guard.acquire("w", "a", str(n), now=NOW) for n in range(16)))
    assert sum(claims) == 1
    owner = str(claims.index(True))
    assert await guard.begin("w", "a", owner, now=NOW)
    assert not await guard.acquire("w", "a", "retry", now=NOW + timedelta(days=1))
    assert not await guard.release("w", "a", "stale-owner")


async def test_real_mongo_stale_claim_and_possible_submission_cannot_replay(mongo_db):
    outbox = ExecutionOutbox(mongo_db)
    doc = await intent(mongo_db)
    assert await outbox.claim("w", doc["_id"], "old", now=NOW)
    later = NOW + timedelta(minutes=3)
    assert await outbox.claim("w", doc["_id"], "new", now=later)
    assert not await outbox.begin_submission("w", doc["_id"], "old", now=later)
    assert await outbox.begin_submission("w", doc["_id"], "new", now=later)
    assert await outbox.quarantine_expired("w", doc["_id"], now=NOW + timedelta(days=1))
    assert not await outbox.claim("w", doc["_id"], "replay", now=NOW + timedelta(days=2))


async def test_real_mongo_duplicate_worker_dispatch_submits_once(mongo_db, monkeypatch):
    executor, transport = stub_transport(monkeypatch)
    for name, collection in execution_db().collections.items():
        if collection.docs:
            await mongo_db[name].insert_many(collection.docs)
    await asyncio.gather(*(executor.SequenceExecutor.execute_lead_step("l", mongo_db, workspace_id="w") for _ in range(12)))
    assert transport.send_direct_message.await_count == 1
    assert (await mongo_db.outreach_tasks.find_one({"id": "l:n"}))["status"] == "completed"
    assert (await mongo_db.outreach_intents.find_one({}))["attempt"]["outcome"] == "provider_accepted"


async def test_real_mongo_sequence_job_duplicate_delivery_keeps_original_context(mongo_db, monkeypatch):
    from outreach.tasks import sequence_dispatch
    executor, transport = stub_transport(monkeypatch)
    monkeypatch.setattr(sequence_dispatch, "sequence_dispatch_enabled", lambda: True)
    for name, collection in execution_db().collections.items():
        if collection.docs:
            await mongo_db[name].insert_many(collection.docs)
    assert (await sequence_dispatch.prepare_due(mongo_db))["prepared"] == 1
    job = await mongo_db.outreach_sequence_jobs.find_one({})
    await asyncio.gather(*(sequence_dispatch.execute_job(mongo_db, "w", job["_id"]) for _ in range(12)))
    assert transport.send_direct_message.await_count == 1
    assert (await mongo_db.outreach_sequence_jobs.find_one({"_id": job["_id"]}))["status"] == "completed"
    lead = await mongo_db.outreach_leads.find_one({"id": "l"})
    assert "execution_claim_token" not in lead


async def test_real_mongo_saved_acceptance_recovers_after_projection_crash(mongo_db):
    outbox = ExecutionOutbox(mongo_db)
    doc = await intent(mongo_db)
    await outbox.claim("w", doc["_id"], "owner", now=NOW)
    await outbox.begin_submission("w", doc["_id"], "owner", now=NOW)
    await mongo_db.outreach_tasks.insert_one({"id": "l:n", "workspace_id": "w", "intent_id": doc["_id"],
                                            "owner_token": "owner", "status": "dispatching"})
    await outbox.finish("w", doc["_id"], "owner", "provider_accepted", provider_message_id="m", now=NOW)
    assert await recover_intent(mongo_db, await mongo_db.outreach_intents.find_one({"_id": doc["_id"]})) == "repaired"
    assert (await mongo_db.outreach_tasks.find_one({"id": "l:n"}))["provider_message_id"] == "m"
    assert not await outbox.claim("w", doc["_id"], "replay", now=NOW + timedelta(days=1))


async def test_real_mongo_concurrent_sequence_edit_publishes_one_pointer(mongo_db):
    await mongo_db.outreach_campaigns.insert_one({"id": "c", "workspace_id": "w", "status": "paused", "authorization_revision": 1})
    results = await asyncio.gather(*(publish_sequence(mongo_db, "w", "c", {"nodes": [{"id": str(n)}]}, expected_revision=1) for n in range(8)))
    assert sum(results) == 1
    assert (await load_sequence(mongo_db, "w", "c"))["version"] == 1
    assert (await mongo_db.outreach_campaigns.find_one({"id": "c"}))["authorization_revision"] == 2


async def test_real_mongo_manual_duplicate_workers_and_received_projection(mongo_db, monkeypatch):
    from tests.test_outreach_manual_actions import database
    from outreach.core import manual_actions as module
    from unittest.mock import AsyncMock
    for name, collection in database().collections.items():
        if collection.docs:
            await mongo_db[name].insert_many(collection.docs)
    service = module.ManualActions(mongo_db)
    await service.queue("j", "w", "a", "p", "engage", "like", {"reaction": "LIKE"}, "human")
    monkeypatch.setattr(module, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    transport = type("Client", (), {"like_update": AsyncMock(return_value={"status": "liked"})})()
    monkeypatch.setattr(service, "client", AsyncMock(return_value=transport))
    await asyncio.gather(*(service.run("w", "j") for _ in range(20)))
    assert transport.like_update.await_count == 1
    assert (await mongo_db.outreach_engage_posts.find_one({"id": "p"}))["reactions_count"] == 1
    assert (await mongo_db.outreach_manual_actions.find_one({"_id": "j"}))["status"] == "completed"


async def test_real_mongo_inbox_reply_slot_is_atomic_and_projection_preserves_revision(mongo_db):
    from tests.test_outreach_manual_actions import database
    from outreach.core.manual_actions import ManualActions
    from datetime import datetime, timezone
    for name, collection in database().collections.items():
        if collection.docs:
            await mongo_db[name].insert_many(collection.docs)
    service = ManualActions(mongo_db)
    results = await asyncio.gather(*(service.queue(f"j-{n}", "w", "a", "t", "inbox_reply", "reply", {"body": "Reviewed reply"}, "human") for n in range(16)), return_exceptions=True)
    jobs = [result for result in results if isinstance(result, dict)]
    assert len(jobs) == 1
    job = jobs[0]
    now = datetime.now(timezone.utc)
    job["stages"]["reply"] = {"status": "provider_accepted", "accepted_at": now, "provenance": "adapter_response"}
    await mongo_db.outreach_inbox_threads.update_one({"id": "t"}, {"$set": {"last_message_at": now + timedelta(seconds=1), "last_message_snippet": "Later inbound"}})
    await asyncio.gather(*(service.project(job) for _ in range(16)))
    thread = await mongo_db.outreach_inbox_threads.find_one({"id": "t"})
    assert len(thread["messages"]) == 1
    assert thread["thread_revision"] == 2
    assert thread["last_message_snippet"] == "Later inbound"
    stale_sync = await mongo_db.outreach_inbox_threads.update_one({"id": "t", "thread_revision": 1}, {"$set": {"messages": []}, "$inc": {"thread_revision": 1}})
    assert not stale_sync.matched_count


async def test_real_mongo_review_decisions_fence_concurrent_reviewers(mongo_db):
    from outreach.core.content_approval import ContentApproval
    from tests.test_outreach_content_approval import binding
    service = ContentApproval(mongo_db)
    record = await service.ensure(binding())
    results = await asyncio.gather(*(service.decide("w", record["_id"], f"human-{n}", "approve", revision=1) for n in range(16)), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert await service.allowed(binding())
    await service.decide("w", record["_id"], "human", "revoke", revision=2)
    assert not await service.authorize_submission(binding())


async def test_real_mongo_shared_physical_budget_caps_concurrent_workers(mongo_db):
    from outreach.core.request_guard import PhysicalBudget
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    budget = PhysicalBudget(mongo_db)
    config = {"request_budget": {"hourly_cap": 10, "daily_cap": 20, "reserved_hourly": 2, "reserved_daily": 2}}
    results = await asyncio.gather(*(budget.reserve("w", "a", "search", "read", config, now=now) for _ in range(32)))
    assert sum(item[0] for item in results) == 8
    assert (await budget.reserve("w", "a", "sync", "read", config, now=now))[0]
    assert (await budget.reserve("w", "a", "sync", "read", config, now=now))[0]
    assert not (await budget.reserve("w", "a", "sync", "read", config, now=now))[0]
    assert (await mongo_db.outreach_request_budgets.find_one({"workspace_id": "w"}))["hourly_total"] == 10


async def test_real_mongo_different_traffic_sources_share_one_owner(mongo_db, monkeypatch):
    from outreach.core import request_guard
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    from outreach.core.execution_permission import ExecutionPermission
    from unittest.mock import AsyncMock
    import httpx
    await mongo_db.outreach_accounts.insert_one({"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g", "proxy": {"host": "191.116.125.248"}})
    sources = ["sequence", "sync", "search", "inbox_reply", "engage"]
    await ExecutionPermission(mongo_db).grant("w", "a", "g", sources, "operator")
    monkeypatch.setattr(request_guard, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(request_guard, "is_shutting_down", lambda: False)
    monkeypatch.setattr(RequestEnvelope, "_proxy_matches", lambda *args: True)
    release = asyncio.Event()
    started = asyncio.Event()
    count = 0
    async def transport():
        nonlocal count
        count += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json={})
    async def request(source):
        try:
            await RequestEnvelope(mongo_db, "w", "a", "g", source, "http://proxy:8000").call("GET", "/search/blended", transport)
            return True
        except RequestDenied:
            return False
    tasks = [asyncio.create_task(request(source)) for source in sources]
    await asyncio.wait_for(started.wait(), timeout=3)
    await asyncio.sleep(0.05)
    release.set()
    assert sum(await asyncio.gather(*tasks)) == 1
    assert count == 1


async def test_real_mongo_permission_revoke_at_final_context_check_prevents_send(mongo_db, monkeypatch):
    from outreach.core import request_guard
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    from outreach.core.execution_permission import ExecutionPermission
    from unittest.mock import AsyncMock
    await mongo_db.outreach_accounts.insert_one({"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g", "proxy": {"host": "191.116.125.248"}})
    await ExecutionPermission(mongo_db).grant("w", "a", "g", ["sequence"], "operator")
    monkeypatch.setattr(request_guard, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(request_guard, "is_shutting_down", lambda: False)
    monkeypatch.setattr(RequestEnvelope, "_proxy_matches", lambda *args: True)
    monkeypatch.setattr(RequestEnvelope, "_validate_content", AsyncMock(return_value=None))
    monkeypatch.setattr(RequestEnvelope, "_authorize_content", AsyncMock(return_value=None))
    validate = RequestEnvelope._validate
    checks = 0
    async def validate_then_revoke(self, *args):
        nonlocal checks
        account = await validate(self, *args)
        checks += 1
        if checks == 3:
            await ExecutionPermission(mongo_db).revoke("w", "a", "operator", "stop")
        return account
    monkeypatch.setattr(RequestEnvelope, "_validate", validate_then_revoke)
    transport = AsyncMock()
    with pytest.raises(RequestDenied):
        await RequestEnvelope(mongo_db, "w", "a", "g", "sequence", "http://proxy:8000").call("POST", "/messaging/conversations", transport, action="message")
    transport.assert_not_awaited()
    assert (await mongo_db.outreach_request_budgets.find_one({"workspace_id": "w"}))["actions"]["message"] == 0
