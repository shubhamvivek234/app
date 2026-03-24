"""
Phase 6 — Bulk CSV import via Celery.
Users upload a CSV file → triggers this task → validates + schedules posts.
CSV columns: content, platforms (comma-separated), scheduled_time (ISO 8601), post_type, media_url
"""
import asyncio
import csv
import io
import logging
import os
import uuid
from datetime import datetime, timezone

from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

_MAX_ROWS = 500           # Safety cap per import
_IMPORT_TIMEOUT_SEC = 300  # 5 minutes max per import task

REQUIRED_COLUMNS = {"content", "platforms", "scheduled_time"}


@celery_app.task(
    name="celery_workers.tasks.bulk_import.process_csv_import",
    time_limit=_IMPORT_TIMEOUT_SEC,
)
def process_csv_import(
    csv_content: str,
    workspace_id: str,
    user_id: str,
    import_id: str,
) -> dict:
    """
    Process a CSV file uploaded for bulk post scheduling.
    csv_content: raw CSV text (decoded from uploaded file).
    Returns summary of imported / failed rows.
    """
    return asyncio.get_event_loop().run_until_complete(
        _async_process(csv_content, workspace_id, user_id, import_id)
    )


async def _async_process(
    csv_content: str,
    workspace_id: str,
    user_id: str,
    import_id: str,
) -> dict:
    from utils.content_policy import check_content_policy, validate_platform_content_type

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    reader = csv.DictReader(io.StringIO(csv_content))

    # Validate header
    if not reader.fieldnames:
        return {"status": "failed", "error": "CSV has no headers"}

    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        return {"status": "failed", "error": f"Missing required columns: {missing}"}

    imported = 0
    failed = 0
    errors: list[dict] = []

    async def _update_progress() -> None:
        await db.bulk_imports.update_one(
            {"_id": import_id},
            {"$set": {"imported": imported, "failed": failed, "updated_at": now}},
        )

    for row_num, row in enumerate(reader, start=2):
        if imported + failed >= _MAX_ROWS:
            errors.append({"row": row_num, "error": "Row limit reached"})
            break

        try:
            content = (row.get("content") or "").strip()
            if not content:
                raise ValueError("content is required")

            platforms_raw = (row.get("platforms") or "").strip()
            platforms = [p.strip().lower() for p in platforms_raw.split(",") if p.strip()]
            if not platforms:
                raise ValueError("platforms is required")

            scheduled_raw = (row.get("scheduled_time") or "").strip()
            scheduled_time = datetime.fromisoformat(scheduled_raw)
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

            if scheduled_time <= now:
                raise ValueError(f"scheduled_time must be in the future: {scheduled_raw}")

            post_type = (row.get("post_type") or "text").strip().lower()
            media_url = (row.get("media_url") or "").strip() or None

            # Gap 5.4: SSRF guard — reject internal/private URLs in CSV
            if media_url:
                from utils.ssrf_guard import assert_safe_url
                assert_safe_url(media_url)

            # Validate platform compatibility + content policy
            for platform in platforms:
                validate_platform_content_type(platform, post_type)
                result = check_content_policy(content, platform)
                if not result.approved:
                    raise ValueError(f"Content policy violation on {platform}: {result.violations}")

            post = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "workspace_id": workspace_id,
                "content": content,
                "platforms": platforms,
                "post_type": post_type,
                "media_ids": [],
                "media_url": media_url,
                "scheduled_time": scheduled_time,
                "status": "scheduled",
                "platform_results": {},
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "bulk_import_id": import_id,
            }
            await db.posts.insert_one(post)
            imported += 1

        except Exception as exc:
            failed += 1
            errors.append({"row": row_num, "error": str(exc)})
            logger.warning("Bulk import row %d failed: %s", row_num, exc)

        # Progress update every 50 rows
        if (imported + failed) % 50 == 0:
            await _update_progress()

    # Final status update
    final_status = "completed" if failed == 0 else ("partial" if imported > 0 else "failed")
    await db.bulk_imports.update_one(
        {"_id": import_id},
        {
            "$set": {
                "status": final_status,
                "imported": imported,
                "failed": failed,
                "errors": errors[:50],  # cap stored errors
                "completed_at": datetime.now(timezone.utc),
            }
        },
    )

    logger.info(
        "Bulk import %s: imported=%d failed=%d status=%s",
        import_id, imported, failed, final_status,
    )
    return {"status": final_status, "imported": imported, "failed": failed}
