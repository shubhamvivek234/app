"""Workspace identity claims use real snapshot/majority transactions, no transport."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os

from bson import Code
import pytest

from outreach.core.connection_repair import ConnectionRepair
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
URN = 'urn:li:fs_miniProfile:member'


async def job(db, sender='one', workspace='w', reconnect=False):
    now = datetime.now(timezone.utc)
    value = {'id': 'job-' + sender, 'workspace_id': workspace, 'sender_id': sender,
        'user_id': 'u', 'country_code': 'IN', 'status': 'running', 'verification_owner_token': sender,
        'created_at': now, 'custody_expires_at': now + timedelta(minutes=15), 'reconnect': reconnect}
    await db.outreach_connection_jobs.insert_one(deepcopy(value))
    await db.outreach_connection_locks.insert_one({'_id': sender, 'workspace_id': workspace, 'job_id': value['id']})
    return value


async def prepare(db, value, urn=URN):
    await ConnectionRepair(db).prepare(value, value['sender_id'], 'g-' + value['sender_id'], {'linkedin_urn': urn})


async def finalizing(db, value):
    await prepare(db, value)
    await db.outreach_connection_jobs.update_one({'id': value['id']}, {'$set': {'status': 'finalizing'}})
    return await db.outreach_connection_jobs.find_one({'id': value['id']})


async def test_concurrent_jobs_cannot_reserve_the_same_identity(replica_db):
    one, two = await job(replica_db), await job(replica_db, 'two')
    results = await asyncio.gather(prepare(replica_db, one), prepare(replica_db, two), return_exceptions=True)
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    assert await replica_db.outreach_accounts.count_documents({'workspace_id': 'w'}) == 1
    rows = await replica_db.outreach_connection_jobs.find({}).to_list(10)
    assert sum(row.get('finalization_prepared') is True for row in rows) == 1
    assert not (await replica_db.outreach_accounts.find_one({})).get('session_cookie_enc')


async def test_distinct_members_and_other_workspaces_remain_independent(replica_db):
    one, two, foreign = await job(replica_db), await job(replica_db, 'two'), await job(replica_db, 'foreign', 'other')
    await asyncio.gather(prepare(replica_db, one), prepare(replica_db, two, 'urn:li:fs_miniProfile:other'), prepare(replica_db, foreign))
    assert await replica_db.outreach_accounts.count_documents({}) == 3


@pytest.mark.parametrize('state', ['active', 'disconnected', 'reauth_required', 'deleted', 'closed_stub'])
async def test_existing_identity_is_reserved_regardless_of_lifecycle(replica_db, state):
    await replica_db.outreach_accounts.insert_one({'id': 'old', 'workspace_id': 'w', 'linkedin_urn': URN,
        'status': 'disconnected' if state == 'deleted' else state, 'is_deleted': state == 'deleted'})
    value = await job(replica_db)
    with pytest.raises(ValueError):
        await prepare(replica_db, value)
    assert not (await replica_db.outreach_connection_jobs.find_one({'id': value['id']})).get('finalization_prepared')


async def test_reconnect_sole_native_owner_can_prepare_and_install(replica_db):
    await replica_db.outreach_accounts.insert_one({'id': 'one', 'workspace_id': 'w', 'linkedin_urn': URN,
        'status': 'reauth_required', 'credential_generation': 'old'})
    value = await finalizing(replica_db, await job(replica_db, reconnect=True))
    assert await ConnectionRepair(replica_db).install(value, 'one', 'g-one', {'linkedin_urn': URN, 'session_cookie_enc': 'new-cipher'})


@pytest.mark.parametrize('same_public_id', [False, True])
async def test_reconnect_cannot_ignore_an_existing_duplicate_native_record(replica_db, same_public_id):
    await replica_db.outreach_accounts.insert_many([
        {'id': 'one', 'workspace_id': 'w', 'linkedin_urn': URN},
        {'id': 'one' if same_public_id else 'other', 'workspace_id': 'w', 'linkedin_urn': URN}])
    with pytest.raises(ValueError):
        await prepare(replica_db, await job(replica_db, reconnect=True))


@pytest.mark.parametrize('field', ['job', 'fence', 'account', 'updates', 'duplicate'])
async def test_install_rechecks_every_identity_binding(replica_db, field):
    value = await finalizing(replica_db, await job(replica_db))
    updates = {'linkedin_urn': URN, 'session_cookie_enc': 'must-not-install'}
    if field == 'job':
        await replica_db.outreach_connection_jobs.update_one({'id': value['id']}, {'$set': {'expected_linkedin_urn': 'urn:other'}})
    elif field in {'account', 'fence'}:
        key = 'linkedin_urn' if field == 'account' else 'connection_finalization.expected_linkedin_urn'
        await replica_db.outreach_accounts.update_one({'id': 'one'}, {'$set': {key: 'urn:other'}})
    elif field == 'updates':
        updates['linkedin_urn'] = 'urn:other'
    else:
        await replica_db.outreach_accounts.insert_one({'id': 'legacy', 'workspace_id': 'w', 'linkedin_urn': URN})
    assert not await ConnectionRepair(replica_db).install(value, 'one', 'g-one', updates)
    assert not (await replica_db.outreach_accounts.find_one({'id': 'one'})).get('session_cookie_enc')


@pytest.mark.parametrize('urn', [None, '', ' ' + URN, URN + '\n', ['urn:other'], Code(URN), 'urn:' + 'x' * 513])
async def test_noncanonical_or_nonplain_verified_identity_is_rejected(replica_db, urn):
    value = await job(replica_db)
    with pytest.raises(ValueError):
        await prepare(replica_db, value, urn)
    assert await replica_db.outreach_accounts.count_documents({}) == 0


@pytest.mark.parametrize('change', [{'workspace_id': ['w']}, {'linkedin_urn': [URN]}, {'id': ['one']}])
async def test_malformed_legacy_authority_is_not_adopted(replica_db, change):
    await replica_db.outreach_accounts.insert_one({'id': 'legacy', 'workspace_id': 'w', 'linkedin_urn': URN, **change})
    with pytest.raises(ValueError):
        await prepare(replica_db, await job(replica_db))


async def test_prepare_account_write_failure_rolls_back_job_claim(replica_db, monkeypatch):
    value = await job(replica_db)
    original = SuppressionCollection.insert_one
    async def fail(self, *args, **kwargs):
        if self.collection.name == 'outreach_accounts':
            raise ValueError('synthetic insert failure')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail)
    with pytest.raises(ValueError):
        await prepare(replica_db, value)
    assert not (await replica_db.outreach_connection_jobs.find_one({'id': value['id']})).get('finalization_prepared')


async def test_standalone_cannot_prepare_an_identity_claim(real_db):
    value = await job(real_db)
    with pytest.raises(SuppressionUnavailable):
        await prepare(real_db, value)
    assert await real_db.outreach_accounts.count_documents({}) == 0


async def test_exact_capacity_allows_last_claim_and_denies_overflow_before_writes(replica_db):
    from outreach.core.sender_identity import MAX_WORKSPACE_SENDERS
    await replica_db.outreach_accounts.insert_many([{'id': str(i), 'workspace_id': 'w', 'linkedin_urn': 'urn:member:' + str(i)}
        for i in range(MAX_WORKSPACE_SENDERS - 1)])
    first = await finalizing(replica_db, await job(replica_db))
    assert await ConnectionRepair(replica_db).install(first, 'one', 'g-one', {'linkedin_urn': URN, 'session_cookie_enc': 'cipher'})
    second = await job(replica_db, 'two')
    with pytest.raises(ValueError, match='capacity|bound'):
        await prepare(replica_db, second, 'urn:new')
    assert not (await replica_db.outreach_connection_jobs.find_one({'id': second['id']})).get('finalization_prepared')
    assert await replica_db.outreach_accounts.count_documents({}) == MAX_WORKSPACE_SENDERS


@pytest.mark.parametrize('identity', [None, 'absent'])
async def test_unrelated_not_yet_identified_row_is_not_guessed_as_an_alias(replica_db, identity):
    row = {'id': 'unidentified', 'workspace_id': 'w'}
    if identity is None:
        row['linkedin_urn'] = None
    await replica_db.outreach_accounts.insert_one(row)
    await prepare(replica_db, await job(replica_db))


@pytest.mark.parametrize('field', ['sender_id', 'workspace_id', 'user_id', 'reconnect'])
async def test_preparation_denies_changed_current_job_scope(replica_db, field):
    value = await job(replica_db)
    await replica_db.outreach_connection_jobs.update_one({'id': value['id']}, {'$set': {field: ['one'] if field != 'reconnect' else [False]}})
    with pytest.raises(ValueError):
        await prepare(replica_db, value)
    assert await replica_db.outreach_accounts.count_documents({}) == 0


async def test_preparation_lost_acknowledgement_retains_durable_identity_reservation(replica_db, monkeypatch):
    from outreach.core import suppression
    original = suppression.mutate_suppression
    async def lose_ack(*args, **kwargs):
        await original(*args, **kwargs)
        raise SuppressionUnavailable('synthetic acknowledgement loss after committed preparation')
    one, two = await job(replica_db), await job(replica_db, 'two')
    monkeypatch.setattr(suppression, 'mutate_suppression', lose_ack)
    with pytest.raises(SuppressionUnavailable):
        await prepare(replica_db, one)
    monkeypatch.setattr(suppression, 'mutate_suppression', original)
    with pytest.raises(ValueError):
        await prepare(replica_db, two)
    assert (await replica_db.outreach_accounts.find_one({}))['id'] == 'one'
    assert (await replica_db.outreach_connection_jobs.find_one({'id': one['id']}))['finalization_prepared']


@pytest.mark.parametrize('ordering', ['before', 'concurrent', 'after'])
async def test_actual_erasure_orders_with_identity_preparation(replica_db, ordering):
    from outreach.core.erasure import OutreachErasure
    await replica_db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'u'})
    value = await job(replica_db)
    if ordering == 'before':
        await OutreachErasure(replica_db).request('w', 'u')
        with pytest.raises(SuppressionUnavailable):
            await prepare(replica_db, value)
    elif ordering == 'after':
        await prepare(replica_db, value)
        await OutreachErasure(replica_db).request('w', 'u')
    else:
        result = await asyncio.gather(prepare(replica_db, value), OutreachErasure(replica_db).request('w', 'u'), return_exceptions=True)
        assert isinstance(result[1], dict)
    account = await replica_db.outreach_accounts.find_one({})
    assert account is None or account['is_deleted'] is True and account['connection_finalization']['state'] == 'closed'
