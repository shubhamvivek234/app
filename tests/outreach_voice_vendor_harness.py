"""Fresh-process SIGKILL harness; only loopback GET and a test custody stand-in."""
import asyncio
import os
import sys
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv('UNRAVLER_VENDOR_DRILL') != '1': raise RuntimeError('Test-only process')


class LoopbackTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if request.url.host != 'api.elevenlabs.io' or request.url.path != '/v1/voices/original-remote' or request.method != 'GET':
            raise AssertionError('External egress denied')
        endpoint = httpx.URL(os.environ['UNRAVLER_VENDOR_ENDPOINT'])
        if endpoint.scheme != 'http' or endpoint.host != '127.0.0.1': raise AssertionError('Non-loopback test destination denied')
        request.url = endpoint
        return await super().handle_async_request(request)


async def main():
    from outreach.core import suppression, voice_key_custody
    from outreach.core.authorization import canonical_hash
    from outreach.core.voice_vendor_evidence import VoiceVendorEvidence
    from outreach.core.voice_vendor_provider import metadata_call
    from tests.test_outreach_voice_vendor_evidence import KEY, EVIDENCE
    database, voice, expected, stage, checkpoint = sys.argv[1:6]
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client[database]
    async def key(**kwargs):
        # This drill validates crash/GET ordering; KMS is separately tested.
        config = voice_key_custody.capture_configuration()
        assert config.digest == kwargs['expected_digest'] and config.source == kwargs['expected_source']
        return voice_key_custody.PreparedKey(KEY, config, canonical_hash(KEY))
    voice_key_custody.prepare_key = key
    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: original_client(**kw, transport=LoopbackTransport())
    async def pause():
        await db.drill_controls.update_one({'_id': checkpoint}, {'$set': {'checkpoint': stage}}, upsert=True)
        await asyncio.Event().wait()
    original_control = suppression.mutate_suppression
    async def control(database, workspace, operation):
        result = await original_control(database, workspace, operation)
        if (stage, operation.__name__) in {('after_prepare', 'prepare'), ('after_possible', 'authorize'), ('after_receipt', 'save')}:
            await pause()
        return result
    suppression.mutate_suppression = control
    async def provider(request):
        result = await metadata_call(request)
        if stage == 'after_response': await pause()
        return result
    try:
        await VoiceVendorEvidence(db).capture('w', voice, 'operator', EVIDENCE, expected,
            workers_drained=True, provider=provider)
    finally: client.close()


asyncio.run(main())
