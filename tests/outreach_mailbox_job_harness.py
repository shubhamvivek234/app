"""Fresh-process OAuth crash harness: disposable Mongo and loopback HTTP only."""
import asyncio
import os
from types import SimpleNamespace

from motor.motor_asyncio import AsyncIOMotorClient
from outreach.core import mailbox_connection as connection


async def main():
    endpoint = os.environ["OUTREACH_DRILL_OAUTH_URL"]
    if not endpoint.startswith("http://127.0.0.1:"):
        raise RuntimeError("Crash harness permits loopback transport only")
    connection._provider_config = lambda _: SimpleNamespace(provider="gmail", client_id="local", client_secret="local",
        redirect_uri="https://local.invalid/callback", scopes=(), token_url=endpoint)
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    try:
        result = await connection.complete_connection_job(client[os.environ["OUTREACH_DRILL_DB"]], "w", "job")
        print(result["status"], flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
