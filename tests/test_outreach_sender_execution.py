from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.sender_execution import SenderExecution
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_sender_ownership_serializes_different_actions_and_fences_old_owner():
    db = Database()
    guard = SenderExecution(db)
    now = datetime.now(timezone.utc)
    assert await guard.acquire("w", "a", "old", now=now)
    assert not await guard.acquire("w", "a", "other", now=now)
    assert await guard.acquire("w", "a", "new", now=now + timedelta(minutes=3))
    assert not await guard.begin("w", "a", "old", now=now + timedelta(minutes=3))
    assert not await guard.release("w", "a", "old")
    assert await guard.begin("w", "a", "new", now=now + timedelta(minutes=3))
    assert not await guard.acquire("w", "a", "retry", now=now + timedelta(days=1))
    assert not await guard.release("other", "a", "new")
    assert await guard.release("w", "a", "new")
    assert await guard.acquire("w", "a", "next", now=now + timedelta(days=1))


@pytest.mark.asyncio
async def test_database_failure_denies_sender_ownership(monkeypatch):
    from unittest.mock import AsyncMock
    db = Database()
    monkeypatch.setattr(db.outreach_sender_execution, "insert_one", AsyncMock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(RuntimeError):
        await SenderExecution(db).acquire("w", "a", "owner")
