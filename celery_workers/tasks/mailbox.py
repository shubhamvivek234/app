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
from outreach.core.mailbox_connection import complete_connection_job, enqueue_connection_job
from outreach.core.mailbox_jobs import publish_due_jobs, recover_due_jobs
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
    return await complete_connection_job(db if db is not None else await _database(), workspace_id, job_id)


@celery_app.task(name="celery_workers.tasks.mailbox.dispatch_due_connections", queue="outreach", acks_late=True)
def dispatch_due_connections() -> dict:
    return run_async(_dispatch_due_connections())


async def _dispatch_due_connections(db=None) -> dict:
    return await publish_due_jobs(db if db is not None else await _database(), enqueue_connection_job)


@celery_app.task(name="celery_workers.tasks.mailbox.recover_connections", queue="outreach", acks_late=True)
def recover_connections() -> dict:
    return run_async(_recover_connections())


async def _recover_connections(db=None) -> dict:
    return await recover_due_jobs(db if db is not None else await _database())


@celery_app.task(name="celery_workers.tasks.mailbox.sync_replies", queue="outreach", acks_late=True)
def sync_replies() -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    return run_async(_sync_replies())


async def _sync_replies(db=None) -> dict:
    from outreach.core import mailbox_sync_jobs as jobs
    from outreach.core.erasure import _control
    if is_shutting_down() or os.getenv('OUTREACH_EMAIL_SYNC_ENABLED', 'false').strip().lower() not in {'true', '1'}:
        return {'status': 'disabled', 'checked': 0}
    db = db if db is not None else await _database()
    mailboxes = await db.outreach_mailboxes.find({'status': 'active', 'provider': {'$in': ['gmail', 'microsoft']},
        '$or': [{'next_sync_at': {'$lte': jobs.now()}}, {'next_sync_at': {'$exists': False}}]
    }).sort('next_sync_at', 1).limit(50).to_list(length=50)
    result = {'status': 'completed', 'checked': 0, 'queued': 0}
    limit = asyncio.Semaphore(5)
    async def select(mailbox):
        async with limit:
            if is_shutting_down(): return None
            workspace, sender = mailbox.get('workspace_id'), mailbox.get('sender_account_id')
            if not workspace or not sender: return None
            try:
                job = await jobs.ensure_job(db, workspace, sender)
            except Exception as exc:
                logger.error('Mailbox sync selection failed (%s)', type(exc).__name__)
                job = None
            # Scheduling metadata only, ordered even for a closed/unpaid
            # tenant. No broad stale write can touch replacement credentials.
            async def postpone(current):
                await current.outreach_mailboxes.update_one({**jobs.sync._mailbox_snapshot_filter(mailbox),
                    'next_sync_at': mailbox['next_sync_at'] if 'next_sync_at' in mailbox else {'$exists': False}},
                    {'$set': {'next_sync_at': jobs.now() + jobs.POLL_INTERVAL}})
            await _control(db, workspace, postpone)
            return job
    for job in await asyncio.gather(*(select(mailbox) for mailbox in mailboxes)):
        result['checked'] += 1
        result['queued'] += bool(job)
    return result


def enqueue_sync_job(job_id: str, workspace_id: str) -> None:
    celery_app.send_task('celery_workers.tasks.mailbox.sync_job', args=[job_id, workspace_id], queue='outreach')


@celery_app.task(name='celery_workers.tasks.mailbox.sync_job', queue='outreach', acks_late=True)
def sync_job(job_id: str, workspace_id: str) -> dict:
    return run_async(_sync_job(job_id, workspace_id))


async def _sync_job(job_id: str, workspace_id: str, db=None) -> dict:
    from outreach.core.mailbox_sync_jobs import execute_job
    if is_shutting_down(): return {'status': 'shutting_down'}
    return await execute_job(db if db is not None else await _database(), workspace_id, job_id)


@celery_app.task(name='celery_workers.tasks.mailbox.dispatch_due_sync', queue='outreach', acks_late=True)
def dispatch_due_sync() -> dict:
    return run_async(_dispatch_due_sync())


async def _dispatch_due_sync(db=None) -> dict:
    from outreach.core.mailbox_sync_jobs import publish_due
    return await publish_due(db if db is not None else await _database(), enqueue_sync_job)


@celery_app.task(name='celery_workers.tasks.mailbox.recover_sync', queue='outreach', acks_late=True)
def recover_sync() -> dict:
    return run_async(_recover_sync())


async def _recover_sync(db=None) -> dict:
    from outreach.core.mailbox_sync_jobs import recover_due, cleanup_due
    current = db if db is not None else await _database()
    return {**await recover_due(current), **await cleanup_due(current)}


celery_app.conf.beat_schedule.update({
    'dispatch-due-outreach-mailbox-sync': {'task': 'celery_workers.tasks.mailbox.dispatch_due_sync', 'schedule': 30.0, 'options': {'queue': 'outreach'}},
    'recover-outreach-mailbox-sync': {'task': 'celery_workers.tasks.mailbox.recover_sync', 'schedule': 30.0, 'options': {'queue': 'outreach'}},
    "dispatch-due-outreach-mailbox-connections": {
        "task": "celery_workers.tasks.mailbox.dispatch_due_connections", "schedule": 30.0,
        "options": {"queue": "outreach"},
    },
    "recover-outreach-mailbox-connections": {
        "task": "celery_workers.tasks.mailbox.recover_connections", "schedule": 30.0,
        "options": {"queue": "outreach"},
    },
    "sync-outreach-mailbox-replies": {
        "task": "celery_workers.tasks.mailbox.sync_replies",
        "schedule": 120.0,
        "options": {"queue": "outreach"},
    },
})
