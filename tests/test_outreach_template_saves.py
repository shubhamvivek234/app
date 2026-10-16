"""Stable save references and strict historical creation receipts."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from bson import Code

from fastapi import HTTPException
import pytest

from outreach.core.template_saves import input_digest, save_context, control_scope, public_receipt

REQUEST = '01234567-89ab-4cde-8fab-0123456789ab'


def control():
    return {**control_scope('workspace', 'actor', 'uid', REQUEST),
        'contract_version': 1, 'input_digest': 'a'*64, 'status': 'saved',
        'template_id': 'tpl_custom_012345abcd', 'template_revision': 1,
        'template_identity_digest': 'b'*64, 'template_review_digest': 'c'*64,
        'created_at': datetime(2026,10,16,tzinfo=timezone.utc)}


def test_input_digest_binds_exact_utf8_serialization():
    assert input_digest('{"name":"é"}') == hashlib.sha256('{"name":"é"}'.encode()).hexdigest()
    assert input_digest('{"a":1}') != input_digest('{"a":1.0}')


@pytest.mark.parametrize('value', [None, {}, '', 'é' * 524289], ids=['missing','object','empty','utf8-overflow'])
def test_invalid_or_oversized_input_is_rejected(value):
    with pytest.raises(HTTPException): input_digest(value)


def test_scope_binds_original_identity_and_never_authorizes_execution():
    a = save_context('workspace', 'actor', 'uid')
    assert a['execution_authorized'] is False
    for args in [('other','actor','uid'),('workspace','other','uid'),('workspace','actor','other')]:
        assert save_context(*args)['scope_digest'] != a['scope_digest']


@pytest.mark.parametrize('request_id', [None, '', REQUEST.upper(), 'other', ['request']])
def test_request_reference_is_strict(request_id):
    with pytest.raises(HTTPException): control_scope('workspace','actor','uid',request_id)


def test_receipt_contains_references_only_and_preserves_input():
    row = control(); before = deepcopy(row)
    result = public_receipt(row, control_scope('workspace','actor','uid',REQUEST))
    assert result['status'] == 'saved' and result['input_digest'] == 'a'*64
    assert not {'_id','actor_id','created_at','name','nodes','tree'} & result.keys()
    assert row == before


@pytest.mark.parametrize('change', [ {'contract_version':True}, {'template_revision':True},
    {'template_revision':2}, {'workspace_id':['workspace']}, {'actor_id':'other'},
    {'request_id':'other'}, {'scope_digest':'d'*64}, {'input_digest':None},
    {'status':'pending'}, {'template_id':'other'}, {'template_identity_digest':[]},
    {'template_review_digest':'bad'}, {'created_at':'today'}, {'future':'field'}])
def test_malformed_receipts_cannot_confirm_save(change):
    row={**control(),**change}
    with pytest.raises(HTTPException) as caught:
        public_receipt(row,control_scope('workspace','actor','uid',REQUEST))
    assert caught.value.status_code == 503


@pytest.mark.parametrize('field',['template_id','input_digest','template_identity_digest','template_review_digest','status'])
def test_bson_code_is_not_a_scalar_receipt_string(field):
    row=control();row[field]=Code(row[field])
    with pytest.raises(HTTPException):public_receipt(row,control_scope('workspace','actor','uid',REQUEST))
