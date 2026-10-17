"""Metadata reviews bind full native originals without granting graph editing."""
from copy import deepcopy

from bson import Code
from fastapi import HTTPException
import pytest

from outreach.core import template_metadata as metadata
from tests.test_outreach_template_governance import record


def test_review_is_read_only_and_distinct_from_deletion():
    from outreach.core.template_governance import scoped_review
    row = record(); before = deepcopy(row)
    result = metadata.metadata_review(row, 'workspace', 'actor', 'original-uid')
    assert result['reviewable'] is True and result['revision'] == 0
    assert result['update_authorized'] is False and result['execution_authorized'] is False
    assert result['scope_digest'] != scoped_review(row, 'workspace', 'actor', 'original-uid')['scope_digest']
    assert row == before


@pytest.mark.parametrize('change', [
    {'name': ''}, {'name': '   '}, {'name': 1}, {'name': Code('name')},
    {'name': 'x'*101}, {'description': None}, {'description': []},
    {'description': Code('description')}, {'description': 'x'*1001},
    {'template_revision': 2**53-1}, {'workspace_id': ['workspace']},
    {'id': 'tpl_prebuilt'}, {'_id': None},
])
def test_unsupported_metadata_stays_unavailable(change):
    result = metadata.metadata_review({**record(), **change}, 'workspace', 'actor', 'original-uid')
    assert result['reviewable'] is False and result['update_authorized'] is False


@pytest.mark.parametrize('name,description', [
    ('', ''), (' '*2, ''), ('x'*101, ''), ('Name', 'x'*1001),
    (True, ''), (Code('Name'), ''), ('Name', None), ('Name', Code('text')),
    ('Name\x00', ''), ('Name', 'text\x00'), ('\ud800', ''), ('Name', '\ud800'),
])
def test_new_metadata_requires_exact_bounded_unicode_strings(name, description):
    with pytest.raises(HTTPException) as caught:
        metadata.validate_metadata(name, description)
    assert caught.value.status_code == 422


def test_exact_metadata_is_preserved_without_normalization_or_name_uniqueness():
    assert metadata.validate_metadata('  Outreach ☕  ', '') == ('  Outreach ☕  ', '')


def test_review_rejects_invalid_actor_context_without_throwing():
    result = metadata.metadata_review(record(), 'workspace', 'actor', None)
    assert result['reviewable'] is False and result['scope_digest'] is None
