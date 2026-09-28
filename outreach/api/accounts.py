"""
Phase 2: Accounts API endpoints for LinkedIn Outbound Engine.
Supports verified session-cookie connection; legacy credential routes are retired.
Assigns one pre-purchased dedicated static residential proxy per sender.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.models import (
    AccountStatus,
)
from outreach.api.connection_jobs import queue_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["LinkedIn Outreach Accounts"])


# ── Request / Response DTOs ────────────────────────────────────────────────

class ConnectCookieRequest(BaseModel):
    li_at: str = Field(..., description="LinkedIn session cookie li_at")
    li_a: str | None = Field(default="", description="Optional li_a cookie for Sales Navigator or Recruiter")
    premium_product: str = Field(default="classic", description="classic, sales_navigator, or recruiter")
    user_agent: str | None = Field(default="", description="Browser user agent string")
    jsession_id: str | None = Field(default="", description="JSESSIONID cookie required for live verification")
    country_code: str = Field(
        ..., min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$",
        description="2-letter ISO country code for proxy matching",
    )
    reconnect_account_id: str | None = Field(default=None, description="Existing sender ID when renewing its session")
    workspace_id: str | None = None


class UpdateLimitsRequest(BaseModel):
    connection_invites: int | None = None
    messages: int | None = None
    voice_notes: int | None = None
    inmails: int | None = None
    profile_visits: int | None = None
    follows: int | None = None
    post_likes: int | None = None
    comments: int | None = None
    email_sends: int | None = None


def _sanitize_account(acc: dict[str, Any]) -> dict[str, Any]:
    """Strips secret tokens from response payloads."""
    clean = dict(acc)
    clean.pop("session_cookie_enc", None)
    clean.pop("encrypted_session_cookie", None)
    clean.pop("li_a_enc", None)
    clean.pop("jsession_id", None)
    clean.pop("li_at_enc", None)
    clean.pop("_id", None)
    if clean.get("proxy"):
        clean["proxy"] = dict(clean["proxy"])
        clean["proxy"].pop("password_enc", None)
        clean["proxy"].pop("username", None)
    if clean.get("proxy_config"):
        clean["proxy_config"] = dict(clean["proxy_config"])
        clean["proxy_config"].pop("password_enc", None)
        clean["proxy_config"].pop("username", None)
    return clean


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
async def list_outreach_accounts(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists all connected LinkedIn sender accounts for the active user."""
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    cursor = db.outreach_accounts.find({"workspace_id": ws_id})
    accounts = await cursor.to_list(length=100)
    return [_sanitize_account(a) for a in accounts]



@router.get("/connection-jobs/{job_id}")
async def get_connection_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    job = await db.outreach_connection_jobs.find_one({"id": job_id, "workspace_id": workspace_id})
    if not job:
        raise HTTPException(status_code=404, detail="Connection job not found")
    result = {"job_id": job_id, "status": job.get("status", "queued")}
    if job.get("status") == "failed":
        result["error"] = job.get("error") or "Sender verification failed. Check your session values and try again."
    if job.get("status") == "completed" and job.get("account_id"):
        account = await db.outreach_accounts.find_one({
            "id": job["account_id"], "workspace_id": workspace_id,
        })
        if account:
            result["account"] = _sanitize_account(account)
    return result


@router.post("/connect-cookie", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[require_permission("account:connect")])
async def connect_via_cookie(
    req: ConnectCookieRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await queue_connection(req, current_user, db)
@router.post("/login-start")
async def login_start(
    current_user: dict = Depends(get_current_user),
):
    """Reject stale clients without accepting a password DTO or allocating a proxy."""
    raise HTTPException(status_code=410, detail="Password connection has been retired. Sign in on LinkedIn, then use verified session connection.")


@router.post("/login-verify-2fa")
async def login_verify_2fa(
    current_user: dict = Depends(get_current_user),
):
    """Reject stale 2FA clients; users complete challenges on LinkedIn itself."""
    raise HTTPException(status_code=410, detail="Password connection has been retired. Complete sign-in on LinkedIn.")


@router.patch("/{account_id}/limits", dependencies=[require_permission("account:connect")])
async def update_account_limits(
    account_id: str,
    req: UpdateLimitsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Updates daily safety caps for a specific connected account."""
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    account = await db.outreach_accounts.find_one({
        "id": account_id,
        "workspace_id": ws_id,
    })
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    updates: dict[str, Any] = {}
    for field, val in req.model_dump(exclude_unset=True).items():
        if val is not None:
            # Enforce max limit of 35 per day to prevent aggressive spamming bans
            capped_val = min(max(val, 0), 35)
            updates[f"limits.{field}"] = capped_val

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.outreach_accounts.update_one({"id": account_id, "workspace_id": ws_id}, {"$set": updates})

    updated_account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": ws_id})
    return _sanitize_account(updated_account)


@router.delete("/{account_id}", dependencies=[require_permission("account:disconnect")])
async def disconnect_account(
    account_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Disconnect session; retain the sender's paid-term IP for same-sender reuse."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    account = await db.outreach_accounts.find_one({
        "id": account_id,
        "workspace_id": ws_id,
    })
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    now = datetime.now(timezone.utc)
    # Disable the sender first: a failed database update must not leave an active
    # account pointing at a proxy we have already released.
    await db.outreach_accounts.update_one(
        {"id": account_id, "workspace_id": ws_id},
        {"$set": {"status": AccountStatus.DISCONNECTED, "updated_at": now},
         "$unset": {"session_cookie_enc": "", "encrypted_session_cookie": "",
                    "jsession_id": "", "li_a_enc": ""}},
    )
    # Relational Cascade: Unbind account from campaign sender pools
    await db.outreach_campaigns.update_many(
        {"workspace_id": ws_id, "sender_account_ids": account_id},
        {"$pull": {"sender_account_ids": account_id}, "$set": {"updated_at": now, "status": "paused"}}
    )

    # Relational Cascade: Cancel queued/pending tasks scheduled on this account
    await db.outreach_tasks.update_many(
        {"workspace_id": ws_id, "account_id": account_id, "status": {"$in": ["queued", "pending", "scheduled"]}},
        {"$set": {
            "status": "cancelled",
            "cancellation_reason": f"Sender account {account_id} was disconnected",
            "updated_at": now,
        }}
    )

    logger.info("Account %s disconnected; paid-term IP retained for user %s", account_id, user_id)
    return {"status": "success", "message": "Sender disconnected and campaigns paused. Its IP remains reserved through the paid provider term for this sender only."}
