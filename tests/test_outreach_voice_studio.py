"""Voice Studio consent, bounded offline work and conservative provider recovery."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from tests.outreach_memory import Database
from outreach.core.voice_cloner import generate_mock_voice_wav


@pytest.fixture
def studio_db(monkeypatch):
    from utils import encryption
    monkeypatch.setattr(encryption, "_fernet", Fernet(Fernet.generate_key()))
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    monkeypatch.setenv("OUTREACH_VOICE_STUDIO_ENABLED", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "local-provider-key")
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    return Database(workspace_members=[{"workspace_id": "w", "user_id": "actor", "role": "owner"}],
        outreach_entitlements=[{"workspace_id": "w", "status": "active", "seats": 1,
            "payment_source": "manual_verified_invoice", "paid_through": datetime.now(timezone.utc) + timedelta(days=1)}])


async def clone(service, request="request-1"):
    job = await service.queue("w", "actor", "clone", request, name="My voice",
        audio=generate_mock_voice_wav(duration_s=20), consent=True)
    return next(row for row in service.db.outreach_voice_studio_jobs.docs if row["_id"] == job["_id"])


@pytest.mark.asyncio
async def test_clone_is_durable_encrypted_and_requires_consent(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db)
    with pytest.raises(ValueError):
        await service.queue("w", "actor", "clone", "request-1", name="voice",
            audio=generate_mock_voice_wav(duration_s=20), consent=False)
    assert not studio_db.outreach_voice_studio_jobs.docs
    job = await clone(service)
    assert job["status"] == "queued" and job["input_enc"]
    assert job["consent"]["actor"] == "actor" and job["consent"]["version"] == 1
    assert studio_db.outreach_voices.docs[0]["status"] == "creating"
    assert (await clone(service))["_id"] == job["_id"]
    assert len(studio_db.outreach_voices.docs) == 1
    with pytest.raises(ValueError):
        await service.queue("w", "actor", "clone", "request-1", name="changed",
            audio=generate_mock_voice_wav(duration_s=20), consent=True)


@pytest.mark.asyncio
async def test_received_clone_installs_once_and_never_replays(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    provider = AsyncMock(return_value={"voice_id": "provider_voice"})
    assert (await service.run("w", job["_id"], provider=provider))["status"] == "completed"
    profile = studio_db.outreach_voices.docs[0]
    assert profile["status"] == "active" and profile["elevenlabs_voice_id"] == "provider_voice"
    assert profile["consent"]["actor"] == "actor"
    assert not job.get("input_enc") and not profile.get("studio_job_id")
    assert (await service.run("w", job["_id"], provider=provider))["status"] == "completed"
    provider.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "cancel", "bad_result"])
async def test_possible_clone_is_held_and_not_replayed(studio_db, failure):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    provider = AsyncMock(return_value={"voice_id": None})
    if failure == "timeout": provider.side_effect = TimeoutError("private provider failure")
    if failure == "cancel": provider.side_effect = asyncio.CancelledError()
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError): await service.run("w", job["_id"], provider=provider)
    else:
        assert (await service.run("w", job["_id"], provider=provider))["status"] == "held_outcome"
    job["lease_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    await service.recover("w", job["_id"])
    assert job["status"] == "held_outcome"
    assert not job.get("input_enc")
    await service.run("w", job["_id"], provider=provider)
    provider.assert_awaited_once()
    with pytest.raises(ValueError): await service.cancel("w", job["_id"], "actor")
    assert "private provider failure" not in str(job)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["flag", "key", "role", "paid", "profile"])
async def test_change_during_input_open_prevents_provider(studio_db, monkeypatch, change):
    from outreach.core import voice_studio as module
    service = module.VoiceStudio(studio_db); job = await clone(service)
    opening = module.open_blob
    async def changed(*args):
        result = await opening(*args)
        if change == "flag": monkeypatch.setenv("OUTREACH_VOICE_STUDIO_ENABLED", "false")
        if change == "key": monkeypatch.setenv("ELEVENLABS_API_KEY", "replacement")
        if change == "role": studio_db.workspace_members.docs[0]["role"] = "viewer"
        if change == "paid": studio_db.outreach_entitlements.docs.clear()
        if change == "profile": studio_db.outreach_voices.docs[0]["revision"] += 1
        return result
    monkeypatch.setattr(module, "open_blob", changed)
    provider = AsyncMock(return_value={"voice_id": "provider_voice"})
    await service.run("w", job["_id"], provider=provider)
    provider.assert_not_awaited()
    assert job["status"] == "stopped"


@pytest.mark.asyncio
async def test_quota_counts_pending_and_unknown_clones(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db)
    for number in range(5): await clone(service, f"request-{number}")
    with pytest.raises(ValueError): await clone(service, "request-extra")
    job = studio_db.outreach_voice_studio_jobs.docs[0]
    await service.cancel("w", job["_id"], "actor")
    assert len(studio_db.outreach_voices.docs) == 4
    await clone(service, "request-extra")


@pytest.mark.asyncio
async def test_preview_requires_local_profile_consent_and_returns_saved_audio(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run("w", job["_id"], provider=AsyncMock(return_value={"voice_id": "provider_voice"}))
    profile = studio_db.outreach_voices.docs[0]
    with pytest.raises(ValueError):
        await service.queue("w", "actor", "preview", "preview-1", voice_id="provider_voice", script="Hello")
    preview = await service.queue("w", "actor", "preview", "preview-1", voice_id=profile["id"], script="Hello")
    audio = generate_mock_voice_wav()
    provider = AsyncMock(return_value={"audio": audio})
    assert (await service.run("w", preview["_id"], provider=provider))["status"] == "completed"
    assert await service.preview("w", preview["_id"], "actor") == audio
    await service.run("w", preview["_id"], provider=provider)
    provider.assert_awaited_once()
    with pytest.raises(ValueError): await service.preview("other", preview["_id"], "actor")


@pytest.mark.asyncio
async def test_delete_pauses_use_and_removes_only_matching_profile(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run("w", job["_id"], provider=AsyncMock(return_value={"voice_id": "provider_voice"}))
    profile = studio_db.outreach_voices.docs[0]
    deletion = await service.queue("w", "actor", "delete", "delete-1", voice_id=profile["id"])
    assert profile["status"] == "deleting"
    assert (await service.run("w", deletion["_id"], provider=AsyncMock(return_value={"deleted": True})))["status"] == "completed"
    assert not studio_db.outreach_voices.docs


@pytest.mark.asyncio
async def test_cancel_delete_restores_local_use_with_new_revision(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run("w", job["_id"], provider=AsyncMock(return_value={"voice_id": "provider_voice"}))
    profile = studio_db.outreach_voices.docs[0]; revision = profile["revision"]
    deletion = await service.queue("w", "actor", "delete", "delete-1", voice_id=profile["id"])
    await service.cancel("w", deletion["_id"], "actor")
    assert profile["status"] == "active" and profile["revision"] > revision


@pytest.mark.asyncio
async def test_publication_is_fair_and_reference_only_even_when_broker_fails(studio_db):
    from outreach.core.voice_studio import VoiceStudio, publish_studio_jobs
    service = VoiceStudio(studio_db); job = await clone(service)
    publish = AsyncMock(side_effect=RuntimeError("private broker failure"))
    assert await publish_studio_jobs(studio_db, publish) == 0
    publish.assert_awaited_once_with(job["_id"], "w")
    assert job["status"] == "queued" and job["next_publish_at"] > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_recording_format_and_size_fail_before_storage(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db)
    for audio in (b"not-a-wav", generate_mock_voice_wav(), b"x" * 2000001):
        with pytest.raises(ValueError):
            await service.queue("w", "actor", "clone", "request-1", name="voice", audio=audio, consent=True)
    assert not studio_db.outreach_voice_studio_jobs.docs

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['paid', 'role', 'profile', 'key'])
async def test_known_receipt_survives_authority_loss_without_replay(studio_db, monkeypatch, change):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    async def provider(_request):
        if change == 'paid': studio_db.outreach_entitlements.docs.clear()
        if change == 'role': studio_db.workspace_members.docs[0]['role'] = 'viewer'
        if change == 'profile': studio_db.outreach_voices.docs[0]['revision'] += 1
        if change == 'key': monkeypatch.setenv('ELEVENLABS_API_KEY', 'replacement')
        return {'voice_id': 'remote'}
    call = AsyncMock(side_effect=provider)
    result = await service.run('w', job['_id'], provider=call)
    assert result['status'] == 'held_received' and result['receipt']['voice_id'] == 'remote'
    assert not result.get('input_enc')
    await service.run('w', job['_id'], provider=call)
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_required_profile_cannot_be_used(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote', 'requires_verification': True}))
    profile = studio_db.outreach_voices.docs[0]
    assert profile['status'] == 'needs_vendor_verification'
    with pytest.raises(ValueError): await service.queue('w', 'actor', 'preview', 'preview-new', voice_id=profile['id'], script='Hello')


@pytest.mark.asyncio
async def test_consent_revocation_blocks_preview_and_keeps_cleanup_available(studio_db):
    from outreach.api.voice import update_consent, ConsentRequest
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = studio_db.outreach_voices.docs[0]
    await update_consent(profile['id'], ConsentRequest(consent=False), {'user_id': 'actor', 'default_workspace_id': 'w'}, studio_db)
    with pytest.raises(ValueError): await service.queue('w', 'actor', 'preview', 'preview-new', voice_id=profile['id'], script='Hello')
    deletion = await service.queue('w', 'actor', 'delete', 'delete-new', voice_id=profile['id'])
    await service.cancel('w', deletion['_id'], 'actor')
    assert profile['status'] == 'consent_revoked'


@pytest.mark.asyncio
async def test_daily_budget_and_content_cleanup_do_not_drop_evidence(studio_db):
    from outreach.core.voice_studio import VoiceStudio, publish_studio_jobs
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = studio_db.outreach_voices.docs[0]
    preview = await service.queue('w', 'actor', 'preview', 'preview-new', voice_id=profile['id'], script='Hello')
    await service.run('w', preview['_id'], provider=AsyncMock(return_value={'audio': generate_mock_voice_wav()}))
    saved = studio_db.outreach_voice_studio_jobs.docs[-1]
    saved['result_expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    await publish_studio_jobs(studio_db, AsyncMock())
    assert not saved.get('result_enc') and saved['receipt']['audio_digest']
    studio_db.outreach_voice_studio_budgets.docs[-1]['calls'] = 20
    another = await service.queue('w', 'actor', 'preview', 'preview-next', voice_id=profile['id'], script='Hi')
    provider = AsyncMock()
    assert (await service.run('w', another['_id'], provider=provider))['status'] == 'stopped'
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_preparing_and_queued_are_stopped_with_flags_off(studio_db, monkeypatch):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    job.update(status='preparing', owner='old', lease_until=datetime.now(timezone.utc)-timedelta(seconds=1))
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'false')
    await service.recover('w', job['_id'])
    assert job['status'] == 'stopped' and not job.get('input_enc')
    assert not studio_db.outreach_voices.docs

@pytest.mark.asyncio
async def test_key_snapshot_cannot_mix_source_proof(studio_db, monkeypatch):
    from outreach.core import voice_studio
    service = voice_studio.VoiceStudio(studio_db)
    original_access, seal = service._access, voice_studio.seal_blob
    async def rotate(*args):
        expiry = await original_access(*args)
        monkeypatch.setenv('ELEVENLABS_API_KEY', 'replacement')
        return expiry
    async def restore(*args):
        monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-provider-key')
        return await seal(*args)
    monkeypatch.setattr(service, '_access', rotate)
    monkeypatch.setattr(voice_studio, 'seal_blob', restore)
    with pytest.raises(ValueError): await clone(service)
    assert not studio_db.outreach_voice_studio_jobs.docs


@pytest.mark.asyncio
async def test_preview_ciphertext_must_match_audio_receipt(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    from outreach.core.voice_studio_custody import seal_blob
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = studio_db.outreach_voices.docs[0]
    preview = await service.queue('w', 'actor', 'preview', 'preview-bad', voice_id=profile['id'], script='Hi')
    await service.run('w', preview['_id'], provider=AsyncMock(return_value={'audio': generate_mock_voice_wav()}))
    stored = studio_db.outreach_voice_studio_jobs.docs[-1]
    for replacement in (b'not-a-wav', generate_mock_voice_wav(duration_s=2)):
        stored['result_enc'] = await seal_blob(replacement, stored, 'result')
        with pytest.raises(ValueError): await service.preview('w', stored['_id'], 'actor')


@pytest.mark.asyncio
async def test_worker_result_contains_only_reference_and_status(studio_db, monkeypatch):
    from celery_workers.tasks import voice_studio as worker
    monkeypatch.setattr(worker, 'is_shutting_down', lambda: False)
    monkeypatch.setattr(worker.VoiceStudio, 'run', AsyncMock(return_value={'status': 'completed',
        'input_enc': 'private', 'result_enc': 'private', 'receipt': {'voice_id': 'private'}, 'actor': 'private'}))
    assert await worker._prepare('job', 'w', studio_db) == {'status': 'completed', 'job_id': 'job'}

@pytest.mark.asyncio
async def test_consent_withdrawal_is_allowed_with_unknown_preview(studio_db):
    from outreach.api.voice import update_consent, ConsentRequest
    from outreach.core.voice_studio import VoiceStudio, require_profile
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = studio_db.outreach_voices.docs[0]
    preview = await service.queue('w', 'actor', 'preview', 'preview-hold', voice_id=profile['id'], script='Hi')
    await service.run('w', preview['_id'], provider=AsyncMock(side_effect=TimeoutError()))
    await update_consent(profile['id'], ConsentRequest(consent=False), {'user_id': 'actor', 'default_workspace_id': 'w'}, studio_db)
    assert profile['status'] == 'consent_revoked' and profile['studio_job_id'] == preview['_id']
    with pytest.raises(ValueError): require_profile(profile)
    assert studio_db.outreach_voice_studio_jobs.docs[-1]['status'] == 'held_outcome'

@pytest.mark.asyncio
async def test_non_call_cleanup_does_not_delete_replacement_remote_profile(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    studio_db.outreach_voices.docs[0]['elevenlabs_voice_id'] = 'replacement-remote'
    await service.cancel('w', job['_id'], 'actor')
    assert studio_db.outreach_voices.docs[0]['elevenlabs_voice_id'] == 'replacement-remote'
    assert job['status'] == 'cancelled' and job['error_code'] == 'profile_cleanup_needs_review'

@pytest.mark.asyncio
async def test_known_preview_receipt_survives_content_custody_failure(studio_db, monkeypatch):
    from outreach.core import voice_studio
    service = voice_studio.VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
    profile = studio_db.outreach_voices.docs[0]
    preview = await service.queue('w', 'actor', 'preview', 'preview-kms', voice_id=profile['id'], script='Hi')
    monkeypatch.setattr(voice_studio, 'seal_blob', AsyncMock(side_effect=RuntimeError('private custody details')))
    provider = AsyncMock(return_value={'audio': generate_mock_voice_wav()})
    result = await service.run('w', preview['_id'], provider=provider)
    assert result['status'] == 'held_received' and result['receipt']['audio_digest']
    assert result['receipt']['received_at'] and not result.get('result_enc')
    assert not result.get('input_enc') and 'private custody details' not in str(result)
    await service.run('w', preview['_id'], provider=provider)
    provider.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('declared', ['3000000', None])
async def test_clone_ingress_is_bounded_before_multipart_parsing(declared):
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.responses import Response
    from fastapi import HTTPException
    from outreach.api.voice import StudioRoute
    async def endpoint(): return Response()
    route = StudioRoute('/voice/clone', endpoint, methods=['POST'])
    messages = [{'type': 'http.request', 'body': b'x' * 1500000, 'more_body': True},
        {'type': 'http.request', 'body': b'x' * 1500000, 'more_body': False}]
    # Exercise the bound independently of a parser accepting/rejecting malformed data.
    from unittest.mock import patch
    from fastapi.routing import APIRoute
    async def consume(request):
        async for _part in request.stream(): pass
        return Response()
    with patch.object(APIRoute, 'get_route_handler', return_value=consume):
        handler = route.get_route_handler()
    headers = [(b'content-length', declared.encode())] if declared else []
    async def receive(): return messages.pop(0)
    with pytest.raises(HTTPException) as error:
        await handler(Request({'type': 'http', 'method': 'POST', 'path': '/voice/clone', 'headers': headers}, receive))
    assert error.value.status_code == 413
    if declared: assert len(messages) == 2


def test_actual_multipart_clone_route_queues_without_provider(studio_db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.deps import get_current_user
    from db.mongo import get_db
    from outreach.api.voice import router
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 'actor', 'default_workspace_id': 'w'}
    app.dependency_overrides[get_db] = lambda: studio_db
    with TestClient(app) as api:
        response = api.post('/voice/clone', data={'name': 'My voice', 'consent': 'true', 'request_id': 'router-clone'},
            files={'file': ('sample.wav', generate_mock_voice_wav(duration_s=20), 'audio/wav')})
    assert response.status_code == 202
    assert response.json()['status'] == 'queued' and 'input_enc' not in response.json()
    assert len(studio_db.outreach_voice_studio_jobs.docs) == 1
