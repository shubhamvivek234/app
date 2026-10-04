"""One bounded metadata GET, no retries, redirects, samples or verification POST."""
import json
import httpx
from outreach.core.voice_key_custody import PreparedKey
from outreach.core.voice_studio_review import REMOTE

MAX_METADATA_BYTES = 262144


async def metadata_call(request: dict) -> dict:
    credential, remote = request.get('credential'), request.get('voice_id')
    if (not isinstance(credential, PreparedKey) or not credential.matches() or not request['allowed']()
            or not isinstance(remote, str) or not REMOTE.fullmatch(remote) or remote.startswith('voice_mock_')):
        raise ValueError('Vendor metadata permission is unavailable')
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
        if not request['allowed']() or not credential.matches(): raise ValueError('Vendor read expired')
        async with client.stream('GET', 'https://api.elevenlabs.io/v1/voices/' + remote,
                headers={'xi-api-key': credential.value, 'Accept-Encoding': 'identity'}) as response:
            if (response.status_code != 200 or response.headers.get('content-encoding', 'identity').lower() != 'identity'
                    or response.headers.get('content-type', '').split(';')[0].lower() != 'application/json'):
                raise ValueError('Vendor metadata response is unavailable')
            body = bytearray()
            async for part in response.aiter_raw(chunk_size=16384):
                if len(body) + len(part) > MAX_METADATA_BYTES: raise ValueError('Vendor metadata exceeded its bounds')
                body.extend(part)
    result = json.loads(body)
    if not isinstance(result, dict): raise ValueError('Vendor metadata is unavailable')
    return result
