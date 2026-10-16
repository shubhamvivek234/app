"""Persist selection, publish references, and fence each sequence worker."""
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from celery_workers.shutdown_handler import is_shutting_down
from outreach.core.authorization import canonical_hash
from outreach.core.execution_outbox import ExecutionOutbox
from outreach.core.inbox_freshness import credential_generation
from outreach.core.sequence_versions import load_sequence
from outreach.core.sequence_capabilities import sequence_dispatch_enabled
from outreach.core.sequence_preview import validate_pinned_sequence
from outreach.core.sequence_contract import DAGValidationError

logger = logging.getLogger(__name__)
_CONTEXT = ContextVar("sequence_dispatch_job", default=None)
LEASE_SECONDS = 120
EFFECT_ACTIONS = {"visit_profile", "connection_request", "send_message", "like_last_post", "voice_note", "find_email", "send_email"}
DEFERRED = {"outside_working_hours": 5, "mailbox_unavailable": 30, "paid_access_required": 60, "action_disabled": 60}
RETRY = {"inbox_sync_required", "inbox_stale", "inbox_generation_changed", "inbox_coverage_invalid",
    "action_busy", "sender_busy", "request_deferred", "execution_permission_required", "authorization_required",
    "authorization_stale", "sender_changed", "sequence_changed", "dispatch_context_missing", "content_invalid",
    "voice_preparation_failed", "content_approval_required", "stale_job"}
FAILED = {"no_account_assigned", "account_unavailable", "sequence_not_configured", "action_failed", "unsupported_action"}


def lead_stamp(lead: dict, campaign: dict, sequence: dict, account: dict) -> dict:
    roots = (sequence.get("compiled_dag") or {}).get("root_node_ids") or []
    stamp = {"campaign_id": lead["campaign_id"], "lead_id": lead["id"], "sender_id": lead.get("assigned_account_id"),
        "enrollment_id": lead.get("enrollment_id") or "legacy:" + lead["id"], "node_id": lead.get("current_node_id") or (roots[0] if roots else None),
        "lead_node_id": lead.get("current_node_id"), "sequence_version": lead.get("sequence_version"),
        "sequence_digest": canonical_hash(sequence.get("compiled_dag")), "authorization_revision": lead.get("authorized_revision"),
        "campaign_revision": campaign.get("authorization_revision"), "credential_generation": credential_generation(account),
        "execution_state": lead.get("execution_state"), "waiting_for_reply_at": lead.get("waiting_for_reply_at"),
        "next_action_due_at": lead.get("next_action_due_at")}
    if lead.get('connection_wait_required') or lead.get('connection_wait_id'):
        from outreach.core.connection_waits import native
        stamp.update({'connection_wait_id': lead.get('connection_wait_id'),
            'connection_wait_revision': lead.get('connection_wait_revision'), 'lead_native_digest': native(lead)})
    node = (sequence.get('compiled_dag') or {}).get('nodes', {}).get(stamp['node_id'], {})
    if node.get('type') == 'has_data_in_column':
        from outreach.core.connection_waits import native
        stamp.update({'field_condition_contract_version': 1,
            'condition_native_ids': [native(row) for row in (lead, campaign, sequence, account)]})
    return stamp


