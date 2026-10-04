"""Real transaction/recovery checks on a disposable loopback replica set."""
import asyncio
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from outreach.core import suppression
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.erasure import OutreachErasure
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation, publish_voice_jobs, utcnow
from tests.test_outreach_voice_preparation import voice_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable local replica set is opt-in")]


@pytest_asyncio.fixture
async def real_voice_db(voice_db):
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    name = "test_unravler_voice_" + uuid.uuid4().hex
    db = client[name]
    for collection, source in voice_db.collections.items():
        if source.docs: await db[collection].insert_many(source.docs)
    try:
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def test_real_duplicate_queue_worker_and_repeated_prepare_use_one_call(real_voice_db):
    db = real_voice_db
    service = VoicePreparation(db)
    jobs = await asyncio.gather(*(service.queue("w", "l", "human") for _ in range(8)))
    assert len({job["_id"] for job in jobs}) == 1
    generate = AsyncMock(return_value=generate_mock_voice_wav())
    await asyncio.gather(*(service.run("w", jobs[0]["_id"], generator=generate) for _ in range(6)))
    generate.assert_awaited_once()
    job = await service.queue("w", "l", "human")
    assert job["status"] == "prepared"
    artifact = await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})
    binding = await sequence_binding(db, "w", "l", voice_artifact=artifact)
    async def ensure(current):
        return await ContentApproval(current).ensure(binding)
    first = await suppression.mutate_suppression(db, "w", ensure)
    second = await suppression.mutate_suppression(db, "w", ensure)
    assert first["_id"] == second["_id"]
    await ContentApproval(db).decide("w", first["_id"], "human", "approve", revision=1)
    await db.outreach_voice_artifacts.update_one({"_id": artifact["_id"]}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}})
    fresh = await service.queue("w", "l", "human")
    assert fresh["status"] == "queued"
    assert (await service.run("w", fresh["_id"], generator=generate))["status"] == "prepared"
    assert generate.await_count == 2
    assert await db.outreach_content_approvals.count_documents({"workspace_id": "w"}) == 2
    current_artifact = await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})
    current_binding = await sequence_binding(db, "w", "l", voice_artifact=current_artifact)
    assert current_binding != binding
    assert not await ContentApproval(db).allowed(current_binding)


@pytest.mark.parametrize("stage", ["before_call", "after_call"])
async def test_real_erasure_orders_before_call_or_blocks_final_clip(real_voice_db, stage):
    db = real_voice_db
    service = VoicePreparation(db)
    job = await service.queue("w", "l", "human")
    async def close():
        async def stop(current):
            await current.outreach_suppression_guards.update_one(suppression.guard_scope("w"), {"$set": {"erasure_state": "requested"}})
        await suppression.mutate_suppression(db, "w", stop)
    generate = AsyncMock(return_value=generate_mock_voice_wav())
    if stage == "before_call": await close()
    else:
        async def generate_and_close(_binding):
            await close()
            return generate_mock_voice_wav()
        generate = AsyncMock(side_effect=generate_and_close)
    with pytest.raises(suppression.SuppressionUnavailable):
        await service.run("w", job["_id"], generator=generate)
    assert generate.await_count == (0 if stage == "before_call" else 1)
    assert not await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})
    assert not await db.outreach_content_approvals.find_one({"workspace_id": "w"})


@pytest.mark.parametrize("authority", ["profile", "paid", "sender", "lead"])
async def test_real_edit_after_snapshot_read_retries_and_denies_provider(real_voice_db, monkeypatch, authority):
    from outreach.core.dispatch_authority import AuthorityCollection
    db = real_voice_db
    service = VoicePreparation(db)
    job = await service.queue("w", "l", "human")
    original = AuthorityCollection.fence
    target = {"profile": "outreach_voices", "paid": "outreach_entitlements", "sender": "outreach_accounts", "lead": "outreach_leads"}[authority]
    seen, release = asyncio.Event(), asyncio.Event()
    paused = False
    async def pause(self, document, query):
        nonlocal paused
        if self.name == target and not paused:
            paused = True
            seen.set()
            await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, "fence", pause)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    running = asyncio.create_task(service.run("w", job["_id"], generator=generator))
    await asyncio.wait_for(seen.wait(), 5)
    edits = {"profile": {"revision": 2}, "paid": {"is_revoked": True},
        "sender": {"credential_generation": "new"}, "lead": {"execution_state": "replied"}}
    await db[target].update_one({"workspace_id": "w"}, {"$set": edits[authority]})
    release.set()
    assert (await running)["status"] in {"blocked", "superseded"}
    generator.assert_not_awaited()
    assert not await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})


