"""Strict reference-only metadata update contracts, independent of database I/O."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_metadata_updates as updates
from outreach.core import template_metadata as metadata
from tests.test_outreach_template_governance import record

REQUEST = '01234567-89ab-cdef-0123-456789abcdef'


def content(row=None, **changes):
    row = row or record()
    review = metadata.metadata_review(row, 'workspace', 'actor', 'original-uid')
    proof = {key: review[key] for key in ('contract_version', 'workspace_id', 'revision',
        'review_digest', 'identity_digest', 'scope_digest')}
    return json.dumps({**proof, 'template_id': row['id'], 'name': 'Renamed ☕', 'description': '', **changes})


def receipt():
    scope = updates.control_scope('workspace', 'actor', 'original-uid', REQUEST)
    raw = content(); original = json.loads(raw)
    return {**scope, 'contract_version': 1, 'input_digest': updates.input_digest(raw),
        'status': 'updated', 'template_id': original['template_id'], 'revision': 0,
        'review_digest': original['review_digest'], 'identity_digest': original['identity_digest'],
        'review_scope_digest': original['scope_digest'], 'new_revision': 1,
        'new_review_digest': 'd'*64, 'created_at': datetime(2026, 10, 17, tzinfo=timezone.utc)}


def test_distinct_context_and_reference_do_not_grant_execution():
    context = updates.update_context('workspace', 'actor', 'original-uid')
    assert context['execution_authorized'] is False
    assert context['scope_digest'] != metadata.metadata_scope('workspace', 'actor', 'original-uid')
    assert updates.control_scope('workspace', 'actor', 'other-uid', REQUEST)['_id'] != receipt()['_id']


def test_exact_utf8_json_digest_preserves_whitespace_and_text():
    raw = content()
    assert updates.input_digest(raw) != updates.input_digest(raw+' ')
    prepared = updates.prepare_update(raw, 'workspace', 'actor', 'original-uid')
    assert prepared['name'] == 'Renamed ☕' and prepared['description'] == ''


@pytest.mark.parametrize('change', [
    {'revision': True}, {'revision': 1.0}, {'revision': 2**53-1}, {'contract_version': True},
    {'name': ''}, {'name': 1}, {'description': None}, {'nodes': []},
    {'template_id': 'tpl_prebuilt'}, {'review_digest': 'bad'}, {'scope_digest': 'a'*64},
    {'workspace_id': 'other'}, {'description': '\ud800'},
])
def test_new_request_rejects_unreviewed_or_coerced_content(change):
    with pytest.raises(HTTPException):
        updates.prepare_update(content(**change), 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['{}', '[]', '{"name":1,"name":2}', '{"x":{"a":1,"a":2}}'])
def test_new_request_rejects_missing_and_recursive_duplicate_json(raw):
    with pytest.raises(HTTPException): updates.prepare_update(raw, 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['', Code('{}'), '\ud800', 'a'*8193])
def test_exact_input_requires_plain_bounded_utf8(raw):
    with pytest.raises(HTTPException): updates.input_digest(raw)


def test_receipt_is_reference_only_and_read_only():
    row = receipt(); before = deepcopy(row)
    public = updates.public_receipt(row, updates.control_scope('workspace', 'actor', 'original-uid', REQUEST), metadata.metadata_scope('workspace', 'actor', 'original-uid'))
    assert 'name' not in public and 'description' not in public and 'actor_id' not in public
    assert row == before
    row['revision'] = Int64(2**53-2); row['new_revision'] = Int64(2**53-1)
    assert updates.public_receipt(row, updates.control_scope('workspace', 'actor', 'original-uid', REQUEST), metadata.metadata_scope('workspace', 'actor', 'original-uid'))['new_revision'] == 2**53-1


@pytest.mark.parametrize('change', [
    {'revision': True}, {'new_revision': 3}, {'new_revision': 2**53}, {'status': Code('updated')},
    {'input_digest': ['a'*64]}, {'created_at': 'today'}, {'created_at': datetime(2026, 1, 1, microsecond=1)},
    {'name': 'private text'}, {'review_scope_digest': None}, {'review_scope_digest': 'a'*64}, {'template_id': Code('tpl_custom_012345abcd')},
])
def test_malformed_receipts_are_never_outcome_authority(change):
    with pytest.raises(HTTPException) as caught:
        updates.public_receipt({**receipt(), **change}, updates.control_scope('workspace', 'actor', 'original-uid', REQUEST), metadata.metadata_scope('workspace', 'actor', 'original-uid'))
    assert caught.value.status_code == 503
