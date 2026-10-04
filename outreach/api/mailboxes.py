"""Workspace-scoped, secret-free mailbox connection and email-discovery settings."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.mailbox_connection import (
    consume_oauth_callback, start_mailbox_connection,
    mailbox_connection_enabled, email_send_enabled, browser_binding_cookie_name,
    is_mailbox_pilot_allowed, is_email_send_pilot_allowed,
)


router = APIRouter(prefix="/mailboxes", tags=["Outreach Email Mailboxes"])


async def _open_mailbox_workspace(current_user: dict = Depends(get_current_user),
                                  db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    from outreach.core.erasure import require_open_workspace
    await require_open_workspace(current_user, db)
    return current_user


def _workspace_id(user: dict) -> str:
    workspace_id = user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=403, detail="An active workspace is required")
    return str(workspace_id)


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"true", "1", "yes"}


class AuthorizeMailboxRequest(BaseModel):
    sender_account_id: str = Field(..., min_length=1, max_length=128)


class HunterKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=256)


@router.get("")
async def list_mailboxes(
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    cursor = db.outreach_mailboxes.find({"workspace_id": workspace_id}, {
        "_id": 0, "sender_account_id": 1, "email": 1, "provider": 1,
        "status": 1, "sync_status": 1, "last_sync_at": 1,
    })
    docs = await cursor.to_list(length=100)
    allowed = {"sender_account_id", "email", "provider", "status", "sync_status", "last_sync_at"}
    return {
        "mailboxes": [{key: doc[key] for key in allowed if key in doc} for doc in docs],
        "connection_enabled": is_mailbox_pilot_allowed(workspace_id),
        "send_enabled": is_email_send_pilot_allowed(workspace_id),
        "sync_enabled": _enabled("OUTREACH_EMAIL_SYNC_ENABLED") and is_mailbox_pilot_allowed(workspace_id),
    }


@router.get("/hunter-key")
async def hunter_key_status(
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await db.outreach_hunter_credentials.find_one(
        {"workspace_id": _workspace_id(current_user)}, {"_id": 0, "api_key_enc": 1},
    )
    return {"configured": bool(doc and doc.get("api_key_enc")),
            "enabled": _enabled("OUTREACH_HUNTER_ENABLED")}


@router.put("/hunter-key", dependencies=[require_permission("account:connect")])
async def put_hunter_key(
    request: HunterKeyRequest,
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not _enabled("OUTREACH_HUNTER_ENABLED"):
        raise HTTPException(status_code=503, detail="Email discovery is not enabled")
    now = datetime.now(timezone.utc)
    from outreach.core.provider_custody import seal_finder_key
    from outreach.core.suppression import mutate_suppression, SuppressionUnavailable
    from outreach.core.credential_custody import CustodyUnavailable
    workspace = _workspace_id(current_user)
    try:
        async def verify(current):
            if not _enabled('OUTREACH_HUNTER_ENABLED'):
                raise CustodyUnavailable('Finder configuration changed')
        await mutate_suppression(db, workspace, verify)
        encrypted = await seal_finder_key(request.api_key.strip(), workspace)
        async def save(current):
            await verify(current)
            await current.outreach_hunter_credentials.update_one({"workspace_id": workspace},
                {"$set": {**encrypted, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
        await mutate_suppression(db, workspace, save)
    except (CustodyUnavailable, SuppressionUnavailable):
        raise HTTPException(503, "Encrypted finder credentials are unavailable") from None
    return {"configured": True, "enabled": True}


@router.delete("/hunter-key", dependencies=[require_permission("account:connect")])
async def delete_hunter_key(
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    from outreach.core.suppression import mutate_suppression
    workspace = _workspace_id(current_user)
    await mutate_suppression(db, workspace, lambda current: current.outreach_hunter_credentials.delete_one({"workspace_id": workspace}))
    return {"configured": False, "enabled": _enabled("OUTREACH_HUNTER_ENABLED")}


@router.get("/connection-jobs/{job_id}")
async def get_mailbox_connection_job(
    job_id: str,
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    job = await db.outreach_mailbox_connection_jobs.find_one({
        "workspace_id": _workspace_id(current_user), "id": job_id,
    })
    if not job:
        raise HTTPException(status_code=404, detail="Mailbox connection job was not found")
    result = {"connection_job_id": job_id, "status": job.get("status", "pending")}
    if job.get('status') == 'review_stopped':
        result['error'] = 'Mailbox authorization was stopped after operator review.'
    if job.get("status") in {"failed", "review_required"}:
        from outreach.core.mailbox_jobs import REVIEW_ERROR
        result["error"] = job.get("error") or (REVIEW_ERROR if job.get("status") == "review_required"
            else "Mailbox connection failed. Reconnect and try again.")
    return result


@router.post("/{provider}/authorize", dependencies=[require_permission("account:connect")])
async def authorize_mailbox(
    provider: str,
    request: AuthorizeMailboxRequest,
    response: Response,
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    result = await start_mailbox_connection(
        db, workspace_id, str(current_user.get("user_id") or ""),
        request.sender_account_id, provider,
    )
    cookie_name = result.pop("browser_binding_cookie_name")
    browser_nonce = result.pop("browser_binding_nonce")
    response.set_cookie(cookie_name, browser_nonce, max_age=600, path="/",
                        secure=True, httponly=True, samesite="lax")
    return result


def _callback_destination(job_id: str) -> str:
    base = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
        raise HTTPException(status_code=503, detail="Frontend callback is not configured")
    if parsed.username or parsed.password or not parsed.netloc or parsed.query or parsed.fragment:
        raise HTTPException(status_code=503, detail="Frontend callback is not configured")
    return f"{base}/outreach?{urlencode({'tab': 'settings', 'mailbox_job_id': job_id})}"


@router.get("/{provider}/callback", include_in_schema=False)
async def mailbox_oauth_callback(
    provider: str,
    request: Request,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # OAuth redirects do not carry application cookies. The one-time hashed
    # state identifies the workspace; no user-controlled redirect is accepted.
    cookie_name = browser_binding_cookie_name(state)
    job_id = await consume_oauth_callback(
        db, provider, state, code, error,
        browser_binding_nonce=request.cookies.get(cookie_name),
    )
    redirect = RedirectResponse(_callback_destination(job_id), status_code=303)
    redirect.delete_cookie(cookie_name, path="/", secure=True, httponly=True, samesite="lax")
    return redirect


@router.delete("/{sender_account_id}", dependencies=[require_permission("account:disconnect")])
async def disconnect_mailbox(
    sender_account_id: str,
    current_user: dict = Depends(_open_mailbox_workspace),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    now = datetime.now(timezone.utc)
    from outreach.core.suppression import mutate_suppression
    from outreach.core.mailbox_jobs import stop_connection_jobs
    async def stop(current):
        result = await current.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": sender_account_id,
             "status": {"$ne": "disconnected"}},
            {"$set": {"status": "disconnected", "sync_status": "disabled", "updated_at": now},
             "$unset": {"access_token_enc": "", "refresh_token_enc": "", "refresh_lease_nonce": "",
                        "refresh_lease_until": "", "sync_lease_until": "", "sync_lease_id": ""}},
        )
        if not getattr(result, "matched_count", 0):
            raise HTTPException(status_code=404, detail="Mailbox was not found")
        scope = {"workspace_id": workspace_id, "sender_account_id": sender_account_id}
        await stop_connection_jobs(current, workspace_id, sender=sender_account_id, now=now, error="Mailbox was disconnected")
        states = await current.outreach_mailbox_oauth_states.find(scope).limit(6).to_list(length=6)
        for state in states:
            await current.outreach_mailbox_oauth_states.delete_one({**scope, "_id": state["_id"]})
    await mutate_suppression(db, workspace_id, stop)
    return {"status": "disconnected"}
