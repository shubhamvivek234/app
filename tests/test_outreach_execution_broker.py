"""Real Redis/Celery process-kill/redelivery; fake provider, isolated Mongo."""
import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

from tests.test_outreach_execution_outbox import execution_db
from outreach.tasks import sequence_dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv("OUTREACH_TEST_LOCAL_BROKER") != "1",
    reason="Disposable local Redis and Mongo crash drill is opt-in")]


async def wait_for(read, predicate, timeout=45):
    async with asyncio.timeout(timeout):
        while True:
            value = await read()
            if predicate(value):
                return value
            await asyncio.sleep(0.2)


@pytest.mark.parametrize("stage,expected_calls", [("before_submission", 1), ("after_possible", 0), ("after_call", 1), ("after_accepted", 1)])
async def test_worker_kill_and_real_broker_redelivery_never_repeat_possible_call(monkeypatch, tmp_path, stage, expected_calls):
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    name = "test_unravler_broker_" + uuid.uuid4().hex
    queue = "unravler_drill_" + uuid.uuid4().hex
    db = client[name]
    app = Celery("drill_publisher", broker="redis://127.0.0.1:6389/15")
    app.conf.broker_transport_options = {"visibility_timeout": 3, "global_keyprefix": queue + ":"}
    processes = []
    handles = []
    def start_worker():
        # Pass only the environment needed to run this isolated Python worker.
        env = {"PATH": os.environ["PATH"], "UNRAVLER_BROKER_DRILL": "1", "UNRAVLER_DRILL_DB": name,
            "UNRAVLER_DRILL_QUEUE": queue, "PYTHONUNBUFFERED": "1"}
        handle = (tmp_path / f"worker-{len(processes)}.log").open("w")
        handles.append(handle)
        process = subprocess.Popen([sys.executable, "-m", "celery", "-A", "tests.outreach_broker_harness:app", "worker",
            "--pool=solo", "--loglevel=WARNING", "--without-heartbeat", "--without-gossip", "--without-mingle", "-Q", queue],
            cwd=Path(__file__).resolve().parents[1], env=env, stdout=handle, stderr=subprocess.STDOUT)
        processes.append(process)
    try:
        for collection, values in execution_db().collections.items():
            if values.docs:
                await db[collection].insert_many(values.docs)
        monkeypatch.setattr(sequence_dispatch, "sequence_dispatch_enabled", lambda: True)
        await sequence_dispatch.prepare_due(db)
        job = await db.outreach_sequence_jobs.find_one({})
        await db.drill_controls.insert_one({"_id": job["_id"], "halt_at": stage, "fake_provider_calls": 0, "deliveries": 0})
        read = lambda: db.drill_controls.find_one({"_id": job["_id"]})
        start_worker()
        def publish(task, **kwargs):
            kwargs["queue"] = queue
            return app.send_task(task, **kwargs)
        assert (await sequence_dispatch.publish_due(db, publish))["published"] == 1
        await wait_for(read, lambda value: value.get("checkpoint") == stage)
        processes[0].kill()
        await asyncio.to_thread(processes[0].wait, 5)
        # Simulate elapsed lease time in our isolated database, without waiting
        # two minutes. Redis, not this test, restores the unacknowledged message.
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.drill_controls.update_one({"_id": job["_id"]}, {"$set": {"resume": True}})
        await db.outreach_sequence_jobs.update_one({"_id": job["_id"]}, {"$set": {"claim_expires_at": past}})
        await db.outreach_leads.update_one({"id": "l"}, {"$set": {"execution_claimed_at": past}})
        await db.outreach_intents.update_one({"_id": job["intent_id"]}, {"$set": {"claim_expires_at": past}})
        await asyncio.sleep(4)  # Let Redis visibility expire before the new consumer first restores.
        start_worker()
        result = await wait_for(read, lambda value: value.get("deliveries", 0) >= 2 and value.get("redelivered"))
        await wait_for(lambda: db.outreach_sequence_jobs.find_one({"_id": job["_id"]}), lambda value: value["status"] in {"completed", "held_outcome"})
        result = await read()
        assert result["fake_provider_calls"] == expected_calls
        intent = await db.outreach_intents.find_one({"_id": job["intent_id"]})
        assert intent["status"] == ("executed" if stage in {"before_submission", "after_accepted"} else "in_flight")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(process.wait, 5)
        for handle in handles:
            handle.close()
        from redis import Redis
        redis = Redis(host="127.0.0.1", port=6389, db=15)
        keys = list(redis.scan_iter(match=queue + ":*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        app.close()
        await client.drop_database(name)
        client.close()


async def test_real_broker_outage_retains_job_then_publishes_after_start(monkeypatch, tmp_path):
    import shutil
    import socket
    from redis import Redis
    redis_binary = shutil.which("redis-server")
    if not redis_binary:
        pytest.skip("Local redis-server is required")
    with socket.socket() as socket_probe:
        socket_probe.bind(("127.0.0.1", 0))
        port = socket_probe.getsockname()[1]
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True)
    name = "test_unravler_broker_" + uuid.uuid4().hex
    db = client[name]
    queue = "unravler_drill_" + uuid.uuid4().hex
    app = Celery("outage_publisher", broker=f"redis://127.0.0.1:{port}/0")
    app.conf.broker_connection_timeout = 0.3
    server = None
    redis = Redis(host="127.0.0.1", port=port, socket_connect_timeout=0.3)
    try:
        for collection, values in execution_db().collections.items():
            if values.docs:
                await db[collection].insert_many(values.docs)
        monkeypatch.setattr(sequence_dispatch, "sequence_dispatch_enabled", lambda: True)
        await sequence_dispatch.prepare_due(db)
        def publish(task, **kwargs):
            kwargs.update(queue=queue, retry=False)
            return app.send_task(task, **kwargs)
        assert (await sequence_dispatch.publish_due(db, publish))["published"] == 0
        assert (await db.outreach_sequence_jobs.find_one({}))["status"] == "queued"
        assert (await db.outreach_intents.find_one({}))["attempt"] is None
        server = subprocess.Popen([redis_binary, "--bind", "127.0.0.1", "--port", str(port), "--dir", str(tmp_path),
            "--save", "", "--appendonly", "no"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        async def alive():
            try:
                return await asyncio.to_thread(redis.ping)
            except Exception:
                return False
        await wait_for(alive, bool, timeout=5)
        assert (await sequence_dispatch.publish_due(db, publish))["published"] == 1
        assert redis.llen(queue) == 1
    finally:
        app.close()
        redis.close()
        if server:
            server.terminate()
            await asyncio.to_thread(server.wait, 5)
        await client.drop_database(name)
        client.close()
