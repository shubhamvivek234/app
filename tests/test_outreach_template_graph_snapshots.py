"""Exact encrypted graph capture, typed field policy and cross-kind binding."""
from copy import deepcopy
from datetime import datetime,timezone
import json

from bson import BSON,Code,Int64
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from utils import encryption
from outreach.core import template_graph_content as content
from outreach.core import template_graph_snapshots as snapshots
from outreach.core import template_metadata_snapshots as metadata
from outreach.core.template_revision_checkpoints import checkpoint_for
from outreach.core.template_graphs import compile_graph
from tests.test_outreach_template_revision_checkpoints import record

NOW=datetime(2026,10,19,tzinfo=timezone.utc)


class DerivedKey(str):
    pass


def graph():
    check={'id':'check','type':'if_connected','title':'Connection','subtitle':'Visible condition',
        'delay_hours':0,'config':{'timeout_days':3},'position':{'x':250.0,'y':50}}
    message={'id':'message','type':'send_message','title':'Message','subtitle':'Visible copy',
        'delay_hours':24,'config':{'body':'Hello {{first_name}} — नमस्ते','timeout_days':7},'position':{'x':250,'y':180.0}}
    tree=[{k:deepcopy(v) for k,v in check.items() if k not in {'position','delay_hours'}}]
    tree[0].update(delay_days=0,branches={
        'left':{'condition':'No','type':'danger','steps':[],'endsHere':True},
        'right':{'condition':'Yes','type':'success','steps':[{k:deepcopy(v) for k,v in message.items() if k not in {'position','delay_hours'}}]}})
    tree[0]['branches']['right']['steps'][0].update(delay_days=1,isActionRequired=True,endsHere=True)
    return {'nodes':[check,message],'edges':[{'id':'edge','source':'check','target':'message',
        'label':'Yes','sourceHandle':'positive','targetHandle':None}],'tree':tree}


def single(kind,config=None):
    node={'id':'root','type':kind,'config':config or {}}
    return {'nodes':[deepcopy(node)],'edges':[],'tree':[deepcopy(node)]}


def source(value=None,revision=1,compiled=False):
    row={**record(revision),**deepcopy(value if value is not None else graph())}
    if compiled:row.update(compile_graph({k:row[k] for k in ('nodes','edges','tree')}))
    return row,checkpoint_for(row,'actor',NOW)


@pytest.fixture(autouse=True)
def owned_key(monkeypatch):monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))


@pytest.mark.parametrize('compiled',[False,True])
def test_actual_canvas_fields_and_original_array_order_round_trip(compiled):
    row,checkpoint=source(compiled=compiled);before=deepcopy(row)
    projected=content.project_graph(row);assert projected==graph() and row==before
    saved=snapshots.seal(row,checkpoint,'actor',NOW)
    assert snapshots.open_snapshot(saved,checkpoint)==projected and set(saved)==snapshots.FIELDS
    raw=BSON.encode(saved)
    assert 'नमस्ते'.encode() not in raw and b'never copy this' not in raw and b'compiled_dag' not in raw
    assert not {'nodes','tree','name','ciphertext'} & snapshots.receipt(saved).keys()


@pytest.mark.parametrize('kind,config',[
    ('visit_profile',{'dwell_mode':'deep','skip_if_visited':True}),
    ('connection_request',{'note':'Hello','timeout_days':30}),
    ('send_message',{'body':'Hello','timeout_days':1}),
    ('voice_note',{'script':'A reviewed script','fallback':'A fallback','timeout_days':7}),
    ('like_last_post',{'max_post_age_days':365,'skip_if_no_posts':False}),
    ('if_connected',{'timeout_days':3}),('find_email',{}),
    ('send_email',{'subject':'Subject','body':'Hello'}),('if_email_available',{}),
    ('has_data_in_column',{'condition_contract_version':1,'field':'custom_variables.score','operator':'equals','value_type':'number','value':Int64(42)})])
def test_supported_configuration_fields_are_retained_without_defaults(kind,config):
    value=single(kind,config);assert content.project_graph(value)==value


@pytest.mark.parametrize('fault',['root_extra','node_extra','tree_extra','branch_extra','config_extra',
    'nonplain_key','code_value','body_object','timeout_bool','delay_float','position_extra','position_infinite',
    'position_bool','branch_type','subtitle_object','end_bool','action_bool','handle_object','bad_label',
    'unknown_type','unknown_compiler_field','marker_alone','compiled_alone','compiled_drift'])
