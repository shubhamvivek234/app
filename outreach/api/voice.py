"""
Phase 6: AI Voice Cloning API Router for LinkedIn Outreach Engine.
Enables uploading a 30s voice recording, cloning via ElevenLabs, previewing with lead variables,
and assigning voice profiles to senders.
"""
import base64
import logging
from typing import Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.voice_cloner import VoiceCloner, VoiceCloningError
from outreach.models import OutreachVoice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["LinkedIn Voice AI Engine"])

MAX_VOICE_PROFILES = 5


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 1000) -> list[dict[str, Any]]:
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


class VoicePreviewRequest(BaseModel):
    voice_id: str
    template_text: str = Field(
        default="Hey {{first_name}}, saw you're also at {{company_name}} and wanted to connect!",
        description="Script with personalization tokens",
    )
    lead_sample: dict[str, Any] = Field(
        default_factory=lambda: {"first_name": "Alex", "company_name": "Acme Corp"},
        description="Sample lead attributes for interpolation",
    )


class AssignVoiceRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)


@router.get("")
async def list_voices(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns list of configured AI voices for the workspace, matching Part 3, Image 2.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    voices = await _fetch_cursor_docs(
        db.outreach_voices.find({
            "$or": [{"workspace_id": user_id}, {"workspace_id": ws_id}, {"user_id": user_id}],
        }),
        length=MAX_VOICE_PROFILES,
    )

    clean_voices = []
    for v in voices:
        doc = dict(v)
        doc.pop("_id", None)
        clean_voices.append(doc)

    return {
        "voices": clean_voices,
        "used_count": len(clean_voices),
        "max_voices": MAX_VOICE_PROFILES,
    }


@router.post("/clone", status_code=status.HTTP_201_CREATED)
async def clone_voice(
    file: UploadFile = File(...),
    name: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Accepts an audio recording (WAV/MP3/M4A), creates an ElevenLabs instant voice clone,
    and registers it in the outreach database.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id

    # Check quota
    existing = await _fetch_cursor_docs(
        db.outreach_voices.find({
            "$or": [{"workspace_id": user_id}, {"workspace_id": ws_id}, {"user_id": user_id}],
        }),
        length=MAX_VOICE_PROFILES + 1,
    )
    if len(existing) >= MAX_VOICE_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Voice profile limit reached ({MAX_VOICE_PROFILES}/{MAX_VOICE_PROFILES}). Please delete an existing voice to record a new one.",
        )

    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording was empty or too short. Please record for at least 30 seconds.",
        )

    cloner = VoiceCloner()
    try:
        elevenlabs_voice_id = await cloner.create_voice_clone(
            audio_bytes=audio_bytes,
            voice_name=name.strip(),
            filename=file.filename or "sample.wav",
        )
    except VoiceCloningError as err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))

    voice_record = OutreachVoice(
        workspace_id=ws_id,
        user_id=user_id,
        name=name.strip(),
        elevenlabs_voice_id=elevenlabs_voice_id,
        sample_audio_url="",
        assigned_account_ids=[],
    )

    await db.outreach_voices.insert_one(voice_record.model_dump())
    result = voice_record.model_dump()
    result.pop("_id", None)
    return result


@router.post("/preview")
async def preview_voice_note(
    req: VoicePreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Synthesizes a sample voice note with dynamic lead tokens and returns base64 audio.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"

    # Verify voice belongs to workspace or is mock
    voice = await db.outreach_voices.find_one({
        "id": req.voice_id,
        "$or": [{"workspace_id": user_id}, {"workspace_id": ws_id}, {"user_id": user_id}],
    })
    if not voice and not req.voice_id.startswith("voice_mock_"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice profile not found in workspace",
        )

    elevenlabs_voice_id = voice.get("elevenlabs_voice_id", req.voice_id) if voice else req.voice_id

    cloner = VoiceCloner()
    try:
        audio_bytes = await cloner.synthesize_voice_note(
            voice_id=elevenlabs_voice_id,
            template_text=req.template_text,
            lead=req.lead_sample,
        )
    except VoiceCloningError as err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))

    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    return {
        "voice_id": req.voice_id,
        "media_type": "audio/wav" if cloner.is_mock else "audio/mp3",
        "audio_base64": audio_base64,
        "sample_lead": req.lead_sample,
        "interpolated_text": cloner.is_mock,
    }


@router.post("/{voice_id}/assign")
async def assign_voice(
    voice_id: str,
    req: AssignVoiceRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Assigns this voice profile to one or more LinkedIn sender accounts.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    res = await db.outreach_voices.update_one(
        {"id": voice_id, "$or": [{"workspace_id": user_id}, {"workspace_id": ws_id}, {"user_id": user_id}]},
        {"$set": {"assigned_account_ids": req.account_ids}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")

    return {"status": "success", "voice_id": voice_id, "assigned_account_ids": req.account_ids}


@router.delete("/{voice_id}")
async def delete_voice(
    voice_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Deletes a voice profile from the database and ElevenLabs.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    voice = await db.outreach_voices.find_one({
        "id": voice_id,
        "$or": [{"workspace_id": user_id}, {"workspace_id": ws_id}, {"user_id": user_id}],
    })
    if not voice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")

    cloner = VoiceCloner()
    await cloner.delete_voice_clone(voice.get("elevenlabs_voice_id", voice_id))
    await db.outreach_voices.delete_one({"id": voice_id})

    return {"status": "deleted", "voice_id": voice_id}

