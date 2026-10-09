"""Native stopped inventory snapshots retain uncertainty and never approve activation."""
import os
from copy import deepcopy
import pytest
from outreach.core import restore_inventory as inventory, suppression
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def inspect(db):
    return await inventory.RestoreInventory(db).inspect('w', workers_drained=True)


async def test_native_metadata_projection_and_retained_uncertainty(real_restore):
    db = real_restore
    await prepare(db)
    before = await db.outreach_manual_actions.find_one({'_id': 'unknown'})
    await db.outreach_accounts.insert_one({'_id': 'private-account', 'workspace_id': 'w',
        'proxy': {'proxy_id': 'asset', 'password_enc': 'secret'}, 'cookie_enc': 'secret'})
    first = await inspect(db)
    await db.outreach_accounts.update_one({'_id': 'private-account'}, {'$set': {'cookie_enc': 'replacement', 'proxy.password_enc': 'replacement'}})
    assert (await inspect(db))['digest'] == first['digest']
    assert not first['activation_allowed'] and not first['completeness_verified']
    assert await db.outreach_manual_actions.find_one({'_id': 'unknown'}) == before
    assert await db.account_invoice_guards.count_documents({}) == 0
    assert await db.account_proxy_ip_guards.count_documents({}) == 0


async def test_native_same_session_snapshot_across_collections(real_restore, monkeypatch):
    db = real_restore
    await prepare(db)
    baseline = await inspect(db)
    original = inventory.raw_database
    triggered = False

    class Cursor:
        def __init__(self, cursor): self.cursor = cursor
        def sort(self, *args): self.cursor = self.cursor.sort(*args); return self
        def limit(self, *args): self.cursor = self.cursor.limit(*args); return self
        async def to_list(self, **kwargs):
            nonlocal triggered
            result = await self.cursor.to_list(**kwargs)
            if not triggered:
                triggered = True
                await db.outreach_payment_receipts.insert_one({'_id': 'concurrent', 'workspace_id': 'w', 'seats': 1})
            return result

    class Collection:
        def find(self, *args, **kwargs): return Cursor(db.outreach_entitlements.find(*args, **kwargs))

    class Database:
        def __getattr__(self, name):
            return Collection() if name == 'outreach_entitlements' else getattr(db, name)

    def wrapped(current):
        raw, options = original(current)
        assert options.get('session') is not None
        return Database(), options

    monkeypatch.setattr(inventory, 'raw_database', wrapped)
    result = await inspect(db)
    assert triggered and result['digest'] == baseline['digest']
    monkeypatch.setattr(inventory, 'raw_database', original)
    fresh = await inspect(db)
    assert fresh['counts']['outreach_payment_receipts'] == 1
    assert fresh['digest'] != baseline['digest']


@pytest.mark.parametrize('fault', ['closed', 'root', 'capacity', 'late_flag'])
async def test_native_denial_preserves_domain_rows(real_restore, monkeypatch, fault):
    db = real_restore
    await prepare(db)
    before = await db.outreach_sender_execution.find_one({'workspace_id': 'w'})
    if fault == 'closed':
        await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state': 'closed'}})
    elif fault == 'root': await db.outreach_execution_epochs.delete_many({})
    elif fault == 'capacity':
        await db.outreach_entitlements.insert_many([{'_id': str(i), 'workspace_id': 'w'} for i in range(101)])
    else:
        original = suppression.mutate_suppression
        async def changed(*args, **kwargs):
            result = await original(*args, **kwargs)
            monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
            return result
        monkeypatch.setattr(suppression, 'mutate_suppression', changed)
    with pytest.raises(Exception): await inspect(db)
    assert await db.outreach_sender_execution.find_one({'workspace_id': 'w'}) == before


async def test_native_candidate_scope_is_not_ownership(real_restore):
    db = real_restore
    await prepare(db)
    await db.outreach_proxy_inventory.insert_many([
        {'_id': 'legacy', 'last_workspace_id': 'w', 'provider': 'iproyal_static', 'host': '191.116.125.248'},
        {'_id': 'foreign', 'workspace_id': 'other', 'provider': 'iproyal_static', 'host': '191.116.125.249'}])
    result = await inspect(db)
    assert result['counts']['outreach_proxy_inventory'] == 1
    assert result['findings']['ip_binding_missing'] == 1
    assert result['findings']['proxy_term_unproven'] == 1
    assert not result['provider_ownership_verified']


