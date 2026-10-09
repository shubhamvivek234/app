"""Review finished content without making provider calls or granting execution."""
from typing import Literal
import hashlib
from motor.motor_asyncio import AsyncIOMotorDatabase

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.authorization import canonical_hash
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_preparation import VoicePreparation
from outreach.core import suppression

router = APIRouter(prefix="/content-approvals", tags=["Outreach Content Review"])


def workspace(user: dict) -> str:
    value = user.get("default_workspace_id")
    if not value:
        raise HTTPException(403, "An active workspace is required")
    return value


class ContentDecision(BaseModel):
    decision: Literal["approve", "reject", "revoke"]
    revision: int = Field(ge=1)
    reviewed: bool = False


async def current_sequence_binding(db: AsyncIOMotorDatabase, record: dict) -> dict | None:
    binding = record["binding"]
    artifact_id = binding["context"].get("voice_artifact_id")
    artifact = None
    if artifact_id:
        clip = await VoiceArtifacts(db).prepare_load(binding["workspace_id"], artifact_id)
        artifact = clip.document
    return await sequence_binding(db, binding["workspace_id"], binding["context"]["lead_id"], voice_artifact=artifact)


async def current_binding(db: AsyncIOMotorDatabase, record: dict) -> dict | None:
    binding = record["binding"]
    if binding["source"] == "sequence":
        return await current_sequence_binding(db, record)
    from outreach.core.manual_actions import ManualActions
    service = ManualActions(db)
    job = await db.outreach_manual_actions.find_one({"_id": binding["context"]["job_id"], "workspace_id": binding["workspace_id"],
        "status": {"$in": ["queued", "awaiting_approval"]}})
    account = await db.outreach_accounts.find_one({"id": binding["sender_id"], "workspace_id": binding["workspace_id"], "is_deleted": {"$ne": True}})
    target = await service.target(binding["workspace_id"], binding["context"]["target_id"], binding["source"])
    if not job or not account or not target:
        raise ValueError("Action is no longer available for approval")
    return await service.binding(job, account, target)


@router.get("", dependencies=[require_permission("outreach:manage")])
async def list_content_reviews(view: Literal["pending", "history"] = "pending", skip: int = Query(0, ge=0, le=5000),
                               limit: int = Query(25, ge=1, le=50), current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    ws = workspace(current_user)
    query = {"workspace_id": ws, "status": "pending" if view == "pending" else {"$ne": "pending"}}
    records = await db.outreach_content_approvals.find(query).sort("updated_at", -1).skip(skip).limit(limit).to_list(length=limit)
    items = []
    for record in records:
        value = record["binding"]
        account = await db.outreach_accounts.find_one({"id": value["sender_id"], "workspace_id": ws}) or {}
        job = await db.outreach_manual_actions.find_one({"_id": value["context"].get("job_id"), "workspace_id": ws}) if value["context"].get("job_id") else None
        current = False
        try:
            current = await current_binding(db, record) == value
        except (ValueError, KeyError):
            pass
        items.append({"id": record["_id"], "revision": record["revision"], "status": record["status"],
                      "source": value["source"], "action": value["action"], "recipient": value["recipient"],
                      "sender_id": value["sender_id"], "campaign_id": value["context"].get("campaign_id"),
                      "sender_name": account.get("account_name") or account.get("name") or value["sender_id"],
                      "content": value["content"], "current": current, "has_audio": bool(value["context"].get("voice_artifact_id")),
                      "manual_job_id": value["context"].get("job_id"),
                      "can_cancel": bool(job and job["status"] in {"queued", "awaiting_approval"}),
                      "reviewed_by": record.get("reviewed_by"), "expires_at": record.get("expires_at")})
    return {"items": items, "total": await db.outreach_content_approvals.count_documents(query)}


@router.post("/prepare/{campaign_id}", dependencies=[require_permission("outreach:manage")])
async def prepare_content_reviews(campaign_id: str, skip: int = Query(0, ge=0, le=50000),
                                  limit: int = Query(50, ge=1, le=50), current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    ws = workspace(current_user)
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "workspace_id": ws, "is_deleted": {"$ne": True}})
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    query = {"workspace_id": ws, "campaign_id": campaign_id,
        "execution_state": {"$in": ["queued", "waiting_delay"]}, "assigned_account_id": {"$nin": [None, ""]},
        "current_node_id": {"$nin": [None, ""]}}
    leads = await db.outreach_leads.find(query).sort("id", 1).skip(skip).limit(limit).to_list(length=limit)
    prepared = 0
    voice_pending = 0
    voice_queued = voice_held = voice_unavailable = 0
    for lead in leads:
        async def prepare_one(current):
            value = await sequence_binding(current, ws, lead["id"])
            if not value:
                return "skip"
            if value["action"] == "voice_note":
                artifact = await current.outreach_voice_artifacts.find_one({"_id": canonical_hash(value), "workspace_id": ws, "status": "prepared"})
                try:
                    artifact = await VoiceArtifacts(current).metadata(ws, canonical_hash(value))
                except ValueError:
                    held = await current.outreach_voice_preparation_jobs.find_one({"_id": canonical_hash(value), "workspace_id": ws,
                        "status": "held_outcome"})
                    if held:
                        return "voice_held"
                    try:
                        job = await VoicePreparation(current).queue(ws, lead["id"], current_user.get("user_id"))
                    except ValueError:
                        return "voice_unavailable"
                    return "voice_held" if job["status"] == "held_outcome" else "voice_queued"
                value = await sequence_binding(current, ws, lead["id"], voice_artifact=artifact)
            await ContentApproval(current).ensure(value)
            return "prepared"
        try:
            result = await suppression.mutate_suppression(db, ws, prepare_one)
            if result == "prepared": prepared += 1
            elif result.startswith("voice_"):
                voice_pending += 1
                if result == "voice_queued": voice_queued += 1
                elif result == "voice_held": voice_held += 1
                else: voice_unavailable += 1
        except ValueError:
            continue
        except suppression.SuppressionUnavailable as exc:
            raise HTTPException(409, "Content preparation is unavailable for this workspace") from exc
    total = await db.outreach_leads.count_documents(query)
    return {"prepared": prepared, "voice_pending": voice_pending, "voice_queued": voice_queued,
            "voice_held": voice_held, "voice_unavailable": voice_unavailable, "limit": limit,
            "next_skip": skip + len(leads) if skip + len(leads) < total else None}


