"""
Phase 2: Accounts API endpoints for LinkedIn Outbound Engine.
Supports verified session-cookie connection; legacy credential routes are retired.
Assigns one pre-purchased dedicated static residential proxy per sender.
"""
import logging
from typing import Annotated, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core import suppression
from outreach.core.suppression import SuppressionUnavailable
from outreach.models import (
    AccountStatus,
)
from outreach.api.connection_jobs import queue_connection
from outreach.core.sender_verification_recovery import discover_jobs, verify_recovery_context, job_metadata

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
    connection_scope_digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
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
    activity_control_enabled: bool | None = None
    connections_count: int | None = Field(default=None, ge=0, le=50000)
    high_volume_mode: bool | None = None


class ActivityControlRequest(BaseModel):
    activity_control_enabled: bool | None = None
    connections_count: int | None = Field(default=None, ge=0, le=50000)
    warmup_level: int | None = Field(default=None, ge=1, le=4)
    connection_invites: int | None = Field(default=None, ge=0, le=75)
    messages: int | None = Field(default=None, ge=0, le=150)
    profile_visits: int | None = Field(default=None, ge=0, le=150)
    inmails: int | None = Field(default=None, ge=0, le=50)
    follows: int | None = Field(default=None, ge=0, le=100)
    post_likes: int | None = Field(default=None, ge=0, le=100)
    comments: int | None = Field(default=None, ge=0, le=50)
    email_sends: int | None = Field(default=None, ge=0, le=150)


