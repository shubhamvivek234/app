"""Missing insertion is not proof of never-installed credentials; require exact provenance."""
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from outreach.core.connection_storage_repair import ConnectionStorageRepair, storage_account_digest
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.execution_permission import ExecutionPermission
from tests.outreach_memory import Database

@pytest.fixture
def storage_db(monkeypatch):
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    return Database(outreach_connection_locks=[{'_id': 'a', 'workspace_id': 'w', 'job_id': 'job',
        'installation_protocol': 2, 'storage_protocol': 1, 'storage_outcome_unknown': True,
        'storage_proof': {'base_account_digest': storage_account_digest(None), 'proxy_id': 'p',
            'created_slot': True, 'new_proxy_reservation': True, 'country_code': 'IN'}}],
        outreach_sender_slots=[{'_id': 'w:1', 'workspace_id': 'w', 'sender_id': 'a', 'reservation_job_id': 'job'}],
        outreach_proxy_leases=[{'_id': 'p', 'workspace_id': 'w', 'sender_id': 'a', 'reservation_job_id': 'job'}])

@pytest.mark.asyncio
async def test_stop_absent_job_installs_permanent_reference_closure_and_releases_only_owned_reservations(storage_db):
    service = ConnectionStorageRepair(storage_db)
    view = await service.inspect('w', 'job')
    assert not view['blockers']
    result = await service.resolve('w', 'job', 'operator', 'All connection writers drained; reviewed exact absent insertion.', view['digest'], workers_drained=True)
    assert result['status'] == 'storage_stopped'
    job = storage_db.outreach_connection_jobs.docs[0]
    assert 'created_at' not in job and job['repair_cleanup_complete']
    assert not storage_db.outreach_connection_locks.docs and not storage_db.outreach_sender_slots.docs and not storage_db.outreach_proxy_leases.docs
    assert storage_db.outreach_sender_execution.docs[0]['permission']['latched']
    # A retry must not release a replacement sender's reservations.
    storage_db.outreach_proxy_leases.docs.append({'_id': 'new', 'workspace_id': 'w', 'sender_id': 'a'})
    assert (await service.resolve('w', 'job', 'operator', 'Reviewed saved storage closure after complete drain.', view['digest'], workers_drained=True))['status'] == 'storage_stopped'
    assert storage_db.outreach_proxy_leases.docs[0]['_id'] == 'new'

@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['no_drain', 'live', 'evidence', 'legacy', 'base', 'job', 'fence', 'physical', 'sender_owner', 'slot', 'lease', 'stale'])
async def test_ambiguous_storage_retains_every_resource(storage_db, reason, monkeypatch):
    service = ConnectionStorageRepair(storage_db)
    view = await service.inspect('w', 'job')
    lock = storage_db.outreach_connection_locks.docs[0]
    if reason == 'live': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if reason == 'legacy': lock.pop('storage_protocol')
    if reason == 'base': storage_db.outreach_accounts.docs.append({'id': 'a', 'workspace_id': 'w', 'credential_generation': 'replacement'})
    if reason == 'job': storage_db.outreach_connection_jobs.docs.append({'id': 'job', 'workspace_id': 'w', 'sender_id': 'a', 'status': 'queued'})
    if reason == 'fence': storage_db.outreach_accounts.docs.append({'id': 'a', 'workspace_id': 'w', 'connection_finalization': {'job_id': 'job', 'state': 'closed', 'ever_installed': True}})
    if reason == 'physical': storage_db.outreach_physical_requests.docs.append({'workspace_id': 'w', 'sender_id': 'a', 'credential_generation': 'pending:job', 'status': 'response_received'})
    if reason == 'sender_owner':
        from outreach.core.sender_execution import SenderExecution
        storage_db.outreach_sender_execution.docs.append({**SenderExecution.scope('w', 'a'), 'status': 'in_flight', 'owner_token': 'old'})
    if reason == 'slot': storage_db.outreach_sender_slots.docs[0]['reservation_job_id'] = 'replacement'
    if reason == 'lease': storage_db.outreach_proxy_leases.docs[0]['reservation_job_id'] = 'replacement'
    if reason == 'stale': lock['needs_operator_repair'] = True
    before = deepcopy(storage_db.outreach_connection_locks.docs)
    with pytest.raises((CustodyUnavailable, ValueError)):
        await service.resolve('w', 'job', 'operator', 'short' if reason == 'evidence' else 'All storage writers stopped and exact resources inspected.',
            view['digest'], workers_drained=reason != 'no_drain')
    assert storage_db.outreach_connection_locks.docs == before
    assert storage_db.outreach_sender_slots.docs and storage_db.outreach_proxy_leases.docs

@pytest.mark.asyncio
async def test_reconnect_storage_closure_preserves_existing_lease_slot_and_credentials(storage_db):
    account = {'id': 'a', 'workspace_id': 'w', 'status': 'active', 'credential_generation': 'old-cookie', 'session_cookie_enc': 'private-encrypted'}
    storage_db.outreach_accounts.docs.append(deepcopy(account))
    proof = storage_db.outreach_connection_locks.docs[0]['storage_proof']
    proof.update(base_account_digest=storage_account_digest(account), created_slot=False, new_proxy_reservation=False)
    storage_db.outreach_sender_slots.docs[0].pop('reservation_job_id')
    storage_db.outreach_proxy_leases.docs[0].pop('reservation_job_id')
    service = ConnectionStorageRepair(storage_db)
    view = await service.inspect('w', 'job')
    assert not view['blockers'] and 'private-encrypted' not in str(view)
    await service.resolve('w', 'job', 'operator', 'Drained reconnect storage failed before any installation.', view['digest'], workers_drained=True)
    current = storage_db.outreach_accounts.docs[0]
    assert current['status'] == 'paused' and current['credential_generation'] == 'old-cookie' and current['session_cookie_enc'] == 'private-encrypted'
    assert storage_db.outreach_sender_slots.docs and storage_db.outreach_proxy_leases.docs

@pytest.mark.asyncio
async def test_storage_quarantine_prevents_installed_permission_grant_even_explicit_unlatch(storage_db):
    with pytest.raises(ValueError):
        await ExecutionPermission(storage_db).grant('w', 'a', 'installed', ['sync'], 'operator', clear_latch=True)
