"""Reference-only OAuth outbox and bounded database-only recovery.

The authorization deadline limits code use, not evidence retention. Once an
exchange could have happened, no lease expiry or broker redelivery can replay it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Callable

from outreach.core import suppression
from outreach.core.dispatch_authority import AuthorityDatabase

ACTIVE_JOB_STATES = ("pending", "queued", "running", "review_required")
HELD_EXCHANGES = ("possible", "unknown")
WORKER_LEASE = timedelta(minutes=2)
PUBLICATION_INTERVAL = timedelta(seconds=30)
JOB_SECRETS = {"authorization_code_enc": "", "code_verifier_enc": ""}
DAILY_EXCHANGE_LIMIT = 10
REVIEW_ERROR = "Mailbox authorization outcome needs operator review before reconnecting."


def _fenced(current: Any, owner: str) -> Any:
    return (AuthorityDatabase(current.database, current.session, owner)
        if isinstance(current, suppression.SuppressionDatabase) else current)


def _owned(job: dict) -> dict:
    """CAS the captured owner and material; never clean up replacement work."""
    fields = ("status", "provider", "sender_account_id", "connection_owner", "exchange_state", "lease_until", "app_config_digest",
        "authorization_code_enc", "code_verifier_enc", "authorization_expires_at")
    return {"workspace_id": job["workspace_id"], "id": job["id"], **{
        name: job[name] if name in job else {"$exists": False} for name in fields}}


async def _postpone(db: Any, row: dict, field: str, due: datetime) -> None:
    """Guard-ordered scheduling metadata for closed work; never reopen or replay."""
    from outreach.core.erasure import _control
    async def backoff(current):
        await current.outreach_mailbox_connection_jobs.update_one({**_owned(row),
            field: row[field] if field in row else {"$exists": False}}, {"$set": {field: due}})
    await _control(db, row["workspace_id"], backoff)


async def reserve_exchange_budget(current: Any, workspace: str, sender: str, now: datetime) -> None:
    """Conservative physical allowance: possible calls are never refunded."""
    from outreach.core.authorization import canonical_hash
    from outreach.core.mailbox_connection import MailboxUnavailable
    scope = {"workspace_id": workspace, "_id": canonical_hash(["oauth_exchange", workspace, sender, now.date().isoformat()])}
    row = await current.outreach_mailbox_exchange_budgets.find_one(scope)
    if row and row.get("used", 0) >= DAILY_EXCHANGE_LIMIT:
        raise MailboxUnavailable("Mailbox authorization daily allowance exhausted")
    if row:
        changed = await current.outreach_mailbox_exchange_budgets.update_one({**scope, "used": row.get("used", 0)}, {
            "$inc": {"used": 1}, "$set": {"updated_at": now}})
        if changed.matched_count != 1: raise MailboxUnavailable("Mailbox authorization allowance changed")
    else:
        await current.outreach_mailbox_exchange_budgets.insert_one({**scope, "sender_account_id": sender,
            "day": now.date().isoformat(), "used": 1, "updated_at": now})


async def stop_connection_jobs(current: Any, workspace: str, *, sender: str | None = None, now: datetime,
                               error: str) -> None:
    """Shared paid/disconnect stop preserves unresolved provider outcomes."""
    scope = {"workspace_id": workspace, **({"sender_account_id": sender} if sender else {})}
    await current.outreach_mailbox_connection_jobs.update_many({**scope, "$or": [
        {"exchange_state": {"$in": list(HELD_EXCHANGES)}},
        {"status": "running", "protocol_version": {"$ne": 2}},
    ]}, {"$set": {"status": "review_required", "error": REVIEW_ERROR, "updated_at": now},
        "$unset": {**JOB_SECRETS, "expires_at": ""}})
    await current.outreach_mailbox_connection_jobs.update_many({**scope,
        "status": {"$in": ["pending", "queued", "running"]}}, {
        "$set": {"status": "failed", "error": error, "updated_at": now}, "$unset": {**JOB_SECRETS, "expires_at": ""}})


async def claim_job(db: Any, workspace: str, job_id: str, owner: str) -> dict | None:
    """Claim only a usable, never-submitted code under current paid authority."""
    from outreach.core import mailbox_connection as connection
    async def claim(current):
        fenced = _fenced(current, owner)
        job = await fenced.outreach_mailbox_connection_jobs.find_one({
            "workspace_id": workspace, "id": job_id, "status": "queued",
            "exchange_state": {"$nin": [*HELD_EXCHANGES, "installed"]}})
        if not job:
            return None
        now = connection.datetime.now(timezone.utc)
        deadline = connection._utc(job.get("authorization_expires_at"))
        if (not deadline or deadline <= now or not connection._control_allowed(workspace)
                or not await connection._paid_sender(fenced, workspace, job["sender_account_id"])):
            await current.outreach_mailbox_connection_jobs.update_one(_owned(job), {
                "$set": {"status": "failed", "error": "Mailbox authorization expired or access ended; reconnect.", "updated_at": now},
                "$unset": {**JOB_SECRETS, "expires_at": ""}})
            return {"status": "failed"}
        changed = await current.outreach_mailbox_connection_jobs.update_one(_owned(job), {
            "$set": {"protocol_version": 2, "status": "running", "exchange_state": "preparing",
                "started_at": now, "updated_at": now, "connection_owner": owner,
                "lease_until": now + WORKER_LEASE, "next_recovery_at": now + WORKER_LEASE},
            "$unset": {"expires_at": ""}})
        if changed.modified_count != 1: return None
        return await current.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace, "id": job_id,
            "status": "running", "connection_owner": owner})
    return await suppression.mutate_suppression(db, workspace, claim)


async def fail_owned_job(db: Any, job: dict, *, rejected: bool = False) -> dict:
    """Retain ambiguous metadata, or scrub proven pre-call/rejected credentials."""
    from outreach.core import mailbox_connection as connection
    scope = {"workspace_id": job["workspace_id"], "id": job["id"], "status": "running",
        "connection_owner": job["connection_owner"]}
    async def fail(current):
        row = await current.outreach_mailbox_connection_jobs.find_one(scope)
        if not row:
            return {"status": "already_claimed"}
        held = row.get("exchange_state") in HELD_EXCHANGES and not rejected
        status = "review_required" if held else "failed"
        await current.outreach_mailbox_connection_jobs.update_one(_owned(row), {
            "$set": {"status": status, "exchange_state": "unknown" if held else "rejected" if rejected else "not_submitted",
                "error": REVIEW_ERROR if held else "Mailbox connection failed; check access and reconnect.",
                "updated_at": connection.datetime.now(timezone.utc)},
            "$unset": {**JOB_SECRETS, "expires_at": "", "publication_owner": ""}})
        return {"status": status}
    return await suppression.mutate_suppression(db, job["workspace_id"], fail)


async def recover_job(db: Any, captured: dict) -> bool:
    """Reclaim only proven preparation; unmarked legacy workers remain held."""
    from outreach.core import mailbox_connection as connection
    workspace = captured["workspace_id"]
    async def recover(current):
        row = await current.outreach_mailbox_connection_jobs.find_one(_owned(captured))
        if not row or row.get("status") not in {"pending", "queued", "running"}:
            return False
        now = connection.datetime.now(timezone.utc)
        deadline = connection._utc(row.get("authorization_expires_at"))
        usable = bool(deadline and deadline > now)
        state = row.get("exchange_state")
        if row["status"] == "running":
            lease = connection._utc(row.get("lease_until"))
            started = connection._utc(row.get("started_at"))
            if lease and lease > now or not lease and started and started + WORKER_LEASE > now:
                return False
            proven = row.get("protocol_version") == 2 and state == "preparing"
            if not proven:
                changes = {"status": "review_required", "error": REVIEW_ERROR}
                unset = {**JOB_SECRETS, "expires_at": ""}
            elif usable:
                changes = {"status": "queued", "exchange_state": "pending", "next_publish_at": now}
                unset = {"connection_owner": "", "lease_until": "", "expires_at": ""}
            else:
                changes = {"status": "failed", "exchange_state": "not_submitted", "error": "Mailbox authorization expired; reconnect."}
                unset = {**JOB_SECRETS, "expires_at": ""}
        elif usable:
            return False
        else:
            changes = {"status": "failed", "error": "Mailbox authorization expired; reconnect."}
            unset = {**JOB_SECRETS, "expires_at": ""}
        changed = await current.outreach_mailbox_connection_jobs.update_one(_owned(row), {
            "$set": {**changes, "updated_at": now}, "$unset": unset})
        return changed.modified_count == 1
    return await suppression.mutate_suppression(db, workspace, recover)


async def expire_sender_jobs(db: Any, workspace: str, sender: str) -> None:
    rows = await db.outreach_mailbox_connection_jobs.find({"workspace_id": workspace,
        "sender_account_id": sender, "status": {"$in": ["pending", "queued", "running"]}}).limit(6).to_list(length=6)
    for row in rows:
        await recover_job(db, row)


async def recover_due_jobs(db: Any) -> dict:
    """Separate fair recovery schedule, including disabled-pilot cleanup."""
    from outreach.core import mailbox_connection as connection
    if connection.is_shutting_down():
        return {"recovered": 0}
    now = connection.datetime.now(timezone.utc)
    rows = await db.outreach_mailbox_connection_jobs.find({"status": {"$in": ["pending", "queued", "running"]},
        "$or": [{"next_recovery_at": {"$lte": now}}, {"next_recovery_at": {"$exists": False}}]
    }).sort("next_recovery_at", 1).limit(50).to_list(length=50)
    recovered = 0
    for row in rows:
        if connection.is_shutting_down(): break
        try:
            recovered += bool(await recover_job(db, row))
            await db.outreach_mailbox_connection_jobs.update_one(_owned(row), {
                "$set": {"next_recovery_at": now + PUBLICATION_INTERVAL}})
        except suppression.SuppressionUnavailable:
            # Closed tenants belong to drained erasure, not an open-work recovery.
            await _postpone(db, row, "next_recovery_at", now + timedelta(minutes=5))
            continue
    return {"recovered": recovered}


async def publish_due_jobs(db: Any, publish: Callable[[str, str], None]) -> dict:
    """Persist a fair publication claim before sending only references to Redis."""
    from outreach.core import mailbox_connection as connection
    counts = {"published": 0, "failed": 0}
    if connection.is_shutting_down(): return counts
    now = connection.datetime.now(timezone.utc)
    rows = await db.outreach_mailbox_connection_jobs.find({"status": "queued",
        "authorization_expires_at": {"$gt": now}, "$or": [
            {"next_publish_at": {"$lte": now}}, {"next_publish_at": {"$exists": False}}]
    }).sort("next_publish_at", 1).limit(50).to_list(length=50)
    for row in rows:
        if connection.is_shutting_down(): break
        if not connection._control_allowed(row["workspace_id"]):
            await _postpone(db, row, "next_publish_at", now + timedelta(minutes=5))
            continue
        nonce = secrets.token_urlsafe(18)
        async def claim(current):
            fresh = await current.outreach_mailbox_connection_jobs.find_one(_owned(row))
            now = connection.datetime.now(timezone.utc)
            if not fresh or connection._utc(fresh.get("next_publish_at")) and connection._utc(fresh["next_publish_at"]) > now:
                return False
            changed = await current.outreach_mailbox_connection_jobs.update_one(_owned(fresh), {
                "$set": {"publication_owner": nonce, "next_publish_at": now + PUBLICATION_INTERVAL}})
            return changed.modified_count == 1
        try:
            if not await suppression.mutate_suppression(db, row["workspace_id"], claim): continue
        except suppression.SuppressionUnavailable:
            await _postpone(db, row, "next_publish_at", now + timedelta(minutes=5))
            continue
        try:
            publish(row["id"], row["workspace_id"])
            counts["published"] += 1
        except Exception:
            counts["failed"] += 1
        # A lost broker acknowledgement retains the due row; duplicate workers
        # are excluded by the running owner and possible-exchange marker.
    return counts
