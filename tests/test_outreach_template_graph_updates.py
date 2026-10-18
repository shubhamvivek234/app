"""Strict frozen whole-operation graph updates and historical receipt contracts."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_graph_updates as updates
from outreach.core import template_graphs as graphs
from tests.test_outreach_template_graphs import original, NODE

REQUEST = '01234567-89ab-cdef-0123-456789abcdef'
NEW_NODE = {**NODE, 'delay_hours': 24, 'title': 'Updated visit ☕'}


def content(row=None, **changes):
    row = row or original()
    review = graphs.graph_review(row, 'workspace', 'actor', 'original-uid')
    proof = {key: review[key] for key in ('contract_version', 'workspace_id', 'revision',
        'review_digest', 'identity_digest', 'scope_digest')}
    return json.dumps({**proof, 'template_id': row['id'], 'nodes': [NEW_NODE], 'edges': [], 'tree': [NEW_NODE], **changes})


def receipt():
    scope = updates.control_scope('workspace', 'actor', 'original-uid', REQUEST)
    raw = content(); source = json.loads(raw)
    return {**scope, 'contract_version': 1, 'input_digest': updates.input_digest(raw),
        'status': 'updated', 'template_id': source['template_id'], 'revision': 0,
        'review_digest': source['review_digest'], 'identity_digest': source['identity_digest'],
        'review_scope_digest': source['scope_digest'], 'new_revision': 1, 'graph_digest': 'e'*64,
        'new_review_digest': 'd'*64, 'created_at': datetime(2026, 10, 18, tzinfo=timezone.utc)}


def public(row):
    return updates.public_receipt(row, updates.control_scope('workspace', 'actor', 'original-uid', REQUEST),
        graphs.graph_scope('workspace', 'actor', 'original-uid'))


def test_distinct_original_operation_scope_and_no_execution_grant():
    from outreach.core.template_metadata_updates import update_context
    context = updates.update_context('workspace', 'actor', 'original-uid')
    assert context['execution_authorized'] is False
    assert context['scope_digest'] != graphs.graph_scope('workspace', 'actor', 'original-uid')
    assert context['scope_digest'] != update_context('workspace', 'actor', 'original-uid')['scope_digest']


def test_whole_input_graph_only_and_compiled_digests_have_separate_meanings():
    raw = content()
    operation, prepared = updates.prepare_update(raw, 'workspace', 'actor', 'original-uid')
    graph_only = json.dumps({k: json.loads(raw)[k] for k in ('nodes', 'edges', 'tree')})
    assert operation['template_id'] == original()['id']
    assert prepared['input_digest'] == updates.input_digest(raw) != graphs.prepare_graph(graph_only)['input_digest']
    assert prepared['graph_digest'] == graphs.prepare_graph(graph_only)['graph_digest']
    _, reformatted = updates.prepare_update(raw+' ', 'workspace', 'actor', 'original-uid')
    assert reformatted['input_digest'] != prepared['input_digest']
    assert reformatted['graph_digest'] == prepared['graph_digest']


@pytest.mark.parametrize('change', [
    {'revision': True}, {'revision': 1.0}, {'revision': 2**53-1}, {'contract_version': True},
    {'nodes': []}, {'tree': []}, {'tree': None}, {'tree': [{**NEW_NODE, 'delay_hours': 48}]},
    {'template_id': 'tpl_prebuilt'}, {'review_digest': 'bad'}, {'scope_digest': 'a'*64},
    {'workspace_id': 'other'}, {'name': 'not graph input'}, {'compiled_dag': {}},
    {'nodes': [{**NEW_NODE, 'delay_hours': True}]}, {'tree': [{**NEW_NODE, 'config': []}]},
])
def test_new_request_rejects_unreviewed_or_unfaithful_graph(change):
    with pytest.raises(HTTPException):
        updates.prepare_update(content(**change), 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['{}', '[]', '{"nodes":1,"nodes":2}', '{"x":{"a":1,"a":2}}'])
def test_missing_or_recursive_duplicate_json_denies(raw):
    with pytest.raises(HTTPException): updates.prepare_update(raw, 'workspace', 'actor', 'original-uid')


@pytest.mark.parametrize('raw', ['', Code('{}'), '\ud800', 'a'*1_048_577, '☕'*349526],
    ids=['empty', 'bson-code', 'surrogate', 'ascii-overflow', 'utf8-overflow'])
def test_whole_input_requires_plain_bounded_utf8(raw):
    with pytest.raises(HTTPException): updates.input_digest(raw)


def test_receipt_is_reference_only_and_handles_final_int64_revision():
    row = receipt(); before = deepcopy(row)
    assert not {'name', 'description', 'nodes', 'edges', 'tree', 'content_json', 'actor_id'} & set(public(row))
    assert row == before
    row['revision'] = Int64(2**53-2); row['new_revision'] = Int64(2**53-1)
    assert public(row)['new_revision'] == 2**53-1


@pytest.mark.parametrize('change', [
    {'revision': True}, {'new_revision': 3}, {'new_revision': 2**53}, {'status': Code('updated')},
    {'input_digest': ['a'*64]}, {'created_at': 'today'}, {'created_at': datetime(2026, 1, 1, microsecond=1)},
    {'nodes': []}, {'review_scope_digest': None}, {'review_scope_digest': 'a'*64},
    {'template_id': Code('tpl_custom_012345abcd')}, {'graph_digest': Code('e'*64)}, {'graph_digest': []},
])
def test_malformed_receipts_never_confirm_an_outcome(change):
    with pytest.raises(HTTPException) as caught: public({**receipt(), **change})
    assert caught.value.status_code == 503
