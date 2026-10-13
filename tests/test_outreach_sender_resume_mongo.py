"""Stopped sender recovery over owned Mongo; no physical/provider requests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os

from cryptography.fernet import Fernet
import pytest

from outreach.core.circuit_breaker import CircuitBreaker
from outreach.core.crypto import encrypt_secret
from outreach.core.suppression import SuppressionUnavailable, guard_scope
from outreach.core import session_custody
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


@pytest.fixture(autouse=True)
def local_custody(monkeypatch):
    from utils import encryption
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(encryption, '_fernet', None)
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false')
    monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH', raising=False)


async def seed(db):
    now = datetime.now(timezone.utc)
    proxy = {'proxy_id': 'asset', 'provider': 'iproyal_static', 'host': '8.8.4.4',
             'port': 1234, 'username': 'synthetic', 'password_enc': encrypt_secret('synthetic-password'),
             'country_code': 'US'}
    sender = {'id': 'sender', 'workspace_id': 'workspace', 'status': 'checkpoint_detected',
              'stop_reason': 'rate_limited_429', 'cooldown_until': now - timedelta(hours=1),
              'credential_generation': 'original', 'country_code': 'US', 'proxy': proxy,
              'session_cookie_enc': encrypt_secret('synthetic-session'), 'jsession_id': 'ajax:synthetic'}
    await db.outreach_accounts.insert_one(sender)
    await db.outreach_entitlements.insert_one({'workspace_id': 'workspace', 'status': 'active',
        'seats': 1, 'payment_source': 'manual_verified_invoice', 'paid_through': now + timedelta(days=1)})
    await db.outreach_proxy_inventory.insert_one({**proxy, '_id': 'asset', 'status': 'available',
        'workspace_id': 'workspace', 'last_workspace_id': 'workspace', 'expires_at': now + timedelta(days=2)})
    await db.outreach_proxy_leases.insert_one({'_id': 'asset', 'workspace_id': 'workspace',
        'sender_id': 'sender', 'country_code': 'US', 'provider': 'iproyal_static'})
    await db.outreach_sender_slots.insert_one({'workspace_id': 'workspace', 'sender_id': 'sender'})
    await db.outreach_tasks.insert_one({'id': 'paused', 'workspace_id': 'workspace',
        'assigned_account_id': 'sender', 'status': 'paused'})
    await db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': 'workspace', 'status': 'paused'})


async def resume(db, **kwargs):
    return await CircuitBreaker.resume_sender('sender', 'workspace', db, **kwargs)


@pytest.mark.parametrize('change', [
    {'status': 'disconnected'}, {'status': 'reauth_required'}, {'status': 'error'},
    {'status': 'active'}, {'status': 'paused'}, {'is_deleted': True},
    {'stop_reason': 'session_expired'}, {'stop_reason': 'checkpoint_captcha'},
    {'stop_reason': 'security_challenge_999'}, {'stop_reason': None},
    {'session_cookie_enc': ''}, {'jsession_id': ''},
    {'cooldown_until': 'malformed'}, {'cooldown_until': None},
])
async def test_unproven_or_ineligible_sender_remains_stopped(replica_db, change):
    await seed(replica_db)
    await replica_db.outreach_accounts.update_one({}, {'$set': change})
    original = await replica_db.outreach_accounts.find_one({})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert await replica_db.outreach_accounts.find_one({}) == original
    assert (await replica_db.outreach_tasks.find_one({}))['status'] == 'paused'


@pytest.mark.parametrize('force', [False, True])
async def test_platform_cooldown_cannot_be_overridden(replica_db, force):
    await seed(replica_db)
    await replica_db.outreach_accounts.update_one({}, {'$set': {'cooldown_until': datetime.now(timezone.utc) + timedelta(hours=1)}})
    with pytest.raises(ValueError):
        await resume(replica_db, force=force)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_valid_recovery_changes_connection_only_and_never_resumes_work(replica_db):
    await seed(replica_db)
    before = await replica_db.outreach_accounts.find_one({})
    result = await resume(replica_db)
    assert result['status'] == 'active' and result['tasks_resumed'] == 0
    assert result['campaigns_resumed'] is False and result['execution_permission_granted'] is False
    after = await replica_db.outreach_accounts.find_one({})
    assert after['credential_generation'] == before['credential_generation']
    assert after['session_cookie_enc'] == before['session_cookie_enc']
    assert after['proxy'] == before['proxy']
    assert (await replica_db.outreach_tasks.find_one({}))['status'] == 'paused'
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'
    assert await replica_db.outreach_execution_permissions.count_documents({}) == 0
    assert await replica_db.outreach_sender_execution.count_documents({}) == 0


@pytest.mark.parametrize('collection,row', [
    ('outreach_sender_execution', {'sender_id': 'sender', 'status': 'idle', 'permission': {'latched': True, 'credential_generation': 'original'}}),
    ('outreach_sender_execution', {'sender_id': 'sender', 'status': 'idle', 'owner_token': 'held'}),
    ('outreach_sender_execution', {'sender_id': 'sender', 'status': 'idle', 'permission': {'latched': False, 'credential_generation': 'replacement'}}),
    ('outreach_sender_execution', {'sender_id': 'sender', 'status': 'idle', 'permission': ['unproven']}),
    ('outreach_physical_requests', {'sender_id': 'sender', 'status': 'unknown_outcome'}),
    ('outreach_intents', {'sender_id': 'sender', 'status': 'in_flight'}),
    ('outreach_tasks', {'account_id': 'sender', 'status': 'uncertain'}),
    ('outreach_manual_actions', {'account_id': 'sender', 'status': 'projection_pending'}),
    ('outreach_connection_jobs', {'sender_id': 'sender', 'status': 'finalizing'}),
    ('outreach_connection_locks', {'_id': 'sender'}),
    ('outreach_health_controls', {'sender_id': 'sender', 'status': 'armed'}),
])
async def test_held_or_owned_work_blocks_recovery(replica_db, collection, row):
    await seed(replica_db)
    from outreach.core.execution_permission import ExecutionPermission
    identity = ExecutionPermission.scope('workspace', 'sender') if collection == 'outreach_sender_execution' else {}
    await getattr(replica_db, collection).insert_one({'workspace_id': 'workspace', **identity, **row})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('change', ['replacement', 'credentials', 'erasure', 'paid', 'proxy'])
async def test_change_during_key_preparation_blocks_final_transition(replica_db, monkeypatch, change):
    await seed(replica_db)
    original_open = session_custody.account_session
    async def changed(account):
        material = await original_open(account)
        if change == 'replacement':
            old = await replica_db.outreach_accounts.find_one({}); old.pop('_id')
            await replica_db.outreach_accounts.delete_many({})
            await replica_db.outreach_accounts.insert_one(old)
        elif change == 'credentials':
            await replica_db.outreach_accounts.update_one({}, {'$set': {'credential_generation': 'new'}})
        elif change == 'erasure':
            await replica_db.outreach_suppression_guards.insert_one({**guard_scope('workspace'), 'erasure_state': 'stopped'})
        elif change == 'paid':
            await replica_db.outreach_entitlements.update_one({}, {'$set': {'status': 'expired'}})
        else:
            await replica_db.outreach_proxy_inventory.update_one({}, {'$set': {'username': 'replacement'}})
        return material
    monkeypatch.setattr(session_custody, 'account_session', changed)
    with pytest.raises((ValueError, SuppressionUnavailable)):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_standalone_cannot_mark_sender_active(real_db):
    await seed(real_db)
    with pytest.raises(SuppressionUnavailable):
        await resume(real_db)
    assert (await real_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_foreign_sender_and_resources_are_not_adopted(replica_db):
    await seed(replica_db)
    row = deepcopy(await replica_db.outreach_accounts.find_one({})); row.pop('_id')
    row.update(workspace_id='foreign', status='disconnected')
    await replica_db.outreach_accounts.insert_one(row)
    await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({'workspace_id': 'foreign'}))['status'] == 'disconnected'


@pytest.mark.parametrize('cookie', ['', 'li_at=', 'mock_session', 'test_session', 'with\r\nheader'])
async def test_encrypted_but_unusable_session_never_recovers(replica_db, cookie):
    await seed(replica_db)
    await replica_db.outreach_accounts.update_one({}, {'$set': {'session_cookie_enc': encrypt_secret(cookie)}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('field', ['session_cookie_enc', 'proxy.password_enc'])
async def test_plaintext_custody_fallback_is_not_recovery_proof(replica_db, field):
    await seed(replica_db)
    await replica_db.outreach_accounts.update_one({}, {'$set': {field: 'synthetic-unproven-plaintext'}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('policy_name,value', [
    ('OUTREACH_LIVE_ACTIONS_ENABLED', 'false'),
    ('OUTREACH_EXECUTION_EPOCH', 'changed'),
    ('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1'),
])
async def test_policy_change_after_transition_write_rolls_back(replica_db, monkeypatch, policy_name, value):
    from outreach.core.suppression import SuppressionCollection
    await seed(replica_db)
    original = SuppressionCollection.update_one
    async def change_after_write(self, query, update, **kwargs):
        result = await original(self, query, update, **kwargs)
        if self.collection.name == 'outreach_accounts' and update.get('$set', {}).get('status') == 'active':
            monkeypatch.setenv(policy_name, value)
        return result
    monkeypatch.setattr(SuppressionCollection, 'update_one', change_after_write)
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_disabled_live_policy_does_not_open_session_keys(replica_db, monkeypatch):
    from unittest.mock import AsyncMock
    await seed(replica_db)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    opening = AsyncMock(side_effect=AssertionError('must not open keys'))
    monkeypatch.setattr(session_custody, 'account_session', opening)
    with pytest.raises(ValueError):
        await resume(replica_db)
    opening.assert_not_awaited()


def http_client(db):
    import httpx
    from fastapi import FastAPI
    from api.deps import get_current_user
    from db.mongo import get_db
    from outreach.api.router import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        'user_id': 'actor', 'default_workspace_id': 'workspace', 'workspace_ids': ['workspace']}
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def seed_access(db, role='admin'):
    await db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'another'})
    await db.workspace_members.insert_one({'workspace_id': 'workspace', 'user_id': 'actor', 'role': role})


@pytest.mark.parametrize('state,role,expected', [
    ('checkpoint_detected', 'admin', 200), ('disconnected', 'admin', 409),
    ('checkpoint_detected', 'viewer', 403),
])
async def test_resume_http_preserves_permission_and_truthful_state(replica_db, state, role, expected):
    await seed(replica_db); await seed_access(replica_db, role)
    await replica_db.outreach_accounts.update_one({}, {'$set': {'status': state}})
    async with http_client(replica_db) as client:
        result = await client.post('/outreach/accounts/sender/resume', json={})
    assert result.status_code == expected
    assert 'synthetic-session' not in result.text and 'synthetic-password' not in result.text
    assert (await replica_db.outreach_tasks.find_one({}))['status'] == 'paused'
    if expected == 200:
        assert result.json()['result']['execution_permission_granted'] is False
    else:
        assert (await replica_db.outreach_accounts.find_one({}))['status'] == state


async def test_standalone_resume_http_is_retryable_without_false_success(real_db):
    await seed(real_db); await seed_access(real_db)
    async with http_client(real_db) as client:
        result = await client.post('/outreach/accounts/sender/resume', json={})
    assert result.status_code == 503 and 'unavailable' in result.json()['detail']
    assert (await real_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('kind', ['breaker', 'shield'])
async def test_stop_helpers_never_pause_foreign_same_id_records(replica_db, kind):
    from outreach.core.safety_shield import SafetyShield
    # Foreign parents come first, exposing a wrong unscoped update_one.
    for ws in ['foreign', 'workspace']:
        await replica_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': ws, 'status': 'active'})
        await replica_db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': ws,
            'status': 'active', 'sender_account_ids': ['sender']})
        for field in ['account_id', 'assigned_account_id']:
            await replica_db.outreach_tasks.insert_one({'id': field, 'workspace_id': ws,
                field: 'sender', 'status': 'pending'})
    await replica_db.outreach_accounts.insert_one({'id': 'alternate', 'workspace_id': 'foreign', 'status': 'active'})
    await replica_db.outreach_campaigns.update_one({'workspace_id': 'workspace'}, {'$set': {'sender_account_ids': ['sender', 'alternate']}})
    if kind == 'breaker':
        await CircuitBreaker.trip_circuit_breaker('sender', 'rate_limited_429', replica_db, 'workspace')
    else:
        await SafetyShield.trip_circuit_breaker('sender', 'synthetic restriction', replica_db, 'workspace')
    assert (await replica_db.outreach_accounts.find_one({'workspace_id': 'foreign'}))['status'] == 'active'
    assert (await replica_db.outreach_campaigns.find_one({'workspace_id': 'foreign'}))['status'] == 'active'
    assert (await replica_db.outreach_campaigns.find_one({'workspace_id': 'workspace'}))['status'] == 'paused'
    assert await replica_db.outreach_tasks.count_documents({'workspace_id': 'foreign', 'status': 'pending'}) == 2
    assert await replica_db.outreach_tasks.count_documents({'workspace_id': 'workspace', 'status': 'paused'}) == 2


@pytest.mark.parametrize('kind', ['breaker', 'shield'])
async def test_stop_helpers_require_explicit_scalar_workspace(replica_db, kind):
    from outreach.core.safety_shield import SafetyShield
    await seed(replica_db)
    before = await replica_db.outreach_accounts.find_one({})
    with pytest.raises(ValueError):
        if kind == 'breaker':
            await CircuitBreaker.trip_circuit_breaker('sender', 'rate_limited_429', replica_db)
        else:
            await SafetyShield.trip_circuit_breaker('sender', 'synthetic restriction', replica_db)
    assert await replica_db.outreach_accounts.find_one({}) == before


async def test_breaker_event_deduplication_cannot_overwrite_foreign_workspace(replica_db, monkeypatch):
    from outreach.core import circuit_breaker
    from outreach.core.authorization import canonical_hash
    stamp = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return stamp
    monkeypatch.setattr(circuit_breaker, 'datetime', Clock)
    key = canonical_hash(['circuit_breaker', 'workspace', 'sender', int(stamp.timestamp())])
    await replica_db.outreach_event_outbox.insert_one({'workspace_id': 'foreign', 'dedupe_key': key, 'payload': 'private'})
    await replica_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'workspace', 'status': 'active'})
    await CircuitBreaker.trip_circuit_breaker('sender', 'rate_limited_429', replica_db, 'workspace')
    assert (await replica_db.outreach_event_outbox.find_one({'workspace_id': 'foreign'}))['payload'] == 'private'
    assert await replica_db.outreach_event_outbox.count_documents({'workspace_id': 'workspace'}) == 1


@pytest.mark.parametrize('collection,field', [
    ('outreach_accounts', 'id'), ('outreach_proxy_leases', 'sender_id'), ('outreach_sender_slots', 'sender_id'),
])
async def test_array_identity_aliases_do_not_prove_recovery_ownership(replica_db, collection, field):
    await seed(replica_db)
    await getattr(replica_db, collection).update_one({}, {'$set': {field: ['sender', 'another']}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_policy_change_during_session_open_prevents_proxy_key_open(replica_db, monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.core import sender_recovery
    await seed(replica_db)
    original = session_custody.account_session
    async def disable(account):
        result = await original(account)
        monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
        return result
    monkeypatch.setattr(session_custody, 'account_session', disable)
    proxy_open = AsyncMock(side_effect=AssertionError('must not open proxy keys'))
    monkeypatch.setattr(sender_recovery, 'prepare_proxy', proxy_open)
    with pytest.raises(ValueError):
        await resume(replica_db)
    proxy_open.assert_not_awaited()


@pytest.mark.parametrize('active_permission', [False, True])
async def test_existing_permission_is_preserved_and_live_authority_cannot_restart_implicitly(replica_db, active_permission):
    from outreach.core.execution_permission import ExecutionPermission
    await seed(replica_db)
    end = datetime.now(timezone.utc) + timedelta(seconds=30 if active_permission else -30)
    state = {**ExecutionPermission.scope('workspace', 'sender'), 'status': 'idle', 'permission_revision': 4,
        'permission': {'credential_generation': 'original', 'sources': ['sequence'], 'latched': False,
            'issued_at': end - timedelta(seconds=60), 'expires_at': end}}
    await replica_db.outreach_sender_execution.insert_one(state)
    original = await replica_db.outreach_sender_execution.find_one({})
    if active_permission:
        with pytest.raises(ValueError):
            await resume(replica_db)
        assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'
    else:
        assert (await resume(replica_db))['status'] == 'active'
    after = await replica_db.outreach_sender_execution.find_one({})
    assert after['permission'] == original['permission'] and after['permission_revision'] == 4


@pytest.mark.parametrize('key_stage', ['session', 'proxy'])
async def test_cancellation_during_key_preparation_keeps_sender_stopped(replica_db, monkeypatch, key_stage):
    import asyncio
    from unittest.mock import AsyncMock
    from outreach.core import sender_recovery
    await seed(replica_db)
    target, name = (session_custody, 'account_session') if key_stage == 'session' else (sender_recovery, 'prepare_proxy')
    monkeypatch.setattr(target, name, AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('password', ['', 'with\r\nheader'])
async def test_unusable_encrypted_proxy_password_does_not_recover(replica_db, password):
    await seed(replica_db)
    encrypted = Fernet(os.environ['ENCRYPTION_KEY'].encode()).encrypt(password.encode()).decode()
    await replica_db.outreach_accounts.update_one({}, {'$set': {'proxy.password_enc': encrypted}})
    await replica_db.outreach_proxy_inventory.update_one({}, {'$set': {'password_enc': encrypted}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_array_payment_scope_does_not_prove_paid_access(replica_db):
    await seed(replica_db)
    await replica_db.outreach_entitlements.update_one({}, {'$set': {'workspace_id': ['workspace', 'foreign']}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


async def test_duplicate_sender_authorities_require_review(replica_db):
    from outreach.core.execution_permission import ExecutionPermission
    await seed(replica_db)
    end = datetime.now(timezone.utc) - timedelta(seconds=30)
    state = {**ExecutionPermission.scope('workspace', 'sender'), 'status': 'idle',
        'permission': {'credential_generation': 'original', 'sources': ['sequence'], 'latched': False,
            'issued_at': end - timedelta(seconds=60), 'expires_at': end}}
    await replica_db.outreach_sender_execution.insert_one(state)
    await replica_db.outreach_sender_execution.insert_one({**state, '_id': 'unproven-second-authority'})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'


@pytest.mark.parametrize('field', ['session_cookie_enc', 'jsession_id'])
@pytest.mark.parametrize('corrupt', [False, True])
async def test_ciphertext_must_open_under_the_current_legacy_key(replica_db, field, corrupt):
    await seed(replica_db)
    ciphertext = 'gAAAAAinvalid' if corrupt else Fernet(Fernet.generate_key()).encrypt(b'unusable-replacement').decode()
    await replica_db.outreach_accounts.update_one({}, {'$set': {field: ciphertext}})
    with pytest.raises(ValueError):
        await resume(replica_db)
    assert (await replica_db.outreach_accounts.find_one({}))['status'] == 'checkpoint_detected'
