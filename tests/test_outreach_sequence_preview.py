"""Supplied-data preview parity, unknown holds and bounded delay contracts."""
from datetime import datetime, timezone, timedelta
import uuid
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from outreach.api.sequences import PreviewSequenceRequest, preview_sequence, _compile_visual_tree, preview_scope
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError, interpolate_template
from outreach.core.sequence_preview import simulate_sequence, successor_fields, validate_pinned_sequence


def graph(kind='if_connected',delay=24):
    nodes=[{'id':'check','type':kind,'config':{}},{'id':'next','type':'visit_profile','delay_hours':delay,'config':{}}]
    edges=[{'source':'check','target':'next','label':'yes'}]
    return nodes,edges,DAGCompiler.validate_and_compile(nodes,edges)


def test_preview_does_not_invent_action_completion_or_provider_outcomes():
    _,_,compiled=graph('connection_request')
    result=simulate_sequence(compiled,observations={'check':'yes'})
    assert result['ending']=='await_action_outcome' and len(result['steps'])==1 and not result['assumptions']
    assert result['provider_outcomes_verified'] is False and result['execution_authorized'] is False


@pytest.mark.parametrize('observation,ending',[('unknown','waiting_for_observation'),('no','waiting_for_deadline'),('deadline_unknown','needs_review')])
def test_connection_unknown_and_unexpired_no_never_take_negative_branch(observation,ending):
    _,_,compiled=graph()
    result=simulate_sequence(compiled,observations={'check':observation},assume_action_completion=True)
    assert result['ending']==ending and len(result['steps'])==1


def test_one_sided_positive_observation_can_end_without_a_missing_target():
    nodes=[{'id':'check','type':'if_connected'},{'id':'invite','type':'connection_request'}]
    compiled=DAGCompiler.validate_and_compile(nodes,[{'source':'check','target':'invite','label':'no'}])
    result=simulate_sequence(compiled,observations={'check':'yes'},assume_action_completion=True)
    assert result['ending']=='finished' and len(result['steps'])==1


def test_timeout_no_enters_negative_route_only_with_explicit_assumed_deadline():
    nodes=[{'id':'check','type':'if_connected'},{'id':'invite','type':'connection_request','delay_hours':12}]
    compiled=DAGCompiler.validate_and_compile(nodes,[{'source':'check','target':'invite','label':'no'}])
    result=simulate_sequence(compiled,observations={'check':'deadline_no'},assume_action_completion=True)
    assert result['configured_delay_hours']==12 and result['assumed_wait_hours']==72
    assert [row['node_id'] for row in result['steps']]==['check','invite']
    assert result['assumptions']==[{'node_id':'invite','kind':'action_completes_successfully'}]


def test_email_sample_presence_does_not_establish_usable_policy_evidence():
    _,_,compiled=graph('if_email_available')
    result=simulate_sequence(compiled,sample={'email':'a@example.invalid'},assume_action_completion=True)
    assert result['ending']=='waiting_for_observation' and len(result['steps'])==1
    result=simulate_sequence(compiled,observations={'check':'yes'},assume_action_completion=True)
    assert len(result['steps'])==2 and result['configured_delay_hours']==24


@pytest.mark.parametrize('observations',[{'other':'yes'},{'check':'deadline_no'},{'check':True}])
def test_email_observations_are_exact_typed_policy_checks(observations):
    _,_,compiled=graph('if_email_available')
    with pytest.raises(DAGValidationError): simulate_sequence(compiled,observations=observations)


def test_custom_variables_missing_from_sample_do_not_become_finished_copy():
    compiled=DAGCompiler.validate_and_compile([{'id':'message','type':'send_message','config':{'body':'Hi {{custom_field}}'}}],[])
    result=simulate_sequence(compiled,initial_connected='yes',assume_action_completion=True)
    assert result['ending']=='sample_variables_missing'
    assert result['steps'][0]['missing_variables']==['custom_field']
    result=simulate_sequence(compiled,sample={'custom_variables':{'custom_field':'Example'}},initial_connected='yes',assume_action_completion=True)
    assert result['steps'][0]['content']['body']['text']=='Hi Example'


def test_location_alias_matches_existing_location_raw():
    assert interpolate_template('{{location}}/{{location_raw}}',{'location':'Example City'})=='Example City/Example City'


@pytest.mark.parametrize('value',[[],False,'bad'])
def test_empty_or_wrong_shape_samples_are_not_normalized_to_empty_dict(value):
    _,_,compiled=graph()
    with pytest.raises(DAGValidationError): simulate_sequence(compiled,sample=value)


def test_tree_preserves_exact_whole_hour_fraction_and_rejects_rounding():
    assert _compile_visual_tree([{'id':'one','type':'visit_profile','delay_days':1/24}])['nodes']['one']['delay_hours']==1
    for delay in [True,'1',.1,float('inf')]:
        with pytest.raises(DAGValidationError): _compile_visual_tree([{'id':'one','type':'visit_profile','delay_days':delay}])


def test_tree_cannot_hide_branch_children_after_end_or_use_a_third_branch():
    for step in [
        {'id':'one','type':'if_connected','branches':{'middle':{'condition':'yes','steps':[]}}},
        {'id':'one','type':'if_connected','branches':{'left':{'condition':'no','endsHere':True,'steps':[{'id':'two','type':'visit_profile'}]}}},
    ]:
        with pytest.raises(DAGValidationError): _compile_visual_tree([step])


