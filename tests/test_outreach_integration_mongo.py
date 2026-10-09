"""Opt-in disposable replica-set verification; no AWS or provider traffic."""
import asyncio
from contextvars import ContextVar
from datetime import timedelta
import os
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure, PyMongoError
from db.indexes import ensure_integration_indexes
from outreach.core import integration_custody as custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.integration_delivery import IntegrationDelivery, now
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]

@pytest_asyncio.fixture
async def real_db(integration_db):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_unravler_integrations_' + uuid.uuid4().hex]
    try:
        for name, collection in integration_db.collections.items():
            if collection.docs: await db[name].insert_many(collection.docs)
        await ensure_integration_indexes(db)
        yield db
    finally:
        await client.drop_database(db.name)
        client.close()

@pytest.mark.parametrize('kind', ['webhook', 'slack', 'hubspot'])
async def test_concurrent_majority_workers_send_once_and_open_outside_transaction(real_db, scoped, monkeypatch, kind):
    db = real_db; inside = ContextVar('integration_txn', default=False); original = suppression.mutate_suppression
    async def txn(database, workspace, callback):
        async def marked(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await original(database, workspace, marked)
    monkeypatch.setattr(suppression, 'mutate_suppression', txn)
    opening = scoped.open
    async def open_key(*args):
        assert not inside.get()
        return await opening(*args)
    monkeypatch.setattr(scoped, 'open', open_key)
    jobs = await asyncio.gather(*(queue(db, kind) for _ in range(4)))
    assert len({job['id'] for job in jobs}) == 1
    provider = AsyncMock(return_value={'status_code': 200, 'external_id': '123'})
    await asyncio.gather(*(IntegrationDelivery(db).run('w', jobs[0]['id'], provider=provider) for _ in range(4)))
    assert provider.await_count == 1
    assert (await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w'}))['status'] == 'delivered'

async def test_rotated_configuration_orders_before_authorization(real_db, scoped, monkeypatch):
    db = real_db; job = await queue(db); opening = scoped.open
    async def rotate(*args):
        value = await opening(*args)
        previous = await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'})
        row = {key: val for key, val in previous.items() if key != '_id'}
        policy = custody.policy_digest(); row.update(await custody.seal('replacement-secret', row, 'w', 'webhook'))
        await custody.save(db, 'w', 'webhook', row, previous=previous, policy=policy, authority={"actor": "actor"})
        return value
    monkeypatch.setattr(scoped, 'open', rotate)
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'cancelled'
    provider.assert_not_awaited()

async def test_membership_revocation_transaction_denies_http(real_db):
    db = real_db; job = await queue(db)
    await db.workspace_members.update_one({'workspace_id': 'w', 'user_id': 'actor'}, {'$set': {'role': 'viewer'}})
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'cancelled'
    provider.assert_not_awaited()

async def test_erasure_orders_stop_before_dispatch_and_preserves_minimal_unknown(real_db):
    db = real_db; job = await queue(db, 'hubspot')
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'actor'})
    await db.outreach_webhook_deliveries.update_one({'workspace_id': 'w', 'id': job['id']}, {'$set': {
        'status': 'possible', 'lease_id': 'interrupted', 'leased_until': now() - timedelta(seconds=1), 'possible_at': now()}})
    service = OutreachErasure(db)
    await service.request('w', 'actor')
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'review_required'
    provider.assert_not_awaited()
    inspected = await service.inspect('w')
    await service.finish('w', 'operator', 'All writers and caches drained for local fixture.',
        workers_drained=True, expected_digest=inspected['review_digest'])
    hold = await db.outreach_erasure_holds.find_one({'workspace_id': 'w', 'operation_kind': 'integration_delivery'})
    assert hold and hold['kind'] == 'unresolved_submission' and not hold['activation_allowed']
    assert 'private-' not in str(hold) and 'person@example.com' not in str(hold) and 'target_url' not in str(hold)

