"""Audience contract validation, identities and strict request shapes."""
import uuid

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from outreach.api.lead_lists import CreateList, ListRevision, AdoptExisting
from outreach.core.lead_lists import clean_name, identifier, list_identifier, request_identity, physical_digest


@pytest.mark.parametrize("value", [None, [], {}, True, "", "a" * 201, "two words", "line\nfeed", "é"])
def test_scalar_resource_identity_is_required(value):
    with pytest.raises(HTTPException): identifier(value)


def test_creation_identity_is_stable_scoped_and_request_bound():
    request = str(uuid.uuid4())
    first = request_identity("w", "campaign", request)
    assert list_identifier(first) == first
    assert first == request_identity("w", "campaign", request.upper())
    assert first != request_identity("other", "campaign", request)
    assert first != request_identity("w", "other", request)
    assert first != request_identity("w", "campaign", str(uuid.uuid4()))


def test_native_identity_digest_preserves_bson_type():
    value = ObjectId()
    assert physical_digest(value) != physical_digest(str(value))


@pytest.mark.parametrize("revision", [True, False, "1", 0, -1])
def test_edit_revision_cannot_coerce_unproven_values(revision):
    with pytest.raises(ValidationError): ListRevision(revision=revision, review_digest="a"*64)


def test_creation_does_not_accept_a_source_or_execution_override():
    with pytest.raises(ValidationError):
        CreateList(campaign_id="campaign", name="List", request_id=str(uuid.uuid4()), source_kind="sales_nav")
    with pytest.raises(ValidationError):
        AdoptExisting(campaign_id="campaign", revision=0, writers_drained="true")


@pytest.mark.parametrize('name',['','x'*61,'Bad\x00name'])
def test_list_name_errors_match_the_audience_contract(name):
    with pytest.raises(HTTPException) as failure: clean_name(name)
    assert 'Audience list name' in failure.value.detail


def test_list_name_normalization_and_maximum_are_consistent():
    assert clean_name('  Sales   Team ') == ('Sales Team','sales team')
    assert clean_name('x'*60)[0] == 'x'*60
    with pytest.raises(ValidationError):
        CreateList(campaign_id='campaign',name='x'*61,request_id=str(uuid.uuid4()))
