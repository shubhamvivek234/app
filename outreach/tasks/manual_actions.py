"""Publish references from durable manual jobs; recovery never calls a provider."""
import logging
from typing import Callable
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta, timezone

from outreach.core.manual_actions import ManualActions
from outreach.core.paid_access import live_actions_enabled

logger = logging.getLogger(__name__)


async def publish_due(db: AsyncIOMotorDatabase, publish: Callable, *, limit: int = 50) -> dict:
    if not live_actions_enabled():
        return {"published": 0, "status": "disabled"}
    now = datetime.now(timezone.utc)
    jobs = await db.outreach_manual_actions.find({"next_due_at": {"$lte": now}, "$and": [
        {"$or": [{"next_publish_at": {"$exists": False}}, {"next_publish_at": {"$lte": now}}]},
        {"$or": [{"status": "queued"}, {"status": "preparing", "claim_expires_at": {"$lte": now}}]},
    ]}).sort([("next_publish_at", 1), ("created_at", 1), ("_id", 1)]).limit(limit).to_list(length=limit)
    count = 0
    for job in jobs:
        if job["source"] == "engage":
            task = "celery_workers.tasks.engage." + job["action"] + "_post"
            args = [job["target_id"], job["workspace_id"], job["account_id"], None, job["_id"]]
        else:
            task = "celery_workers.tasks.outreach.send_inbox_reply"
            args = [job["_id"], job["workspace_id"], job["account_id"], job["target_id"]]
        try:
            publish(task, args=args, queue="outreach", ignore_result=True, headers={"x-trace-id": job["_id"]})
            count += 1
            await db.outreach_manual_actions.update_one({"_id": job["_id"], "workspace_id": job["workspace_id"], "status": job["status"]}, {
                "$set": {"next_publish_at": now + timedelta(seconds=30)}})
        except Exception as exc:
            logger.warning("Manual publication retained (%s)", type(exc).__name__)
    return {"published": count}


async def recover_due(db: AsyncIOMotorDatabase, *, limit: int = 50) -> dict:
    now = datetime.now(timezone.utc)
    jobs = await db.outreach_manual_actions.find({"$and": [{"$or": [
        {"next_recovery_due_at": {"$exists": False}}, {"next_recovery_due_at": {"$lte": now}},
    ]}], "$or": [
        {"status": "in_flight", "claim_expires_at": {"$lte": now}},
        {"status": {"$in": ["unknown_outcome", "projection_pending", "resolving"]}},
        {"status": {"$in": ["completed", "cancelled", "resolved"]}, "cleanup_complete": {"$ne": True}},
    ]}).sort([("next_recovery_due_at", 1), ("_id", 1)]).limit(limit).to_list(length=limit)
    outcomes = {}
    for job in jobs:
        try:
            result = await ManualActions(db).recover(job["workspace_id"], job["_id"])
            status = result["status"]
            outcomes[status] = outcomes.get(status, 0) + 1
        except Exception as exc:
            logger.warning("Manual recovery retained (%s)", type(exc).__name__)
        finally:
            await db.outreach_manual_actions.update_one({"_id": job["_id"], "workspace_id": job["workspace_id"]}, {
                "$set": {"next_recovery_due_at": now + timedelta(minutes=1)}})
    return outcomes