async def prepare_due(db: AsyncIOMotorDatabase, *, limit: int = 50, now: datetime | None = None) -> dict:
    if is_shutting_down() or not sequence_dispatch_enabled():
        return {"disabled": True, "prepared": 0}
    now = now or datetime.now(timezone.utc)
    campaigns = await db.outreach_campaigns.find({"status": "active", "is_deleted": {"$ne": True}}).sort([
        ("next_sequence_scan_at", 1), ("id", 1)]).limit(limit).to_list(length=limit)
    count = 0
    for campaign in campaigns:
        if count >= limit or is_shutting_down():
            break
        ws, cid = campaign["workspace_id"], campaign["id"]
        await db.outreach_campaigns.update_one({"workspace_id": ws, "id": cid}, {"$set": {"next_sequence_scan_at": now}})
        sequence = await load_sequence(db, ws, cid, campaign=campaign)
        if not sequence or campaign.get("pause_reasons") or campaign.get("sequence_edit_pending"):
            continue
        try:
            validate_pinned_sequence(sequence)
        except DAGValidationError:
            continue
        query = {"workspace_id": ws, "campaign_id": cid, "execution_state": {"$in": ["queued", "waiting_delay", "replied"]}, "$and": [
            {"$or": [{"next_action_due_at": None}, {"next_action_due_at": {"$lte": now}}]},
            {"$or": [{"execution_state": {"$ne": "replied"}}, {"waiting_for_reply_at": {"$exists": True}}]},
        ]}
        leads = await db.outreach_leads.find(query).sort([("next_sequence_scan_at", 1), ("id", 1)]).limit(limit - count).to_list(length=limit - count)
        for lead in leads:
            await db.outreach_leads.update_one({"workspace_id": ws, "id": lead["id"]}, {"$set": {"next_sequence_scan_at": now}})
            account = await db.outreach_accounts.find_one({"workspace_id": ws, "id": lead.get("assigned_account_id"), "is_deleted": {"$ne": True}})
            if not account:
                continue
            if not isinstance(lead.get('current_node_id'), str) or not lead['current_node_id']:
                continue  # Launch/intake initialize roots with their actual due time.
            stamp = lead_stamp(lead, campaign, sequence, account)
            if (not stamp["node_id"] or stamp["authorization_revision"] != stamp["campaign_revision"]
                    or stamp["sequence_version"] != sequence.get("version", 1)):
                continue
            node = (sequence.get("compiled_dag") or {}).get("nodes", {}).get(stamp["node_id"], {})
            if not node:
                continue
            key = canonical_hash([ws, stamp])
            if node.get('type') == 'has_data_in_column':
                from outreach.core.sequence_conditions import field_job_bound
                if not field_job_bound({'workspace_id': ws, '_id': key, 'stamp': stamp}):
                    continue
            intent_id = None
            if node.get("type") in EFFECT_ACTIONS:
                intent = await ExecutionOutbox(db).ensure(workspace_id=ws, campaign_id=cid, lead_id=lead["id"], sender_id=account["id"],
                    node_id=stamp["node_id"], action_kind=node["type"], sequence_version=sequence.get("version", 1),
                    authorization_revision=campaign["authorization_revision"], credential_generation=credential_generation(account),
                    legacy_operation_id=lead["id"] + ":" + stamp["node_id"], enrollment_id=lead.get("enrollment_id"), now=now)
                intent_id = intent["_id"]
            try:
                await db.outreach_sequence_jobs.insert_one({"_id": key, "workspace_id": ws, "stamp": stamp, "intent_id": intent_id,
                    "status": "queued", "next_due_at": now, "created_at": now})
                count += 1
            except DuplicateKeyError:
                pass
    return {"prepared": count}


async def publish_due(db: AsyncIOMotorDatabase, publish: Callable, *, limit: int = 50, now: datetime | None = None) -> dict:
    if is_shutting_down() or not sequence_dispatch_enabled():
        return {"published": 0, "disabled": True}
    now = now or datetime.now(timezone.utc)
    jobs = await db.outreach_sequence_jobs.find({"next_due_at": {"$lte": now}, "$and": [
        {"$or": [{"status": "queued"}, {"status": "processing", "claim_expires_at": {"$lte": now}}]},
        {"$or": [{"next_publish_at": {"$exists": False}}, {"next_publish_at": {"$lte": now}}]},
    ]}).sort([("next_publish_at", 1), ("created_at", 1), ("_id", 1)]).limit(limit).to_list(length=limit)
    count = 0
    for job in jobs:
        try:
            publish("celery_workers.tasks.outreach.execute_sequence_job", args=[job["workspace_id"], job["_id"]],
                queue="outreach", ignore_result=True, headers={"x-trace-id": job["_id"]})
            count += 1
            await db.outreach_sequence_jobs.update_one({"workspace_id": job["workspace_id"], "_id": job["_id"], "status": job["status"]}, {
                "$set": {"next_publish_at": now + timedelta(seconds=30)}})
        except Exception as exc:
            logger.warning("Sequence publication retained (%s)", type(exc).__name__)
    return {"published": count}