async def test_native_standalone_has_no_inspection_fallback(real_restore, tmp_path):
    import asyncio
    import shutil
    import socket
    import subprocess
    from motor.motor_asyncio import AsyncIOMotorClient
    await prepare(real_restore)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    storage = tmp_path / 'mongo'
    storage.mkdir()
    with (tmp_path / 'mongo.log').open('w') as log:
        proc = subprocess.Popen(['/opt/homebrew/bin/mongod', '--dbpath', str(storage),
            '--bind_ip', '127.0.0.1', '--port', str(port)], stdout=log, stderr=log)
        client = AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=1000)
        db = client.test_inventory_standalone
        try:
            for attempt in range(20):
                try:
                    await client.admin.command('ping')
                    break
                except Exception:
                    if attempt == 19: raise
                    await asyncio.sleep(.2)
            for name in ('outreach_execution_epochs', 'outreach_suppression_guards'):
                rows = await real_restore[name].find({}).to_list(length=10)
                if rows: await db[name].insert_many(rows)
            with pytest.raises(suppression.SuppressionUnavailable): await inspect(db)
            assert await db.account_invoice_guards.count_documents({}) == 0
        finally:
            try: await client.drop_database(db.name)
            finally:
                client.close()
                proc.terminate()
                proc.wait(timeout=10)
                shutil.rmtree(storage)


async def test_native_global_bindings_use_bson_terms_and_block_presence(real_restore):
    from datetime import datetime
    from outreach.core.authorization import canonical_hash
    from outreach.core.proxy_identity import identity
    db = real_restore
    await prepare(db)
    term = datetime(2027, 1, 1)
    await db.outreach_payment_receipts.insert_one({'_id': 'invoice', 'workspace_id': 'w', 'seats': 1, 'paid_through': term})
    invoice = {'_id': canonical_hash(['verified_invoice', 'invoice']),
        'binding_digest': canonical_hash(['w', 1, inventory.native_date(term)])}
    await db.account_invoice_guards.insert_one(invoice)
    await db.outreach_proxy_inventory.insert_one({'_id': 'asset', 'workspace_id': 'w',
        'provider': 'iproyal_static', 'host': '191.116.125.248', 'expires_at': term})
    proxy = identity('191.116.125.248', 'w', 'asset', 'iproyal_static')
    await db.account_proxy_ip_guards.insert_one(proxy)
    first = await inspect(db)
    assert first['findings']['local_invoice_binding_matches'] == 1
    assert first['findings']['local_ip_binding_matches'] == 1
    await db.account_invoice_guards.update_one({'_id': invoice['_id']}, {'$set': {'restore_reuse_blocked': False}})
    await db.account_proxy_ip_guards.update_one({'_id': proxy['_id']}, {'$set': {'restore_reuse_blocked': None}})
    blocked = await inspect(db)
    assert blocked['findings']['invoice_restore_blocked'] == 1
    assert blocked['findings']['ip_restore_blocked'] == 1
    assert blocked['digest'] != first['digest']
    await db.account_invoice_guards.update_one({'_id': invoice['_id']}, {'$set': {'binding_digest': '0' * 64}})
    await db.account_proxy_ip_guards.update_one({'_id': proxy['_id']}, {'$set': {'binding_digest': '0' * 64}})
    changed = await inspect(db)
    assert changed['findings']['invoice_binding_mismatch'] == 1
    assert changed['findings']['ip_binding_mismatch'] == 1
    assert not changed['activation_allowed']


