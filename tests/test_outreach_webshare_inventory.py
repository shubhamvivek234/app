"""Inventory reads are bounded and source-fenced; all transport is local."""
from unittest.mock import AsyncMock
import time

import httpx
import pytest

from outreach.core.proxy_manager import JITProxyManager, ProxyProvisioningError
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_webshare_custody import installed


PLAN = {'id': 42, 'status': 'active', 'proxy_type': 'dedicated', 'proxy_subtype': 'isp', 'automatic_refresh_frequency': 0}
PROXY = {'id': 'd-1', 'valid': True, 'country_code': 'US', 'proxy_address': '5.6.7.8',
    'port': 8080, 'username': 'private-user', 'password': 'private:pass@word'}


def fake_client(monkeypatch, handler):
    from outreach.core import webshare_inventory
    original = httpx.AsyncClient
    calls = []
    def streamed(request):
        reply = handler(request)
        if not reply.is_stream_consumed:
            return reply
        return httpx.Response(reply.status_code, headers=reply.headers, stream=httpx.ByteStream(reply.content))
    def create(**kwargs):
        calls.append(kwargs)
        return original(transport=httpx.MockTransport(streamed), trust_env=False, follow_redirects=False)
    monkeypatch.setattr(webshare_inventory, 'create_safe_client', create)
    return calls


def response(request):
    assert request.headers['authorization'] == 'Token private-webshare-key'
    assert request.method == 'GET'
    assert request.url.host == 'proxy.webshare.io'
    results = [PLAN] if request.url.path.endswith('/subscription/plan/') else [PROXY]
    return httpx.Response(200, json={'results': results, 'next': None})


@pytest.mark.asyncio
async def test_scoped_new_selection_seals_tenant_asset_password(scoped, monkeypatch):
    from outreach.core.proxy_custody import prepare_proxy
    await installed(monkeypatch)
    monkeypatch.setattr('outreach.core.proxy_manager.encrypt', lambda _: pytest.fail('No temporary Fernet in scoped mode'))
    calls = fake_client(monkeypatch, response)
    proxy = await JITProxyManager().order_static_residential_proxy('US', workspace_id='w')
    assert proxy.password_enc.startswith('uc1:')
    assert 'uc1:' not in repr(proxy) and 'private:pass@word' not in repr(proxy)
    assert proxy.custody_workspace_id == 'w' and proxy.credential_generation
    prepared = await prepare_proxy(proxy, 'w')
    assert prepared.url == 'http://private-user:private%3Apass%40word@5.6.7.8:8080'
    from outreach.core.credential_custody import CustodyUnavailable
    with pytest.raises(CustodyUnavailable): await prepare_proxy(proxy, 'other')
    assert len(calls) == 1 and calls[0]['preflight']()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['workspace', 'mixed', 'override', 'missing', 'legacy_iproyal'])
async def test_unproven_scoped_selection_denies_before_open_or_http(scoped, monkeypatch, failure):
    await installed(monkeypatch)
    opened = AsyncMock(side_effect=AssertionError('Denied before opening'))
    monkeypatch.setattr(scoped, 'open', opened)
    calls = fake_client(monkeypatch, lambda _: pytest.fail('No HTTP'))
    if failure == 'mixed': monkeypatch.setenv('WEBSHARE_API_KEY', 'plaintext-key')
    if failure == 'missing': monkeypatch.delenv('OUTREACH_WEBSHARE_API_KEY_ENC')
    if failure == 'legacy_iproyal': monkeypatch.setenv('OUTREACH_PROXY_PROVIDER', 'iproyal')
    manager = JITProxyManager(api_key='override' if failure == 'override' else None)
    with pytest.raises(ProxyProvisioningError):
        await manager.order_static_residential_proxy('US', workspace_id=None if failure == 'workspace' else 'w')
    assert not calls
    opened.assert_not_awaited()


@pytest.mark.asyncio
async def test_rotation_between_pages_stops_without_second_get(scoped, monkeypatch):
    await installed(monkeypatch)
    requests=[]
    def changed(request):
        requests.append(request)
        monkeypatch.setenv('OUTREACH_WEBSHARE_KEY_GENERATION', 'replacement')
        return response(request)
    fake_client(monkeypatch, changed)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager().order_static_residential_proxy('US', workspace_id='w')
    assert len(requests)==1


@pytest.mark.asyncio
async def test_rotation_during_asset_sealing_returns_no_asset(scoped, monkeypatch):
    await installed(monkeypatch)
    fake_client(monkeypatch, response)
    original=scoped.seal
    async def changed(*args):
        result=await original(*args)
        monkeypatch.setenv('OUTREACH_WEBSHARE_KEY_GENERATION', 'replacement')
        return result
    monkeypatch.setattr(scoped,'seal',changed)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager().order_static_residential_proxy('US', workspace_id='w')


