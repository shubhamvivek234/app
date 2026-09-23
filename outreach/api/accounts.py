"""
Phase 2: Accounts API endpoints for LinkedIn Outbound Engine.
Supports Session Cookie (li_at) connection and Credential Login with 2FA Challenge Relay.
Allocates 1:1 dedicated static residential proxies JIT upon connection.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.models import (
    AccountAuthMode,
    AccountStatus,
    DailyLimits,
    OutreachAccount,
)
from outreach.core.crypto import encrypt_secret, decrypt_secret
from outreach.core.proxy_manager import JITProxyManager
from outreach.engine.session_authenticator import (
    SessionAuthenticator,
    InvalidSessionError,
    AuthenticationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["LinkedIn Outreach Accounts"])


# ── Request / Response DTOs ────────────────────────────────────────────────

class ConnectCookieRequest(BaseModel):
    li_at: str = Field(..., description="LinkedIn session cookie li_at")
    li_a: str | None = Field(default="", description="Optional li_a cookie for Sales Navigator or Recruiter")
    premium_product: str = Field(default="classic", description="classic, sales_navigator, or recruiter")
    user_agent: str | None = Field(default="", description="Browser user agent string")
    jsession_id: str | None = Field(default="", description="Optional JSESSIONID cookie")
    country_code: str = Field(default="US", description="2-letter ISO country code for proxy matching")
    workspace_id: str | None = None


class LoginStartRequest(BaseModel):
    email: str
    password: str
    country_code: str = Field(default="US")
    workspace_id: str | None = None


class LoginVerify2FARequest(BaseModel):
    session_id: str
    code: str
    country_code: str = Field(default="US")
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


def _sanitize_account(acc: dict[str, Any]) -> dict[str, Any]:
    """Strips secret tokens from response payloads."""
    clean = dict(acc)
    clean.pop("session_cookie_enc", None)
    clean.pop("li_a_enc", None)
    clean.pop("_id", None)
    if clean.get("proxy"):
        clean["proxy"] = dict(clean["proxy"])
        clean["proxy"].pop("password_enc", None)
    return clean


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
async def list_outreach_accounts(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists all connected LinkedIn sender accounts for the active user."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    cursor = db.outreach_accounts.find({
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    accounts = await cursor.to_list(length=100)
    return [_sanitize_account(a) for a in accounts]



@router.post("/connect-cookie")
async def connect_via_cookie(
    req: ConnectCookieRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Connects a LinkedIn account using the li_at session cookie.
    Automatically provisions a 1:1 dedicated static residential proxy.
    """
    user_id = current_user.get("user_id")
    workspace_id = req.workspace_id or current_user.get("default_workspace_id") or "default_ws"

    # 1. Order static residential proxy (JIT)
    proxy_manager = JITProxyManager()
    try:
        proxy_config = await proxy_manager.order_static_residential_proxy(country_code=req.country_code)
    except Exception as exc:
        logger.error("Failed to allocate proxy for account: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to allocate dedicated residential proxy. Please retry.",
        ) from exc

    # 2. Validate session cookie through the proxy
    proxy_url = proxy_manager.format_proxy_url(proxy_config)
    try:
        profile_data = await SessionAuthenticator.validate_session_cookie(
            li_at=req.li_at,
            jsession_id=req.jsession_id or "",
            proxy_url=proxy_url,
            user_agent=req.user_agent,
            li_a=req.li_a,
        )
    except InvalidSessionError as exc:
        # Release the proxy if cookie validation fails
        await proxy_manager.release_proxy(proxy_config.proxy_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # 3. Encrypt session tokens
    enc_cookie = encrypt_secret(req.li_at)
    enc_li_a = encrypt_secret(req.li_a.strip()) if req.li_a and req.li_a.strip() else ""
    account_doc = OutreachAccount(
        workspace_id=workspace_id,
        user_id=user_id,
        account_name=profile_data["account_name"],
        avatar_url=profile_data.get("avatar_url"),
        linkedin_urn=profile_data.get("linkedin_urn"),
        vanity_name=profile_data.get("vanity_name"),
        auth_mode=AccountAuthMode.COOKIE,
        session_cookie_enc=enc_cookie,
        li_a_enc=enc_li_a,
        premium_product=req.premium_product or "classic",
        user_agent=req.user_agent or "",
        jsession_id=req.jsession_id or "",
        status=AccountStatus.ACTIVE,
        country_code=req.country_code,
        proxy=proxy_config,
        limits=DailyLimits(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).model_dump()

    # 4. Save to MongoDB (update if already exists for this user, otherwise insert)
    existing = await db.outreach_accounts.find_one({
        "user_id": user_id,
        "linkedin_urn": profile_data.get("linkedin_urn"),
    }) if profile_data.get("linkedin_urn") else None

    if existing and isinstance(existing, dict):
        await db.outreach_accounts.update_one(
            {"id": existing["id"]},
            {"$set": {
                "account_name": profile_data["account_name"],
                "avatar_url": profile_data.get("avatar_url") or existing.get("avatar_url"),
                "vanity_name": profile_data.get("vanity_name") or existing.get("vanity_name"),
                "session_cookie_enc": enc_cookie,
                "li_a_enc": enc_li_a,
                "premium_product": req.premium_product or "classic",
                "user_agent": req.user_agent or "",
                "status": AccountStatus.ACTIVE,
                "proxy": proxy_config.model_dump(),
                "updated_at": datetime.now(timezone.utc),
            }}
        )
        updated = await db.outreach_accounts.find_one({"id": existing["id"]})
        logger.info("Successfully refreshed session for existing LinkedIn account %s", existing["id"])
        return _sanitize_account(updated)

    await db.outreach_accounts.insert_one(account_doc)
    logger.info("Successfully connected LinkedIn account %s for user %s", account_doc["id"], user_id)
    return _sanitize_account(account_doc)


@router.post("/login-start")
async def login_start(
    req: LoginStartRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Starts email + password login flow. Returns 2FA challenge if required by LinkedIn.
    """
    user_id = current_user.get("user_id")
    workspace_id = req.workspace_id or current_user.get("default_workspace_id") or "default_ws"

    proxy_manager = JITProxyManager()
    proxy_config = await proxy_manager.order_static_residential_proxy(country_code=req.country_code)
    proxy_url = proxy_manager.format_proxy_url(proxy_config)

    try:
        auth_result = await SessionAuthenticator.start_credential_login(
            email=req.email,
            password=req.password,
            proxy_url=proxy_url,
        )
    except AuthenticationError as exc:
        await proxy_manager.release_proxy(proxy_config.proxy_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # If 2FA is needed, return challenge session ID to frontend modal
    if auth_result.get("status") == "2fa_required":
        return {
            "status": "2fa_required",
            "session_id": auth_result["session_id"],
            "challenge_type": auth_result.get("challenge_type", "otp"),
            "message": auth_result.get("message"),
        }

    # Direct login succeeded without 2FA
    enc_cookie = encrypt_secret(auth_result["li_at"])
    account_doc = OutreachAccount(
        workspace_id=workspace_id,
        user_id=user_id,
        account_name=auth_result["account_name"],
        avatar_url=auth_result.get("avatar_url"),
        linkedin_urn=auth_result.get("linkedin_urn"),
        vanity_name=auth_result.get("vanity_name"),
        auth_mode=AccountAuthMode.CREDENTIALS,
        session_cookie_enc=enc_cookie,
        jsession_id=auth_result.get("jsession_id", ""),
        status=AccountStatus.ACTIVE,
        country_code=req.country_code,
        proxy=proxy_config,
        limits=DailyLimits(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).model_dump()

    await db.outreach_accounts.insert_one(account_doc)
    return {
        "status": "authenticated",
        "account": _sanitize_account(account_doc),
    }


@router.post("/login-verify-2fa")
async def login_verify_2fa(
    req: LoginVerify2FARequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Completes 2FA login with the OTP verification code.
    """
    user_id = current_user.get("user_id")
    workspace_id = req.workspace_id or current_user.get("default_workspace_id") or "default_ws"

    try:
        auth_result = await SessionAuthenticator.verify_2fa_code(
            session_id=req.session_id,
            otp_code=req.code,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    proxy_manager = JITProxyManager()
    proxy_config = await proxy_manager.order_static_residential_proxy(country_code=req.country_code)

    enc_cookie = encrypt_secret(auth_result["li_at"])
    account_doc = OutreachAccount(
        workspace_id=workspace_id,
        user_id=user_id,
        account_name=auth_result["account_name"],
        avatar_url=auth_result.get("avatar_url"),
        linkedin_urn=auth_result.get("linkedin_urn"),
        vanity_name=auth_result.get("vanity_name"),
        auth_mode=AccountAuthMode.CREDENTIALS,
        session_cookie_enc=enc_cookie,
        jsession_id=auth_result.get("jsession_id", ""),
        status=AccountStatus.ACTIVE,
        country_code=req.country_code,
        proxy=proxy_config,
        limits=DailyLimits(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).model_dump()

    await db.outreach_accounts.insert_one(account_doc)
    return {
        "status": "authenticated",
        "account": _sanitize_account(account_doc),
    }


@router.patch("/{account_id}/limits")
async def update_account_limits(
    account_id: str,
    req: UpdateLimitsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Updates daily safety caps for a specific connected account."""
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    account = await db.outreach_accounts.find_one({
        "id": account_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
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
        await db.outreach_accounts.update_one({"id": account_id}, {"$set": updates})

    updated_account = await db.outreach_accounts.find_one({"id": account_id})
    return _sanitize_account(updated_account)


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Disconnects the LinkedIn account and immediately tears down the dedicated proxy.
    """
    user_id = current_user.get("user_id")
    ws_id = current_user.get("default_workspace_id") or "default_ws"
    account = await db.outreach_accounts.find_one({
        "id": account_id,
        "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": ws_id}],
    })
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Release proxy
    if account.get("proxy") and account["proxy"].get("proxy_id"):
        proxy_manager = JITProxyManager()
        await proxy_manager.release_proxy(account["proxy"]["proxy_id"])

    now = datetime.now(timezone.utc)
    # Relational Cascade: Unbind account from campaign sender pools
    await db.outreach_campaigns.update_many(
        {"sender_account_ids": account_id},
        {"$pull": {"sender_account_ids": account_id}, "$set": {"updated_at": now}}
    )

    # Relational Cascade: Cancel queued/pending tasks scheduled on this account
    await db.outreach_tasks.update_many(
        {"account_id": account_id, "status": {"$in": ["queued", "pending", "scheduled"]}},
        {"$set": {
            "status": "cancelled",
            "cancellation_reason": f"Sender account {account_id} was disconnected",
            "updated_at": now,
        }}
    )

    # Delete account from MongoDB
    await db.outreach_accounts.delete_one({"id": account_id})
    logger.info("Account %s disconnected, unlinked from campaigns, and proxy released for user %s", account_id, user_id)
    return {"status": "success", "message": "Account disconnected, campaigns updated, and proxy deallocated."}
