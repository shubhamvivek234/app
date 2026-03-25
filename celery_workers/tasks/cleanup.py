"""
Phase 2.6 — Media lifecycle cleanup.
Respects plan-based archive tiers. Thumbnails are PERMANENT — never deleted.
Only cleans up when ALL platforms are in terminal state (EC media cleanup gate).

Section 22 fixes:
- _delete_from_storage: real deletion via utils/storage (R2/Firebase) or direct GCS
- _archive_to_nearline: real GCS update_storage_class("NEARLINE")
- _archive_to_coldline: real GCS update_storage_class("COLDLINE")
- _async_cleanup: $unset media_urls + store thumbnail_urls to prevent dead URL refs
"""
import logging
import os
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# GCS public URL prefix for extracting bucket/blob path
_GCS_PUBLIC_PREFIX = "https://storage.googleapis.com/"


def _extract_gcs_path(url: str) -> tuple[str, str]:
    """
    Parse a GCS public URL → (bucket_name, blob_path).

    URL format: https://storage.googleapis.com/{BUCKET}/{PATH}
    Returns ("", "") for non-GCS URLs (R2, Firebase, etc.).
    """
    if not url.startswith(_GCS_PUBLIC_PREFIX):
        return ("", "")
    remainder = url[len(_GCS_PUBLIC_PREFIX):]
    parts = remainder.split("/", 1)
    if len(parts) < 2:
        return (parts[0], "")
    return (parts[0], parts[1])


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
        logger.info("22: Cleanup gate blocked — not all platforms terminal for post %s", post_id)
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

        media_url = asset.get("media_url", "")
        thumb_url = asset.get("thumbnail_url")

        # Always preserve thumbnail URLs — they are stored permanently
        if thumb_url:
            surviving_thumbnail_urls.append(thumb_url)

        if plan == "starter":
            # Free/starter: delete immediately after publish
            await _delete_from_storage(media_url)
        elif plan == "pro":
            # Pro: transition to NEARLINE (30-day retrieval SLA, cheaper storage)
            await _archive_to_nearline(media_url, post_id)
        elif plan == "agency":
            # Agency: transition to COLDLINE (1-year retention, cheapest storage)
            await _archive_to_coldline(media_url, post_id)
        # enterprise: no auto-action — GCS lifecycle rules handle archiving at 365 days

        await db.media_assets.update_one(
            {"media_id": media_id},
            {"$set": {
                "status": "archived" if plan in ("pro", "agency", "enterprise") else "cleaned",
                "media_cleaned_at": datetime.now(timezone.utc).isoformat(),
                # thumbnail_url is intentionally NOT touched — permanent
            }},
        )
        cleaned += 1

    # 22 BUG FIX: Clear media_urls (now stale/dead) + store permanent thumbnail_urls.
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
        "22: Cleaned %d media files for post %s (plan=%s, thumbnails_preserved=%d)",
        cleaned, post_id, plan, len(surviving_thumbnail_urls),
    )
    return {
        "status": "cleaned",
        "count": cleaned,
        "thumbnails_preserved": len(surviving_thumbnail_urls),
    }


async def _delete_from_storage(url: str) -> None:
    """
    Delete a media file from storage.

    Uses utils/storage.delete_file() which handles both R2 (default) and
    Firebase backends. Falls back to direct GCS deletion for GCS URLs
    produced by the media processing pipeline.
    """
    if not url:
        return

    storage_backend = os.environ.get("STORAGE_BACKEND", "r2").lower()

    # GCS URLs (from media processing pipeline) — delete via google-cloud-storage
    if url.startswith(_GCS_PUBLIC_PREFIX):
        bucket_name, blob_path = _extract_gcs_path(url)
        if bucket_name and blob_path:
            try:
                from google.cloud import storage as gcs_storage  # noqa: PLC0415
                client = gcs_storage.Client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(blob_path)
                blob.delete()
                logger.info("22: GCS delete complete: gs://%s/%s", bucket_name, blob_path)
            except Exception as exc:
                logger.error("22: GCS delete failed for %s: %s", url[:80], exc)
        return

    # R2 / Firebase URLs — use the unified storage abstraction
    try:
        from utils.storage import delete_file  # noqa: PLC0415
        delete_file(url)
        logger.info("22: Storage delete complete (%s): %s", storage_backend, url[:80])
    except Exception as exc:
        logger.error("22: Storage delete failed for %s: %s", url[:80], exc)


