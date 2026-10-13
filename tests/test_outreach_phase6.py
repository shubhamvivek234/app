"""
Automated test suite for Phase 6: ElevenLabs AI Voice Cloning & Dynamic Audio Personalization Pipeline.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest

pytestmark = pytest.mark.usefixtures("outreach_paid_gate_stub")


@pytest.fixture(autouse=True)
def sandbox_linkedin_sessions(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "mock")
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile
import io

from outreach.core.voice_cloner import VoiceCloner
from tests.test_outreach_voice_studio import studio_db, clone
from outreach.api.voice import (
    clone_voice,
    list_voices,
    preview_voice_note,
    assign_voice,
    delete_voice,
    VoicePreviewRequest,
    AssignVoiceRequest,
)


@pytest.mark.asyncio
async def test_voice_cloner_mock_lifecycle():
    """Verify VoiceCloner mock lifecycle generates mock IDs and synthesizes valid audio bytes."""
    cloner = VoiceCloner(api_key="mock")
    assert cloner.is_mock is True

    # Test cloning
    audio_sample = b"RIFF" + b"\x00" * 200
    voice_id = await cloner.create_voice_clone(audio_sample, "Test Executive Voice")
    assert voice_id.startswith("voice_mock_")

    # Test synthesis with dynamic interpolation
    lead_data = {"first_name": "Jordan", "company_name": "Stripe"}
    script = "Hi {{first_name}}, saw your team at {{company_name}} is scaling!"
    audio_bytes = await cloner.synthesize_voice_note(voice_id, script, lead_data)
    assert isinstance(audio_bytes, bytes)
    assert len(audio_bytes) > 0
    assert audio_bytes.startswith(b"RIFF")

    # Test deletion
    deleted = await cloner.delete_voice_clone(voice_id)
    assert deleted is True


@pytest.mark.asyncio
async def test_voice_api_create_and_list(studio_db):
    from outreach.core.voice_cloner import generate_mock_voice_wav
    from outreach.core.voice_studio import VoiceStudio
    user = {'user_id': 'actor', 'default_workspace_id': 'w'}
    upload = UploadFile(filename='sample.wav', file=io.BytesIO(generate_mock_voice_wav(duration_s=20)))
    job = await clone_voice(file=upload, name='Founder voice', consent=True, request_id='api-clone-1', current_user=user, db=studio_db)
    assert job['status'] == 'queued' and 'input_enc' not in job
    listing = await list_voices(user, studio_db)
    assert listing['used_count'] == 1 and listing['voices'][0]['status'] == 'creating'
    assert 'elevenlabs_voice_id' not in listing['voices'][0]


@pytest.mark.asyncio
async def test_voice_api_preview_synthesis(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'provider_voice'}))
    profile = studio_db.outreach_voices.docs[0]
    req = VoicePreviewRequest(voice_id=profile['id'], request_id='api-preview-1', template_text='Hi {{first_name}}', lead_sample={'first_name': 'Alex'})
    preview = await preview_voice_note(req, {'user_id': 'actor', 'default_workspace_id': 'w'}, studio_db)
    assert preview['status'] == 'queued' and 'audio_base64' not in preview


@pytest.mark.asyncio
async def test_voice_api_assignment_and_deletion(studio_db):
    from outreach.core.voice_studio import VoiceStudio
    service = VoiceStudio(studio_db); job = await clone(service)
    await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'provider_voice'}))
    profile = studio_db.outreach_voices.docs[0]
    studio_db.outreach_accounts.docs.append({'id': 'a', 'workspace_id': 'w'})
    user = {'user_id': 'actor', 'default_workspace_id': 'w'}
    assert (await assign_voice(profile['id'], AssignVoiceRequest(account_ids=['a'], revision=profile['revision']), user, studio_db))['status'] == 'success'
    deletion = await delete_voice(profile['id'], 'api-delete-1', user, studio_db)
    assert deletion['status'] == 'queued' and len(studio_db.outreach_voices.docs) == 1


@pytest.mark.asyncio
async def test_voice_cloner_synthesizes_playable_wav():
    """Verify mock synthesis generates audible WAV bytes > 1000 bytes with RIFF header."""
    from outreach.core.voice_cloner import generate_mock_voice_wav
    wav_bytes = generate_mock_voice_wav(duration_s=1.0)
    assert len(wav_bytes) > 1000
    assert wav_bytes.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_sequence_executor_handles_voice_note_step(monkeypatch):
    """Verify SequenceExecutor dispatches voice notes through Voyager and checks daily limits."""
    from outreach.tasks.sequence_executor import SequenceExecutor
    from outreach.models import SequenceNodeType

    mock_db = AsyncMock()
    mock_db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead_voice_1",
        "workspace_id": "ws_123",
        "campaign_id": "camp_voice_1",
        "assigned_account_id": "acc_voice_1",
        "linkedin_url": "https://linkedin.com/in/alexprospect",
        "first_name": "Alex",
        "company_name": "TechVentures",
        "execution_state": "queued",
        "current_node_id": "step_vn_1",
    })
    mock_db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_voice_1",
        "status": "active",
        "schedule": {"timezone": "UTC", "start_time": "00:00", "end_time": "23:59", "days": [0, 1, 2, 3, 4, 5, 6]},
    })
    mock_db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": "acc_voice_1",
        "workspace_id": "ws_123",
        "status": "active",
        "session_cookie_enc": "mock_cookie",
        "limits": {"voice_notes": 20},
        "counters": {"date": "2026-09-23", "voice_notes": 0},
    })
    mock_db.outreach_sequences.find_one = AsyncMock(return_value={
        "campaign_id": "camp_voice_1",
        "compiled_dag": {
            "root_node_ids": ["step_vn_1"],
            "nodes": {
                "step_vn_1": {
                    "id": "step_vn_1",
                    "type": SequenceNodeType.VOICE_NOTE,
                    "config": {"script": "Hey {{first_name}}, loved {{company_name}}!"},
                    "next_default": None,
                }
            }
        }
    })
    from outreach.core.voice_studio import source_digest
    from datetime import datetime, timezone
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-provider-key')
    from tests.outreach_memory import Cursor
    mock_db.outreach_voices.find = MagicMock(return_value=Cursor([{
        'status': 'active', 'provider_source_digest': source_digest(),
        'consent': {'actor': 'actor', 'version': 1, 'asserted_at': datetime.now(timezone.utc), 'assertion_digest': 'test-consent'},
        "id": "v_voice_1",
        "workspace_id": "ws_123",
        "elevenlabs_voice_id": "voice_mock_custom",
        "assigned_account_ids": ["acc_voice_1"], "revision": 1,
    }]))
    mock_db.outreach_accounts.update_one = AsyncMock()
    mock_db.outreach_leads.update_one = AsyncMock()

    result = await SequenceExecutor.execute_lead_step(lead_id="lead_voice_1", db=mock_db)
    assert result["status"] == "success"
    assert result["action"] == SequenceNodeType.VOICE_NOTE
    mock_db.outreach_leads.update_one.assert_called()
