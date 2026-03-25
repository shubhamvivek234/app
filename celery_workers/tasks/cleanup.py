"""
Phase 2.6 — Media lifecycle cleanup.
Respects plan-based archive tiers. Thumbnails are PERMANENT — never deleted.
Only cleans up when ALL platforms are in terminal state (EC media cleanup gate).
"""
import logging
import os
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.cleanup.schedule_media_cleanup",
    bind=True,
    acks_late=True,
)
def schedule_media_cleanup(self, post_id: str) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_cleanup(post_id))


async def _async_cleanup(post_id: str) -> dict:
    from db.mongo import get_client
    from celery_workers.tasks.publish import should_cleanup_media

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not post:
        return {"status": "post_not_found"}

    # Double-check cleanup gate — all platforms must be terminal
    platform_results = post.get("platform_results", {})
    if not should_cleanup_media(platform_results):
        logger.info("Cleanup gate blocked — not all platforms terminal for post %s", post_id)
        return {"status": "gate_blocked"}

    user = await db.users.find_one({"user_id": post["user_id"]}, {"plan": 1})
    plan = (user or {}).get("plan", "starter")

    media_ids = post.get("media_ids", [])
    cleaned = 0
    # Collect permanent thumbnail URLs to store on the post
    # (thumbnails survive cleanup — needed for dashboard previews)
    surviving_thumbnail_urls: list[str] = []

    for media_id in media_ids:
        asset = await db.media_assets.find_one({"media_id": media_id}, {"_id": 0})
        if not asset:
            continue

        storage_key = asset.get("storage_key", "")
        thumb_url = asset.get("thumbnail_url")

        # Always preserve thumbnail URLs — they are stored permanently
        if thumb_url:
            surviving_thumbnail_urls.append(thumb_url)

        if plan == "starter":
            # Delete immediately from R2
            if storage_key:
                await _delete_from_storage(storage_key)
            else:
                logger.warning("No storage_key for media_id %s — cannot delete from R2", media_id)
        elif plan in ("pro", "agency"):
            # Retain in R2 — lifecycle policy on the bucket handles expiry.
            # pro: 30-day R2 lifecycle rule on media/ prefix
            # agency: 1-year R2 lifecycle rule on media/ prefix
            logger.info("Retaining media %s for plan=%s (R2 lifecycle handles expiry)", media_id, plan)
        # enterprise: no auto-action — R2 lifecycle rules handle archiving at 365 days

        await db.media_assets.update_one(
            {"media_id": media_id},
            {"$set": {
                "status": "archived" if plan in ("pro", "agency", "enterprise") else "cleaned",
                "media_cleaned_at": datetime.now(timezone.utc).isoformat(),
                # thumbnail_url is intentionally NOT touched — permanent
            }},
        )
        cleaned += 1

    # Clear media_urls (now stale/dead) + store permanent thumbnail_urls.
    post_update: dict = {
        "$set": {
            "media_cleaned_at": datetime.now(timezone.utc).isoformat(),
        },
        "$unset": {"media_urls": ""},  # remove dead file references
    }
    if surviving_thumbnail_urls:
        # Thumbnails are permanent — keep them for dashboard previews
        post_update["$set"]["thumbnail_urls"] = surviving_thumbnail_urls

    await db.posts.update_one({"id": post_id}, post_update)

    logger.info(
        "Cleaned %d media files for post %s (plan=%s, thumbnails_preserved=%d)",
        cleaned, post_id, plan, len(surviving_thumbnail_urls),
    )
    return {
        "status": "cleaned",
        "count": cleaned,
        "thumbnails_preserved": len(surviving_thumbnail_urls),
    }


