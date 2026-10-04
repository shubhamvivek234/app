"""Driver commit failures can restart only explicitly aborted DB transactions."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pymongo.errors import OperationFailure
from outreach.core import suppression, erasure

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]


async def run(monkeypatch, labels=None, failures=1, hang=False):
    body = AsyncMock(return_value='committed'); ensure = AsyncMock(); calls = 0
    error = OperationFailure('local commit failure', 112, {'errorLabels': labels or []})
    sessions = []
    class Session:
        def __init__(self): self.closed = False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): self.closed = True
        async def with_transaction(self, callback, **options):
            nonlocal calls
            calls += 1
            assert options['max_commit_time_ms'] == 5000
            assert options['read_concern'].level == 'snapshot' and options['write_concern'].document == {'w': 'majority'}
            result = await callback(self)
            if hang: await asyncio.Event().wait()
            if calls <= failures: raise error
            return result
    async def new_session():
        assert all(session.closed for session in sessions)
        session = Session(); sessions.append(session)
        return session
    db = SimpleNamespace(client=SimpleNamespace(start_session=AsyncMock(side_effect=new_session)))
    monkeypatch.setattr(suppression, 'ensure_suppression_guard', ensure)
    monkeypatch.setattr(suppression, 'touch_suppression_guard', AsyncMock())
    monkeypatch.setattr(erasure, 'workspace_is_open', AsyncMock(return_value=True))
    try:
        result = await suppression.mutate_suppression(db, 'w', body)
        assert len(sessions) == calls and all(session.closed for session in sessions)
        return result, calls, body.await_count
    except suppression.SuppressionUnavailable:
        assert len(sessions) == calls and all(session.closed for session in sessions)
        return 'denied', calls, body.await_count


async def test_explicit_transient_commit_restarts_database_only_callback(monkeypatch):
    assert await run(monkeypatch, ['TransientTransactionError']) == ('committed', 2, 2)


@pytest.mark.parametrize('labels', [[], ['UnknownTransactionCommitResult'], ['TransientTransactionError', 'UnknownTransactionCommitResult']])
async def test_unknown_or_unlabelled_commit_never_replays_callback(monkeypatch, labels):
    assert await run(monkeypatch, labels) == ('denied', 1, 1)


async def test_restarts_are_finite_even_with_immediate_driver_failures(monkeypatch):
    assert await run(monkeypatch, ['TransientTransactionError'], failures=1000) == ('denied', 3, 3)


async def test_normal_commit_invokes_callback_once(monkeypatch):
    assert await run(monkeypatch, failures=0) == ('committed', 1, 1)


async def test_original_deadline_still_bounds_driver_operation(monkeypatch):
    monkeypatch.setattr(suppression, 'SUPPRESSION_TIMEOUT_SECONDS', .02)
    assert await run(monkeypatch, hang=True) == ('denied', 1, 1)
