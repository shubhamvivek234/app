"""Selected recipient negatives restore without manufacturing reply outcomes."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import pytest
import pytest_asyncio
from outreach.core import restore_suppressions as rs, suppression, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from outreach.core.email_finder import is_lead_email_available
from outreach.core.erasure import workspace_is_open as real_workspace_is_open
from outreach.core.lead_importer import check_compound_suppression
from tests.test_outreach_restore_epoch import restored_db, prepare, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]
DATE = '2026-01-02T03:04:05.123Z'
EMAIL = 'recipient@example.com'


def source(**changes):
    doc = {'version': 1, 'workspace_guard_digest': suppression.guard_scope('w')['_id'], 'facts': [
        {'kind': 'email', 'field': 'email', 'value': EMAIL, 'blocked_at': DATE, 'record_digest': 'd' * 64},
        {'kind': 'dnc', 'field': 'vanity_name', 'value': 'recipient', 'blocked_at': DATE, 'record_digest': 'e' * 64}]}
    doc.update(changes)
    return json.dumps(doc, sort_keys=True).encode()


@pytest_asyncio.fixture
async def suppression_db(restored_db, monkeypatch):
    monkeypatch.setattr('outreach.core.erasure.workspace_is_open', real_workspace_is_open)
    await prepare(restored_db)
    restored_db.outreach_suppression_guards.docs.append({**suppression.guard_scope('w'), 'revision': 0})
    monkeypatch.setattr(type(restored_db.outreach_email_suppressions), 'with_options', lambda self, **kwargs: self,
                        raising=False)
    async def memory_control(db, workspace, operation):
        return await operation(db)
    monkeypatch.setattr(suppression, 'mutate_suppression', memory_control)
    return restored_db


async def apply(db, raw=None, view=None, **changes):
    raw = source() if raw is None else raw
    service = rs.RestoreSuppressions(db)
    view = await service.inspect('w', raw) if view is None else view
    args = dict(operator='operator', evidence_digest=EVIDENCE,
                source_digest=hashlib.sha256(raw).hexdigest(), review_digest=view['digest'], workers_drained=True)
    args.update(changes)
    return await service.apply('w', raw, **args)


async def test_restored_blocks_reach_existing_gates_without_reply_or_grant(suppression_db):
    db = suppression_db
    names = ('outreach_leads', 'outreach_inbox_threads', 'outreach_accounts', 'outreach_sender_execution',
             'outreach_campaigns', 'outreach_manual_actions', 'outreach_request_budgets')
    before = {name: deepcopy(getattr(db, name).docs) for name in names}
    result = await apply(db)
    assert result['applied'] and not result['activation_allowed'] and not result['reply_history_restored']
    assert not await is_lead_email_available(db, 'w', {'email': EMAIL})
    assert await check_compound_suppression('w', [{'linkedin_url': 'https://www.linkedin.com/in/recipient'}], db)
    assert await is_lead_email_available(db, 'other', {'email': EMAIL})
    assert not await check_compound_suppression('other', [{'vanity_name': 'recipient'}], db)
    for name in names: assert getattr(db, name).docs == before[name]
    journal = db.outreach_restore_suppressions.docs[0]
    assert EMAIL not in json.dumps(journal, default=str) and 'recipient' not in json.dumps(journal, default=str)
    assert db.outreach_email_suppressions.docs[0]['created_at'].microsecond == 123000
    with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')


async def test_exact_retry_preserves_existing_and_later_metadata(suppression_db):
    db = suppression_db
    existing = {'_id': 'original-email', 'workspace_id': 'w', 'email': EMAIL,
                'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc), 'reason': 'reply', 'private': 'retained'}
    db.outreach_email_suppressions.docs.append(deepcopy(existing))
    view = await rs.RestoreSuppressions(db).inspect('w', source())
    await apply(db, view=view)
    assert db.outreach_email_suppressions.docs[0] == existing
    dnc = db.outreach_do_not_contact.docs[0]; dnc['later_metadata'] = True
    before = deepcopy(dnc)
    assert (await apply(db, view=view))['recovered']
    assert dnc == before and len(db.outreach_restore_suppressions.docs) == 1


@pytest.mark.parametrize('fault', ['drain', 'flags', 'source', 'review', 'operator', 'evidence', 'scope', 'epoch'])
async def test_unproven_review_never_installs(suppression_db, monkeypatch, fault):
    db = suppression_db; view = await rs.RestoreSuppressions(db).inspect('w', source()); changes = {}
    raw = source()
    if fault == 'drain': changes['workers_drained'] = False
    if fault == 'flags': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if fault == 'source': changes['source_digest'] = 'a' * 64
    if fault == 'review': changes['review_digest'] = 'a' * 64
    if fault == 'operator': changes['operator'] = ''
    if fault == 'evidence': changes['evidence_digest'] = 'unproven'
    if fault == 'scope': raw = source(workspace_guard_digest='a' * 64)
    if fault == 'epoch': db.outreach_execution_epochs.docs = []
    with pytest.raises(ValueError): await apply(db, raw, view, **changes)
    assert not db.outreach_email_suppressions.docs and not db.outreach_do_not_contact.docs


@pytest.mark.parametrize('fault', ['closed', 'saved_closed', 'duplicate_email', 'changed_email', 'collision', 'missing_saved'])
async def test_target_conflicts_and_closed_tenants_deny(suppression_db, fault):
    db = suppression_db; view = await rs.RestoreSuppressions(db).inspect('w', source())
    if fault in {'saved_closed', 'missing_saved'}: await apply(db, view=view)
    if fault in {'closed', 'saved_closed'}: db.outreach_suppression_guards.docs[0]['erasure_state'] = 'erased'
    if fault in {'duplicate_email', 'changed_email'}:
        for i in range(2 if fault == 'duplicate_email' else 1):
            db.outreach_email_suppressions.docs.append({'_id': str(i), 'workspace_id': 'w', 'email': EMAIL,
                'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc)})
    if fault == 'collision':
        fact = next(fact for fact in rs.parse(source()).facts if fact.kind == 'dnc')
        db.outreach_do_not_contact.docs.append({'_id': rs.dnc_scope('w', fact)['_id'], 'workspace_id': 'w',
            'identifiers': {'vanity_name': 'someone-else'}, 'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc)})
    if fault == 'missing_saved': db.outreach_do_not_contact.docs = []
    with pytest.raises(ValueError): await apply(db, view=view)


@pytest.mark.parametrize('fault', ['version', 'unknown', 'empty', 'duplicate', 'future', 'bad_date', 'mixed_case',
                                   'kind', 'field', 'digest', 'oversize', 'duplicate_key', 'nonfinite', 'utf8'])
async def test_strict_source_rejects_unproven_input(fault):
    doc = json.loads(source()); raw = None
    if fault == 'version': doc['version'] = True
    if fault == 'unknown': doc['extra'] = 'private'
    if fault == 'empty': doc['facts'] = []
    if fault == 'duplicate': doc['facts'].append(doc['facts'][0])
    if fault == 'future': doc['facts'][0]['blocked_at'] = '2099-01-01T00:00:00.000Z'
    if fault == 'bad_date': doc['facts'][0]['blocked_at'] = '2026-01-02'
    if fault == 'mixed_case': doc['facts'][0]['value'] = 'Recipient@example.com'
    if fault == 'kind': doc['facts'][0]['kind'] = 'reply'
    if fault == 'field': doc['facts'][0]['field'] = 'member_urn'
    if fault == 'digest': doc['facts'][0]['record_digest'] = 'private'
    if fault == 'oversize': raw = b'x' * 65537
    if fault == 'duplicate_key': raw = source().replace(b'"version": 1', b'"version": 1, "version": 1')
    if fault == 'nonfinite': raw = source().replace(b'"version": 1', b'"version": NaN')
    if fault == 'utf8': raw = b'\xff'
    with pytest.raises(ValueError): rs.parse(json.dumps(doc).encode() if raw is None else raw)


async def test_export_preserves_current_and_saved_aliases_without_content(suppression_db):
    db = suppression_db; date = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    db.outreach_do_not_contact.docs.append({'_id': 'dnc-source', 'workspace_id': 'w', 'created_at': date,
        'vanity_name': 'current', 'email': 'current@example.com', 'identifiers': {'vanity_name': 'old'},
        'reason': 'private-original-reason'})
    db.outreach_email_suppressions.docs.append({'_id': 'email-source', 'workspace_id': 'w', 'created_at': date,
        'email': EMAIL, 'reason': 'private-original-reason'})
    doc = await rs.export_manifest(db, 'w', ['dnc-source'], ['email-source'], workers_drained=True)
    raw = json.dumps(doc).encode(); parsed = rs.parse(raw)
    assert len(parsed.facts) == 4 and {f.value for f in parsed.facts} == {'current', 'old', 'current@example.com', EMAIL}
    assert 'private-original-reason' not in raw.decode() and 'dnc-source' not in raw.decode()
    assert all(f.blocked_at.microsecond == 123000 for f in parsed.facts)
    with pytest.raises(ValueError): await rs.export_manifest(db, 'other', ['dnc-source'], [], workers_drained=True)


@pytest.mark.parametrize('fault', ['empty', 'missing', 'imported', 'timestamp', 'identity', 'capacity', 'duplicate'])
async def test_export_denies_unsupported_originals(suppression_db, fault):
    db = suppression_db
    row = {'_id': 'source', 'workspace_id': 'w', 'email': EMAIL,
           'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}
    if fault == 'imported': row['restore_provenance'] = 'selected_negative'
    if fault == 'timestamp': row['created_at'] = '2026-01-01'
    if fault == 'identity': row['email'] = 'unknown'
    db.outreach_email_suppressions.docs.append(row)
    refs = ['source']
    if fault == 'empty': refs = []
    if fault == 'missing': refs = ['missing']
    if fault == 'capacity': refs = [str(i) for i in range(101)]
    if fault == 'duplicate': refs = ['source', 'source']
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', [], refs, workers_drained=True)


@pytest.mark.parametrize('field,value', [('normalized_url', 'https://linkedin.com/in/recipient'),
    ('normalized_url', 'https://www.linkedin.com/in/recipient'), ('member_urn', 'urn:li:member:123456'),
    ('sales_lead_urn', 'urn:li:fs_salesProfile:ACoExample'), ('email', EMAIL)])
async def test_each_supported_dnc_identity_blocks_existing_matcher(suppression_db, field, value):
    doc = json.loads(source()); doc['facts'] = [{**doc['facts'][1], 'field': field, 'value': value}]
    await apply(suppression_db, json.dumps(doc).encode())
    candidate = {'identifiers': {field: value}}
    assert await check_compound_suppression('w', [candidate], suppression_db)


async def test_original_flat_saved_duplicates_are_deduplicated_and_source_drain_required(suppression_db):
    db = suppression_db
    db.outreach_do_not_contact.docs.append({'_id': 'source', 'workspace_id': 'w', 'created_at': epoch.now(),
        'vanity_name': 'recipient', 'identifiers': {'vanity_name': 'recipient'}, 'linkedin_urn': 'urn:li:person:ACoExample'})
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', ['source'], [])
    doc = await rs.export_manifest(db, 'w', ['source'], [], workers_drained=True)
    assert len(doc['facts']) == 2
    db.outreach_suppression_guards.docs[0]['erasure_state'] = 'stopped'
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', ['source'], [], workers_drained=True)
    with pytest.raises(ValueError): await rs.RestoreSuppressions(db).inspect('w', source())


async def test_expansion_capacity_and_independent_duplicate_aliases_deny(suppression_db):
    db = suppression_db
    for i in range(51):
        db.outreach_do_not_contact.docs.append({'_id': str(i), 'workspace_id': 'w', 'created_at': epoch.now(),
            'vanity_name': f'person{i}', 'email': f'person{i}@example.com'})
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', [str(i) for i in range(51)], [], workers_drained=True)
    db.outreach_do_not_contact.docs[1]['vanity_name'] = 'person0'
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', ['0', '1'], [], workers_drained=True)


@pytest.mark.parametrize('change', ['operator', 'evidence', 'review', 'late_flags'])
async def test_saved_review_must_match_and_late_policy_change_denies(suppression_db, monkeypatch, change):
    db = suppression_db; view = await rs.RestoreSuppressions(db).inspect('w', source())
    await apply(db, view=view); changes = {}
    if change == 'operator': changes['operator'] = 'other'
    if change == 'evidence': changes['evidence_digest'] = 'f' * 64
    if change == 'review': changes['review_digest'] = 'f' * 64
    if change == 'late_flags':
        original = rs.RestoreSuppressions._view
        async def late(self, *args, **kwargs):
            result = await original(self, *args, **kwargs)
            monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED', 'true')
            return result
        monkeypatch.setattr(rs.RestoreSuppressions, '_view', late)
    with pytest.raises(ValueError): await apply(db, view=view, **changes)