async def test_ttl_is_removed_before_strict_duplicate_failure_and_unknown_kept(real_db):
    db = real_db
    await db.outreach_integrations.drop_indexes()
    await db.outreach_integrations.insert_one({'workspace_id': 'w', 'provider': 'slack'})
    await db.outreach_webhook_deliveries.create_index('created_at', expireAfterSeconds=77777777)
    with pytest.raises(OperationFailure): await ensure_integration_indexes(db)
    assert all('expireAfterSeconds' not in definition for definition in (await db.outreach_webhook_deliveries.index_information()).values())

async def test_index_cutover_quarantines_old_lease_and_normal_start_preserves_new_work(real_db):
    db = real_db
    await db.outreach_webhook_deliveries.drop_index('integration_active_slot_v2')
    await db.outreach_webhook_deliveries.insert_one({'workspace_id': 'w', 'id': 'old', 'event_id': 'old-event',
        'destination_id': 'old-hook', 'status': 'leased'})
    job = await queue(db)
    await ensure_integration_indexes(db); await ensure_integration_indexes(db)
    assert (await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w', 'id': 'old'}))['status'] == 'review_required'
    assert (await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w', 'id': job['id']}))['status'] == 'pending'

async def test_active_crm_slot_is_atomic_and_tenant_event_identity_is_independent(real_db):
    db = real_db
    outcomes = await asyncio.gather(*(IntegrationDelivery(db).queue('w', 'hubspot', 'hubspot', 'e'+str(i), {},
        actor='actor', lead_id='lead') for i in range(3)), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in outcomes) == 1
    await db.outreach_webhooks.insert_one({'workspace_id': 'other', 'id': 'hook', 'target_url': 'https://example.com/hook',
        'secret_enc': 'opaque', 'status': 'active'})
    one = await IntegrationDelivery(db).queue('w', 'webhook', 'hook', 'same-event', {})
    two = await IntegrationDelivery(db).queue('other', 'webhook', 'hook', 'same-event', {})
    assert one['id'] != two['id']

async def test_actual_standalone_denies_before_open_or_http(real_db, scoped, monkeypatch, tmp_path):
    with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1', 27029)) != 0
    root = tmp_path / 'mongo'; root.mkdir()
    process = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(root), '--port', '27029',
        '--bind_ip', '127.0.0.1', '--logpath', str(root / 'mongo.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true', serverSelectionTimeoutMS=500)
    db = client['test_unravler_integration_sa_' + uuid.uuid4().hex]
    try:
        for _ in range(40):
            try: await client.admin.command('ping'); break
            except PyMongoError: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone failed to start')
        for name in await real_db.list_collection_names():
            rows = await real_db[name].find({}).to_list(length=200)
            if rows: await db[name].insert_many(rows)
        await ensure_integration_indexes(db)
        opening = AsyncMock(wraps=scoped.open); monkeypatch.setattr(scoped, 'open', opening)
        with pytest.raises(suppression.SuppressionUnavailable): await queue(db)
        opening.assert_not_awaited()
        assert await db.outreach_webhook_deliveries.count_documents({}) == 0
    finally:
        await client.drop_database(db.name)
        client.close(); process.terminate(); process.wait(timeout=10)

async def test_global_retention_precedes_unrelated_mailbox_duplicate_failure(real_db, monkeypatch):
    from db.indexes import create_all_indexes
    db = real_db
    collections = ['outreach_webhook_deliveries', 'outreach_voice_studio_jobs',
        'outreach_voice_source_migrations', 'outreach_voice_vendor_reads', 'outreach_mailbox_connection_jobs']
    for name in collections: await db[name].create_index('created_at', expireAfterSeconds=77777777)
    await db.outreach_mailbox_connection_jobs.insert_many([
        {'workspace_id': 'w', 'sender_account_id': 'a', 'status': 'queued', 'id': str(i)} for i in range(2)])
    monkeypatch.setenv('DB_NAME', db.name)
    with pytest.raises(OperationFailure): await create_all_indexes(db.client)
    for name in collections:
        assert all('expireAfterSeconds' not in definition for definition in (await db[name].index_information()).values())

@pytest.mark.parametrize('phase', ['authority', 'source_read', 'insert', 'update', 'delete', 'cancel'])
async def test_expiry_during_configuration_await_rolls_back_all_writes(real_db, monkeypatch, phase):
    from outreach.core import integration_delivery as delivery
    from tests.test_outreach_integration_custody import resource
    db = real_db
    baseline = now()
    clock = [baseline]
    monkeypatch.setattr(delivery, 'now', lambda: clock[0])
    await db.outreach_api_keys.insert_one({'workspace_id': 'w', 'id': 'key', 'key_hash': 'hash',
        'scopes': ['leads:read'], 'expires_at': baseline + timedelta(seconds=1)})
    authority = {'api_key_id': 'key', 'key_hash': 'hash'}
    job = await queue(db)
    previous = await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'})
    row = {key: value for key, value in previous.items() if key != '_id'}
    if phase == 'insert':
        row = resource(id='new-hook')
        row.update(await custody.seal('new-secret', row, 'w', 'webhook'))
        previous = None
    method, collection_name = {
        'authority': ('update_one', 'outreach_api_keys'),
        'source_read': ('find_one', 'outreach_webhooks'),
        'insert': ('insert_one', 'outreach_webhooks'),
        'update': ('update_one', 'outreach_webhooks'),
        'delete': ('delete_one', 'outreach_webhooks'),
        'cancel': ('update_many', 'outreach_webhook_deliveries'),
    }[phase]
    original = getattr(suppression.SuppressionCollection, method)
    async def delayed(current, *args, **kwargs):
        result = await original(current, *args, **kwargs)
        if current.collection.name == collection_name:
            clock[0] = baseline + timedelta(seconds=2)
        return result
    monkeypatch.setattr(suppression.SuppressionCollection, method, delayed)
    with pytest.raises(CustodyUnavailable, match='expired'):
        if phase in {'delete', 'cancel'}:
            await custody.disconnect(db, 'w', 'webhook', 'hook', authority=authority)
        else:
            await custody.save(db, 'w', 'webhook', row, previous=previous,
                policy=custody.policy_digest(), authority=authority)
    assert 'integration_authority_revision' not in await db.outreach_api_keys.find_one({'id': 'key'})
    assert await db.outreach_webhooks.count_documents({'workspace_id': 'w'}) == 1
    if previous:
        assert await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'}) == previous
    assert (await db.outreach_webhook_deliveries.find_one({'id': job['id']}))['status'] == 'pending'

@pytest.mark.parametrize('stopped', ['deletion_pending', 'deleted', 'tombstone'])
async def test_shared_workspace_actor_stop_denies_without_erasing_other_owner(real_db, stopped):
    db = real_db
    job = await queue(db, 'slack')
    await db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'different-owner'})
    if stopped == 'tombstone':
        await db.account_erasure_tombstones.insert_one({'_id': canonical_hash(['firebase_identity', 'fixture-uid'])})
    else:
        await db.users.update_one({'user_id': 'actor'}, {'$set': {'status': stopped}})
    provider = AsyncMock(return_value={'status_code': 200})
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'cancelled'
    provider.assert_not_awaited()
    assert (await db.workspace_members.find_one({'workspace_id': 'w', 'user_id': 'actor'}))['role'] == 'owner'
    previous = await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'})
    with pytest.raises(ValueError, match='actor'):
        await custody.save(db, 'w', 'webhook', {k: v for k, v in previous.items() if k != '_id'},
            previous=previous, policy=custody.policy_digest(), authority={'actor': 'actor'})
    assert await db.outreach_webhooks.find_one({'workspace_id': 'w', 'id': 'hook'}) == previous
    internal = await IntegrationDelivery(db).queue('w', 'slack', 'slack', 'internal-event', {})
    assert (await IntegrationDelivery(db).run('w', internal['id'], provider=provider))['status'] == 'delivered'
    assert provider.await_count == 1
    assert await db.outreach_leads.count_documents({'workspace_id': 'w'}) == 1
