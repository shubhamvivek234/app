"""Offline generation cannot authorize sending or silently repeat paid work."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation, publish_voice_jobs
from tests.test_outreach_execution_outbox import execution_db


@pytest.fixture
def voice_db(monkeypatch):
    from utils import encryption
    monkeypatch.setattr(encryption, "_fernet", Fernet(Fernet.generate_key()))
    monkeypatch.setenv("OUTREACH_VOICE_PREPARATION_ENABLED", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-offline-credential")
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    db = execution_db()
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"].update(type="voice_note", config={"script": "Hello {{first_name}}"})
    db.outreach_voices.docs.append({"id": "v", "workspace_id": "w", "elevenlabs_voice_id": "voice1", "assigned_account_ids": ["a"], "revision": 1})
    db.outreach_entitlements.docs.append({"_id": "paid", "workspace_id": "w", "status": "active", "is_revoked": False,
        "payment_source": "manual_verified_invoice", "paid_through": datetime.now(timezone.utc) + timedelta(days=1), "seats": 1})
    from outreach.core.voice_studio import source_digest
    db.outreach_voices.docs[0].update(status='active', provider_source_digest=source_digest(),
        consent={'version': 1, 'actor': 'human', 'asserted_at': datetime.now(timezone.utc), 'assertion_digest': 'recorded-test-consent'})
    db.workspace_members.docs.append({'workspace_id': 'w', 'user_id': 'human', 'role': 'owner'})
    return db


@pytest.mark.asyncio
async def test_queue_deduplicates_and_publishes_ids_only(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    assert (await service.queue("w", "l", "human"))["_id"] == job["_id"]
    publish = AsyncMock()
    assert await publish_voice_jobs(voice_db, publish) == 1
    publish.assert_awaited_once_with(job["_id"], "w")
    assert len(voice_db.outreach_voice_preparation_jobs.docs) == 1
    assert not voice_db.outreach_sender_execution.docs


@pytest.mark.asyncio
async def test_exact_clip_is_encrypted_pending_review_and_never_regenerated(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    audio = generate_mock_voice_wav()
    generator = AsyncMock(return_value=audio)
    assert (await service.run("w", job["_id"], generator=generator))["status"] == "prepared"
    assert (await service.run("w", job["_id"], generator=generator))["status"] == "prepared"
    generator.assert_awaited_once()
    artifact = voice_db.outreach_voice_artifacts.docs[0]
    assert await VoiceArtifacts(voice_db).load("w", artifact["_id"]) == audio
    assert audio.hex() not in str(artifact)
    review = voice_db.outreach_content_approvals.docs[0]
    assert review["status"] == "pending"
    assert review["binding"] == await sequence_binding(voice_db, "w", "l", voice_artifact=artifact)
    assert not await ContentApproval(voice_db).allowed(review["binding"])
    assert not voice_db.outreach_intents.docs
    assert not voice_db.outreach_execution_permissions.docs


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["recipient", "profile"])
async def test_recording_cannot_be_reviewed_for_another_current_context(voice_db, change):
    base = await sequence_binding(voice_db, "w", "l")
    artifact = await VoiceArtifacts(voice_db).store(base, generate_mock_voice_wav())
    if change == "recipient":
        voice_db.outreach_leads.docs[0]["linkedin_urn"] = "urn:li:person:replacement"
    else:
        voice_db.outreach_voices.docs[0]["revision"] = 2
    with pytest.raises(ValueError, match="recording context changed"):
        await sequence_binding(voice_db, "w", "l", voice_artifact=artifact)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["profile", "sender", "script", "recipient", "node"])
async def test_current_context_edit_discards_generated_audio(voice_db, change):
    job = await VoicePreparation(voice_db).queue("w", "l", "human")
    async def generate(_binding):
        if change == "profile": voice_db.outreach_voices.docs[0]["revision"] = 2
        elif change == "sender": voice_db.outreach_accounts.docs[0]["credential_generation"] = "new"
        elif change == "script": voice_db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["config"]["script"] = "New script"
        elif change == "recipient": voice_db.outreach_leads.docs[0]["linkedin_url"] = "https://linkedin.com/in/new"
        else: voice_db.outreach_leads.docs[0]["current_node_id"] = "gone"
        return generate_mock_voice_wav()
    assert (await VoicePreparation(voice_db).run("w", job["_id"], generator=generate))["status"] == "superseded"
    assert not voice_db.outreach_voice_artifacts.docs
    assert not voice_db.outreach_content_approvals.docs


@pytest.mark.asyncio
async def test_ambiguous_failure_and_worker_loss_are_held_without_replay(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    generator = AsyncMock(side_effect=TimeoutError("do not expose credentials or provider body"))
    assert (await service.run("w", job["_id"], generator=generator))["status"] == "held_outcome"
    assert (await service.queue("w", "l", "human"))["status"] == "held_outcome"
    await service.run("w", job["_id"], generator=generator)
    generator.assert_awaited_once()
    assert "credentials" not in str(voice_db.outreach_voice_preparation_jobs.docs)
    doc = voice_db.outreach_voice_preparation_jobs.docs[0]
    doc.update(status="generating", claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    await service.recover("w", job["_id"])
    assert doc["status"] == "held_outcome"


@pytest.mark.asyncio
async def test_duplicate_workers_have_one_paid_call(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    await asyncio.gather(*(service.run("w", job["_id"], generator=generator) for _ in range(5)))
    generator.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["disabled", "mock", "missing_voice", "unpaid"])
async def test_preparation_configuration_denies_before_queue(voice_db, monkeypatch, mode):
    if mode == "disabled": monkeypatch.setenv("OUTREACH_VOICE_PREPARATION_ENABLED", "false")
    elif mode == "mock": monkeypatch.setenv("ELEVENLABS_API_KEY", "mock")
    elif mode == "missing_voice": voice_db.outreach_voices.docs.clear()
    else: voice_db.outreach_entitlements.docs.clear()
    with pytest.raises(ValueError): await VoicePreparation(voice_db).queue("w", "l", "human")
    assert not voice_db.outreach_voice_preparation_jobs.docs


@pytest.mark.asyncio
async def test_broker_failure_keeps_due_job_and_recovery_only_reclaims_non_calls(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    assert await publish_voice_jobs(voice_db, AsyncMock(side_effect=RuntimeError("broker"))) == 0
    doc = voice_db.outreach_voice_preparation_jobs.docs[0]
    assert doc["status"] == "queued"
    doc.update(status="claimed", owner="old", claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    await service.recover("w", job["_id"])
    assert doc["status"] == "queued"


@pytest.mark.asyncio
async def test_daily_generation_cap_stops_before_provider(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    day = datetime.now(timezone.utc).date().isoformat()
    voice_db.outreach_voice_preparation_budgets.docs.append({"_id": "w:" + day, "workspace_id": "w", "day": day, "clips": 20, "chars": 20000})
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    assert (await service.run("w", job["_id"], generator=generator))["status"] == "budget_wait"
    generator.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_workspace_and_malformed_audio_never_create_review(voice_db):
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    generator = AsyncMock(return_value=b"not audio")
    assert (await service.run("other", job["_id"], generator=generator))["status"] == "missing"
    generator.assert_not_awaited()
    assert (await service.run("w", job["_id"], generator=generator))["status"] == "held_outcome"
    assert not voice_db.outreach_content_approvals.docs


@pytest.mark.asyncio
async def test_queue_api_is_offline_and_reports_hold_even_after_flag_disabled(voice_db, monkeypatch):
    from tests.test_outreach_content_approval_api import client
    provider = AsyncMock(side_effect=AssertionError("API must not call provider"))
    monkeypatch.setattr("outreach.core.voice_preparation.generate_campaign_voice", provider)
    api = client(voice_db)
    response = api.post("/content-approvals/prepare/c").json()
    assert response["voice_queued"] == response["voice_pending"] == 1
    provider.assert_not_awaited()
    voice_db.outreach_voice_preparation_jobs.docs[0]["status"] = "held_outcome"
    monkeypatch.setenv("OUTREACH_VOICE_PREPARATION_ENABLED", "false")
    assert api.post("/content-approvals/prepare/c").json()["voice_held"] == 1


@pytest.mark.asyncio
async def test_prepared_voice_waits_for_review_then_sends_exact_cached_bytes(voice_db, monkeypatch):
    from tests.test_outreach_execution_outbox import stub_transport
    service = VoicePreparation(voice_db)
    job = await service.queue("w", "l", "human")
    audio = generate_mock_voice_wav()
    provider = AsyncMock(return_value=audio)
    await service.run("w", job["_id"], generator=provider)
    executor, transport = stub_transport(monkeypatch, review_content=True)
    transport.send_voice_note = AsyncMock(return_value={"status": "voice_note_sent"})
    assert (await executor.SequenceExecutor.execute_lead_step("l", voice_db, workspace_id="w"))["status"] == "content_approval_required"
    transport.send_voice_note.assert_not_awaited()
    review = voice_db.outreach_content_approvals.docs[0]
    await ContentApproval(voice_db).decide("w", review["_id"], "human", "approve", revision=1)
    voice_db.outreach_intents.docs[0]["next_action_due_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await executor.SequenceExecutor.execute_lead_step("l", voice_db, workspace_id="w"))["status"] == "success"
    assert transport.send_voice_note.await_args.kwargs["audio_bytes"] == audio
    provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_shutdown_and_media_queue_ids_only(voice_db, monkeypatch):
    from celery_workers.tasks import voice_preparation as worker
    sent = []
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker.prepare, "apply_async", lambda **kwargs: sent.append(kwargs))
    job = await VoicePreparation(voice_db).queue("w", "l", "human")
    assert (await worker._publish(voice_db))["published"] == 1
    assert sent == [{"args": [job["_id"], "w"], "queue": "media_processing"}]
    monkeypatch.setattr(worker, "is_shutting_down", lambda: True)
    assert (await worker._prepare(job["_id"], "w", voice_db))["status"] == "shutting_down"
    assert (await worker._publish(voice_db))["status"] == "shutting_down"


@pytest.mark.asyncio
async def test_worker_database_adapter_completion_and_closed_workspace(voice_db, monkeypatch):
    from celery_workers.tasks import voice_preparation as worker
    from outreach.core.suppression import SuppressionUnavailable
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "get_client", AsyncMock(return_value={"voice-test": voice_db}))
    monkeypatch.setenv("DB_NAME", "voice-test")
    assert await worker._database() is voice_db
    job = await VoicePreparation(voice_db).queue("w", "l", "human")
    monkeypatch.setattr("outreach.core.voice_preparation.generate_campaign_voice", AsyncMock(return_value=generate_mock_voice_wav()))
    assert (await worker._prepare(job["_id"], "w"))["status"] == "prepared"
    monkeypatch.setattr(worker.VoicePreparation, "run", AsyncMock(side_effect=SuppressionUnavailable("closed")))
    assert (await worker._prepare(job["_id"], "w", voice_db))["status"] == "workspace_unavailable"


def test_celery_entry_points_observe_shutdown_and_delegate(monkeypatch):
    from celery_workers.tasks import voice_preparation as worker
    monkeypatch.setattr(worker, "is_shutting_down", lambda: True)
    assert worker.prepare.run("id", "w")["status"] == "shutting_down"
    assert worker.publish.run()["status"] == "shutting_down"
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    def execute(coroutine):
        coroutine.close()
        return {"status": "delegated"}
    monkeypatch.setattr(worker, "run_async", execute)
    assert worker.prepare.run("id", "w")["status"] == "delegated"
    assert worker.publish.run()["status"] == "delegated"


@pytest.mark.asyncio
async def test_voice_profile_crud_is_scoped_and_provider_failure_preserves_record(voice_db, monkeypatch):
    from fastapi import HTTPException
    from outreach.api.voice import delete_voice, assign_voice, list_voices, AssignVoiceRequest
    from outreach.core.voice_studio import VoiceStudio
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'true')
    user = {'user_id': 'human', 'default_workspace_id': 'w'}
    await voice_db.outreach_voices.insert_one({'id': 'other', 'workspace_id': 'elsewhere', 'elevenlabs_voice_id': 'outside'})
    assert (await list_voices(user, voice_db))['used_count'] == 1
    with pytest.raises(HTTPException):
        await delete_voice('other', 'delete-other', user, voice_db)
    with pytest.raises(HTTPException):
        await assign_voice('other', AssignVoiceRequest(account_ids=['a'], revision=1), user, voice_db)
    await assign_voice('v', AssignVoiceRequest(account_ids=['a'], revision=1), user, voice_db)
    job = await delete_voice('v', 'delete-test', user, voice_db)
    assert job['status'] == 'queued' and voice_db.outreach_voices.docs[0]['status'] == 'deleting'
    result = await VoiceStudio(voice_db).run('w', job['_id'], provider=AsyncMock(return_value={'deleted': False}))
    assert result['status'] == 'held_outcome'
    assert voice_db.outreach_voices.docs[0]['id'] == 'v'


@pytest.mark.asyncio
async def test_bad_encryption_and_expired_owner_deny_new_recording(voice_db, monkeypatch):
    service = VoicePreparation(voice_db)
    check = AsyncMock(return_value=generate_mock_voice_wav())
    monkeypatch.setattr("outreach.core.voice_preparation.validate_encryption_key", lambda: (_ for _ in ()).throw(ValueError("bad key")))
    with pytest.raises(ValueError, match="encrypted storage"): await service.queue("w", "l", "human")
    assert not voice_db.outreach_voice_preparation_jobs.docs
    monkeypatch.setattr("outreach.core.voice_preparation.validate_encryption_key", lambda: None)
    job = await service.queue("w", "l", "human")
    async def expire_owner(_binding):
        voice_db.outreach_voice_preparation_jobs.docs[0]["claim_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        return await check()
    assert (await service.run("w", job["_id"], generator=expire_owner))["status"] == "owner_changed"
    await service.recover("w", job["_id"])
    assert voice_db.outreach_voice_preparation_jobs.docs[0]["status"] == "held_outcome"
    assert "binding" not in voice_db.outreach_voice_preparation_jobs.docs[0]
    assert not voice_db.outreach_voice_artifacts.docs
