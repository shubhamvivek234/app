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
from outreach.core.proxy_manager import JITProxyManager
from outreach.engine.session_authenticator import SessionAuthenticator, InvalidSessionError
from outreach.core.session_custody import pending_session, account_session, seal_installed, custody_mode
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.paid_access import get_active_entitlement, live_actions_enabled, sender_is_ready, _utc
from outreach.core.sequence_capabilities import sequence_dispatch_enabled
from outreach.core.managed_proxy import _proxy_from_inventory, release_sender_reservation
from outreach.models import AccountAuthMode, AccountStatus
from outreach.core.connection_repair import ConnectionRepair, credential_deadline
from outreach.core.request_guard import RequestEnvelope, RequestDenied
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.health_monitor import HealthMonitor, connection_evidence, now as health_now
from outreach.core.inbox_freshness import credential_generation

logger = logging.getLogger(__name__)


@celery_app.task(name="celery_workers.tasks.outreach.verify_sender_connection", queue="outreach", acks_late=True)
def verify_sender_connection(job_id: str, workspace_id: str, trace_id: str) -> dict:
    return run_async(_verify_sender_connection(job_id, workspace_id, trace_id))


async def _verify_sender_connection(job_id: str, workspace_id: str, trace_id: str, db=None) -> dict:
    """Verify encrypted pending values through the sender's leased provider IP."""
    if is_shutting_down():
        return {"status": "shutting_down"}
    db = db or await _inbox_db()
    from outreach.core.restore_epoch import positive, EpochUnavailable
    try:
        epoch = await positive(db, workspace_id)
    except EpochUnavailable:
        return {'status': 'restore_epoch_required'}
    now = datetime.now(timezone.utc)
    owner = str(uuid.uuid4())
    claimed = await db.outreach_connection_jobs.update_one(
        {"id": job_id, "workspace_id": workspace_id, "status": "queued", "$and": [
            {"$or": [{"next_verification_due_at": {"$lte": now}}, {"next_verification_due_at": {"$exists": False}}]},
            {"$or": [{"created_at": {"$gte": now - timedelta(minutes=15)}}, {"created_at": {"$exists": False}}]},
        ]},
        {"$set": {"status": "running", "started_at": now, "verification_owner_token": owner}},
    )
    if not claimed.modified_count:
        return {"status": "already_claimed"}
    job = await db.outreach_connection_jobs.find_one({"id": job_id, "workspace_id": workspace_id})
    if not job:
        return {"status": "job_missing"}

    sender_id = job["sender_id"]
    job_scope = {"id": job_id, "workspace_id": workspace_id, "status": "running", "verification_owner_token": owner}
    deferred = False
    finalizing = False
    error = "Sender verification failed. Check your session and proxy, then try again."
    try:
        if not credential_deadline(job) or credential_deadline(job) <= datetime.now(timezone.utc):
            raise ValueError("connection_job_expired")
        if (not live_actions_enabled()
                or os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}
                or not await get_active_entitlement(db, workspace_id)):
            raise ValueError("paid_access_unavailable")
        slot = await db.outreach_sender_slots.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
        })
        lease = await db.outreach_proxy_leases.find_one({
            "_id": job["proxy_id"], "workspace_id": workspace_id, "sender_id": sender_id,
        })
        inventory = await db.outreach_proxy_inventory.find_one({"_id": job["proxy_id"]})
        if (not slot or not lease or not inventory or inventory.get("status") != "available"
                or inventory.get("last_workspace_id") != workspace_id):
            raise ValueError("sender_capacity_unavailable")
        expires_at = _utc(inventory.get("expires_at"))
        if (inventory.get("country_code") != job["country_code"] or not expires_at
                or expires_at <= datetime.now(timezone.utc)):
            raise ValueError("provider_term_expired")
        if inventory.get('provider') == 'webshare_plan' or str(job['proxy_id']).startswith('webshare:'):
            from outreach.core.webshare_provisioning import managed_webshare_valid
            if not await managed_webshare_valid(db, inventory, workspace_id):
                raise ValueError('proxy_import_requires_review')
        if not await ExecutionPermission(db).allowed(workspace_id, sender_id, "pending:" + job_id, "verify"):
            raise RequestDenied("execution_permission_required", 15)
        proxy = _proxy_from_inventory(inventory)
        from outreach.core.proxy_identity import check_restore_ips
        await check_restore_ips(db, workspace_id, [proxy.host], captured=epoch.captured)
        prepared = await prepare_proxy(proxy, workspace_id)
        await positive(db, workspace_id, captured=epoch.captured)
        await check_restore_ips(db, workspace_id, [proxy.host], captured=epoch.captured)
        health_options = {"prepared_proxy": prepared} if prepared.scoped else {}
        health_options['allowed'] = epoch.live
        if not await JITProxyManager().test_proxy_health(proxy, **health_options):
            raise ValueError("proxy_health_failed")
        material = await pending_session(job)
        if credential_deadline(job) <= datetime.now(timezone.utc):
            raise ValueError("connection_job_expired")
        profile = await SessionAuthenticator.validate_session_cookie(
            **material,
            proxy_url=prepared.url,
            user_agent=job.get("user_agent"),
            request_envelope=RequestEnvelope(db, workspace_id, sender_id, "pending:" + job_id, "verify",
                prepared.url, connection_job_id=job_id, prepared_proxy=prepared),
        )
        health_observed_at = health_now()
        linkedin_urn = profile.get("linkedin_urn")
        if not linkedin_urn:
            raise InvalidSessionError("LinkedIn identity was not returned")
        existing = await db.outreach_accounts.find_one({
            "id": sender_id, "workspace_id": workspace_id,
        }) if job.get("reconnect") else None
        if existing and existing.get("linkedin_urn") != linkedin_urn:
            raise InvalidSessionError("Session belongs to a different sender")
        if not existing:
            duplicate = await db.outreach_accounts.find_one({
                "workspace_id": workspace_id, "linkedin_urn": linkedin_urn,
            })
            if duplicate:
                raise InvalidSessionError("Sender already exists; reconnect it instead")

        # Payment and provider term may have changed during the network call.
        if not await get_active_entitlement(db, workspace_id):
            raise ValueError("paid_access_unavailable")
        current_job = await db.outreach_connection_jobs.find_one(job_scope)
        if not current_job:
            raise ValueError("connection_job_expired")
        refreshed = await db.outreach_proxy_inventory.find_one({"_id": job["proxy_id"]})
        if not refreshed or not _utc(refreshed.get("expires_at")) or _utc(refreshed["expires_at"]) <= datetime.now(timezone.utc):
            raise ValueError("provider_term_expired")
        fresh_lease = await db.outreach_proxy_leases.find_one({
            "_id": job["proxy_id"], "workspace_id": workspace_id, "sender_id": sender_id})
        fresh_slot = await db.outreach_sender_slots.find_one({"workspace_id": workspace_id, "sender_id": sender_id})
        if (not fresh_lease or not fresh_slot or refreshed.get("status") != "available"
                or refreshed.get("last_workspace_id") != workspace_id
                or refreshed.get("country_code") != job["country_code"]):
            raise ValueError("sender_capacity_unavailable")
        if refreshed.get('provider') == 'webshare_plan':
            from outreach.core.webshare_provisioning import managed_webshare_valid
            if not await managed_webshare_valid(db, refreshed, workspace_id) or not prepared.matches(refreshed, workspace_id):
                raise ValueError('proxy_import_changed')

        hosts = [proxy.host]
        if refreshed.get('host') is not None:
            hosts.append(refreshed['host'])
        await check_restore_ips(db, workspace_id, hosts, captured=epoch.captured)
        now = datetime.now(timezone.utc)
        generation = str(uuid.uuid4())
        installed = (await seal_installed(material, workspace_id, sender_id, generation)
            if custody_mode() == "kms_v1" else {"session_cookie_enc": job["li_at_enc"],
                "jsession_id": job["jsession_id_enc"], "li_a_enc": job.get("li_a_enc") or ""})
        now = datetime.now(timezone.utc)
        if credential_deadline(job) <= now:
            raise ValueError("connection_job_expired")
        # From preparation onward an uncertain acknowledgement is quarantined.
        await positive(db, workspace_id, captured=epoch.captured)
        finalizing = True
        repair = ConnectionRepair(db)
        await repair.prepare(job, owner, generation, profile, now=now)
        # Credential writes can commit even if the acknowledgement is lost.
        # The ordinary timeout/paid cleanup may only release pre-activation jobs.
        final_claim = await db.outreach_connection_jobs.update_one({**job_scope, "custody_expires_at": {"$gt": now}}, {"$set": {
            "status": "finalizing", "finalizing_at": now, "credential_generation": generation,
            "custody_started_at": job.get("custody_started_at") or job.get("created_at"),
            "expected_linkedin_urn": linkedin_urn}, "$unset": {"created_at": ""}})
        if not final_claim.modified_count:
            return {"status": "connection_job_expired"}
        job_scope = {**job_scope, "status": "finalizing"}
        updates = {
            "account_name": profile.get("account_name") or "LinkedIn sender",
            "avatar_url": profile.get("avatar_url"),
            "linkedin_urn": linkedin_urn,
            "vanity_name": profile.get("vanity_name"),
            "auth_mode": AccountAuthMode.COOKIE,
            **installed,
            "premium_product": job.get("premium_product") or "classic",
            "user_agent": job.get("user_agent") or "",
            "country_code": job["country_code"],
            "proxy": proxy.model_dump(), "status": AccountStatus.ACTIVE,
            "credential_generation": generation, "inbox_sync": {"status": "required"},
            "updated_at": now,
        }
        updates['execution_health'] = connection_evidence(job_id, generation,
            {'workspace_id': workspace_id, 'id': sender_id, **updates}, health_observed_at)
        if not await get_active_entitlement(db, workspace_id) or not await repair.install(job, owner, generation, updates, prepared_proxy=prepared):
            raise ValueError("connection_installation_stopped")
        # The paid period may end while identity verification or the DB write
        # is in flight. Never leave a newly usable session behind in that case.
        if not await get_active_entitlement(db, workspace_id):
            await repair.close_fence(job)
            raise ValueError("paid_access_unavailable")
        # Mark the account fence closed without renewing or copying credentials.
        closed = await db.outreach_accounts.update_one({"id": sender_id, "workspace_id": workspace_id,
            "credential_generation": generation, "connection_finalization.job_id": job_id,
            "connection_finalization.owner_token": owner, "connection_finalization.state": "installed"}, {
            "$set": {"connection_finalization.state": "closed", "connection_finalization.completion": "verified_install"}})
        if not closed.matched_count:
            raise ValueError("connection_installation_stopped")
        completed = await db.outreach_connection_jobs.update_one(
            {**job_scope, "custody_expired_at": {"$exists": False},
             "$expr": {"$gt": ["$custody_expires_at", "$$NOW"]}},
            {"$set": {"status": "completed", "account_id": sender_id, "updated_at": now,
                      "connection_cleanup_complete": False},
             "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": "", "verification_owner_token": ""}},
        )
        if not completed.modified_count:
            raise RuntimeError("Connection finalization ownership changed")
        finalizing = False
        return {"status": "completed", "account_id": sender_id}
    except RequestDenied as exc:
        # Known non-calls wait for operator permission/capacity without losing
        # encrypted pending values. The existing 15-minute reaper bounds custody.
        changed = await db.outreach_connection_jobs.update_one(job_scope, {
            "$set": {"status": "queued", "deferred_reason": exc.reason,
                      "next_verification_due_at": datetime.now(timezone.utc) + timedelta(seconds=max(5, exc.retry_after)),
                      "updated_at": datetime.now(timezone.utc)},
            "$unset": {"verification_owner_token": ""},
        })
        deferred = bool(changed.modified_count)
        return {"status": "deferred" if deferred else "connection_job_expired", "reason": exc.reason}
    except Exception as exc:
        # Never write exception strings: network errors may contain proxy credentials.
        logger.error("Sender verification failed trace=%s reason=%s", trace_id, type(exc).__name__)
        if finalizing:
            current = await db.outreach_connection_jobs.find_one({"id": job_id, "workspace_id": workspace_id})
            if current and current.get("status") == "failed" and not current.get("finalization_prepared"):
                # Another cleanup owns the job. No account fence was prepared.
                deferred = True
                finalizing = False
                return {"status": "connection_job_expired"}
            if current and current.get("status") == "completed" and current.get("credential_generation") == generation:
                finalizing = False
                return {"status": "completed", "account_id": sender_id}
            # Preserve reservations/lock after a possible credential activation.
            # A drained operator repair must inspect the exact new generation.
            await ExecutionPermission(db).revoke(workspace_id, sender_id, "connection_guard", "connection_finalization_unknown")
            await db.outreach_connection_jobs.update_one({"id": job_id, "workspace_id": workspace_id,
                "verification_owner_token": owner, "status": {"$in": ["running", "finalizing"]}}, {"$set": {
                "status": "finalizing", "custody_started_at": job.get("custody_started_at") or job.get("created_at"),
                "error": "Connection finalization requires operator review.", "needs_operator_repair": True,
                "updated_at": datetime.now(timezone.utc)},
                "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": "", "created_at": ""}})
            return {"status": "finalization_review_required"}
        if isinstance(exc, InvalidSessionError):
            error = "LinkedIn session was rejected or belongs to another sender. Recheck the session values."
        elif isinstance(exc, ValueError) and str(exc) == "paid_access_unavailable":
            error = "Paid sender access is no longer active."
        elif isinstance(exc, ValueError) and str(exc) in {"provider_term_expired", "proxy_health_failed", "sender_capacity_unavailable"}:
            error = "The assigned provider IP is unavailable. Contact support before retrying."
        stopped = await db.outreach_connection_jobs.update_one(
            job_scope,
            {"$set": {"status": "failed", "error": error, "updated_at": datetime.now(timezone.utc)},
             "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": "", "verification_owner_token": ""}},
        )
        if not stopped.modified_count:
            return {"status": "connection_job_expired"}
        if job.get("new_proxy_reservation"):
            await release_sender_reservation(db, workspace_id, sender_id, job["proxy_id"])
        if job.get("created_slot"):
            await db.outreach_sender_slots.delete_one({"workspace_id": workspace_id, "sender_id": sender_id})
        return {"status": "failed"}
    finally:
        if not deferred and not finalizing:
            await db.outreach_connection_locks.delete_one({"_id": sender_id, "job_id": job_id})
            await db.outreach_connection_jobs.update_one({"id": job_id, "workspace_id": workspace_id,
                "status": "completed", "connection_cleanup_complete": False}, {"$set": {
                "connection_cleanup_complete": True, "created_at": datetime.now(timezone.utc)}})


