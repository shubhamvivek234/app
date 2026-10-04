"""Offline TTS on the media queue; the broker contains references only."""
import os
from motor.motor_asyncio import AsyncIOMotorDatabase

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from celery_workers.shutdown_handler import is_shutting_down
from db.mongo import get_client
from outreach.core.suppression import SuppressionUnavailable
from outreach.core.voice_studio import VoiceStudio, publish_studio_jobs


async def _database() -> AsyncIOMotorDatabase:
    return (await get_client())[os.environ["DB_NAME"]]


@celery_app.task(name="celery_workers.tasks.voice_studio.prepare", queue="media_processing", acks_late=True)
def prepare(job_id: str, workspace_id: str) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return run_async(_prepare(job_id, workspace_id))


async def _prepare(job_id: str, workspace_id: str, db: AsyncIOMotorDatabase | None = None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    try:
        result = await VoiceStudio(db if db is not None else await _database()).run(workspace_id, job_id)
        return {'status': result['status'], 'job_id': job_id}
    except SuppressionUnavailable:
        return {"status": "workspace_unavailable"}


@celery_app.task(name="celery_workers.tasks.voice_studio.publish", queue="outreach")
def publish() -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return run_async(_publish())


async def _publish(db: AsyncIOMotorDatabase | None = None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    async def enqueue(job_id, workspace_id):
        if is_shutting_down():
            raise RuntimeError("Worker is shutting down")
        prepare.apply_async(args=[job_id, workspace_id], queue="media_processing")
    count = await publish_studio_jobs(db if db is not None else await _database(), enqueue)
    return {"status": "completed", "published": count}


celery_app.conf.beat_schedule.update({"publish-outreach-voice-studio": {
    "task": "celery_workers.tasks.voice_studio.publish", "schedule": 30.0, "options": {"queue": "outreach"}}})
