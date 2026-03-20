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
        from celery_workers.tasks.gdpr import generate_data_export
        generate_data_export.apply_async(
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
    All data removed within 30 days per retention policy.
    """
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "deletion_requested_at": now,
            "status": "deletion_pending",
        }},
    )

    try:
        from celery_workers.tasks.gdpr import process_erasure_request
        process_erasure_request.apply_async(
            kwargs={
                "user_id": user_id,
                "workspace_id": current_user.get("default_workspace_id", user_id),
            },
            queue="default",
        )
    except (ImportError, Exception) as exc:
        logger.warning("GDPR erasure task unavailable: %s", exc)

    logger.info("Account deletion requested: user=%s", user_id)
    return DeleteAccountResponse(
        status="queued",
        message="Account deletion has been queued. All data will be removed within 30 days.",
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

    doc = await db.notification_prefs.find_one(
        {"user_id": user_id},
        {"_id": 0, "prefs": 1},
    )

    prefs: dict[str, Any] = doc["prefs"] if doc and "prefs" in doc else {}
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

    await db.notification_prefs.update_one(
        {"user_id": user_id},
        {"$set": {
            "prefs": body.preferences,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )

    logger.info("Notification prefs updated: user=%s", user_id)
    return NotificationPreferencesResponse(preferences=body.preferences)
