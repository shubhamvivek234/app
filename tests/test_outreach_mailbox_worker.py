"""Reply polling remains bounded as paid sender count grows."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_reply_polling_uses_bounded_concurrency(monkeypatch):
    from celery_workers.tasks.mailbox import _sync_replies

    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[
        {"workspace_id": "ws", "sender_account_id": f"sender-{index}"}
        for index in range(12)
    ])
    db.outreach_mailboxes.find.return_value = cursor
    active = 0
    peak = 0

    async def sync_one(db_arg, *, workspace_id, sender_account_id):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"status": "healthy"}

    with patch("celery_workers.tasks.mailbox.is_shutting_down", return_value=False), \
         patch("celery_workers.tasks.mailbox.sync_mailbox_replies", new_callable=AsyncMock,
               side_effect=sync_one):
        result = await _sync_replies(db)
    assert result == {"status": "completed", "checked": 12, "healthy": 12, "stale": 0}
    assert 1 < peak <= 5


@pytest.mark.asyncio
async def test_unexpected_poll_failure_marks_only_that_mailbox_stale(monkeypatch):
    from celery_workers.tasks.mailbox import _sync_replies

    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"workspace_id": "ws", "sender_account_id": "sender"}])
    db.outreach_mailboxes.find.return_value = cursor
    db.outreach_mailboxes.update_one = AsyncMock()
    with patch("celery_workers.tasks.mailbox.is_shutting_down", return_value=False), \
         patch("celery_workers.tasks.mailbox.sync_mailbox_replies", new_callable=AsyncMock,
               side_effect=RuntimeError("private provider response")):
        result = await _sync_replies(db)
    assert result["stale"] == 1
    query, update = db.outreach_mailboxes.update_one.await_args.args
    assert query == {"workspace_id": "ws", "sender_account_id": "sender", "status": "active"}
    assert update["$set"]["sync_status"] == "stale"
    assert "private provider response" not in str(update)
