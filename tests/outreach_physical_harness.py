"""Opt-in isolated worker, production guards/adapters and loopback-only HTTP."""
import asyncio
import os
from urllib.parse import urlparse

import httpx
from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv("UNRAVLER_PHYSICAL_DRILL") != "1":
    raise RuntimeError("This worker is restricted to explicit local tests")
DATABASE, QUEUE = os.environ["UNRAVLER_DRILL_DB"], os.environ["UNRAVLER_DRILL_QUEUE"]
ENDPOINT = os.environ["UNRAVLER_DRILL_ENDPOINT"]
endpoint = urlparse(ENDPOINT)
if (not DATABASE.startswith("test_unravler_physical_") or not QUEUE.startswith("unravler_physical_")
        or endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port
        or endpoint.path or endpoint.query or endpoint.fragment or endpoint.username or endpoint.password):
    raise RuntimeError("Isolated names and an exact loopback endpoint are required")

app = Celery("unravler_physical_drill", broker="redis://127.0.0.1:6389/15")
app.conf.update(task_default_queue=QUEUE, task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, task_ignore_result=True,
    broker_transport_options={"visibility_timeout": 3, "global_keyprefix": QUEUE + ":"})
OriginalClient = httpx.AsyncClient


class FaultDatabase:
    """Test-only write checkpoints; session writes precede transaction commit."""
    def __init__(self, database, control):
        self.database, self.control = database, control

    def __getattr__(self, name):
        if name == "client":
            return self.database.client
        return FaultCollection(self.database[name], name, self.control)

    def __getitem__(self, name):
        return getattr(self, name)


class FaultCollection:
    def __init__(self, collection, name, control):
        self.collection, self.name, self.control = collection, name, control

    def __getattr__(self, name):
        return getattr(self.collection, name)

    async def insert_one(self, document, **kwargs):
        result = await self.collection.insert_one(document, **kwargs)
        if self.name == "outreach_physical_requests" and document.get("status") == "preparing":
            await self.control.checkpoint("physical_preparing")
        return result

    async def update_one(self, query, update, **kwargs):
        result = await self.collection.update_one(query, update, **kwargs)
        if result.matched_count:
            await self.after_write(update)
        return result

    async def find_one_and_update(self, query, update, **kwargs):
        result = await self.collection.find_one_and_update(query, update, **kwargs)
        if result:
            await self.after_write(update)
        return result

    async def after_write(self, update):
        fields, removed = update.get("$set", {}), update.get("$unset", {})
        stage = None
        if self.name in {"outreach_manual_actions", "outreach_sequence_jobs"} and fields.get("status") == "preparing":
            stage = "job_preparing"
        elif self.name == "outreach_physical_requests":
            stage = {"in_flight": "physical_possible", "response_received": "physical_receipt"}.get(fields.get("status"))
        elif self.name == "outreach_sender_execution":
            if fields.get("physical_request_token"):
                stage = "transaction_token_written"
            elif "physical_request_token" in removed:
                stage = "physical_token_cleared"
        elif self.name == "outreach_engage_posts" and update.get("$inc", {}).get("reactions_count"):
            stage = "manual_projection"
        elif self.name == "outreach_manual_actions" and fields.get("status") == "completed":
            stage = "manual_completed"
        elif self.name in {"outreach_email_operations", "outreach_email_discoveries"} and fields.get("status") in {"accepted", "found"}:
            stage = "provider_result"
        elif self.name == "outreach_intents" and fields.get("status") == "executed":
            stage = "logical_result"
        if stage:
            await self.control.checkpoint(stage)


class Control:
    def __init__(self, database, record):
        self.database, self.record = database, record

    async def checkpoint(self, stage):
        await self.database.drill_controls.update_one({"_id": "run"}, {"$set": {"checkpoint": stage}})
        if self.record["halt_at"] == stage and not self.record.get("resume"):
            # Only the parent process ends this wait, with real SIGKILL.
            await asyncio.sleep(45)
            raise RuntimeError("The parent failed to kill the isolated worker")


class LoopbackTransport(httpx.AsyncBaseTransport):
    """No mock response: fixed logical URLs are forwarded over local TCP only."""
    def __init__(self, control):
        self.control = control

    async def handle_async_request(self, request):
        allowed = {
            ("POST", "www.linkedin.com", "/voyager/api/feed/reactions"),
            ("POST", "gmail.googleapis.com", "/gmail/v1/users/me/messages/send"),
            ("POST", "graph.microsoft.com", "/v1.0/me/sendMail"),
            ("GET", "api.hunter.io", "/v2/email-finder/found"),
        }
        if request.url.scheme != "https" or (request.method, request.url.host, request.url.path) not in allowed:
            raise RuntimeError("Network URL is outside the isolated provider drill")
        body = await request.aread()
        # Strip credentials and query strings before crossing even this local
        # transport. Production adapters already asserted their real contents.
        async with OriginalClient(trust_env=False, follow_redirects=False, timeout=20) as client:
            response = await client.request(request.method, ENDPOINT + request.url.path, content=body,
                headers={"Content-Type": request.headers.get("content-type", "application/json")})
        await self.control.checkpoint("http_response")
        return httpx.Response(response.status_code, headers=response.headers, content=response.content, request=request)


@app.task(bind=True, name="tests.outreach_physical_harness.execute")
def execute(self, workspace_id, job_id):
    return asyncio.run(run(workspace_id, job_id, bool(self.request.delivery_info.get("redelivered"))))


async def run(workspace_id, job_id, redelivered):
    from outreach.core.dispatch_authority import DispatchAuthority
    from outreach.core.execution_recovery import recover_intent
    from outreach.core.manual_actions import ManualActions
    from outreach.tasks.sequence_dispatch import execute_job
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True)
    database = client[DATABASE]
    original_factory = httpx.AsyncClient
    original_authorize = DispatchAuthority.authorize
    try:
        record = await database.drill_controls.find_one({"_id": "run"})
        control = Control(database, record)
        db = FaultDatabase(database, control)
        async def committed_authorization(self, *args, **kwargs):
            result = await original_authorize(self, *args, **kwargs)
            await control.checkpoint("physical_token")
            return result
        DispatchAuthority.authorize = committed_authorization
        def local_client(*args, **kwargs):
            kwargs.pop("proxy", None)
            kwargs.pop("transport", None)
            kwargs.update(transport=LoopbackTransport(control), trust_env=False, follow_redirects=False)
            return OriginalClient(*args, **kwargs)
        httpx.AsyncClient = local_client
        await database.drill_controls.update_one({"_id": "run"}, {"$inc": {"deliveries": 1}, "$set": {"redelivered": redelivered}})
        if record["kind"] == "manual":
            result = await ManualActions(db).run(workspace_id, job_id)
            if record.get("resume"):
                result = await ManualActions(db).recover(workspace_id, job_id)
        else:
            result = await execute_job(db, workspace_id, job_id)
            if record.get("resume"):
                intent = await db.outreach_intents.find_one({"workspace_id": workspace_id})
                result = {"status": await recover_intent(db, intent)}
        await database.drill_controls.update_one({"_id": "run"}, {"$set": {"finished": True, "result": result}})
        return result
    finally:
        httpx.AsyncClient = original_factory
        DispatchAuthority.authorize = original_authorize
        client.close()
