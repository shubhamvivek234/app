"""Real Mongo atomic migration, rollback and revision races; key service is fake."""
import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from outreach.core import suppression
from outreach.core.credential_migration import CredentialMigration
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityCollection
from tests.test_outreach_credential_migration import migration_db
from tests.test_outreach_session_custody import scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable local replica set is opt-in')]


@pytest_asyncio.fixture
async def real_custody_db(migration_db, monkeypatch):
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True, serverSelectionTimeoutMS=2000)
    name = 'test_unravler_custody_' + uuid.uuid4().hex
    db = client[name]
    for collection, source in migration_db.collections.items():
        if source.docs: await db[collection].insert_many(source.docs)
    try:
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def test_real_migration_receipt_retry_preserves_generation_permission_and_indexes(real_custody_db, monkeypatch):
    from db.indexes import create_all_indexes
    from outreach.core.inbox_freshness import credential_generation
    from outreach.core.session_custody import account_session
    db = real_custody_db
    service = CredentialMigration(db)
    before = await db.outreach_accounts.find_one({'id': 'a'})
    view = await service.inspect('w', 'a')
    assert (await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True))['current_matches']
    after = await db.outreach_accounts.find_one({'id': 'a'})
    assert after['status'] == 'paused' and credential_generation(after) == credential_generation(before)
    assert (await account_session(after))['li_at'] == 'private-cookie'
    assert (await db.outreach_sender_execution.find_one({}))['permission']['latched']
    monkeypatch.setattr('outreach.core.credential_migration.seal_installed', AsyncMock(side_effect=AssertionError('No retry calls')))
    assert (await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True))['current_matches']
    monkeypatch.setenv('DB_NAME', db.name)
    await create_all_indexes(db.client)
    indexes = await db.outreach_credential_migrations.index_information()
    assert any(row['key'] == [('workspace_id', 1), ('sender_id', 1), ('at', -1)] for row in indexes.values())
    assert not any('expireAfterSeconds' in row for row in indexes.values())
    receipt = await db.outreach_credential_migrations.find_one({})
    assert 'uc1:' not in str(receipt) and 'private-cookie' not in str(receipt)


async def test_real_receipt_projection_failure_rolls_back_ciphertext_install(real_custody_db, monkeypatch):
    from outreach.core.suppression import SuppressionCollection
    db = real_custody_db
    service = CredentialMigration(db)
    view = await service.inspect('w', 'a')
    before = await db.outreach_accounts.find_one({'id': 'a'})
    original = SuppressionCollection.insert_one
    async def fail(self, *args, **kwargs):
        if self.collection.name == 'outreach_credential_migrations': raise RuntimeError('local projection interrupted')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail)
    with pytest.raises(RuntimeError): await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True)
    after = await db.outreach_accounts.find_one({'id': 'a'})
    assert after['session_cookie_enc'] == before['session_cookie_enc']
    assert not await db.outreach_credential_migrations.find_one({})


@pytest.mark.parametrize('change', ['generation', 'permission', 'campaign', 'erasure'])
async def test_real_context_change_during_kms_prevents_install(real_custody_db, monkeypatch, change):
    from outreach.core import credential_migration
    db = real_custody_db
    service = CredentialMigration(db)
    view = await service.inspect('w', 'a')
    original = credential_migration.seal_installed
    async def seal_and_change(*args):
        value = await original(*args)
        if change == 'generation':
            await db.outreach_accounts.update_one({'id': 'a'}, {'$set': {'credential_generation': 'replacement'}})
        elif change == 'permission':
            await db.outreach_sender_execution.update_one({}, {'$set': {'permission.latched': False}})
        elif change == 'campaign':
            await db.outreach_campaigns.insert_one({'workspace_id': 'w', 'sender_account_ids': ['a'], 'status': 'active'})
        else:
            async def close(current):
                await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'requested'}})
            await suppression.mutate_suppression(db, 'w', close)
        return value
    monkeypatch.setattr(credential_migration, 'seal_installed', seal_and_change)
    with pytest.raises((CustodyUnavailable, suppression.SuppressionUnavailable)):
        await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True)
    assert (await db.outreach_accounts.find_one({'id': 'a'}))['session_cookie_enc'].startswith('gAAAAA')
    assert not await db.outreach_credential_migrations.find_one({})