@celery_app.task(name="celery_workers.tasks.outreach.dispatch_due_verifications", queue="outreach", acks_late=True)
def dispatch_due_verifications() -> dict:
    return run_async(_dispatch_due_verifications())


async def _dispatch_due_verifications(db=None) -> dict:
    """Publish durable pending references, never credentials; worker CAS fences duplicates."""
    if is_shutting_down() or not live_actions_enabled():
        return {"disabled": True, "published": 0}
    db = db or await _inbox_db()
    now = datetime.now(timezone.utc)
    jobs = await db.outreach_connection_jobs.find({"status": "queued", "$and": [
        {"$or": [{"next_verification_due_at": {"$lte": now}}, {"next_verification_due_at": {"$exists": False}}]},
        {"$or": [{"created_at": {"$gte": now - timedelta(minutes=15)}}, {"created_at": {"$exists": False}}]},
    ]}).limit(50).to_list(length=50)
    published = 0
    for job in jobs:
        if is_shutting_down():
            break
        try:
            verify_sender_connection.delay(job["id"], job["workspace_id"], job.get("trace_id") or job["id"])
            published += 1
        except Exception as exc:
            logger.warning("Due verification publication failed (%s)", type(exc).__name__)
    return {"published": published}


celery_app.conf.beat_schedule["dispatch-due-outreach-verifications"] = {
    "task": "celery_workers.tasks.outreach.dispatch_due_verifications", "schedule": 30.0,
    "options": {"queue": "outreach"},
}


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
    if is_shutting_down() or not live_actions_enabled() or not await get_active_entitlement(db, workspace_id):
        await _set_inbox_job(db, job_id, workspace_id, "failed", error="Paid outreach access is unavailable")
        return {"status": "paid_access_required"}
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
        logger.error("Inbox sync job %s failed (%s)", job_id, type(exc).__name__)
        await _set_inbox_job(db, job_id, workspace_id, "failed", error="LinkedIn inbox sync failed")
        raise


