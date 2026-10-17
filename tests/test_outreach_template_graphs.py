"""Strict full-source template graph review and frozen-input binding."""
from copy import deepcopy
import json

from bson import Code
from fastapi import HTTPException
import pytest

from outreach.core import template_graphs as graphs
from outreach.core.template_governance import scoped_review
from outreach.core.template_metadata import metadata_review
from tests.test_outreach_template_governance import record

NODE = {'id': 'root', 'type': 'visit_profile', 'title': 'Original visit', 'delay_hours': 0, 'config': {}}
GRAPH = {'nodes': [NODE], 'edges': [], 'tree': [NODE]}
CONTENT = json.dumps(GRAPH)


def original():
    return {**record(), **deepcopy(GRAPH)}


def test_compile_and_review_preserve_source_and_grant_no_authority():
    graph = deepcopy(GRAPH); before = deepcopy(graph)
    prepared = graphs.compile_graph(graph)
    assert graph == before and prepared['compiler_contract_version'] == 1
    assert prepared['nodes'] == graph['nodes'] and prepared['tree'] == graph['tree']
    row = original(); review = graphs.graph_review(row, 'workspace', 'actor', 'uid')
    assert review['reviewable'] and not review['update_authorized'] and not review['execution_authorized']
    assert review['scope_digest'] not in {scoped_review(row,'workspace','actor','uid')['scope_digest'],
        metadata_review(row,'workspace','actor','uid')['scope_digest']}


@pytest.mark.parametrize('patch', [
    {'tree': None}, {'tree': []}, {'nodes': []}, {'edges': [] , 'compiled_dag': {}},
    {'nodes': [{**NODE, 'delay_hours': True}]}, {'nodes': [{**NODE, 'delay_hours': 1.5}]},
    {'nodes': [{**NODE, 'config': []}]}, {'nodes': [{**NODE, 'type': 'unknown_action'}]},
    {'tree': [{**NODE, 'delay_hours': 24}]}, {'tree': [{**NODE, 'steps': [NODE]}]},
])
def test_invalid_or_hidden_graphs_are_rejected(patch):
    with pytest.raises(HTTPException) as caught: graphs.compile_graph({**deepcopy(GRAPH), **patch})
    assert caught.value.status_code == 422


@pytest.mark.parametrize('content', [None, Code(CONTENT), '', 'not json', '{"nodes":[],"nodes":[]}',
    '{"nodes":[],"edges":[],"tree":[],"x":NaN}', '{"nodes":[],"edges":[],"tree":[],"x":1e400}',
    '"'+'x'*1_048_576+'"'], ids=['missing','code','empty','syntax','duplicate-key','nan','infinite','utf8-overflow'])
def test_frozen_input_is_exact_strict_bounded_json(content):
    with pytest.raises(HTTPException): graphs.prepare_graph(content)


@pytest.mark.parametrize('patch', [
    {'tree': None}, {'tree': []}, {'template_revision': 2**53-1}, {'workspace_id': ['workspace']},
    {'nodes': [{**NODE, 'delay_hours': True}]}, {'compiled_dag': {}},
    {'compiled_dag': {'nodes': {}}, 'compiler_contract_version': True},
])
def test_unproven_originals_stay_unavailable(patch):
    result = graphs.graph_review({**original(), **patch}, 'workspace', 'actor', 'uid')
    assert result['reviewable'] is False and result['review_digest'] is None


def test_input_digest_binds_original_whitespace_and_unicode():
    first = graphs.prepare_graph(CONTENT)
    second = graphs.prepare_graph(json.dumps(GRAPH, indent=2))
    assert first['input_digest'] != second['input_digest']
    assert first['graph_digest'] == second['graph_digest']


def test_review_rejects_context_without_throwing():
    assert graphs.graph_review(original(), 'workspace', 'actor', None)['reviewable'] is False


@pytest.mark.parametrize('fault',['boolean_delay','wrong_id','wrong_order','missing_order','extra_field','float_delay','config_shape','code_title'])
def test_original_current_compiler_document_must_be_strict_not_only_semantically_similar(fault):
    row=original();row.update(graphs.compile_graph(deepcopy(GRAPH)))
    compiled=row['compiled_dag']
    if fault=='boolean_delay': compiled['nodes']['root']['delay_hours']=False
    elif fault=='float_delay': compiled['nodes']['root']['delay_hours']=0.0
    elif fault=='wrong_id': compiled['nodes']['root']['id']='replacement'
    elif fault=='wrong_order': compiled['execution_order']=['replacement']
    elif fault=='missing_order': compiled.pop('execution_order')
    elif fault=='extra_field': compiled['future_execution']='unknown'
    elif fault=='code_title': compiled['nodes']['root']['title']=Code(compiled['nodes']['root']['title'])
    else: compiled['nodes']['root']['config']=[]
    assert graphs.graph_review(row,'workspace','actor','uid')['reviewable'] is False


@pytest.mark.parametrize('value',[2**53,-2**53,1e100,Code('literal')])
def test_graph_values_must_have_lossless_supported_browser_json_values(value):
    node={**NODE,'config':{'value':value}}
    with pytest.raises(HTTPException): graphs.compile_graph({'nodes':[node],'edges':[],'tree':[node]})


@pytest.mark.parametrize('marker',[None,True,1,1.0,2,'1'])
def test_present_compiler_marker_without_compiled_original_stays_held(marker):
    row={**original(),'compiler_contract_version':marker}
    assert graphs.graph_review(row,'workspace','actor','uid')['reviewable'] is False