@pytest.mark.asyncio
async def test_mode_change_between_initial_read_and_capture_denies_before_open(scoped, monkeypatch):
    from outreach.core import session_custody
    await installed(monkeypatch)
    original = session_custody.custody_mode
    reads = []
    def switched():
        reads.append(True)
        return 'legacy_fernet' if len(reads) == 1 else original()
    monkeypatch.setattr(session_custody, 'custody_mode', switched)
    opened = AsyncMock(side_effect=AssertionError('No mixed-mode key opening'))
    monkeypatch.setattr(scoped, 'open', opened)
    calls = fake_client(monkeypatch, lambda _:pytest.fail('No mixed-mode HTTP'))
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager().order_static_residential_proxy('US', workspace_id='w')
    opened.assert_not_awaited()
    assert not calls


@pytest.mark.asyncio
async def test_scoped_to_mock_cutover_cannot_return_a_legacy_mock(monkeypatch):
    from outreach.core import session_custody
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setenv('WEBSHARE_API_KEY','mock')
    monkeypatch.delenv('OUTREACH_WEBSHARE_API_KEY_ENC',raising=False)
    monkeypatch.delenv('OUTREACH_WEBSHARE_KEY_GENERATION',raising=False)
    reads=[]
    def switched():
        reads.append(True)
        return 'kms_v1' if len(reads)==1 else 'legacy_fernet'
    monkeypatch.setattr(session_custody,'custody_mode',switched)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager().order_static_residential_proxy('US',workspace_id='w')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['oversize', 'encoding', 'redirect', 'bad_json', 'bad_results', 'api_error'])
async def test_bad_response_is_bounded_and_sanitized(monkeypatch, failure):
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    def bad(request):
        if failure=='oversize': return httpx.Response(200,content=b'x'*(webshare_inventory.MAX_RESPONSE_BYTES+1))
        if failure=='encoding': return httpx.Response(200,content=b'private-key',headers={'Content-Encoding':'gzip'})
        if failure=='redirect': return httpx.Response(302,headers={'Location':'https://elsewhere.invalid/private'})
        if failure=='bad_json': return httpx.Response(200,content=b'private-key-invalid-json')
        if failure=='bad_results': return httpx.Response(200,json={'results':'private-key'})
        return httpx.Response(200,json={'error':'private-key','results':[]})
    fake_client(monkeypatch,bad)
    with pytest.raises(ProxyProvisioningError) as error:
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert 'private-key' not in str(error.value) and 'elsewhere' not in str(error.value)


@pytest.mark.asyncio
async def test_request_allowance_covers_all_plan_and_proxy_pages(monkeypatch):
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setattr(webshare_inventory,'MAX_REQUESTS',3)
    requests=[]
    def pages(request):
        requests.append(request)
        values=[{**PLAN,'id':n} for n in (1,2,3)] if request.url.path.endswith('/subscription/plan/') else []
        return httpx.Response(200,json={'results':values,'next':None})
    fake_client(monkeypatch,pages)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert len(requests)==3


@pytest.mark.asyncio
async def test_pagination_does_not_follow_vendor_next_url(monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    requests=[]
    def pages(request):
        requests.append(request)
        if request.url.path.endswith('/subscription/plan/') and request.url.params['page']=='1':
            return httpx.Response(200,json={'results':[], 'next':'https://private.invalid/key'})
        values=[PLAN] if request.url.path.endswith('/subscription/plan/') else [PROXY]
        return httpx.Response(200,json={'results':values,'next':None})
    fake_client(monkeypatch,pages)
    proxy=await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert proxy.provider=='webshare_plan'
    assert len(requests)==3 and all(request.url.host=='proxy.webshare.io' for request in requests)


@pytest.mark.asyncio
async def test_expired_inventory_preflight_denies_before_transport(monkeypatch):
    from outreach.core import webshare_inventory, webshare_key_custody
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    key=await webshare_key_custody.prepare_key(override='private-key')
    calls=fake_client(monkeypatch,lambda _:pytest.fail('Expired before HTTP'))
    read=webshare_inventory.InventoryRead(key, deadline=time.monotonic()-1)
    with pytest.raises(ProxyProvisioningError):
        async with read:
            await read.pages('/subscription/plan/',{})
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'proxy_address':'127.0.0.1'},{'proxy_address':'evil.invalid'},{'username':'x'*257},{'password':'x'*4097},{'port':True}])
async def test_invalid_returned_proxy_cannot_be_selected(monkeypatch, change):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    def bad(request):
        values=[PLAN] if request.url.path.endswith('/subscription/plan/') else [{**PROXY,**change}]
        return httpx.Response(200,json={'results':values,'next':None})
    fake_client(monkeypatch,bad)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')


