"""Opt-in isolated Celery process drill, with provider egress forced to loopback."""
import asyncio
import os

import httpx
from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv("UNRAVLER_VOICE_DRILL") != "1":
    raise RuntimeError("Voice drill is test-only")

app = Celery("voice_drill", broker="redis://127.0.0.1:6389/15")
app.conf.update(task_default_queue=os.environ["UNRAVLER_DRILL_QUEUE"], task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3, "global_keyprefix": os.environ["UNRAVLER_DRILL_QUEUE"] + ":"})


class LoopbackTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if request.url.host != "api.elevenlabs.io" or request.method != "POST":
            raise AssertionError("External egress is forbidden")
        request.url = httpx.URL(os.environ["UNRAVLER_DRILL_ENDPOINT"])
        return await super().handle_async_request(request)


async def execute(job_id, workspace):
    from outreach.core import suppression
    from outreach.core.voice_preparation import VoicePreparation
    from outreach.core.voice_provider import generate_campaign_voice
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True)
    db = client[os.environ["UNRAVLER_DRILL_DB"]]
    original_client = httpx.AsyncClient
    original_mutate = suppression.mutate_suppression
    httpx.AsyncClient = lambda **kwargs: original_client(**kwargs, transport=LoopbackTransport())
    control = await db.drill_controls.find_one({"_id": job_id})
    await db.drill_controls.update_one({"_id": job_id}, {"$inc": {"deliveries": 1}})
    async def checkpoint(stage):
        if control.get("halt_at") == stage:
            await db.drill_controls.update_one({"_id": job_id}, {"$set": {"checkpoint": stage}})
            await asyncio.Event().wait()
    async def mutate(database, scope, operation):
        value = await original_mutate(database, scope, operation)
        if isinstance(value, dict) and value.get("status") == "claimed":
            await checkpoint("after_claim")
        return value
    suppression.mutate_suppression = mutate
    async def generate(binding):
        await checkpoint("before_call")
        try:
            result = await generate_campaign_voice(binding)
        except Exception as exc:
            await db.drill_controls.update_one({"_id": job_id}, {"$set": {"provider_error_type": type(exc.__cause__).__name__}})
            raise
        await checkpoint("after_call")
        return result
    try:
        result = await VoicePreparation(db).run(workspace, job_id, generator=generate)
        await db.drill_controls.update_one({"_id": job_id}, {"$set": {"result": result["status"]}})
        await checkpoint("after_commit")
        return result
    finally:
        httpx.AsyncClient = original_client
        suppression.mutate_suppression = original_mutate
        client.close()


@app.task(name="voice_drill.prepare")
def prepare(job_id, workspace):
    return asyncio.run(execute(job_id, workspace))
