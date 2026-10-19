"""Minimal revision checkpoints bind native records without retaining content."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta

from bson import Code, Int64, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core.template_revision_checkpoints import checkpoint_for, validate_checkpoint, append_metadata_checkpoints
from outreach.core.template_governance import template_review

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def record(revision=0):
    return {'_id': ObjectId(), 'workspace_id': 'workspace', 'user_id': 'creator',
        'id': 'tpl_custom_012345abcd', 'is_custom': True, 'template_revision': revision,
        'name': 'Private name', 'description': 'Private description', 'nodes': [], 'edges': [],
        'future_private_field': {'credential': 'never copy this'}}


def check(value):
    return validate_checkpoint(value, 'workspace', value['template_id'], value['identity_digest'], int(value['revision']))


def test_observed_baseline_has_exact_schema_and_no_material_or_uid():
    row = record(); before = deepcopy(row)
    value = checkpoint_for(row, 'actor', NOW)
    assert check(value) == value
    assert value['event'] == 'observed' and value['predecessor_revision'] is None
    assert value['predecessor_review_digest'] is None and value['revision'] == 0
    assert len(value) == 12 and value['review_digest'] == template_review(row, 'workspace')['review_digest']
    assert not {'name', 'description', 'nodes', 'edges', 'tree', 'firebase_uid', 'content_json', 'future_private_field'} & set(value)
    assert 'never copy this' not in repr(value) and row == before


def test_metadata_checkpoint_links_exact_original_revision_and_record_hash():
    before = record(7);after = {**before, 'template_revision': 8, 'name': 'Changed'}
    value = checkpoint_for(after, 'actor', NOW, predecessor=before)
    assert value['event'] == 'metadata' and value['predecessor_revision'] == 7
    assert value['predecessor_review_digest'] == template_review(before, 'workspace')['review_digest']
    assert check(value) == value
    assert checkpoint_for({**after, 'template_revision': Int64(8)}, 'actor', NOW, predecessor=before)['revision'] == 8


@pytest.mark.parametrize('change', [{'revision': True}, {'revision': 1.5}, {'revision': -1},
    {'revision': 2**53}, {'event': 'created'}, {'event': Code('observed')}, {'recorded_by': Code('actor')},
    {'recorded_by': ' '}, {'recorded_at': NOW + timedelta(microseconds=1)}, {'recorded_at': 'today'},
    {'recorded_at': NOW.astimezone(timezone(timedelta(hours=1)))}, {'review_digest': Code('a'*64)},
    {'review_digest': 'bad'}, {'predecessor_revision': 0}, {'predecessor_review_digest': 'a'*64},
    {'_id': 'wrong'}, {'unexpected': 'data'}])
def test_malformed_or_changed_checkpoint_is_not_silently_repaired(change):
    value = {**checkpoint_for(record(), 'actor', NOW), **change}
    with pytest.raises(HTTPException): validate_checkpoint(value, 'workspace', 'tpl_custom_012345abcd', value['identity_digest'], 0)


@pytest.mark.parametrize('change', ['native', 'workspace', 'revision', 'template_id'])
def test_predecessor_must_be_same_native_template_and_immediately_previous_revision(change):
    before = record();after = {**before, 'template_revision': 1}
    if change == 'native': after['_id'] = ObjectId()
    elif change == 'workspace': after['workspace_id'] = 'other'
    elif change == 'revision': after['template_revision'] = 3
    else: after['id'] = 'tpl_custom_fffffffffe'
    with pytest.raises(HTTPException): checkpoint_for(after, 'actor', NOW, predecessor=before)


def test_identity_distinguishes_replacement_even_with_same_public_id_revision_and_text():
    row = record()
    first = checkpoint_for(row, 'actor', NOW)
    replacement = checkpoint_for({**row, '_id': ObjectId()}, 'actor', NOW)
    assert replacement['_id'] != first['_id'] and replacement['identity_digest'] != first['identity_digest']


@pytest.mark.parametrize('revision', [True, 1.0])
def test_expected_context_revision_cannot_be_coerced(revision):
    value = checkpoint_for(record(1), 'actor', NOW)
    with pytest.raises(HTTPException):
        validate_checkpoint(value, 'workspace', value['template_id'], value['identity_digest'], revision)


@pytest.mark.asyncio
async def test_append_requires_an_active_transaction_before_any_database_access():
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from outreach.core.suppression import SuppressionDatabase
    database = MagicMock();current = SuppressionDatabase(database, 'workspace', SimpleNamespace(in_transaction=False))
    before = record();after = {**before, 'template_revision': 1}
    with pytest.raises(HTTPException): await append_metadata_checkpoints(current, before, after, 'actor', NOW)
    assert database.mock_calls == []
