"""Fail-closed paid access for the invite-only outreach pilot.

Only an operator with a verified external invoice can activate access. A
customer-facing API must never create or extend an entitlement.
"""
from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
import os
from pymongo.errors import DuplicateKeyError


PRICE_USD_PER_SENDER_MONTH = 59
PILOT_MAX_SENDERS = 5


def live_actions_enabled() -> bool:
    """Explicit operator go/no-go for unofficial session-based actions."""
    return os.getenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false").lower() in {"1", "true"}


def _utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def entitlement_is_active(doc: dict[str, Any] | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return bool(
        doc and doc.get("status") == "active" and not doc.get("is_revoked")
        and 1 <= int(doc.get("seats") or 0) <= PILOT_MAX_SENDERS
        and (paid_through := _utc(doc.get("paid_through"))) is not None
        and paid_through > now
        and doc.get("payment_source") == "manual_verified_invoice"
    )


async def get_active_entitlement(db, workspace_id: str, now: datetime | None = None) -> dict | None:
    from outreach.core.erasure import workspace_is_open
    if not await workspace_is_open(db, workspace_id):
        return None
    doc = await db.outreach_entitlements.find_one({"workspace_id": workspace_id})
    return doc if entitlement_is_active(doc, now) else None


async def claim_invoice_reference(db: AsyncIOMotorDatabase, invoice_id: str, workspace_id: str, seats: int,
                                  paid_through: datetime, *, session: AsyncIOMotorClientSession | None = None,
                                  reject_restore_blocked: bool = False) -> None:
    """Permanent digest authority survives receipt erasure/retention release.

    Reservation precedes receipt/entitlement writes. An interrupted claim can
    only retry its original terms; it never grants access by itself.
    """
    from outreach.core.authorization import canonical_hash
    from pymongo.read_concern import ReadConcern
    from pymongo.write_concern import WriteConcern
    identity = canonical_hash(["verified_invoice", invoice_id])
    if not isinstance(workspace_id, str) or not workspace_id or type(seats) is not int or not 1 <= seats <= PILOT_MAX_SENDERS:
        raise ValueError("Invoice workspace and pilot seat binding are required")
    term = _utc(paid_through)
    if term is None:
        raise ValueError("Invoice paid-through term is required")
    term = term.replace(microsecond=term.microsecond // 1000 * 1000)
    binding = canonical_hash([workspace_id, seats, term])
    collection = db.account_invoice_guards.with_options(
        read_concern=ReadConcern("majority"), write_concern=WriteConcern("majority"))
    try:
        update = {"$setOnInsert": {"binding_digest": binding}}
        if session is not None:
            update["$inc"] = {"dispatch_fence_revision": 1}
        await collection.update_one({"_id": identity}, update, upsert=True, session=session)
    except DuplicateKeyError:
        if session is not None:
            raise  # An aborted transaction must be retried as a complete group.
    saved = await collection.find_one({"_id": identity}, session=session)
    if (not saved or saved.get("binding_digest") != binding
            or "restore_reuse_blocked" in saved and saved["restore_reuse_blocked"] is not True):
        raise ValueError("Invoice ID has already been used for different or unproven payment terms")
    if reject_restore_blocked and saved.get("restore_reuse_blocked") is True:
        raise ValueError("Invoice reference is restore-blocked; paid access requires separate reconciliation")


async def record_verified_payment(
    db, workspace_id: str, invoice_id: str, verified_by: str, seats: int,
    paid_through: datetime, *, now: datetime | None = None,
) -> dict:
    """Operator-only service; not exposed on a public or customer API."""
    final_clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    now = now or datetime.now(timezone.utc)
    invoice_id = invoice_id.strip()
    verified_by = verified_by.strip()
    if not workspace_id or not invoice_id or not verified_by:
        raise ValueError("Workspace, verified invoice, and operator are required")
    from outreach.core.erasure import workspace_is_open
    from outreach.core import restore_epoch as epoch
    captured = epoch.policy()
    if not await workspace_is_open(db, workspace_id):
        raise ValueError("Workspace is closed for erasure")
    if type(seats) is not int or not 1 <= seats <= PILOT_MAX_SENDERS:
        raise ValueError("Pilot seat count must be between 1 and 5")
    paid_through = _utc(paid_through)
    if paid_through is None or paid_through <= now:
        raise ValueError("Paid-through date must be in the future")
    paid_through = paid_through.replace(microsecond=paid_through.microsecond // 1000 * 1000)
    request = await db.outreach_access_requests.find_one({"workspace_id": workspace_id})
    country_code = (request or {}).get("country_code")
    if not country_code:
        raise ValueError("A country-specific paid access request is required before activation")
    if request.get("seats") != seats:
        raise ValueError("The verified seat count must match the access request")
    available = await db.outreach_proxy_inventory.count_documents({
        "last_workspace_id": workspace_id, "country_code": country_code,
        "status": "available", "provider": "iproyal_static",
        "expires_at": {"$gte": paid_through},
    })
    from outreach.core.webshare_provisioning import managed_webshare_valid
    candidates = await db.outreach_proxy_inventory.find({
        'workspace_id': workspace_id, 'last_workspace_id': workspace_id, 'country_code': country_code,
        'provider': 'webshare_plan', 'status': 'available', 'expires_at': {'$gte': paid_through},
    }).to_list(length=100)
    for candidate in candidates:
        if await managed_webshare_valid(db, candidate, workspace_id, now=now):
            available += 1
    if available < seats:
        raise ValueError("Import enough country-matched IPs covering the paid term before taking payment")
    occupied = await db.outreach_sender_slots.count_documents({"workspace_id": workspace_id})
    if occupied > seats:
        raise ValueError("Existing sender assignments exceed the requested seat count")

    # Capacity preparation above is deliberately not a complete provider/financial
    # reconciliation. Final financial writes share restore/erasure ordering.
    from outreach.core import suppression, restore_epoch as epoch
    from outreach.core.restore_exclusions import raw_database
    async def finalize(current):
        from outreach.core.dispatch_authority import AuthorityDatabase
        authority = (AuthorityDatabase(current.database, current.session, 'verified_payment')
                     if isinstance(current, suppression.SuppressionDatabase) else current)
        proof = await epoch.positive(authority, workspace_id, captured=captured)
        current_request = await authority.outreach_access_requests.find_one({'workspace_id': workspace_id})
        if (not current_request or current_request.get('_id') != request.get('_id')
                or current_request.get('country_code') != country_code or current_request.get('seats') != seats):
            raise ValueError('Paid access request changed before payment finalization')
        existing = await authority.outreach_entitlements.find_one({'workspace_id': workspace_id})
        raw, options = raw_database(current)
        # Global receipt lookup is only for permanent invoice exclusion/backfill.
        prior = await raw.outreach_payment_receipts.find_one({'_id': invoice_id}, **options)
        if not prior and epoch.stable(current_request) != epoch.stable(request):
            raise ValueError('Paid access request changed before payment finalization')
        if prior:
            prior = await authority.outreach_payment_receipts.find_one({
                '_id': invoice_id, 'workspace_id': prior['workspace_id']})
            if not prior: raise ValueError('Original invoice receipt changed')
            await claim_invoice_reference(raw, invoice_id, prior['workspace_id'], prior['seats'],
                                          prior['paid_through'], **options)
        await claim_invoice_reference(raw, invoice_id, workspace_id, seats, paid_through,
                                      reject_restore_blocked=True, **options)
        if prior:
            if (prior.get('workspace_id') != workspace_id or prior.get('seats') != seats
                    or _utc(prior.get('paid_through')) != paid_through):
                raise ValueError('Invoice ID has already been used for different payment terms')
            if (not existing or existing.get('last_invoice_id') != invoice_id or existing.get('seats') != seats
                    or _utc(existing.get('paid_through')) != paid_through
                    or existing.get('payment_source') != 'manual_verified_invoice'):
                raise ValueError('Invoice receipt exists but entitlement needs operator reconciliation')
            # Report exactly the current state, including expired/revoked; never reactivate it.
            proof.assert_live()
            return existing
        if existing and existing.get('is_revoked'):
            raise ValueError('Revoked paid access requires separate operator reconciliation')
        if paid_through <= final_clock():
            raise ValueError('Paid-through date expired before finalization')
        receipt = {'_id': invoice_id, 'workspace_id': workspace_id,
            'verified_by': verified_by, 'verified_at': now,
            'seats': seats, 'paid_through': paid_through,
            'amount_usd_expected': PRICE_USD_PER_SENDER_MONTH * seats, 'source': 'manual_verified_invoice'}
        await current.outreach_payment_receipts.insert_one(receipt)
        updates = {'status': 'active', 'seats': seats, 'paid_through': paid_through,
            'price_usd_per_sender_month': PRICE_USD_PER_SENDER_MONTH,
            'payment_source': 'manual_verified_invoice', 'last_invoice_id': invoice_id,
            'cancel_at_period_end': False, 'updated_at': now}
        await current.outreach_entitlements.update_one({'workspace_id': workspace_id},
            {'$set': updates, '$setOnInsert': {'created_at': now}}, upsert=True)
        await current.outreach_access_requests.update_one({'workspace_id': workspace_id},
            {'$set': {'status': 'fulfilled', 'fulfilled_at': now}})
        proof.assert_live()
        if paid_through <= final_clock():
            raise ValueError('Paid-through date expired before finalization')
        return {'workspace_id': workspace_id, **updates}
    return await suppression.mutate_suppression(db, workspace_id, finalize)


async def expire_due_entitlements(db, *, now: datetime | None = None, limit: int = 100) -> int:
    """Stop all active work at paid-through; retain provider IP until its term ends."""
    now = now or datetime.now(timezone.utc)
    due = await db.outreach_entitlements.find({
        "paid_through": {"$lte": now},
        "$or": [
            {"status": "active"},
            {"status": "expired", "expiry_cleanup_completed_at": {"$exists": False}},
        ],
    }).to_list(length=limit)
    expired = 0
    for doc in due:
        workspace_id = doc["workspace_id"]
        if doc.get("status") == "active":
            changed = await db.outreach_entitlements.update_one(
                {"workspace_id": workspace_id, "status": "active", "paid_through": {"$lte": now}},
                {
                    "$set": {"status": "expired", "expired_at": now, "updated_at": now},
                    "$unset": {"expiry_cleanup_completed_at": ""},
                },
            )
            if not changed.modified_count:
                continue
            expired += 1
        await db.outreach_campaigns.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["active", "warming_up"]}},
            {"$set": {"status": "paused", "auto_launch_enabled": False, "updated_at": now},
             "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "billing_expired"}},
        )
        await db.outreach_accounts.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["active", "warming", "paused"]}},
            {"$set": {"status": "reauth_required", "updated_at": now}},
        )
        await db.outreach_accounts.update_many(
            {"workspace_id": workspace_id, "connection_finalization": {"$exists": True}},
            {"$set": {"connection_finalization.state": "closed", "connection_finalization.closed_at": now}},
        )
        await db.outreach_accounts.update_many(
            {"workspace_id": workspace_id},
            {"$unset": {"session_cookie_enc": "", "encrypted_session_cookie": "", "jsession_id": "", "li_a_enc": "", "li_at_enc": "", "jsession_id_enc": ""}},
        )
        # Mailbox OAuth access is tied to the same paid sender seat. Keep the
        # mailbox record for a future reconnect, but do not retain usable
        # credentials or an in-flight authorization after the paid term ends.
        from outreach.core import suppression
        from outreach.core.mailbox_jobs import stop_connection_jobs, _fenced
        async def stop_mailboxes(current):
            entitlement = await _fenced(current, "paid-mailbox-stop").outreach_entitlements.find_one({
                "workspace_id": workspace_id, "status": "expired", "paid_through": {"$lte": now}})
            if not entitlement: return
            await current.outreach_mailboxes.update_many({"workspace_id": workspace_id}, {
                "$set": {"status": "reauth_required", "updated_at": now},
                "$unset": {"access_token_enc": "", "refresh_token_enc": ""}})
            await stop_connection_jobs(current, workspace_id, now=now, error="Paid sender access has ended")
            states = await current.outreach_mailbox_oauth_states.find({"workspace_id": workspace_id}).limit(101).to_list(length=101)
            if len(states) > 100:
                raise ValueError("Mailbox authorization cleanup requires bounded operator review")
            for state in states:
                await current.outreach_mailbox_oauth_states.delete_one({"workspace_id": workspace_id, "_id": state["_id"]})
        await suppression.mutate_suppression(db, workspace_id, stop_mailboxes)
        await db.outreach_tasks.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["queued", "pending", "scheduled"]}},
            {"$set": {"status": "cancelled", "cancellation_reason": "Paid outreach period ended", "updated_at": now}},
        )
        pending_jobs = await db.outreach_connection_jobs.find({
            "workspace_id": workspace_id, "status": {"$in": ["queued", "running", "finalizing", "repairing"]},
        }).to_list(length=1000)
        for job in pending_jobs:
            from outreach.core.connection_repair import ConnectionRepair
            repair = ConnectionRepair(db)
            await repair.expire(job, now=now, force=True)
            if job.get("finalization_prepared") or job["status"] in {"finalizing", "repairing"}:
                await db.outreach_connection_jobs.update_one({"id": job["id"], "workspace_id": workspace_id,
                    "status": {"$in": ["running", "finalizing"]}}, {"$set": {
                    "status": "finalizing", "needs_operator_repair": True, "custody_started_at": job.get("custody_started_at") or job.get("created_at")},
                    "$unset": {"created_at": ""}})
                continue
            stopped = await db.outreach_connection_jobs.update_one(
                {"id": job["id"], "workspace_id": workspace_id,
                 "status": {"$in": ["queued", "running"]}},
                {"$set": {"status": "failed", "error": "Paid sender access has ended", "updated_at": now},
                 "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": ""}},
            )
            if stopped.modified_count:
                proof = await repair.close_fence(job, now=now)
                proven = proof.get("proven_uninstalled") or (proof.get("account_absent")
                    and job.get("installation_protocol") == 2 and not job.get("finalization_prepared"))
                if not proven:
                    await db.outreach_connection_jobs.update_one({"id": job["id"], "workspace_id": workspace_id, "status": "failed"}, {
                        "$set": {"status": "finalizing", "needs_operator_repair": True,
                            "custody_started_at": job.get("custody_started_at") or job.get("created_at")}, "$unset": {"created_at": ""}})
                    continue
                if job.get("new_proxy_reservation"):
                    await db.outreach_proxy_leases.delete_one({
                        "_id": job["proxy_id"], "workspace_id": workspace_id,
                        "sender_id": job["sender_id"],
                        "reservation_job_id": job["id"],
                    })
                if job.get("created_slot"):
                    await db.outreach_sender_slots.delete_one({
                        "workspace_id": workspace_id, "sender_id": job["sender_id"],
                        "reservation_job_id": job["id"],
                    })
                await db.outreach_connection_locks.delete_one({
                    "_id": job["sender_id"], "job_id": job["id"],
                })
        # If any cleanup call above fails, the expired entitlement remains
        # eligible for another pass. Without this marker, a crash after the
        # status transition could strand valid OAuth credentials indefinitely.
        await db.outreach_entitlements.update_one(
            {"workspace_id": workspace_id, "status": "expired", "paid_through": {"$lte": now}},
            {"$set": {"expiry_cleanup_completed_at": now}},
        )
        # No proxy lease or paid provider term is deleted here. An operator
        # manages provider auto-renewal and expiry independently.
    return expired