@pytest.mark.parametrize('authority', ['outreach_accounts', 'outreach_sender_execution'])
async def test_real_edit_after_snapshot_read_retries_before_kms(real_custody_db, monkeypatch, authority):
    db = real_custody_db
    service = CredentialMigration(db)
    view = await service.inspect('w', 'a')
    seen, release = asyncio.Event(), asyncio.Event()
    original, paused = AuthorityCollection.fence, False
    async def pause(self, document, query):
        nonlocal paused
        if self.name == authority and not paused:
            paused = True
            seen.set()
            await release.wait()
        await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', pause)
    seal = AsyncMock(side_effect=AssertionError('Must deny before KMS'))
    monkeypatch.setattr('outreach.core.credential_migration.seal_installed', seal)
    task = asyncio.create_task(service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        changes = {'credential_generation': 'replacement'} if authority == 'outreach_accounts' else {'permission.latched': False}
        await db[authority].update_one({'workspace_id': 'w'}, {'$set': changes})
    finally:
        release.set()
    with pytest.raises(CustodyUnavailable): await task
    seal.assert_not_awaited()


async def test_real_lost_response_retries_saved_receipt_without_kms(real_custody_db, monkeypatch):
    db = real_custody_db
    service = CredentialMigration(db)
    view = await service.inspect('w', 'a')
    mutate = suppression.mutate_suppression
    calls = 0
    async def lose_response(*args):
        nonlocal calls
        calls += 1
        result = await mutate(*args)
        if calls == 2: raise TimeoutError('simulated response loss after commit')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lose_response)
    with pytest.raises(TimeoutError): await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True)
    monkeypatch.setattr('outreach.core.credential_migration.seal_installed', AsyncMock(side_effect=AssertionError('No retry calls')))
    assert (await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True))['current_matches']
    assert await db.outreach_credential_migrations.count_documents({}) == 1


async def test_real_erasure_denies_before_legacy_open_or_kms(real_custody_db, monkeypatch):
    db = real_custody_db
    service = CredentialMigration(db)
    view = await service.inspect('w', 'a')
    async def close(current):
        await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'requested'}})
    await suppression.mutate_suppression(db, 'w', close)
    seal = AsyncMock(side_effect=AssertionError('Must deny before KMS'))
    monkeypatch.setattr('outreach.core.credential_migration.seal_installed', seal)
    with pytest.raises(suppression.SuppressionUnavailable):
        await service.migrate('w', 'a', 'local-operator', view['digest'], workers_drained=True)
    seal.assert_not_awaited()


@pytest.mark.parametrize('close_during_seal', [False, True])
async def test_real_api_pending_insert_orders_with_erasure(real_custody_db, monkeypatch, close_during_seal):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from outreach.api import connection_jobs
    from outreach.api.accounts import ConnectCookieRequest
    from tests.test_outreach_async_connection import proxy
    db = real_custody_db
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    await db.outreach_entitlements.insert_one({'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': datetime.now(timezone.utc) + timedelta(days=1)})
    monkeypatch.setattr(connection_jobs, 'reserve_sender_proxy', AsyncMock(return_value=proxy()))
    monkeypatch.setattr(connection_jobs, 'release_sender_reservation', AsyncMock())
    publish = []
    monkeypatch.setattr(connection_jobs, '_enqueue_connection_job', lambda *args: publish.append(args))
    original = connection_jobs.seal_pending
    async def seal_and_close(*args):
        value = await original(*args)
        async def close(current):
            await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'requested'}})
        await suppression.mutate_suppression(db, 'w', close)
        return value
    if close_during_seal: monkeypatch.setattr(connection_jobs, 'seal_pending', seal_and_close)
    req = ConnectCookieRequest(li_at='local-private-cookie', jsession_id='ajax:local-csrf', country_code='IN')
    if close_during_seal:
        with pytest.raises(HTTPException) as failed:
            await connection_jobs.queue_connection(req, {'user_id': 'u', 'default_workspace_id': 'w'}, db)
        assert failed.value.status_code == 503
        assert not await db.outreach_connection_jobs.find_one({}) and not publish
    else:
        result = await connection_jobs.queue_connection(req, {'user_id': 'u', 'default_workspace_id': 'w'}, db)
        assert result['status'] == 'queued'
        row = await db.outreach_connection_jobs.find_one({})
        assert row['li_at_enc'].startswith('uc1:') and 'local-private-cookie' not in str(row)
        assert len(publish) == 1