async def validate_job(db: AsyncIOMotorDatabase, job: dict, owner: str | None = None, *, require_lead_owner: bool = False,
                       authorize_submission: bool = False, submission_owner: str | None = None) -> str | None:
    ws, stamp = job["workspace_id"], job["stamp"]
    if not isinstance(stamp, dict) or not isinstance(stamp.get('node_id'), str):
        return 'stale_job'
    if 'field_condition_contract_version' in stamp or 'condition_native_ids' in stamp:
        from outreach.core.sequence_conditions import field_job_bound
        if not field_job_bound(job):
            return 'stale_job'
    if owner:
        current = await db.outreach_sequence_jobs.find_one({"workspace_id": ws, "_id": job["_id"], "owner": owner,
            "status": "processing", "claim_expires_at": {"$gt": datetime.now(timezone.utc)}})
        if not current:
            return "stale_job"
    lead = await db.outreach_leads.find_one({"workspace_id": ws, "id": stamp["lead_id"]})
    campaign = await db.outreach_campaigns.find_one({"workspace_id": ws, "id": stamp["campaign_id"], "status": "active", "is_deleted": {"$ne": True}})
    account = await db.outreach_accounts.find_one({"workspace_id": ws, "id": stamp["sender_id"], "is_deleted": {"$ne": True}})
    sequence = await load_sequence(db, ws, stamp["campaign_id"], campaign=campaign) if campaign else None
    node = ((sequence or {}).get('compiled_dag') or {}).get('nodes', {}).get(stamp.get('node_id'), {})
    if node.get('type') == 'has_data_in_column' or 'field_condition_contract_version' in stamp:
        from outreach.core.sequence_conditions import field_job_bound
        if not field_job_bound(job):
            return 'stale_job'
    if (not lead or not campaign or not account or not sequence or lead_stamp(lead, campaign, sequence, account) != stamp
            or require_lead_owner and lead.get("execution_claim_token") != owner):
        return "stale_job"
    if job.get("intent_id"):
        intent = await db.outreach_intents.find_one({"workspace_id": ws, "_id": job["intent_id"]})
        if (not intent or intent["lead_id"] != stamp["lead_id"] or intent["node_id"] != stamp["node_id"]
                or intent["enrollment_id"] != stamp["enrollment_id"] or intent["sequence_version"] != stamp["sequence_version"]
                or intent.get("sender_id") != stamp["sender_id"] or intent.get("authorization_revision") != stamp["authorization_revision"]
                or intent.get("credential_generation") != stamp["credential_generation"]
                or intent.get("campaign_id") != stamp["campaign_id"]
                or intent.get("action_kind") != sequence["compiled_dag"]["nodes"].get(stamp["node_id"], {}).get("type")):
            return "stale_job"
        if authorize_submission and (not submission_owner or intent.get("status") != "in_flight"
                or intent.get("claim_token") != submission_owner or intent.get("resolution")
                or (intent.get("attempt") or {}).get("owner_token") != submission_owner):
            return "stale_job"
    return None


async def validate_dispatch_context(db_override=None, *, authorize_submission: bool = False) -> str | None:
    value = _CONTEXT.get()
    if not value:
        return "dispatch_context_missing" if authorize_submission else None
    db, job, owner = value
    from outreach.core.request_guard import current_request_parent
    parent = current_request_parent() if authorize_submission else None
    return await validate_job(db_override if db_override is not None else db, job, owner,
        require_lead_owner=True, authorize_submission=authorize_submission,
        submission_owner=parent.owner if parent else None)


def dispatch_intent_id() -> str | None:
    value = _CONTEXT.get()
    return value[1].get("intent_id") if value else None


def dispatch_job_id() -> str | None:
    value = _CONTEXT.get()
    return value[1].get('_id') if value else None


def condition_dispatch_context():
    """Only the durable claimed job may choose a stored-field branch."""
    return _CONTEXT.get()


@contextmanager
def dispatch_context(db: AsyncIOMotorDatabase, job: dict, owner: str):
    token = _CONTEXT.set((db, job, owner))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


