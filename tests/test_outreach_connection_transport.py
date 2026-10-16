"""Adapter original-recipient contracts with synthetic HTTP responses only."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from outreach.engine.voyager_client import VoyagerClient
from outreach.core.request_guard import RequestDenied

TARGET='urn:li:fsd_profile:original'

@pytest.mark.asyncio
@pytest.mark.parametrize('shape,expected',[('positive',True),('empty',False),('partial',None),('nested_error',None),('error',None)])
async def test_observation_uses_original_urn_without_resolving_current_url(monkeypatch,shape,expected):
    envelope=SimpleNamespace(record_connection_fact=AsyncMock(return_value='receipt'))
    client=VoyagerClient(li_at='synthetic',jsession_id='ajax:synthetic',request_envelope=envelope)
    client.is_mock=False
    data={'elements':[] if shape=='empty' else [{'profileUrn':TARGET}],'paging':{'start':0,'count':1000,'total':0 if shape=='empty' else 1}}
    if shape=='partial':data={'elements':[],'paging':{'start':0,'count':1000,'total':2000}}
    if shape=='nested_error':data['paging']['statusCode']=500
    if shape=='error':data={'errors':[]}
    client._request=AsyncMock(return_value=httpx.Response(200,json=data))
    client._resolve_profile_urn=AsyncMock(side_effect=AssertionError('Original recipient cannot be re-resolved'))
    result=await client.observe_original_connection(TARGET)
    assert result=={'connected':expected,'request_id':'receipt'}
    envelope.record_connection_fact.assert_awaited_once_with(TARGET,kind='observed_connection',connected=expected)
    client._resolve_profile_urn.assert_not_awaited()
    assert client._request.call_args.args[1]=='GET'

@pytest.mark.asyncio
@pytest.mark.parametrize('recipient',[None,'https://linkedin.com/in/person','urn:li:company:123'])
async def test_unsupported_original_target_never_calls_transport(recipient):
    client=VoyagerClient(li_at='synthetic',jsession_id='ajax:synthetic',request_envelope=SimpleNamespace())
    client.is_mock=False;client._request=AsyncMock(side_effect=AssertionError('No request'))
    assert await client.observe_original_connection(recipient)=={'connected':None,'request_id':None}
    client._request.assert_not_awaited()

@pytest.mark.asyncio
async def test_unsupported_resolved_invite_identity_is_denied_before_post():
    envelope=SimpleNamespace(assert_content=lambda *a:None)
    client=VoyagerClient(li_at='synthetic',jsession_id='ajax:synthetic',request_envelope=envelope)
    client.is_mock=False;client._resolve_profile_urn=AsyncMock(return_value='urn:li:company:123')
    client._request=AsyncMock(side_effect=AssertionError('No POST'))
    with pytest.raises(RequestDenied):await client.send_connection_invite('https://linkedin.com/in/person')
    client._request.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('body',[[],{'error':{}},{'errors':[]}])
async def test_success_status_with_unsupported_invite_body_never_fabricates_confirmation(body):
    envelope=SimpleNamespace(assert_content=lambda *a:None,received_receipt={},record_connection_fact=AsyncMock())
    client=VoyagerClient(li_at='synthetic',jsession_id='ajax:synthetic',request_envelope=envelope)
    client.is_mock=False;client._resolve_profile_urn=AsyncMock(return_value=TARGET)
    client._request=AsyncMock(return_value=httpx.Response(201,json=body))
    result=await client.send_connection_invite(TARGET)
    assert result['status']=='failed'
    envelope.record_connection_fact.assert_not_awaited()
