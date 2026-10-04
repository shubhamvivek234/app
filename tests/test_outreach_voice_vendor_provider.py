"""Strict one-GET transport tested only over local MockTransport."""
import json
import httpx
import pytest
from outreach.core import voice_key_custody
from outreach.core.voice_vendor_provider import metadata_call, MAX_METADATA_BYTES
from tests.test_outreach_voice_vendor_evidence import METADATA
from tests.test_outreach_voice_studio_provider import Stream, configured

pytestmark = pytest.mark.asyncio


async def test_one_fixed_bounded_metadata_get(monkeypatch):
    seen = []; original = httpx.AsyncClient
    def handle(request):
        seen.append(request)
        return httpx.Response(200, headers={'content-type': 'application/json'}, stream=Stream(json.dumps(METADATA).encode()))
    def client(**kw):
        assert kw == {'timeout': 25, 'follow_redirects': False, 'trust_env': False}
        return original(**kw, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    result = await metadata_call({'voice_id': 'original-remote', 'credential': await voice_key_custody.prepare_key(),
        'allowed': lambda: True})
    assert result == METADATA and len(seen) == 1
    assert seen[0].method == 'GET' and str(seen[0].url) == 'https://api.elevenlabs.io/v1/voices/original-remote'
    assert seen[0].headers['accept-encoding'] == 'identity'


@pytest.mark.parametrize('failure', ['redirect', 'denied', 'encoded', 'media', 'oversize', 'invalid', 'list'])
async def test_metadata_failures_never_retry(monkeypatch, failure):
    seen = []; original = httpx.AsyncClient
    def handle(request):
        seen.append(request)
        value = b'x' * (MAX_METADATA_BYTES + 1) if failure == 'oversize' else b'[]' if failure == 'list' else b'invalid' if failure == 'invalid' else b'{}'
        return httpx.Response(302 if failure == 'redirect' else 403 if failure == 'denied' else 200,
            headers={'content-type': 'text/html' if failure == 'media' else 'application/json',
                'content-encoding': 'gzip' if failure == 'encoded' else 'identity'}, stream=Stream(value))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    with pytest.raises(ValueError): await metadata_call({'voice_id': 'remote', 'credential': await voice_key_custody.prepare_key(),
        'allowed': lambda: True})
    assert len(seen) == 1


@pytest.mark.parametrize('remote', ['../user', 'voice_mock_x', '', None, ['remote']])
async def test_unbounded_or_mock_reference_has_no_request(monkeypatch, remote):
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: pytest.fail('No client'))
    with pytest.raises(ValueError): await metadata_call({'voice_id': remote, 'credential': await voice_key_custody.prepare_key(),
        'allowed': lambda: True})


async def test_permission_and_config_rechecked_after_client_entry(monkeypatch):
    key = await voice_key_custody.prepare_key()
    class Client:
        async def __aenter__(self):
            monkeypatch.setenv('ELEVENLABS_API_KEY', 'replacement-key'); return self
        async def __aexit__(self, *args): pass
        def stream(self, *args, **kw): pytest.fail('No request')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: Client())
    with pytest.raises(ValueError): await metadata_call({'voice_id': 'remote', 'credential': key, 'allowed': lambda: True})