@celery_app.task(name="celery_workers.tasks.outreach.send_inbox_reply", queue="outreach", acks_late=True)
def send_inbox_reply(job_id: str, workspace_id: str, account_id: str, thread_id: str, body: str | None = None) -> dict:
    return run_async(_send_inbox_reply(job_id, workspace_id, account_id, thread_id, body))


async def _send_inbox_reply(job_id: str, workspace_id: str, account_id: str, thread_id: str, body: str | None = None) -> dict:
    from outreach.core.manual_actions import ManualActions

    db = await _inbox_db()
    job = await db.outreach_manual_actions.find_one({"_id": job_id, "workspace_id": workspace_id})
    if not job or job.get("source") != "inbox_reply" or job.get("account_id") != account_id or job.get("target_id") != thread_id:
        return {"status": "unapproved_legacy_job"}
    return await ManualActions(db).run(workspace_id, job_id)

_SCAN_INTERVAL_SECONDS = max(10, int(os.environ.get("OUTREACH_SCAN_INTERVAL_SECONDS", "30")))
_BATCH_SIZE = max(1, int(os.environ.get("OUTREACH_SCAN_BATCH_SIZE", "50")))


@celery_app.task(name='celery_workers.tasks.outreach.monitor_sender_health', queue='outreach', acks_late=True)
def monitor_sender_health() -> dict:
    return run_async(_monitor_sender_health())


async def _monitor_sender_health(db=None) -> dict:
    if is_shutting_down():
        return {'status': 'shutting_down'}
    return await HealthMonitor(db if db is not None else await _inbox_db()).sweep(limit=100)

celery_app.conf.beat_schedule.update({
    'monitor-verified-sender-health': {
        'task': 'celery_workers.tasks.outreach.monitor_sender_health', 'schedule': 30.0, 'options': {'queue': 'outreach'},
    },
    "publish-durable-sequence-jobs": {
        "task": "celery_workers.tasks.outreach.publish_sequence_jobs", "schedule": 30.0, "options": {"queue": "outreach"},
    },
    "publish-durable-manual-outreach-actions": {
        "task": "celery_workers.tasks.outreach.publish_manual_actions", "schedule": 30.0, "options": {"queue": "outreach"},
    },
    "recover-durable-manual-outreach-actions": {
        "task": "celery_workers.tasks.outreach.recover_manual_actions", "schedule": 30.0, "options": {"queue": "outreach"},
    },
    "expire-paid-outreach-entitlements": {
        "task": "celery_workers.tasks.outreach.expire_entitlements",
        "schedule": 60.0,
        "options": {"queue": "outreach"},
    },
    "clean-stale-outreach-connections": {
        "task": "celery_workers.tasks.outreach.clean_stale_connections",
        "schedule": 60.0,
        "options": {"queue": "outreach"},
    },
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
    "scan-outreach-event-outbox": {
        "task": "celery_workers.tasks.outreach.scan_event_outbox",
        "schedule": 15.0,
        "options": {"queue": "outreach"},
    },
    "dispatch-due-outreach-deliveries": {
        "task": "celery_workers.tasks.outreach.dispatch_webhook_deliveries",
        "schedule": 15.0,
        "options": {"queue": "outreach"},
    },
    "sync-linkedin-inbox-replies": {
        "task": "celery_workers.tasks.outreach.periodic_inbox_sync",
        "schedule": 300.0,
        "options": {"queue": "outreach"},
    },
    "sync-priority-linkedin-inboxes": {
        "task": "celery_workers.tasks.outreach.sync_priority_inboxes",
        "schedule": 30.0,
        "options": {"queue": "outreach"},
    },
    "recover-outreach-execution-evidence": {
        "task": "celery_workers.tasks.outreach.recover_execution_intents",
        "schedule": 30.0,
        "options": {"queue": "outreach"},
    },
    "withdraw-stale-outreach-invitations": {
        "task": "celery_workers.tasks.outreach.withdraw_stale_invitations",
        "schedule": 3600.0,
        "options": {"queue": "outreach"},
    },
    "reap-stale-search-crawlers": {
        "task": "celery_workers.tasks.outreach.reap_stale_search_crawlers",
        "schedule": 120.0,
        "options": {"queue": "outreach"},
    },
})


