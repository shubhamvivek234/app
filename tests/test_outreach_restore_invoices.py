"""Selected consumed invoice fingerprints restore exclusions, never paid access."""
from copy import deepcopy
import hashlib
import json
import pytest
import pytest_asyncio
from outreach.core import restore_invoices as ri, suppression, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from outreach.core.paid_access import claim_invoice_reference
from tests.test_outreach_restore_suppressions import suppression_db
from tests.test_outreach_restore_epoch import restored_db, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]
INVOICE = canonical_hash(['verified_invoice', 'private-invoice'])
BINDING = 'b' * 64


def source(**changes):
    doc = {'version': 1, 'workspace_guard_digest': suppression.guard_scope('w')['_id'],
           'invoices': [{'invoice_digest': INVOICE, 'binding_digest': BINDING}]}
    doc.update(changes)
    return json.dumps(doc, sort_keys=True).encode()


async def apply(db, raw=None, view=None, **changes):
    raw = source() if raw is None else raw
    service = ri.RestoreInvoices(db)
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


async def test_negative_restoration_never_recreates_receipt_or_entitlement(suppression_db):
    db = suppression_db
    names = ('outreach_payment_receipts', 'outreach_entitlements', 'outreach_access_requests', 'outreach_campaigns',
             'outreach_sender_execution', 'outreach_manual_actions', 'outreach_proxy_inventory')
    before = {name: deepcopy(getattr(db, name).docs) for name in names}
    result = await apply(db)
    assert result['applied'] and not result['activation_allowed'] and not result['payment_restored']
    assert db.account_invoice_guards.docs[0]['binding_digest'] == BINDING
    assert db.account_invoice_guards.docs[0]['restore_reuse_blocked'] is True
    for name in names: assert getattr(db, name).docs == before[name]
    assert 'private-invoice' not in json.dumps(db.outreach_restore_invoices.docs, default=str)
    with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')


async def test_existing_binding_metadata_preserved_and_closed_hash_retry_allowed(suppression_db):
    db = suppression_db
    db.account_invoice_guards.docs.append({'_id': INVOICE, 'binding_digest': BINDING, 'original_metadata': True})
    view = await ri.RestoreInvoices(db).inspect('w', source()); await apply(db, view=view)
    row = db.account_invoice_guards.docs[0]; row['later_metadata'] = True
    before = deepcopy(row)
    db.outreach_suppression_guards.docs[0]['erasure_state'] = 'erased'
    assert (await apply(db, view=view))['recovered']
    assert row == before and row['original_metadata']


@pytest.mark.parametrize('fault', ['drain', 'flag', 'source', 'review', 'operator', 'evidence', 'scope', 'epoch',
    'binding', 'saved_missing', 'saved_latch', 'saved_operator', 'saved_evidence', 'saved_review'])
async def test_changed_proof_or_missing_negative_denies(suppression_db, monkeypatch, fault):
    db = suppression_db; view = await ri.RestoreInvoices(db).inspect('w', source()); changes = {}; raw = source()
    if fault.startswith('saved_'): await apply(db, view=view)
    if fault == 'drain': changes['workers_drained'] = False
    if fault == 'flag': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if fault == 'source': changes['source_digest'] = 'f' * 64
    if fault in {'review', 'saved_review'}: changes['review_digest'] = 'f' * 64
    if fault in {'operator', 'saved_operator'}: changes['operator'] = 'other' if fault.startswith('saved') else ''
    if fault in {'evidence', 'saved_evidence'}: changes['evidence_digest'] = 'f' * 64 if fault.startswith('saved') else 'bad'
    if fault == 'scope': raw = source(workspace_guard_digest='f' * 64)
    if fault == 'epoch': db.outreach_execution_epochs.docs = []
    if fault == 'binding': db.account_invoice_guards.docs.append({'_id': INVOICE, 'binding_digest': 'f' * 64})
    if fault == 'saved_missing': db.account_invoice_guards.docs = []
    if fault == 'saved_latch': db.account_invoice_guards.docs[0].pop('restore_reuse_blocked')
    with pytest.raises(ValueError): await apply(db, raw, view, **changes)


