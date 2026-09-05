"""
Celery tasks for outbound email notifications.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from bson import ObjectId
from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.notification_emails import send_notification_email_async
from utils.notification_prefs import should_notify

logger = logging.getLogger(__name__)


async def _async_send_notification_email(
    *,
    user_id: str,
    event: str,
    title: str,
    message: str,
    target_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    if not user_id:
        logger.warning("send_notification_email_task: missing user_id")
        return False

    client = await get_client()
    db_name = os.environ.get("DB_NAME") or os.environ.get("MONGO_DB_NAME") or "social_media_db"
    if isinstance(client, dict) and db_name not in client:
        db = next(iter(client.values())) if client else client[db_name]
    else:
        db = client[db_name]

    # 1. Double check user notification preferences (Settings gating)
    if not await should_notify(db, user_id, event, "email"):
        logger.info(
            "Notification email suppressed by user preferences: user_id=%s event=%s",
            user_id,
            event,
        )
        return False

    # 2. Fetch user profile from DB
    user_query = {"user_id": user_id}
    if ObjectId.is_valid(user_id):
        user_query = {"$or": [{"user_id": user_id}, {"_id": ObjectId(user_id)}]}

    user_doc = await db.users.find_one(user_query)
    if not user_doc or not user_doc.get("email"):
        logger.warning("send_notification_email_task: user email not found for user_id=%s", user_id)
        return False

    email = str(user_doc["email"]).strip()
    display_name = user_doc.get("display_name") or user_doc.get("name") or email.split("@")[0]

    # 3. Send email
    return await send_notification_email_async(
        email=email,
        event=event,
        title=title,
        message=message,
        target_path=target_path,
        display_name=display_name,
        metadata=metadata,
    )


@celery_app.task(
    name="celery_workers.tasks.notifications.send_notification_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="default",
)
def send_notification_email_task(
    self,
    user_id: str,
    event: str,
    title: str,
    message: str,
    target_path: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Celery task to asynchronously send notification emails."""
    try:
        return run_async(
            _async_send_notification_email(
                user_id=user_id,
                event=event,
                title=title,
                message=message,
                target_path=target_path,
                metadata=metadata,
            )
        )
    except Exception as exc:
        logger.error(
            "Error in send_notification_email_task (user_id=%s, event=%s): %s",
            user_id,
            event,
            exc,
        )
        raise self.retry(exc=exc)
