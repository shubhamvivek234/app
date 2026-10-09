"""Selected physical-IP fingerprints restore exclusions, never provider assets."""
from copy import deepcopy
import hashlib
import json
import pytest
import pytest_asyncio
from outreach.core import restore_proxy_exclusions as ri, suppression, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from tests.test_outreach_restore_suppressions import suppression_db
from tests.test_outreach_restore_epoch import restored_db, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]
IP = canonical_hash(['managed-proxy-ip-v1', '191.116.125.248'])
BINDING = 'b' * 64


@pytest.fixture(autouse=True)
def local_encryption(monkeypatch):
    from cryptography.fernet import Fernet
    from utils import encryption
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))


def source(**changes):
    doc = {'version': 1, 'workspace_guard_digest': suppression.guard_scope('w')['_id'],
           'ips': [{'ip_digest': IP, 'binding_digest': BINDING}]}
    doc.update(changes)
    return json.dumps(doc, sort_keys=True).encode()


async def apply(db, raw=None, view=None, **changes):
    raw = source() if raw is None else raw
    service = ri.RestoreProxyExclusions(db)
    view = await service.inspect('w', raw) if view is None else view
    args = dict(operator='operator', evidence_digest=EVIDENCE, source_digest=hashlib.sha256(raw).hexdigest(),
                review_digest=view['digest'], workers_drained=True)
    args.update(changes)
    return await service.apply('w', raw, **args)


@pytest.fixture(autouse=True)
def fake_closed_control(monkeypatch):
    # Private hash-only control may retain negatives after closure; real tests keep production transactions.
    async def run(db, workspace, operation): return await operation(db)
    monkeypatch.setattr('outreach.core.erasure._control', run)


async def test_negative_restoration_never_recreates_inventory_or_leases(suppression_db):
    db = suppression_db
    names = ('outreach_payment_receipts', 'outreach_entitlements', 'outreach_access_requests', 'outreach_campaigns',
             'outreach_sender_execution', 'outreach_manual_actions', 'outreach_proxy_inventory')
    before = {name: deepcopy(getattr(db, name).docs) for name in names}
    result = await apply(db)
    assert result['applied'] and not result['activation_allowed'] and not result['assets_restored']
    assert db.account_proxy_ip_guards.docs[0]['binding_digest'] == BINDING
    assert db.account_proxy_ip_guards.docs[0]['restore_reuse_blocked'] is True
    for name in names: assert getattr(db, name).docs == before[name]
    assert '191.116.125.248' not in json.dumps(db.outreach_restore_proxy_exclusions.docs, default=str)
    with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')


async def test_existing_binding_metadata_preserved_and_closed_hash_retry_allowed(suppression_db):
    db = suppression_db
    db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': BINDING, 'original_metadata': True})
    view = await ri.RestoreProxyExclusions(db).inspect('w', source()); await apply(db, view=view)
    row = db.account_proxy_ip_guards.docs[0]; row['later_metadata'] = True
    before = deepcopy(row)
    db.outreach_suppression_guards.docs[0]['erasure_state'] = 'erased'
    assert (await apply(db, view=view))['recovered']
    assert row == before and row['original_metadata']


@pytest.mark.parametrize('fault', ['drain', 'flag', 'source', 'review', 'operator', 'evidence', 'scope', 'epoch',
    'binding', 'saved_missing', 'saved_latch', 'saved_operator', 'saved_evidence', 'saved_review'])
async def test_changed_proof_or_missing_negative_denies(suppression_db, monkeypatch, fault):
    db = suppression_db; view = await ri.RestoreProxyExclusions(db).inspect('w', source()); changes = {}; raw = source()
    if fault.startswith('saved_'): await apply(db, view=view)
    if fault == 'drain': changes['workers_drained'] = False
    if fault == 'flag': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if fault == 'source': changes['source_digest'] = 'f' * 64
    if fault in {'review', 'saved_review'}: changes['review_digest'] = 'f' * 64
    if fault in {'operator', 'saved_operator'}: changes['operator'] = 'other' if fault.startswith('saved') else ''
    if fault in {'evidence', 'saved_evidence'}: changes['evidence_digest'] = 'f' * 64 if fault.startswith('saved') else 'bad'
    if fault == 'scope': raw = source(workspace_guard_digest='f' * 64)
    if fault == 'epoch': db.outreach_execution_epochs.docs = []
    if fault == 'binding': db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': 'f' * 64})
    if fault == 'saved_missing': db.account_proxy_ip_guards.docs = []
    if fault == 'saved_latch': db.account_proxy_ip_guards.docs[0].pop('restore_reuse_blocked')
    with pytest.raises(ValueError): await apply(db, raw, view, **changes)