async def _delete_from_storage(storage_key: str) -> None:
    """Delete a media file from R2 (or Firebase) using its storage key."""
    if not storage_key:
        return

    storage_backend = os.environ.get("STORAGE_BACKEND", "r2").lower()
    try:
        import asyncio
        from utils.storage import delete_file  # noqa: PLC0415
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, delete_file, storage_key)
        logger.info("Storage delete complete (%s): %s", storage_backend, storage_key)
    except Exception as exc:
        logger.error("Storage delete failed for %s: %s", storage_key, exc)
        raise


@celery_app.task(
    name="celery_workers.tasks.cleanup.scan_orphaned_files",
    bind=True,
)
def scan_orphaned_files(self) -> dict:
    """
    Phase 10.6 — Weekly orphaned file scanner.
    Lists files in /media/ and /quarantine/ GCS paths, checks if
    corresponding post exists in MongoDB, deletes orphaned files.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_scan_orphans())


async def _async_scan_orphans() -> dict:
    """Scan GCS for orphaned media files and delete them in batches."""
    import re
    from db.mongo import get_client

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    media_bucket = os.environ.get("GCS_BUCKET_MEDIA", "")
    quarantine_bucket = os.environ.get("GCS_BUCKET_QUARANTINE", "")

    if not media_bucket and not quarantine_bucket:
        logger.warning("orphan_scan: GCS bucket env vars not set — skipping")
        return {"status": "skipped", "reason": "no_buckets_configured"}

    # UUID pattern used in filenames
    uuid_pattern = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)

    files_scanned = 0
    orphaned_found = 0
    bytes_freed = 0
    errors = 0

    try:
        from google.cloud import storage as gcs_storage
        gcs_client = gcs_storage.Client()
    except (ImportError, Exception) as exc:
        logger.warning("orphan_scan: GCS client not available — %s", exc)
        return {"status": "skipped", "reason": str(exc)}

    for bucket_name, prefix_list in [
        (media_bucket, ["media/", ""]),
        (quarantine_bucket, ["quarantine/", ""]),
    ]:
        if not bucket_name:
            continue

        try:
            bucket = gcs_client.bucket(bucket_name)
        except Exception as exc:
            logger.error("orphan_scan: cannot access bucket %s — %s", bucket_name, exc)
            errors += 1
            continue

        for prefix in prefix_list:
            blobs = bucket.list_blobs(prefix=prefix, max_results=5000)
            batch_delete = []

            for blob in blobs:
                files_scanned += 1
                # Extract UUID from blob name
                match = uuid_pattern.search(blob.name)
                if not match:
                    continue

                file_uuid = match.group(1)

                # Check if any post or media_asset references this UUID
                post = await db.posts.find_one(
                    {"$or": [{"id": file_uuid}, {"media_ids": file_uuid}]},
                    {"_id": 1, "deleted_at": 1},
                )
                asset = await db.media_assets.find_one(
                    {"media_id": file_uuid},
                    {"_id": 1},
                )

                is_orphaned = (post is None and asset is None) or (
                    post is not None and post.get("deleted_at") is not None
                )

                if is_orphaned:
                    batch_delete.append(blob)
                    bytes_freed += blob.size or 0
                    orphaned_found += 1

                # Delete in batches of 100
                if len(batch_delete) >= 100:
                    for b in batch_delete:
                        try:
                            b.delete()
                        except Exception as del_exc:
                            logger.warning("orphan_scan: failed to delete %s — %s", b.name, del_exc)
                            errors += 1
                    batch_delete = []

            # Flush remaining batch
            for b in batch_delete:
                try:
                    b.delete()
                except Exception as del_exc:
                    logger.warning("orphan_scan: failed to delete %s — %s", b.name, del_exc)
                    errors += 1

    logger.info(
        "orphan_scan: scanned=%d orphaned=%d bytes_freed=%d errors=%d",
        files_scanned, orphaned_found, bytes_freed, errors,
    )
    return {
        "status": "complete",
        "files_scanned": files_scanned,
        "orphaned_found": orphaned_found,
        "bytes_freed": bytes_freed,
        "errors": errors,
    }
