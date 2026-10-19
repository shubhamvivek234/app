"""Digest lineage, page/cursor bounds and strict storage-index contracts."""
from copy import deepcopy
from datetime import datetime, timezone
import base64

from bson import Code, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core import template_history as history
from outreach.core import template_history_storage as storage
from outreach.core.template_revision_checkpoints import checkpoint_for, deletion_checkpoint_for
from tests.test_outreach_template_revision_checkpoints import record

NOW = datetime(2026,10,19,tzinfo=timezone.utc)
NATIVE = ObjectId('0123456789ab0123456789ab')


def chain():
    first = {**record(1),'_id':NATIVE}; second = {**first,'template_revision':2,'name':'Changed'}
    return [checkpoint_for(first,'actor',NOW,event='created'),
        checkpoint_for(second,'actor',NOW,predecessor=first,event='graph'),
        deletion_checkpoint_for(second,'actor',NOW)]


def page(rows=None,**changes):
    values = rows if rows is not None else chain(); first=values[0]
    return history.make_page(values,'workspace',first['template_id'],first['identity_digest'],'actor','uid',**changes)


def test_same_revision_terminal_follows_ordinary_parent_and_pages_without_loss():
    rows=chain(); first=page(list(reversed(rows)),page_size=2)
    assert [r['event'] for r in first['items']] == ['created','graph']
    second=page(rows,page_size=2,cursor=first['next_cursor'])
    assert [r['event'] for r in second['items']] == ['deleted'] and second['next_cursor'] is None
    assert first['history_digest']==second['history_digest'] and first['record_count']==3
    assert not first['capture_complete'] and not first['content_available'] and not first['restore_available'] and not first['execution_authorized']
    assert first['terminal_recorded'] and all(not {'name','nodes','firebase_uid'} & r.keys() for r in first['items'])
    assert first['items'][0]['recorded_at']=='2026-10-19T00:00:00.000Z'


@pytest.mark.parametrize('fault',['missing_parent','wrong_parent','duplicate_ordinary','duplicate_terminal',
    'ordinary_after_terminal','created_before_zero','terminal_without_ordinary','unknown_field','wrong_identity','bad_terminal'])
def test_inconsistent_history_is_held_before_any_page(fault):
    rows=chain()
    if fault=='missing_parent': rows.pop(0)
    elif fault=='wrong_parent': rows[1]['predecessor_review_digest']='a'*64
    elif fault=='duplicate_ordinary': rows.append(deepcopy(rows[0]))
    elif fault=='duplicate_terminal': rows.append(deepcopy(rows[-1]))
    elif fault=='ordinary_after_terminal':
        row={**record(3),'_id':NATIVE};rows.append(checkpoint_for(row,'actor',NOW))
    elif fault=='created_before_zero':
        row={**record(0),'_id':NATIVE};value=checkpoint_for(row,'actor',NOW);rows.append(value)
    elif fault=='terminal_without_ordinary': rows.pop(1)
    elif fault=='unknown_field': rows[0]['private_text']='must not be projected away'
    elif fault=='wrong_identity': rows[0]['identity_digest']='b'*64
    else: rows[-1]['review_digest']='bad'
    with pytest.raises(HTTPException): page(rows,page_size=1)


def test_observed_gaps_are_explicit_without_invented_creation_or_continuity():
    row=record(4); result=page([checkpoint_for(row,'actor',NOW)])
    assert result['items'][0]['event']=='observed' and result['items'][0]['predecessor_revision'] is None
    assert not result['capture_complete'] and not result['terminal_recorded']


def test_snapshot_hash_binds_full_native_record_including_actor_audit():
    rows=chain(); before=page(rows,page_size=1)
    changed=deepcopy(rows);changed[0]['recorded_by']='another-actor'
    with pytest.raises(HTTPException) as caught: page(changed,page_size=1,cursor=before['next_cursor'])
    assert caught.value.status_code==409


@pytest.mark.parametrize('size',[True,0,26,1.0,'2',None])
def test_page_size_is_strict_and_bounded(size):
    with pytest.raises(HTTPException): page(page_size=size)


@pytest.mark.parametrize('value',['','a','!!!!','e30=','e30',Code('e30'),'a'*769])
def test_malformed_noncanonical_cursor_cannot_be_used(value):
    with pytest.raises(HTTPException): page(cursor=value)


def test_cursor_binds_identity_scope_and_page_size():
    rows=chain(); first=page(rows,page_size=1)
    with pytest.raises(HTTPException) as caught:
        history.make_page(rows,'workspace',rows[0]['template_id'],rows[0]['identity_digest'],'other','uid',page_size=1,cursor=first['next_cursor'])
    assert caught.value.status_code==403
    with pytest.raises(HTTPException): page(rows,page_size=2,cursor=first['next_cursor'])