@pytest.mark.asyncio
async def test_actual_stream_without_length_is_stopped_at_byte_limit(monkeypatch):
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(3):
                yield b'x'*(webshare_inventory.MAX_RESPONSE_BYTES//2)
    requests=[]
    def large(request):
        requests.append(request)
        return httpx.Response(200,stream=Chunks())
    fake_client(monkeypatch,large)
    with pytest.raises(ProxyProvisioningError,match='bound'):
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert len(requests)==1


@pytest.mark.asyncio
async def test_slow_body_obeys_whole_operation_deadline(monkeypatch):
    import asyncio
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setattr(webshare_inventory,'TOTAL_TIMEOUT',.01)
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(.05)
            yield b'{}'
    requests=[]
    def slow(request):
        requests.append(request)
        return httpx.Response(200,stream=Slow())
    fake_client(monkeypatch,slow)
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert len(requests)==1


@pytest.mark.asyncio
async def test_page_limit_is_distinct_from_total_request_limit(monkeypatch):
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setattr(webshare_inventory,'MAX_PAGES',2)
    requests=[]
    def many(request):
        requests.append(request)
        return httpx.Response(200,json={'results':[],'next':'untrusted-next-url'})
    fake_client(monkeypatch,many)
    with pytest.raises(ProxyProvisioningError,match='page allowance'):
        await JITProxyManager(api_key='private-key').order_static_residential_proxy('US')
    assert len(requests)==2


@pytest.mark.asyncio
async def test_late_client_close_rotation_returns_no_selected_asset(monkeypatch):
    from outreach.core import webshare_inventory
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setenv('WEBSHARE_API_KEY','private-webshare-key')
    import json
    def handle(request):
        values=[PLAN] if request.url.path.endswith('/subscription/plan/') else [PROXY]
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps({'results':values,'next':None}).encode()))
    class RotatingClient(httpx.AsyncClient):
        async def __aexit__(self,*args):
            await super().__aexit__(*args)
            monkeypatch.setenv('WEBSHARE_API_KEY','replacement')
    monkeypatch.setattr(webshare_inventory,'create_safe_client',lambda **kwargs:
        RotatingClient(transport=httpx.MockTransport(handle),trust_env=False,follow_redirects=False))
    with pytest.raises(ProxyProvisioningError):
        await JITProxyManager().order_static_residential_proxy('US')


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['dns','tls_write'])
async def test_captured_key_change_blocks_socket_or_write(monkeypatch,boundary):
    import socket
    from outreach.core import webshare_inventory,webshare_key_custody
    from outreach.core.safe_transport import PinnedAsyncNetworkBackend,FencedAsyncNetworkStream,SSRFSecurityError
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setenv('WEBSHARE_API_KEY','private-key')
    key=await webshare_key_custody.prepare_key()
    read=webshare_inventory.InventoryRead(key,deadline=time.monotonic()+30)
    if boundary=='dns':
        backend=PinnedAsyncNetworkBackend(preflight=read.matches)
        def resolve(*args,**kwargs):
            monkeypatch.setenv('WEBSHARE_API_KEY','replacement')
            return [(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',('8.8.8.8',443))]
        monkeypatch.setattr(socket,'getaddrinfo',resolve)
        connect=AsyncMock()
        monkeypatch.setattr(backend._anyio_backend,'connect_tcp',connect)
        with pytest.raises(SSRFSecurityError):await backend.connect_tcp('proxy.webshare.io',443)
        connect.assert_not_awaited()
    else:
        raw=AsyncMock();tls=AsyncMock();raw.start_tls.return_value=tls
        wrapped=await FencedAsyncNetworkStream(raw,read.matches).start_tls(None)
        monkeypatch.setenv('WEBSHARE_API_KEY','replacement')
        with pytest.raises(SSRFSecurityError):await wrapped.write(b'Authorization: Token private-key')
        tls.write.assert_not_awaited();tls.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('rotate',[False,True])
async def test_production_reader_over_owned_loopback_gets_only(monkeypatch,rotate):
    import asyncio,json
    from outreach.core import webshare_inventory
    from outreach.core.safe_transport import create_safe_client
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER','webshare')
    monkeypatch.setenv('WEBSHARE_API_KEY','private-key')
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
    requests=[];tasks=set()
    async def handle(reader,writer):
        task=asyncio.current_task();tasks.add(task)
        try:
            request=await reader.readuntil(b'\r\n\r\n');requests.append(request)
            assert request.startswith(b'GET ') and b'Authorization: Token private-key' in request
            values=[PLAN] if b'/subscription/plan/' in request else [PROXY]
            body=json.dumps({'results':values,'next':None}).encode()
            if rotate:monkeypatch.setenv('WEBSHARE_API_KEY','replacement')
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
            await writer.drain()
        finally:
            writer.close();await writer.wait_closed();tasks.discard(task)
    server=await asyncio.start_server(handle,'127.0.0.1',0)
    port=server.sockets[0].getsockname()[1]
    monkeypatch.setattr(webshare_inventory,'API_URL',f'http://127.0.0.1:{port}/api/v2')
    monkeypatch.setattr(webshare_inventory,'create_safe_client',lambda **kwargs:
        create_safe_client(allow_private_for_tests=True,**kwargs))
    try:
        if rotate:
            with pytest.raises(ProxyProvisioningError):await JITProxyManager().order_static_residential_proxy('US')
            assert len(requests)==1
        else:
            proxy=await JITProxyManager().order_static_residential_proxy('US')
            assert proxy.proxy_id=='webshare:42:d-1' and len(requests)==2
    finally:
        server.close();await server.wait_closed()
        if tasks:await asyncio.gather(*list(tasks))
