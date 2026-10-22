"""Version-one graph field policy: exact known JSON, never silent filtering.

Capture preserves stored definitions, including UI fields and absent defaults.
It proves neither renderer/provider behavior nor execution authorization.
"""
import logging
logger = logging.getLogger(__name__)
from copy import deepcopy
import math
import re

from bson import Int64
from fastapi import HTTPException

from outreach.core.template_governance import MAX_REVISION
from outreach.core.template_graphs import compile_graph
from outreach.core.sequence_contract import bounded_json
from outreach.core.field_conditions import validate_config
from outreach.core.template_snapshot_capture import canonical_json

MAX_GRAPH_BYTES=128*1024
NODE_FIELDS={'id','type','title','subtitle','delay_hours','config','position'}
TREE_FIELDS=NODE_FIELDS-{'position'}|{'delay_days','branches','steps','endsHere','isActionRequired'}
EDGE_FIELDS={'id','source','target','label','sourceHandle','targetHandle'}
CONFIG_FIELDS={
    'visit_profile':{'dwell_mode','skip_if_visited'},'connection_request':{'note','timeout_days'},
    'send_message':{'body','timeout_days'},'voice_note':{'script','fallback','timeout_days'},
    'like_last_post':{'max_post_age_days','skip_if_no_posts'},'if_connected':{'timeout_days'},
    'find_email':set(),'send_email':{'subject','body'},'if_email_available':set(),
    'add_tag':{'tag_name','auto_tag'},
    'has_data_in_column':{'condition_contract_version','field','operator','value_type','value'}}


def _hold():
    raise HTTPException(409,'Template graph snapshot fields need review')


def _plain(value):
    bounded_json(value)
    pending=[value]
    while pending:
        item=pending.pop()
        if type(item) is dict:
            if any(type(k) is not str for k in item):_hold()
            pending.extend(item.values())
        elif type(item) is list:pending.extend(item)
        elif type(item) is str:
            if '\x00' in item:_hold()
        elif type(item) in {int,Int64,float}:
            if not math.isfinite(item) or abs(item)>MAX_REVISION:_hold()
        elif item is not None and type(item) is not bool:_hold()
    if len(canonical_json(value).encode('utf-8'))>MAX_GRAPH_BYTES:_hold()


def _object(value,fields):
    if type(value) is not dict or set(value)-fields:_hold()


def _text(value,maximum):
    if type(value) is not str or len(value)>maximum or '\x00' in value:_hold()


def _number(value,bound):
    if type(value) not in {int,Int64,float} or not math.isfinite(value) or abs(value)>bound:_hold()


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value):_hold()


def _config(kind,value):
    _object(value,CONFIG_FIELDS[kind])
    if kind=='has_data_in_column':validate_config(value);return
    for key,item in value.items():
        if key in {'note','body','subject','script','fallback'}:_text(item,10000)
        elif key in {'skip_if_visited','skip_if_no_posts'}:
            if type(item) is not bool:_hold()
        elif key=='dwell_mode':
            if type(item) is not str or item not in {'quick','realistic','deep'}:_hold()
        elif key in {'timeout_days','max_post_age_days'}:
            if type(item) is not int or not 1<=item<=(30 if key=='timeout_days' else 365):_hold()


def _step(node,tree=False):
    _object(node,TREE_FIELDS if tree else NODE_FIELDS)
    _identifier(node.get('id'));kind=node.get('type')
    if type(kind) is not str or kind not in CONFIG_FIELDS:_hold()
    for key,maximum in [('title',200),('subtitle',1000)]:
        if key in node:_text(node[key],maximum)
    if 'delay_hours' in node and (type(node['delay_hours']) is not int or not 0<=node['delay_hours']<=8760):_hold()
    if 'delay_days' in node:
        days=node['delay_days']
        if type(days) not in {int,float} or not math.isfinite(days) or not 0<=days<=365 or not float(days*24).is_integer():_hold()
    if 'config' in node:_config(kind,node['config'])
    if 'position' in node:
        _object(node['position'],{'x','y'})
        if set(node['position'])!={'x','y'}:_hold()
        for item in node['position'].values():_number(item,1000000)
    if not tree:return
    for key in ('endsHere','isActionRequired'):
        if key in node and type(node[key]) is not bool:_hold()
    if 'steps' in node and (type(node['steps']) is not list or node['steps']):_hold()
    if 'branches' in node:
        _object(node['branches'],{'left','right'})
        for branch in node['branches'].values():
            _object(branch,{'condition','type','steps','endsHere'})
            if 'condition' in branch:_text(branch['condition'],80)
            if 'type' in branch and (type(branch['type']) is not str or branch['type'] not in {'danger','success'}):_hold()
            if 'endsHere' in branch and type(branch['endsHere']) is not bool:_hold()
            if 'steps' in branch:
                if type(branch['steps']) is not list:_hold()
                for step in branch['steps']:_step(step,True)


def project_graph(source: dict) -> dict:
    """Return only the original three graph fields after complete validation."""
    try:
        if type(source) is not dict:_hold()
        graph={key:source.get(key) for key in ('nodes','edges','tree')}
        _plain(graph)
        if any(type(graph[k]) is not list for k in graph):_hold()
        for node in graph['nodes']:_step(node)
        for node in graph['tree']:_step(node,True)
        for edge in graph['edges']:
            _object(edge,EDGE_FIELDS)
            _identifier(edge.get('source'));_identifier(edge.get('target'))
            if 'id' in edge:_identifier(edge['id'])
            for key in ('label','sourceHandle','targetHandle'):
                if key in edge and edge[key] is not None:_text(edge[key],80)
        compiled=compile_graph(graph)
        if ('compiled_dag' in source)!=('compiler_contract_version' in source):_hold()
        if 'compiled_dag' in source:
            if type(source['compiler_contract_version']) is not int or source['compiler_contract_version']!=1:_hold()
            _plain(source['compiled_dag'])
            if canonical_json(source['compiled_dag'])!=canonical_json(compiled['compiled_dag']):_hold()
        return deepcopy(graph)
    except HTTPException as exc:
        if exc.status_code==409:raise
        _hold()
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):_hold()
