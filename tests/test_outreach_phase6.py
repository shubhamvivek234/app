"""
Automated test suite for Phase 6: ElevenLabs AI Voice Cloning & Dynamic Audio Personalization Pipeline.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock
from fastapi import UploadFile
import io

from outreach.core.voice_cloner import VoiceCloner
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
async def test_voice_api_create_and_list():
    """Verify voice cloning API endpoint and quota listing."""
    mock_db = AsyncMock()
    mock_db.outreach_voices.find = lambda q: AsyncMock(to_list=AsyncMock(return_value=[]))
    mock_db.outreach_voices.insert_one = AsyncMock()

    user = {"user_id": "test_user_789"}
    file_content = b"RIFF" + b"\x00" * 300
    upload = UploadFile(filename="sample.wav", file=io.BytesIO(file_content))

    result = await clone_voice(
        file=upload,
        name="Founder Voice Note",
        current_user=user,
        db=mock_db,
    )

    assert result["name"] == "Founder Voice Note"
    assert result["workspace_id"] == "test_user_789"
    assert "elevenlabs_voice_id" in result
    mock_db.outreach_voices.insert_one.assert_called_once()

    # Test listing
    mock_db.outreach_voices.find = lambda q: AsyncMock(to_list=AsyncMock(return_value=[result]))
    listing = await list_voices(current_user=user, db=mock_db)
    assert listing["used_count"] == 1
    assert listing["max_voices"] == 5
    assert len(listing["voices"]) == 1


@pytest.mark.asyncio
async def test_voice_api_preview_synthesis():
    """Verify voice note preview endpoint interpolates lead variables and returns base64 audio."""
    mock_db = AsyncMock()
    mock_db.outreach_voices.find_one = AsyncMock(return_value={
        "id": "v_123",
        "workspace_id": "test_user_789",
        "name": "Outbound Voice",
        "elevenlabs_voice_id": "voice_mock_abcdef1234",
    })

    user = {"user_id": "test_user_789"}
    req = VoicePreviewRequest(
        voice_id="v_123",
        template_text="Hello {{first_name}} from {{company_name}}!",
        lead_sample={"first_name": "Elena", "company_name": "Linear"},
    )

    preview_res = await preview_voice_note(req=req, current_user=user, db=mock_db)
    assert preview_res["voice_id"] == "v_123"
    assert "audio_base64" in preview_res
    assert len(preview_res["audio_base64"]) > 10


@pytest.mark.asyncio
async def test_voice_api_assignment_and_deletion():
    """Verify assigning voices to senders and deleting voice profiles."""
    mock_db = AsyncMock()
    mock_db.outreach_voices.update_one = AsyncMock(return_value=AsyncMock(matched_count=1))
    mock_db.outreach_voices.find_one = AsyncMock(return_value={
        "id": "v_123",
        "workspace_id": "test_user_789",
        "elevenlabs_voice_id": "voice_mock_123",
    })
    mock_db.outreach_voices.delete_one = AsyncMock()

    user = {"user_id": "test_user_789"}

    # Assignment
    assign_res = await assign_voice(
        voice_id="v_123",
        req=AssignVoiceRequest(account_ids=["acc_1", "acc_2"]),
        current_user=user,
        db=mock_db,
    )
    assert assign_res["status"] == "success"
    assert assign_res["assigned_account_ids"] == ["acc_1", "acc_2"]

    # Deletion
    del_res = await delete_voice(voice_id="v_123", current_user=user, db=mock_db)
    assert del_res["status"] == "deleted"
    mock_db.outreach_voices.delete_one.assert_called_once()


@pytest.mark.asyncio
async def test_voice_cloner_synthesizes_playable_wav():
    """Verify mock synthesis generates audible WAV bytes > 1000 bytes with RIFF header."""
    from outreach.core.voice_cloner import generate_mock_voice_wav
    wav_bytes = generate_mock_voice_wav(duration_s=1.0)
    assert len(wav_bytes) > 1000
    assert wav_bytes.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_sequence_executor_handles_voice_note_step():
    """Verify SequenceExecutor dispatches voice notes through Voyager and checks daily limits."""
    from outreach.tasks.sequence_executor import SequenceExecutor
    from outreach.models import SequenceNodeType

    mock_db = AsyncMock()
    mock_db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead_voice_1",
        "campaign_id": "camp_voice_1",
        "assigned_account_id": "acc_voice_1",
        "linkedin_url": "https://linkedin.com/in/alexprospect",
        "first_name": "Alex",
        "company_name": "TechVentures",
        "execution_state": "queued",
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
    mock_db.outreach_voices.find_one = AsyncMock(return_value={
        "id": "v_voice_1",
        "workspace_id": "ws_123",
        "elevenlabs_voice_id": "voice_mock_custom",
    })
    mock_db.outreach_accounts.update_one = AsyncMock()
    mock_db.outreach_leads.update_one = AsyncMock()

    result = await SequenceExecutor.execute_lead_step(lead_id="lead_voice_1", db=mock_db)
    assert result["status"] == "success"
    assert result["action"] == SequenceNodeType.VOICE_NOTE
    mock_db.outreach_leads.update_one.assert_called()