@celery_app.task(name="celery_workers.tasks.outreach.publish_manual_actions", queue="outreach", acks_late=True)
def publish_manual_actions() -> dict:
    return run_async(_publish_manual_actions())


async def _publish_manual_actions() -> dict:
    from outreach.tasks.manual_actions import publish_due
    if is_shutting_down():
        return {"status": "shutting_down"}
    return await publish_due(await _inbox_db(), celery_app.send_task)


@celery_app.task(name="celery_workers.tasks.outreach.recover_manual_actions", queue="outreach", acks_late=True)
def recover_manual_actions() -> dict:
    return run_async(_recover_manual_actions())


async def _recover_manual_actions() -> dict:
    from outreach.tasks.manual_actions import recover_due
    if is_shutting_down():
        return {"status": "shutting_down"}
    return await recover_due(await _inbox_db())


@celery_app.task(name="celery_workers.tasks.outreach.expire_entitlements", queue="outreach", acks_late=True)
def expire_entitlements() -> dict:
    return run_async(_expire_entitlements())


async def _expire_entitlements(db=None) -> dict:
    from outreach.core.paid_access import expire_due_entitlements
    if is_shutting_down():
        return {"status": "shutting_down"}
    db = db or await _inbox_db()
    return {"expired": await expire_due_entitlements(db)}


@celery_app.task(name="celery_workers.tasks.outreach.clean_stale_connections", queue="outreach", acks_late=True)
def clean_stale_connections() -> dict:
    return run_async(_clean_stale_connections())


async def _clean_stale_connections(db=None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    db = db or await _inbox_db()
    await ConnectionRepair(db).sweep()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=15)
    overdue = {"$or": [{"created_at": {"$lt": cutoff}}, {"custody_expires_at": {"$lte": now}},
        {"created_at": {"$exists": False}, "custody_expires_at": {"$exists": False}}]}
    stale = await db.outreach_connection_jobs.find({"$and": [{"$or": [
        {"status": {"$in": ["queued", "running"]}, **overdue},
        {"status": "failed", "pending_cleanup_complete": False}]},
        {"$or": [{"next_custody_check_at": {"$exists": False}}, {"next_custody_check_at": {"$lte": now}}]}]
    }).sort([("next_custody_check_at", 1), ("id", 1)]).limit(100).to_list(length=100)
    count = 0
    for job in stale:
        scope = {"id": job["id"], "workspace_id": job["workspace_id"]}
        try:
            if job["status"] != "failed":
                claimed = await db.outreach_connection_jobs.update_one({**scope, **overdue, "status": job["status"],
                    "verification_owner_token": job.get("verification_owner_token"), "finalization_prepared": job.get("finalization_prepared")}, {
                    "$set": {"status": "failed", "pending_cleanup_complete": False,
                        "custody_started_at": job.get("custody_started_at") or job.get("created_at"),
                        "custody_expired_at": now, "error": "Verification timed out. Please retry.", "updated_at": now},
                    "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": "", "created_at": ""}})
                if not claimed.matched_count:
                    continue
            await ExecutionPermission(db).revoke(job["workspace_id"], job["sender_id"], "custody_guard", "connection_custody_expired")
            try:
                outcome = await ConnectionRepair(db).close_fence(job)
                proven = outcome.get("proven_uninstalled") or (outcome.get("account_absent")
                    and job.get("installation_protocol") == 2 and not job.get("finalization_prepared"))
                if not proven:
                    raise ValueError("Unproven legacy installation requires drained repair")
            except ValueError:
                await db.outreach_connection_jobs.update_one({**scope, "status": "failed", "pending_cleanup_complete": False}, {
                    "$set": {"status": "finalizing", "needs_operator_repair": True}, "$unset": {"created_at": ""}})
                continue
            if job.get("new_proxy_reservation"):
                await release_sender_reservation(db, job["workspace_id"], job["sender_id"], job["proxy_id"],
                    reservation_job_id=job["id"])
            if job.get("created_slot"):
                await db.outreach_sender_slots.delete_one({"workspace_id": job["workspace_id"], "sender_id": job["sender_id"],
                    "reservation_job_id": job["id"]})
            await db.outreach_connection_locks.delete_one({"_id": job["sender_id"], "workspace_id": job["workspace_id"], "job_id": job["id"]})
            await db.outreach_connection_jobs.update_one({**scope, "status": "failed", "pending_cleanup_complete": False}, {
                "$set": {"pending_cleanup_complete": True, "created_at": now}})
            count += 1
        except Exception as exc:
            logger.warning("Connection custody cleanup retained (%s)", type(exc).__name__)
        finally:
            await db.outreach_connection_jobs.update_one(scope, {"$set": {"next_custody_check_at": now + timedelta(minutes=1)}})
    return {"cleaned": count}


@celery_app.task(name="celery_workers.tasks.outreach.run_warmup_launches", queue="outreach", acks_late=True)
def run_warmup_launches() -> dict:
    return run_async(_run_warmup_launches())


async def _verify_auto_launch_senders(campaign: dict, db) -> None:
    """At the trigger, verify the selected session through its configured proxy."""
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
        material = await account_session(account)
        prepared = await prepare_proxy(proxy, workspace_id) if proxy.get("host") else None
        profile = await SessionAuthenticator.validate_session_cookie(
            **material,
            proxy_url=prepared.url if prepared else None,
            user_agent=account.get("user_agent"),
            request_envelope=RequestEnvelope(db, workspace_id, account_id, credential_generation(account), "verify",
                prepared.url if prepared else None, prepared_proxy=prepared),
        )
        if not profile.get("linkedin_urn") or profile["linkedin_urn"] != account.get("linkedin_urn"):
            raise RuntimeError("LinkedIn sender identity could not be re-verified")


async def _run_warmup_launches(db=None) -> dict:
    if not conditional_auto_launch_enabled() or not live_actions_enabled():
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
                "campaign_id": campaign_id, "workspace_id": workspace_id, "execution_state": {"$ne": "staged"},
            }), length=10001)
            from outreach.core.sequence_versions import load_sequence
            sequence = await load_sequence(db, workspace_id, campaign_id, campaign=campaign)
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
    """Persist a bounded batch of due steps for active campaigns."""
    return run_async(_run_due_steps())


