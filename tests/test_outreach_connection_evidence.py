"""Original immutable-recipient connection observations; no provider calls."""
from copy import deepcopy
import pytest
from outreach.core.connection_evidence import recipient_key, parse_connection_page

TARGET='urn:li:fsd_profile:original'

def page(elements=None,**paging):
    values=[{'profileUrn':TARGET}] if elements is None else elements
    return {'elements':values,'paging':{'start':0,'count':1000,'total':len(values),**paging}}

@pytest.mark.parametrize('value',[None,[],True,'urn:li:company:123','https://linkedin.com/in/original','urn:li:member:abc','urn:li:fsd_profile:bad space'])
def test_only_supported_immutable_person_recipient_ids_are_authority(value):
    assert recipient_key(value) is None

def test_profile_prefix_alias_is_typed_but_numeric_member_namespace_is_separate():
    assert recipient_key(TARGET)==recipient_key('urn:li:fs_miniProfile:original')
    assert recipient_key('urn:li:member:123')!=recipient_key('urn:li:fsd_profile:123')

def test_partial_page_can_establish_exact_presence_but_never_absence():
    assert parse_connection_page(page(total=5000),TARGET) is True
    assert parse_connection_page(page([{'profileUrn':'urn:li:fsd_profile:other'}],total=5000),TARGET) is None
    assert parse_connection_page(page([]),TARGET) is False

def test_vanity_match_or_contradictory_identity_never_establishes_presence():
    assert parse_connection_page(page([{'profileUrn':'urn:li:fsd_profile:other','publicIdentifier':'original'}]),TARGET) is False
    assert parse_connection_page(page([{'profileUrn':TARGET,'memberUrn':'urn:li:member:123'}]),TARGET) is None

@pytest.mark.parametrize('fault',['error','errors','shape','record','missing_identity','duplicate','bool_total','negative_total','bool_start','later_page','missing_paging','contradictory_total','too_many'])
def test_malformed_error_and_incomplete_pages_remain_unknown(fault):
    data=page()
    if fault in {'error','errors'}:data[fault]={}
    elif fault=='shape':data['elements']={}
    elif fault=='record':data['elements']=[None]
    elif fault=='missing_identity':data['elements']=[{'publicIdentifier':'original'}]
    elif fault=='duplicate':data['elements']*=2;data['paging']['total']=2
    elif fault=='bool_total':data['paging']['total']=True
    elif fault=='negative_total':data['paging']['total']=-1
    elif fault=='bool_start':data['paging']['start']=False
    elif fault=='later_page':data['paging']['start']=1000
    elif fault=='missing_paging':data.pop('paging')
    elif fault=='contradictory_total':data['paging']['total']=0
    else:data['elements']=[{'profileUrn':f'urn:li:fsd_profile:id{i}'} for i in range(1001)];data['paging']['total']=1001
    original=deepcopy(data)
    assert parse_connection_page(data,TARGET) is None
    assert data==original

@pytest.mark.parametrize('where,key',[('paging','statusCode'),('paging','error'),('mini','statusCode'),('mini','errors'),('mini','unknown')])
def test_nested_error_and_unsupported_metadata_cannot_establish_positive(where,key):
    data=page([{'miniProfile':{'entityUrn':TARGET}}])
    target=data['paging'] if where=='paging' else data['elements'][0]['miniProfile']
    target[key]=500
    assert parse_connection_page(data,TARGET) is None


@pytest.mark.parametrize('where',['row','mini'])
@pytest.mark.parametrize('value',[{'errors':['denied']},[],True,None,'x'*201])
def test_optional_public_identifier_is_bounded_text_not_hidden_error_metadata(where,value):
    data=page([{'entityUrn':TARGET}] if where=='row' else [{'miniProfile':{'entityUrn':TARGET}}])
    record=data['elements'][0] if where=='row' else data['elements'][0]['miniProfile']
    record['publicIdentifier']=value
    assert parse_connection_page(data,TARGET) is None