def test_all_successor_types_apply_the_exact_saved_delay_or_terminal_state():
    _,_,compiled=graph(); now=datetime(2026,10,14,tzinfo=timezone.utc)
    fields=successor_fields(compiled,'next',now)
    assert fields=={'current_node_id':'next','execution_state':'waiting_delay','next_action_due_at':now+timedelta(hours=24)}
    assert successor_fields(compiled,None,now)=={'current_node_id':None,'execution_state':'finished','next_action_due_at':None}
    with pytest.raises(DAGValidationError): successor_fields(compiled,'missing',now)


def test_invalid_older_pinned_graph_cannot_gain_new_attempt_authority():
    nodes,edges,compiled=graph()
    assert validate_pinned_sequence({'nodes':nodes,'edges':edges,'compiled_dag':compiled})==compiled
    compiled['nodes']['next']['delay_hours']=1
    with pytest.raises(DAGValidationError): validate_pinned_sequence({'nodes':nodes,'edges':edges,'compiled_dag':compiled})


@pytest.mark.asyncio
async def test_preview_binds_complete_request_without_reading_real_records():
    nodes,edges,_=graph()
    request=PreviewSequenceRequest(request_scope=preview_scope({"user_id":"actor","default_workspace_id":"workspace"}),request_id=str(uuid.uuid4()),nodes=nodes,edges=edges,observations={'check':'yes'})
    one=await preview_sequence(request,{"user_id":"actor","default_workspace_id":"workspace"})
    changed=await preview_sequence(request.model_copy(update={'sample':{'first_name':'Changed'}}),{"user_id":"actor","default_workspace_id":"workspace"})
    assert one['input_digest']!=changed['input_digest'] and one['graph_digest']==changed['graph_digest']
    assert one['request_id']==request.request_id and one['execution_authorized'] is False
    request.tree=[{'id':'different','type':'visit_profile'}]
    with pytest.raises(HTTPException): await preview_sequence(request,{"user_id":"actor","default_workspace_id":"workspace"})


def test_preview_request_cannot_coerce_execution_assumptions():
    nodes,edges,_=graph()
    with pytest.raises(ValidationError): PreviewSequenceRequest(request_scope=preview_scope({"user_id":"actor","default_workspace_id":"workspace"}),request_id=str(uuid.uuid4()),nodes=nodes,edges=edges,assume_action_completion='true')



def test_variables_are_literal_single_pass_values_and_expansion_is_bounded():
    assert interpolate_template('{{a}}',{'custom_variables':{'a':'{{b}}','b':'different'}})=='{{b}}'
    with pytest.raises(DAGValidationError): interpolate_template('{{a}}'*10,{'custom_variables':{'a':'x'*2000}})


def test_compiled_only_legacy_inspection_preserves_successor_default_without_rewriting():
    from copy import deepcopy
    from outreach.core.sequence_preview import checked_compiled, same_execution_graph
    _,_,compiled=graph()
    compiled['nodes']['next'].pop('delay_hours')
    before=deepcopy(compiled)
    assert checked_compiled(compiled)['nodes']['next']['delay_hours']==24
    assert compiled==before
    bad=deepcopy(compiled);bad['nodes']['next']=[]
    assert same_execution_graph(compiled,bad) is False


def test_wide_json_is_rejected_before_encoding_or_enqueuing_all_children(monkeypatch):
    from outreach.core.sequence_contract import bounded_json
    monkeypatch.setattr('outreach.core.sequence_contract.json.dumps',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('must reject before encoding')))
    for value in [[None]*20001, {str(i):None for i in range(10001)}]:
        with pytest.raises(DAGValidationError):bounded_json(value)


@pytest.mark.asyncio
async def test_template_compatibility_inspects_without_rewriting_saved_graphs():
    from copy import deepcopy
    from unittest.mock import MagicMock,AsyncMock
    from outreach.api.sequences import get_sequence_templates
    nodes,edges,_=graph();nodes[0]['delay_hours']=True
    row={'id':'legacy-template','nodes':nodes,'edges':edges,'workspace_id':'workspace'}
    before=deepcopy(row)
    db=MagicMock();db.outreach_templates.find.return_value.sort.return_value.to_list=AsyncMock(return_value=[row])
    templates=await get_sequence_templates({'user_id':'actor','default_workspace_id':'workspace'},db)
    assert templates[-1]['compatibility']['valid'] is False
    assert templates[-1]['compatibility']['execution_authorized'] is False
    assert row==before and any(item['compatibility']['valid'] for item in templates[:-1])


@pytest.mark.parametrize('value',[None,False,0,{},'no'])
def test_present_child_steps_and_end_markers_are_not_silently_ignored(value):
    with pytest.raises(DAGValidationError):_compile_visual_tree([{'id':'one','type':'visit_profile','steps':value}])
    if type(value) is not bool:
        with pytest.raises(DAGValidationError):_compile_visual_tree([{'id':'one','type':'visit_profile','endsHere':value}])


def test_terminal_connection_condition_has_no_observation_to_route():
    compiled=DAGCompiler.validate_and_compile([{'id':'terminal','type':'if_connected'}],[])
    result=simulate_sequence(compiled)
    assert result['ending']=='finished' and result['steps'][0]['status']=='terminal_condition'


def test_nested_linear_steps_cannot_hide_actions_from_the_actual_editor():
    with pytest.raises(DAGValidationError):_compile_visual_tree([{'id':'one','type':'visit_profile','steps':[{'id':'hidden','type':'visit_profile'}]}])


@pytest.mark.parametrize('value',['0001-01-01T00:00:00+23:00','9999-12-31T23:59:59-23:00'])
def test_waiting_start_timezone_overflow_is_a_controlled_hold(value):
    from outreach.core.sequence_preview import waiting_start
    with pytest.raises(DAGValidationError):waiting_start({'waiting_for_connection_at':value},'if_connected',datetime.now(timezone.utc))
