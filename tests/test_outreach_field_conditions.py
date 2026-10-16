"""Shared stored-field semantics; supplied preview values never authorize sends."""
import math
import pytest
from bson import BSON
from bson.int64 import Int64

from outreach.core.field_conditions import evaluate, validate_config
from outreach.core.sequence_contract import DAGValidationError
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.sequence_preview import simulate_sequence


def config(**changes):
    return {'condition_contract_version': 1, 'field': 'custom_variables.score', 'operator': 'has_value', **changes}


@pytest.mark.parametrize('value,result,reason', [
    (None,False,'null'), ('',False,'empty'), (' \t\u2003\u00a0',False,'blank'),
    ('0',True,'present'), (0,True,'present'), (False,True,'present'),
    ([],None,'unsupported_value'), ({},None,'unsupported_value'),
    (math.inf,None,'unsupported_value'), (2**53,None,'unsupported_value'),
    (Int64(2**32),True,'present'),(10**1000,None,'unsupported_value'),
])
def test_presence(value,result,reason):
    assert evaluate(config(), {'custom_variables':{'score':value}})=={'condition_met':result,'reason':reason}


def test_missing_and_malformed_container():
    assert evaluate(config(), {})['reason']=='missing'
    assert evaluate(config(), {'custom_variables':[]})['condition_met'] is None


@pytest.mark.parametrize('actual,kind,target,result', [
    (False,'boolean',False,True),(0,'number',0,True),('0','number',0,None),
    (False,'number',0,None),(0,'boolean',False,None),(' A ','text','A',False),
    ('a','text','A',False),(None,'text','',None),('', 'text','',True),
])
@pytest.mark.parametrize('operator',['equals','not_equals'])
def test_typed_comparison(actual,kind,target,result,operator):
    expected=result if operator=='equals' or result is None else not result
    c=config(operator=operator,value_type=kind,value=target)
    assert evaluate(c,{'custom_variables':{'score':actual}})['condition_met'] is expected


@pytest.mark.parametrize('changes', [
    {'condition_contract_version':True},{'condition_contract_version':2}, {'field':'permission'},
    {'field':'custom_variables.secret.nested'}, {'field':'custom_variables.$x'},
    {'field':'custom_variables.spaced name'}, {'operator':'truthy'}, {'timeout_days':3},
    {'operator':'equals'}, {'operator':'equals','value_type':'number','value':True},
    {'operator':'equals','value_type':'number','value':2**53},
    {'operator':'equals','field':'email','value_type':'boolean','value':False},
    {'value':'hidden'}, {'field':'_id'},
])
def test_invalid_contract(changes):
    with pytest.raises(DAGValidationError): validate_config(config(**changes))


def graph(field='custom_variables.score'):
    return DAGCompiler.validate_and_compile([
        {'id':'check','type':'has_data_in_column','config':config(field=field)},
        {'id':'yes','type':'send_email','config':{'subject':'Hi','body':'Hello'}}],
        [{'source':'check','target':'yes','label':'yes'}])


def test_preview_uses_typed_values_without_action_assumption_or_email_authority():
    report=simulate_sequence(graph('email'),condition_values={'email':'x@example.com'})
    assert report['steps'][0]['status']=='evaluated_branch'
    assert report['steps'][0]['branch']=='positive'
    assert report['ending']=='usable_email_required'
    assert report['execution_authorized'] is False


def test_preview_missing_comparison_holds_and_no_manual_observation_override():
    compiled=graph()
    compiled['nodes']['check']['config']=config(operator='not_equals',value_type='number',value=1)
    assert simulate_sequence(compiled)['ending']=='needs_review'
    with pytest.raises(DAGValidationError): simulate_sequence(compiled,observations={'check':'yes'})


def test_native_bson_numeric_config_and_value_preserve_preview_parity():
    compiled=graph()
    compiled['nodes']['check']['config']=config(operator='equals',value_type='number',value=2**32)
    native=BSON(BSON.encode(compiled)).decode()
    result=simulate_sequence(native,condition_values={'custom_variables':{'score':2**32}})
    assert result['steps'][0]['branch']=='positive'


@pytest.mark.parametrize('receipt',[None,[],{'version':1,'status':[]},{'version':True,'status':'branch_advanced'}])
def test_malformed_recovery_receipts_are_total_and_do_not_claim_completion(receipt):
    from outreach.core.sequence_conditions import saved_result
    assert saved_result({'workspace_id':'workspace','status':'completed','condition_decision':receipt}) is None
