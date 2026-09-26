"""
Phase 2: Accounts API endpoints for LinkedIn Outbound Engine.
Supports verified session-cookie connection; legacy credential routes are retired.
Allocates 1:1 dedicated static residential proxies JIT upon connection.
"""
import logging
import os
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
    _clean_cookie_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["LinkedIn Outreach Accounts"])


# ── Request / Response DTOs ────────────────────────────────────────────────

class ConnectCookieRequest(BaseModel):
    li_at: str = Field(..., description="LinkedIn session cookie li_at")
    li_a: str | None = Field(default="", description="Optional li_a cookie for Sales Navigator or Recruiter")
    premium_product: str = Field(default="classic", description="classic, sales_navigator, or recruiter")
    user_agent: str | None = Field(default="", description="Browser user agent string")
    jsession_id: str | None = Field(default="", description="JSESSIONID cookie required for live verification")
    country_code: str = Field(default="US", description="2-letter ISO country code for proxy matching")
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
    clean.pop("encrypted_session_cookie", None)
    clean.pop("li_a_enc", None)
    clean.pop("jsession_id", None)
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
    ws_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    cursor = db.outreach_accounts.find({"workspace_id": ws_id})
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
    workspace_id = current_user.get("default_workspace_id") or user_id
    csrf_cookie = _clean_cookie_token(req.jsession_id, "JSESSIONID")
    if not _clean_cookie_token(req.li_at, "li_at"):
        raise HTTPException(status_code=400, detail="LinkedIn li_at session cookie is required")
    if not csrf_cookie and os.getenv("OUTREACH_MOCK_AUTH", "false").lower() not in {"true", "1"}:
        raise HTTPException(status_code=400, detail="LinkedIn JSESSIONID cookie is required")

    # 1. Order static residential proxy (JIT)
    proxy_manager = JITProxyManager()
    if proxy_manager.is_mock and os.getenv("OUTREACH_MOCK_AUTH", "false").lower() not in {"true", "1"}:
        raise HTTPException(status_code=503, detail="A residential proxy is not configured for LinkedIn connection")
    persisted = False
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
            jsession_id=csrf_cookie,
            proxy_url=proxy_url,
            user_agent=req.user_agent,
            li_a=req.li_a,
        )
    except InvalidSessionError as exc:
        # Release the proxy if cookie validation fails
        await proxy_manager.release_proxy(proxy_config.proxy_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        await proxy_manager.release_proxy(proxy_config.proxy_id)
        logger.exception("Could not verify LinkedIn session")
        raise HTTPException(status_code=502, detail="LinkedIn session verification failed. Please retry.") from exc

    try:
        # 3. Encrypt session tokens
        enc_cookie = encrypt_secret(_clean_cookie_token(req.li_at, "li_at"))
        enc_li_a = encrypt_secret(_clean_cookie_token(req.li_a, "li_a")) if req.li_a and req.li_a.strip() else ""
        enc_csrf = encrypt_secret(csrf_cookie)
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
            jsession_id=enc_csrf,
            status=AccountStatus.ACTIVE,
            country_code=req.country_code,
            proxy=proxy_config,
            limits=DailyLimits(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ).model_dump()

        # 4. Save to MongoDB (update if already exists for this workspace, otherwise insert)
        existing = await db.outreach_accounts.find_one({
            "workspace_id": workspace_id,
            "linkedin_urn": profile_data.get("linkedin_urn"),
        }) if profile_data.get("linkedin_urn") else None

        if existing and isinstance(existing, dict):
            await db.outreach_accounts.update_one(
                {"id": existing["id"], "workspace_id": workspace_id},
                {"$set": {
                    "account_name": profile_data["account_name"],
                    "avatar_url": profile_data.get("avatar_url") or existing.get("avatar_url"),
                    "vanity_name": profile_data.get("vanity_name") or existing.get("vanity_name"),
                    "session_cookie_enc": enc_cookie,
                    "li_a_enc": enc_li_a,
                    "premium_product": req.premium_product or "classic",
                    "user_agent": req.user_agent or "",
                    "jsession_id": enc_csrf,
                    "country_code": req.country_code,
                    "status": AccountStatus.ACTIVE,
                    "proxy": proxy_config.model_dump(),
                    "updated_at": datetime.now(timezone.utc),
                }}
            )
            persisted = True
            updated = await db.outreach_accounts.find_one({"id": existing["id"], "workspace_id": workspace_id})
            if not updated:
                raise RuntimeError("Updated LinkedIn account could not be reloaded")
            old_proxy_id = (existing.get("proxy") or {}).get("proxy_id")
            if old_proxy_id and old_proxy_id != proxy_config.proxy_id:
                if not await proxy_manager.release_proxy(old_proxy_id):
                    logger.error("Old proxy %s could not be released after sender refresh", old_proxy_id)
            logger.info("Successfully refreshed session for existing LinkedIn account %s", existing["id"])
            return _sanitize_account(updated)

        await db.outreach_accounts.insert_one(account_doc)
        persisted = True
        logger.info("Successfully connected LinkedIn account %s for user %s", account_doc["id"], user_id)
        return _sanitize_account(account_doc)
    except Exception:
        if not persisted:
            await proxy_manager.release_proxy(proxy_config.proxy_id)
        raise


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


@router.patch("/{account_id}/limits")
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
        {"$set": {"status": AccountStatus.DISCONNECTED, "updated_at": now}},
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

    proxy_id = (account.get("proxy") or {}).get("proxy_id")
    if proxy_id:
        proxy_manager = JITProxyManager()
        if not await proxy_manager.release_proxy(proxy_id):
            raise HTTPException(status_code=502, detail="Sender was disabled, but its proxy could not be released. Retry disconnect to finish cleanup.")

    # Delete account from MongoDB
    await db.outreach_accounts.delete_one({"id": account_id, "workspace_id": ws_id})
    logger.info("Account %s disconnected, unlinked from campaigns, and proxy released for user %s", account_id, user_id)
    return {"status": "success", "message": "Account disconnected, campaigns updated, and proxy deallocated."}
