"""Pinned stream admission through production generator; no legacy guard stubs."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference

from outreach.api.analytics import live_activity_feed
from outreach.core.suppression import guard_scope
from tests.outreach_memory import Collection, Database

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER = {'user_id': 'actor', 'default_workspace_id': 'original', 'firebase_uid': 'synthetic-firebase'}


class AuthorityCollection(Collection):
    def with_options(self, **kwargs):
        if 'read_concern' in kwargs:
            assert kwargs['read_concern'] == ReadConcern('majority')
        else:
            assert kwargs['write_concern'].document == {'w': 'majority'}
        return self


class StreamDatabase(Database):
    def with_options(self, **kwargs):
        assert kwargs['read_concern'] == ReadConcern('majority')
        assert kwargs['read_preference'] == ReadPreference.PRIMARY
        return self


def stream_db():
    db = StreamDatabase(
        users=[{**USER, 'status': 'active'}],
        workspaces=[{'workspace_id': 'original', 'owner_id': 'another'}],
        workspace_members=[{'workspace_id': 'original', 'user_id': 'actor', 'role': 'viewer'}],
        outreach_tasks=[],
    )
    db.collections['account_erasure_tombstones'] = AuthorityCollection()
    return db


async def task(db, identifier='private-task', **extra):
    await db.outreach_tasks.insert_one({'id': identifier, 'workspace_id': 'original',
        'status': 'completed', 'updated_at': datetime.now(timezone.utc), **extra})


async def stream_for(db):
    return (await live_activity_feed(current_user=deepcopy(USER), db=db)).body_iterator


@pytest.mark.parametrize('change', ['membership', 'workspace', 'owner', 'role', 'deleted-user', 'missing-user', 'identity', 'erasure', 'tombstone'])
async def test_stream_stops_before_reading_new_activity_after_access_changes(change):
    db = stream_db()
    if change == 'owner':
        db.workspace_members.docs.clear()
        db.workspaces.docs[0]['owner_id'] = USER['user_id']
    stream = await stream_for(db)
    try:
        assert 'event: connected' in await anext(stream)
        if change == 'membership': db.workspace_members.docs.clear()
        if change == 'workspace': db.workspaces.docs.clear()
        if change == 'owner': db.workspaces.docs[0]['owner_id'] = 'another'
        if change == 'role': db.workspace_members.docs[0]['role'] = 'unrecognized'
        if change == 'deleted-user': db.users.docs[0]['status'] = 'deletion_pending'
        if change == 'missing-user': db.users.docs.clear()
        if change == 'identity': db.users.docs[0]['firebase_uid'] = 'replacement'
        if change == 'erasure':
            await db.outreach_suppression_guards.insert_one({**guard_scope('original'), 'erasure_state': 'stopped'})
        if change == 'tombstone':
            from outreach.core.erasure import stop_identity
            await stop_identity(db, USER['firebase_uid'])
        # A fallback workspace must never authorize this original stream.
        await db.workspace_members.insert_one({'workspace_id': 'other', 'user_id': 'actor', 'role': 'admin'})
        await task(db)
        event = await anext(stream)
        assert 'event: stream_closed' in event and 'access_changed' in event
        assert 'private-task' not in event and 'actor' not in event and 'original' not in event
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_revocation_discards_already_queried_rows_between_yields():
    db = stream_db()
    await task(db, 'first')
    await task(db, 'buffered')
    stream = await stream_for(db)
    try:
        assert 'event: connected' in await anext(stream)
        assert 'event: task_completed' in await anext(stream)
        db.workspace_members.docs.clear()
        assert 'event: stream_closed' in await anext(stream)
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_access_change_before_first_iteration_never_greets_as_connected():
    db = stream_db()
    stream = await stream_for(db)
    db.workspace_members.docs.clear()
    try:
        assert 'event: stream_closed' in await anext(stream)
    finally:
        await stream.aclose()


async def test_owner_without_membership_and_viewer_membership_remain_readable():
    for owner in (False, True):
        db = stream_db()
        if owner:
            db.workspace_members.docs.clear()
            db.workspaces.docs[0]['owner_id'] = USER['user_id']
        await task(db, 'permitted')
        stream = await stream_for(db)
        try:
            assert 'event: connected' in await anext(stream)
            assert 'permitted' in await anext(stream)
            assert 'event: heartbeat' in await anext(stream)
        finally:
            await stream.aclose()


@pytest.mark.parametrize('empty', [False, True])
async def test_revocation_during_task_query_blocks_tasks_and_heartbeat(empty):
    db = stream_db()
    if not empty: await task(db)
    original_find = db.outreach_tasks.find
    def find(*args, **kwargs):
        cursor = original_find(*args, **kwargs)
        original_list = cursor.to_list
        async def fetched(*args, **kwargs):
            result = await original_list(*args, **kwargs)
            db.workspace_members.docs.clear()
            return result
        cursor.to_list = fetched
        return cursor
    db.outreach_tasks.find = find
    stream = await stream_for(db)
    try:
        assert 'event: connected' in await anext(stream)
        assert 'event: stream_closed' in await anext(stream)
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('failure', ['membership-read', 'task-read', 'auth-timeout', 'task-timeout'])
async def test_failures_end_stream_with_sanitized_control(failure, monkeypatch, caplog):
    from outreach.core import activity_stream
    db = stream_db()
    monkeypatch.setattr(activity_stream, 'STREAM_READ_TIMEOUT_SECONDS', 0.01)
    stream = await stream_for(db)
    try:
        assert 'event: connected' in await anext(stream)
        async def fail(*args, **kwargs):
            raise RuntimeError('secret-database-endpoint-and-password')
        async def hang(*args, **kwargs):
            await asyncio.Event().wait()
        if failure == 'membership-read': db.workspace_members.find_one = fail
        if failure == 'auth-timeout': db.users.find_one = hang
        if failure in {'task-read', 'task-timeout'}:
            original_find = db.outreach_tasks.find
            def find(*args, **kwargs):
                cursor = original_find(*args, **kwargs)
                cursor.to_list = fail if failure == 'task-read' else hang
                return cursor
            db.outreach_tasks.find = find
        event = await asyncio.wait_for(anext(stream), timeout=0.5)
        assert 'event: stream_closed' in event and 'unavailable' in event
        assert 'secret' not in event and 'secret' not in caplog.text
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_cancellation_propagates_without_a_fake_access_error():
    db = stream_db()
    stream = await stream_for(db)
    try:
        await anext(stream)
        async def cancel(*args, **kwargs): raise asyncio.CancelledError
        db.users.find_one = cancel
        with pytest.raises(asyncio.CancelledError): await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('when', ['before-first-iteration', 'after-read', 'between-buffered-rows'])
async def test_lifetime_is_bounded_before_and_after_awaits(when, monkeypatch):
    import time
    from types import SimpleNamespace
    from outreach.api import analytics
    from outreach.core import activity_stream
    db = stream_db()
    clock = [time.monotonic()]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(activity_stream, 'time', fake_time)
    monkeypatch.setattr(analytics, 'time', fake_time)
    if when == 'before-first-iteration': monkeypatch.setattr(analytics, 'STREAM_LIFETIME_SECONDS', 0)
    await task(db, 'first')
    await task(db, 'buffered')
    stream = await stream_for(db)
    try:
        if when == 'after-read':
            original = db.users.find_one
            async def slow(*args, **kwargs):
                result = await original(*args, **kwargs)
                clock[0] += 301
                return result
            db.users.find_one = slow
        if when == 'between-buffered-rows':
            assert 'event: connected' in await anext(stream)
            assert 'event: task_completed' in await anext(stream)
            clock[0] += 301
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_unreadable_database_configuration_ends_without_details(caplog):
    db = stream_db()
    def fail(**kwargs): raise RuntimeError('secret-config')
    db.with_options = fail
    stream = await stream_for(db)
    try:
        event = await anext(stream)
        assert 'unavailable' in event and 'secret' not in event and 'secret' not in caplog.text
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_idle_poll_rechecks_access_and_does_not_treat_cancellation_as_error(monkeypatch):
    from outreach.core import activity_stream
    db = stream_db()
    async def no_wait(seconds): pass
    monkeypatch.setattr(activity_stream.asyncio, 'sleep', no_wait)
    stream = await stream_for(db)
    try:
        await anext(stream)
        assert 'event: heartbeat' in await anext(stream)
        db.workspace_members.docs.clear()
        assert 'event: stream_closed' in await anext(stream)
    finally:
        await stream.aclose()
