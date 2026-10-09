"""Selected sender-specific negative reply evidence; never inbox reconstruction."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import pytest
from outreach.core import restore_reply_stops as rs, suppression, restore_epoch as epoch
from outreach.core.authorization import canonical_hash
from outreach.tasks.sequence_executor import _recipient_has_reply
from tests.test_outreach_restore_suppressions import suppression_db
from tests.test_outreach_restore_epoch import restored_db, EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]
SENDER = 'urn:li:fsd_profile:Sender'
RECIPIENT = 'urn:li:fs_miniProfile:Recipient'
URL = 'https://www.linkedin.com/in/recipient'
DATE = '2026-01-02T03:04:05.123Z'


@pytest.fixture(autouse=True)
def memory_majority(monkeypatch):
    from tests.outreach_memory import Database
    monkeypatch.setattr(Database, 'with_options', lambda self, **kwargs: self, raising=False)


def source(**changes):
    doc = {'version': 1, 'workspace_guard_digest': suppression.guard_scope('w')['_id'], 'facts': [
        {'sender_id': 'sender', 'sender_identity_digest': canonical_hash(['linkedin_sender_v1', 'w', 'sender', SENDER]),
         'field': 'member_urn', 'value': RECIPIENT, 'blocked_at': DATE, 'record_digest': 'd' * 64},
        {'sender_id': 'sender', 'sender_identity_digest': canonical_hash(['linkedin_sender_v1', 'w', 'sender', SENDER]),
         'field': 'normalized_url', 'value': URL, 'blocked_at': DATE, 'record_digest': 'd' * 64}]}
    doc.update(changes)
    return json.dumps(doc, sort_keys=True).encode()


def add_sender(db):
    db.outreach_accounts.docs.append({'_id': 'sender-row', 'workspace_id': 'w', 'id': 'sender',
                                    'linkedin_urn': SENDER, 'credential_generation': 1})


def add_thread(db):
    db.outreach_inbox_threads.docs.append({'_id': 'thread', 'workspace_id': 'w', 'account_id': 'sender',
        'lead_urn': RECIPIENT, 'lead_profile_url': URL, 'has_lead_reply': True,
        'messages': [{'sender_type': 'lead', 'timestamp': datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc),
                      'body': 'private-reply-content'}]})


async def apply(db, raw=None, view=None, **changes):
    raw = source() if raw is None else raw
    service = rs.RestoreReplyStops(db)
    view = await service.inspect('w', raw) if view is None else view
    args = dict(operator='operator', evidence_digest=EVIDENCE, source_digest=hashlib.sha256(raw).hexdigest(),
                review_digest=view['digest'], workers_drained=True)
    args.update(changes)
    return await service.apply('w', raw, **args)


async def test_sender_scoped_blocks_reach_runtime_without_history_or_authority(suppression_db):
    db = suppression_db; add_sender(db)
    names = ('outreach_inbox_threads', 'outreach_leads', 'outreach_event_outbox', 'outreach_campaigns',
             'outreach_sender_execution', 'outreach_manual_actions', 'outreach_accounts')
    before = {n: deepcopy(getattr(db, n).docs) for n in names}
    assert (await apply(db))['applied']
    for lead in ({'linkedin_urn': RECIPIENT}, {'linkedin_url': URL.replace('www.', '')}):
        assert await _recipient_has_reply(db, 'w', 'sender', lead)
        assert not await _recipient_has_reply(db, 'other', 'sender', lead)
        assert not await _recipient_has_reply(db, 'w', 'other', lead)
    for n in names: assert getattr(db, n).docs == before[n]
    journal = json.dumps(db.outreach_restore_reply_stops.docs, default=str)
    assert RECIPIENT not in journal and URL not in journal and SENDER not in journal
    with pytest.raises(epoch.EpochUnavailable): await epoch.positive(db, 'w')


async def test_retry_allows_credential_rotation_but_never_ignores_existing_negative(suppression_db):
    db = suppression_db; add_sender(db); view = await rs.RestoreReplyStops(db).inspect('w', source())
    await apply(db, view=view)
    db.outreach_accounts.docs[0]['credential_generation'] = 2
    db.outreach_reply_stops.docs[0]['later_metadata'] = True
    before = deepcopy(db.outreach_reply_stops.docs)
    assert (await apply(db, view=view))['recovered']
    assert db.outreach_reply_stops.docs == before
    db.outreach_accounts.docs[0]['linkedin_urn'] = 'urn:li:member:Replacement'
    with pytest.raises(ValueError): await apply(db, view=view)
    assert await _recipient_has_reply(db, 'w', 'sender', {'linkedin_urn': RECIPIENT})


@pytest.mark.parametrize('fault', ['sender_missing', 'sender_changed', 'sender_deleted', 'sender_duplicate', 'scope',
    'drain', 'review', 'source', 'evidence', 'operator', 'flags', 'epoch', 'closed', 'collision', 'missing_saved',
    'saved_operator', 'saved_evidence', 'saved_review'])
async def test_unproven_source_target_or_review_denies(suppression_db, monkeypatch, fault):
    db = suppression_db; add_sender(db); raw = source(); view = await rs.RestoreReplyStops(db).inspect('w', raw)
    changes = {}
    if fault in {'missing_saved', 'saved_operator', 'saved_evidence', 'saved_review'}: await apply(db, view=view)
    if fault == 'sender_missing': db.outreach_accounts.docs = []
    if fault == 'sender_changed': db.outreach_accounts.docs[0]['linkedin_urn'] = 'urn:li:member:Other'
    if fault == 'sender_deleted': db.outreach_accounts.docs[0]['is_deleted'] = True
    if fault == 'sender_duplicate': db.outreach_accounts.docs.append(deepcopy(db.outreach_accounts.docs[0]))
    if fault == 'scope': raw = source(workspace_guard_digest='f' * 64)
    if fault == 'drain': changes['workers_drained'] = False
    if fault in {'review', 'saved_review'}: changes['review_digest'] = 'f' * 64
    if fault == 'source': changes['source_digest'] = 'f' * 64
    if fault in {'evidence', 'saved_evidence'}: changes['evidence_digest'] = 'f' * 64 if fault.startswith('saved') else 'bad'
    if fault in {'operator', 'saved_operator'}: changes['operator'] = 'other' if fault.startswith('saved') else ''
    if fault == 'flags': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    if fault == 'epoch': db.outreach_execution_epochs.docs = []
    if fault == 'closed': db.outreach_suppression_guards.docs[0]['erasure_state'] = 'erased'
    if fault == 'collision':
        fact = rs.parse(raw).facts[0]
        db.outreach_reply_stops.docs.append({**rs.scope('w', fact), 'field': fact.field, 'value': 'changed',
            'sender_id': 'sender', 'sender_identity_digest': fact.sender_identity_digest,
            'created_at': epoch.now(), 'channel': 'linkedin', 'restore_provenance': 'selected_reply_stop'})
    if fault == 'missing_saved': db.outreach_reply_stops.docs = []
    with pytest.raises(ValueError): await apply(db, raw, view, **changes)


@pytest.mark.parametrize('fault', ['version', 'unknown', 'empty', 'duplicate', 'future', 'date', 'sender', 'digest',
    'field', 'urn', 'url', 'oversize', 'duplicate_key', 'nonfinite', 'utf8', 'mixed_sender'])
async def test_strict_manifest(fault):
    doc = json.loads(source()); raw = None
    if fault == 'version': doc['version'] = True
    if fault == 'unknown': doc['extra'] = True
    if fault == 'empty': doc['facts'] = []
    if fault == 'duplicate': doc['facts'].append(doc['facts'][0])
    if fault == 'future': doc['facts'][0]['blocked_at'] = '2099-01-01T00:00:00.000Z'
    if fault == 'date': doc['facts'][0]['blocked_at'] = '2026-01-01'
    if fault == 'sender': doc['facts'][0]['sender_id'] = '$bad\n'
    if fault == 'digest': doc['facts'][0]['record_digest'] = 'bad'
    if fault == 'field': doc['facts'][0]['field'] = 'email'
    if fault == 'urn': doc['facts'][0]['value'] = 'recipient@example.com'
    if fault == 'url': doc['facts'][1]['value'] = 'https://evil.example/in/person'
    if fault == 'oversize': raw = b'x' * 65537
    if fault == 'duplicate_key': raw = source().replace(b'"version": 1', b'"version": 1, "version": 1')
    if fault == 'nonfinite': raw = b'{"version": NaN}'
    if fault == 'utf8': raw = b'\xff'
    if fault == 'mixed_sender': doc['facts'][0]['sender_identity_digest'] = 'e' * 64
    with pytest.raises(ValueError): rs.parse(json.dumps(doc).encode() if raw is None else raw)


async def test_export_original_stored_timestamp_and_sender_proof_without_content(suppression_db):
    db = suppression_db; add_sender(db); add_thread(db)
    doc = await rs.export_manifest(db, 'w', ['thread'], workers_drained=True)
    parsed = rs.parse(json.dumps(doc).encode())
    assert len(parsed.facts) == 2 and all(f.blocked_at.microsecond == 123000 for f in parsed.facts)
    assert all(f.sender_identity_digest == canonical_hash(['linkedin_sender_v1', 'w', 'sender', SENDER]) for f in parsed.facts)
    assert 'private-reply-content' not in json.dumps(doc) and 'thread' not in json.dumps(doc)


@pytest.mark.parametrize('fault', ['empty', 'missing', 'duplicate', 'capacity', 'imported', 'demo', 'flag_only',
    'timestamp', 'future', 'urn', 'sender', 'closed', 'drain', 'overlap', 'not_reply'])
async def test_export_unproven_originals_deny(suppression_db, fault):
    db = suppression_db; add_sender(db); add_thread(db); refs = ['thread']; drained = True
    row = db.outreach_inbox_threads.docs[0]
    if fault == 'empty': refs = []
    if fault == 'missing': refs = ['missing']
    if fault == 'duplicate': refs *= 2
    if fault == 'capacity': refs = [str(i) for i in range(101)]
    if fault == 'imported': row['restore_provenance'] = 'restored'
    if fault == 'demo': row['is_demo'] = True
    if fault == 'flag_only': row['messages'] = []
    if fault == 'timestamp': row['messages'][0]['timestamp'] = DATE
    if fault == 'future': row['messages'][0]['timestamp'] = datetime(2099, 1, 1)
    if fault == 'urn': row['lead_urn'] = 'email@example.com'
    if fault == 'sender': db.outreach_accounts.docs = []
    if fault == 'closed': db.outreach_suppression_guards.docs[0]['erasure_state'] = 'stopped'
    if fault == 'drain': drained = False
    if fault == 'overlap': db.outreach_inbox_threads.docs.append({**deepcopy(row), '_id': 'other'}); refs += ['other']
    if fault == 'not_reply': row['has_lead_reply'] = False
    with pytest.raises(ValueError): await rs.export_manifest(db, 'w', refs, workers_drained=drained)
