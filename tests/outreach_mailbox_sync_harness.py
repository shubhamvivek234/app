"""Fresh-process production sync over actual loopback TCP; never a live provider."""
import asyncio
import os
from urllib.parse import urlparse

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from outreach.core import mailbox_sync, mailbox_sync_jobs


async def main():
    target = os.environ['OUTREACH_DRILL_SYNC_URL']
    if urlparse(target).hostname != '127.0.0.1': raise RuntimeError('Loopback required')
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', tz_aware=True)
    db = client[os.environ['OUTREACH_DRILL_DB']]
    actual_client = httpx.AsyncClient
    class LocalTransport:
        async def __aenter__(self):
            self.client = actual_client(timeout=25, follow_redirects=False)
            return self
        async def __aexit__(self, *_): await self.client.aclose()
        def stream(self, method, url, **kwargs):
            if not url.startswith(mailbox_sync.GMAIL_BASE + '/'): raise RuntimeError('Expected Gmail test adapter')
            return self.client.stream(method, target, **kwargs)
    mailbox_sync.httpx.AsyncClient = lambda **_: LocalTransport()
    if os.getenv('OUTREACH_DRILL_SYNC_PAUSE') == 'received':
        async def pause(*args):
            print('received', flush=True)
            await asyncio.Future()
        mailbox_sync_jobs.finish_job = pause
    try:
        result = await mailbox_sync_jobs.execute_job(db, 'w', os.environ['OUTREACH_DRILL_JOB'])
        print(result['status'], flush=True)
    finally: client.close()


if __name__ == '__main__': asyncio.run(main())
