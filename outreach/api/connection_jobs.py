"""Queue session verification without calling LinkedIn in the API process."""
from datetime import datetime, timezone
from uuid import uuid4
import os

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from outreach.core.crypto import encrypt_secret
from outreach.core.managed_proxy import (
    ManagedProxyUnavailable, release_sender_reservation, reserve_sender_proxy,
)
from outreach.core.paid_access import get_active_entitlement, live_actions_enabled
from outreach.engine.session_authenticator import _clean_cookie_token


def _enqueue_connection_job(job_id: str, workspace_id: str, trace_id: str) -> None:
    # Broker arguments contain identifiers only, never session values.
    from celery_workers.tasks.outreach import verify_sender_connection
    verify_sender_connection.delay(job_id, workspace_id, trace_id)


async def queue_connection(req, current_user: dict, db) -> dict:
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
    created_slot = False
    reserved_proxy_id = None
    locked = False
    try:
        slot = await db.outreach_sender_slots.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
        }) if reconnect_target else None
        if not slot:
            for number in range(1, int(entitlement["seats"]) + 1):
                try:
                    await db.outreach_sender_slots.insert_one({
                        "_id": f"{workspace_id}:{number}", "workspace_id": workspace_id,
                        "sender_id": sender_id, "created_at": datetime.now(timezone.utc),
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
            })
            locked = True
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail="Sender verification is already in progress") from exc

        prior_lease = await db.outreach_proxy_leases.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
        })
        proxy = await reserve_sender_proxy(db, workspace_id, sender_id, country_code)
        if not prior_lease or prior_lease.get("_id") != proxy.proxy_id:
            reserved_proxy_id = proxy.proxy_id
        await db.outreach_connection_jobs.insert_one({
            "id": job_id, "workspace_id": workspace_id, "user_id": user_id,
            "sender_id": sender_id, "reconnect": bool(reconnect_target),
            "created_slot": created_slot, "new_proxy_reservation": bool(reserved_proxy_id),
            "proxy_id": proxy.proxy_id, "country_code": country_code,
            "premium_product": req.premium_product or "classic",
            "user_agent": req.user_agent or "",
            "li_at_enc": encrypt_secret(li_at), "jsession_id_enc": encrypt_secret(csrf),
            "li_a_enc": encrypt_secret(_clean_cookie_token(req.li_a, "li_a")) if req.li_a else "",
            "status": "queued", "trace_id": job_id,
            "created_at": datetime.now(timezone.utc),
        })
        _enqueue_connection_job(job_id, workspace_id, job_id)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        if locked:
            await db.outreach_connection_locks.delete_one({"_id": sender_id, "job_id": job_id})
        if reserved_proxy_id:
            await release_sender_reservation(db, workspace_id, sender_id, reserved_proxy_id)
        if created_slot:
            await db.outreach_sender_slots.delete_one({"workspace_id": workspace_id, "sender_id": sender_id})
        await db.outreach_connection_jobs.delete_one({"id": job_id, "workspace_id": workspace_id, "status": "queued"})
        if isinstance(exc, ManagedProxyUnavailable):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise
