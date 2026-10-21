"""Native discovery and original-job reads; no provider requests or positive grants."""
from datetime import datetime, timedelta, timezone
import os

from bson import Code
from fastapi import HTTPException, Response
import pytest

from outreach.api.accounts import get_connection_job, discover_connection_jobs, ConnectCookieRequest
from outreach.api.connection_jobs import queue_connection
from outreach.core.sender_verification_recovery import discover_jobs, recovery_context
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_sender_recovery import USER, record

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


async def completed(db):
    await db.outreach_connection_jobs.insert_one(record(status='completed', account_id='sender',
        credential_generation='g', expected_linkedin_urn='urn:sender'))
    await db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'w', 'status': 'active',
        'account_name': 'Synthetic sender', 'credential_generation': 'g', 'linkedin_urn': 'urn:sender',
        'session_cookie_enc': 'never-return', 'connection_finalization': {'job_id': 'job', 'generation': 'g',
            'ever_installed': True, 'state': 'closed', 'completion': 'verified_install', 'owner_token': 'never-return'}})


async def read(db, **kwargs):
    return await get_connection_job('job', current_user=USER, db=db,
        scope_digest=recovery_context(USER)['scope_digest'], **kwargs)


async def test_lost_post_ack_is_discoverable_from_saved_job_without_replay(replica_db):
    await replica_db.outreach_connection_jobs.insert_one(record())
    response = Response()
    value = await discover_connection_jobs(response, current_user=USER, db=replica_db)
    assert value['jobs'][0]['job_id'] == 'job' and value['jobs'][0]['status'] == 'running'
    assert response.headers['cache-control'] == 'private, no-store'
    assert await replica_db.outreach_accounts.count_documents({}) == 0
    assert 'never-return' not in str(value)


async def test_current_completed_job_returns_only_minimal_account_after_exact_binding(replica_db):
    await completed(replica_db)
    value = await read(replica_db)
    assert value['account_current'] is True
    assert set(value['account']) == {'id', 'workspace_id', 'status', 'account_name'}
    assert 'never-return' not in str(value)


@pytest.mark.parametrize('change', [
    {'status': 'disconnected'}, {'status': ['active']}, {'status': Code('active')}, {'is_deleted': True}, {'is_deleted': []},
    {'id': ['sender']}, {'workspace_id': ['w']}, {'credential_generation': 'replacement'}, {'linkedin_urn': 'urn:replacement'},
    {'connection_finalization.state': 'prepared'}, {'connection_finalization.job_id': 'other'},
    {'connection_finalization.job_id': Code('job')}, {'connection_finalization.generation': Code('g')},
    {'connection_finalization.ever_installed': 1}, {'connection_finalization.completion': 'disconnected'},
])
async def test_stale_malformed_or_replaced_account_is_never_reported_connected(replica_db, change):
    await completed(replica_db)
    await replica_db.outreach_accounts.update_one({}, {'$set': change})
    value = await read(replica_db)
    assert value['account_current'] is False and 'account' not in value


async def test_duplicate_native_job_or_account_holds_without_first_row_adoption(replica_db):
    await completed(replica_db)
    await replica_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'w', 'status': 'active'})
    assert not (await read(replica_db))['account_current']
    await replica_db.outreach_connection_jobs.insert_one(record())
    with pytest.raises(HTTPException) as failure:
        await read(replica_db)
    assert failure.value.status_code == 503


async def test_discovery_strictly_scopes_actor_and_current_workspace(replica_db):
    await replica_db.outreach_connection_jobs.insert_many([record(), record(id='actor', user_id='other'),
        record(id='workspace', workspace_id='other')])
    assert [item['job_id'] for item in (await discover_jobs(replica_db, USER))['jobs']] == ['job']
    with pytest.raises(HTTPException) as failure:
        await get_connection_job('job', current_user={**USER, 'default_workspace_id': 'other'}, db=replica_db,
            scope_digest=recovery_context(USER)['scope_digest'])
    assert failure.value.status_code == 409


async def test_connection_post_with_stale_context_cannot_allocate_or_store_anything(replica_db):
    with pytest.raises(HTTPException) as failure:
        await queue_connection(ConnectCookieRequest(li_at='synthetic', jsession_id='synthetic', country_code='IN',
            connection_scope_digest=recovery_context(USER)['scope_digest']), {**USER, 'firebase_uid': 'different'}, replica_db)
    assert failure.value.status_code == 409
    for name in ('outreach_connection_jobs', 'outreach_accounts', 'outreach_sender_slots', 'outreach_proxy_leases', 'outreach_connection_locks'):
        assert await replica_db[name].count_documents({}) == 0


async def test_array_workspace_or_actor_never_appears_as_authorized_discovery(replica_db):
    await replica_db.outreach_connection_jobs.insert_one(record(workspace_id=['w']))
    with pytest.raises(HTTPException) as failure:
        await discover_jobs(replica_db, USER)
    assert failure.value.status_code == 503


async def test_unbound_lock_and_overflow_are_support_holds(replica_db):
    await replica_db.outreach_connection_locks.insert_one({'_id': 'sender', 'workspace_id': 'w', 'job_id': 'absent'})
    assert (await discover_jobs(replica_db, USER))['operator_review_required'] is True
    await replica_db.outreach_connection_jobs.insert_many([record(id=str(i)) for i in range(21)])
    with pytest.raises(HTTPException) as failure:
        await discover_jobs(replica_db, USER)
    assert failure.value.status_code == 503


async def test_expired_terminal_is_not_silently_selected_in_recovery(replica_db):
    await replica_db.outreach_connection_jobs.insert_many([record(id='old', status='completed',
        created_at=datetime.now(timezone.utc) - timedelta(days=2)), record(id='pending',
        created_at=datetime.now(timezone.utc) - timedelta(days=2))])
    assert [item['job_id'] for item in (await discover_jobs(replica_db, USER))['jobs']] == ['pending']
