"""
Phase 2 — Media processing Celery task.
Validates, compresses, thumbnails. Moves from /quarantine/ to /media/ on success.
"""
import logging
import os
from datetime import datetime

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.media.process_media",
    bind=True,
    max_retries=2,
    acks_late=True,
    queue="media_processing",
    time_limit=360,       # hard kill after 6 minutes
    soft_time_limit=300,  # soft kill after 5 minutes (raises SoftTimeLimitExceeded)
)
def process_media(self, media_job_id: str, user_id: str) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _async_process_media(self, media_job_id, user_id)
    )


async def _async_process_media(task, media_job_id: str, user_id: str) -> dict:
    from db.mongo import get_client
    from media_pipeline.validation import validate_media
    from media_pipeline.ffmpeg_worker import process_video
    from media_pipeline.thumbnail import generate_thumbnail

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    asset = await db.media_assets.find_one({"media_id": media_job_id}, {"_id": 0})
    if not asset:
        return {"status": "not_found"}

    quarantine_path = asset.get("quarantine_path")
    mime_type = asset.get("mime_type")

    try:
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "processing"}},
        )

        # Step 1: Validate
        validation_result = await validate_media(quarantine_path, mime_type)

        # Step 2: Process (transcode if video)
        if mime_type and mime_type.startswith("video/"):
            processed_path = await process_video(quarantine_path, validation_result)
        else:
            processed_path = quarantine_path

        # Step 3: Generate thumbnail
        thumbnail_path = await generate_thumbnail(processed_path, mime_type, media_job_id, user_id)

        # Step 4: Move to permanent storage
        # TODO: Upload processed_path to GCS /media/{user_id}/{media_job_id}
        media_url = f"https://storage.googleapis.com/{os.environ.get('GCS_BUCKET_MEDIA')}/media/{user_id}/{media_job_id}"
        thumbnail_url = f"https://storage.googleapis.com/{os.environ.get('GCS_BUCKET_THUMBNAILS')}/thumbnails/{user_id}/{media_job_id}.webp"

        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {
                "status": "ready",
                "media_url": media_url,
                "thumbnail_url": thumbnail_url,
                "processed_at": datetime.utcnow().isoformat(),
                "duration_seconds": validation_result.get("duration"),
                "width": validation_result.get("width"),
                "height": validation_result.get("height"),
            }},
        )

        logger.info("Media %s processed successfully", media_job_id)
        return {"status": "ready", "media_url": media_url, "thumbnail_url": thumbnail_url}

    except Exception as exc:
        logger.error("Media processing failed for %s: %s", media_job_id, exc)
        await db.media_assets.update_one(
            {"media_id": media_job_id},
            {"$set": {"status": "failed", "error_message": str(exc)}},
        )
        raise task.retry(countdown=30, exc=exc)


@celery_app.task(name="celery_workers.tasks.media.send_notification")
def send_notification(post_id: str, type: str, platform: str | None = None, error: str | None = None) -> None:
    logger.info("Notification queued: type=%s post_id=%s platform=%s", type, post_id, platform)
