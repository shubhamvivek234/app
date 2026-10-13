"""Chronological, resumable observations of retained completed-task projections.

This is a mutable timeline, not an immutable execution/reply event log. Backdated
raw writes behind a cursor cannot establish complete historical coverage.
"""
import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference

from outreach.core.erasure import identity_is_erased, workspace_is_open
from outreach.core.workspace_scope import workspace_scope
from utils.roles import has_permission
from outreach.core.authorization import canonical_hash

logger = logging.getLogger(__name__)
STREAM_LIFETIME_SECONDS = 300
STREAM_READ_TIMEOUT_SECONDS = 5
STREAM_POLL_SECONDS = 15
STREAM_PAGE_SIZE = 100
STREAM_RESUME_HOURS = 24


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def task_cursor(workspace: str, stamp: datetime, identifier: str) -> str:
    value = [1, canonical_hash(['task_timeline', workspace]), _utc(stamp).isoformat(), identifier]
    return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()).decode().rstrip('=')


def parse_cursor(token: str, workspace: str, now: datetime) -> tuple[datetime, str]:
    """Untrusted selection token, never an authorization or completeness proof."""
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise ValueError
        value = json.loads(base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True))
        if (not isinstance(value, list) or len(value) != 4 or type(value[0]) is not int or value[0] != 1
                or value[1] != canonical_hash(['task_timeline', workspace])
                or not isinstance(value[2], str) or not isinstance(value[3], str) or not 1 <= len(value[3]) <= 256):
            raise ValueError
        stamp = datetime.fromisoformat(value[2])
        if stamp.tzinfo is None:
            raise ValueError
        stamp = _utc(stamp)
        if not now - timedelta(hours=STREAM_RESUME_HOURS) <= stamp <= now:
            raise ValueError
        return stamp, value[3]
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise ValueError('Activity resume position is unavailable') from None


@dataclass(frozen=True)
class StreamAccess:
    """Capture the original actor/tenant; never hydrate a fallback workspace."""
    user_id: str
    workspace_id: str
    firebase_uid: str | None

    def __post_init__(self) -> None:
        values = (self.user_id, self.workspace_id)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError('Invalid stream context')
        if self.firebase_uid is not None and (
            not isinstance(self.firebase_uid, str) or not self.firebase_uid.strip()
        ):
            raise ValueError('Invalid stream identity')

    async def allowed(self, db: AsyncIOMotorDatabase) -> bool:
        """Read current primary/majority authorities without creating or changing any."""
        user = await db.users.find_one(
            {'user_id': self.user_id, 'user_id.0': {'$exists': False}},
            {'_id': 0, 'user_id': 1, 'firebase_uid': 1, 'status': 1},
        )
        if not user or user.get('user_id') != self.user_id:
            return False
        if user.get('firebase_uid') != self.firebase_uid:
            return False
        if user.get('status') in {'deletion_pending', 'deleted'}:
            return False
        if await identity_is_erased(db, self.firebase_uid):
            return False
        workspace = await db.workspaces.find_one(workspace_scope(self.workspace_id),
                                                  {'_id': 0, 'owner_id': 1})
        if not workspace:
            return False
        membership = await db.workspace_members.find_one({
            **workspace_scope(self.workspace_id),
            'user_id': self.user_id, 'user_id.0': {'$exists': False},
        }, {'_id': 0, 'role': 1})
        if membership:
            try:
                if not has_permission(membership.get('role'), 'workspace:read'):
                    return False
            except (ValueError, TypeError, KeyError):
                return False
        elif workspace.get('owner_id') != self.user_id:
            return False
        return await workspace_is_open(db, self.workspace_id)


def _event(kind: str, payload: dict, cursor: str | None = None) -> str:
    prefix = f'id: {cursor}\n' if cursor else ''
    return f'{prefix}event: {kind}\ndata: {json.dumps(payload)}\n\n'


