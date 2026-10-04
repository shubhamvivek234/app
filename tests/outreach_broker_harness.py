"""Isolated crash-drill worker. Never starts the application Celery runtime."""
import asyncio
import os
from datetime import datetime, timezone

from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv("UNRAVLER_BROKER_DRILL") != "1":
    raise RuntimeError("This worker is restricted to explicit local tests")
DATABASE = os.environ["UNRAVLER_DRILL_DB"]
QUEUE = os.environ["UNRAVLER_DRILL_QUEUE"]
if not DATABASE.startswith("test_unravler_broker_") or not QUEUE.startswith("unravler_drill_"):
    raise RuntimeError("Isolated names are required")

app = Celery("unravler_crash_drill", broker="redis://127.0.0.1:6389/15")
app.conf.update(task_default_queue=QUEUE, task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, broker_transport_options={"visibility_timeout": 3, "global_keyprefix": QUEUE + ":"},
    task_ignore_result=True)


@app.task(bind=True, name="celery_workers.tasks.outreach.execute_sequence_job")
def execute(self, workspace_id: str, job_id: str) -> dict:
    return asyncio.run(run(workspace_id, job_id, bool(self.request.delivery_info.get("redelivered"))))


async def run(workspace_id: str, job_id: str, redelivered: bool) -> dict:
    # No application settings, credentials, HTTP client or real provider factory.
    from outreach.core.execution_outbox import ExecutionOutbox
    from outreach.tasks import sequence_dispatch
    sequence_dispatch.sequence_dispatch_enabled = lambda: True
    sequence_dispatch.is_shutting_down = lambda: False
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True)
    db = client[DATABASE]
    try:
        await db.drill_controls.update_one({"_id": job_id}, {"$inc": {"deliveries": 1}, "$set": {"redelivered": redelivered}})
        async def fake_executor(lead_id, database, **kwargs):
            job = await database.outreach_sequence_jobs.find_one({"workspace_id": workspace_id, "_id": job_id})
            control = await database.drill_controls.find_one({"_id": job_id})
            outbox = ExecutionOutbox(database)
            owner = job["owner"]
            async def checkpoint(stage):
                await database.drill_controls.update_one({"_id": job_id}, {"$set": {"checkpoint": stage}})
                if control.get("halt_at") == stage and not control.get("resume"):
                    await asyncio.sleep(600)  # Parent test kills this worker process.
            if not await outbox.claim(workspace_id, job["intent_id"], owner):
                intent = await database.outreach_intents.find_one({"_id": job["intent_id"]})
                return {"status": "confirmed" if intent["status"] == "executed" else "action_uncertain"}
            await checkpoint("before_submission")
            if not await outbox.begin_submission(workspace_id, job["intent_id"], owner):
                return {"status": "action_busy"}
            await checkpoint("after_possible")
            await database.drill_controls.update_one({"_id": job_id}, {"$inc": {"fake_provider_calls": 1}})
            await checkpoint("after_call")
            await outbox.finish(workspace_id, job["intent_id"], owner, "provider_accepted", provider_message_id="fake-message")
            await checkpoint("after_accepted")
            return {"status": "confirmed"}
        return await sequence_dispatch.execute_job(db, workspace_id, job_id, executor=fake_executor)
    finally:
        client.close()
