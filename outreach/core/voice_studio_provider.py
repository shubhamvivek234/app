"""Exactly one bounded ElevenLabs request; no redirects/retries/mock fallback."""
import logging
logger = logging.getLogger(__name__)
import json
import re
import httpx
from outreach.core.voice_policy import MAX_PCM_BYTES, VOICE_POLICY, pcm_to_wav, validate_audio
from outreach.core.voice_key_custody import PreparedKey


async def studio_call(request: dict) -> dict:
    operation = request['operation']
    remote = request.get('voice_id')
    credential = request.get('credential')
    if not isinstance(credential, PreparedKey) or not credential.matches():
        raise ValueError('Studio provider configuration changed')
    if operation not in {'clone', 'preview', 'delete'} or not request['allowed']():
        raise ValueError('Studio call is unavailable')
    if operation != 'clone' and (not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', remote)):
        raise ValueError('Invalid voice identity')
    headers = {'xi-api-key': credential.value, 'Accept-Encoding': 'identity'}
    options = {}
    if operation == 'clone':
        validate_audio(request['input'])
        method, path = 'POST', 'voices/add'
        options = {'data': {'name': request['name']}, 'files': {'files': ('sample.wav', request['input'], 'audio/wav')}}
    elif operation == 'preview':
        method, path = 'POST', 'text-to-speech/' + remote
        options = {'params': {'output_format': VOICE_POLICY['output_format']}, 'json': {
            'text': request['input'].decode(), 'model_id': VOICE_POLICY['model_id'],
            'voice_settings': {'stability': .5, 'similarity_boost': .8}}}
    else:
        method, path = 'DELETE', 'voices/' + remote
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
        if not request['allowed']() or not credential.matches():
            raise ValueError('Studio call expired')
        async with client.stream(method, 'https://api.elevenlabs.io/v1/' + path, headers=headers, **options) as response:
            if response.status_code not in ({200, 201} if operation == 'clone' else {200} if operation == 'delete' else {200}):
                raise ValueError('Studio outcome needs review')
            if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise ValueError('Encoded Studio responses are unavailable')
            if operation == 'preview' and response.headers.get('content-type', '').split(';')[0].lower() not in {'audio/pcm', 'audio/l16', 'application/octet-stream'}:
                raise ValueError('Unexpected audio format')
            body = bytearray()
            bound = MAX_PCM_BYTES if operation == 'preview' else 65536
            async for part in response.aiter_raw(chunk_size=16384):
                if len(body) + len(part) > bound:
                    raise ValueError('Studio response is outside its bounds')
                body.extend(part)
    if operation == 'clone':
        result = json.loads(body)
        if type(result.get('requires_verification')) is not bool:
            raise ValueError('Clone verification receipt is unavailable')
        return {'voice_id': result['voice_id'], 'requires_verification': result['requires_verification']}
    if operation == 'delete':
        if json.loads(body).get('status') != 'ok':
            raise ValueError('Voice deletion was not confirmed')
        return {'deleted': True}
    return {'audio': pcm_to_wav(bytes(body))}