def test_unknown_or_malformed_graph_fields_hold_instead_of_silent_filtering(fault):
    row,_=source(compiled=True)
    if fault=='root_extra':row['nodes'][0]['config']['access_token']='private-secret'
    elif fault=='node_extra':row['nodes'][0]['credential']='private-secret'
    elif fault=='tree_extra':row['tree'][0]['credential']='private-secret'
    elif fault=='branch_extra':row['tree'][0]['branches']['left']['credential']='private-secret'
    elif fault=='config_extra':row['nodes'][1]['config']['headers']={'Authorization':'private-secret'}
    elif fault=='nonplain_key':row['nodes'][1]['config']={DerivedKey('body'):'Hello'}
    elif fault=='code_value':row['nodes'][1]['config']['body']=Code('Hello')
    elif fault=='body_object':row['nodes'][1]['config']['body']={'text':'Hello'}
    elif fault=='timeout_bool':row['nodes'][1]['config']['timeout_days']=True
    elif fault=='delay_float':row['nodes'][1]['delay_hours']=24.0
    elif fault=='position_extra':row['nodes'][0]['position']['secret']='private-secret'
    elif fault=='position_infinite':row['nodes'][0]['position']['x']=float('inf')
    elif fault=='position_bool':row['nodes'][0]['position']['x']=True
    elif fault=='branch_type':row['tree'][0]['branches']['left']['type']='other'
    elif fault=='subtitle_object':row['nodes'][0]['subtitle']={}
    elif fault=='end_bool':row['tree'][0]['branches']['left']['endsHere']=1
    elif fault=='action_bool':row['tree'][0]['branches']['right']['steps'][0]['isActionRequired']=1
    elif fault=='handle_object':row['edges'][0]['targetHandle']={}
    elif fault=='bad_label':row['edges'][0]['label']='x'*81
    elif fault=='unknown_type':row['nodes'][0]['type']='inmail'
    elif fault=='unknown_compiler_field':row['compiled_dag']['secret']='private-secret'
    elif fault=='marker_alone':row.pop('compiled_dag')
    elif fault=='compiled_alone':row.pop('compiler_contract_version')
    else:row['compiled_dag']['nodes']['check']['title']='Changed'
    with pytest.raises(HTTPException) as caught:content.project_graph(row)
    assert caught.value.status_code==409 and 'private-secret' not in str(caught.value.detail)


def test_root_document_secrets_are_excluded_and_missing_fields_not_invented():
    value=single('visit_profile');row,_=source(value);row['api_key']='private-secret'
    assert content.project_graph(row)==value
    assert 'title' not in content.project_graph(row)['nodes'][0]


@pytest.mark.parametrize('field,value',[('contract_version',True),('contract_version',1.0),('revision',True),('revision',1.0)])
def test_encrypted_context_rejects_numeric_aliases(field,value):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    payload=json.loads(encryption.decrypt_strict(saved['ciphertext']));payload['context'][field]=value
    saved['ciphertext']=encryption.encrypt(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)


@pytest.mark.parametrize('field',['template_id','workspace_id','identity_digest','review_digest','checkpoint_id','recorded_by','_id','content_kind','extra'])
def test_outer_context_transplants_and_extra_fields_hold(field):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW);saved[field]='changed'
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)


def test_cross_kind_scopes_ciphertext_and_wrong_source_context_hold():
    row,checkpoint=source();graph_saved=snapshots.seal(row,checkpoint,'actor',NOW);meta_saved=metadata.seal(row,checkpoint,'actor',NOW)
    assert snapshots.snapshot_scope('workspace','actor','uid')!=metadata.snapshot_scope('workspace','actor','uid')
    assert graph_saved['_id']!=meta_saved['_id']
    with pytest.raises(HTTPException):snapshots.open_snapshot({**graph_saved,'ciphertext':meta_saved['ciphertext']},checkpoint)
    wrong={**checkpoint,'template_id':'tpl_custom_deadbeef00'}
    with pytest.raises(HTTPException):snapshots.seal(row,wrong,'actor',NOW)


def test_final_revision_graph_and_native_json_integer_values_are_supported():
    value=single('has_data_in_column',{'condition_contract_version':1,'field':'custom_variables.score',
        'operator':'equals','value_type':'number','value':Int64(2**40)})
    row,checkpoint=source(value,revision=2**53-1);saved=snapshots.seal(row,checkpoint,'actor',NOW)
    opened=snapshots.open_snapshot(saved,checkpoint)
    assert type(opened['nodes'][0]['config']['value']) is int and opened['nodes'][0]['config']['value']==2**40


@pytest.mark.parametrize('fault',['graph_size','cipher_size','wrong_key','plaintext','duplicate_json','extra_payload'])
def test_crypto_and_payload_bounds_hold_without_plaintext_fallback(monkeypatch,fault):
    row,checkpoint=source();saved=snapshots.seal(row,checkpoint,'actor',NOW)
    if fault=='graph_size':
        monkeypatch.setattr(content,'MAX_GRAPH_BYTES',1)
        with pytest.raises(HTTPException):content.project_graph(row)
        return
    if fault=='cipher_size':saved['ciphertext']='x'*(snapshots.MAX_TOKEN_BYTES+1)
    elif fault=='wrong_key':monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))
    elif fault=='plaintext':saved['ciphertext']='plain private text'
    elif fault=='duplicate_json':saved['ciphertext']=encryption.encrypt('{"context":{},"context":{},"graph":{}}')
    else:saved['ciphertext']=encryption.encrypt('{"context":{},"graph":{},"credential":"secret"}')
    with pytest.raises(HTTPException):snapshots.open_snapshot(saved,checkpoint)
