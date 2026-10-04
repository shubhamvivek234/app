"""Mailbox selection persists references and cannot broad-stale a reconnect."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from tests.test_outreach_durable_mailbox_sync import sync_db
from tests.test_outreach_mailbox_job_lifecycle import lifecycle

@pytest.mark.asyncio
async def test_reply_polling_uses_bounded_concurrency(sync_db, monkeypatch):
    from copy import deepcopy
    from celery_workers.tasks.mailbox import _sync_replies
    from outreach.core import mailbox_sync_jobs as jobs, erasure
    base = sync_db.outreach_mailboxes.docs[0]
    sync_db.outreach_mailboxes.docs[:] = [{**deepcopy(base), 'sender_account_id': str(i)} for i in range(12)]
    active = 0; peak = 0
    async def ensure(*args):
        nonlocal active, peak
        active += 1; peak = max(peak, active)
        await asyncio.sleep(.01); active -= 1
        return {'_id': args[-1]}
    async def control(db, workspace, operation): return await operation(db)
    monkeypatch.setattr(jobs, 'ensure_job', ensure); monkeypatch.setattr(erasure, '_control', control)
    assert await _sync_replies(sync_db) == {'status': 'completed', 'checked': 12, 'queued': 12}
    assert 1 < peak <= 5
    assert all(row.get('next_sync_at') for row in sync_db.outreach_mailboxes.docs)

@pytest.mark.asyncio
async def test_unexpected_selection_failure_cannot_stale_replacement(sync_db, monkeypatch):
    from celery_workers.tasks.mailbox import _sync_replies
    from outreach.core import mailbox_sync_jobs as jobs, erasure
    async def ensure(*args):
        sync_db.outreach_mailboxes.docs[0]['connection_job_id'] = 'replacement'
        raise RuntimeError('private response')
    async def control(db, workspace, operation): return await operation(db)
    monkeypatch.setattr(jobs, 'ensure_job', ensure); monkeypatch.setattr(erasure, '_control', control)
    assert await _sync_replies(sync_db) == {'status': 'completed', 'checked': 1, 'queued': 0}
    mailbox = sync_db.outreach_mailboxes.docs[0]
    assert mailbox['sync_status'] == 'healthy' and 'next_sync_at' not in mailbox