@pytest.mark.parametrize('fault', ['matching', 'mismatch', 'missing', 'revoked'])
async def test_native_financial_relationship_and_physical_holds_are_retained(real_restore, fault):
    from datetime import datetime
    db = real_restore
    await prepare(db)
    term = datetime(2027, 1, 1, 0, 0, 0, 123000)
    entitlement = {'_id': 'term', 'workspace_id': 'w', 'status': 'active', 'seats': 1,
        'paid_through': term, 'last_invoice_id': 'invoice', 'payment_source': 'manual_verified_invoice'}
    if fault == 'revoked': entitlement['is_revoked'] = True
    await db.outreach_entitlements.insert_one(entitlement)
    if fault != 'missing':
        await db.outreach_payment_receipts.insert_one({'_id': 'invoice', 'workspace_id': 'w',
            'seats': 2 if fault == 'mismatch' else 1, 'paid_through': term, 'source': 'manual_verified_invoice'})
    requests = [{'_id': 'hold-' + str(i), 'workspace_id': 'w', 'status': state,
        'mutation': True, 'owner_token': 'retained-owner', 'receipt': {'original': 'evidence'}}
        for i, state in enumerate(['preparing', 'in_flight', 'unknown_outcome', 'response_received', 'future'])]
    await db.outreach_physical_requests.insert_many(requests)
    before = await db.outreach_entitlements.find_one({'_id': 'term'})
    held = await db.outreach_physical_requests.find({'workspace_id': 'w'}).sort('_id', 1).to_list(length=100)
    result = await inspect(db)
    reason = {'matching': 'local_entitlement_receipt_matches', 'mismatch': 'entitlement_receipt_mismatch',
        'missing': 'entitlement_receipt_missing', 'revoked': 'entitlement_stopped'}[fault]
    assert result['findings'][reason] == 1
    # The restored fixture already retains one original unknown physical request.
    assert result['findings']['physical_outcome_unresolved'] == 3
    assert result['findings']['physical_preparing_review'] == 1
    assert result['findings']['physical_received_review'] == 1
    assert result['findings']['physical_state_unproven'] == 1
    assert await db.outreach_entitlements.find_one({'_id': 'term'}) == before
    assert await db.outreach_physical_requests.find({'workspace_id': 'w'}).sort('_id', 1).to_list(length=100) == held
    assert not result['activation_allowed'] and not result['completeness_verified']
    await db.outreach_entitlements.update_one({'_id': 'term'}, {'$set': {'seats': 3}})
    assert (await inspect(db))['digest'] != result['digest']


@pytest.mark.parametrize('fault', ['matching', 'country', 'generation', 'sender_missing', 'sender_duplicate', 'multiple_leases', 'sticky_scope'])
async def test_native_lease_consistency_retains_resources_and_holds(real_restore, fault):
    from datetime import datetime
    db = real_restore
    await prepare(db)
    asset = {'_id': 'review-asset', 'workspace_id': 'w', 'provider': 'iproyal_static',
        'host': '191.116.125.248', 'country_code': 'US', 'credential_generation': 'proxy-generation',
        'expires_at': datetime(2027, 1, 1), 'password_enc': 'retained-secret'}
    lease = {'_id': 'review-asset', 'workspace_id': 'w', 'sender_id': 'review-sender',
        'provider': 'iproyal_static', 'country_code': 'GB' if fault == 'country' else 'US',
        'reservation_job_id': 'retained-reservation'}
    sender = {'_id': 'review-account', 'id': 'review-sender', 'workspace_id': 'w',
        'proxy': {'proxy_id': 'review-asset', 'credential_generation': 'replacement' if fault == 'generation' else 'proxy-generation',
            'password_enc': 'retained-secret'}, 'session_cookie_enc': 'retained-cookie'}
    if fault == 'sticky_scope': asset['last_workspace_id'] = 'other'
    await db.outreach_proxy_inventory.insert_one(asset)
    await db.outreach_proxy_leases.insert_one(lease)
    if fault != 'sender_missing': await db.outreach_accounts.insert_one(sender)
    if fault == 'sender_duplicate': await db.outreach_accounts.insert_one({**sender, '_id': 'duplicate-account'})
    if fault == 'multiple_leases': await db.outreach_proxy_leases.insert_one({**lease, '_id': 'missing-second-asset'})
    names = ['outreach_proxy_inventory', 'outreach_proxy_leases', 'outreach_accounts', 'outreach_physical_requests']
    before = {name: await db[name].find({}).sort('_id', 1).to_list(length=100) for name in names}
    result = await inspect(db)
    reason = {'matching': 'local_lease_links_match', 'country': 'lease_provider_country_mismatch',
        'generation': 'lease_credential_generation_mismatch', 'sender_missing': 'lease_sender_review_required',
        'sender_duplicate': 'lease_sender_ambiguous', 'multiple_leases': 'lease_sender_multiple_assets', 'sticky_scope': 'lease_asset_scope_unproven'}[fault]
    assert result['findings'][reason] >= 1
    for name in names: assert await db[name].find({}).sort('_id', 1).to_list(length=100) == before[name]
    assert not result['activation_allowed'] and not result['provider_ownership_verified']
    await db.outreach_accounts.update_one({'_id': 'review-account'}, {'$set': {'proxy.password_enc': 'replacement-secret'}})
    assert (await inspect(db))['digest'] == result['digest']
    await db.outreach_proxy_inventory.update_one({'_id': 'review-asset'}, {'$set': {'credential_generation': 'new'}})
    assert (await inspect(db))['digest'] != result['digest']


