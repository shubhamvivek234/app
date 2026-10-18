"""Original deletion reference contracts independent of database I/O."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_deletions as deletions
from outreach.core import template_governance as governance
from outreach.core import template_graph_updates, template_metadata_updates, template_saves
from tests.test_outreach_template_governance import record

REQUEST = '01234567-89ab-cdef-0123-456789abcdef'


def content(row=None, **changes):
    row = row or record()
    review = governance.scoped_review(row, 'workspace', 'actor', 'original-uid')
    proof = {key: review[key] for key in ('contract_version', 'workspace_id', 'revision',
        'review_digest', 'identity_digest', 'scope_digest')}
    return json.dumps({**proof, 'template_id': row['id'], **changes})


def receipt():
    scope = deletions.control_scope('workspace', 'actor', 'original-uid', REQUEST)
    raw = content(); original = json.loads(raw)
    return {**scope, 'contract_version': 1, 'input_digest': deletions.input_digest(raw),
        'status': 'deleted', **{key: original[key] for key in ('template_id', 'revision', 'review_digest', 'identity_digest')},
        'review_scope_digest': original['scope_digest'], 'created_at': datetime(2026, 10, 18, tzinfo=timezone.utc)}


def test_operation_context_is_distinct_and_never_grants_execution():
    context = deletions.deletion_context('workspace', 'actor', 'original-uid')
    assert context['execution_authorized'] is False
    scopes = [governance.review_scope('workspace', 'actor', 'original-uid'),
        template_saves.save_context('workspace', 'actor', 'original-uid')['scope_digest'],
        template_metadata_updates.update_context('workspace', 'actor', 'original-uid')['scope_digest'],
        template_graph_updates.update_context('workspace', 'actor', 'original-uid')['scope_digest']]
    assert context['scope_digest'] not in scopes
    assert deletions.control_scope('workspace', 'actor', 'other-uid', REQUEST)['_id'] != receipt()['_id']


def test_exact_input_hashes_utf8_whitespace_without_normalizing_original_review():
    raw = content(); assert deletions.input_digest(raw) == hashlib.sha256(raw.encode()).hexdigest()
    assert deletions.input_digest(raw) != deletions.input_digest(raw+' ')
    operation = deletions.prepare_deletion(raw, 'workspace', 'actor', 'original-uid')
    assert operation == {key:value for key,value in json.loads(raw).items() if key not in {'contract_version', 'workspace_id'}}


@pytest.mark.parametrize('original_request', ['bad', REQUEST.upper(), Code(REQUEST), None])
def test_only_original_plain_canonical_uuid_can_locate_a_receipt(original_request):
    with pytest.raises(HTTPException): deletions.control_scope('workspace', 'actor', 'original-uid', original_request)


@pytest.mark.parametrize('change', [
    {'revision': True}, {'revision': 1.0}, {'revision': 2**53}, {'contract_version': True},
    {'name': 'not retained'}, {'description': ''}, {'nodes': []}, {'template_id': 'tpl_prebuilt'},
    {'review_digest': 'bad'}, {'identity_digest': ['a'*64]}, {'scope_digest': 'a'*64}, {'workspace_id': 'other'},
])
def test_new_request_rejects_coercion_extra_fields_and_wrong_proof(change):
    with pytest.raises(HTTPException): deletions.prepare_deletion(content(**change), 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['{}', '[]', '{"revision":1,"revision":2}', '{"x":{"a":1,"a":2}}'])
def test_new_request_rejects_missing_and_recursive_duplicate_json(raw):
    with pytest.raises(HTTPException): deletions.prepare_deletion(raw, 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['', Code('{}'), '\ud800', 'a'*8193, '☕'*2731])
def test_input_is_plain_bounded_utf8(raw):
    with pytest.raises(HTTPException): deletions.input_digest(raw)


def test_receipt_is_reference_only_and_allows_final_js_safe_native_revision():
    row = receipt(); before = deepcopy(row)
    public = deletions.public_receipt(row, deletions.control_scope('workspace', 'actor', 'original-uid', REQUEST), governance.review_scope('workspace', 'actor', 'original-uid'))
    assert not {'name', 'description', 'nodes', 'actor_id', 'created_at'} & set(public)
    assert row == before
    row['revision'] = Int64(2**53-1)
    assert deletions.public_receipt(row, deletions.control_scope('workspace', 'actor', 'original-uid', REQUEST), governance.review_scope('workspace', 'actor', 'original-uid'))['revision'] == 2**53-1


@pytest.mark.parametrize('change', [
    {'revision': True}, {'revision': 2**53}, {'status': Code('deleted')}, {'input_digest': ['a'*64]},
    {'created_at': 'today'}, {'created_at': datetime(2026, 1, 1, microsecond=1)},
    {'name': 'private text'}, {'review_scope_digest': None}, {'review_scope_digest': 'a'*64},
    {'template_id': Code('tpl_custom_012345abcd')}, {'new_revision': 1},
])
def test_malformed_receipts_are_unconfirmed(change):
    with pytest.raises(HTTPException) as caught:
        deletions.public_receipt({**receipt(), **change}, deletions.control_scope('workspace', 'actor', 'original-uid', REQUEST), governance.review_scope('workspace', 'actor', 'original-uid'))
    assert caught.value.status_code == 503