async def test_real_final_projection_failure_rolls_back_and_never_replays(real_voice_db, monkeypatch):
    db = real_voice_db
    service = VoicePreparation(db)
    job = await service.queue("w", "l", "human")
    generate = AsyncMock(return_value=generate_mock_voice_wav())
    original = ContentApproval.ensure
    monkeypatch.setattr(ContentApproval, "ensure", AsyncMock(side_effect=RuntimeError("projection interrupted")))
    with pytest.raises(RuntimeError): await service.run("w", job["_id"], generator=generate)
    assert not await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})
    monkeypatch.setattr(ContentApproval, "ensure", original)
    await db.outreach_voice_preparation_jobs.update_one({"_id": job["_id"]}, {"$set": {"claim_expires_at": utcnow() - timedelta(seconds=1)}})
    assert (await service.run("w", job["_id"], generator=generate))["status"] == "held_outcome"
    generate.assert_awaited_once()


async def test_real_budget_limits_concurrent_different_leads(real_voice_db):
    db = real_voice_db
    base = await db.outreach_leads.find_one({"workspace_id": "w"})
    await db.outreach_leads.insert_many([{**{k: v for k, v in base.items() if k != "_id"}, "id": "l" + str(i)} for i in range(3)])
    day = utcnow().date().isoformat()
    await db.outreach_voice_preparation_budgets.insert_one({"_id": "w:" + day, "workspace_id": "w", "clips": 19, "chars": 19000})
    service = VoicePreparation(db)
    jobs = [await service.queue("w", "l" + str(i), "human") for i in range(3)]
    generate = AsyncMock(return_value=generate_mock_voice_wav())
    results = await asyncio.gather(*(service.run("w", job["_id"], generator=generate) for job in jobs))
    assert sorted(result["status"] for result in results) == ["budget_wait", "budget_wait", "prepared"]
    generate.assert_awaited_once()
    assert (await db.outreach_voice_preparation_budgets.find_one({"workspace_id": "w"}))["clips"] == 20


async def test_real_voice_uncertainty_retention_keeps_no_script_or_audio(real_voice_db):
    db = real_voice_db
    service = VoicePreparation(db)
    job = await service.queue("w", "l", "human")
    await service.run("w", job["_id"], generator=AsyncMock(side_effect=TimeoutError()))
    row = await db.outreach_voice_preparation_jobs.find_one({"workspace_id": "w"})
    async def retain(current):
        await OutreachErasure(db)._archive(current, "outreach_voice_preparation_jobs", "w", row)
    await suppression.mutate_suppression(db, "w", retain)
    hold = await db.outreach_erasure_holds.find_one({"workspace_id": "w"})
    assert hold["kind"] == "unresolved_submission"
    assert hold["outcome_state"] == "held_outcome"
    assert "Hello" not in str(hold) and "audio_enc" not in hold and "binding" not in hold


async def test_real_closed_prefix_cannot_starve_open_worker_recovery(real_voice_db):
    db = real_voice_db
    now = utcnow()
    for i in range(3):
        ws = "closed" + str(i)
        await db.outreach_suppression_guards.insert_one({**suppression.guard_scope(ws), "erasure_state": "requested"})
        await db.outreach_voice_preparation_jobs.insert_one({"_id": "closed" + str(i), "workspace_id": ws, "status": "generating",
            "owner": "old", "claim_expires_at": now - timedelta(minutes=5)})
    job = await VoicePreparation(db).queue("w", "l", "human")
    await db.outreach_voice_preparation_jobs.update_one({"_id": job["_id"]}, {"$set": {"status": "claimed", "owner": "old",
        "claim_expires_at": now - timedelta(minutes=1)}})
    publisher = AsyncMock()
    await publish_voice_jobs(db, publisher, limit=2)
    await publish_voice_jobs(db, publisher, limit=2)
    assert (await db.outreach_voice_preparation_jobs.find_one({"_id": job["_id"]}))["status"] == "queued"
    publisher.assert_awaited_once_with(job["_id"], "w")
    for i in range(3):
        row = await db.outreach_voice_preparation_jobs.find_one({"_id": "closed" + str(i)})
        assert row["status"] == "generating" and row["owner"] == "old"
        assert row["next_recovery_due_at"] > now