@router.post("/{approval_id}/decision", dependencies=[require_permission("outreach:manage")])
async def decide_content(approval_id: str, req: ContentDecision, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    ws = workspace(current_user)
    record = await db.outreach_content_approvals.find_one({"_id": approval_id, "workspace_id": ws})
    if not record:
        raise HTTPException(404, "Content review not found")
    try:
        if req.decision == "approve" and not req.reviewed:
            raise ValueError("Confirm that you reviewed the exact content and recipient")
        if req.decision == "approve" and await current_binding(db, record) != record["binding"]:
            raise ValueError("Content changed; prepare and review the current step")
        await ContentApproval(db).decide(ws, approval_id, current_user.get("user_id"), req.decision, revision=req.revision)
        if req.decision == "approve" and record["binding"]["source"] != "sequence":
            await db.outreach_manual_actions.update_one({"_id": record["binding"]["context"]["job_id"], "workspace_id": ws,
                "status": "awaiting_approval"}, {"$set": {"status": "queued"}})
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "recorded", "execution_permission": "unchanged"}


@router.post("/{approval_id}/cancel", dependencies=[require_permission("outreach:manage")])
async def cancel_manual_content(approval_id: str, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    from outreach.core.manual_actions import ManualActions
    ws = workspace(current_user)
    record = await db.outreach_content_approvals.find_one({"_id": approval_id, "workspace_id": ws})
    job_id = (record or {}).get("binding", {}).get("context", {}).get("job_id")
    if not job_id:
        raise HTTPException(404, "Manual action not found")
    try:
        await ManualActions(db).cancel(ws, job_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "cancelled"}


@router.get("/{approval_id}/audio", dependencies=[require_permission("outreach:manage")])
async def content_audio(approval_id: str, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)) -> Response:
    ws = workspace(current_user)
    record = await db.outreach_content_approvals.find_one({"_id": approval_id, "workspace_id": ws})
    artifact_id = (record or {}).get("binding", {}).get("context", {}).get("voice_artifact_id")
    if not artifact_id:
        raise HTTPException(404, "Prepared voice clip not found")
    try:
        clip = await VoiceArtifacts(db).prepare_load(ws, artifact_id)
        audio = clip.audio
        if (hashlib.sha256(audio).hexdigest() != record["binding"]["content"].get("audio_digest")
                or clip.document['generation_id'] != record['binding']['context'].get('voice_artifact_generation')):
            raise ValueError("Voice preview changed; prepare and review it again")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(audio, media_type="audio/wav" if audio.startswith(b"RIFF") else "audio/mpeg", headers={"Cache-Control": "private, no-store"})
