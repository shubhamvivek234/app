"""Native majority-transaction sender disconnect ordering; no provider traffic."""
import asyncio
from datetime import datetime, timedelta, timezone
import os

import pytest
from fastapi import HTTPException

from outreach.api.accounts import disconnect_account
from outreach.core.connection_repair import ConnectionRepair
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_connection_repair import database, prepared
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'default_workspace_id': 'w', 'user_id': 'u'}


async def seed(db):
    for name, collection in database().collections.items():
        if collection.docs:
            await db[name].insert_many(collection.docs)
    return await prepared(db)


@pytest.mark.parametrize('ordering', ['before_install', 'after_install', 'concurrent'])
async def test_disconnect_wins_every_install_order(replica_db, ordering):
    service, job = await seed(replica_db)
    updates = {'session_cookie_enc': 'new-cipher', 'status': 'active'}
    if ordering == 'after_install':
        assert await service.install(job, 'owner', 'g', updates)
        await disconnect_account('a', current_user=USER, db=replica_db)
    elif ordering == 'before_install':
        await disconnect_account('a', current_user=USER, db=replica_db)
        assert not await service.install(job, 'owner', 'g', updates)
    else:
        await asyncio.gather(service.install(job, 'owner', 'g', updates),
            disconnect_account('a', current_user=USER, db=replica_db))
    account = await replica_db.outreach_accounts.find_one({'id': 'a'})
    assert account['status'] == 'disconnected' and not account.get('session_cookie_enc')
    assert account['connection_finalization']['completion'] == 'disconnected'
    saved = await replica_db.outreach_connection_jobs.find_one({'id': 'j'})
    assert not saved.get('li_at_enc') and saved.get('custody_expired_at')
    assert await replica_db.outreach_proxy_leases.count_documents({}) == 1
    assert await replica_db.outreach_sender_slots.count_documents({}) == 1
    await service.close_fence(job)
    assert (await replica_db.outreach_accounts.find_one({'id': 'a'}))['status'] == 'disconnected'


async def test_disconnect_rolls_back_all_stops_if_campaign_write_fails(replica_db, monkeypatch):
    await seed(replica_db)
    await replica_db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': 'w',
        'status': 'warming_up', 'auto_launch_enabled': True, 'sender_account_ids': ['a']})
    before_account = await replica_db.outreach_accounts.find_one({'id': 'a'})
    before_job = await replica_db.outreach_connection_jobs.find_one({'id': 'j'})
    original = SuppressionCollection.update_many
    async def fail(self, *args, **kwargs):
        if self.collection.name == 'outreach_campaigns':
            raise SuppressionUnavailable('synthetic rollback')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_many', fail)
    with pytest.raises(HTTPException) as failure:
        await disconnect_account('a', current_user=USER, db=replica_db)
    assert failure.value.status_code == 503
    assert await replica_db.outreach_accounts.find_one({'id': 'a'}) == before_account
    assert await replica_db.outreach_connection_jobs.find_one({'id': 'j'}) == before_job
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'warming_up'


async def test_disconnect_scopes_jobs_tasks_and_campaigns_to_current_workspace(replica_db):
    await seed(replica_db)
    await replica_db.outreach_accounts.insert_one({'id': 'a', 'workspace_id': 'other', 'status': 'active'})
    await replica_db.outreach_connection_jobs.insert_one({'id': 'foreign', 'workspace_id': 'other',
        'sender_id': 'a', 'status': 'running', 'li_at_enc': 'foreign'})
    for workspace in ('w', 'other'):
        await replica_db.outreach_tasks.insert_one({'workspace_id': workspace, 'id': workspace,
            'assigned_account_id': 'a', 'status': 'queued'})
        await replica_db.outreach_campaigns.insert_one({'id': workspace, 'workspace_id': workspace,
            'sender_account_ids': ['a'], 'status': 'warming_up', 'auto_launch_enabled': True})
    await disconnect_account('a', current_user=USER, db=replica_db)
    assert (await replica_db.outreach_accounts.find_one({'workspace_id': 'other'}))['status'] == 'active'
    assert (await replica_db.outreach_connection_jobs.find_one({'id': 'foreign'}))['li_at_enc'] == 'foreign'
    assert (await replica_db.outreach_tasks.find_one({'workspace_id': 'w'}))['status'] == 'cancelled'
    assert (await replica_db.outreach_tasks.find_one({'workspace_id': 'other'}))['status'] == 'queued'
    assert (await replica_db.outreach_campaigns.find_one({'workspace_id': 'w'}))['auto_launch_enabled'] is False
    assert (await replica_db.outreach_campaigns.find_one({'workspace_id': 'other'}))['auto_launch_enabled'] is True


async def test_fresh_explicit_reconnect_after_disconnect_can_install(replica_db):
    await seed(replica_db)
    await disconnect_account('a', current_user=USER, db=replica_db)
    # Distinct operator-authorized operation after the original custody is closed.
    await replica_db.outreach_connection_jobs.delete_many({})
    await replica_db.outreach_connection_locks.delete_many({})
    now = datetime.now(timezone.utc) + timedelta(milliseconds=1)
    await replica_db.outreach_connection_jobs.insert_one({'id': 'new', 'sender_id': 'a', 'workspace_id': 'w',
        'user_id': 'u', 'reconnect': True, 'created_at': now, 'custody_expires_at': now + timedelta(minutes=15),
        'status': 'running', 'verification_owner_token': 'new-owner'})
    await replica_db.outreach_connection_locks.insert_one({'_id': 'a', 'workspace_id': 'w', 'job_id': 'new'})
    service = ConnectionRepair(replica_db)
    job = await replica_db.outreach_connection_jobs.find_one({'id': 'new'})
    await service.prepare(job, 'new-owner', 'new-generation', {'linkedin_urn': 'urn:sender'})
    await replica_db.outreach_connection_jobs.update_one({'id': 'new'}, {'$set': {'status': 'finalizing'}})
    assert await service.install(job, 'new-owner', 'new-generation', {'status': 'active', 'session_cookie_enc': 'new-cipher'})


async def test_standalone_disconnect_cannot_report_success(real_db):
    await real_db.outreach_accounts.insert_one({'id': 'a', 'workspace_id': 'w', 'status': 'active'})
    with pytest.raises(HTTPException) as failure:
        await disconnect_account('a', current_user=USER, db=real_db)
    assert failure.value.status_code == 503
    assert (await real_db.outreach_accounts.find_one({}))['status'] == 'active'