def _sanitize_account(acc: dict[str, Any]) -> dict[str, Any]:
    """Strips secret tokens from response payloads."""
    clean = dict(acc)
    clean.pop("session_cookie_enc", None)
    clean.pop("encrypted_session_cookie", None)
    clean.pop("li_a_enc", None)
    clean.pop("jsession_id", None)
    clean.pop("li_at_enc", None)
    clean.pop("jsession_id_enc", None)
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
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists all connected LinkedIn sender accounts for the active user."""
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    cursor = db.outreach_accounts.find({"workspace_id": ws_id})
    accounts = await cursor.to_list(length=100)
    return [_sanitize_account(a) for a in accounts]



@router.get('/connection-jobs')
async def discover_connection_jobs(
    response: Response,
    current_user: dict = require_outreach_permission('account:connect'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return await discover_jobs(db, current_user)


@router.get("/connection-jobs/{job_id}")
async def get_connection_job(
    job_id: str,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    scope_digest: Annotated[str | None, Query(pattern=r'^[0-9a-f]{64}$')] = None,
    response: Response = None,
):
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    if response is not None:
        response.headers['Cache-Control'] = 'private, no-store'
    if scope_digest is not None:
        verify_recovery_context(current_user, scope_digest)
        matches = await db.outreach_connection_jobs.find({'id': job_id, 'workspace_id': workspace_id},
            {'id': 1, 'workspace_id': 1, 'user_id': 1, 'sender_id': 1, 'status': 1, 'reconnect': 1,
             'account_id': 1, 'credential_generation': 1, 'expected_linkedin_urn': 1}).limit(2).to_list(2)
        if len(matches) > 1:
            raise HTTPException(503, 'Duplicate verification records require support review')
        job = matches[0] if matches else None
    else:
        job = await db.outreach_connection_jobs.find_one({"id": job_id, "workspace_id": workspace_id})
    if not job:
        raise HTTPException(status_code=404, detail="Connection job not found")
    if scope_digest is not None:
        context = verify_recovery_context(current_user, scope_digest)
        if job.get('user_id') != current_user.get('user_id'):
            raise HTTPException(404, 'Connection job not found')
        result = {**job_metadata(job, workspace_id, current_user['user_id']), **context, 'account_current': False}
        if job['status'] == 'completed' and type(job.get('account_id')) is str and job['account_id'] == job['sender_id']:
            accounts = await db.outreach_accounts.find({'workspace_id': workspace_id, 'id': job['account_id']},
                {'id': 1, 'workspace_id': 1, 'account_name': 1, 'status': 1, 'is_deleted': 1,
                 'credential_generation': 1, 'linkedin_urn': 1, 'connection_finalization': 1}).limit(2).to_list(2)
            account = accounts[0] if len(accounts) == 1 else None
            fence = account.get('connection_finalization') if account else None
            if (account and type(account.get('id')) is str and account['id'] == job['sender_id']
                    and type(account.get('workspace_id')) is str and account['workspace_id'] == workspace_id
                    and type(account.get('status')) is str and account['status'] == 'active'
                    and (account.get('is_deleted') is None or account.get('is_deleted') is False)
                    and type(job.get('credential_generation')) is str and job['credential_generation']
                    and type(account.get('credential_generation')) is str and account['credential_generation'] == job['credential_generation']
                    and type(job.get('expected_linkedin_urn')) is str and job['expected_linkedin_urn']
                    and type(account.get('linkedin_urn')) is str and account['linkedin_urn'] == job['expected_linkedin_urn']
                    and type(fence) is dict and type(fence.get('job_id')) is str and fence['job_id'] == job_id
                    and type(fence.get('generation')) is str and fence['generation'] == job['credential_generation']
                    and fence.get('ever_installed') is True and type(fence.get('state')) is str and fence['state'] == 'closed'
                    and type(fence.get('completion')) is str and fence['completion'] == 'verified_install'):
                result['account_current'] = True
                result['account'] = {key: account[key] for key in ('id', 'workspace_id', 'status')}
                result['account']['account_name'] = account.get('account_name') if type(account.get('account_name')) is str else 'LinkedIn sender'
        return result
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


@router.post("/connect-cookie", status_code=status.HTTP_202_ACCEPTED)
async def connect_via_cookie(
    req: ConnectCookieRequest,
    current_user: dict = require_outreach_permission('account:connect'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await queue_connection(req, current_user, db)
@router.post("/login-start")
async def login_start(
    current_user: dict = Depends(get_outreach_user),
):
    """Reject stale clients without accepting a password DTO or allocating a proxy."""
    raise HTTPException(status_code=410, detail="Password connection has been retired. Sign in on LinkedIn, then use verified session connection.")


@router.post("/login-verify-2fa")
async def login_verify_2fa(
    current_user: dict = Depends(get_outreach_user),
):
    """Reject stale 2FA clients; users complete challenges on LinkedIn itself."""
    raise HTTPException(status_code=410, detail="Password connection has been retired. Complete sign-in on LinkedIn.")


@router.patch("/{account_id}/limits")
async def update_account_limits(
    account_id: str,
    req: UpdateLimitsRequest,
    current_user: dict = require_outreach_permission('account:connect'),
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

    from outreach.core.safety_shield import WarmUpGovernor
    high_vol = bool(req.high_volume_mode or account.get("activity_control_enabled"))
    updates: dict[str, Any] = {}
    payload = req.model_dump(exclude_unset=True)
    if "activity_control_enabled" in payload and payload["activity_control_enabled"] is not None:
        updates["activity_control_enabled"] = bool(payload.pop("activity_control_enabled"))
        high_vol = high_vol or updates["activity_control_enabled"]
    if "connections_count" in payload and payload["connections_count"] is not None:
        updates["connections_count"] = int(payload.pop("connections_count"))
    payload.pop("high_volume_mode", None)

    for field, val in payload.items():
        if val is not None:
            field_cap = WarmUpGovernor.HARD_CEILINGS.get(field, 75) if high_vol else 35
            capped_val = min(max(val, 0), field_cap)
            updates[f"limits.{field}"] = capped_val

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.outreach_accounts.update_one({"id": account_id, "workspace_id": ws_id}, {"$set": updates})

    updated_account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": ws_id})
    return _sanitize_account(updated_account)


@router.patch("/{account_id}/activity-control")
async def update_activity_control(
    account_id: str,
    req: ActivityControlRequest,
    current_user: dict = require_outreach_permission('account:connect'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Configures Dripify-style Activity Control (dynamic warm-up + up to 75 invites / 150 messages per day)."""
    from outreach.core.safety_shield import WarmUpGovernor

    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": ws_id})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    updates: dict[str, Any] = {}
    payload = req.model_dump(exclude_unset=True)
    for top_field in ("activity_control_enabled", "connections_count", "warmup_level"):
        if top_field in payload and payload[top_field] is not None:
            updates[top_field] = payload.pop(top_field)

    for field, val in payload.items():
        if val is not None and field in WarmUpGovernor.HARD_CEILINGS:
            updates[f"limits.{field}"] = min(max(int(val), 0), WarmUpGovernor.HARD_CEILINGS[field])

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.outreach_accounts.update_one({"id": account_id, "workspace_id": ws_id}, {"$set": updates})

    updated_account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": ws_id})
    sanitized = _sanitize_account(updated_account)
    sanitized["activity_control"] = WarmUpGovernor.compute_activity_control_summary(updated_account)
    return sanitized


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: str,
    current_user: dict = require_outreach_permission('account:disconnect'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Disconnect session; retain the sender's paid-term IP for same-sender reuse."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or user_id
    async def apply(current):
        account = await current.outreach_accounts.find_one({"id": account_id, "workspace_id": ws_id})
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        now = datetime.now(timezone.utc)
        changes = {"status": AccountStatus.DISCONNECTED, "updated_at": now,
                   "connection_disconnected_at": now}
        fence = account.get("connection_finalization")
        if isinstance(fence, dict) and fence:
            changes["connection_finalization"] = {**fence, "state": "closed",
                "closed_at": now, "completion": "disconnected"}
        # Installation and disconnect share the workspace transaction guard.
        # The timestamp also rejects a captured job which has not prepared yet.
        await current.outreach_accounts.update_one(
            {"id": account_id, "workspace_id": ws_id}, {"$set": changes,
             "$unset": {"session_cookie_enc": "", "encrypted_session_cookie": "",
                        "jsession_id": "", "li_a_enc": "", "li_at_enc": "", "jsession_id_enc": ""}})
        await current.outreach_connection_jobs.update_many(
            {"workspace_id": ws_id, "sender_id": account_id,
             "status": {"$in": ["queued", "running", "finalizing", "repairing"]}},
            {"$set": {"custody_expires_at": now, "custody_expired_at": now,
                      "error": "Sender was disconnected. Verification has stopped.", "updated_at": now},
             "$unset": {"li_at_enc": "", "jsession_id_enc": "", "li_a_enc": ""}})
        await current.outreach_connection_jobs.update_many(
            {"workspace_id": ws_id, "sender_id": account_id,
             "status": {"$in": ["queued", "running"]}, "finalization_prepared": {"$ne": True}},
            {"$set": {"status": "failed", "pending_cleanup_complete": False}})
        # Keep locks, original generations, leases and uncertain request evidence.
        # Existing custody cleanup/explicit drained repair owns their release.
        await current.outreach_campaigns.update_many(
            {"workspace_id": ws_id, "sender_account_ids": account_id},
            {"$pull": {"sender_account_ids": account_id},
             "$set": {"updated_at": now, "status": "paused", "auto_launch_enabled": False},
             "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "sender_unavailable"}})
        await current.outreach_tasks.update_many(
            {"workspace_id": ws_id, "$or": [{"account_id": account_id}, {"assigned_account_id": account_id}],
             "status": {"$in": ["queued", "pending", "scheduled"]}},
            {"$set": {"status": "cancelled", "cancellation_reason": "Sender was disconnected", "updated_at": now}})
    try:
        await suppression.mutate_suppression(db, ws_id, apply)
    except SuppressionUnavailable:
        raise HTTPException(status_code=503, detail="Sender disconnect could not be confirmed; reload its current state") from None

    logger.info("Account %s disconnected; paid-term IP retained for user %s", account_id, user_id)
    return {"status": "success", "message": "Sender disconnected and campaigns paused. Its IP remains reserved through the paid provider term for this sender only."}


class ResumeSenderRequest(BaseModel):
    force: bool = Field(default=False, description="Deprecated; cooldown overrides are rejected")


@router.post("/{account_id}/resume")
async def resume_sender_account(
    account_id: str,
    req: ResumeSenderRequest = ResumeSenderRequest(),
    current_user: dict = require_outreach_permission('account:connect'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Recover an eligible cooled-down connection without resuming work or granting execution.
    """
    from outreach.core.circuit_breaker import CircuitBreaker
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    try:
        result = await CircuitBreaker.resume_sender(
            sender_id=account_id,
            workspace_id=ws_id,
            db=db,
            force=req.force,
        )
        return {"status": "success", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SuppressionUnavailable:
        raise HTTPException(status_code=503, detail="Sender recovery is unavailable; reload its current state") from None