@pytest.mark.parametrize('fault', ['matching', 'missing', 'changed', 'older_history', 'capacity'])
async def test_native_webshare_lifecycle_metadata_review(real_restore, fault):
    from outreach.core.authorization import canonical_hash
    from outreach.core.proxy_lifecycle_proof import material
    db = real_restore
    await prepare(db)
    asset = {'_id': 'webshare:plan:resource', 'workspace_id': 'w', 'provider': 'webshare_plan',
        'host': '191.116.125.248', 'credential_generation': 'generation', 'import_basis_digest': 'a' * 64,
        'root_import_basis_digest': 'b' * 64, 'proxy_lifecycle_revision': 2, 'proxy_lifecycle_review_id': 'c' * 64,
        'password_enc': 'retained-secret'}
    receipt = {'_id': 'c' * 64, 'workspace_id': 'w', 'proxy_id': asset['_id'], 'status': 'completed',
        'revision': 2, 'root_import_basis_digest': 'b' * 64, 'after_basis_digest': material(asset),
        'generation_digest': canonical_hash('generation'), 'private': 'not-projected'}
    if fault == 'changed': receipt['generation_digest'] = '0' * 64
    await db.outreach_proxy_inventory.insert_one(asset)
    if fault != 'missing': await db.outreach_proxy_lifecycle_reviews.insert_one(receipt)
    if fault == 'older_history': await db.outreach_proxy_lifecycle_reviews.insert_one({**receipt, '_id': 'older', 'revision': 1})
    if fault == 'capacity':
        await db.outreach_proxy_lifecycle_reviews.insert_many([{'_id': 'excess-' + str(i), 'workspace_id': 'w'} for i in range(100)])
    names = ['outreach_proxy_inventory', 'outreach_proxy_lifecycle_reviews', 'outreach_physical_requests']
    before = {name: await db[name].find({}).sort('_id', 1).to_list(length=200) for name in names}
    if fault == 'capacity':
        with pytest.raises(ValueError): await inspect(db)
    else:
        result = await inspect(db)
        reason = 'local_webshare_lifecycle_matches' if fault in ('matching', 'older_history') else 'webshare_lifecycle_review_required'
        assert result['findings'][reason] == 1
        assert not result['activation_allowed'] and not result['provider_ownership_verified']
        await db.outreach_proxy_lifecycle_reviews.update_one({'_id': receipt['_id']}, {'$set': {'private': 'replacement'}})
        assert (await inspect(db))['digest'] == result['digest']
        if fault != 'missing':
            await db.outreach_proxy_lifecycle_reviews.update_one({'_id': receipt['_id']}, {'$set': {'private': 'not-projected'}})
    for name in names: assert await db[name].find({}).sort('_id', 1).to_list(length=200) == before[name]


@pytest.mark.parametrize('fault', ['matching', 'missing', 'foreign_receipt', 'changed', 'capacity'])
async def test_native_webshare_adoption_metadata_preserves_sources(real_restore, fault):
    db = real_restore
    await prepare(db)
    asset = {'_id': 'webshare:plan:adopted', 'workspace_id': 'w', 'provider': 'webshare_plan',
        'host': '191.116.125.248', 'import_basis_digest': 'a' * 64, 'root_import_basis_digest': 'b' * 64,
        'proxy_adoption_id': 'c' * 64, 'proxy_adoption_source_digest': 'd' * 64, 'password_enc': 'retained-secret'}
    receipt = {'_id': 'c' * 64, 'workspace_id': 'other' if fault == 'foreign_receipt' else 'w',
        'proxy_id': asset['_id'], 'status': 'completed', 'source_digest': 'd' * 64,
        'adopted_basis_digest': '0' * 64 if fault == 'changed' else 'b' * 64, 'private': 'secret'}
    await db.outreach_proxy_inventory.insert_one(asset)
    if fault != 'missing': await db.outreach_proxy_adoptions.insert_one(receipt)
    if fault == 'capacity':
        await db.outreach_proxy_adoptions.insert_many([{'_id': 'extra-' + str(i), 'workspace_id': 'w'} for i in range(100)])
    names = ['outreach_proxy_inventory', 'outreach_proxy_adoptions', 'outreach_physical_requests']
    before = {name: await db[name].find({}).sort('_id', 1).to_list(length=200) for name in names}
    if fault == 'capacity':
        with pytest.raises(ValueError): await inspect(db)
    else:
        result = await inspect(db)
        reason = 'local_webshare_adoption_matches' if fault == 'matching' else 'webshare_adoption_review_required'
        assert result['findings'][reason] == 1
        assert not result['activation_allowed'] and not result['completeness_verified']
        assert result['counts']['outreach_proxy_adoptions'] == (0 if fault in ('missing', 'foreign_receipt') else 1)
        await db.outreach_proxy_adoptions.update_one({'_id': receipt['_id']}, {'$set': {'private': 'replacement'}})
        assert (await inspect(db))['digest'] == result['digest']
        if fault != 'missing':
            await db.outreach_proxy_adoptions.update_one({'_id': receipt['_id']}, {'$set': {'private': 'secret'}})
    for name in names: assert await db[name].find({}).sort('_id', 1).to_list(length=200) == before[name]


