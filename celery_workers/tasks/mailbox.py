"""Background mailbox OAuth exchange and bounded inbound reply polling."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from celery_workers.shutdown_handler import is_shutting_down
from db.mongo import get_client
from outreach.core.mailbox_connection import complete_connection_job
from outreach.core.mailbox_sync import sync_mailbox_replies


logger = logging.getLogger(__name__)


async def _database():
    client = await get_client()
    return client[os.environ["DB_NAME"]]


@celery_app.task(name="celery_workers.tasks.mailbox.exchange_connection", queue="outreach", acks_late=True)
def exchange_connection(job_id: str, workspace_id: str) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return run_async(_exchange_connection(job_id, workspace_id))


async def _exchange_connection(job_id: str, workspace_id: str, db=None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return await complete_connection_job(db or await _database(), workspace_id, job_id)


@celery_app.task(name="celery_workers.tasks.mailbox.sync_replies", queue="outreach", acks_late=True)
def sync_replies() -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return run_async(_sync_replies())


async def _sync_replies(db=None) -> dict:
    if is_shutting_down() or os.getenv("OUTREACH_EMAIL_SYNC_ENABLED", "false").strip().lower() not in {"true", "1", "yes"}:
        return {"status": "disabled", "checked": 0}
    db = db or await _database()
    # Oldest cursor first keeps larger workspaces from starving the rest.
    cursor = db.outreach_mailboxes.find(
        {"status": "active", "provider": {"$in": ["gmail", "microsoft"]}},
        {"workspace_id": 1, "sender_account_id": 1, "last_sync_at": 1},
    ).sort("last_sync_at", 1).limit(50)
    mailboxes = await cursor.to_list(length=50)
    results = {"status": "completed", "checked": 0, "healthy": 0, "stale": 0}
    limit = asyncio.Semaphore(5)

    async def poll(mailbox: dict) -> dict | None:
        async with limit:
            if is_shutting_down():
                return None
            workspace_id, sender_id = mailbox.get("workspace_id"), mailbox.get("sender_account_id")
            if not workspace_id or not sender_id:
                return None
            try:
                return await sync_mailbox_replies(
                    db, workspace_id=workspace_id, sender_account_id=sender_id,
                )
            except Exception as exc:
                # A single unexpected sender failure must not starve all
                # other mailboxes. Fail closed if this was outside sync's
                # normal provider-error handler.
                logger.error("Mailbox reply polling failed (%s)", type(exc).__name__)
                try:
                    await db.outreach_mailboxes.update_one(
                        {"workspace_id": workspace_id, "sender_account_id": sender_id,
                         "status": "active"},
                        {"$set": {"sync_status": "stale", "sync_error": "Reply synchronization needs attention",
                                  "updated_at": datetime.now(timezone.utc)}},
                    )
                except Exception as stale_exc:
                    logger.error("Mailbox stale marker could not be saved (%s)", type(stale_exc).__name__)
                return {"status": "stale"}

    for result in await asyncio.gather(*(poll(mailbox) for mailbox in mailboxes)):
        if result is None:
            continue
        results["checked"] += 1
        if result.get("status") in {"healthy", "stale"}:
            results[result["status"]] += 1
    return results


celery_app.conf.beat_schedule.update({
    "sync-outreach-mailbox-replies": {
        "task": "celery_workers.tasks.mailbox.sync_replies",
        "schedule": 120.0,
        "options": {"queue": "outreach"},
    },
})