def test_canonical_cursor_still_requires_an_existing_after_record():
    rows=chain(); first=page(rows,page_size=1)
    token=history.encode_cursor(history.scope_digest('workspace','actor','uid',rows[0]['template_id'],rows[0]['identity_digest']),
        first['history_digest'],'a'*64,1)
    with pytest.raises(HTTPException) as caught: page(rows,page_size=1,cursor=token)
    assert caught.value.status_code==409


def test_duplicate_cursor_json_keys_are_rejected():
    raw='{"contract_version":1,"contract_version":1}'
    token=base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')
    with pytest.raises(HTTPException): page(cursor=token)


def indexes():
    return {'_id_':{'key':[('_id',1)],'v':2},storage.INDEX_NAME:{'key':deepcopy(storage.INDEX_KEYS),'v':2}}


def test_index_defaults_are_equivalent_to_explicit_false_and_simple_collation():
    storage.validate_indexes(indexes())
    rows=indexes();rows[storage.INDEX_NAME].update(unique=False,sparse=False,hidden=False,prepareUnique=False,collation={'locale':'simple'})
    storage.validate_indexes(rows)


@pytest.mark.parametrize('change',[{'unique':True},{'sparse':True},{'hidden':True},{'prepareUnique':True},
    {'partialFilterExpression':{}},{'expireAfterSeconds':0},{'collation':{'locale':'en'}},
    {'key':[('workspace_id',True)]},{'key':[('identity_digest',1),('workspace_id',1)]}])
def test_incompatible_index_options_are_not_silently_repaired(change):
    rows=indexes();rows[storage.INDEX_NAME].update(change)
    with pytest.raises(HTTPException): storage.validate_indexes(rows)


def test_any_retention_ttl_holds_readiness_and_missing_required_index_holds():
    rows=indexes();rows['legacy_ttl']={'key':[('recorded_at',1)],'expireAfterSeconds':10}
    with pytest.raises(HTTPException): storage.validate_indexes(rows)
    with pytest.raises(HTTPException): storage.validate_indexes({'_id_':rows['_id_']})


def test_maximum_unicode_context_has_bounded_cursor_and_exact_response_shape():
    workspace='界'*200;row={**record(1),'_id':NATIVE,'workspace_id':workspace}
    rows=[checkpoint_for(row,'界'*200,NOW,event='created'),deletion_checkpoint_for(row,'界'*200,NOW)]
    result=history.make_page(rows,workspace,row['id'],rows[0]['identity_digest'],'界'*200,'界'*200,page_size=1)
    assert len(result['next_cursor'])<=768
    assert set(result)=={'contract_version','workspace_id','template_id','identity_digest','history_digest',
        'record_count','items','next_cursor','terminal_recorded','capture_complete','content_available','restore_available','execution_authorized'}
    assert len(result['items'][0])==8
    second=history.make_page(rows,workspace,row['id'],rows[0]['identity_digest'],'界'*200,'界'*200,page_size=1,cursor=result['next_cursor'])
    assert second['next_cursor'] is None and second['items'][0]['event']=='deleted'


@pytest.mark.parametrize('bound',['rows','bytes','response'])
def test_history_bounds_hold_without_partial_page(monkeypatch,bound):
    monkeypatch.setattr(history,{'rows':'MAX_CHECKPOINTS','bytes':'MAX_HISTORY_BYTES','response':'MAX_RESPONSE_BYTES'}[bound],1)
    with pytest.raises(HTTPException) as caught:page()
    assert caught.value.status_code==409


def test_collation_metadata_cannot_use_native_code_alias():
    rows=indexes();rows[storage.INDEX_NAME]['collation']={'locale':Code('simple')}
    with pytest.raises(HTTPException):storage.validate_indexes(rows)


@pytest.mark.parametrize('kind,status',[('missing',404),('stale',409),('malformed',422),('foreign',403)])
def test_empty_history_preserves_cursor_shape_scope_and_staleness_contract(kind,status):
    rows=chain();first=page(rows,page_size=1);cursor=first['next_cursor']
    if kind=='missing':cursor=None
    elif kind=='malformed':cursor='invalid'
    elif kind=='foreign':
        cursor=history.encode_cursor('a'*64,first['history_digest'],rows[0]['_id'],1)
    with pytest.raises(HTTPException) as caught:
        history.make_page([],'workspace',rows[0]['template_id'],rows[0]['identity_digest'],'actor','uid',page_size=1,cursor=cursor)
    assert caught.value.status_code==status
