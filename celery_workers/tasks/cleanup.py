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
        source_storage_key = asset.get("source_storage_key", "")
        thumb_url = asset.get("thumbnail_url")

        # Always preserve thumbnail URLs — they are stored permanently
        if thumb_url:
            surviving_thumbnail_urls.append(thumb_url)

        # Raw upload sources are transient processing artifacts — delete them
        # regardless of plan once the post is fully terminal.
        if source_storage_key and source_storage_key != storage_key:
            try:
                await _delete_from_storage(source_storage_key)
                await db.media_assets.update_one(
                    {"media_id": media_id},
                    {
                        "$set": {"source_storage_deleted_at": datetime.now(timezone.utc).isoformat()},
                        "$unset": {"source_storage_key": ""},
                    },
                )
            except Exception as raw_exc:
                logger.warning(
                    "Failed to delete raw source key for media_id=%s key=%s: %s",
                    media_id,
                    source_storage_key,
                    raw_exc,
                )

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

    from utils.storage import get_storage_backend

    storage_backend = get_storage_backend()
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
    name="celery_workers.tasks.cleanup.scan_stale_direct_uploads",
    bind=True,
)
def scan_stale_direct_uploads(self) -> dict:
    """
    Scan direct-to-cloud uploads whose session expired before completion.
    Recovery path:
    - if the raw object exists, promote to processing and enqueue the worker
    - otherwise best-effort abort multipart uploads and mark the asset failed
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(_async_scan_stale_direct_uploads())


async def _async_scan_stale_direct_uploads() -> dict:
    from api.models.media import MediaStatus
    from db.mongo import get_client
    from redis.exceptions import RedisError
    from utils.storage import (
        abort_direct_upload_session,
        head_storage_object_async,
    )

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    scanned = 0
    recovered = 0
    failed = 0
    errors = 0

    cursor = db.media_assets.find(
        {
            "status": {"$in": [MediaStatus.PENDING_UPLOAD, MediaStatus.UPLOADING]},
            "upload_expires_at": {"$lte": now_ts},
            "source_storage_key": {"$exists": True, "$ne": None},
        },
        {"_id": 0},
        limit=500,
    )

    async for asset in cursor:
        scanned += 1
        media_id = asset["media_id"]
        user_id = asset.get("user_id")
        source_storage_key = asset.get("source_storage_key")
        upload_mode = asset.get("upload_mode")
        upload_session_id = asset.get("upload_session_id")

        try:
            head = await head_storage_object_async(source_storage_key)
            if head and int(head.get("size") or 0) > 0:
                update_result = await db.media_assets.update_one(
                    {
                        "media_id": media_id,
                        "status": {"$in": [MediaStatus.PENDING_UPLOAD, MediaStatus.UPLOADING]},
                    },
                    {
                        "$set": {
                            "status": MediaStatus.PROCESSING,
                            "file_size_bytes": int(head.get("size") or asset.get("file_size_bytes") or 0),
                            "upload_completed_at": now,
                            "recovered_from_expired_upload": True,
                            "recovered_at": now,
                            "error_message": None,
                        },
                        "$unset": {
                            "upload_session_id": "",
                            "upload_expires_at": "",
                        },
                    },
                )
                if update_result.modified_count:
                    from celery_workers.tasks.media import process_media

                    process_media.apply_async(
                        kwargs={"media_job_id": media_id},
                        queue="media_processing",
                    )
                    await _release_upload_slot_if_possible(user_id)
                    recovered += 1
                continue

            if upload_mode == "multipart" and upload_session_id:
                try:
                    abort_direct_upload_session(
                        key=source_storage_key,
                        upload_id=upload_session_id,
                    )
                except Exception as abort_exc:
                    logger.warning(
                        "stale_upload_scan: multipart abort failed for media_id=%s upload_id=%s: %s",
                        media_id,
                        upload_session_id,
                        abort_exc,
                    )

            update_result = await db.media_assets.update_one(
                {
                    "media_id": media_id,
                    "status": {"$in": [MediaStatus.PENDING_UPLOAD, MediaStatus.UPLOADING]},
                },
                {
                    "$set": {
                        "status": MediaStatus.FAILED,
                        "error_message": "Direct upload expired before completion",
                        "aborted_at": now,
                    },
                    "$unset": {
                        "upload_session_id": "",
                        "upload_expires_at": "",
                    },
                },
            )
            if update_result.modified_count:
                await _release_upload_slot_if_possible(user_id)
                failed += 1
        except Exception as exc:
            logger.exception("stale_upload_scan: failed for media_id=%s: %s", media_id, exc)
            errors += 1

    logger.info(
        "stale_upload_scan: scanned=%d recovered=%d failed=%d errors=%d",
        scanned,
        recovered,
        failed,
        errors,
    )
    return {
        "status": "complete",
        "scanned": scanned,
        "recovered": recovered,
        "failed": failed,
        "errors": errors,
    }


async def _release_upload_slot_if_possible(user_id: str | None) -> None:
    if not user_id:
        return

    try:
        from db.redis_client import get_cache_redis

        cache_redis = get_cache_redis()
        key = f"upload:concurrent:{user_id}"
        value = await cache_redis.get(key)
        if value and int(value) > 0:
            await cache_redis.decr(key)
    except Exception as exc:
        logger.warning("stale_upload_scan: failed to release upload slot for user=%s: %s", user_id, exc)


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
    """Scan the active storage backend for orphaned media files and delete them in batches."""
    import re
    from db.mongo import get_client
    from utils.storage import delete_file, get_storage_backend

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    backend = get_storage_backend()

    # UUID pattern used in filenames
    uuid_pattern = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)

    files_scanned = 0
    orphaned_found = 0
    bytes_freed = 0
    errors = 0

    if backend == "r2":
        try:
            from utils.storage import _R2_BUCKET, _get_r2_client  # noqa: PLC0415

            client_r2 = _get_r2_client()
            continuation_token = None

            while True:
                kwargs = {"Bucket": _R2_BUCKET, "Prefix": "media/", "MaxKeys": 1000}
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                resp = client_r2.list_objects_v2(**kwargs)
                for obj in resp.get("Contents", []):
                    key = obj.get("Key", "")
                    files_scanned += 1
                    match = uuid_pattern.search(key)
                    if not match:
                        continue

                    file_uuid = match.group(1)
                    post = await db.posts.find_one(
                        {"$or": [{"id": file_uuid}, {"media_ids": file_uuid}]},
                        {"_id": 1, "deleted_at": 1},
                    )
                    asset = await db.media_assets.find_one(
                        {"$or": [{"media_id": file_uuid}, {"asset_id": file_uuid}]},
                        {"_id": 1},
                    )

                    is_orphaned = (post is None and asset is None) or (
                        post is not None and post.get("deleted_at") is not None
                    )
                    if not is_orphaned:
                        continue

                    try:
                        delete_file(key)
                        bytes_freed += obj.get("Size", 0) or 0
                        orphaned_found += 1
                    except Exception as del_exc:
                        logger.warning("orphan_scan: failed to delete %s — %s", key, del_exc)
                        errors += 1

                if not resp.get("IsTruncated"):
                    break
                continuation_token = resp.get("NextContinuationToken")
        except Exception as exc:
            logger.warning("orphan_scan: R2 listing unavailable — %s", exc)
            return {"status": "skipped", "reason": str(exc)}
    else:
        media_bucket = os.environ.get("GCS_BUCKET_MEDIA", "")
        quarantine_bucket = os.environ.get("GCS_BUCKET_QUARANTINE", "")
        if not media_bucket and not quarantine_bucket:
            logger.warning("orphan_scan: GCS bucket env vars not set — skipping")
            return {"status": "skipped", "reason": "no_buckets_configured"}

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
                    match = uuid_pattern.search(blob.name)
                    if not match:
                        continue

                    file_uuid = match.group(1)
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

                    if len(batch_delete) >= 100:
                        for b in batch_delete:
                            try:
                                b.delete()
                            except Exception as del_exc:
                                logger.warning("orphan_scan: failed to delete %s — %s", b.name, del_exc)
                                errors += 1
                        batch_delete = []

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