@pytest.mark.parametrize('fault', ['version', 'unknown', 'empty', 'duplicate', 'capacity', 'raw_invoice', 'binding',
    'oversize', 'duplicate_key', 'nonfinite', 'utf8'])
async def test_strict_digest_only_manifest(fault):
    doc = json.loads(source()); raw = None
    if fault == 'version': doc['version'] = True
    if fault == 'unknown': doc['timestamp'] = 'invented'
    if fault == 'empty': doc['invoices'] = []
    if fault == 'duplicate': doc['invoices'] *= 2
    if fault == 'capacity': doc['invoices'] *= 101
    if fault == 'raw_invoice': doc['invoices'][0]['invoice_digest'] = 'private-invoice'
    if fault == 'binding': doc['invoices'][0]['binding_digest'] = 'unproven'
    if fault == 'oversize': raw = b'x' * 65537
    if fault == 'duplicate_key': raw = source().replace(b'"version": 1', b'"version": 1, "version": 1')
    if fault == 'nonfinite': raw = b'{"version": Infinity}'
    if fault == 'utf8': raw = b'\xff'
    with pytest.raises(ValueError): ri.parse(json.dumps(doc).encode() if raw is None else raw)


async def test_original_global_guard_export_has_no_ownership_or_payment_claim(suppression_db):
    db = suppression_db
    db.account_invoice_guards.docs.append({'_id': INVOICE, 'binding_digest': BINDING})
    doc = await ri.export_manifest(db, 'w', [INVOICE], workers_drained=True)
    assert doc == json.loads(source()) and 'private-invoice' not in json.dumps(doc)
    assert 'workspace_id' not in doc['invoices'][0] and 'paid_through' not in doc['invoices'][0]


@pytest.mark.parametrize('fault', ['empty', 'missing', 'duplicate', 'capacity', 'digest', 'binding', 'imported', 'drain'])
async def test_export_requires_selected_original_digest_facts(suppression_db, fault):
    db = suppression_db; row = {'_id': INVOICE, 'binding_digest': BINDING}; refs = [INVOICE]; drained = True
    if fault == 'empty': refs = []
    if fault == 'missing': refs = ['f' * 64]
    if fault == 'duplicate': refs *= 2
    if fault == 'capacity': refs *= 101
    if fault == 'digest': refs = ['raw-invoice']
    if fault == 'binding': row['binding_digest'] = 'raw-terms'
    if fault == 'imported': row['restore_reuse_blocked'] = True
    if fault == 'drain': drained = False
    db.account_invoice_guards.docs.append(row)
    with pytest.raises(ValueError): await ri.export_manifest(db, 'w', refs, workers_drained=drained)


@pytest_asyncio.fixture
async def legacy_payment_db(suppression_db, monkeypatch):
    from datetime import timedelta
    from tests.outreach_memory import Collection
    original_update, original_find = Collection.update_one, Collection.find_one
    async def update(self, *args, **kwargs):
        kwargs.pop("session", None); return await original_update(self, *args, **kwargs)
    async def find(self, *args, **kwargs):
        kwargs.pop("session", None); return await original_find(self, *args, **kwargs)
    monkeypatch.setattr(Collection, "update_one", update); monkeypatch.setattr(Collection, "find_one", find)
    db = suppression_db
    db.outreach_execution_epochs.docs = []
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false'); monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '')
    term = epoch.now() + timedelta(days=30)
    db.outreach_access_requests.docs.append({'_id': 'request', 'workspace_id': 'w', 'country_code': 'IN', 'seats': 1})
    db.outreach_proxy_inventory.docs.append({'_id': 'ip', 'last_workspace_id': 'w', 'country_code': 'IN',
        'status': 'available', 'provider': 'iproyal_static', 'expires_at': term + timedelta(days=1)})
    return db, term