async def test_real_erasure_scrubs_aliases_and_purges_migration_receipts(real_custody_db):
    from outreach.core.erasure import OutreachErasure
    db = real_custody_db
    await db.outreach_accounts.update_one({'id': 'a'}, {'$set': {'li_at_enc': 'legacy-cipher', 'jsession_id_enc': 'legacy-csrf'}})
    await db.outreach_credential_migrations.insert_one({'_id': 'receipt', 'workspace_id': 'w', 'sender_id': 'a', 'status': 'completed'})
    service = OutreachErasure(db)
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'local-user'})
    await service.request('w', 'local-user')
    account = await db.outreach_accounts.find_one({'id': 'a'})
    assert not account.get('session_cookie_enc') and not account.get('li_at_enc') and not account.get('jsession_id_enc')
    view = await service.inspect('w')
    await service.finish('w', 'local-operator', 'All local workspace writers are stopped and drained.',
        workers_drained=True, expected_digest=view['review_digest'])
    assert not await db.outreach_credential_migrations.find_one({})


@pytest.mark.parametrize('claimed_status', ['queued', 'running', 'finalizing'])
async def test_real_api_committed_insert_lost_response_preserves_current_job_resources(real_custody_db, monkeypatch, claimed_status):
    from datetime import datetime, timedelta, timezone
    from outreach.api import connection_jobs
    from outreach.api.accounts import ConnectCookieRequest
    from tests.test_outreach_async_connection import proxy
    db = real_custody_db
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH', 'false')
    await db.outreach_entitlements.insert_one({'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': datetime.now(timezone.utc) + timedelta(days=1)})
    async def reserve(_db, workspace, sender, country, reservation_job_id):
        await db.outreach_proxy_leases.insert_one({'_id': proxy().proxy_id, 'workspace_id': workspace,
            'sender_id': sender, 'reservation_job_id': reservation_job_id})
        return proxy()
    monkeypatch.setattr(connection_jobs, 'reserve_sender_proxy', reserve)
    release = AsyncMock(side_effect=AssertionError('Unknown storage cannot release resources'))
    monkeypatch.setattr(connection_jobs, 'release_sender_reservation', release)
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == 'save':
            await db.outreach_connection_jobs.update_one({'workspace_id': 'w'}, {'$set': {
                'status': claimed_status, 'verification_owner_token': 'new-owner',
                'finalization_prepared': claimed_status == 'finalizing'}})
            raise TimeoutError('simulated acknowledgement loss')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    result = await connection_jobs.queue_connection(ConnectCookieRequest(li_at='local-cookie', jsession_id='ajax:local', country_code='IN'),
        {'user_id': 'u', 'default_workspace_id': 'w'}, db)
    assert result['status'] == claimed_status
    assert await db.outreach_connection_locks.count_documents({}) == 1
    assert await db.outreach_sender_slots.count_documents({}) == 1
    assert await db.outreach_proxy_leases.count_documents({}) == 1
    assert (await db.outreach_connection_jobs.find_one({}))['verification_owner_token'] == 'new-owner'
    release.assert_not_awaited()
