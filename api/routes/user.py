"""
User account management — GDPR data export, account deletion, notification preferences.
Section 20.3 (GDPR Article 17/20) and 20.12 (notification prefs).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB
from api.limiter import limiter
from api.task_queue import enqueue_task
from utils.notification_prefs import get_user_prefs, sanitize_preferences

logger = logging.getLogger(__name__)
router = APIRouter(tags=["user"])


# ── Response models ───────────────────────────────────────────────────────────

class DataExportResponse(BaseModel):
    status: str
    export_id: str
    message: str


class DeleteAccountResponse(BaseModel):
    status: str
    message: str


class NotificationPreferencesResponse(BaseModel):
    preferences: dict[str, Any]


class NotificationPreferencesUpdate(BaseModel):
    preferences: dict[str, Any]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/user/data-export", response_model=DataExportResponse,
             status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/hour")
async def request_data_export(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> DataExportResponse:
    """
    GDPR Article 20 — Right to data portability.
    Enqueues a Celery task that assembles a ZIP of all user data
    and emails a download link when ready (up to 15 minutes).
    """
    user_id = current_user["user_id"]
    export_id = str(uuid.uuid4())

    await db.data_exports.insert_one({
        "_id": export_id,
        "user_id": user_id,
        "status": "pending",
        "requested_at": datetime.now(timezone.utc),
    })

    try:
        enqueue_task(
            "celery_workers.tasks.gdpr.generate_data_export",
            kwargs={
                "user_id": user_id,
                "workspace_id": current_user.get("default_workspace_id", user_id),
                "export_id": export_id,
            },
            queue="default",
        )
    except (ImportError, Exception) as exc:
        logger.warning("GDPR export task unavailable: %s", exc)

    logger.info("Data export requested: user=%s export_id=%s", user_id, export_id)
    return DataExportResponse(
        status="queued",
        export_id=export_id,
        message="Export will be emailed when ready (up to 15 minutes).",
    )


@router.delete("/user/account", response_model=DeleteAccountResponse,
               status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> DeleteAccountResponse:
    """
    GDPR Article 17 — Right to erasure.
    Marks account as deletion_pending and enqueues full data wipe.
    Outreach database cleanup waits for operator-confirmed writer drain.
    """
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "deletion_requested_at": now,
            "deletion_next_publish_at": now,
            "status": "deletion_pending",
        }},
    )

    from outreach.core.erasure import begin_user_erasure, stop_identity
    try:
        await stop_identity(db, current_user.get("firebase_uid"))
        await begin_user_erasure(db, user_id)
    except Exception as exc:
        logger.warning("Account deletion stop could not be completed (%s)", type(exc).__name__)
        raise HTTPException(503, "Data deletion could not be safely started. Please retry.") from None

    try:
        enqueue_task(
            "celery_workers.tasks.gdpr.process_erasure_request",
            kwargs={
                "user_id": user_id,
                "workspace_id": current_user.get("default_workspace_id", user_id),
                "firebase_uid": current_user.get("firebase_uid"),
            },
            queue="default",
        )
    except Exception as exc:
        logger.warning("Account deletion publication will retry (%s)", type(exc).__name__)

    logger.info("Account deletion requested: user=%s", user_id)
    return DeleteAccountResponse(
        status="queued",
        message="Account deletion has been requested. Outreach is stopped; cleanup may await operator review. Limited recovery and provider-term records can remain under retention review.",
    )


@router.get("/user/notification-preferences", response_model=NotificationPreferencesResponse)
@limiter.limit("30/minute")
async def get_notification_preferences(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> NotificationPreferencesResponse:
    """Section 20.12 — Fetch per-channel notification preferences for the current user."""
    user_id = current_user["user_id"]
    prefs = await get_user_prefs(db, user_id)
    return NotificationPreferencesResponse(preferences=prefs)


@router.patch("/user/notification-preferences", response_model=NotificationPreferencesResponse)
@limiter.limit("30/minute")
async def update_notification_preferences(
    request: Request,
    body: NotificationPreferencesUpdate,
    current_user: CurrentUser,
    db: DB,
) -> NotificationPreferencesResponse:
    """Section 20.12 — Update per-channel notification preferences."""
    user_id = current_user["user_id"]
    sanitized_preferences = sanitize_preferences(body.preferences)

    await db.notification_prefs.update_one(
        {"user_id": user_id},
        {"$set": {
            "prefs": sanitized_preferences,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )

    logger.info("Notification prefs updated: user=%s", user_id)
    prefs = await get_user_prefs(db, user_id)
    return NotificationPreferencesResponse(preferences=prefs)


@router.get("/user/data-deletion-status/{confirmation_code}")
@limiter.limit("60/minute")
async def get_data_deletion_status(
    request: Request,
    confirmation_code: str,
    db: DB,
) -> dict:
    """
    Public lookup for data deletion request status.
    Called by users or Meta reviewers to verify that data has been purged.
    """
    record = await db.data_deletions.find_one({"confirmation_code": confirmation_code})
    if record:
        created = record.get("created_at")
        return {
            "found": True,
            "confirmation_code": confirmation_code,
            "status": record.get("status", "unknown"),
            "details": record.get("details", "No completion details have been recorded for this request."),
            "created_at": created.isoformat() if isinstance(created, datetime) else None,
        }
    return {
        "found": False,
        "confirmation_code": confirmation_code,
        "status": "not_found",
        "details": "No deletion request was found for this confirmation code.",
        "created_at": None,
    }