async def _run_due_steps() -> dict:
    """Persist selection only; provider work belongs to per-job workers."""
    from outreach.tasks.sequence_dispatch import prepare_due
    return await prepare_due(await _inbox_db(), limit=_BATCH_SIZE)


@celery_app.task(name="celery_workers.tasks.outreach.publish_sequence_jobs", queue="outreach", acks_late=True)
def publish_sequence_jobs() -> dict:
    return run_async(_publish_sequence_jobs())


async def _publish_sequence_jobs() -> dict:
    from outreach.tasks.sequence_dispatch import publish_due
    return await publish_due(await _inbox_db(), celery_app.send_task, limit=_BATCH_SIZE)


@celery_app.task(name="celery_workers.tasks.outreach.execute_sequence_job", queue="outreach", acks_late=True,
                 reject_on_worker_lost=True)
def execute_sequence_job(workspace_id: str, job_id: str) -> dict:
    return run_async(_execute_sequence_job(workspace_id, job_id))


async def _execute_sequence_job(workspace_id: str, job_id: str) -> dict:
    from outreach.tasks.sequence_dispatch import execute_job
    return await execute_job(await _inbox_db(), workspace_id, job_id)


@celery_app.task(name="celery_workers.tasks.outreach.recover_execution_intents", queue="outreach", acks_late=True)
def recover_execution_intents() -> dict:
    return run_async(_recover_execution_intents())


async def _recover_execution_intents() -> dict:
    """Local-only recovery continues while provider actions are disabled."""
    if is_shutting_down():
        return {"checked": 0}
    from outreach.core.execution_recovery import recover_intent
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    records = await db.outreach_intents.find({"$and": [{"$or": [
        {"status": "in_flight", "claim_expires_at": {"$lte": now}},
        {"status": "executed", "projection_reconciled": {"$ne": True}},
        {"status": "unknown_outcome", "resolution": {"$exists": False}},
    ]}, {"$or": [{"next_recovery_due_at": {"$exists": False}}, {"next_recovery_due_at": {"$lte": now}}]}]}).sort([
        ("next_recovery_due_at", 1), ("_id", 1)]).limit(200).to_list(length=200)
    counts = {"checked": 0, "repaired": 0, "quarantined": 0}
    for record in records:
        if is_shutting_down():
            break
        try:
            # Rotate even missing or faulting projections so a failing prefix
            # cannot indefinitely hide later receipts or unknown submissions.
            await db.outreach_intents.update_one({"_id": record["_id"], "workspace_id": record["workspace_id"],
                "claim_token": record.get("claim_token"), "status": record["status"]},
                {"$set": {"next_recovery_due_at": now + timedelta(minutes=5)}})
            outcome = await recover_intent(db, record, now=now)
            counts["checked"] += 1
            if outcome in {"repaired", "quarantined"}:
                counts[outcome] += 1
        except Exception as exc:
            logger.warning("Execution recovery deferred (%s)", type(exc).__name__)
    return counts


@celery_app.task(name="celery_workers.tasks.outreach.sync_priority_inboxes", queue="outreach", acks_late=True)
def sync_priority_inboxes() -> dict:
    return run_async(_sync_priority_inboxes())


async def _sync_priority_inboxes() -> dict:
    from outreach.engine.inbox_sync import InboxSynchronizer
    if is_shutting_down() or not live_actions_enabled():
        return {"disabled": True}
    db = await _inbox_db()
    now = datetime.now(timezone.utc)
    accounts = await db.outreach_accounts.find({
        "status": "active", "priority_sync_due_at": {"$lte": now},
    }).limit(20).to_list(length=20)
    synced = 0
    for account in accounts:
        if is_shutting_down():
            break
        scope = {"id": account["id"], "workspace_id": account["workspace_id"],
                 "priority_sync_due_at": {"$lte": now}, "status": "active"}
        claim = await db.outreach_accounts.update_one(scope, {
            "$set": {"priority_sync_due_at": now + timedelta(minutes=5)},
        })
        if not claim.modified_count:
            continue
        try:
            result = await InboxSynchronizer(db, account["workspace_id"], account.get("user_id")).sync_account_inbox(account["id"])
            synced += int(bool(result.get("coverage_complete")))
        except Exception as exc:
            logger.error("Priority inbox sync failed (%s)", type(exc).__name__)
    return {"synced": synced}


@celery_app.task(name="celery_workers.tasks.outreach.scan_event_outbox", queue="outreach", acks_late=True)
def scan_event_outbox(batch_size: int = 50) -> dict:
    return run_async(_scan_event_outbox(batch_size=batch_size))


