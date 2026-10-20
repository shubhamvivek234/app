"""Explicit sender disconnect fences pending installs; verification respects stops."""
from datetime import timedelta

import pytest

from outreach.api.accounts import disconnect_account
from outreach.core.connection_repair import ConnectionRepair
from tests.test_outreach_connection_repair import NOW, database, prepared


@pytest.mark.asyncio
async def test_explicit_disconnect_prevents_prepared_credentials_from_returning():
    db = database()
    service, job = await prepared(db)
    await disconnect_account('a', current_user={'default_workspace_id': 'w', 'user_id': 'u'}, db=db)
    assert not await service.install(job, 'owner', 'g', {
        'session_cookie_enc': 'new-cipher', 'status': 'active'}, now=NOW)
    account = await db.outreach_accounts.find_one({'id': 'a'})
    assert account['status'] == 'disconnected' and not account.get('session_cookie_enc')
    assert not (await db.outreach_connection_jobs.find_one({'id': 'j'})).get('li_at_enc')
    assert db.outreach_proxy_leases.docs and db.outreach_sender_slots.docs


@pytest.mark.asyncio
async def test_disconnect_before_preparation_invalidates_captured_reconnect():
    db = database()
    db.outreach_accounts.docs.append({'id': 'a', 'workspace_id': 'w', 'status': 'active',
        'credential_generation': 'old', 'linkedin_urn': 'urn:sender', 'session_cookie_enc': 'old-cipher'})
    db.outreach_connection_jobs.docs[0].update(reconnect=True, base_credential_generation='old')
    job = await db.outreach_connection_jobs.find_one({'id': 'j'})
    await disconnect_account('a', current_user={'default_workspace_id': 'w', 'user_id': 'u'}, db=db)
    with pytest.raises(ValueError, match='disconnect|stopped|owner'):
        await ConnectionRepair(db).prepare(job, 'owner', 'g', {'linkedin_urn': 'urn:sender'}, now=NOW)
    assert db.outreach_accounts.docs[0]['status'] == 'disconnected'


@pytest.mark.asyncio
@pytest.mark.parametrize('reason,deadline,expected', [
    ('session_expired', None, 'active'),
    ('session_expired', NOW - timedelta(hours=1), 'active'),
    ('rate_limited_429', NOW - timedelta(hours=1), 'active'),
    ('commercial_limit', NOW - timedelta(hours=1), 'active'),
    ('proxy_unhealthy', NOW - timedelta(hours=1), 'active'),
    ('rate_limited_429', NOW + timedelta(hours=1), 'checkpoint_detected'),
    ('rate_limited_429', None, 'checkpoint_detected'),
    ('session_expired', 'invalid', 'checkpoint_detected'),
    ('checkpoint_captcha', NOW - timedelta(hours=1), 'checkpoint_detected'),
    ('security_challenge_999', NOW - timedelta(hours=1), 'checkpoint_detected'),
    ('unknown_stop', NOW - timedelta(hours=1), 'checkpoint_detected'),
    (False, None, 'checkpoint_detected'),
    ([], None, 'checkpoint_detected'),
])
async def test_verified_reconnect_clears_only_proven_expired_or_session_stops(reason, deadline, expected):
    db = database()
    db.outreach_accounts.docs.append({'id': 'a', 'workspace_id': 'w', 'status': 'checkpoint_detected',
        'credential_generation': 'old', 'linkedin_urn': 'urn:sender', 'session_cookie_enc': 'old-cipher',
        'stop_reason': reason, 'cooldown_until': deadline, 'stopped_at': NOW - timedelta(days=1)})
    db.outreach_connection_jobs.docs[0].update(reconnect=True, base_credential_generation='old')
    service, job = await prepared(db)
    assert await service.install(job, 'owner', 'g', {'session_cookie_enc': 'new-cipher', 'status': 'active'}, now=NOW)
    account = db.outreach_accounts.docs[0]
    assert account['status'] == expected
    if expected == 'active':
        assert account.get('stop_reason') is None and account.get('cooldown_until') is None
        assert account.get('stopped_at') is None
    else:
        assert account['stop_reason'] == reason and account['cooldown_until'] == deadline


@pytest.mark.asyncio
async def test_disconnect_custody_sweep_keeps_explicit_disconnected_state():
    db = database()
    service, job = await prepared(db)
    assert await service.install(job, 'owner', 'g', {'session_cookie_enc': 'cipher', 'status': 'active'}, now=NOW)
    await disconnect_account('a', current_user={'default_workspace_id': 'w', 'user_id': 'u'}, db=db)
    await service.close_fence(job)
    assert db.outreach_accounts.docs[0]['status'] == 'disconnected'
    assert not db.outreach_accounts.docs[0].get('session_cookie_enc')


@pytest.mark.asyncio
@pytest.mark.parametrize('reason,deadline,expected', [
    ('session_expired', None, 'active'),
    ('rate_limited_429', NOW + timedelta(hours=1), 'checkpoint_detected'),
    ('checkpoint_captcha', NOW - timedelta(hours=1), 'checkpoint_detected'),
])
async def test_actual_verification_worker_keeps_the_installation_stop_policy(monkeypatch, reason, deadline, expected):
    from unittest.mock import AsyncMock, patch
    from celery_workers.tasks.outreach import _verify_sender_connection
    from tests.test_outreach_connection_worker import make_db
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    db = make_db()
    db.outreach_accounts.docs.append({'id': 'sender-1', 'workspace_id': 'ws-1',
        'linkedin_urn': 'urn:li:person:one', 'credential_generation': 'old',
        'status': 'reauth_required', 'stop_reason': reason, 'cooldown_until': deadline})
    db.outreach_connection_jobs.docs[0].update(reconnect=True, base_credential_generation='old')
    with patch('celery_workers.tasks.outreach.JITProxyManager.test_proxy_health',
            new_callable=AsyncMock, return_value=True), patch(
        'celery_workers.tasks.outreach.SessionAuthenticator.validate_session_cookie', new_callable=AsyncMock,
        return_value={'account_name': 'Pilot', 'linkedin_urn': 'urn:li:person:one'}), patch(
        'celery_workers.tasks.outreach.ExecutionPermission.allowed', new_callable=AsyncMock, return_value=True):
        result = await _verify_sender_connection('job-1', 'ws-1', 'job-1', db=db)
    assert result['status'] == 'completed'
    account = db.outreach_accounts.docs[0]
    assert account['status'] == expected
    assert account.get('stop_reason') == (None if expected == 'active' else reason)
    assert account['connection_finalization']['completion'] == 'verified_install'
