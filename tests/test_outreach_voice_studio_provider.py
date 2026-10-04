"""Studio adapter wire bounds use local MockTransport only."""
import httpx
import pytest
from outreach.core.voice_studio_provider import studio_call
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_policy import MAX_PCM_BYTES, validate_audio
from outreach.core.voice_key_custody import prepare_key


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-key')


class Stream(httpx.AsyncByteStream):
    def __init__(self, value): self.value = value
    async def __aiter__(self): yield self.value


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['clone', 'preview', 'delete'])
async def test_one_fixed_provider_call(monkeypatch, operation):
    seen = []
    def handle(request):
        seen.append(request)
        body = b'{"voice_id":"remote","requires_verification":false}' if operation == 'clone' else b'{"status":"ok"}' if operation == 'delete' else bytes(32000)
        return httpx.Response(200, headers={'content-type': 'audio/pcm' if operation == 'preview' else 'application/json'}, stream=Stream(body))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    result = await studio_call({'operation': operation, 'voice_id': 'remote', 'name': 'My voice',
        'input': generate_mock_voice_wav(duration_s=20) if operation == 'clone' else b'Hi', 'credential': await prepare_key(), 'allowed': lambda: True})
    assert len(seen) == 1 and seen[0].url.host == 'api.elevenlabs.io'
    assert seen[0].headers['accept-encoding'] == 'identity'
    if operation == 'preview': assert validate_audio(result['audio'])['duration_ms'] == 1000
    elif operation == 'delete': assert result['deleted'] is True
    else: assert result['voice_id'] == 'remote'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['redirect', 'encoded', 'oversize', 'media', 'unconfirmed_delete', 'missing_verification'])
async def test_unsafe_response_has_no_retry(monkeypatch, failure):
    seen = []
    def handle(request):
        seen.append(request)
        body = bytes(MAX_PCM_BYTES + 1) if failure == 'oversize' else b'{}' if failure in {'unconfirmed_delete', 'missing_verification'} else bytes(32000)
        headers = {'content-type': 'text/html' if failure == 'media' else 'audio/pcm'}
        if failure == 'encoded': headers['content-encoding'] = 'gzip'
        return httpx.Response(302 if failure == 'redirect' else 200, headers=headers, stream=Stream(body))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    with pytest.raises(ValueError):
        await studio_call({'operation': 'delete' if failure == 'unconfirmed_delete' else 'clone' if failure == 'missing_verification' else 'preview',
            'voice_id': 'remote', 'name': 'My voice', 'input': generate_mock_voice_wav(duration_s=20) if failure == 'missing_verification' else b'Hi',
            'credential': await prepare_key(), 'allowed': lambda: True})
    assert len(seen) == 1