@pytest.mark.parametrize('fault', ['version', 'unknown', 'empty', 'duplicate', 'capacity', 'raw_ip', 'binding',
    'oversize', 'duplicate_key', 'nonfinite', 'utf8'])
async def test_strict_digest_only_manifest(fault):
    doc = json.loads(source()); raw = None
    if fault == 'version': doc['version'] = True
    if fault == 'unknown': doc['timestamp'] = 'invented'
    if fault == 'empty': doc['ips'] = []
    if fault == 'duplicate': doc['ips'] *= 2
    if fault == 'capacity': doc['ips'] *= 101
    if fault == 'raw_ip': doc['ips'][0]['ip_digest'] = '191.116.125.248'
    if fault == 'binding': doc['ips'][0]['binding_digest'] = 'unproven'
    if fault == 'oversize': raw = b'x' * 65537
    if fault == 'duplicate_key': raw = source().replace(b'"version": 1', b'"version": 1, "version": 1')
    if fault == 'nonfinite': raw = b'{"version": Infinity}'
    if fault == 'utf8': raw = b'\xff'
    with pytest.raises(ValueError): ri.parse(json.dumps(doc).encode() if raw is None else raw)


async def test_original_global_guard_export_has_no_ownership_or_provider_term_claim(suppression_db):
    db = suppression_db
    db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': BINDING})
    doc = await ri.export_manifest(db, 'w', [IP], workers_drained=True)
    assert doc == json.loads(source()) and '191.116.125.248' not in json.dumps(doc)
    assert 'workspace_id' not in doc['ips'][0] and 'paid_through' not in doc['ips'][0]


@pytest.mark.parametrize('fault', ['empty', 'missing', 'duplicate', 'capacity', 'digest', 'binding', 'imported', 'drain'])
async def test_export_requires_selected_original_digest_facts(suppression_db, fault):
    db = suppression_db; row = {'_id': IP, 'binding_digest': BINDING}; refs = [IP]; drained = True
    if fault == 'empty': refs = []
    if fault == 'missing': refs = ['f' * 64]
    if fault == 'duplicate': refs *= 2
    if fault == 'capacity': refs *= 101
    if fault == 'digest': refs = ['raw-invoice']
    if fault == 'binding': row['binding_digest'] = 'raw-terms'
    if fault == 'imported': row['restore_reuse_blocked'] = True
    if fault == 'drain': drained = False
    db.account_proxy_ip_guards.docs.append(row)
    with pytest.raises(ValueError): await ri.export_manifest(db, 'w', refs, workers_drained=drained)



@pytest.mark.parametrize('flag', [True, False, None, 'true', 1])
async def test_restored_or_malformed_negative_blocks_original_binding_and_claim(flag):
    from tests.outreach_memory import Database
    from outreach.core.proxy_identity import require_ip_binding, identity, restore_ip_allowed
    row = {'_id': 'asset', 'provider': 'iproyal_static', 'host': '191.116.125.248'}
    original = {**identity(row['host'], 'w', 'asset', row['provider']), 'restore_reuse_blocked': flag}
    db = Database(account_proxy_ip_guards=[deepcopy(original)])
    assert not await restore_ip_allowed(db, row['host'])
    assert not await require_ip_binding(db, row, 'w', claim=True)
    assert db.account_proxy_ip_guards.docs == [original]


@pytest.mark.parametrize('host', [None, True, '191.116.125.0248', 'proxy.example.com', '2001:db8::1'])
async def test_unproven_physical_host_denies_negative_check(host):
    from tests.outreach_memory import Database
    from outreach.core.proxy_identity import restore_ip_allowed
    assert not await restore_ip_allowed(Database(), host)