async def pay(db, term, invoice='private-invoice'):
    from outreach.core.paid_access import record_verified_payment
    return await record_verified_payment(db, 'w', invoice, 'operator', 1, term)


async def test_legacy_payment_and_exact_retry_never_reactivate_revoked_state(legacy_payment_db):
    db, term = legacy_payment_db
    assert (await pay(db, term))['status'] == 'active'
    db.outreach_entitlements.docs[0].update(status='expired', is_revoked=True)
    before = deepcopy(db.outreach_entitlements.docs)
    returned = await pay(db, term)
    assert returned['status'] == 'expired' and returned['is_revoked']
    assert db.outreach_entitlements.docs == before and len(db.outreach_payment_receipts.docs) == 1


async def test_restored_consumed_reference_denies_payment_but_preserves_archival_binding(legacy_payment_db):
    from outreach.core.paid_access import claim_invoice_reference
    db, term = legacy_payment_db
    await claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
    row = db.account_invoice_guards.docs[0]; row['restore_reuse_blocked'] = True
    before = deepcopy(row)
    await claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
    assert row == before
    with pytest.raises(ValueError, match='restore-blocked'): await pay(db, term)
    assert not db.outreach_payment_receipts.docs and not db.outreach_entitlements.docs


@pytest.mark.parametrize('change', ['seats', 'paid_through', 'payment_source', 'last_invoice_id', 'missing'])
async def test_receipt_retry_requires_exact_current_entitlement(legacy_payment_db, change):
    from datetime import timedelta
    db, term = legacy_payment_db; await pay(db, term)
    entitlement = db.outreach_entitlements.docs[0]
    if change == 'seats': entitlement['seats'] = 2
    if change == 'paid_through': entitlement['paid_through'] += timedelta(days=1)
    if change == 'payment_source': entitlement['payment_source'] = 'unproven'
    if change == 'last_invoice_id': entitlement['last_invoice_id'] = 'replacement'
    if change == 'missing': db.outreach_entitlements.docs = []
    with pytest.raises(ValueError, match='reconciliation'): await pay(db, term)


@pytest.mark.parametrize('change', ['malformed_flag', 'revoked', 'request', 'restore_epoch'])
async def test_payment_cannot_bypass_current_stop_or_changed_authority(legacy_payment_db, monkeypatch, change):
    from outreach.core.paid_access import claim_invoice_reference
    db, term = legacy_payment_db
    if change == 'malformed_flag':
        await claim_invoice_reference(db, 'private-invoice', 'w', 1, term)
        db.account_invoice_guards.docs[0]['restore_reuse_blocked'] = False
    if change == 'revoked': db.outreach_entitlements.docs.append({'workspace_id': 'w', 'is_revoked': True})
    if change == 'request':
        original = db.outreach_access_requests.find_one; calls = 0
        async def replace(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: db.outreach_access_requests.docs[0]['country_code'] = 'US'
            return await original(*args, **kwargs)
        monkeypatch.setattr(db.outreach_access_requests, 'find_one', replace)
    if change == 'restore_epoch': monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', 'a' * 64)
    with pytest.raises(ValueError): await pay(db, term)
    assert not db.outreach_payment_receipts.docs


@pytest.mark.parametrize('late', [False, True])
async def test_payment_deadline_rechecks_use_actual_final_clock(legacy_payment_db, monkeypatch, late):
    from datetime import datetime, timedelta
    from outreach.core import paid_access
    db, term = legacy_payment_db; initial = epoch.now(); calls = 0
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            calls += 1
            return initial if calls < (3 if late else 2) else term + timedelta(seconds=1)
    monkeypatch.setattr(paid_access, 'datetime', Clock)
    with pytest.raises(ValueError, match='expired before finalization'): await pay(db, term)
