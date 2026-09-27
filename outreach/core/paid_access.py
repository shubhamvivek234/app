"""Fail-closed paid access for the invite-only outreach pilot.

Only an operator with a verified external invoice can activate access. A
customer-facing API must never create or extend an entitlement.
"""
from datetime import datetime, timezone
from typing import Any
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
        doc and doc.get("status") == "active"
        and 1 <= int(doc.get("seats") or 0) <= PILOT_MAX_SENDERS
        and (paid_through := _utc(doc.get("paid_through"))) is not None
        and paid_through > now
        and doc.get("payment_source") == "manual_verified_invoice"
    )


async def get_active_entitlement(db, workspace_id: str, now: datetime | None = None) -> dict | None:
    doc = await db.outreach_entitlements.find_one({"workspace_id": workspace_id})
    return doc if entitlement_is_active(doc, now) else None


async def record_verified_payment(
    db, workspace_id: str, invoice_id: str, verified_by: str, seats: int,
    paid_through: datetime, *, now: datetime | None = None,
) -> dict:
    """Operator-only service; not exposed on a public or customer API."""
    now = now or datetime.now(timezone.utc)
    invoice_id = invoice_id.strip()
    verified_by = verified_by.strip()
    if not workspace_id or not invoice_id or not verified_by:
        raise ValueError("Workspace, verified invoice, and operator are required")
    if not 1 <= seats <= PILOT_MAX_SENDERS:
        raise ValueError("Pilot seat count must be between 1 and 5")
    paid_through = _utc(paid_through)
    if paid_through is None or paid_through <= now:
        raise ValueError("Paid-through date must be in the future")
    request = await db.outreach_access_requests.find_one({"workspace_id": workspace_id})
    country_code = (request or {}).get("country_code")
    if not country_code:
        raise ValueError("A country-specific paid access request is required before activation")
    if request.get("seats") != seats:
        raise ValueError("The verified seat count must match the access request")
    available = await db.outreach_proxy_inventory.count_documents({
        "last_workspace_id": workspace_id, "country_code": country_code,
        "status": "available",
        "expires_at": {"$gte": paid_through},
    })
    if available < seats:
        raise ValueError("Import enough country-matched IPs covering the paid term before taking payment")
    occupied = await db.outreach_sender_slots.count_documents({"workspace_id": workspace_id})
    if occupied > seats:
        raise ValueError("Existing sender assignments exceed the requested seat count")

    # The receipt _id makes a verified invoice impossible to apply twice,
    # including to a second workspace. DB indexes also make workspace unique.
    receipt = {
        "_id": invoice_id, "workspace_id": workspace_id,
        "verified_by": verified_by, "verified_at": now,
        "seats": seats, "paid_through": paid_through,
        "amount_usd_expected": PRICE_USD_PER_SENDER_MONTH * seats,
        "source": "manual_verified_invoice",
    }
    try:
        await db.outreach_payment_receipts.insert_one(receipt)
    except DuplicateKeyError:
        prior = await db.outreach_payment_receipts.find_one({"_id": invoice_id})
        if not prior or prior.get("workspace_id") != workspace_id or prior.get("seats") != seats or _utc(prior.get("paid_through")) != paid_through:
            raise ValueError("Invoice ID has already been used for different payment terms") from None
        entitlement = await db.outreach_entitlements.find_one({"workspace_id": workspace_id})
        if entitlement and entitlement.get("last_invoice_id") == invoice_id:
            return entitlement
        raise ValueError("Invoice receipt exists but entitlement needs operator reconciliation") from None
    updates = {
        "status": "active", "seats": seats, "paid_through": paid_through,
        "price_usd_per_sender_month": PRICE_USD_PER_SENDER_MONTH,
        "payment_source": "manual_verified_invoice", "last_invoice_id": invoice_id,
        "cancel_at_period_end": False, "updated_at": now,
    }
    await db.outreach_entitlements.update_one(
        {"workspace_id": workspace_id},
        {"$set": updates, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await db.outreach_access_requests.update_one(
        {"workspace_id": workspace_id},
        {"$set": {"status": "fulfilled", "fulfilled_at": now}},
    )
    return {"workspace_id": workspace_id, **updates}


async def expire_due_entitlements(db, *, now: datetime | None = None, limit: int = 100) -> int:
    """Stop all active work at paid-through; retain provider IP until its term ends."""
    now = now or datetime.now(timezone.utc)
    due = await db.outreach_entitlements.find({
        "status": "active", "paid_through": {"$lte": now},
    }).to_list(length=limit)
    expired = 0
    for doc in due:
        workspace_id = doc["workspace_id"]
        changed = await db.outreach_entitlements.update_one(
            {"workspace_id": workspace_id, "status": "active", "paid_through": {"$lte": now}},
            {"$set": {"status": "expired", "expired_at": now, "updated_at": now}},
        )
        if not changed.modified_count:
            continue
        expired += 1
        await db.outreach_campaigns.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["active", "warming_up"]}},
            {"$set": {"status": "paused", "auto_launch_enabled": False, "updated_at": now}},
        )
        await db.outreach_accounts.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["active", "warming", "paused"]}},
            {"$set": {"status": "reauth_required", "updated_at": now}},
        )
        await db.outreach_accounts.update_many(
            {"workspace_id": workspace_id},
            {"$unset": {"session_cookie_enc": "", "encrypted_session_cookie": "", "jsession_id": "", "li_a_enc": ""}},
        )
        await db.outreach_tasks.update_many(
            {"workspace_id": workspace_id, "status": {"$in": ["queued", "pending", "scheduled"]}},
            {"$set": {"status": "cancelled", "cancellation_reason": "Paid outreach period ended", "updated_at": now}},
        )
        pending_jobs = await db.outreach_connection_jobs.find({
            "workspace_id": workspace_id, "status": {"$in": ["queued", "running"]},
        }).to_list(length=1000)
        for job in pending_jobs:
            stopped = await db.outreach_connection_jobs.update_one(
                {"id": job["id"], "workspace_id": workspace_id,
                 "status": {"$in": ["queued", "running"]}},
                {"$set": {"status": "failed", "error": "Paid sender access has ended", "updated_at": now},
                 "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": ""}},
            )
            if stopped.modified_count:
                if job.get("new_proxy_reservation"):
                    await db.outreach_proxy_leases.delete_one({
                        "_id": job["proxy_id"], "workspace_id": workspace_id,
                        "sender_id": job["sender_id"],
                    })
                if job.get("created_slot"):
                    await db.outreach_sender_slots.delete_one({
                        "workspace_id": workspace_id, "sender_id": job["sender_id"],
                    })
                await db.outreach_connection_locks.delete_one({
                    "_id": job["sender_id"], "job_id": job["id"],
                })
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
    return bool(
        inventory and inventory.get("status") == "available"
        and inventory.get("last_workspace_id") == workspace_id
        and inventory.get("country_code") == account.get("country_code")
        and (expiry := _utc(inventory.get("expires_at"))) is not None and expiry > now
        and inventory.get("provider") in {"iproyal_static", "webshare_plan"}
    )
