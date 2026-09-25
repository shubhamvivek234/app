"""Periodic dispatcher for due LinkedIn campaign sequence steps."""
import logging
import os
from datetime import datetime, timedelta, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

_SCAN_INTERVAL_SECONDS = max(10, int(os.environ.get("OUTREACH_SCAN_INTERVAL_SECONDS", "30")))
_BATCH_SIZE = max(1, int(os.environ.get("OUTREACH_SCAN_BATCH_SIZE", "50")))
_CLAIM_TIMEOUT_SECONDS = max(60, int(os.environ.get("OUTREACH_CLAIM_TIMEOUT_SECONDS", "600")))

celery_app.conf.beat_schedule.update({
    "run-due-linkedin-outreach-steps": {
        "task": "celery_workers.tasks.outreach.run_due_steps",
        "schedule": _SCAN_INTERVAL_SECONDS,
        "options": {"queue": "outreach"},
    },
})


@celery_app.task(name="celery_workers.tasks.outreach.run_due_steps", queue="outreach", acks_late=True)
def run_due_steps() -> dict:
    """Claim and execute a bounded batch of due steps for active campaigns."""
    return run_async(_run_due_steps())


async def _run_due_steps() -> dict:
    from outreach.models import LeadExecutionState
    from outreach.tasks.sequence_executor import SequenceExecutor

    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    claim_cutoff = now - timedelta(seconds=_CLAIM_TIMEOUT_SECONDS)

    campaign_ids = await db.outreach_campaigns.distinct(
        "id", {"status": "active", "is_deleted": {"$ne": True}}
    )
    if not campaign_ids:
        return {"claimed": 0, "completed": 0, "deferred": 0, "failed": 0}

    due_filter = {
        "campaign_id": {"$in": campaign_ids},
        "execution_state": {"$in": [
            LeadExecutionState.QUEUED.value,
            LeadExecutionState.WAITING_DELAY.value,
            LeadExecutionState.REPLIED.value,
        ]},
        "$and": [
            {"$or": [
                {"next_action_due_at": {"$exists": False}},
                {"next_action_due_at": None},
                {"next_action_due_at": {"$lte": now}},
            ]},
            {"$or": [
                {"execution_state": {"$ne": LeadExecutionState.REPLIED.value}},
                {"waiting_for_reply_at": {"$exists": True}},
            ]},
        ],
    }
    candidates = await db.outreach_leads.find(due_filter).sort("created_at", 1).limit(_BATCH_SIZE).to_list(length=_BATCH_SIZE)
    counts = {"claimed": 0, "completed": 0, "deferred": 0, "failed": 0}

    for lead in candidates:
        claim_filter = {
            "id": lead.get("id"),
            "campaign_id": lead.get("campaign_id"),
            "$and": [
                {"execution_state": {"$in": [
                    LeadExecutionState.QUEUED.value,
                    LeadExecutionState.WAITING_DELAY.value,
                    LeadExecutionState.REPLIED.value,
                ]}},
                {"$or": [
                    {"next_action_due_at": {"$exists": False}},
                    {"next_action_due_at": None},
                    {"next_action_due_at": {"$lte": now}},
                ]},
                {"$or": [
                    {"execution_claimed_at": {"$exists": False}},
                    {"execution_claimed_at": {"$lte": claim_cutoff}},
                ]},
                {"$or": [
                    {"execution_state": {"$ne": LeadExecutionState.REPLIED.value}},
                    {"waiting_for_reply_at": {"$exists": True}},
                ]},
            ],
        }
        claim = await db.outreach_leads.update_one(
            claim_filter,
            {"$set": {"execution_claimed_at": now}},
        )
        if not claim.modified_count:
            continue

        counts["claimed"] += 1
        try:
            result = await SequenceExecutor.execute_lead_step(lead["id"], db)
            result_status = result.get("status")
            if result_status == "outside_working_hours":
                await db.outreach_leads.update_one(
                    {"id": lead["id"]},
                    {"$set": {"next_action_due_at": now + timedelta(minutes=5)}},
                )
                counts["deferred"] += 1
            elif result_status == "rate_limited":
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                await db.outreach_leads.update_one(
                    {"id": lead["id"]},
                    {"$set": {"next_action_due_at": tomorrow, "execution_state": LeadExecutionState.WAITING_DELAY}},
                )
                counts["deferred"] += 1
            elif result_status in {"no_account_assigned", "account_unavailable", "sequence_not_configured", "action_failed", "unsupported_action"}:
                await db.outreach_leads.update_one(
                    {"id": lead["id"]},
                    {"$set": {
                        "execution_state": LeadExecutionState.FAILED,
                        "failure_reason": result.get("reason") or result_status,
                        "updated_at": datetime.now(timezone.utc),
                    }},
                )
                counts["failed"] += 1
            else:
                counts["completed"] += 1
        except Exception as exc:
            logger.exception("Outreach step failed for lead %s", lead.get("id"))
            await db.outreach_leads.update_one(
                {"id": lead.get("id")},
                {"$set": {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_reason": str(exc)[:500],
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            counts["failed"] += 1
        finally:
            await db.outreach_leads.update_one(
                {"id": lead.get("id")},
                {"$unset": {"execution_claimed_at": ""}},
            )

    return counts
