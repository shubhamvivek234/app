"""Strict graph contracts and path-sensitive offline analysis; no provider calls."""
import pytest
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError


def node(identity='a',kind='visit_profile',**fields): return {'id':identity,'type':kind,**fields}


@pytest.mark.parametrize('field,value',[('id',[]),('id',{}),('id','bad id'),('id','x'*201),('type',[]),('config',[]),('config',None),('title',[]),('delay_hours',True),('delay_hours','1'),('delay_hours',1.5),('delay_hours',1.0),('delay_hours',8761),('delay_hours',float('inf'))])
def test_graph_rejects_malformed_fields_without_coercion_or_crash(field,value):
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(**{field:value})],[])


@pytest.mark.parametrize('kind,label',[('visit_profile','yes'),('connection_request','acceptd'),('if_connected','email available'),('send_message','connected'),('if_email_available','replied')])
def test_branch_vocabulary_is_specific_to_the_source_step(kind,label):
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(kind=kind),node('b')],[{'source':'a','target':'b','label':label}])


def test_conflicting_handle_and_display_branch_is_rejected():
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(kind='if_connected'),node('b')],[{'source':'a','target':'b','label':'accepted','sourceHandle':'no'}])


def test_same_branch_synonyms_and_unsupported_condition_topology_remain_inspectable():
    graph=DAGCompiler.validate_and_compile([node(kind='if_connected'),node('b')],[{'source':'a','target':'b','label':'connected','sourceHandle':'yes'}])
    assert graph['nodes']['a']['branches']=={'positive':'b'}
    graph=DAGCompiler.validate_and_compile([node(kind='if_opened_message'),node('b')],[{'source':'a','target':'b','label':'opened'}])
    assert graph['nodes']['a']['branches']=={'positive':'b'}


def test_default_and_conditional_successors_cannot_silently_compete():
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(kind='connection_request'),node('b'),node('c')],[{'source':'a','target':'b','label':'accepted'},{'source':'a','target':'c'}])


@pytest.mark.parametrize('edge',[None,[],{'source':[],'target':'a'},{'source':'a','target':{}},{'source':'a','target':'b','label':[]}])
def test_bad_edges_produce_controlled_validation_errors(edge):
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(),node('b')],[edge])


@pytest.mark.parametrize('value',[True,'3',0,31,1.5])
def test_condition_deadlines_are_strict_and_bounded(value):
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(kind='if_connected',config={'timeout_days':value})],[])


def test_graph_size_and_nonfinite_deep_json_are_bounded():
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(str(i)) for i in range(101)],[])
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node()],[{'source':'a','target':'a'}]*201)
    for config in ({'x':float('nan')},{'x':'\ud800'},{'x':'v'*1_000_001}):
        with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(config=config)],[])
    config={}; cursor=config
    for _ in range(20): cursor['x']={}; cursor=cursor['x']
    with pytest.raises(DAGValidationError): DAGCompiler.validate_and_compile([node(config=config)],[])


def test_semantic_analysis_keeps_negative_witness_after_paths_merge():
    from outreach.core.sequence_preview import analyze_sequence
    graph=DAGCompiler.validate_and_compile([node(kind='if_connected'),node('yes'),node('no'),node('join',kind='send_message',config={'body':'Hi'})],[{'source':'a','target':'yes','label':'yes'},{'source':'a','target':'no','label':'no'},{'source':'yes','target':'join'},{'source':'no','target':'join'}])
    report=analyze_sequence(graph)
    bad=next(item for item in report['issues'] if item['code']=='message_without_connection_guard')
    assert bad['node_id']=='join' and 'no' in bad['path'] and not report['valid']


def test_unknown_initial_connection_is_a_requirement_not_an_assumed_negative():
    from outreach.core.sequence_preview import analyze_sequence
    report=analyze_sequence(DAGCompiler.validate_and_compile([node(kind='send_message',config={'body':'Hi'})],[]))
    assert report['valid'] and any(item['code']=='connection_required_at_execution' for item in report['issues'])


def test_invite_default_path_does_not_establish_connection():
    from outreach.core.sequence_preview import analyze_sequence
    report=analyze_sequence(DAGCompiler.validate_and_compile([node(kind='connection_request'),node('b',kind='send_message',config={'body':'Hi'})],[{'source':'a','target':'b'}]))
    assert not report['valid']


def test_unavailable_actions_and_unresolved_prompt_tokens_are_not_valid_execution():
    from outreach.core.sequence_preview import analyze_sequence
    for action,config in [('inmail',{}),('send_message',{'body':'✨ [generate something]'})]:
        assert not analyze_sequence(DAGCompiler.validate_and_compile([node(kind=action,config=config)],[]))['valid']


def test_negative_email_path_needs_new_evidence_or_finder_before_send():
    from outreach.core.sequence_preview import analyze_sequence
    graph=DAGCompiler.validate_and_compile([node(kind='if_email_available'),node('b',kind='send_email',config={'subject':'Hi','body':'Hello'})],[{'source':'a','target':'b','label':'no'}])
    assert not analyze_sequence(graph)['valid']


def test_reply_positive_successors_cannot_promise_work_after_reply_stop():
    from outreach.core.sequence_preview import analyze_sequence
    graph=DAGCompiler.validate_and_compile([node(kind='send_message',config={'body':'Hi'}),node('b')],[{'source':'a','target':'b','label':'replied'}])
    assert not analyze_sequence(graph)['valid']


@pytest.mark.parametrize('config',[{'max_post_age_days':[]},{'max_post_age_days':True},{'max_post_age_days':'30'},{'max_post_age_days':0},{'max_post_age_days':366},{'skip_if_no_posts':'false'},{'skip_if_no_posts':0}])
def test_like_settings_are_typed_before_any_provider_reads(config):
    with pytest.raises(DAGValidationError):DAGCompiler.validate_and_compile([node(kind='like_last_post',config=config)],[])


@pytest.mark.parametrize('wait',[False,True])
def test_invitation_path_does_not_allow_another_invitation_after_negative_wait(wait):
    from outreach.core.sequence_preview import analyze_sequence
    nodes=[node(kind='connection_request'),node('next',kind='connection_request')]
    edges=[{'source':'a','target':'next'}]
    if wait:
        nodes.append(node('wait',kind='if_connected'))
        edges=[{'source':'a','target':'wait'},{'source':'wait','target':'next','label':'no'}]
    report=analyze_sequence(DAGCompiler.validate_and_compile(nodes,edges))
    assert not report['valid'] and any(row['code']=='invite_already_requested_on_path' for row in report['issues'])


@pytest.mark.parametrize('value',[-2**63,2**63-1])
def test_json_integer_contract_matches_native_bson_boundaries(value):
    from bson import BSON
    graph=DAGCompiler.validate_and_compile([node(config={'arbitrary':value})],[])
    assert BSON.encode(graph)


@pytest.mark.parametrize('config',[{'arbitrary':2**63},{'arbitrary':-2**63-1},{'\x00':1}])
def test_json_rejects_values_or_keys_that_cannot_be_saved_as_bson(config):
    with pytest.raises(DAGValidationError):DAGCompiler.validate_and_compile([node(config=config)],[])