@pytest.mark.parametrize('fault', ['matching', 'resource', 'custody', 'missing_review', 'expired'])
async def test_native_webshare_import_metadata_keeps_original_evidence(real_restore, fault):
    from datetime import datetime
    db = real_restore
    await prepare(db)
    asset = {'_id': 'webshare:plan:original', 'workspace_id': 'w', 'last_workspace_id': 'w',
        'provider': 'webshare_plan', 'host': '191.116.125.248', 'provider_plan_id': 'plan',
        'provider_resource_id': 'original', 'provider_order_id': 'order', 'custody_workspace_id': 'w',
        'managed_webshare_version': 1, 'dedicated_isp_confirmed': True, 'verified_by': 'operator',
        'verified_at': datetime(2026, 1, 1, 0, 0, 0, 123000), 'expires_at': datetime(2027, 1, 1),
        'evidence_digest': 'a' * 64, 'import_basis_digest': 'b' * 64, 'credential_generation': 'generation',
        'password_enc': 'retained-secret', 'username': 'retained-identity'}
    if fault == 'resource': asset['provider_resource_id'] = 'replacement'
    if fault == 'custody': asset['custody_workspace_id'] = 'other'
    if fault == 'missing_review': asset.pop('verified_at')
    if fault == 'expired': asset['expires_at'] = datetime(2020, 1, 1)
    await db.outreach_proxy_inventory.insert_one(asset)
    before = await db.outreach_proxy_inventory.find_one({'_id': asset['_id']})
    held = await db.outreach_physical_requests.find({}).sort('_id', 1).to_list(length=100)
    result = await inspect(db)
    reason = 'local_webshare_import_metadata_consistent' if fault == 'matching' else 'webshare_import_metadata_review_required'
    assert result['findings'][reason] == 1
    assert await db.outreach_proxy_inventory.find_one({'_id': asset['_id']}) == before
    assert await db.outreach_physical_requests.find({}).sort('_id', 1).to_list(length=100) == held
    assert not result['provider_ownership_verified'] and not result['activation_allowed']
    await db.outreach_proxy_inventory.update_one({'_id': asset['_id']}, {'$set': {'password_enc': 'replacement', 'username': 'replacement'}})
    assert (await inspect(db))['digest'] == result['digest']
    await db.outreach_proxy_inventory.update_one({'_id': asset['_id']}, {'$set': {'evidence_digest': 'c' * 64}})
    assert (await inspect(db))['digest'] != result['digest']


