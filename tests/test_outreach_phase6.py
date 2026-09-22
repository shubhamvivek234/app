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