async def sender_is_ready(db, workspace_id: str, account: dict, now: datetime | None = None) -> bool:
    """Re-check entitlement, sender-specific lease and provider term before a call."""
    now = now or datetime.now(timezone.utc)
    if not live_actions_enabled() or account.get("workspace_id") != workspace_id or account.get("status") != "active":
        return False
    if not await get_active_entitlement(db, workspace_id, now):
        return False
    proxy_id = (account.get("proxy") or {}).get("proxy_id")
    if not proxy_id:
        return False
    lease = await db.outreach_proxy_leases.find_one({
        "_id": proxy_id, "workspace_id": workspace_id, "sender_id": account.get("id"),
    })
    if not lease:
        return False
    inventory = await db.outreach_proxy_inventory.find_one({"_id": proxy_id})
    from outreach.core.proxy_identity import restore_ip_allowed
    hosts = [(account.get('proxy') or {}).get('host')]
    if inventory and inventory.get('host') is not None:
        hosts.append(inventory['host'])
    for host in set(hosts):
        if not await restore_ip_allowed(db, host):
            return False
    if inventory and (inventory.get('provider') == 'webshare_plan'
            or (account.get('proxy') or {}).get('provider') == 'webshare_plan'
            or inventory.get('managed_webshare_version') is not None):
        from outreach.core.webshare_provisioning import managed_webshare_valid
        from outreach.core.proxy_custody import proxy_digest
        if (not await managed_webshare_valid(db, inventory, workspace_id, now=now)
                or lease.get('provider') != 'webshare_plan' or lease.get('country_code') != account.get('country_code')
                or proxy_digest(inventory) != proxy_digest(account.get('proxy') or {})):
            return False
    return bool(
        inventory and inventory.get("status") == "available"
        and inventory.get("last_workspace_id") == workspace_id
        and inventory.get("country_code") == account.get("country_code")
        and (expiry := _utc(inventory.get("expires_at"))) is not None and expiry > now
        and inventory.get("provider") in {"iproyal_static", "webshare_plan"}
    )