async def _scan_event_outbox(batch_size: int = 50, db=None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    db = db or await _inbox_db()
    from outreach.core.event_outbox import scan_and_fanout_outbox
    return await scan_and_fanout_outbox(db, batch_size=batch_size)


@celery_app.task(name="celery_workers.tasks.outreach.dispatch_webhook_deliveries", queue="outreach", acks_late=True)
def dispatch_webhook_deliveries(batch_size: int = 20) -> dict:
    return run_async(_dispatch_webhook_deliveries(batch_size=batch_size))


async def _dispatch_webhook_deliveries(batch_size: int = 20, db=None) -> dict:
    if is_shutting_down():
        return {"status": "shutting_down"}
    db = db or await _inbox_db()
    from outreach.core.webhook_delivery import dispatch_due_deliveries
    return await dispatch_due_deliveries(db, batch_size=batch_size)


@celery_app.task(name="celery_workers.tasks.outreach.periodic_inbox_sync", queue="outreach", acks_late=True)
def periodic_inbox_sync() -> dict:
    return run_async(_periodic_inbox_sync())


async def _periodic_inbox_sync(db=None) -> dict:
    """Periodic poll of active LinkedIn sender inboxes for prospect replies."""
    if is_shutting_down() or not live_actions_enabled():
        return {"status": "skipped", "reason": "live_actions_disabled"}
    db = db or await _inbox_db()
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.paid_access import get_active_entitlement

    active_senders = await db.outreach_accounts.find(
        {"status": "active"},
        {"workspace_id": 1, "user_id": 1, "id": 1},
    ).to_list(length=100)

    synced_accounts = 0
    total_replies = 0
    workspaces: dict[str, list[dict]] = {}
    for s in active_senders:
        ws_id = s.get("workspace_id")
        if ws_id:
            workspaces.setdefault(ws_id, []).append(s)

    for ws_id, senders in workspaces.items():
        if not await get_active_entitlement(db, ws_id):
            continue
        syncer = InboxSynchronizer(db, ws_id, senders[0].get("user_id", ""))
        for sender in senders:
            try:
                res = await syncer.sync_account_inbox(sender["id"])
                if res.get("synced_threads"):
                    synced_accounts += 1
                total_replies += res.get("new_replies_detected", 0)
            except Exception as exc:
                logger.warning("Periodic inbox sync error for sender %s: %s", sender["id"], exc)

    return {"synced_accounts": synced_accounts, "new_replies_detected": total_replies}


@celery_app.task(name="celery_workers.tasks.outreach.withdraw_stale_invitations", queue="outreach", acks_late=True)
def withdraw_stale_invitations() -> dict:
    return run_async(_withdraw_stale_invitations())


async def _withdraw_stale_invitations(db=None, redis_client=None) -> dict:
    """Periodic auto-withdrawal of stale sent invitations for opted-in senders."""
    if is_shutting_down():
        return {"status": "shutting_down", "processed_senders": 0, "total_withdrawn": 0}
    db = db or await _inbox_db()
    from outreach.core.safety_shield import SafetyShield

    cursor = db.outreach_accounts.find(
        {
            "auto_withdraw_enabled": True,
            "status": "active",
            "is_deleted": {"$ne": True},
        }
    )
    senders = await _fetch_cursor_docs(cursor, length=200)

    total_withdrawn = 0
    for sender in senders:
        sender_id = sender.get("id")
        workspace_id = sender.get("workspace_id")
        try:
            withdrawn = await SafetyShield.withdraw_stale_invitations(
                account_id=sender_id,
                db=db,
                workspace_id=workspace_id,
                redis_client=redis_client,
            )
            total_withdrawn += withdrawn
        except Exception as exc:
            logger.error("Auto-withdraw failed for sender %s: %s", sender_id, exc)

    return {"processed_senders": len(senders), "total_withdrawn": total_withdrawn}


@celery_app.task(name="celery_workers.tasks.outreach.crawl_page", queue="outreach", acks_late=True)
def crawl_page(job_id: str, cursor: int = 0, lease_token: str = "") -> dict:
    return run_async(_crawl_page(job_id, cursor, lease_token))


async def _crawl_page(job_id: str, cursor: int = 0, lease_token: str = "", db=None, redis_client=None) -> dict:
    """Discrete single-page search crawler. Fetches one page, lands leads in 'staged', and reschedules."""
    if is_shutting_down() or not live_actions_enabled():
        return {"status": "shutting_down"}

    import random
    from pymongo import ReturnDocument
    from outreach.core.lead_importer import build_lead_identifiers, check_compound_suppression
    from outreach.core.name_cleaner import clean_first_name
    from outreach.core.safety_shield import SafetyShield
    from outreach.engine.voyager_client import LinkedInVoyagerClient
    from outreach.models import LeadExecutionState, SearchImportJobStatus, SearchImportStopReason

    db = db if db is not None else await _inbox_db()

    page_owner = str(uuid.uuid4())
    claim_now = datetime.now(timezone.utc)
    # 1. Atomic claim: ensure job is queued or crawling and lease token matches
    claim_query = {
        "id": job_id, "cursor": cursor,
        "page_owner_token": None,
        "$or": [{"next_page_due_at": {"$lte": claim_now}}, {"next_page_due_at": {"$exists": False}}],
        "status": {"$in": [SearchImportJobStatus.QUEUED.value, SearchImportJobStatus.CRAWLING.value]},
    }
    if lease_token:
        claim_query["lease_token"] = lease_token

    job = await db.outreach_import_jobs.find_one_and_update(
        claim_query,
        {
            "$set": {
                "status": SearchImportJobStatus.CRAWLING.value,
                "page_owner_token": page_owner,
                "heartbeat_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not job:
        logger.info("Import job %s could not be claimed or is already stopped/completed.", job_id)
        return {"status": "job_not_found_or_cancelled"}

    active_lease_token = job.get("lease_token", lease_token)
    job_scope = {"id": job_id, "workspace_id": job["workspace_id"], "lease_token": active_lease_token, "page_owner_token": page_owner, "status": "crawling"}
    workspace_id = job.get("workspace_id")
    campaign_id = job.get("campaign_id")
    sender_id = job.get("sender_account_id")

    from outreach.core.search_sources import SearchSourceError, require_search_collection
    try:
        require_search_collection(job.get("search_url", ""))
    except SearchSourceError:
        stopped_at = datetime.now(timezone.utc)
        changed = await db.outreach_import_jobs.update_one(job_scope, {"$set": {
            "status": SearchImportJobStatus.STOPPED.value,
            "stop_reason": SearchImportStopReason.SOURCE_REVIEW_REQUIRED.value,
            "user_error_message": "This search source needs verification. Saved records are retained for review; use CSV or public profile URLs.",
            "completed_at": stopped_at, "updated_at": stopped_at}})
        return {"status": "stopped" if changed.matched_count else "job_changed",
                "reason": SearchImportStopReason.SOURCE_REVIEW_REQUIRED.value}

    # 2. Entitlement check
    if not await get_active_entitlement(db, workspace_id):
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.STOPPED.value,
                    "stop_reason": SearchImportStopReason.ENTITLEMENT_LOST.value,
                    "user_error_message": "Active paid outreach subscription required.",
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "entitlement_lost"}

    # 3. Sender validation
    sender = await db.outreach_accounts.find_one({
        "id": sender_id,
        "workspace_id": workspace_id,
        "is_deleted": {"$ne": True},
    })
    if not sender:
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.STOPPED.value,
                    "stop_reason": SearchImportStopReason.CANCELLED.value,
                    "user_error_message": "Sender account was removed or not found.",
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "sender_not_found"}

    if sender.get("status") in {"checkpoint_detected", "checkpoint", "reauth_required", "error"}:
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.STOPPED.value,
                    "stop_reason": SearchImportStopReason.CHECKPOINT.value,
                    "user_error_message": "Sender encountered a security checkpoint or error. Automation paused.",
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "sender_checkpoint"}

    # 4. Proxy verification - fail closed, never direct egress
    lease = await db.outreach_proxy_leases.find_one({
        "workspace_id": workspace_id,
        "sender_id": sender_id,
    })
    inventory = await db.outreach_proxy_inventory.find_one({"_id": lease["_id"]}) if lease else None
    if not lease or not inventory or inventory.get("status") != "available":
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.STOPPED.value,
                    "stop_reason": SearchImportStopReason.PROXY_UNHEALTHY.value,
                    "user_error_message": "Dedicated proxy lease is unavailable. Direct egress is blocked for safety.",
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "proxy_unavailable"}

    proxy = _proxy_from_inventory(inventory)
    prepared = await prepare_proxy(proxy, workspace_id)
    proxy_url = prepared.url

    # 6. Fetch search page from LinkedIn Voyager / mock
    material = await account_session(sender)

    async def validate_page(database=None):
        current = database if database is not None else db
        return None if await current.outreach_import_jobs.find_one(job_scope) else "search_job_changed"

    page_size = job.get("page_size", 10)
    voyager = LinkedInVoyagerClient(
        **material,
        proxy_url=proxy_url,
        user_agent=sender.get("user_agent"),
        request_envelope=RequestEnvelope(db, workspace_id, sender_id, credential_generation(sender), "search", proxy_url,
            prepared_proxy=prepared, authority_validator=validate_page, transaction_validator=validate_page),
    )
    try:
        search_res = await voyager.search_people_entities(
            search_url=job["search_url"], start=cursor, count=page_size)
    except RequestDenied as exc:
        await db.outreach_import_jobs.update_one(job_scope, {"$set": {
            "status": "queued", "next_page_due_at": datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after),
            "page_owner_token": None, "updated_at": datetime.now(timezone.utc), "defer_reason": exc.reason}})
        return {"status": "rescheduled", "retry_after": exc.retry_after, "reason": exc.reason}


    # 7. Check for stop reasons from network response
    stop_reason = search_res.get("stop_reason")
    if stop_reason:
        stop_reason_val = stop_reason.value if hasattr(stop_reason, "value") else str(stop_reason)
        user_msg = search_res.get("user_error_message") or "Search crawl stopped."
        if stop_reason in (SearchImportStopReason.CHECKPOINT, SearchImportStopReason.RATE_LIMITED, SearchImportStopReason.SESSION_EXPIRED):
            from outreach.core.circuit_breaker import CircuitBreaker
            from outreach.models import StopReason
            cb_reason = (
                StopReason.RATE_LIMITED_429 if stop_reason == SearchImportStopReason.RATE_LIMITED
                else StopReason.SESSION_EXPIRED if stop_reason == SearchImportStopReason.SESSION_EXPIRED
                else StopReason.SECURITY_CHALLENGE_999
            )
            await CircuitBreaker.trip_circuit_breaker(
                sender_id=sender["id"],
                reason=cb_reason,
                db=db,
                workspace_id=workspace_id,
                error_details=user_msg,
                cooldown_hours=24 if stop_reason == SearchImportStopReason.RATE_LIMITED else 0,
            )
        if stop_reason == SearchImportStopReason.SEARCH_EXHAUSTED:
            final_status = SearchImportJobStatus.COMPLETED.value
        elif stop_reason == SearchImportStopReason.SESSION_EXPIRED:
            final_status = SearchImportJobStatus.FAILED.value
        else:
            final_status = SearchImportJobStatus.STOPPED.value

        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": final_status,
                    "stop_reason": stop_reason_val,
                    "user_error_message": user_msg,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {
            "status": final_status,
            "stop_reason": stop_reason_val,
            "reason": stop_reason_val,
        }

    # 8. Clamping & target count setup on page 1 (cursor == 0)
    target_count = job.get("target_count", 100)
    if cursor == 0:
        total_results = search_res.get("total_results", 0)
        max_cap = 2500 if job.get("search_type") == "sales_nav" else 1000
        target_count = min(target_count, total_results, max_cap) if total_results > 0 else min(target_count, max_cap)
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "total_available": total_results,
                    "target_count": target_count,
                }
            },
        )

    # 9. Process entities: suppression checks & name cleaning
    entities = search_res.get("entities", [])
    new_staged = 0
    duplicates_count = 0
    dnc_count = 0
    withdrawn_count = 0
    unresolvable_count = 0
    now = datetime.now(timezone.utc)
    current_imported = job.get("leads_imported", 0)

    for ent in entities:
        if await validate_page():
            return {"status": "job_changed"}
        if ent.get("is_unresolvable"):
            unresolvable_count += 1
            continue

        ident = build_lead_identifiers(
            raw_url=ent.get("profile_url"),
            member_urn=ent.get("member_urn"),
            sales_lead_urn=ent.get("sales_lead_urn"),
            vanity_name=ent.get("vanity_name"),
        )

        # Compound DNC suppression
        dnc_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=[ident],
            db=db,
            collection_name="outreach_do_not_contact",
        )
        if dnc_matches:
            dnc_count += 1
            continue

        # Existing leads suppression (in same campaign or workspace leads)
        lead_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=[ident],
            db=db,
            collection_name="outreach_leads",
            extra_filter={"campaign_id": campaign_id, "is_deleted": {"$ne": True}},
        )
        if lead_matches:
            duplicates_count += 1
            continue

        # Withdrawn invites 21-day cooldown suppression
        withdrawn_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=[ident],
            db=db,
            collection_name="outreach_withdrawn_invites",
            extra_filter={"cooldown_until": {"$gt": now}},
        )
        if withdrawn_matches:
            withdrawn_count += 1
            continue

        cleaned_first = clean_first_name(ent.get("first_name", ""))
        lead_doc = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "campaign_id": campaign_id,
            "first_name": cleaned_first,
            "last_name": ent.get("last_name", ""),
            "company_name": ent.get("company_name", ""),
            "job_title": ent.get("job_title", ""),
            "linkedin_url": ent.get("profile_url", ""),
            "email": ent.get("email"),
            "location": ent.get("location", ""),
            "headline": ent.get("headline", ""),
            "identifiers": ident.model_dump(),
            "execution_state": LeadExecutionState.STAGED.value,
            "import_job_id": job_id,
            "staged_at": now,
            "created_at": now,
            "updated_at": now,
        }
        await db.outreach_leads.insert_one(lead_doc)
        new_staged += 1

        if (current_imported + new_staged) >= target_count:
            break

    # 10. Increment progress counters
    new_cursor = cursor + len(entities)
    updated_job = await db.outreach_import_jobs.find_one_and_update(
        job_scope,
        {
            "$inc": {
                "leads_imported": new_staged,
                "duplicates_skipped": duplicates_count,
                "dnc_suppressed": dnc_count,
                "withdrawn_cooldown_skipped": withdrawn_count,
                "unresolvable_skipped": unresolvable_count,
                "pages_scanned": 1,
            },
            "$set": {
                "cursor": new_cursor,
                "heartbeat_at": now,
                "updated_at": now,
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    total_imported = updated_job.get("leads_imported", 0) if updated_job else (current_imported + new_staged)

    # 11. Check termination conditions
    if total_imported >= target_count:
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.COMPLETED.value,
                    "stop_reason": SearchImportStopReason.COMPLETED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "completed", "leads_imported": total_imported}

    if len(entities) == 0:
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.COMPLETED.value,
                    "stop_reason": SearchImportStopReason.SEARCH_EXHAUSTED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "completed", "reason": "search_exhausted", "leads_imported": total_imported}

    if len(entities) < page_size:
        await db.outreach_import_jobs.update_one(
            job_scope,
            {
                "$set": {
                    "status": SearchImportJobStatus.COMPLETED.value,
                    "stop_reason": SearchImportStopReason.SEARCH_EXHAUSTED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return {"status": "completed", "reason": "short_page_exhausted", "leads_imported": total_imported}

    # Stored due times survive broker failure; beat publishes only due references.
    pacing_delay = random.randint(10, 20)
    await db.outreach_import_jobs.update_one(job_scope, {"$set": {
        "status": "queued", "next_page_due_at": datetime.now(timezone.utc) + timedelta(seconds=pacing_delay),
        "page_owner_token": None, "updated_at": datetime.now(timezone.utc)}})
    return {"status": "next_page_scheduled", "cursor": new_cursor, "leads_imported": total_imported}


@celery_app.task(name="celery_workers.tasks.outreach.dispatch_due_search_pages", queue="outreach", acks_late=True)
def dispatch_due_search_pages() -> dict:
    return run_async(_dispatch_due_search_pages())


async def _dispatch_due_search_pages(db=None) -> dict:
    """Publish due read-page references; duplicates are fenced by page ownership."""
    if is_shutting_down() or not live_actions_enabled():
        return {"disabled": True, "published": 0}
    db = db or await _inbox_db()
    now = datetime.now(timezone.utc)
    jobs = await db.outreach_import_jobs.find({"status": "queued", "page_owner_token": None,
        "next_page_due_at": {"$lte": now}}).limit(50).to_list(length=50)
    published = 0
    for job in jobs:
        if is_shutting_down():
            break
        try:
            crawl_page.delay(job["id"], job.get("cursor", 0), job["lease_token"])
            published += 1
        except Exception as exc:
            logger.warning("Due search page publication failed (%s)", type(exc).__name__)
    return {"published": published}


celery_app.conf.beat_schedule["dispatch-due-outreach-search-pages"] = {
    "task": "celery_workers.tasks.outreach.dispatch_due_search_pages", "schedule": 30.0,
    "options": {"queue": "outreach"},
}


@celery_app.task(name="celery_workers.tasks.outreach.reap_stale_search_crawlers", queue="outreach", acks_late=True)
def reap_stale_search_crawlers() -> dict:
    return run_async(_reap_stale_search_crawlers())


async def _reap_stale_search_crawlers(db=None) -> dict:
    """Watchdog that detects dropped tasks / crashed workers and cleanly resumes their import jobs."""
    if is_shutting_down():
        return {"status": "shutting_down", "reaped": 0}
    db = db or await _inbox_db()

    stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=180)
    cursor = db.outreach_import_jobs.find({
        "status": "crawling",
        "heartbeat_at": {"$lt": stale_cutoff},
    })
    stale_jobs = await _fetch_cursor_docs(cursor, length=50)
    reaped = 0

    for job in stale_jobs:
        job_id = job["id"]
        new_lease = str(uuid.uuid4())
        res = await db.outreach_import_jobs.update_one(
            {
                "id": job_id,
                "workspace_id": job["workspace_id"], "page_owner_token": job.get("page_owner_token"),
                "cursor": job.get("cursor", 0), "heartbeat_at": job.get("heartbeat_at"),
                "status": "crawling",
                "lease_token": job.get("lease_token"),
            },
            {
                "$set": {
                    "lease_token": new_lease,
                    "page_owner_token": None, "status": "queued",
                    "next_page_due_at": datetime.now(timezone.utc),
                    "heartbeat_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if res.modified_count:
            reaped += 1
            logger.info("Resumed stale search import job %s from cursor %s", job_id, job.get("cursor", 0))

    return {"reaped": reaped}


@celery_app.task(name="celery_workers.tasks.outreach.process_due_inbox_reminders", queue="outreach", acks_late=True)
def process_due_inbox_reminders() -> dict:
    return run_async(_process_due_inbox_reminders())


async def _process_due_inbox_reminders(db=None) -> dict:
    """Process due `outreach_inbox_reminders` records and mark their threads as due for follow-up."""
    if is_shutting_down():
        return {"status": "shutting_down", "triggered": 0}
    db = db or await _inbox_db()
    now = datetime.now(timezone.utc)
    if not hasattr(db, "outreach_inbox_reminders"):
        return {"triggered": 0}
    cursor = db.outreach_inbox_reminders.find({
        "status": "pending",
        "remind_at": {"$lte": now},
    })
    due_reminders = await _fetch_cursor_docs(cursor, length=100)
    triggered = 0
    for rem in due_reminders:
        rem_id = rem.get("id")
        ws_id = rem.get("workspace_id")
        thread_id = rem.get("thread_id")
        if not rem_id or not ws_id:
            continue
        claimed = await db.outreach_inbox_reminders.update_one(
            {"id": rem_id, "workspace_id": ws_id, "status": "pending"},
            {"$set": {"status": "triggered", "triggered_at": now, "updated_at": now}},
        )
        if getattr(claimed, "modified_count", 0) == 0:
            continue
        triggered += 1
        if thread_id and hasattr(db, "outreach_inbox_threads"):
            await db.outreach_inbox_threads.update_one(
                {"id": thread_id, "workspace_id": ws_id},
                {
                    "$set": {
                        "has_due_reminder": True,
                        "reminder_note": rem.get("note") or "",
                        "reminder_triggered_at": now,
                        "updated_at": now,
                    }
                },
            )
        user_id = rem.get("user_id")
        if user_id and hasattr(db, "notifications"):
            try:
                await db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "workspace_id": ws_id,
                    "type": "outreach_inbox_reminder",
                    "title": "Follow-up reminder due",
                    "message": rem.get("note") or "A scheduled Outreach inbox reminder is due for follow-up.",
                    "thread_id": thread_id,
                    "is_read": False,
                    "created_at": now,
                })
            except Exception as exc:
                logger.debug("Inbox reminder notification insert skipped (%s)", type(exc).__name__)
    return {"triggered": triggered}


celery_app.conf.beat_schedule["process-due-outreach-inbox-reminders"] = {
    "task": "celery_workers.tasks.outreach.process_due_inbox_reminders",
    "schedule": 60.0,
    "options": {"queue": "outreach"},
}
celery_app.conf.beat_schedule["scan-outreach-event-outbox"] = {
    "task": "celery_workers.tasks.outreach.scan_event_outbox",
    "schedule": 30.0,
    "options": {"queue": "outreach"},
}
celery_app.conf.beat_schedule["dispatch-outreach-webhook-deliveries"] = {
    "task": "celery_workers.tasks.outreach.dispatch_webhook_deliveries",
    "schedule": 30.0,
    "options": {"queue": "outreach"},
}