@pytest.mark.parametrize('provider', ['iproyal_static', 'webshare_plan'])
async def test_original_import_is_denied_before_any_sealing(monkeypatch, provider):
    from tests.outreach_memory import Database
    from tests.test_outreach_managed_webshare import arguments, URL, NOW
    from outreach.core.managed_proxy import import_iproyal_proxy
    from outreach.core.webshare_provisioning import import_webshare_proxy
    from unittest.mock import AsyncMock
    db = Database(account_proxy_ip_guards=[{'_id': IP, 'binding_digest': BINDING, 'restore_reuse_blocked': True}])
    seal = AsyncMock(side_effect=AssertionError('No key or sealing operation may run'))
    module = 'managed_proxy' if provider == 'iproyal_static' else 'webshare_provisioning'
    monkeypatch.setattr('outreach.core.' + module + '.seal_proxy_password', seal)
    if provider == 'iproyal_static':
        from datetime import timedelta
        call = import_iproyal_proxy(db, URL, 'IN', 'order', 'w', NOW + timedelta(days=30), now=NOW)
    else:
        call = import_webshare_proxy(db, **arguments())
    with pytest.raises(ValueError): await call
    seal.assert_not_awaited()
    assert not db.outreach_proxy_inventory.docs


@pytest.mark.parametrize('reconnect', [False, True])
async def test_reservation_and_reconnect_keep_blocked_inventory_and_leases(reconnect):
    from tests.test_outreach_managed_webshare import imported, NOW
    from outreach.core.managed_proxy import reserve_sender_proxy, ManagedProxyUnavailable
    db, _, row = await imported()
    if reconnect:
        await reserve_sender_proxy(db, 'w', 'sender', 'IN', now=NOW)
    db.account_proxy_ip_guards.docs[0]['restore_reuse_blocked'] = True
    before = deepcopy(db.outreach_proxy_leases.docs)
    with pytest.raises(ManagedProxyUnavailable): await reserve_sender_proxy(db, 'w', 'sender', 'IN', now=NOW)
    assert db.outreach_proxy_leases.docs == before and db.outreach_proxy_inventory.docs[0] == row


@pytest.mark.parametrize('when', ['before_key', 'after_key', 'before_install'])
async def test_verification_never_uses_or_installs_restored_block(monkeypatch, when):
    from tests.test_outreach_connection_worker import make_db
    from celery_workers.tasks import outreach as worker
    from unittest.mock import AsyncMock
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false')
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '')
    db = make_db(); original_prepare = worker.prepare_proxy
    health = AsyncMock(return_value=True); opened = AsyncMock(wraps=original_prepare)
    verify = AsyncMock(return_value={'account_name': 'Pilot', 'linkedin_urn': 'urn:li:person:one'})
    def block(): db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': BINDING, 'restore_reuse_blocked': True})
    if when == 'before_key': block()
    if when == 'after_key':
        async def open_then_block(*args, **kwargs):
            result = await original_prepare(*args, **kwargs); block(); return result
        opened = AsyncMock(side_effect=open_then_block)
    if when == 'before_install':
        async def receive_then_block(*args, **kwargs):
            block(); return {'account_name': 'Pilot', 'linkedin_urn': 'urn:li:person:one'}
        verify = AsyncMock(side_effect=receive_then_block)
    monkeypatch.setattr(worker, 'prepare_proxy', opened)
    monkeypatch.setattr(worker.JITProxyManager, 'test_proxy_health', health)
    monkeypatch.setattr(worker.SessionAuthenticator, 'validate_session_cookie', verify)
    monkeypatch.setattr(worker.ExecutionPermission, 'allowed', AsyncMock(return_value=True))
    result = await worker._verify_sender_connection('job-1', 'ws-1', 'job-1', db=db)
    assert result['status'] != 'completed' and all(row.get('status') != 'active' for row in db.outreach_accounts.docs)
    if when == 'before_key': opened.assert_not_awaited()
    if when != 'before_install': health.assert_not_awaited(); verify.assert_not_awaited()
    assert db.account_proxy_ip_guards.docs[0]['restore_reuse_blocked'] is True

from tests.test_outreach_proxy_migration import proxy_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_webshare_migration import webshare_db, ASSET
from tests.test_outreach_proxy_adoption import legacy_db


async def test_original_iproyal_custody_conversion_denies_before_sealing(proxy_db, monkeypatch):
    from outreach.core import proxy_migration
    from outreach.core.credential_custody import CustodyUnavailable
    from unittest.mock import AsyncMock
    db = proxy_db; service = proxy_migration.ProxyMigration(db)
    view = await service.inspect('w', 'iproyal:p')
    db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': BINDING, 'restore_reuse_blocked': True})
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(proxy_migration, 'seal_proxy_password', seal)
    assert 'proxy_restore_reconciliation_required' in (await service.inspect('w', 'iproyal:p'))['blockers']
    with pytest.raises(CustodyUnavailable):
        await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True)
    seal.assert_not_awaited()