@pytest.mark.parametrize("edit", ["none", "profile", "audio_generation", "audio_expiry", "recipient", "message_recipient"])
async def test_real_voice_dispatch_final_fence_checks_current_reviewed_recording(real_voice_db, monkeypatch, edit):
    import httpx
    from utils.encryption import encrypt
    from outreach.core.dispatch_authority import AuthorityCollection
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.tasks import sequence_dispatch
    from outreach.engine.voyager_client import VoyagerClient
    db = real_voice_db
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    await db.outreach_campaigns.update_one({"id": "c"}, {"$set": {"schedule": {
        "timezone": "UTC", "start_time": "00:00", "end_time": "23:59", "days": [0, 1, 2, 3, 4, 5, 6]}}})
    await db.outreach_accounts.update_one({"id": "a"}, {"$set": {"country_code": "US", "session_cookie_enc": encrypt("local-only-session"),
        "jsession_id": "ajax:local", "proxy": {"proxy_id": "local-ip", "host": "127.0.0.1", "port": 9,
            "username": "local", "password_enc": encrypt("local-only-password")}}})
    await db.outreach_sender_slots.insert_one({"workspace_id": "w", "sender_id": "a"})
    await db.outreach_proxy_leases.insert_one({"_id": "local-ip", "workspace_id": "w", "sender_id": "a"})
    await db.outreach_proxy_inventory.insert_one({"_id": "local-ip", "workspace_id": "w", "last_workspace_id": "w",
        "country_code": "US", "status": "available", "provider": "iproyal_static", "expires_at": utcnow() + timedelta(days=1)})
    await ExecutionPermission(db).grant("w", "a", "g", ["sequence"], "local-reviewer")
    audio = generate_mock_voice_wav()
    if edit == "message_recipient":
        await db.outreach_sequences.update_one({"campaign_id": "c"}, {"$set": {
            "compiled_dag.nodes.n.type": "send_message", "compiled_dag.nodes.n.config": {"body": "Hello"}}})
        review = await ContentApproval(db).ensure(await sequence_binding(db, "w", "l"))
    else:
        job = await VoicePreparation(db).queue("w", "l", "human")
        await VoicePreparation(db).run("w", job["_id"], generator=AsyncMock(return_value=audio))
        review = await db.outreach_content_approvals.find_one({"workspace_id": "w"})
    await ContentApproval(db).decide("w", review["_id"], "human", "approve", revision=1)
    if edit in {"recipient", "message_recipient"}:
        from copy import deepcopy
        # Model an older approved record: both recipient choices already have
        # approvals, so the final callback must match the captured one exactly.
        changed = deepcopy(review["binding"])
        changed["recipient"] = "urn:li:person:replacement"
        alternate = await ContentApproval(db).ensure(changed)
        await ContentApproval(db).decide("w", alternate["_id"], "human", "approve", revision=1)
    calls = []
    original_client = httpx.AsyncClient
    def make_client(**kwargs):
        kwargs.pop("proxy", None)  # Test-only; production must use its approved proxy.
        return original_client(**kwargs, transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(201, json={"entityUrn": "urn:local:message"}))[1]))
    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    monkeypatch.setattr(VoyagerClient, "_resolve_profile_urn", AsyncMock(return_value="urn:li:fsd_profile:person"))
    original = AuthorityCollection.fence
    seen, release = asyncio.Event(), asyncio.Event()
    paused = False
    async def pause(self, document, query):
        nonlocal paused
        target = ("outreach_leads" if edit in {"recipient", "message_recipient"}
            else "outreach_voices" if edit == "profile" else "outreach_voice_artifacts")
        if edit != "none" and self.name == target and not paused:
            paused = True
            seen.set()
            await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, "fence", pause)
    assert (await sequence_dispatch.prepare_due(db))["prepared"] == 1
    sequence_job = await db.outreach_sequence_jobs.find_one({"workspace_id": "w"})
    running = asyncio.create_task(sequence_dispatch.execute_job(db, "w", sequence_job["_id"]))
    if edit != "none":
        await asyncio.wait_for(seen.wait(), 5)
        collection = ("outreach_leads" if edit in {"recipient", "message_recipient"}
            else "outreach_voices" if edit == "profile" else "outreach_voice_artifacts")
        changes = {"profile": {"revision": 2}, "audio_generation": {"generation_id": "replacement"},
            "audio_expiry": {"expires_at": utcnow() - timedelta(seconds=1)},
            "recipient": {"linkedin_urn": "urn:li:person:replacement"},
            "message_recipient": {"linkedin_urn": "urn:li:person:replacement"}}
        await db[collection].update_one({"workspace_id": "w"}, {"$set": changes[edit]})
        release.set()
    result = await running
    assert len(calls) == (1 if edit == "none" else 0), result
    if edit == "none":
        assert result["status"] == "success"
        assert audio in calls[0].content
    else:
        assert result["status"] in {"content_changed", "content_approval_required"} and result["not_submitted"]
