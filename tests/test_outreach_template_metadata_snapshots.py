"""Encrypted allowlist, context binding and immutable metadata snapshot contract."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from bson import BSON, Code
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from utils import encryption
from outreach.core import template_metadata_snapshots as snapshots
from outreach.core.template_revision_checkpoints import checkpoint_for
from tests.test_outreach_template_revision_checkpoints import record

NOW=datetime(2026,10,19,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def owned_key(monkeypatch):monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))


def source(revision=1):
    row=record(revision);return row,checkpoint_for(row,'actor',NOW)


def test_only_exact_metadata_is_encrypted_and_no_plaintext_copied():
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    assert snapshots.open_snapshot(saved,checkpoint)=={'name':row['name'],'description':row['description']}
    assert set(saved)==snapshots.FIELDS
    assert row['name'].encode() not in BSON.encode(saved) and row['description'].encode() not in BSON.encode(saved)
    assert b'future_private_field' not in BSON.encode(saved) and b'never copy this' not in BSON.encode(saved)
    assert 'firebase_uid' not in saved and 'name' not in snapshots.receipt(saved)


@pytest.mark.parametrize('field',['workspace_id','template_id','identity_digest','revision','review_digest',
    'checkpoint_id','recorded_by','recorded_at','_id','contract_version','content_kind','extra','ciphertext'])
def test_native_context_and_ciphertext_tampering_holds(field):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    saved[field]='changed' if field!='revision' else True
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)


def test_ciphertext_cannot_be_transplanted_between_contexts():
    row,checkpoint=source();first=snapshots.seal(row,checkpoint,'actor',NOW)
    next_row={**row,'template_revision':2};next_checkpoint=checkpoint_for(next_row,'actor',NOW)
    second=snapshots.seal(next_row,next_checkpoint,'actor',NOW);second['ciphertext']=first['ciphertext']
    with pytest.raises(HTTPException):snapshots.open_snapshot(second,next_checkpoint)


@pytest.mark.parametrize('change',[{'name':Code('Private name')},{'description':None},{'name':''},{'description':'x'*1001}])
def test_malformed_metadata_never_silently_coerces(change):
    row,_=source();row.update(change);checkpoint=checkpoint_for(row,'actor',NOW)
    with pytest.raises(HTTPException):snapshots.seal(row,checkpoint,'actor',NOW)


def test_missing_legacy_description_is_held_without_inventing_empty_text():
    row,_=source();row.pop('description');checkpoint=checkpoint_for(row,'actor',NOW)
    with pytest.raises(HTTPException):snapshots.seal(row,checkpoint,'actor',NOW)


def test_final_revision_and_maximum_unicode_round_trip():
    row,_=source(2**53-1);row.update(name='界'*100,description='界'*1000)
    checkpoint=checkpoint_for(row,'界'*200,NOW);saved=snapshots.seal(row,checkpoint,'界'*200,NOW)
    assert snapshots.open_snapshot(saved,checkpoint)=={'name':row['name'],'description':row['description']}


def test_wrong_key_plaintext_fallback_and_oversize_ciphertext_hold(monkeypatch):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    for token in ['plaintext', 'x'*(snapshots.MAX_TOKEN_BYTES+1), saved['ciphertext']]:
        monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))
        with pytest.raises(HTTPException):snapshots.open_snapshot({**saved,'ciphertext':token},checkpoint)


@pytest.mark.parametrize('payload',['{"context":{},"context":{},"metadata":{}}',
    '{"context":{},"metadata":{},"extra":"private"}'])
def test_encrypted_duplicate_or_extra_json_fields_hold(payload):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    saved['ciphertext']=encryption.encrypt(payload)
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)


def test_snapshot_scope_is_distinct_and_strict():
    from outreach.core.template_governance import review_scope
    assert snapshots.snapshot_scope('workspace','actor','uid')!=review_scope('workspace','actor','uid')
    with pytest.raises(HTTPException):snapshots.snapshot_scope(Code('workspace'),'actor','uid')


@pytest.mark.parametrize('field,value',[('contract_version',True),('contract_version',1.0),('revision',True),('revision',1.0)])
def test_encrypted_context_rejects_equal_but_differently_typed_scalars(field,value):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    payload=json.loads(encryption.decrypt_strict(saved['ciphertext']));payload['context'][field]=value
    saved['ciphertext']=encryption.encrypt(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)


def test_codec_requires_exact_public_template_source_binding():
    row,checkpoint=source();checkpoint['template_id']='tpl_custom_deadbeef00'
    with pytest.raises(HTTPException):snapshots.seal(row,checkpoint,'actor',NOW)
