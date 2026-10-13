"""Bounded, pinned access for the completed-task SSE feed.

Admission is rechecked before reads and emissions. It is not a transaction
with revocation, nor a resumable or complete activity/event log.
"""
import asyncio
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

logger = logging.getLogger(__name__)
STREAM_LIFETIME_SECONDS = 300
STREAM_READ_TIMEOUT_SECONDS = 5
STREAM_POLL_SECONDS = 15


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


def _event(kind: str, payload: dict) -> str:
    return f'event: {kind}\ndata: {json.dumps(payload)}\n\n'


async def activity_events(
    db: AsyncIOMotorDatabase, access: StreamAccess, deadline: float,
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
    yield _event('connected', {'type': 'connected', 'status': 'online',
                               'timestamp': datetime.now(timezone.utc).isoformat()})
    last_check = datetime.now(timezone.utc) - timedelta(minutes=10)
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
                    'updated_at': {'$gt': last_check, '$lte': now},
                }).sort('updated_at', -1).to_list(length=10)
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
            payload = {key: task.get(key) for key in (
                'id', 'task_type', 'campaign_id', 'lead_id', 'account_id',
            )}
            updated_at = task.get('updated_at')
            payload['timestamp'] = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at or now.isoformat())
            yield _event('task_completed', payload)
        last_check = now
        reason = await admission()
        if reason:
            if reason != 'expired':
                yield closure(reason)
            return
        yield _event('heartbeat', {'type': 'heartbeat', 'timestamp': now.isoformat()})
        await asyncio.sleep(min(STREAM_POLL_SECONDS, max(0, deadline - time.monotonic())))
