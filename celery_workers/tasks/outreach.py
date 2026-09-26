"""Periodic dispatcher for due LinkedIn campaign sequence steps."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from celery_workers.shutdown_handler import is_shutting_down
from outreach.api.campaigns import (
    _evaluate_warmup, _fetch_cursor_docs, _launch_campaign_impl,
    conditional_auto_launch_enabled,
)
from outreach.core.rate_limiter import OutboundRateLimiter

logger = logging.getLogger(__name__)


async def _inbox_db():
    client = await get_client()
    return client[os.environ["DB_NAME"]]


async def _set_inbox_job(db, job_id: str, workspace_id: str, status: str, **extra) -> None:
    await db.outreach_inbox_jobs.update_one(
        {"id": job_id, "workspace_id": workspace_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc), **extra}},
    )


@celery_app.task(name="celery_workers.tasks.outreach.sync_inbox", queue="outreach", acks_late=True)
def sync_inbox(job_id: str, workspace_id: str, user_id: str, account_id: str | None = None) -> dict:
    return run_async(_sync_inbox(job_id, workspace_id, user_id, account_id))


async def _sync_inbox(job_id: str, workspace_id: str, user_id: str, account_id: str | None) -> dict:
    from outreach.engine.inbox_sync import InboxSynchronizer

    db = await _inbox_db()
    await _set_inbox_job(db, job_id, workspace_id, "running")
    try:
        syncer = InboxSynchronizer(db, workspace_id, user_id)
        result = await (syncer.sync_account_inbox(account_id) if account_id else syncer.sync_all_accounts())
        if result.get("status") == "error" or result.get("errors"):
            await _set_inbox_job(db, job_id, workspace_id, "failed", error=result.get("error") or "Some accounts failed to sync", result=result)
        else:
            await _set_inbox_job(db, job_id, workspace_id, "completed", result=result)
        return result
    except Exception as exc:
        logger.exception("Inbox sync job %s failed", job_id)
        await _set_inbox_job(db, job_id, workspace_id, "failed", error="LinkedIn inbox sync failed")
        raise


@celery_app.task(name="celery_workers.tasks.outreach.send_inbox_reply", queue="outreach", acks_late=True)
def send_inbox_reply(job_id: str, workspace_id: str, account_id: str, thread_id: str, body: str) -> dict:
    return run_async(_send_inbox_reply(job_id, workspace_id, account_id, thread_id, body))


async def _send_inbox_reply(job_id: str, workspace_id: str, account_id: str, thread_id: str, body: str) -> dict:
    from outreach.core.proxy_manager import JITProxyManager
    from outreach.core.rate_limiter import OutboundRateLimiter
    from outreach.core.safety_shield import SafetyShield
    from outreach.engine.voyager_client import VoyagerClient
    from outreach.models import MessageSenderType, OutreachInboxMessage

    db = await _inbox_db()
    claim = await db.outreach_inbox_jobs.update_one(
        {"id": job_id, "workspace_id": workspace_id, "status": "queued"},
        {"$set": {"status": "running", "updated_at": datetime.now(timezone.utc)}},
    )
    if not claim.modified_count:
        return {"status": "already_claimed"}
    try:
        thread = await db.outreach_inbox_threads.find_one({"id": thread_id, "workspace_id": workspace_id, "account_id": account_id})
        account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": workspace_id, "status": "active"})
        if not thread or not account or not thread.get("conversation_urn"):
            raise ValueError("The conversation or its assigned sender is unavailable")
        if thread.get("is_demo"):
            raise ValueError("Sample conversations cannot be sent to LinkedIn")
        cookie_enc = account.get("session_cookie_enc") or account.get("encrypted_session_cookie")
        if not cookie_enc:
            raise ValueError("Sender account has no LinkedIn session")
        proxy_config = account.get("proxy_config") or account.get("proxy")
        proxy_url = JITProxyManager.format_proxy_url(proxy_config) if proxy_config else None
        client = VoyagerClient(cookie_enc, jsession_id=account.get("jsession_id", ""), proxy_url=proxy_url)
        if client.is_mock and os.getenv("OUTREACH_MOCK_AUTH", "false").lower() not in {"true", "1"}:
            raise ValueError("Mock sender sessions cannot send real replies")
        allowed = await OutboundRateLimiter.check_and_increment_daily_limit(account, "messages", db)
        if not allowed:
            raise ValueError("Sender account has reached its daily message limit")
        response = await client.send_conversation_reply(thread["conversation_urn"], body)
        code = response.get("status_code")
        if code and SafetyShield.should_trip_circuit_breaker(code):
            await SafetyShield.trip_circuit_breaker(account_id, f"Inbox reply triggered HTTP {code}", db, workspace_id)
        if response.get("status") != "sent":
            raise RuntimeError("LinkedIn did not confirm the reply")
        now = datetime.now(timezone.utc)
        message = OutreachInboxMessage(
            sender_type=MessageSenderType.USER,
            sender_name=account.get("account_name") or account.get("name") or "You",
            body=body,
            timestamp=now,
        ).model_dump()
        await db.outreach_inbox_threads.update_one(
            {"id": thread_id, "workspace_id": workspace_id, "account_id": account_id},
            {"$push": {"messages": message}, "$set": {"last_message_snippet": body[:120], "last_message_at": now}},
        )
        await _set_inbox_job(db, job_id, workspace_id, "completed", result={"message": message})
        return {"status": "sent", "message": message}
    except Exception as exc:
        logger.exception("Inbox reply job %s failed", job_id)
        await _set_inbox_job(db, job_id, workspace_id, "failed", error=str(exc)[:200])
        raise

_SCAN_INTERVAL_SECONDS = max(10, int(os.environ.get("OUTREACH_SCAN_INTERVAL_SECONDS", "30")))
_BATCH_SIZE = max(1, int(os.environ.get("OUTREACH_SCAN_BATCH_SIZE", "50")))
_CLAIM_TIMEOUT_SECONDS = max(60, int(os.environ.get("OUTREACH_CLAIM_TIMEOUT_SECONDS", "600")))

celery_app.conf.beat_schedule.update({
    "run-due-linkedin-outreach-steps": {
        "task": "celery_workers.tasks.outreach.run_due_steps",
        "schedule": _SCAN_INTERVAL_SECONDS,
        "options": {"queue": "outreach"},
    },
    "run-conditional-outreach-warmups": {
        "task": "celery_workers.tasks.outreach.run_warmup_launches",
        "schedule": 60.0,
        "options": {"queue": "outreach"},
    },
})


@celery_app.task(name="celery_workers.tasks.outreach.run_warmup_launches", queue="outreach", acks_late=True)
def run_warmup_launches() -> dict:
    return run_async(_run_warmup_launches())


async def _verify_auto_launch_senders(campaign: dict, db) -> None:
    """At the trigger, verify the selected session through its configured proxy."""
    from outreach.core.crypto import decrypt_secret
    from outreach.core.proxy_manager import JITProxyManager
    from outreach.engine.session_authenticator import SessionAuthenticator

    workspace_id = campaign["workspace_id"]
    for account_id in campaign.get("sender_account_ids", []):
        account = await db.outreach_accounts.find_one({
            "id": account_id, "workspace_id": workspace_id, "status": "active",
        })
        if not account:
            raise RuntimeError("A selected sender is no longer active")
        proxy = account.get("proxy") or {}
        if not proxy.get("host") and os.getenv("OUTREACH_MOCK_AUTH", "false").lower() != "true":
            raise RuntimeError("A selected sender has no connected proxy")
        li_at = decrypt_secret(account.get("session_cookie_enc") or account.get("encrypted_session_cookie") or "")
        csrf = account.get("jsession_id") or ""
        if csrf.startswith("gAAAAA"):
            csrf = decrypt_secret(csrf)
        li_a = decrypt_secret(account["li_a_enc"]) if account.get("li_a_enc") else None
        profile = await SessionAuthenticator.validate_session_cookie(
            li_at=li_at, jsession_id=csrf,
            proxy_url=JITProxyManager.format_proxy_url(proxy) if proxy.get("host") else None,
            user_agent=account.get("user_agent"), li_a=li_a,
        )
        if not profile.get("linkedin_urn") or profile["linkedin_urn"] != account.get("linkedin_urn"):
            raise RuntimeError("LinkedIn sender identity could not be re-verified")


async def _run_warmup_launches(db=None) -> dict:
    if not conditional_auto_launch_enabled():
        return {"disabled": True, "checked": 0, "launched": 0}
    if is_shutting_down():
        return {"shutting_down": True, "checked": 0, "launched": 0}
    if db is None:
        client = await get_client()
        db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    candidates = await _fetch_cursor_docs(db.outreach_campaigns.find({
        "status": "warming_up", "auto_launch_enabled": True,
        "is_deleted": {"$ne": True},
        "$or": [
            {"auto_launch_next_check_at": {"$exists": False}},
            {"auto_launch_next_check_at": {"$lte": now}},
        ],
    }), length=25)
    counts = {"checked": 0, "launched": 0, "waiting": 0, "failed": 0}
    for candidate in candidates:
        if is_shutting_down():
            break
        campaign_id = candidate["id"]
        workspace_id = candidate["workspace_id"]
        claim_id = uuid.uuid4().hex
        claim_filter = {
            "id": campaign_id, "workspace_id": workspace_id,
            "status": "warming_up", "auto_launch_enabled": True,
            "$or": [
                {"auto_launch_claimed_at": {"$exists": False}},
                {"auto_launch_claimed_at": {"$lt": now - timedelta(minutes=15)}},
            ],
        }
        claim = await db.outreach_campaigns.update_one(claim_filter, {"$set": {
            "auto_launch_claim_id": claim_id, "auto_launch_claimed_at": now,
        }})
        if not claim.modified_count:
            continue
        counts["checked"] += 1
        scoped = {"id": campaign_id, "workspace_id": workspace_id, "auto_launch_claim_id": claim_id}
        try:
            campaign = await db.outreach_campaigns.find_one(scoped)
            if not campaign:
                continue
            gate = await _evaluate_warmup(
                campaign_id, workspace_id, db,
                required_list_id=campaign.get("auto_launch_list_id"),
            )
            if not gate["ready"]:
                counts["waiting"] += 1
                await db.outreach_campaigns.update_one(scoped, {"$set": {
                    "auto_launch_missing_count": gate["missing_count"],
                    "auto_launch_ready_at": gate["ready_at"],
                    "auto_launch_error": "" if gate["linked_lists_count"] else "Engage list is no longer linked",
                }})
                continue
            if not OutboundRateLimiter.is_within_working_hours(campaign.get("schedule"), now):
                counts["waiting"] += 1
                await db.outreach_campaigns.update_one(scoped, {"$set": {
                    "auto_launch_error": "Waiting for campaign working hours",
                }})
                continue
            leads = await _fetch_cursor_docs(db.outreach_leads.find({
                "campaign_id": campaign_id, "workspace_id": workspace_id,
            }), length=10000)
            sequence = await db.outreach_sequences.find_one({
                "campaign_id": campaign_id, "workspace_id": workspace_id, "is_deleted": {"$ne": True},
            })
            if (sorted(str(lead["id"]) for lead in leads) != campaign.get("auto_launch_lead_ids")
                    or not sequence or sequence.get("updated_at") != campaign.get("auto_launch_sequence_updated_at")):
                await db.outreach_campaigns.update_one(scoped, {"$set": {
                    "status": "paused", "auto_launch_enabled": False,
                    "auto_launch_error": "Lead cohort or sequence changed. Review and re-arm the campaign.",
                }})
                counts["failed"] += 1
                continue
            await _verify_auto_launch_senders(campaign, db)
            await _launch_campaign_impl(
                campaign_id, None,
                {"user_id": campaign["user_id"], "default_workspace_id": workspace_id},
                db, auto_launch_claim_id=claim_id,
            )
            counts["launched"] += 1
        except Exception as exc:
            # Network exceptions can contain proxy URLs; never expose them in logs or UI.
            logger.error("Conditional launch failed for campaign %s (%s)", campaign_id, type(exc).__name__)
            counts["failed"] += 1
            await db.outreach_campaigns.update_one(scoped, {"$set": {
                "auto_launch_error": "Sender verification or campaign checks failed. Review the sender and campaign settings.",
                "auto_launch_next_check_at": datetime.now(timezone.utc) + timedelta(minutes=30),
            }})
        finally:
            await db.outreach_campaigns.update_one(scoped, {
                "$unset": {"auto_launch_claim_id": "", "auto_launch_claimed_at": ""},
            })
    return counts


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
