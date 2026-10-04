"""Fresh process for local SIGKILL tests; transport only permits loopback."""
import asyncio
import os
import sys
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv('UNRAVLER_STUDIO_DRILL') != '1':
    raise RuntimeError('Test-only process')


class LoopbackTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if request.url.host != 'api.elevenlabs.io' or request.url.path != '/v1/voices/add' or request.method != 'POST':
            raise AssertionError('External egress denied')
        endpoint = httpx.URL(os.environ['UNRAVLER_STUDIO_ENDPOINT'])
        if endpoint.scheme != 'http' or endpoint.host != '127.0.0.1':
            raise AssertionError('Non-loopback test destination denied')
        request.url = endpoint
        return await super().handle_async_request(request)


async def main():
    from outreach.core.voice_studio import VoiceStudio
    from outreach.core.voice_studio_provider import studio_call
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True)
    db = client[sys.argv[1]]
    job_id, stage = sys.argv[2:4]
    service = VoiceStudio(db)
    original = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: original(**kw, transport=LoopbackTransport())
    async def pause():
        await db.drill_controls.update_one({'_id': job_id}, {'$set': {'checkpoint': stage}}, upsert=True)
        await asyncio.Event().wait()
    async def provider(request):
        result = await studio_call(request)
        if stage == 'after_response': await pause()
        return result
    if stage == 'after_receipt':
        async def finish(*args): await pause()
        service._finish = finish
    try:
        await service.run('w', job_id, provider=provider)
    finally:
        client.close()

asyncio.run(main())
