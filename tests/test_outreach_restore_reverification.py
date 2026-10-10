"""Adversarial regressions for the offline restore helper trust boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from outreach.core import restore_reply_evidence as replies
from outreach.core.authorization import canonical_hash
from outreach.core.restore_activation import plan_reactivation, rehearse_transaction
from outreach.core.restore_reconciliation import ReconciliationError, verify_manifest, verify_signed_manifest
from tests.test_outreach_restore_reconciliation import manifest

pytestmark = pytest.mark.restore_epoch


def signed_manifest(value):
    key = Ed25519PrivateKey.generate()
    digest = canonical_hash(value)
    result = deepcopy(value)
    result['attestation'] = {'algorithm': 'ed25519', 'payload_digest': digest,
        'signature': base64.b64encode(key.sign(digest.encode())).decode()}
    return result, base64.b64encode(key.public_key().public_bytes_raw()).decode()


@pytest.mark.parametrize('signed', [False, True])
def test_independent_local_changes_cannot_hide_in_self_consistent_manifest(signed):
    value, _ = manifest()
    local = deepcopy(value['local_metadata'])
    local['reply_evidence'].append({'record_id': 'missing-from-backup', 'state': 'reply'})
    if signed:
        value, key = signed_manifest(value)
        result = verify_signed_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
            trusted_public_key=key, local_metadata=local)
    else:
        result = verify_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
            trusted_digest=canonical_hash(value), local_metadata=local)
    assert result['group_matches']['reply_evidence'] is False
    assert not result['completeness_verified'] and not result['selected_metadata_matches']


@pytest.mark.parametrize('fault', ['version_bool', 'extra_root', 'missing_source_group',
    'extra_summary', 'private_record', 'duplicate_record', 'oversized'])
def test_invalid_schema_bounds_and_source_coverage_deny(fault):
    value, _ = manifest()
    local = deepcopy(value['local_metadata'])
    if fault == 'version_bool': value['version'] = True
    if fault == 'extra_root': value['password'] = 'private'
    if fault == 'missing_source_group': value['sources'].pop()
    if fault == 'extra_summary': value['summaries']['unknown'] = {}
    if fault == 'private_record': value['local_metadata']['financial'][0]['password'] = 'private'
    if fault == 'duplicate_record': value['local_metadata']['financial'] *= 2
    if fault == 'oversized': value['local_metadata']['financial'][0]['state'] = 'x'*65537
    with pytest.raises(ReconciliationError):
        verify_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
            trusted_digest=canonical_hash(value), local_metadata=local)


@pytest.mark.parametrize('field', ['workers_drained', 'flags_off', 'operator_confirmed'])
@pytest.mark.parametrize('invalid', ['false', 1, None])
def test_planner_never_accepts_truthiness_as_control_proof(field, invalid):
    args = plan_args()
    assert plan_reactivation(**args)['input_checks_passed']
    args[field] = invalid
    assert plan_reactivation(**args)['input_checks_passed'] is False


def test_arbitrary_caller_status_dictionary_is_not_a_database_rehearsal():
    result = rehearse_transaction(plan={'reactivation_ready': True, 'new_epoch': 'b'*64,
        'review_digest': 'c'*64}, stopped_root={'workspace_id': 'workspace',
        'status': 'prepared_stopped', 'execution_epoch': 'a'*64}, authorities=[{
        'workspace_id': 'workspace', 'status': 'stopped', 'credential_generation': 'g'}])
    assert not result['input_checks_passed']
    assert not result['rehearsal_passed'] and not result['transaction_exercised']


@pytest.mark.parametrize('fault', ['future', 'offset', 'duplicate_event', 'older'])
def test_reply_future_or_ambiguous_events_deny(monkeypatch, fault):
    monkeypatch.setattr(replies, 'now', lambda: datetime(2026, 10, 10, 12, tzinfo=timezone.utc), raising=False)
    first = {'record_id': '1', 'workspace_id': 'workspace', 'sender_digest': '1'*64,
        'recipient_digest': '2'*64, 'event_digest': '3'*64, 'observed_at': '2026-10-10T10:00:00Z'}
    second = {**first, 'record_id': '2', 'event_digest': '4'*64, 'observed_at': '2026-10-10T11:00:00Z'}
    if fault == 'future': second['observed_at'] = '2026-10-10T13:00:00Z'
    if fault == 'offset': second['observed_at'] = '2026-10-10T11:00:00+01:00'
    if fault == 'duplicate_event': second['event_digest'] = first['event_digest']
    if fault == 'older': second['observed_at'] = '2026-10-10T09:00:00Z'
    with pytest.raises(ReconciliationError): replies.validate([first, second], workspace_id='workspace')


@pytest.mark.parametrize('fault', ['wrong_key', 'tampered_payload', 'bad_signature', 'missing',
    'algorithm', 'encoding', 'signature_length', 'extra_attestation', 'payload_digest'])
def test_signature_verification_fails_for_wrong_keys_and_tampering(fault):
    value, _ = manifest()
    signed, key = signed_manifest(value)
    if fault == 'wrong_key': _, key = signed_manifest(value)
    if fault == 'tampered_payload': signed['workspace_id'] = 'other'
    if fault == 'bad_signature': signed['attestation']['signature'] = base64.b64encode(b'0'*64).decode()
    if fault == 'missing': signed.pop('attestation')
    if fault == 'algorithm': signed['attestation']['algorithm'] = 'none'
    if fault == 'encoding': key = '-'*44
    if fault == 'signature_length': signed['attestation']['signature'] = base64.b64encode(b'0'*32).decode()
    if fault == 'extra_attestation': signed['attestation']['public_key'] = key
    if fault == 'payload_digest': signed['attestation']['payload_digest'] = 'b'*64
    with pytest.raises(ReconciliationError):
        verify_signed_manifest(signed, workspace_id='workspace', execution_epoch='a'*64,
            trusted_public_key=key, local_metadata=value['local_metadata'])


@pytest.mark.parametrize('fault', ['source_shape', 'source_duplicate', 'source_digest', 'source_capacity',
    'summary_shape', 'summary_count', 'summary_bool', 'metadata_shape', 'record_shape',
    'state_shape', 'state_length', 'row_capacity', 'json_object', 'json_nan', 'json_depth'])
def test_remaining_manifest_shapes_and_bounds_are_enforced(fault):
    value, _ = manifest()
    local = deepcopy(value['local_metadata'])
    if fault == 'source_shape': value['sources'][0] = {}
    if fault == 'source_duplicate': value['sources'].append(deepcopy(value['sources'][0]))
    if fault == 'source_digest': value['sources'][0]['evidence_digest'] = 'bad'
    if fault == 'source_capacity': value['sources'] *= 5
    if fault == 'summary_shape': value['summaries']['financial'] = []
    if fault == 'summary_count': value['summaries']['financial']['record_count'] = -1
    if fault == 'summary_bool': value['summaries']['financial']['record_count'] = True
    if fault == 'metadata_shape': local = {}
    if fault == 'record_shape': local['financial'][0] = {}
    if fault == 'state_shape': local['financial'][0]['state'] = []
    if fault == 'state_length': local['financial'][0]['state'] = 'x'*65
    if fault == 'row_capacity': local['financial'] *= 101
    if fault == 'json_object': local['financial'][0]['state'] = object()
    if fault == 'json_nan': local['financial'][0]['state'] = float('nan')
    if fault == 'json_depth':
        local['financial'][0]['state'] = local
    with pytest.raises(ReconciliationError):
        verify_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
            trusted_digest=canonical_hash(value), local_metadata=local)


def test_record_order_is_canonical_and_empty_matches_do_not_prove_completeness():
    value, _ = manifest()
    local = deepcopy(value['local_metadata'])
    local['financial'] = [{'record_id': 'z', 'state': 'review'}, {'record_id': 'a', 'state': 'review'}]
    value['local_metadata']['financial'] = list(reversed(local['financial']))
    value['summaries']['financial'] = {'record_count': 2,
        'metadata_digest': canonical_hash(value['local_metadata']['financial'])}
    result = verify_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
        trusted_digest=canonical_hash(value), local_metadata=local)
    assert result['selected_metadata_matches'] and not result['completeness_verified']
    for group in local:
        value['local_metadata'][group] = local[group] = []
        value['summaries'][group] = {'record_count': 0, 'metadata_digest': canonical_hash([])}
    result = verify_manifest(value, workspace_id='workspace', execution_epoch='a'*64,
        trusted_digest=canonical_hash(value), local_metadata=local)
    assert result['selected_metadata_matches'] and not result['completeness_verified']


def plan_args():
    value, _ = manifest()
    signed, key = signed_manifest(value)
    result = verify_signed_manifest(signed, workspace_id='workspace', execution_epoch='a'*64,
        trusted_public_key=key, local_metadata=value['local_metadata'])
    assert result['artifact_signer_verified'] and not result['source_provenance_verified']
    return dict(reconciliation=result, current_epoch='a'*64, new_epoch='b'*64,
        review_digest=canonical_hash(result), workers_drained=True, flags_off=True, operator_confirmed=True)


@pytest.mark.parametrize('fault', ['malformed', 'current_epoch', 'new_epoch', 'review',
    'foreign_epoch', 'workspace', 'groups', 'reviews', 'positive_claim'])
def test_plan_scope_and_review_cannot_drift(fault):
    args = plan_args()
    if fault == 'malformed': args['reconciliation'] = []
    if fault == 'current_epoch': args['current_epoch'] = None
    if fault == 'new_epoch': args['new_epoch'] = []
    if fault == 'review': args['review_digest'] = 'c'*64
    if fault == 'foreign_epoch': args['reconciliation']['execution_epoch'] = 'c'*64
    if fault == 'workspace': args['reconciliation'].pop('workspace_id')
    if fault == 'groups': args['reconciliation']['group_matches']['financial'] = 1
    if fault == 'reviews': args['reconciliation']['external_review_required'] = 'none'
    if fault == 'positive_claim': args['reconciliation']['completeness_verified'] = True
    result = plan_reactivation(**args)
    assert not result['input_checks_passed'] and not result['reactivation_ready']


@pytest.mark.parametrize('fault', ['changed_plan', 'foreign_root', 'root_epoch', 'empty', 'duplicate',
    'generation', 'unbounded', 'malformed', 'authority_not_object'])
def test_offline_authority_inputs_cannot_be_mislabelled_as_rehearsed(fault):
    args = plan_args()
    plan = plan_reactivation(**args)
    root = {'workspace_id': 'workspace', 'status': 'prepared_stopped', 'execution_epoch': 'a'*64}
    rows = [{'record_id': 'sender', 'workspace_id': 'workspace', 'status': 'stopped',
        'review_digest': args['review_digest'], 'credential_generation': 'g'}]
    if fault == 'changed_plan': plan['new_epoch'] = 'c'*64
    if fault == 'foreign_root': root['workspace_id'] = 'other'
    if fault == 'root_epoch': root['execution_epoch'] = 'c'*64
    if fault == 'empty': rows = []
    if fault == 'duplicate': rows *= 2
    if fault == 'generation': rows[0]['credential_generation'] = []
    if fault == 'unbounded': rows *= 101
    if fault == 'malformed': rows = {}
    if fault == 'authority_not_object': rows = [None]
    result = rehearse_transaction(plan=plan, stopped_root=root, authorities=rows)
    assert not result['input_checks_passed'] and not result['rehearsal_passed']
    assert not result['transaction_exercised'] and not result['activation_allowed']


@pytest.mark.parametrize('fault', ['reuse_epoch', 'controls', 'review_digest', 'reconciliation_digest',
    'different_review', 'blockers', 'missing_blocker'])
def test_rehashed_plan_cannot_bypass_elementary_input_rules(fault):
    args = plan_args()
    plan = plan_reactivation(**args)
    if fault == 'reuse_epoch': plan['new_epoch'] = plan['current_epoch']
    if fault == 'controls': plan['control_assertions'] = dict.fromkeys(plan['control_assertions'], False)
    if fault == 'review_digest': plan['review_digest'] = 'not-a-digest'
    if fault == 'reconciliation_digest': plan['reconciliation_digest'] = 'bad'
    if fault == 'different_review': plan['review_digest'] = 'c'*64
    if fault == 'blockers': plan['blockers'] = 'none'
    if fault == 'missing_blocker': plan['blockers'] = []
    plan['plan_digest'] = canonical_hash({key: value for key, value in plan.items() if key != 'plan_digest'})
    result = rehearse_transaction(plan=plan, stopped_root={'workspace_id': 'workspace',
        'status': 'prepared_stopped', 'execution_epoch': 'a'*64}, authorities=[{
        'record_id': 'sender', 'workspace_id': 'workspace', 'status': 'stopped',
        'review_digest': plan['review_digest'], 'credential_generation': 'g'}])
    assert not result['input_checks_passed'] and not result['activation_allowed']


@pytest.mark.parametrize('fault', ['empty', 'shape', 'naive', 'bad_calendar', 'duplicate_id', 'bound'])
def test_reply_metadata_shapes_and_identities_are_checked(monkeypatch, fault):
    monkeypatch.setattr(replies, 'now', lambda: datetime(2026, 10, 10, 12, tzinfo=timezone.utc))
    row = {'record_id': '1', 'workspace_id': 'workspace', 'sender_digest': '1'*64,
        'recipient_digest': '2'*64, 'event_digest': '3'*64, 'observed_at': '2026-10-10T10:00:00Z'}
    rows = [row]
    if fault == 'empty': rows = []
    if fault == 'shape': rows = [None]
    if fault == 'naive': row['observed_at'] = '2026-10-10T10:00:00'
    if fault == 'bad_calendar': row['observed_at'] = '2026-99-10T10:00:00Z'
    if fault == 'duplicate_id': rows.append({**row, 'event_digest': '4'*64})
    if fault == 'bound': rows *= 101
    with pytest.raises(ReconciliationError): replies.validate(rows, workspace_id='workspace')


def test_reply_metadata_is_not_provider_or_sender_mapping_proof(monkeypatch):
    monkeypatch.setattr(replies, 'now', lambda: datetime(2026, 10, 10, 12, tzinfo=timezone.utc))
    row = {'record_id': '1', 'workspace_id': 'workspace', 'sender_digest': '1'*64,
        'recipient_digest': '2'*64, 'event_digest': '3'*64, 'observed_at': '2026-10-10T10:00:00Z'}
    before = deepcopy(row)
    result = replies.validate([row], workspace_id='workspace')
    assert row == before and result['reply_metadata_valid']
    for field in ('reply_evidence_verified', 'reply_evidence_authenticated', 'sender_mapping_verified',
                  'reply_history_restored', 'activation_allowed'):
        assert result[field] is False
