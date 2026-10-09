"""Stopped financial/proxy inventory never grants authority or echoes material."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from outreach.core import restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from outreach.core.proxy_identity import identity
from outreach.core.restore_inventory import RestoreInventory, FIELDS
from tests.test_outreach_restore_epoch import restored_db, prepare

pytestmark = pytest.mark.restore_epoch

TERM = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def inventory_db(restored_db):
    await prepare(restored_db)
    return restored_db


async def inspect(db):
    return await RestoreInventory(db).inspect('w', workers_drained=True)


@pytest.mark.asyncio
async def test_empty_inventory_never_certifies_complete_or_activated(inventory_db):
    result = await inspect(inventory_db)
    assert result['activation_allowed'] is False and result['completeness_verified'] is False
    assert result['provider_ownership_verified'] is False
    assert result['external_review_required'] == ['financial_facts', 'provider_resources', 'source_completeness']
    assert set(result['counts']) == set(FIELDS)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['drain', 'root', 'flag', 'legacy'])
async def test_missing_stopped_review_denies(inventory_db, monkeypatch, fault):
    if fault == 'root': inventory_db.outreach_execution_epochs.docs = []
    if fault == 'flag': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if fault == 'legacy':
        inventory_db.outreach_execution_epochs.docs = []
        monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false')
        monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH', raising=False)
    with pytest.raises(ValueError):
        await RestoreInventory(inventory_db).inspect('w', workers_drained=fault != 'drain')


@pytest.mark.asyncio
@pytest.mark.parametrize('binding', ['missing', 'mismatch', 'blocked', 'malformed_flag', 'matching', 'bad_receipt'])
async def test_original_invoice_binding_is_only_local_evidence(inventory_db, binding):
    db = inventory_db
    db.outreach_payment_receipts.docs = [{'_id': 'invoice-private', 'workspace_id': 'w', 'seats': 1,
        'paid_through': TERM, 'secret': 'do-not-echo'}]
    if binding == 'bad_receipt': db.outreach_payment_receipts.docs[0]['seats'] = True
    elif binding != 'missing':
        row = {'_id': canonical_hash(['verified_invoice', 'invoice-private']),
               'binding_digest': canonical_hash(['w', 1, TERM])}
        if binding == 'mismatch': row['binding_digest'] = '0' * 64
        if binding == 'blocked': row['restore_reuse_blocked'] = True
        if binding == 'malformed_flag': row['restore_reuse_blocked'] = False
        db.account_invoice_guards.docs = [row]
    before = deepcopy(db.outreach_payment_receipts.docs)
    result = await inspect(db)
    reason = {'missing': 'invoice_binding_missing', 'mismatch': 'invoice_binding_mismatch',
        'blocked': 'invoice_restore_blocked', 'malformed_flag': 'invoice_restore_blocked',
        'matching': 'local_invoice_binding_matches', 'bad_receipt': 'payment_receipt_unproven'}[binding]
    assert result['findings'][reason] == 1
    assert db.outreach_payment_receipts.docs == before and not result['activation_allowed']
    assert 'invoice-private' not in json.dumps(result) and 'do-not-echo' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing', 'blocked', 'expired', 'malformed', 'orphan_lease'])
async def test_managed_proxy_review_preserves_resources(inventory_db, fault):
    db = inventory_db
    row = {'_id': 'asset-private', 'last_workspace_id': 'w', 'provider': 'iproyal_static',
        'host': '191.116.125.248', 'expires_at': TERM, 'password_enc': 'private-password'}
    db.outreach_proxy_inventory.docs = [row]
    if fault == 'expired': row['expires_at'] = datetime(2020, 1, 1)
    if fault == 'malformed': row['host'] = 'hostname-unproven'
    if fault != 'missing' and fault != 'malformed':
        guard = identity('191.116.125.248', 'w', 'asset-private', 'iproyal_static')
        if fault == 'blocked': guard['restore_reuse_blocked'] = None
        db.account_proxy_ip_guards.docs = [guard]
    if fault == 'orphan_lease':
        db.outreach_proxy_leases.docs = [{'_id': 'missing-asset', 'workspace_id': 'w', 'sender_id': 'sender'}]
    before = deepcopy(row)
    result = await inspect(db)
    reason = {'missing': 'ip_binding_missing', 'blocked': 'ip_restore_blocked',
        'expired': 'proxy_term_expired', 'malformed': 'proxy_identity_unproven',
        'orphan_lease': 'lease_asset_missing'}[fault]
    assert result['findings'][reason] == 1 and row == before
    assert 'private-password' not in json.dumps(result) and '191.116.125.248' not in json.dumps(result)


@pytest.mark.asyncio
async def test_metadata_digest_ignores_secrets_but_detects_current_terms(inventory_db):
    db = inventory_db
    db.outreach_entitlements.docs = [{'_id': 'term', 'workspace_id': 'w', 'status': 'revoked',
                                     'paid_through': TERM, 'secret': 'old'}]
    first = await inspect(db)
    db.outreach_entitlements.docs[0]['secret'] = 'new'
    assert (await inspect(db))['digest'] == first['digest']
    db.outreach_entitlements.docs[0]['status'] = 'active'
    assert (await inspect(db))['digest'] != first['digest']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['rows', 'metadata'])
async def test_capacity_denies_without_partial_inventory(inventory_db, fault):
    if fault == 'rows': inventory_db.outreach_entitlements.docs = [{'_id': str(i), 'workspace_id': 'w'} for i in range(101)]
    else: inventory_db.outreach_entitlements.docs = [{'_id': 'row', 'workspace_id': 'w', 'status': 'x' * 70000}]
    with pytest.raises(ValueError): await inspect(inventory_db)


@pytest.mark.asyncio
async def test_cli_closes_connection_and_sanitizes_failure(monkeypatch, capsys):
    from outreach.ops import restore_inventory as cli
    db = SimpleNamespace()
    monkeypatch.setenv('DB_NAME', 'test')
    monkeypatch.setattr(cli, 'get_client', AsyncMock(return_value={'test': db}))
    close = AsyncMock(); monkeypatch.setattr(cli, 'close_client', close)
    monkeypatch.setattr(cli.RestoreInventory, 'inspect', AsyncMock(side_effect=ValueError('private-value')))
    monkeypatch.setattr('sys.argv', ['restore_inventory', 'inspect', '--workspace', 'w', '--all-writers-and-caches-drained'])
    args = cli.parser().parse_args(['inspect', '--workspace', 'w', '--all-writers-and-caches-drained'])
    with pytest.raises(ValueError):
        await cli.run(args)
    close.assert_awaited_once()
    def fail(coroutine):
        coroutine.close()
        raise ValueError('private-value')
    monkeypatch.setattr(cli.asyncio, 'run', fail)
    assert cli.main() == 2
    assert 'private-value' not in capsys.readouterr().err


@pytest.mark.parametrize('arguments', [[], ['activate'], ['inspect', '--workspace', 'secret'],
    ['inspect', '--workspace', 'w', '--all-writers-and-caches-drained', '--token', 'secret']])
def test_cli_rejects_activation_or_material_without_echo(capsys, arguments):
    from outreach.ops.restore_inventory import parser
    with pytest.raises(SystemExit): parser().parse_args(arguments)
    assert 'secret' not in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['match', 'missing', 'seats', 'term', 'source', 'revoked', 'expired', 'malformed'])
async def test_entitlement_receipt_consistency_is_negative_only(inventory_db, fault):
    db = inventory_db
    row = {'_id': 'entitlement', 'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'paid_through': TERM, 'last_invoice_id': 'original', 'payment_source': 'manual_verified_invoice'}
    receipt = {'_id': 'original', 'workspace_id': 'w', 'seats': 1, 'paid_through': TERM,
        'source': 'manual_verified_invoice'}
    db.outreach_entitlements.docs = [row]
    db.outreach_payment_receipts.docs = [] if fault == 'missing' else [receipt]
    if fault == 'seats': row['seats'] = 2
    if fault == 'term': row['paid_through'] = datetime(2028, 1, 1, tzinfo=timezone.utc)
    if fault == 'source': row['payment_source'] = 'unproven'
    if fault == 'revoked': row['is_revoked'] = True
    if fault == 'expired': row['paid_through'] = datetime(2020, 1, 1, tzinfo=timezone.utc)
    if fault == 'malformed': row['seats'] = True
    before = deepcopy(row)
    result = await inspect(db)
    reason = {'match': 'local_entitlement_receipt_matches', 'missing': 'entitlement_receipt_missing',
        'seats': 'entitlement_receipt_mismatch', 'term': 'entitlement_receipt_mismatch',
        'source': 'entitlement_payment_unproven', 'revoked': 'entitlement_stopped',
        'expired': 'entitlement_term_expired', 'malformed': 'entitlement_payment_unproven'}[fault]
    assert result['findings'][reason] == 1
    assert row == before and not result['activation_allowed'] and not result['completeness_verified']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,reason', [('preparing', 'physical_preparing_review'),
    ('in_flight', 'physical_outcome_unresolved'), ('unknown_outcome', 'physical_outcome_unresolved'),
    ('response_received', 'physical_received_review'), ('new_status', 'physical_state_unproven'),
    (None, 'physical_state_unproven'), ('not_submitted', None), ('read_failed', None)])
async def test_physical_evidence_is_reported_without_resolution(inventory_db, status, reason):
    row = {'_id': 'request', 'workspace_id': 'w', 'status': status, 'mutation': status != 'read_failed',
        'owner_token': 'private-owner', 'receipt': {'private': 'evidence'}}
    inventory_db.outreach_physical_requests.docs = [row]
    before = deepcopy(row)
    result = await inspect(inventory_db)
    if reason: assert result['findings'][reason] == 1
    assert row == before and 'private-owner' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [True, None, 'false', 0])
async def test_failed_read_with_unproven_kind_requires_review(inventory_db, kind):
    inventory_db.outreach_physical_requests.docs = [{'_id': 'bad-read', 'workspace_id': 'w',
        'status': 'read_failed', 'mutation': kind}]
    result = await inspect(inventory_db)
    assert result['findings']['physical_state_unproven'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['matching', 'sender_missing', 'sender_duplicate', 'asset_foreign',
    'provider', 'country', 'proxy_link', 'generation', 'sender_invalid', 'duplicate_lease', 'sticky_scope', 'sender_shape', 'generation_shape', 'asset_shape'])
async def test_proxy_assignment_relationships_require_review(inventory_db, fault):
    db = inventory_db
    asset = {'_id': 'asset', 'workspace_id': 'w', 'provider': 'iproyal_static',
        'host': '191.116.125.248', 'country_code': 'US', 'credential_generation': 'generation'}
    lease = {'_id': 'asset', 'workspace_id': 'w', 'sender_id': 'sender',
        'provider': 'iproyal_static', 'country_code': 'US'}
    sender = {'_id': 'mongo-sender', 'id': 'sender', 'workspace_id': 'w',
        'proxy': {'proxy_id': 'asset', 'credential_generation': 'generation', 'password_enc': 'secret'}}
    db.outreach_proxy_inventory.docs = [asset]
    db.outreach_proxy_leases.docs = [lease]
    db.outreach_accounts.docs = [sender]
    if fault == 'sender_missing': db.outreach_accounts.docs = []
    if fault == 'sender_duplicate': db.outreach_accounts.docs.append({**sender, '_id': 'duplicate'})
    if fault == 'asset_foreign': asset.update(workspace_id='other', last_workspace_id='w')
    if fault == 'provider': lease['provider'] = 'webshare_plan'
    if fault == 'country': lease['country_code'] = 'GB'
    if fault == 'proxy_link': sender['proxy']['proxy_id'] = 'replacement'
    if fault == 'generation': sender['proxy']['credential_generation'] = 'replacement'
    if fault == 'sender_invalid': lease['sender_id'] = True
    if fault == 'duplicate_lease': db.outreach_proxy_leases.docs.append({**lease, '_id': 'other-asset'})
    if fault == 'sticky_scope': asset['last_workspace_id'] = 'other'
    if fault == 'sender_shape': lease['sender_id'] = sender['id'] = '\n'
    if fault == 'generation_shape': asset['credential_generation'] = sender['proxy']['credential_generation'] = '\n'
    if fault == 'asset_shape': lease['_id'] = asset['_id'] = sender['proxy']['proxy_id'] = '\n'
    before = deepcopy([asset, lease, sender])
    result = await inspect(db)
    reason = {'matching': 'local_lease_links_match', 'sender_missing': 'lease_sender_review_required',
        'sender_duplicate': 'lease_sender_ambiguous', 'asset_foreign': 'lease_asset_scope_unproven',
        'provider': 'lease_provider_country_mismatch', 'country': 'lease_provider_country_mismatch',
        'proxy_link': 'lease_sender_proxy_mismatch', 'generation': 'lease_credential_generation_mismatch',
        'sender_invalid': 'lease_sender_identity_unproven', 'duplicate_lease': 'lease_sender_multiple_assets', 'sticky_scope': 'lease_asset_scope_unproven',
        'sender_shape': 'lease_sender_identity_unproven', 'generation_shape': 'lease_credential_generation_mismatch',
        'asset_shape': 'lease_asset_identity_unproven'}[fault]
    assert result['findings'][reason] >= 1
    assert [asset, lease, sender] == before
    assert not result['activation_allowed'] and not result['provider_ownership_verified']
    assert 'secret' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['matching', 'missing', 'markers', 'status', 'revision', 'basis', 'generation', 'scope', 'duplicate'])
async def test_webshare_lifecycle_receipts_are_only_local_consistency(inventory_db, fault):
    from outreach.core.proxy_lifecycle_proof import material
    db = inventory_db
    asset = {'_id': 'webshare:plan:resource', 'workspace_id': 'w', 'provider': 'webshare_plan',
        'host': '191.116.125.248', 'credential_generation': 'generation', 'import_basis_digest': 'a' * 64,
        'root_import_basis_digest': 'b' * 64, 'proxy_lifecycle_revision': 1, 'proxy_lifecycle_review_id': 'c' * 64}
    receipt = {'_id': 'c' * 64, 'workspace_id': 'w', 'proxy_id': asset['_id'], 'status': 'completed',
        'revision': 1, 'root_import_basis_digest': 'b' * 64, 'after_basis_digest': material(asset),
        'generation_digest': canonical_hash('generation')}
    db.outreach_proxy_inventory.docs = [asset]
    db.outreach_proxy_lifecycle_reviews.docs = [receipt]
    if fault == 'missing': db.outreach_proxy_lifecycle_reviews.docs = []
    if fault == 'markers': asset.pop('proxy_lifecycle_review_id')
    if fault == 'status': receipt['status'] = 'preparing'
    if fault == 'revision': receipt['revision'] = True
    if fault == 'basis': receipt['after_basis_digest'] = '0' * 64
    if fault == 'generation': receipt['generation_digest'] = '0' * 64
    if fault == 'scope': asset['workspace_id'] = 'other'; asset['last_workspace_id'] = 'w'
    if fault == 'duplicate': db.outreach_proxy_lifecycle_reviews.docs.append({**receipt, '_id': 'd' * 64})
    before = deepcopy([asset, receipt])
    result = await inspect(db)
    reason = 'local_webshare_lifecycle_matches' if fault == 'matching' else 'webshare_lifecycle_review_required'
    assert result['findings'][reason] == 1
    assert [asset, receipt] == before and not result['provider_ownership_verified']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['matching', 'missing', 'markers', 'status', 'source', 'basis', 'scope', 'duplicate', 'root_fallback', 'null_root', 'receipt_id'])
async def test_webshare_adoption_receipt_consistency_is_not_adoption(inventory_db, fault):
    db = inventory_db
    asset = {'_id': 'webshare:plan:resource', 'workspace_id': 'w', 'provider': 'webshare_plan',
        'host': '191.116.125.248', 'import_basis_digest': 'a' * 64, 'root_import_basis_digest': 'b' * 64,
        'proxy_adoption_id': 'c' * 64, 'proxy_adoption_source_digest': 'd' * 64}
    receipt = {'_id': 'c' * 64, 'workspace_id': 'w', 'proxy_id': asset['_id'], 'status': 'completed',
        'source_digest': 'd' * 64, 'adopted_basis_digest': 'b' * 64, 'private': 'secret'}
    db.outreach_proxy_inventory.docs = [asset]
    db.outreach_proxy_adoptions.docs = [receipt]
    if fault == 'missing': db.outreach_proxy_adoptions.docs = []
    if fault == 'markers': asset.pop('proxy_adoption_id')
    if fault == 'status': receipt['status'] = 'preparing'
    if fault == 'source': receipt['source_digest'] = '0' * 64
    if fault == 'basis': receipt['adopted_basis_digest'] = '0' * 64
    if fault == 'scope': asset.update(workspace_id='other', last_workspace_id='w')
    if fault == 'duplicate': db.outreach_proxy_adoptions.docs.append({**receipt, '_id': 'e' * 64})
    if fault == 'root_fallback': asset.pop('root_import_basis_digest'); receipt['adopted_basis_digest'] = 'a' * 64
    if fault == 'null_root': asset['root_import_basis_digest'] = None; receipt['adopted_basis_digest'] = 'a' * 64
    if fault == 'receipt_id': receipt['_id'] = 'e' * 64
    before = deepcopy([asset, receipt])
    result = await inspect(db)
    reason = 'local_webshare_adoption_matches' if fault in ('matching', 'root_fallback') else 'webshare_adoption_review_required'
    assert result['findings'][reason] == 1
    assert [asset, receipt] == before and not result['activation_allowed'] and not result['provider_ownership_verified']
    assert 'secret' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['matching', 'resource', 'plan_shape', 'version', 'custody', 'dedicated',
    'evidence', 'reviewer', 'future_review', 'term', 'scope', 'plan_colon', 'resource_colon'])
async def test_webshare_import_metadata_never_reconstructs_original_proof(inventory_db, fault):
    asset = {'_id': 'webshare:plan:resource', 'workspace_id': 'w', 'last_workspace_id': 'w',
        'provider': 'webshare_plan', 'host': '191.116.125.248', 'provider_plan_id': 'plan',
        'provider_resource_id': 'resource', 'provider_order_id': 'order', 'custody_workspace_id': 'w',
        'managed_webshare_version': 1, 'dedicated_isp_confirmed': True, 'verified_by': 'operator',
        'verified_at': datetime(2026, 1, 1, tzinfo=timezone.utc), 'expires_at': TERM,
        'evidence_digest': 'a' * 64, 'import_basis_digest': 'b' * 64, 'credential_generation': 'generation'}
    if fault == 'resource': asset['provider_resource_id'] = 'replacement'
    if fault == 'plan_shape': asset['provider_plan_id'] = '\n'
    if fault == 'version': asset['managed_webshare_version'] = True
    if fault == 'custody': asset['custody_workspace_id'] = 'other'
    if fault == 'dedicated': asset['dedicated_isp_confirmed'] = 1
    if fault == 'evidence': asset['evidence_digest'] = 'unproven'
    if fault == 'reviewer': asset['verified_by'] = '\n'
    if fault == 'future_review': asset['verified_at'] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    if fault == 'term': asset['expires_at'] = asset['verified_at']
    if fault == 'scope': asset['last_workspace_id'] = 'other'
    if fault in ('plan_colon', 'resource_colon'):
        field = 'provider_plan_id' if fault == 'plan_colon' else 'provider_resource_id'
        asset[field] += ':extra'
        asset['_id'] = f"webshare:{asset['provider_plan_id']}:{asset['provider_resource_id']}"
    inventory_db.outreach_proxy_inventory.docs = [asset]
    before = deepcopy(asset)
    result = await inspect(inventory_db)
    reason = 'local_webshare_import_metadata_consistent' if fault == 'matching' else 'webshare_import_metadata_review_required'
    assert result['findings'][reason] == 1
    assert asset == before and not result['provider_ownership_verified'] and not result['activation_allowed']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['matching', 'asset_missing', 'lease_missing', 'lease_sender', 'sender_duplicate',
    'proxy_shared', 'proxy_invalid', 'sender_invalid', 'asset_scope', 'lease_duplicate', 'generation', 'provider', 'country', 'multiple_leases', 'sticky', 'matching_webshare'])
async def test_sender_reverse_proxy_assignment_requires_review(inventory_db, fault):
    db = inventory_db
    asset = {'_id': 'asset', 'workspace_id': 'w', 'provider': 'iproyal_static',
        'host': '191.116.125.248', 'country_code': 'US', 'credential_generation': 'generation'}
    lease = {'_id': 'asset', 'workspace_id': 'w', 'sender_id': 'sender', 'provider': 'iproyal_static', 'country_code': 'US'}
    sender = {'_id': 'mongo-account', 'id': 'sender', 'workspace_id': 'w',
        'proxy': {'proxy_id': 'asset', 'credential_generation': 'generation', 'password_enc': 'secret'}}
    db.outreach_proxy_inventory.docs = [asset]
    db.outreach_proxy_leases.docs = [lease]
    db.outreach_accounts.docs = [sender]
    if fault == 'asset_missing': db.outreach_proxy_inventory.docs = []
    if fault == 'lease_missing': db.outreach_proxy_leases.docs = []
    if fault == 'lease_sender': lease['sender_id'] = 'other'
    if fault == 'sender_duplicate': db.outreach_accounts.docs.append({**sender, '_id': 'duplicate'})
    if fault == 'proxy_shared': db.outreach_accounts.docs.append({**sender, '_id': 'other', 'id': 'other'})
    if fault == 'proxy_invalid': sender['proxy']['proxy_id'] = '\n'
    if fault == 'sender_invalid': sender['id'] = '\n'
    if fault == 'asset_scope': asset.update(workspace_id='other', last_workspace_id='w')
    if fault == 'lease_duplicate': db.outreach_proxy_leases.docs.append({**lease})
    if fault == 'generation': sender['proxy']['credential_generation'] = 'replacement'
    if fault == 'provider': lease['provider'] = 'webshare_plan'
    if fault == 'country': lease['country_code'] = 'GB'
    if fault == 'multiple_leases': db.outreach_proxy_leases.docs.append({**lease, '_id': 'other-asset'})
    if fault == 'sticky': asset['last_workspace_id'] = 'other'
    if fault == 'matching_webshare': asset['provider'] = lease['provider'] = 'webshare_plan'
    before = deepcopy([asset, lease, sender])
    result = await inspect(db)
    reason = {'matching': 'local_sender_assignment_links_match', 'asset_missing': 'sender_proxy_asset_review_required',
        'lease_missing': 'sender_proxy_lease_review_required', 'lease_sender': 'sender_proxy_lease_review_required',
        'sender_duplicate': 'sender_identity_ambiguous', 'proxy_shared': 'sender_proxy_shared',
        'proxy_invalid': 'sender_assignment_identity_unproven', 'sender_invalid': 'sender_assignment_identity_unproven',
        'asset_scope': 'sender_proxy_asset_review_required', 'lease_duplicate': 'sender_proxy_lease_review_required',
        'generation': 'sender_proxy_generation_review_required', 'provider': 'sender_proxy_lease_review_required',
        'country': 'sender_proxy_lease_review_required', 'multiple_leases': 'sender_proxy_lease_review_required',
        'sticky': 'sender_proxy_asset_review_required', 'matching_webshare': 'local_sender_assignment_links_match'}[fault]
    assert result['findings'][reason] >= 1
    assert [asset, lease, sender] == before and not result['activation_allowed'] and not result['provider_ownership_verified']
    assert 'secret' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('collection', ['outreach_email_operations', 'outreach_email_discoveries'])
@pytest.mark.parametrize('state,category', [('dispatching', 'unresolved'), ('uncertain', 'unresolved'),
    ('accepted', 'recorded_result_review'), ('found', 'recorded_result_review'),
    ('not_found', 'recorded_result_review'), ('failed', 'recorded_result_review'),
    ('not_submitted', None), (None, 'state_unproven'), ('future_state', 'state_unproven')])
async def test_provider_operation_inventory_preserves_outcomes(inventory_db, collection, state, category):
    row = {'_id': 'operation-private', 'workspace_id': 'w', 'status': state,
        'owner_token': 'owner-secret', 'email': 'private@example.test', 'receipt': {'private': 'outcome'}}
    getattr(inventory_db, collection).docs = [row]
    before = deepcopy(row)
    result = await inspect(inventory_db)
    prefix = 'email_operation' if collection == 'outreach_email_operations' else 'finder_operation'
    valid_results = ('accepted', 'failed') if collection == 'outreach_email_operations' else ('found', 'not_found', 'failed')
    if category == 'recorded_result_review' and state not in valid_results: category = 'state_unproven'
    if category: assert result['findings'][prefix + '_' + category] == 1
    else: assert not any(key.startswith(prefix) for key in result['findings'])
    assert row == before and result['counts'][collection] == 1
    assert not result['activation_allowed'] and not result['completeness_verified']
    assert 'owner-secret' not in json.dumps(result) and 'private@example.test' not in json.dumps(result)