async def activity_events(
    db: AsyncIOMotorDatabase, access: StreamAccess, deadline: float, resume: str | None = None,
) -> AsyncIterator[str]:
    """Revalidate even between buffered events; normal expiry rotates via EOF."""
    async def admission() -> str | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return 'expired'
        try:
            async with asyncio.timeout(min(STREAM_READ_TIMEOUT_SECONDS, remaining)):
                allowed = await access.allowed(authority)
        except Exception as exc:
            # Do not serialize exception strings, identities, queries or credentials.
            logger.warning('outreach.stream.admission_unavailable failure_type=%s', type(exc).__name__)
            return 'expired' if time.monotonic() >= deadline else 'unavailable'
        if time.monotonic() >= deadline:
            return 'expired'
        return None if allowed else 'access_changed'

    def closure(reason: str) -> str:
        return _event('stream_closed', {'type': 'stream_closed', 'reason': reason})

    try:
        authority = db.with_options(read_preference=ReadPreference.PRIMARY,
                                    read_concern=ReadConcern('majority'))
    except Exception as exc:
        logger.warning('outreach.stream.configuration_unavailable failure_type=%s', type(exc).__name__)
        yield closure('unavailable')
        return

    reason = await admission()
    if reason:
        if reason != 'expired':
            yield closure(reason)
        return
    now = datetime.now(timezone.utc)
    last_check, last_id = now - timedelta(minutes=10), ''
    if resume:
        try:
            last_check, last_id = parse_cursor(resume, access.workspace_id, now)
            async with asyncio.timeout(min(STREAM_READ_TIMEOUT_SECONDS, max(0, deadline - time.monotonic()))):
                anchor = await authority.outreach_tasks.find_one({
                    **workspace_scope(access.workspace_id), 'status': 'completed',
                    'id': last_id, 'id.0': {'$exists': False}, 'updated_at': last_check,
                }, {'_id': 1})
            if not anchor:
                raise ValueError('Activity resume anchor changed')
        except Exception:
            yield closure('resume_unavailable')
            return
    reason = await admission()
    if reason:
        if reason != 'expired':
            yield closure(reason)
        return
    yield _event('connected', {'type': 'connected', 'status': 'online',
        'coverage': 'retained_completed_task_observations', 'initial_minutes': 10,
        'resume_hours': STREAM_RESUME_HOURS, 'timestamp': now.isoformat()})
    while True:
        reason = await admission()
        if reason:
            if reason != 'expired':
                yield closure(reason)
            return
        now = datetime.now(timezone.utc)
        try:
            async with asyncio.timeout(min(STREAM_READ_TIMEOUT_SECONDS, max(0, deadline - time.monotonic()))):
                recent_tasks = await authority.outreach_tasks.find({
                    **workspace_scope(access.workspace_id), 'status': 'completed',
                    'updated_at': {'$gte': last_check, '$lte': now},
                    '$or': [{'updated_at': {'$gt': last_check}}, {'updated_at': last_check, 'id': {'$gt': last_id}}],
                }, {'_id': 0, 'id': 1, 'task_type': 1, 'campaign_id': 1,
                    'lead_id': 1, 'account_id': 1, 'updated_at': 1}).sort([
                        ('updated_at', 1), ('id', 1)]).to_list(length=STREAM_PAGE_SIZE)
        except Exception as exc:
            logger.warning('outreach.stream.read_unavailable failure_type=%s', type(exc).__name__)
            if time.monotonic() < deadline:
                yield closure('unavailable')
            return
        for task in recent_tasks:
            reason = await admission()
            if reason:
                if reason != 'expired':
                    yield closure(reason)
                return
            updated_at, identifier = task.get('updated_at'), task.get('id')
            if (not isinstance(updated_at, datetime) or not isinstance(identifier, str)
                    or not 1 <= len(identifier) <= 256
                    or any(task.get(key) is not None and not isinstance(task[key], str)
                           for key in ('task_type', 'campaign_id', 'lead_id', 'account_id'))):
                yield closure('unavailable')
                return
            updated_at = _utc(updated_at)
            if (updated_at, identifier) <= (last_check, last_id):
                yield closure('unavailable')
                return
            cursor = task_cursor(access.workspace_id, updated_at, identifier)
            payload = {key: task.get(key) for key in (
                'id', 'task_type', 'campaign_id', 'lead_id', 'account_id',
            )}
            payload.update(timestamp=updated_at.isoformat(), event_id=cursor)
            last_check, last_id = updated_at, identifier
            yield _event('task_completed', payload, cursor)
        # Drain full pages immediately; advance only to emitted rows, never to
        # the current clock. Keep the original access checks on every page/row.
        if len(recent_tasks) == STREAM_PAGE_SIZE:
            continue
        reason = await admission()
        if reason:
            if reason != 'expired':
                yield closure(reason)
            return
        yield _event('heartbeat', {'type': 'heartbeat', 'timestamp': now.isoformat()})
        await asyncio.sleep(min(STREAM_POLL_SECONDS, max(0, deadline - time.monotonic())))
