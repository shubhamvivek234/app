"""Video Clipping Routes for Unravler."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DB, VerifiedUser
from api.models.clipping import ClippingJobResponse, ClippingRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clipping", tags=["video-clipping"])


@router.post("/jobs", response_model=ClippingJobResponse, status_code=status.HTTP_201_CREATED)
async def create_clipping_job(
    request: ClippingRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """Submit a YouTube video for automated 9:16 vertical short clipping with subtitles."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    job_doc = {
        "id": job_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "youtube_url": request.youtube_url.strip(),
        "video_title": "Processing video...",
        "status": "queued",
        "progress": 5,
        "current_step": "Job queued in background worker",
        "error_message": None,
        "num_clips": request.num_clips,
        "fit_mode": request.fit_mode,
        "burn_subtitles": request.burn_subtitles,
        "subtitle_style": request.subtitle_style,
        "min_clip_sec": request.min_clip_sec,
        "max_clip_sec": request.max_clip_sec,
        "target_account_ids": request.target_account_ids,
        "target_platforms": request.target_platforms,
        "auto_create_drafts": request.auto_create_drafts,
        "clips": [],
        "created_at": now,
        "completed_at": None,
    }

    await db.clipping_jobs.insert_one(job_doc)

    # Trigger Celery background worker
    try:
        from celery_workers.tasks.clipping import process_clipping_job
        process_clipping_job.delay(job_id)
    except Exception as exc:
        logger.warning("Could not dispatch to Celery directly (running fallback queue or test mode): %s", exc)

    job_doc.pop("_id", None)
    return job_doc


@router.get("/jobs", response_model=List[ClippingJobResponse])
async def list_clipping_jobs(
    current_user: CurrentUser,
    db: DB,
):
    """List recent video clipping jobs for the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.clipping_jobs.find(
        {"workspace_id": workspace_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(20)
    return await cursor.to_list(None)


@router.get("/jobs/{job_id}", response_model=ClippingJobResponse)
async def get_clipping_job(
    job_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Inspect progress and retrieve generated shorts from a clipping job."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    job = await db.clipping_jobs.find_one({"id": job_id, "workspace_id": workspace_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Clipping job not found")
    return job


@router.delete("/jobs/{job_id}", status_code=status.HTTP_200_OK)
async def delete_clipping_job(
    job_id: str,
    current_user: VerifiedUser,
    db: DB,
):
    """Delete a clipping job."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    res = await db.clipping_jobs.delete_one({"id": job_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Clipping job not found")
    return {"success": True, "message": "Clipping job deleted"}