async def test_saved_iproyal_conversion_reports_blocked_current_state(proxy_db, monkeypatch):
    from outreach.core.proxy_migration import ProxyMigration
    from unittest.mock import AsyncMock
    service = ProxyMigration(proxy_db); view = await service.inspect('w', 'iproyal:p')
    assert (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    proxy_db.account_proxy_ip_guards.docs.append({'_id': IP, 'binding_digest': BINDING, 'restore_reuse_blocked': True})
    seal = AsyncMock(side_effect=AssertionError('No key replay'))
    monkeypatch.setattr('outreach.core.proxy_migration.seal_proxy_password', seal)
    assert not (await service.migrate('w', 'iproyal:p', 'operator', view['digest'], workers_drained=True))['current_matches']
    seal.assert_not_awaited()


async def test_legacy_webshare_adoption_denies_restored_matching_claim_before_key(legacy_db, monkeypatch):
    from outreach.core.proxy_adoption import ProxyAdoption
    from outreach.core.proxy_identity import identity
    from outreach.core.credential_custody import CustodyUnavailable
    from unittest.mock import AsyncMock
    db = legacy_db; service = ProxyAdoption(db); view = await service.inspect('w', ASSET)
    row = db.outreach_proxy_inventory.docs[0]
    db.account_proxy_ip_guards.docs.append({**identity(row['host'], 'w', ASSET, row['provider']), 'restore_reuse_blocked': True})
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr('outreach.core.proxy_adoption.seal_proxy_password', seal)
    assert 'proxy_restore_reconciliation_required' in (await service.inspect('w', ASSET))['blockers']
    with pytest.raises(CustodyUnavailable):
        await service.adopt('w', ASSET, 'operator', EVIDENCE, view['digest'], workers_drained=True)
    seal.assert_not_awaited()


@pytest.mark.parametrize('operation', ['renew', 'rotate'])
async def test_webshare_provider_change_denies_recovered_block_before_key(webshare_db, monkeypatch, operation):
    from outreach.core.proxy_lifecycle import ProxyLifecycle
    from outreach.core.credential_custody import CustodyUnavailable
    from unittest.mock import AsyncMock
    from datetime import timedelta
    db = webshare_db; service = ProxyLifecycle(db); view = await service.inspect('w', ASSET, operation)
    db.account_proxy_ip_guards.docs[0]['restore_reuse_blocked'] = True
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr('outreach.core.proxy_lifecycle.seal_proxy_password', seal)
    options = {'expires_at': epoch.now() + timedelta(days=60)} if operation == 'renew' else {'password_supplier': lambda: 'new-secret'}
    with pytest.raises(CustodyUnavailable):
        await service.apply('w', ASSET, operation, 'operator', EVIDENCE, 'provider-ref', view['digest'], workers_drained=True, **options)
    seal.assert_not_awaited()

@pytest.mark.parametrize('blocked_host', ['actual', 'inventory', 'none'])
async def test_sender_readiness_checks_both_legacy_hosts_without_claiming_ownership(monkeypatch, blocked_host):
    from tests.outreach_memory import Database
    from outreach.core.paid_access import sender_is_ready
    from datetime import timedelta
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    host, other = '191.116.125.248', '8.8.8.8'
    account = {'id': 'sender', 'workspace_id': 'w', 'country_code': 'IN', 'status': 'active',
        'proxy': {'proxy_id': 'asset', 'host': host}}
    db = Database(outreach_entitlements=[{'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': epoch.now() + timedelta(days=1)}],
        outreach_proxy_inventory=[{'_id': 'asset', 'provider': 'iproyal_static', 'host': other,
            'last_workspace_id': 'w', 'status': 'available', 'country_code': 'IN', 'expires_at': epoch.now() + timedelta(days=1)}],
        outreach_proxy_leases=[{'_id': 'asset', 'workspace_id': 'w', 'sender_id': 'sender'}])
    if blocked_host != 'none':
        db.account_proxy_ip_guards.docs.append({'_id': canonical_hash(['managed-proxy-ip-v1', host if blocked_host == 'actual' else other]),
            'binding_digest': BINDING, 'restore_reuse_blocked': True})
    before = deepcopy(db.account_proxy_ip_guards.docs)
    assert await sender_is_ready(db, 'w', account) is (blocked_host == 'none')
    assert db.account_proxy_ip_guards.docs == before
