"""Pure original-wait graph/identity contracts."""
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.connection_waits import negative_region, native, read_operation, ConnectionWaitUnavailable


def graph():
    nodes=[{'id':'invite','type':'connection_request'},*[{'id':key,'type':'visit_profile'} for key in ('yes','no','merge')]]
    return DAGCompiler.validate_and_compile(nodes,[{'source':'invite','target':'yes','label':'accepted'},
        {'source':'invite','target':'no','label':'not accepted'},{'source':'yes','target':'merge'},{'source':'no','target':'merge'}])


def test_negative_region_excludes_shared_positive_merge_and_original_invite():
    source=graph();before=deepcopy(source)
    assert negative_region(source,'invite')==['no'] and source==before


@pytest.mark.parametrize('value',[{},None,{'id':'lead'}])
def test_missing_native_identity_cannot_be_adopted(value):
    with pytest.raises(ConnectionWaitUnavailable):native(value)


def test_native_type_and_original_worker_claim_are_bound():
    assert native({'_id':1})!=native({'_id':'1'})
    scope={'_id':'scope','revision':1};lead={'current_node_id':'no','execution_claim_token':'owner'}
    baseline=read_operation(scope,lead)
    assert baseline!=read_operation(scope,{**lead,'execution_claim_token':'replacement'})
    assert baseline!=read_operation({**scope,'revision':2},lead)
