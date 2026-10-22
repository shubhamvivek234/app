"""Queue session verification without calling LinkedIn in the API process."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import os
import logging

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from outreach.core.session_custody import seal_pending
from outreach.core.connection_storage_repair import storage_account_digest
from outreach.core import suppression
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.inbox_freshness import credential_generation
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.managed_proxy import (
    ManagedProxyUnavailable, release_sender_reservation, reserve_sender_proxy,
)
from outreach.core.paid_access import get_active_entitlement, live_actions_enabled
from outreach.engine.session_authenticator import _clean_cookie_token

logger = logging.getLogger(__name__)


def _enqueue_connection_job(job_id: str, workspace_id: str, trace_id: str) -> None:
    # Broker arguments contain identifiers only, never session values.
    from celery_workers.tasks.outreach import verify_sender_connection
    verify_sender_connection.delay(job_id, workspace_id, trace_id)


async def queue_connection(req, current_user: dict, db) -> dict:
    if getattr(req, 'connection_scope_digest', None) is not None:
        from outreach.core.sender_verification_recovery import verify_recovery_context
        verify_recovery_context(current_user, req.connection_scope_digest)
    if not live_actions_enabled():
        raise HTTPException(status_code=503, detail="Live outreach connection is not enabled for this pilot")
    if os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}:
        raise HTTPException(status_code=503, detail="Mock LinkedIn authentication cannot connect a paid sender")
    user_id = current_user.get("user_id")
    workspace_id = current_user.get("default_workspace_id") or user_id
    entitlement = await get_active_entitlement(db, workspace_id)
    if not entitlement:
        raise HTTPException(status_code=402, detail="A verified paid outreach sender seat is required")
    country_code = req.country_code.upper()
    li_at = _clean_cookie_token(req.li_at, "li_at")
    csrf = _clean_cookie_token(req.jsession_id, "JSESSIONID")
    if not li_at or not csrf:
        raise HTTPException(status_code=400, detail="LinkedIn li_at and JSESSIONID values are required")

    reconnect_target = None
    if req.reconnect_account_id:
        reconnect_target = await db.outreach_accounts.find_one({
            "id": req.reconnect_account_id, "workspace_id": workspace_id,
        })
        if not reconnect_target:
            raise HTTPException(status_code=404, detail="Sender account not found")
        if reconnect_target.get("country_code") != country_code:
            raise HTTPException(status_code=409, detail="A sender's proxy country cannot be changed during reconnection")

    sender_id = reconnect_target["id"] if reconnect_target else str(uuid4())
    job_id = str(uuid4())
    captured_at = datetime.now(timezone.utc)
    created_slot = False
    reserved_proxy_id = None
    locked = False
    insert_attempted = False
    try:
        slot = await db.outreach_sender_slots.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
        }) if reconnect_target else None
        if not slot:
            for number in range(1, int(entitlement["seats"]) + 1):
                try:
                    await db.outreach_sender_slots.insert_one({
                        "_id": f"{workspace_id}:{number}", "workspace_id": workspace_id,
                        "sender_id": sender_id, "created_at": captured_at, "reservation_job_id": job_id,
                    })
                    created_slot = True
                    break
                except DuplicateKeyError:
                    continue
            if not created_slot:
                raise HTTPException(status_code=409, detail="All paid sender seats are assigned")

        try:
            await db.outreach_connection_locks.insert_one({
                "_id": sender_id, "workspace_id": workspace_id, "job_id": job_id,
                "created_at": datetime.now(timezone.utc),
                "custody_expires_at": captured_at + timedelta(minutes=15),
                "installation_protocol": 2, "storage_protocol": 1,
            })
            locked = True
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail="Sender verification is already in progress") from exc

        prior_lease = await db.outreach_proxy_leases.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
        })
        proxy = await reserve_sender_proxy(db, workspace_id, sender_id, country_code, reservation_job_id=job_id)
        if not prior_lease or prior_lease.get("_id") != proxy.proxy_id:
            reserved_proxy_id = proxy.proxy_id
        storage_proof = {"base_account_digest": storage_account_digest(reconnect_target),
            "proxy_id": proxy.proxy_id, "created_slot": created_slot,
            "new_proxy_reservation": bool(reserved_proxy_id), "country_code": country_code}
        async def preserve_storage_proof(current):
            fenced = (AuthorityDatabase(current.database, current.session, job_id)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            base = await fenced.outreach_accounts.find_one({"workspace_id": workspace_id, "id": sender_id})
            if storage_account_digest(base) != storage_proof["base_account_digest"]:
                raise HTTPException(409, "Sender changed before encrypted session storage")
            lock = await fenced.outreach_connection_locks.find_one({"_id": sender_id, "workspace_id": workspace_id, "job_id": job_id})
            if not lock:
                raise HTTPException(409, "Connection owner changed before encrypted storage")
            changed = await current.outreach_connection_locks.update_one({"_id": sender_id,
                "workspace_id": workspace_id, "job_id": job_id, "storage_protocol": 1}, {"$set": {"storage_proof": storage_proof}})
            if changed.matched_count != 1:
                raise HTTPException(409, "Connection storage reference changed")
        await suppression.mutate_suppression(db, workspace_id, preserve_storage_proof)
        encrypted = await seal_pending({"li_at": li_at, "jsession_id": csrf,
            "li_a": _clean_cookie_token(req.li_a, "li_a") if req.li_a else ""}, workspace_id, sender_id, job_id)
        if datetime.now(timezone.utc) >= captured_at + timedelta(minutes=15):
            raise HTTPException(409, "Session custody expired before storage; reconnect")
        record = {
            "id": job_id, "workspace_id": workspace_id, "user_id": user_id,
            "sender_id": sender_id, "reconnect": bool(reconnect_target),
            "installation_protocol": 2,
            "base_credential_generation": (reconnect_target or {}).get("credential_generation"),
            "base_sender_generation": credential_generation(reconnect_target) if reconnect_target else None,
            "created_slot": created_slot, "new_proxy_reservation": bool(reserved_proxy_id),
            "proxy_id": proxy.proxy_id, "country_code": country_code,
            "premium_product": req.premium_product or "classic",
            "user_agent": req.user_agent or "",
            **encrypted,
            "status": "queued", "trace_id": job_id,
            "created_at": captured_at, "custody_expires_at": captured_at + timedelta(minutes=15),
            "next_verification_due_at": datetime.now(timezone.utc),
        }
        async def save(current):
            nonlocal insert_attempted
            fenced = (AuthorityDatabase(current.database, current.session, job_id)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            if (not live_actions_enabled() or not await get_active_entitlement(fenced, workspace_id)
                    or datetime.now(timezone.utc) >= record["custody_expires_at"]):
                raise HTTPException(409, "Paid access or session custody changed before storage")
            if not await fenced.outreach_connection_locks.find_one({"_id": sender_id, "workspace_id": workspace_id, "job_id": job_id}):
                raise HTTPException(409, "Connection owner changed before storage")
            base = await fenced.outreach_accounts.find_one({"workspace_id": workspace_id, "id": sender_id})
            if storage_account_digest(base) != storage_proof["base_account_digest"]:
                raise HTTPException(409, "Sender changed before storage")
            if await fenced.outreach_connection_jobs.find_one({"id": job_id, "workspace_id": workspace_id}):
                raise HTTPException(409, "Connection storage was already closed or saved")
            insert_attempted = True
            await current.outreach_connection_jobs.insert_one(record)
        await suppression.mutate_suppression(db, workspace_id, save)
        try:
            _enqueue_connection_job(job_id, workspace_id, job_id)
        except Exception as exc:
            # MongoDB remains the durable publisher authority during broker outage.
            logger.warning("Connection publication deferred (%s)", type(exc).__name__)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        if insert_attempted:
            # A transaction acknowledgement can be lost after commit, while
            # the due publisher claims the job. That is not proof of non-insert
            # or never-installed credentials. Keep job-bound resources intact.
            try:
                saved = await db.outreach_connection_jobs.find_one({"id": job_id,
                    "workspace_id": workspace_id, "sender_id": sender_id})
                if saved:
                    return {"job_id": job_id, "status": saved["status"]}
                await db.outreach_connection_locks.update_one({"_id": sender_id,
                    "workspace_id": workspace_id, "job_id": job_id}, {"$set": {
                        "storage_outcome_unknown": True, "needs_operator_repair": True}})
            except Exception as lock_exc:
                # Original durable lock/slot/lease references remain held.
                logger.error("Connection lock repair flag update failed for job=%s (%s)", job_id, type(lock_exc).__name__)
            raise HTTPException(503, "Session storage requires operator review; reference " + job_id) from None
        if locked:
            await db.outreach_connection_locks.delete_one({"_id": sender_id, "job_id": job_id})
        if reserved_proxy_id:
            await release_sender_reservation(db, workspace_id, sender_id, reserved_proxy_id, reservation_job_id=job_id)
        if created_slot:
            await db.outreach_sender_slots.delete_one({"workspace_id": workspace_id, "sender_id": sender_id, "reservation_job_id": job_id})
        await db.outreach_connection_jobs.delete_one({"id": job_id, "workspace_id": workspace_id, "status": "queued"})
        if isinstance(exc, ManagedProxyUnavailable):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if isinstance(exc, (CustodyUnavailable, suppression.SuppressionUnavailable)):
            raise HTTPException(503, "Encrypted session custody is unavailable; reconnect after operator review") from None
        raise
