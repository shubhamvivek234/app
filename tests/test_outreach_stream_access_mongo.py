"""Native pinned stream checks plus real loopback HTTP; auth transport substituted."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import socket

import httpx
import pytest
import uvicorn

from outreach.api.analytics import live_activity_feed, router
from outreach.core import activity_stream
from outreach.core.erasure import stop_identity
from outreach.core.suppression import guard_scope
from tests.test_outreach_authorized_context import app_for
from tests.test_outreach_lead_workspace_scope import FOREIGN, USER, USER_ID, WORKSPACE
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable native Mongo is opt-in',
)]
STREAM_USER = {**USER, 'firebase_uid': 'synthetic-firebase'}


async def prepare(db):
    await db.users.insert_one({**STREAM_USER, 'status': 'active'})


async def task(db, identifier='private-task', **extra):
    await db.outreach_tasks.insert_one({'id': identifier, 'workspace_id': WORKSPACE,
        'status': 'completed', 'updated_at': datetime.now(timezone.utc), **extra})


@pytest.mark.parametrize('change', ['membership', 'owner', 'workspace', 'user', 'identity', 'erasure', 'tombstone', 'role'])
async def test_native_revocation_stops_original_stream_without_workspace_fallback(real_db, change):
    await prepare(real_db)
    if change == 'owner':
        await real_db.workspace_members.delete_many({})
        await real_db.workspaces.update_one({'workspace_id': WORKSPACE}, {'$set': {'owner_id': USER_ID}})
    response = await live_activity_feed(current_user=STREAM_USER, db=real_db)
    stream = response.body_iterator
    try:
        assert 'event: connected' in await anext(stream)
        if change == 'membership': await real_db.workspace_members.delete_many({})
        if change == 'owner': await real_db.workspaces.update_one({'workspace_id': WORKSPACE}, {'$set': {'owner_id': 'another'}})
        if change == 'workspace': await real_db.workspaces.delete_many({})
        if change == 'user': await real_db.users.delete_many({})
        if change == 'identity': await real_db.users.update_one({'user_id': USER_ID}, {'$set': {'firebase_uid': 'replacement'}})
        if change == 'erasure': await real_db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), 'erasure_state': 'stopped'})
        if change == 'tombstone': await stop_identity(real_db, STREAM_USER['firebase_uid'])
        if change == 'role': await real_db.workspace_members.update_one({'workspace_id': WORKSPACE}, {'$set': {'role': None}})
        await real_db.workspaces.insert_one({'workspace_id': FOREIGN, 'owner_id': USER_ID})
        await real_db.workspace_members.insert_one({'workspace_id': FOREIGN, 'user_id': USER_ID, 'role': 'admin'})
        await task(real_db)
        event = await anext(stream)
        assert 'event: stream_closed' in event and 'access_changed' in event
        assert 'private-task' not in event
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('table,field', [('users', 'user_id'), ('users', 'firebase_uid'),
    ('workspace_members', 'user_id'), ('workspace_members', 'workspace_id'), ('workspaces', 'workspace_id')])
async def test_native_array_authorities_cannot_admit_stream(real_db, table, field):
    await prepare(real_db)
    original = STREAM_USER.get(field, WORKSPACE)
    await real_db[table].update_many({}, {'$set': {field: [original, 'another']}})
    stream = (await live_activity_feed(current_user=STREAM_USER, db=real_db)).body_iterator
    try:
        assert 'event: stream_closed' in await anext(stream)
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_native_owner_alias_and_task_aliases_are_rejected(real_db):
    await prepare(real_db)
    await real_db.workspace_members.delete_many({})
    await real_db.workspaces.update_one({'workspace_id': WORKSPACE}, {'$set': {'owner_id': [USER_ID, 'another']}})
    stream = (await live_activity_feed(current_user=STREAM_USER, db=real_db)).body_iterator
    assert 'event: stream_closed' in await anext(stream)
    await stream.aclose()
    await real_db.workspaces.update_one({'workspace_id': WORKSPACE}, {'$set': {'owner_id': USER_ID}})
    await task(real_db, 'valid')
    for scope in ([WORKSPACE, FOREIGN], FOREIGN, None):
        await task(real_db, 'private-alias', workspace_id=scope)
    stream = (await live_activity_feed(current_user=STREAM_USER, db=real_db)).body_iterator
    try:
        assert 'event: connected' in await anext(stream)
        event = await anext(stream)
        assert 'valid' in event and 'private-alias' not in event
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


async def test_native_revocation_between_materialized_rows(real_db):
    await prepare(real_db)
    await task(real_db, 'first')
    await task(real_db, 'buffered')
    stream = (await live_activity_feed(current_user=STREAM_USER, db=real_db)).body_iterator
    try:
        await anext(stream)
        assert 'event: task_completed' in await anext(stream)
        await real_db.workspace_members.delete_many({})
        assert 'event: stream_closed' in await anext(stream)
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


@asynccontextmanager
async def http_server(app):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error', timeout_graceful_shutdown=1))
    server.install_signal_handlers = lambda: None
    runner = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                assert not runner.done(), 'Owned HTTP server stopped before startup'
                await asyncio.sleep(0.01)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, timeout=5)
        finally:
            if not runner.done():
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)
            listener.close()


async def next_event(lines):
    event = []
    async with asyncio.timeout(3):
        async for line in lines:
            if not line and event: return '\n'.join(event)
            if line: event.append(line)
    return None


@pytest.mark.parametrize('change', ['membership', 'erasure'])
async def test_actual_http_stream_closes_after_revocation_and_never_sends_new_activity(real_db, monkeypatch, change):
    await prepare(real_db)
    monkeypatch.setattr(activity_stream, 'STREAM_POLL_SECONDS', 0.02)
    app = app_for(real_db, router, lambda: deepcopy(STREAM_USER))
    async with http_server(app) as url:
        async with httpx.AsyncClient(base_url=url, timeout=4) as client:
            async with client.stream('GET', '/analytics/live-feed') as response:
                assert response.status_code == 200
                assert response.headers['content-type'].startswith('text/event-stream')
                lines = response.aiter_lines()
                assert 'event: connected' in await next_event(lines)
                if change == 'membership': await real_db.workspace_members.delete_many({})
                else: await real_db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), 'erasure_state': 'stopped'})
                await task(real_db)
                while True:
                    event = await next_event(lines)
                    assert event is not None
                    assert 'task_completed' not in event and 'private-task' not in event
                    if 'event: stream_closed' in event:
                        assert json.loads(event.split('data: ', 1)[1])['reason'] == 'access_changed'
                        break
                assert await next_event(lines) is None  # HTTP EOF, not a stalled producer.