async def execute_job(db: AsyncIOMotorDatabase, workspace_id: str, job_id: str, *, executor: Callable[..., Awaitable[dict]] | None = None) -> dict:
    if is_shutting_down() or not sequence_dispatch_enabled():
        return {"status": "disabled"}
    now, owner = datetime.now(timezone.utc), str(uuid.uuid4())
    scope = {"workspace_id": workspace_id, "_id": job_id}
    changed = await db.outreach_sequence_jobs.update_one({**scope, "next_due_at": {"$lte": now}, "$or": [
        {"status": "queued"}, {"status": "processing", "claim_expires_at": {"$lte": now}},
    ]}, {"$set": {"status": "processing", "owner": owner, "claim_expires_at": now + timedelta(seconds=LEASE_SECONDS)}})
    if not changed.matched_count:
        from outreach.core.sequence_conditions import saved_result
        recovered = saved_result(await db.outreach_sequence_jobs.find_one(scope))
        if recovered:
            return {**recovered, 'recovered': True}
        return {"status": "already_claimed"}
    job = await db.outreach_sequence_jobs.find_one({**scope, "owner": owner})
    reason = await validate_job(db, job, owner)
    if reason:
        await db.outreach_sequence_jobs.update_one({**scope, "owner": owner}, {"$set": {"status": "stale", "result_status": reason}})
        return {"status": reason}
    stamp = job["stamp"]
    lead_scope = {"workspace_id": workspace_id, "id": stamp["lead_id"], "campaign_id": stamp["campaign_id"],
        "current_node_id": stamp["lead_node_id"], "execution_state": stamp["execution_state"], "authorized_revision": stamp["authorization_revision"],
        "sequence_version": stamp["sequence_version"], "assigned_account_id": stamp["sender_id"],
        "enrollment_id": stamp["enrollment_id"] if not stamp["enrollment_id"].startswith("legacy:") else {"$in": [None, stamp["enrollment_id"]]},
        "next_action_due_at": stamp["next_action_due_at"]}
    claimed = await db.outreach_leads.update_one({**lead_scope, "$or": [
        {"execution_claimed_at": {"$exists": False}}, {"execution_claimed_at": {"$lte": now - timedelta(seconds=LEASE_SECONDS)}},
    ]}, {"$set": {"execution_claimed_at": now, "execution_claim_token": owner}})
    owned = {**scope, "owner": owner, "status": "processing", "stamp": job['stamp']}
    if not claimed.matched_count:
        await db.outreach_sequence_jobs.update_one(owned, {"$set": {"status": "queued", "next_due_at": now + timedelta(seconds=30)}})
        return {"status": "lead_busy"}
    try:
        if executor is None:
            from outreach.tasks.sequence_executor import SequenceExecutor
            executor = SequenceExecutor.execute_lead_step
        with dispatch_context(db, job, owner):
            result = await executor(stamp["lead_id"], db, workspace_id=workspace_id)
        status = result.get("status")
        projection = {**lead_scope, "execution_claim_token": owner, "has_replied": {"$ne": True}}
        if result.get("not_submitted") or status in DEFERRED or status in RETRY or status == "rate_limited":
            due = now + timedelta(minutes=DEFERRED.get(status, 5))
            if status == "rate_limited":
                due = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
            await db.outreach_leads.update_one(projection, {"$set": {"next_action_due_at": due, "defer_reason": status}})
            # The next due occurrence gets its own immutable stamp. A completed
            # poll or deferral must not suppress future checks of this node.
            await db.outreach_sequence_jobs.update_one(owned, {"$set": {"status": "deferred", "next_due_at": due, "result_status": status}})
        else:
            if status in FAILED:
                from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY
                await db.outreach_leads.update_one({**projection, "$nor": [SEARCH_PROVENANCE_QUERY]}, {"$set": {"execution_state": "failed", "failure_reason": result.get("reason") or status}})
            terminal = "held_outcome" if status in {"action_uncertain", "uncertain"} else "completed"
            await db.outreach_sequence_jobs.update_one(owned, {"$set": {"status": terminal, "result_status": status, "completed_at": now}})
        return result
    except Exception as exc:
        logger.error("Sequence job interrupted (%s)", type(exc).__name__)
        # Never label a possibly sent step failed or create a new send permit.
        await db.outreach_sequence_jobs.update_one(owned, {"$set": {"status": "queued", "next_due_at": now + timedelta(minutes=5)}})
        return {"status": "execution_interrupted"}
    finally:
        await db.outreach_leads.update_one({"workspace_id": workspace_id, "id": stamp["lead_id"], "execution_claim_token": owner}, {
            "$unset": {"execution_claim_token": "", "execution_claimed_at": ""}})