async def _archive_to_nearline(url: str, post_id: str) -> None:
    """
    Transition a GCS object to NEARLINE storage class.

    NEARLINE has 30-day minimum storage, ~0.01 $/GB/month retrieval cost.
    For non-GCS backends (R2/Firebase), this is a no-op — objects remain
    accessible; plan-based retention is enforced by R2 bucket lifecycle settings.
    """
    if not url:
        return

    bucket_name, blob_path = _extract_gcs_path(url)
    if not bucket_name or not blob_path:
        logger.debug(
            "22: archive_to_nearline skipped (non-GCS URL) for post %s: %s",
            post_id, url[:80],
        )
        return

    try:
        from google.cloud import storage as gcs_storage  # noqa: PLC0415
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        # update_storage_class rewrites the object in-place with the new class
        blob.update_storage_class("NEARLINE")
        logger.info(
            "22: Archived to NEARLINE: gs://%s/%s (post %s)",
            bucket_name, blob_path, post_id,
        )
    except Exception as exc:
        logger.error(
            "22: Failed to archive to NEARLINE — gs://%s/%s post=%s: %s",
            bucket_name, blob_path, post_id, exc,
        )


async def _archive_to_coldline(url: str, post_id: str) -> None:
    """
    Transition a GCS object to COLDLINE storage class.

    COLDLINE has 90-day minimum storage, higher retrieval cost.
    For non-GCS backends (R2/Firebase), this is a no-op.
    """
    if not url:
        return

    bucket_name, blob_path = _extract_gcs_path(url)
    if not bucket_name or not blob_path:
        logger.debug(
            "22: archive_to_coldline skipped (non-GCS URL) for post %s: %s",
            post_id, url[:80],
        )
        return

    try:
        from google.cloud import storage as gcs_storage  # noqa: PLC0415
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.update_storage_class("COLDLINE")
        logger.info(
            "22: Archived to COLDLINE: gs://%s/%s (post %s)",
            bucket_name, blob_path, post_id,
        )
    except Exception as exc:
        logger.error(
            "22: Failed to archive to COLDLINE — gs://%s/%s post=%s: %s",
            bucket_name, blob_path, post_id, exc,
        )


@celery_app.task(
    name="celery_workers.tasks.cleanup.apply_gcs_lifecycle_rules",
    bind=True,
)
def apply_gcs_lifecycle_rules(self) -> dict:
    """
    22: Apply plan-based GCS lifecycle rules to the media bucket.

    Runs weekly via Beat to ensure rules are current after any bucket
    modifications or deployments. Uses the 'starter' (most conservative)
    rules as the default policy — individual objects are managed explicitly
    by _archive_to_nearline / _archive_to_coldline during post cleanup.

    Can also be invoked manually from an admin endpoint.
    """
    media_bucket = os.environ.get("GCS_BUCKET_MEDIA", "")
    thumbnails_bucket = os.environ.get("GCS_BUCKET_THUMBNAILS", "")

    if not media_bucket:
        logger.warning("apply_gcs_lifecycle_rules: GCS_BUCKET_MEDIA not set — skipping")
        return {"status": "skipped", "reason": "GCS_BUCKET_MEDIA not configured"}

    results: dict = {}

    try:
        from config.gcs_lifecycle import apply_lifecycle_rules  # noqa: PLC0415

        # Apply conservative lifecycle rules to media bucket (covers all plans):
        # - Abort incomplete multipart uploads after 7 days
        # - Delete /media/tmp/ processing artifacts after 1 day
        # Enterprise plan (no auto-delete, archive after 365 days) is the
        # most permissive — use it as the bucket-level safety net.
        # Per-plan enforcement happens in _async_cleanup at publish time.
        result = apply_lifecycle_rules(media_bucket, "enterprise")
        results["media_bucket"] = result
        logger.info(
            "22: Applied lifecycle rules to media bucket %s (%d rules)",
            media_bucket, result.get("rules_applied", 0),
        )
    except Exception as exc:
        logger.error("22: Failed to apply lifecycle rules to %s: %s", media_bucket, exc)
        results["media_bucket"] = {"status": "error", "error": str(exc)}

    # Thumbnails bucket: thumbnails are permanent — only abort incomplete uploads
    if thumbnails_bucket:
        try:
            from google.cloud import storage as gcs_storage  # noqa: PLC0415
            client = gcs_storage.Client()
            bucket = client.bucket(thumbnails_bucket)
            # Only rule: abort incomplete multipart uploads after 7 days
            bucket.lifecycle_rules = [{
                "action": {"type": "AbortIncompleteMultipartUpload"},
                "condition": {"age": 7},
            }]
            bucket.patch()
            results["thumbnails_bucket"] = {
                "status": "ok",
                "bucket": thumbnails_bucket,
                "note": "thumbnails are permanent — only abort-incomplete rule applied",
            }
            logger.info("22: Applied thumbnails bucket rules to %s", thumbnails_bucket)
        except Exception as exc:
            logger.error("22: Failed to apply rules to thumbnails bucket %s: %s", thumbnails_bucket, exc)
            results["thumbnails_bucket"] = {"status": "error", "error": str(exc)}

    return {"status": "complete", "results": results}


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
