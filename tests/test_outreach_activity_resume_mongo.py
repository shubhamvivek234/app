"""Native paging/resume contracts for retained task observations, no provider calls."""
from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from starlette.requests import Request

from outreach.api.analytics import live_activity_feed
from outreach.core.activity_stream import task_cursor
from tests.test_outreach_stream_access_mongo import prepare, STREAM_USER, WORKSPACE
from tests.test_outreach_stream_access_mongo import http_server, next_event
from tests.test_outreach_authorized_context import app_for
from outreach.api.analytics import router
import httpx
from bson.codec_options import CodecOptions
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


def data(event):
    return json.loads(next(line[6:] for line in event.splitlines() if line.startswith('data: ')))


async def open_stream(db, token=None):
    request = Request({'type': 'http', 'headers': [(b'last-event-id', token.encode())] if token else []})
    return (await live_activity_feed(request=request, current_user=STREAM_USER, db=db)).body_iterator


async def insert(db, identifier, stamp, **extra):
    await db.outreach_tasks.insert_one({'workspace_id': WORKSPACE, 'id': identifier,
        'updated_at': stamp, 'status': 'completed', 'task_type': 'send_message', **extra})


async def test_native_burst_drains_all_pages_in_chronological_tied_id_order(real_db):
    await prepare(real_db)
    stamp = datetime.now(timezone.utc) - timedelta(seconds=1)
    identifiers = [f'task-{i:04}' for i in range(237)]
    for identifier in reversed(identifiers):
        await insert(real_db, identifier, stamp, private_result='must-not-be-read')
    stream = await open_stream(real_db)
    try:
        assert 'event: connected' in await anext(stream)
        events = [await anext(stream) for _ in identifiers]
        assert [data(event)['id'] for event in events] == identifiers
        assert len({data(event)['event_id'] for event in events}) == 237
        assert all('id: ' + data(event)['event_id'] in event and 'private_result' not in event for event in events)
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


async def test_native_last_event_id_resumes_with_ties_without_replay(real_db):
    await prepare(real_db)
    stamp = datetime.now(timezone.utc) - timedelta(seconds=1)
    for identifier in ('a', 'b', 'c'):
        await insert(real_db, identifier, stamp)
    stream = await open_stream(real_db)
    await anext(stream)
    first = data(await anext(stream))
    await stream.aclose()
    stream = await open_stream(real_db, first['event_id'])
    try:
        assert 'event: connected' in await anext(stream)
        assert [data(await anext(stream))['id'] for _ in range(2)] == ['b', 'c']
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('identifier', ['🚀' * 256, '\n' * 256])
async def test_native_every_supported_identifier_generates_a_resumable_cursor(real_db, identifier):
    await prepare(real_db)
    await insert(real_db, identifier, datetime.now(timezone.utc) - timedelta(seconds=1))
    stream = await open_stream(real_db)
    await anext(stream)
    event = data(await anext(stream))
    await stream.aclose()
    stream = await open_stream(real_db, event['event_id'])
    try:
        assert 'event: connected' in await anext(stream)
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('kind', ['malformed', 'other-workspace', 'old', 'future', 'deleted', 'changed', 'oversize'])
async def test_native_unusable_resume_never_silently_restarts(real_db, kind):
    await prepare(real_db)
    stamp = datetime.now(timezone.utc) - timedelta(seconds=1)
    await insert(real_db, 'anchor', stamp)
    token = task_cursor(WORKSPACE, stamp.replace(microsecond=stamp.microsecond // 1000 * 1000), 'anchor')
    if kind == 'malformed': token = 'bad-token'
    if kind == 'oversize': token = 'x' * 5000
    if kind == 'other-workspace': token = task_cursor('foreign', stamp, 'anchor')
    if kind == 'old': token = task_cursor(WORKSPACE, stamp - timedelta(days=2), 'anchor')
    if kind == 'future': token = task_cursor(WORKSPACE, stamp + timedelta(days=2), 'anchor')
    if kind == 'deleted': await real_db.outreach_tasks.delete_many({})
    if kind == 'changed': await real_db.outreach_tasks.update_one({'id': 'anchor'}, {'$set': {'updated_at': stamp + timedelta(seconds=1)}})
    stream = await open_stream(real_db, token)
    try:
        event = await anext(stream)
        assert data(event)['reason'] == 'resume_unavailable'
        with pytest.raises(StopAsyncIteration): await anext(stream)
    finally:
        await stream.aclose()


async def test_native_idle_poll_does_not_advance_to_clock_or_repeat_rows(real_db, monkeypatch):
    from outreach.core import activity_stream
    async def no_wait(_seconds): pass
    monkeypatch.setattr(activity_stream.asyncio, 'sleep', no_wait)
    await prepare(real_db)
    stream = await open_stream(real_db)
    try:
        await anext(stream)
        assert 'event: heartbeat' in await anext(stream)
        await insert(real_db, 'after-idle', datetime.now(timezone.utc))
        assert data(await anext(stream))['id'] == 'after-idle'
        assert 'event: heartbeat' in await anext(stream)
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize('bad', [None, ['alias'], 123])
async def test_native_bad_task_identity_reports_unavailable(real_db, bad):
    await prepare(real_db)
    await insert(real_db, bad, datetime.now(timezone.utc))
    stream = await open_stream(real_db)
    try:
        await anext(stream)
        assert data(await anext(stream))['reason'] == 'unavailable'
    finally:
        await stream.aclose()


async def test_actual_http_last_event_id_reconnect_uses_scoped_anchor(real_db):
    await prepare(real_db)
    stamp = datetime.now(timezone.utc) - timedelta(seconds=1)
    await insert(real_db, 'a', stamp)
    await insert(real_db, 'b', stamp)
    app = app_for(real_db, router, lambda: STREAM_USER.copy())
    async with http_server(app) as url:
        async with httpx.AsyncClient(base_url=url, timeout=4) as client:
            async with client.stream('GET', '/analytics/live-feed') as response:
                lines = response.aiter_lines()
                assert 'event: connected' in await next_event(lines)
                first = data(await next_event(lines))
                assert first['id'] == 'a'
            async with client.stream('GET', '/analytics/live-feed', headers={'Last-Event-ID': first['event_id']}) as response:
                lines = response.aiter_lines()
                assert 'event: connected' in await next_event(lines)
                assert data(await next_event(lines))['id'] == 'b'
                assert 'event: heartbeat' in await next_event(lines)


async def test_native_default_naive_bson_clock_keeps_exact_resume_position(real_db):
    await prepare(real_db)
    await insert(real_db, 'anchor', datetime.now(timezone.utc) - timedelta(seconds=1))
    db = real_db.with_options(codec_options=CodecOptions(tz_aware=False))
    stream = await open_stream(db)
    await anext(stream)
    event = data(await anext(stream))
    await stream.aclose()
    stream = await open_stream(db, event['event_id'])
    try:
        assert 'event: connected' in await anext(stream)
        assert 'event: heartbeat' in await anext(stream)
    finally:
        await stream.aclose()


async def test_native_runtime_index_cutover_installs_chronological_feed_index(real_db, monkeypatch):
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME', real_db.name)
    await create_all_indexes(real_db.client)
    indexes = await real_db.outreach_tasks.index_information()
    expected = [('workspace_id', 1), ('status', 1), ('updated_at', 1), ('id', 1)]
    assert any(index['key'] == expected for index in indexes.values())