@pytest.mark.parametrize('fault', ['matching', 'asset_missing', 'lease_missing', 'lease_sender', 'proxy_shared', 'matching_webshare', 'sender_duplicate', 'sticky_scope'])
async def test_native_sender_reverse_assignment_preserves_retained_state(real_restore, fault):
    db = real_restore
    await prepare(db)
    asset = {'_id': 'reverse-asset', 'workspace_id': 'w', 'last_workspace_id': 'w',
        'provider': 'iproyal_static', 'host': '191.116.125.248', 'country_code': 'US',
        'credential_generation': 'generation', 'password_enc': 'retained-secret'}
    lease = {'_id': 'reverse-asset', 'workspace_id': 'w', 'sender_id': 'other' if fault == 'lease_sender' else 'reverse-sender',
        'provider': 'iproyal_static', 'country_code': 'US', 'reservation_job_id': 'retained-reservation'}
    sender = {'_id': 'reverse-account', 'id': 'reverse-sender', 'workspace_id': 'w',
        'proxy': {'proxy_id': 'reverse-asset', 'credential_generation': 'generation', 'password_enc': 'retained-secret'},
        'session_cookie_enc': 'retained-cookie'}
    if fault == 'matching_webshare': asset['provider'] = lease['provider'] = 'webshare_plan'
    if fault == 'sticky_scope': asset['last_workspace_id'] = 'other'
    if fault != 'asset_missing': await db.outreach_proxy_inventory.insert_one(asset)
    if fault != 'lease_missing': await db.outreach_proxy_leases.insert_one(lease)
    await db.outreach_accounts.insert_one(sender)
    if fault == 'proxy_shared': await db.outreach_accounts.insert_one({**sender, '_id': 'other-account', 'id': 'other-sender'})
    if fault == 'sender_duplicate': await db.outreach_accounts.insert_one({**sender, '_id': 'duplicate-account'})
    names = ['outreach_proxy_inventory', 'outreach_proxy_leases', 'outreach_accounts', 'outreach_physical_requests']
    before = {name: await db[name].find({}).sort('_id', 1).to_list(length=200) for name in names}
    result = await inspect(db)
    reason = {'matching': 'local_sender_assignment_links_match', 'asset_missing': 'sender_proxy_asset_review_required',
        'lease_missing': 'sender_proxy_lease_review_required', 'lease_sender': 'sender_proxy_lease_review_required',
        'proxy_shared': 'sender_proxy_shared', 'matching_webshare': 'local_sender_assignment_links_match',
        'sender_duplicate': 'sender_identity_ambiguous', 'sticky_scope': 'sender_proxy_asset_review_required'}[fault]
    assert result['findings'][reason] >= 1
    assert not result['activation_allowed'] and not result['provider_ownership_verified']
    for name in names: assert await db[name].find({}).sort('_id', 1).to_list(length=200) == before[name]
    await db.outreach_accounts.update_one({'_id': 'reverse-account'}, {'$set': {'session_cookie_enc': 'replacement'}})
    assert (await inspect(db))['digest'] == result['digest']
    await db.outreach_accounts.update_one({'_id': 'reverse-account'}, {'$set': {'proxy.proxy_id': 'replacement'}})
    assert (await inspect(db))['digest'] != result['digest']


@pytest.mark.parametrize('collection,prefix,result_state', [
    ('outreach_email_operations', 'email_operation', 'accepted'),
    ('outreach_email_discoveries', 'finder_operation', 'found')])
@pytest.mark.parametrize('fault', ['matching', 'foreign', 'capacity'])
async def test_native_provider_operation_inventory_preserves_held_results(real_restore, collection, prefix, result_state, fault):
    db = real_restore
    await prepare(db)
    base_count = await db[collection].count_documents({'workspace_id': 'w'})
    rows = [{'_id': 'review-' + str(i), 'workspace_id': 'other' if fault == 'foreign' else 'w',
        'status': state, 'owner_token': 'held-owner', 'email': 'private@example.test',
        'receipt': {'original': 'retained'}, 'non_call_history': [{'private': 'history'}]}
        for i, state in enumerate(['dispatching', 'uncertain', result_state, 'not_submitted', None])]
    await db[collection].insert_many(rows)
    if fault == 'capacity':
        await db[collection].insert_many([{'_id': 'extra-' + str(i), 'workspace_id': 'w'} for i in range(100)])
    before = await db[collection].find({}).sort('_id', 1).to_list(length=200)
    physical = await db.outreach_physical_requests.find({}).sort('_id', 1).to_list(length=100)
    if fault == 'capacity':
        with pytest.raises(ValueError): await inspect(db)
    else:
        result = await inspect(db)
        assert result['counts'][collection] == base_count + (0 if fault == 'foreign' else 5)
        if fault == 'matching':
            assert result['findings'][prefix + '_unresolved'] >= 2
            assert result['findings'][prefix + '_recorded_result_review'] >= 1
            assert result['findings'][prefix + '_state_unproven'] >= 1
        assert not result['activation_allowed'] and not result['completeness_verified']
    assert await db[collection].find({}).sort('_id', 1).to_list(length=200) == before
    assert await db.outreach_physical_requests.find({}).sort('_id', 1).to_list(length=100) == physical
    if fault == 'matching':
        await db[collection].update_one({'_id': rows[0]['_id']}, {'$set': {'receipt': {'replacement': 'private'}}})
        assert (await inspect(db))['digest'] == result['digest']
        await db[collection].update_one({'_id': rows[0]['_id']}, {'$set': {'status': 'not_submitted'}})
        assert (await inspect(db))['digest'] != result['digest']
