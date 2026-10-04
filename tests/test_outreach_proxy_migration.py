"""Drained asset migration preserves leases and all installed sender identities."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from outreach.core.proxy_migration import ProxyMigration
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.crypto import encrypt_secret
from outreach.core.sender_execution import SenderExecution
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped

@pytest.fixture
def proxy_db(scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    proxy = {'proxy_id': 'iproyal:p', 'provider': 'iproyal_static', 'host': '191.116.125.248',
        'port': 12323, 'username': 'local-user', 'country_code': 'IN', 'password_enc': encrypt_secret('private-password')}
    return Database(outreach_proxy_inventory=[{**proxy, '_id': proxy['proxy_id'], 'workspace_id': 'w',
        'last_workspace_id': 'w', 'status': 'available', 'expires_at': datetime.now(timezone.utc) + timedelta(days=1)}],
        outreach_proxy_leases=[{'_id': proxy['proxy_id'], 'workspace_id': 'w', 'sender_id': 'a'}],
        outreach_accounts=[{'id': 'a', 'workspace_id': 'w', 'status': 'paused', 'proxy': deepcopy(proxy),
            'proxy_config': deepcopy(proxy), 'credential_generation': 'cookie-generation'}],
        outreach_sender_execution=[{**SenderExecution.scope('w', 'a'), 'status': 'idle', 'permission': {'latched': True}}])

@pytest.mark.asyncio
async def test_migrate_exact_inventory_and_both_embedded_aliases_without_resume(proxy_db, monkeypatch):
    service = ProxyMigration(proxy_db)
    before = deepcopy(proxy_db.outreach_proxy_leases.docs)
    view = await service.inspect('w', 'iproyal:p')
    assert not view['blockers'] and 'private-password' not in str(view) and 'gAAAAA' not in str(view)
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    inventory, account = proxy_db.outreach_proxy_inventory.docs[0], proxy_db.outreach_accounts.docs[0]
    prepared = await prepare_proxy(account['proxy'], 'w')
    assert prepared.matches(inventory, 'w') and prepared.matches(account['proxy_config'], 'w')
    assert account['status'] == 'paused' and account['credential_generation'] == 'cookie-generation'
    assert before == proxy_db.outreach_proxy_leases.docs
    assert proxy_db.outreach_sender_execution.docs[0]['permission']['latched']
    assert 'private-password' not in str(proxy_db.outreach_credential_migrations.docs)
    monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', AsyncMock(side_effect=AssertionError('No replay')))
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    inventory['credential_generation'] = 'replaced'
    assert not (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']

@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['no_drain', 'live', 'operator', 'mode', 'stale', 'term', 'provider', 'workspace',
    'lease', 'active', 'permission', 'physical', 'lock', 'job', 'campaign', 'alias', 'multiple', 'plaintext', 'install'])
async def test_unsafe_proxy_migration_denies_before_kms(proxy_db, monkeypatch, reason):
    service = ProxyMigration(proxy_db)
    view = await service.inspect('w', 'iproyal:p')
    inventory, account = proxy_db.outreach_proxy_inventory.docs[0], proxy_db.outreach_accounts.docs[0]
    if reason == 'live': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if reason == 'mode': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    if reason == 'stale': inventory['username'] = 'changed'
    if reason == 'term': inventory['expires_at'] = datetime.now(timezone.utc)
    if reason == 'provider': inventory['provider'] = 'webshare_plan'
    if reason == 'workspace': inventory['last_workspace_id'] = 'other'
    if reason == 'lease': proxy_db.outreach_proxy_leases.docs[0]['workspace_id'] = 'other'
    if reason == 'active': account['status'] = 'active'
    if reason == 'permission': proxy_db.outreach_sender_execution.docs[0]['permission']['latched'] = False
    if reason == 'physical': proxy_db.outreach_physical_requests.docs.append({'workspace_id': 'w', 'sender_id': 'a', 'status': 'unknown_outcome'})
    if reason == 'lock': proxy_db.outreach_connection_locks.docs.append({'_id': 'a', 'workspace_id': 'w'})
    if reason == 'job': proxy_db.outreach_connection_jobs.docs.append({'workspace_id': 'w', 'proxy_id': 'iproyal:p', 'status': 'failed', 'needs_operator_repair': True})
    if reason == 'campaign': proxy_db.outreach_campaigns.docs.append({'workspace_id': 'w', 'sender_account_ids': ['a'], 'status': 'active'})
    if reason == 'alias': account['proxy_config']['username'] = 'other'
    if reason == 'multiple': proxy_db.outreach_accounts.docs.append({**deepcopy(account), 'id': 'b'})
    if reason == 'plaintext': inventory['password_enc'] = 'plaintext'
    if reason == 'install': account['connection_finalization'] = {'state': 'installed'}
    monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', AsyncMock(side_effect=AssertionError('Before KMS')))
    with pytest.raises(CustodyUnavailable):
        await service.migrate('w', 'iproyal:p', '' if reason == 'operator' else 'operator', view['digest'], workers_drained=reason != 'no_drain')
    assert not proxy_db.outreach_credential_migrations.docs

@pytest.mark.asyncio
async def test_unassigned_legacy_asset_can_migrate_and_context_change_during_kms_denies(proxy_db, monkeypatch):
    proxy_db.outreach_accounts.docs.clear(); proxy_db.outreach_proxy_leases.docs.clear()
    proxy_db.outreach_proxy_inventory.docs[0].pop('workspace_id')
    service = ProxyMigration(proxy_db)
    view = await service.inspect('w', 'iproyal:p')
    from outreach.core import proxy_migration
    original = proxy_migration.seal_proxy_password
    async def change(*args, **kwargs):
        result = await original(*args, **kwargs)
        proxy_db.outreach_proxy_inventory.docs[0]['status'] = 'expired'
        return result
    monkeypatch.setattr(proxy_migration, 'seal_proxy_password', change)
    with pytest.raises(CustodyUnavailable): await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    assert proxy_db.outreach_proxy_inventory.docs[0]['password_enc'].startswith('gAAAAA')
    monkeypatch.setattr(proxy_migration, 'seal_proxy_password', original)
    proxy_db.outreach_proxy_inventory.docs[0]['status'] = 'available'
    view = await service.inspect('w', 'iproyal:p')
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
