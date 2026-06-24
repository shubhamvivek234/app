"""Approval workflow reminder tasks."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.notifications import emit_notification

logger = logging.getLogger(__name__)


REVIEWER_ROLES = ("owner", "admin", "editor")


def _coerce_utc_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _post_review_title(post_doc: dict) -> str:
    title = str(post_doc.get("title") or "").strip()
    if title:
        return title[:80]
    content = str(post_doc.get("content") or post_doc.get("caption") or "").strip()
    if content:
        return content[:80]
    return "Untitled post"


async def _reviewer_user_ids(db, post_doc: dict) -> list[str]:
    assigned_reviewer_id = str(post_doc.get("assigned_reviewer_id") or "").strip()
    if assigned_reviewer_id:
        return [assigned_reviewer_id]

    workspace_id = str(post_doc.get("workspace_id") or "").strip()
    creator_id = str(post_doc.get("user_id") or "").strip()
    if not workspace_id:
        return []

    docs = await db.workspace_members.find(
        {"workspace_id": workspace_id, "role": {"$in": list(REVIEWER_ROLES)}},
        {"_id": 0, "user_id": 1},
    ).to_list(length=100)

    user_ids: list[str] = []
    for doc in docs:
        user_id = str(doc.get("user_id") or "").strip()
        if user_id and user_id != creator_id and user_id not in user_ids:
            user_ids.append(user_id)
    return user_ids


async def _record_overdue_activity(db, post_doc: dict, reviewer_ids: list[str], now: datetime) -> None:
    await db.approval_activity.insert_one(
        {
            "id": str(ObjectId()),
            "workspace_id": post_doc.get("workspace_id"),
            "post_id": post_doc.get("id"),
            "actor_id": "system",
            "action": "overdue_reminder",
            "old_status": post_doc.get("status"),
            "new_status": post_doc.get("status"),
            "reason": "Approval review is overdue",
            "post_version": post_doc.get("version"),
            "metadata": {"reviewer_user_ids": reviewer_ids},
            "created_at": now,
        }
    )


async def _emit_overdue_notifications(db, post_doc: dict, reviewer_ids: list[str], now: datetime) -> list[str]:
    post_id = str(post_doc.get("id") or "").strip()
    if not post_id:
        return []

    notified: list[str] = []
    due_at = _coerce_utc_datetime(post_doc.get("approval_due_at"))
    scheduled_time = _coerce_utc_datetime(post_doc.get("scheduled_time"))
    metadata = {
        "post_id": post_id,
        "workspace_id": post_doc.get("workspace_id"),
        "approval_due_at": due_at.isoformat() if due_at else None,
        "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
    }
    for reviewer_id in reviewer_ids:
        try:
            channels = await emit_notification(
                db,
                user_id=reviewer_id,
                event="approval.overdue",
                notification_type="approval.overdue",
                title="Approval review overdue",
                message=f"{_post_review_title(post_doc)} is waiting for review and is past its approval due time.",
                severity="high",
                metadata=metadata,
                target_path="/approvals",
                dedup_key=f"approval:{post_id}:overdue:{reviewer_id}",
                created_at=now,
                update_existing=True,
            )
            if channels:
                notified.append(reviewer_id)
        except Exception as exc:
            logger.warning(
                "Failed to emit approval overdue notification for post %s user %s: %s",
                post_id,
                reviewer_id,
                exc,
            )
    return notified


async def _async_send_approval_overdue_reminders(db, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    default_due_horizon = now + timedelta(hours=1)
    cursor = db.posts.find(
        {
            "status": "pending_approval",
            "deleted_at": {"$exists": False},
            "scheduled_time": {"$gt": now},
            "approval_overdue_notified_at": {"$exists": False},
            "$or": [
                {"approval_due_at": {"$lte": now}},
                {"approval_due_at": {"$exists": False}, "scheduled_time": {"$lte": default_due_horizon}},
                {"approval_due_at": None, "scheduled_time": {"$lte": default_due_horizon}},
            ],
        },
        {"_id": 0},
    ).limit(250)
    posts = await cursor.to_list(length=250)

    scanned = len(posts)
    reminded_posts = 0
    notified_users = 0

    for post_doc in posts:
        post_id = str(post_doc.get("id") or "").strip()
        if not post_id:
            continue
        reviewer_ids = await _reviewer_user_ids(db, post_doc)
        if not reviewer_ids:
            logger.info("Approval overdue reminder skipped for post %s: no reviewers", post_id)
            continue

        notified = await _emit_overdue_notifications(db, post_doc, reviewer_ids, now)
        if not notified:
            continue

        await _record_overdue_activity(db, post_doc, notified, now)
        await db.posts.update_one(
            {"id": post_id, "status": "pending_approval"},
            {"$set": {"approval_overdue_notified_at": now, "updated_at": now}},
        )
        reminded_posts += 1
        notified_users += len(notified)

    logger.info(
        "approval_overdue_reminders_complete scanned=%s reminded_posts=%s notified_users=%s",
        scanned,
        reminded_posts,
        notified_users,
    )
    return {
        "scanned": scanned,
        "reminded_posts": reminded_posts,
        "notified_users": notified_users,
    }


@celery_app.task(name="celery_workers.tasks.approval_reminders.send_approval_overdue_reminders")
def send_approval_overdue_reminders() -> dict:
    async def _run():
        client = await get_client()
        db = client[os.environ["DB_NAME"]]
        return await _async_send_approval_overdue_reminders(db)

    return run_async(_run())
