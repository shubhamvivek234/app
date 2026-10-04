"""Production API/worker custody paths; all auth, proxy and key calls are local fakes."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from outreach.core import session_custody
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.erasure import workspace_is_open as real_workspace_is_open
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_connection_worker import make_db
from tests.test_outreach_async_connection import proxy
from tests.outreach_memory import Database


async def make_scoped_proxy_db():
    from outreach.core.proxy_custody import seal_proxy_password
    db = make_db()
    inventory = db.outreach_proxy_inventory.docs[0]
    inventory.update(await seal_proxy_password('local-proxy-password', inventory, 'ws-1'))
    return db


@pytest.mark.asyncio
async def test_api_scoped_pending_job_contains_no_plaintext_or_broker_secrets(scoped, monkeypatch):
    from outreach.api import connection_jobs
    from outreach.api.accounts import ConnectCookieRequest
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    db = Database(outreach_entitlements=[{'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'paid_through': datetime.now(timezone.utc) + timedelta(days=1), 'payment_source': 'manual_verified_invoice'}])
    monkeypatch.setattr(connection_jobs, 'reserve_sender_proxy', AsyncMock(return_value=proxy()))
    publish = []
    monkeypatch.setattr(connection_jobs, '_enqueue_connection_job', lambda *args: publish.append(args))
    req = ConnectCookieRequest(li_at='local-private-cookie', jsession_id='ajax:local-csrf', li_a='local-navigation', country_code='IN')
    result = await connection_jobs.queue_connection(req, {'user_id': 'u', 'default_workspace_id': 'w'}, db)
    job = db.outreach_connection_jobs.docs[0]
    assert result['job_id'] == job['id'] and len(publish) == 1
    assert 'local-private-cookie' not in str(job) and 'local-navigation' not in str(job) and 'ajax:local-csrf' not in str(publish)
    material = await session_custody.pending_session(job)
    assert material == {'li_at': req.li_at, 'jsession_id': req.jsession_id, 'li_a': req.li_a}
    with pytest.raises(CustodyUnavailable): await session_custody.pending_session({**job, 'sender_id': 'replacement'})


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['erasure', 'payment', 'lock', 'live'])
async def test_api_state_change_during_sealing_denies_pending_secret_insert(scoped, monkeypatch, change):
    from outreach.api import connection_jobs
    from outreach.api.accounts import ConnectCookieRequest
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    monkeypatch.setattr('outreach.core.erasure.workspace_is_open', real_workspace_is_open)
    monkeypatch.setattr(connection_jobs, '_enqueue_connection_job', lambda *_: None)
    db = Database(outreach_entitlements=[{'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'paid_through': datetime.now(timezone.utc) + timedelta(days=1), 'payment_source': 'manual_verified_invoice'}])
    monkeypatch.setattr(connection_jobs, 'reserve_sender_proxy', AsyncMock(return_value=proxy()))
    release = AsyncMock()
    monkeypatch.setattr(connection_jobs, 'release_sender_reservation', release)
    original = connection_jobs.seal_pending
    async def seal_and_change(*args):
        value = await original(*args)
        if change == 'erasure':
            from outreach.core.suppression import guard_scope
            db.outreach_suppression_guards.docs.append({**guard_scope('w'), 'erasure_state': 'requested'})
        elif change == 'payment': db.outreach_entitlements.docs[0]['is_revoked'] = True
        elif change == 'lock': db.outreach_connection_locks.docs.clear()
        else: monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
        return value
    monkeypatch.setattr(connection_jobs, 'seal_pending', seal_and_change)
    with pytest.raises(HTTPException):
        await connection_jobs.queue_connection(ConnectCookieRequest(li_at='cookie', jsession_id='ajax:csrf', country_code='IN'),
            {'user_id': 'u', 'default_workspace_id': 'w'}, db)
    assert not db.outreach_connection_jobs.docs and not db.outreach_sender_slots.docs
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_rewraps_pending_cookies_for_actual_installed_generation(scoped, monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    db = await make_scoped_proxy_db()
    job = db.outreach_connection_jobs.docs[0]
    material = {'li_at': 'local-private-cookie', 'jsession_id': 'ajax:local-csrf', 'li_a': 'local-navigation'}
    sealed = await session_custody.seal_pending(material, 'ws-1', 'sender-1', 'job-1')
    job.update(sealed)
    monkeypatch.setattr(worker.JITProxyManager, 'test_proxy_health', AsyncMock(return_value=True))
    monkeypatch.setattr(worker.ExecutionPermission, 'allowed', AsyncMock(return_value=True))
    validate = AsyncMock(return_value={'account_name': 'Local', 'linkedin_urn': 'urn:li:person:local'})
    monkeypatch.setattr(worker.SessionAuthenticator, 'validate_session_cookie', validate)
    assert (await worker._verify_sender_connection('job-1', 'ws-1', 'local', db=db))['status'] == 'completed'
    assert validate.await_args.kwargs['li_at'] == material['li_at']
    account = db.outreach_accounts.docs[0]
    assert await session_custody.account_session(account) == material
    assert account['session_cookie_enc'] != sealed['li_at_enc']
    assert 'li_at_enc' not in job and 'jsession_id_enc' not in job and 'li_a_enc' not in job
    with pytest.raises(CustodyUnavailable):
        await session_custody.account_session({**account, 'credential_generation': 'replacement'})


@pytest.mark.asyncio
async def test_worker_scope_swap_denies_before_linkedin(scoped, monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    db = await make_scoped_proxy_db()
    job = db.outreach_connection_jobs.docs[0]
    job.update(await session_custody.seal_pending({'li_at': 'cookie', 'jsession_id': 'ajax:csrf'}, 'ws-1', 'other-sender', 'job-1'))
    health, validate = AsyncMock(return_value=True), AsyncMock()
    monkeypatch.setattr(worker.JITProxyManager, 'test_proxy_health', health)
    monkeypatch.setattr(worker.SessionAuthenticator, 'validate_session_cookie', validate)
    monkeypatch.setattr(worker.ExecutionPermission, 'allowed', AsyncMock(return_value=True))
    assert (await worker._verify_sender_connection('job-1', 'ws-1', 'local', db=db))['status'] == 'failed'
    validate.assert_not_awaited()
    assert not db.outreach_accounts.docs


@pytest.mark.parametrize('field', ['session_cookie_enc', 'jsession_id', 'li_at', 'li_a'])
def test_forgotten_async_open_path_cannot_send_scoped_envelope(field):
    from outreach.engine.voyager_client import VoyagerClient
    with pytest.raises(CustodyUnavailable): VoyagerClient(**{field: 'uc1:encrypted'})


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['opening', 'rewrapping'])
async def test_custody_expiry_during_key_work_prevents_auth_or_install(scoped, monkeypatch, stage):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    db = await make_scoped_proxy_db()
    job = db.outreach_connection_jobs.docs[0]
    job.update(await session_custody.seal_pending({'li_at': 'cookie', 'jsession_id': 'ajax:csrf'}, 'ws-1', 'sender-1', 'job-1'))
    monkeypatch.setattr(worker.JITProxyManager, 'test_proxy_health', AsyncMock(return_value=True))
    monkeypatch.setattr(worker.ExecutionPermission, 'allowed', AsyncMock(return_value=True))
    validate = AsyncMock(return_value={'account_name': 'Local', 'linkedin_urn': 'urn:li:person:local'})
    monkeypatch.setattr(worker.SessionAuthenticator, 'validate_session_cookie', validate)
    original = worker.pending_session if stage == 'opening' else worker.seal_installed
    async def expire(*args):
        value = await original(*args)
        monkeypatch.setattr(worker, 'credential_deadline', lambda _: datetime.now(timezone.utc) - timedelta(seconds=1))
        return value
    monkeypatch.setattr(worker, 'pending_session' if stage == 'opening' else 'seal_installed', expire)
    assert (await worker._verify_sender_connection('job-1', 'ws-1', 'local', db=db))['status'] == 'failed'
    assert validate.await_count == (0 if stage == 'opening' else 1)
    assert not db.outreach_accounts.docs


@pytest.mark.asyncio
async def test_unreadable_storage_outcome_retains_original_lock_slot_and_lease_evidence(scoped, monkeypatch):
    from outreach.api import connection_jobs
    from outreach.api.accounts import ConnectCookieRequest
    from outreach.core import suppression
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    db = Database(outreach_entitlements=[{'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'paid_through': datetime.now(timezone.utc) + timedelta(days=1), 'payment_source': 'manual_verified_invoice'}])
    monkeypatch.setattr(connection_jobs, 'reserve_sender_proxy', AsyncMock(return_value=proxy()))
    release = AsyncMock(side_effect=AssertionError('Unknown insertion cannot release resources'))
    monkeypatch.setattr(connection_jobs, 'release_sender_reservation', release)
    async def uncertain(_db, _workspace, callback):
        await callback(_db)
        if callback.__name__ == 'save':
            monkeypatch.setattr(db.outreach_connection_jobs, 'find_one', AsyncMock(side_effect=RuntimeError('local database outage')))
            raise TimeoutError('local acknowledgement loss')
    monkeypatch.setattr(suppression, 'mutate_suppression', uncertain)
    with pytest.raises(HTTPException) as failed:
        await connection_jobs.queue_connection(ConnectCookieRequest(li_at='local-cookie', jsession_id='ajax:local', country_code='IN'),
            {'user_id': 'u', 'default_workspace_id': 'w'}, db)
    assert failed.value.status_code == 503 and 'reference ' in failed.value.detail
    assert db.outreach_sender_slots.docs and db.outreach_connection_locks.docs and db.outreach_connection_jobs.docs
    assert db.outreach_connection_locks.docs[0]['custody_expires_at']
    release.assert_not_awaited()
