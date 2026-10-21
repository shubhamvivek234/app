"""Read-only, bounded discovery of current actor's durable verification jobs.

Context digests bind current requests, not historical identity ownership or
execution permission. Pending locks without a provable job remain support holds.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pymongo.errors import PyMongoError

from outreach.core.authorization import canonical_hash

JOB_STATUSES = frozenset({'queued', 'running', 'finalizing', 'repairing', 'completed', 'failed',
    'storage_stopped', 'repaired_stopped', 'cancelled'})
HOLD_STATUSES = frozenset({'queued', 'running', 'finalizing', 'repairing', 'storage_stopped', 'repaired_stopped'})
MAX_DISCOVERED_JOBS = 20
METADATA_FIELDS = {'_id': 0, 'id': 1, 'sender_id': 1, 'workspace_id': 1, 'user_id': 1,
    'status': 1, 'reconnect': 1}


def plain_id(value) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= 200


def recovery_context(user: dict) -> dict:
    values = [user.get(key) for key in ('default_workspace_id', 'user_id', 'firebase_uid')]
    if not all(plain_id(value) for value in values):
        raise HTTPException(503, 'Current sender verification context is unavailable; sign in again')
    return {'contract_version': 1, 'workspace_id': values[0],
        'scope_digest': canonical_hash(['sender-verification-recovery', 1, *values])}


def verify_recovery_context(user: dict, digest: str) -> dict:
    context = recovery_context(user)
    if type(digest) is not str or digest != context['scope_digest']:
        raise HTTPException(409, 'Sender verification context changed; refresh sender accounts')
    return context


def job_metadata(row: dict, workspace: str, actor: str) -> dict:
    if (type(row.get('workspace_id')) is not str or row['workspace_id'] != workspace
            or type(row.get('user_id')) is not str or row['user_id'] != actor
            or not plain_id(row.get('id')) or not plain_id(row.get('sender_id'))
            or type(row.get('status')) is not str or row['status'] not in JOB_STATUSES
            or type(row.get('reconnect', False)) is not bool):
        raise HTTPException(503, 'Stored sender verification needs support review')
    return {'job_id': row['id'], 'sender_id': row['sender_id'], 'status': row['status'],
        'reconnect': row.get('reconnect', False)}


async def discover_jobs(db, user: dict) -> dict:
    context = recovery_context(user)
    workspace, actor = context['workspace_id'], user['user_id']
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    try:
        async with asyncio.timeout(5):
            rows = await db.outreach_connection_jobs.find({'workspace_id': workspace, 'user_id': actor,
                '$or': [{'status': {'$in': sorted(HOLD_STATUSES)}}, {'created_at': {'$gte': recent}},
                    {'updated_at': {'$gte': recent}}]}, METADATA_FIELDS).sort([('created_at', -1), ('id', 1)]).limit(MAX_DISCOVERED_JOBS + 1).to_list(MAX_DISCOVERED_JOBS + 1)
            if len(rows) > MAX_DISCOVERED_JOBS:
                raise HTTPException(503, 'Too many verification records; contact support before reconnecting')
            jobs = [job_metadata(row, workspace, actor) for row in rows]
            if len({row['job_id'] for row in jobs}) != len(jobs):
                raise HTTPException(503, 'Duplicate verification records require support review')
            locks = await db.outreach_connection_locks.find({'workspace_id': workspace},
                {'_id': 1, 'workspace_id': 1, 'job_id': 1, 'storage_outcome_unknown': 1}).limit(MAX_DISCOVERED_JOBS + 1).to_list(MAX_DISCOVERED_JOBS + 1)
            if len(locks) > MAX_DISCOVERED_JOBS:
                raise HTTPException(503, 'Verification lock review exceeds the supported bound')
            operator_review = False
            for lock in locks:
                if (type(lock.get('workspace_id')) is not str or lock['workspace_id'] != workspace
                        or not plain_id(lock.get('_id')) or not plain_id(lock.get('job_id'))):
                    raise HTTPException(503, 'Stored verification lock requires support review')
                saved = await db.outreach_connection_jobs.find_one({'workspace_id': workspace, 'id': lock['job_id']}, METADATA_FIELDS)
                if (not saved or saved.get('workspace_id') != workspace or type(saved.get('workspace_id')) is not str
                        or saved.get('id') != lock['job_id'] or type(saved.get('id')) is not str
                        or saved.get('sender_id') != lock['_id'] or type(saved.get('sender_id')) is not str
                        or type(saved.get('status')) is not str or saved['status'] not in JOB_STATUSES
                        or saved['status'] not in HOLD_STATUSES or lock.get('storage_outcome_unknown')):
                    operator_review = True
            return {'context': context, 'jobs': jobs, 'operator_review_required': operator_review}
    except (TimeoutError, PyMongoError):
        raise HTTPException(503, 'Sender verification discovery is unavailable; refresh before reconnecting') from None
