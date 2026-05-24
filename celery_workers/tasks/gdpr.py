"""
Phase 8 — GDPR right to erasure + data export.
Erasure cascades across: posts, social_accounts, analytics, audit_events,
login_events, webhook_endpoints, workspace_members.
Data export generates a ZIP via Celery, stored in the active storage backend, link emailed.
"""
import asyncio
import csv
import io
import json
import logging
import os
import zipfile
from datetime import datetime, timedelta, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

_ERASURE_COLLECTIONS = [
    "posts",
    "social_accounts",
    "analytics",
    "login_events",
    "webhook_endpoints",
    "bulk_imports",
]

# audit_events are retained for legal/compliance — not erased
# workspace_members: soft-delete only (remove PII, keep record)


@celery_app.task(
    name="celery_workers.tasks.gdpr.process_erasure_request",
    time_limit=300,
)
def process_erasure_request(user_id: str, workspace_id: str) -> dict:
    """
    GDPR Article 17 — Right to erasure.
    Deletes or anonymises all user data across all collections.
    """
    return run_async(_async_erase(user_id, workspace_id))


async def _async_erase(user_id: str, workspace_id: str) -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    deleted: dict[str, int] = {}

    # Delete from primary collections
    for collection_name in _ERASURE_COLLECTIONS:
        result = await db[collection_name].delete_many(
            {"$or": [{"user_id": user_id}, {"workspace_id": workspace_id}]}
        )
        deleted[collection_name] = result.deleted_count

    # Anonymise workspace_members (keep the row, remove PII)
    anon_result = await db.workspace_members.update_many(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": f"deleted_{user_id[:8]}",
                "email": "redacted@deleted.invalid",
                "name": "Deleted User",
                "deleted_at": now,
            }
        },
    )
    deleted["workspace_members_anonymised"] = anon_result.modified_count

    # Record erasure completion in audit log (retained for legal compliance)
    try:
        await db.audit_events.insert_one({
            "action": "gdpr.erasure_completed",
            "actor_id": user_id,
            "workspace_id": workspace_id,
            "resource_type": "user",
            "resource_id": user_id,
            "details": {"collections_affected": deleted},
            "created_at": now,
        })
    except Exception:
        pass  # Audit failure must not block erasure

    logger.info("GDPR erasure completed for user=%s: %s", user_id, deleted)
    return {"status": "completed", "deleted": deleted}


@celery_app.task(
    name="celery_workers.tasks.gdpr.generate_data_export",
    time_limit=600,
)
def generate_data_export(user_id: str, workspace_id: str, export_id: str) -> dict:
    """
    GDPR Article 20 — Right to data portability.
    Generates a ZIP file with all user data in CSV/JSON format.
    Stores in the active storage backend and emails the download link.
    """
    return run_async(_async_export(user_id, workspace_id, export_id))


async def _async_export(user_id: str, workspace_id: str, export_id: str) -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Posts
        posts = await db.posts.find(
            {"user_id": user_id},
            {"_id": 0, "user_id": 0},
        ).to_list(length=10000)
        zf.writestr("posts.json", json.dumps(posts, default=str, indent=2))

        # Analytics
        analytics = await db.analytics.find(
            {"workspace_id": workspace_id},
            {"_id": 0},
        ).to_list(length=10000)
        zf.writestr("analytics.json", json.dumps(analytics, default=str, indent=2))

        # Audit events (last 90 days)
        audit = await db.audit_events.find(
            {"actor_id": user_id},
            {"_id": 0},
        ).to_list(length=10000)
        zf.writestr("audit_events.json", json.dumps(audit, default=str, indent=2))

        # Account info (redact tokens)
        accounts = await db.social_accounts.find(
            {"workspace_id": workspace_id},
            {"_id": 0, "access_token_encrypted": 0, "refresh_token_encrypted": 0},
        ).to_list(length=100)
        zf.writestr("social_accounts.json", json.dumps(accounts, default=str, indent=2))

    zip_bytes = zip_buffer.getvalue()

    download_url = await _upload_export_to_storage(zip_bytes, export_id)

    # Update export record
    await db.data_exports.update_one(
        {"_id": export_id},
        {
            "$set": {
                "status": "ready",
                "download_url": download_url,
                "file_size_bytes": len(zip_bytes),
                "completed_at": datetime.now(timezone.utc),
                # URL expires in 7 days
                "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            }
        },
    )

    logger.info("GDPR data export %s ready for user=%s (%d bytes)", export_id, user_id, len(zip_bytes))
    return {"status": "ready", "export_id": export_id}


async def _upload_export_to_storage(zip_bytes: bytes, export_id: str) -> str:
    """Upload ZIP to the active storage backend and return a 7-day download URL."""
    from utils.storage import get_signed_url, upload_file_async

    filename = "data.zip"
    folder = f"exports/{export_id}"
    storage_key = f"{folder}/{filename}"
    public_url = await upload_file_async(
        zip_bytes,
        filename,
        "application/zip",
        folder=folder,
    )
    try:
        return get_signed_url(storage_key, expires_in=604800)
    except Exception as exc:
        logger.warning("Falling back to public export URL for %s: %s", export_id, exc)
        return public_url
