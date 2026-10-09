"""Bounded deletion exclusions cannot activate restored work or fabricate purge."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import pytest
import pytest_asyncio
from outreach.core import restore_exclusions as ex, erasure, suppression, restore_epoch as epoch
from tests.test_outreach_restore_epoch import restored_db, prepare, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]
IDENTITY = 'd' * 64
DATE = '2026-01-02T03:04:05.123Z'


def source(**changes):
    doc = {'version': 1, 'workspace_guard_digest': suppression.guard_scope('w')['_id'],
           'deletion_state': 'erased', 'requested_at': DATE,
           'identities': [{'identity_digest': IDENTITY, 'requested_at': DATE}]}
    doc.update(changes)
    return json.dumps(doc, sort_keys=True).encode()


@pytest_asyncio.fixture
async def excluded_db(restored_db, monkeypatch):
    await prepare(restored_db)
    restored_db.outreach_suppression_guards.docs.append({**suppression.guard_scope('w'), 'revision': 0})
    monkeypatch.setattr(type(restored_db.account_erasure_tombstones), 'with_options', lambda self, **kwargs: self,
                        raising=False)
    async def memory_control(db, workspace, operation):
        return await operation(db)
    monkeypatch.setattr(erasure, '_control', memory_control)
    return restored_db


async def apply(db, raw=None, view=None, **changes):
    raw = source() if raw is None else raw
    service = ex.RestoreExclusions(db)
    view = await service.inspect('w', raw) if view is None else view
    args = dict(operator='operator', evidence_digest=EVIDENCE,
                source_digest=hashlib.sha256(raw).hexdigest(), review_digest=view['digest'], workers_drained=True)
    args.update(changes)
    return await service.apply('w', raw, **args)


async def test_missing_exclusions_install_once_without_purge_or_authority_changes(excluded_db):
    db = excluded_db
    before = deepcopy(db.outreach_sender_execution.docs)
    raw = source(); view = await ex.RestoreExclusions(db).inspect('w', raw)
    result = await apply(db, raw, view)
    assert result['applied'] and not result['activation_allowed'] and not result['purged']
    assert db.outreach_sender_execution.docs == before
    guard = db.outreach_suppression_guards.docs[0]
    assert guard['erasure_state'] == 'restore_excluded' and 'erasure_completed_at' not in guard
    assert db.account_erasure_tombstones.docs[0]['requested_at'].microsecond == 123000
    guard['unrelated'] = 'preserved'
    assert (await apply(db, raw, view))['recovered']
    assert guard['unrelated'] == 'preserved'
    with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')
    journal = db.outreach_restore_exclusions.docs[0]
    assert IDENTITY not in json.dumps(journal, default=str)
    assert 'operator' not in journal


async def test_existing_tombstone_and_completed_closure_are_preserved(excluded_db):
    db = excluded_db
    old = {'_id': IDENTITY, 'requested_at': datetime(2025, 1, 1, tzinfo=timezone.utc), 'old': True}
    db.account_erasure_tombstones.docs.append(deepcopy(old))
    db.outreach_suppression_guards.docs[0].update({
        'erasure_state': 'erased', 'erasure_completed_at': epoch.now()})
    guard = deepcopy(db.outreach_suppression_guards.docs[0])
    await apply(db)
    assert db.account_erasure_tombstones.docs[0] == old
    assert db.outreach_suppression_guards.docs[0] == guard


@pytest.mark.parametrize('change', ['drain', 'flags', 'source_digest', 'review_digest', 'operator', 'evidence', 'root', 'workspace'])
async def test_invalid_review_is_read_only(excluded_db, monkeypatch, change):
    db = excluded_db; service = ex.RestoreExclusions(db); view = await service.inspect('w', source())
    args = {}
    if change == 'drain': args['workers_drained'] = False
    if change == 'flags': monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED', 'true')
    if change == 'source_digest': args['source_digest'] = 'a' * 64
    if change == 'review_digest': args['review_digest'] = 'a' * 64
    if change == 'operator': args['operator'] = ''
    if change == 'evidence': args['evidence_digest'] = 'invalid'
    if change == 'root': db.outreach_execution_epochs.docs.clear()
    if change == 'workspace':
        with pytest.raises(ValueError): await service.inspect('other', source())
        return
    with pytest.raises(ValueError): await apply(db, view=view, **args)
    assert not db.account_erasure_tombstones.docs and not db.outreach_restore_exclusions.docs


@pytest.mark.parametrize('change', [
    {'version': True}, {'version': 2}, {'secret': 'forbidden'}, {'deletion_state': 'active'},
    {'requested_at': '2030-01-01T00:00:00.000Z'}, {'requested_at': '2026-01-02'},
    {'identities': []}, {'identities': [{'identity_digest': 'UID', 'requested_at': DATE}]},
    {'identities': [{'identity_digest': IDENTITY, 'requested_at': DATE, 'email': 'forbidden'}]},
    {'identities': [{'identity_digest': IDENTITY, 'requested_at': DATE}] * 2},
    {'identities': [{'identity_digest': format(i, '064x'), 'requested_at': DATE} for i in range(101)]}])
async def test_strict_manifest_rejects_unknown_or_unproven_facts(change):
    with pytest.raises(ValueError): ex.parse(source(**change))


@pytest.mark.parametrize('raw', [b'{}', b'\xff', b'{"version":1,"version":1}', b'NaN', b'x' * 65537])
async def test_malformed_or_oversize_source_is_rejected(raw):
    with pytest.raises(ValueError): ex.parse(raw)


async def test_export_requires_all_original_selected_facts(excluded_db):
    db = excluded_db
    with pytest.raises(ValueError): await ex.export_manifest(db, 'w', [IDENTITY])
    db.outreach_suppression_guards.docs[0].update({'erasure_state': 'stopped',
        'erasure_requested_at': datetime(2026, 1, 2, 3, 4, 5, 123999, tzinfo=timezone.utc)})
    with pytest.raises(ValueError): await ex.export_manifest(db, 'w', [IDENTITY])
    db.account_erasure_tombstones.docs.append({'_id': IDENTITY,
        'requested_at': datetime(2026, 1, 2, 3, 4, 5, 123000)})
    doc = await ex.export_manifest(db, 'w', [IDENTITY])
    assert doc['requested_at'] == DATE and ex.parse(json.dumps(doc).encode()).identities[0][0] == IDENTITY


async def test_saved_receipt_does_not_fabricate_missing_exclusions(excluded_db):
    view = await ex.RestoreExclusions(excluded_db).inspect('w', source())
    await apply(excluded_db, view=view)
    excluded_db.account_erasure_tombstones.docs.clear()
    with pytest.raises(ValueError): await apply(excluded_db, view=view)
