"""Sender-scoped Gmail and Microsoft mailbox OAuth for the paid outreach pilot.

The API only creates/consumes short-lived OAuth state. Token exchange and
provider profile calls run in the outreach worker, never in a request handler.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from outreach.core.paid_access import _utc, get_active_entitlement
from utils.encryption import decrypt_strict, encrypt


GMAIL_SCOPES = (
    "openid", "email", "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
)
MICROSOFT_SCOPES = ("openid", "offline_access", "User.Read", "Mail.Send", "Mail.Read")
STATE_LIFETIME = timedelta(minutes=10)
JOB_STALE_LIFETIME = timedelta(minutes=15)
SYNC_FRESHNESS = timedelta(minutes=10)


class MailboxUnavailable(Exception):
    """No safe sender/mailbox route is presently available."""


class MailboxTransientError(MailboxUnavailable):
    """A provider or refresh failure may be retried without sending mail."""


class MailboxIdentityConflict(MailboxUnavailable):
    """Changing mailboxes requires human review of prior accepted sends."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    client_id: str
    client_secret: str
    redirect_uri: str
    authorization_url: str
    token_url: str
    scopes: tuple[str, ...]


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"true", "1", "yes"}


def mailbox_connection_enabled() -> bool:
    return _enabled("OUTREACH_MAILBOX_CONNECTION_ENABLED")


def email_send_enabled() -> bool:
    return _enabled("OUTREACH_EMAIL_SEND_ENABLED") and _enabled("OUTREACH_EMAIL_SYNC_ENABLED")


def is_mailbox_pilot_allowed(workspace_id: str | None = None) -> bool:
    """Checks whether mailbox connection is enabled globally and for this specific pilot workspace."""
    if not mailbox_connection_enabled():
        return False
    allowlist = os.getenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "").strip()
    if not allowlist or allowlist == "*":
        return True
    allowed_ids = {ws.strip() for ws in allowlist.split(",") if ws.strip()}
    return bool(workspace_id and workspace_id in allowed_ids)


def is_email_send_pilot_allowed(workspace_id: str | None = None) -> bool:
    """Checks whether email send is enabled globally and for this specific pilot workspace."""
    if not email_send_enabled():
        return False
    allowlist = os.getenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "").strip()
    if not allowlist or allowlist == "*":
        return True
    allowed_ids = {ws.strip() for ws in allowlist.split(",") if ws.strip()}
    return bool(workspace_id and workspace_id in allowed_ids)


def _provider_config(provider: str) -> ProviderConfig:
    if provider == "gmail":
        prefix = "OUTREACH_GMAIL"
        authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
        # Public OAuth endpoint; Bandit's B105 token-name heuristic is a false positive.
        token_url = "https://oauth2.googleapis.com/token"  # nosec B105
        scopes = GMAIL_SCOPES
    elif provider == "microsoft":
        prefix = "OUTREACH_MICROSOFT"
        tenant = os.getenv("OUTREACH_MICROSOFT_TENANT", "common").strip()
        if tenant not in {"common", "organizations", "consumers"} and not (
            len(tenant) == 36 and all(char in "0123456789abcdefABCDEF-" for char in tenant)
        ):
            raise MailboxUnavailable("Microsoft tenant configuration is invalid")
        authorization_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        scopes = MICROSOFT_SCOPES
    else:
        raise HTTPException(status_code=404, detail="Unsupported email provider")
    client_id = os.getenv(f"{prefix}_CLIENT_ID", "").strip()
    client_secret = os.getenv(f"{prefix}_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv(f"{prefix}_REDIRECT_URI", "").strip()
    if not (client_id and client_secret and redirect_uri.startswith("https://")):
        raise MailboxUnavailable(f"{provider.title()} mailbox OAuth is not configured")
    if not redirect_uri.endswith(f"/outreach/mailboxes/{provider}/callback"):
        raise MailboxUnavailable("Mailbox OAuth callback configuration is invalid")
    return ProviderConfig(provider, client_id, client_secret, redirect_uri,
                          authorization_url, token_url, scopes)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def browser_binding_cookie_name(state: str) -> str:
    """A distinct cookie per authorization allows parallel sender connections."""
    return f"outreach_oauth_{_state_hash(state)[:20]}"


async def _paid_sender(db, workspace_id: str, sender_account_id: str) -> bool:
    if not await get_active_entitlement(db, workspace_id):
        return False
    account = await db.outreach_accounts.find_one({
        "workspace_id": workspace_id, "id": sender_account_id, "status": "active",
    }, {"_id": 0, "id": 1})
    if not account:
        return False
    slot = await db.outreach_sender_slots.find_one({
        "workspace_id": workspace_id, "sender_id": sender_account_id,
    }, {"_id": 0, "sender_id": 1})
    return bool(slot)


async def _expire_abandoned_connection_jobs(db, workspace_id: str, sender_account_id: str, now: datetime) -> None:
    """Release the unique sender job slot when authorization or a worker stalled.

    Mongo TTL removal is asynchronous and must not be relied on to unblock a
    new attempt. The compare-and-set status filter keeps a live callback or
    worker from being overwritten after it advances the job.
    """
    await db.outreach_mailbox_connection_jobs.update_many(
        {"workspace_id": workspace_id, "sender_account_id": sender_account_id,
         "$or": [
             {"status": "pending", "authorization_expires_at": {"$lte": now}},
             {"status": "pending", "authorization_expires_at": {"$exists": False},
              "created_at": {"$lte": now - STATE_LIFETIME}},
             {"status": "queued", "updated_at": {"$lte": now - JOB_STALE_LIFETIME}},
             {"status": "running", "started_at": {"$lte": now - JOB_STALE_LIFETIME}},
         ]},
        {"$set": {"status": "failed", "error": "Mailbox connection expired; please try again",
                  "updated_at": now},
         "$unset": {"authorization_code_enc": "", "code_verifier_enc": ""}},
    )


async def start_mailbox_connection(
    db, workspace_id: str, user_id: str, sender_account_id: str, provider: str,
) -> dict:
    if not is_mailbox_pilot_allowed(workspace_id):
        raise HTTPException(status_code=503, detail="Mailbox connections are not enabled for this workspace in the current pilot")
    try:
        config = _provider_config(provider)
    except MailboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if not await get_active_entitlement(db, workspace_id):
        raise HTTPException(status_code=402, detail="A paid sender seat is required")
    if not await _paid_sender(db, workspace_id, sender_account_id):
        raise HTTPException(status_code=404, detail="Paid sender was not found")
    now = datetime.now(timezone.utc)
    await _expire_abandoned_connection_jobs(db, workspace_id, sender_account_id, now)
    in_progress = await db.outreach_mailbox_connection_jobs.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "status": {"$in": ["pending", "queued", "running"]},
    }, {"_id": 1})
    if in_progress:
        raise HTTPException(status_code=409, detail="This sender already has a mailbox connection in progress")
    state = secrets.token_urlsafe(36)
    verifier = secrets.token_urlsafe(64)
    browser_nonce = secrets.token_urlsafe(32)
    job_id = f"mbx_{secrets.token_urlsafe(18)}"
    try:
        await db.outreach_mailbox_connection_jobs.insert_one({
            "id": job_id, "workspace_id": workspace_id, "sender_account_id": sender_account_id,
            "user_id": user_id, "provider": provider, "status": "pending", "created_at": now,
            "authorization_expires_at": now + STATE_LIFETIME,
            "expires_at": now + timedelta(days=1),
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="This sender already has a mailbox connection in progress") from None
    try:
        await db.outreach_mailbox_oauth_states.insert_one({
            "_id": _state_hash(state), "job_id": job_id, "workspace_id": workspace_id,
            "sender_account_id": sender_account_id, "user_id": user_id,
            "provider": provider, "code_verifier_enc": encrypt(verifier),
            "browser_binding_hash": _state_hash(browser_nonce),
            "created_at": now, "expires_at": now + STATE_LIFETIME,
        })
    except Exception:
        await db.outreach_mailbox_connection_jobs.update_one(
            {"workspace_id": workspace_id, "id": job_id, "status": "pending"},
            {"$set": {"status": "failed", "error": "Mailbox authorization could not be started", "updated_at": datetime.now(timezone.utc)}},
        )
        raise
    params = {
        "client_id": config.client_id, "redirect_uri": config.redirect_uri,
        "response_type": "code", "scope": " ".join(config.scopes), "state": state,
        "code_challenge": _pkce_challenge(verifier), "code_challenge_method": "S256",
    }
    if provider == "gmail":
        params.update({"access_type": "offline", "prompt": "consent"})
    else:
        params.update({"response_mode": "query", "prompt": "select_account"})
    return {"authorization_url": f"{config.authorization_url}?{urlencode(params)}",
            "connection_job_id": job_id,
            "browser_binding_nonce": browser_nonce,
            "browser_binding_cookie_name": browser_binding_cookie_name(state)}


def enqueue_connection_job(job_id: str, workspace_id: str) -> None:
    from celery_workers.celery_app import celery_app

    celery_app.send_task(
        "celery_workers.tasks.mailbox.exchange_connection",
        args=[job_id, workspace_id], queue="outreach", ignore_result=True,
    )


async def consume_oauth_callback(
    db, provider: str, state: str, code: str | None, error: str | None = None,
    *, browser_binding_nonce: str | None = None,
) -> str:
    if not state or provider not in {"gmail", "microsoft"} or not browser_binding_nonce:
        raise HTTPException(status_code=400, detail="Invalid mailbox authorization")
    now = datetime.now(timezone.utc)
    state_doc = await db.outreach_mailbox_oauth_states.find_one_and_delete({
        "_id": _state_hash(state), "provider": provider, "expires_at": {"$gt": now},
        "browser_binding_hash": _state_hash(browser_binding_nonce),
    })
    if not state_doc:
        raise HTTPException(status_code=400, detail="Mailbox authorization expired or was already used")
    job_id, workspace_id = state_doc["job_id"], state_doc["workspace_id"]
    if error or not code:
        await db.outreach_mailbox_connection_jobs.update_one(
            {"workspace_id": workspace_id, "id": job_id, "status": "pending"},
            {"$set": {"status": "failed", "error": "Mailbox authorization was declined or incomplete", "updated_at": now}},
        )
        return job_id
    changed = await db.outreach_mailbox_connection_jobs.update_one(
        {"workspace_id": workspace_id, "id": job_id, "status": "pending"},
        {"$set": {"authorization_code_enc": encrypt(code),
                  "code_verifier_enc": state_doc["code_verifier_enc"],
                  "status": "queued", "updated_at": now}},
    )
    if not getattr(changed, "modified_count", 0):
        raise HTTPException(status_code=400, detail="Mailbox authorization could not be claimed")
    try:
        enqueue_connection_job(job_id, workspace_id)
    except Exception:
        await db.outreach_mailbox_connection_jobs.update_one(
            {"workspace_id": workspace_id, "id": job_id, "status": "queued"},
            {"$set": {"status": "failed", "error": "Mailbox connection could not be queued", "updated_at": now},
             "$unset": {"authorization_code_enc": "", "code_verifier_enc": ""}},
        )
    return job_id


async def _token_exchange(config: ProviderConfig, job: dict) -> dict:
    data = {
        "client_id": config.client_id, "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri, "grant_type": "authorization_code",
        "code": decrypt_strict(job["authorization_code_enc"]),
        "code_verifier": decrypt_strict(job["code_verifier_enc"]),
    }
    if config.provider == "microsoft":
        data["scope"] = " ".join(config.scopes)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(config.token_url, data=data)
    if response.status_code != 200:
        raise MailboxUnavailable("Provider authorization failed; reconnect this mailbox")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error") or not payload.get("access_token"):
        raise MailboxUnavailable("Provider did not grant mailbox access")
    granted = set(str(payload.get("scope") or "").lower().split())
    required = ({"https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"}
                if config.provider == "gmail" else {"mail.send", "mail.read"})
    if not required.issubset(granted):
        raise MailboxUnavailable("Required send and reply permissions were not granted")
    return payload


async def _mailbox_identity(provider: str, access_token: str) -> dict:
    url = ("https://gmail.googleapis.com/gmail/v1/users/me/profile" if provider == "gmail"
           else "https://graph.microsoft.com/v1.0/me?$select=id,mail,userPrincipalName")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        raise MailboxUnavailable("Mailbox identity could not be verified")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error"):
        raise MailboxUnavailable("Mailbox identity could not be verified")
    email = (payload.get("emailAddress") if provider == "gmail"
             else payload.get("mail") or payload.get("userPrincipalName"))
    if not isinstance(email, str) or "@" not in email:
        raise MailboxUnavailable("Provider did not return a mailbox address")
    return {"email": email.strip().lower(), "provider_user_id": payload.get("id") or email.strip().lower(),
            "history_id": payload.get("historyId") if provider == "gmail" else None}


async def complete_connection_job(db, workspace_id: str, job_id: str) -> dict:
    """Worker-side code exchange; secrets never appear in task arguments/results."""
    now = datetime.now(timezone.utc)
    claimed = await db.outreach_mailbox_connection_jobs.update_one(
        {"workspace_id": workspace_id, "id": job_id, "status": "queued"},
        {"$set": {"status": "running", "started_at": now}},
    )
    if not getattr(claimed, "modified_count", 0):
        return {"status": "already_claimed"}
    job = await db.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id})
    if not job:
        return {"status": "missing"}
    try:
        if not await _paid_sender(db, workspace_id, job["sender_account_id"]):
            raise MailboxUnavailable("Paid sender access is unavailable")
        config = _provider_config(job["provider"])
        tokens = await _token_exchange(config, job)
        identity = await _mailbox_identity(config.provider, tokens["access_token"])
        old = await db.outreach_mailboxes.find_one({
            "workspace_id": workspace_id, "sender_account_id": job["sender_account_id"],
        })
        same_mailbox = bool(
            old and old.get("provider") == config.provider
            and old.get("provider_user_id") == identity["provider_user_id"]
            and old.get("email") == identity["email"]
        )
        saved_cursor = (old.get("history_id") if config.provider == "gmail" else old.get("delta_url")) if same_mailbox else None
        if old and not saved_cursor:
            outstanding = await db.outreach_email_operations.find_one({
                "workspace_id": workspace_id, "sender_account_id": job["sender_account_id"],
                "status": {"$in": ["dispatching", "uncertain", "accepted"]},
            }, {"_id": 1})
            if outstanding:
                raise MailboxIdentityConflict(
                    "A different mailbox or missing reply cursor requires review of prior sends"
                )
        if old and not same_mailbox and old.get("status") == "active":
            raise MailboxIdentityConflict("Disconnect the existing mailbox before switching accounts")
        if not tokens.get("refresh_token"):
            if not same_mailbox or not old.get("refresh_token_enc"):
                raise MailboxUnavailable("Offline mailbox access was not granted; reconnect and approve access")
            refresh_enc = old["refresh_token_enc"]
        else:
            refresh_enc = encrypt(tokens["refresh_token"])
        if not await _paid_sender(db, workspace_id, job["sender_account_id"]):
            raise MailboxUnavailable("Paid sender access ended during mailbox connection")
        current_job = await db.outreach_mailbox_connection_jobs.find_one({
            "workspace_id": workspace_id, "id": job_id, "status": "running",
        }, {"_id": 1})
        if not current_job:
            raise MailboxUnavailable("Mailbox connection was canceled")
        now = datetime.now(timezone.utc)
        updates = {
            "provider": config.provider, "provider_user_id": identity["provider_user_id"],
            "email": identity["email"], "status": "active", "access_token_enc": encrypt(tokens["access_token"]),
            "refresh_token_enc": refresh_enc, "token_expires_at": now + timedelta(seconds=max(60, int(tokens.get("expires_in") or 3600))),
            "scopes": str(tokens.get("scope") or "").split(),
            "sync_status": "reconnecting" if saved_cursor else "initializing",
            "last_sync_at": None,
            "connected_at": now, "updated_at": now, "connection_job_id": job_id,
        }
        if config.provider == "gmail":
            updates["history_id"] = saved_cursor or identity.get("history_id")
            obsolete_cursor = "delta_url"
        else:
            if saved_cursor:
                updates["delta_url"] = saved_cursor
            obsolete_cursor = "history_id"
        unset_fields = {obsolete_cursor: ""}
        if config.provider == "microsoft" and not saved_cursor:
            unset_fields["delta_url"] = ""
        await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"]},
            {"$set": updates, "$unset": unset_fields,
             "$setOnInsert": {"created_at": now}}, upsert=True,
        )
        # A reconnect MUST process the old cursor before becoming ready.
        # Rebootstrapping at the provider's current cursor would skip every
        # reply received while the sender was disconnected.
        from outreach.core.mailbox_sync import _sync_enabled, bootstrap_mailbox_sync, sync_mailbox_replies

        if saved_cursor:
            if _sync_enabled():
                caught_up = await sync_mailbox_replies(
                    db, workspace_id=workspace_id, sender_account_id=job["sender_account_id"],
                )
                if caught_up.get("status") != "healthy":
                    raise MailboxUnavailable("Reply catch-up did not complete; reconnect after review")
            # If reply sync is disabled, leave 'reconnecting' in place; no
            # sending is possible, and the old cursor is retained for later.
        else:
            await bootstrap_mailbox_sync(db, workspace_id, job["sender_account_id"])
        if not await _paid_sender(db, workspace_id, job["sender_account_id"]) or not await db.outreach_mailbox_connection_jobs.find_one({
            "workspace_id": workspace_id, "id": job_id, "status": "running",
        }, {"_id": 1}):
            await db.outreach_mailboxes.update_one(
                {"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"], "connection_job_id": job_id},
                {"$set": {"status": "reauth_required"},
                 "$unset": {"access_token_enc": "", "refresh_token_enc": ""}},
            )
            raise MailboxUnavailable("Paid sender access ended during mailbox connection")
        completed = await db.outreach_mailbox_connection_jobs.update_one(
            {"workspace_id": workspace_id, "id": job_id, "status": "running"},
            {"$set": {"status": "connected", "updated_at": datetime.now(timezone.utc)},
             "$unset": {"authorization_code_enc": "", "code_verifier_enc": ""}},
        )
        if not getattr(completed, "modified_count", 0):
            raise MailboxUnavailable("Mailbox connection was canceled")
        return {"status": "connected"}
    except Exception as exc:
        # A provider cursor must be initialized before sending. If any step
        # fails after token persistence, revoke our local ability to use it.
        await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"],
             "connection_job_id": job_id},
            {"$set": {"status": "reauth_required", "sync_status": "stale", "updated_at": datetime.now(timezone.utc)},
             "$unset": {"access_token_enc": "", "refresh_token_enc": ""}},
        )
        await db.outreach_mailbox_connection_jobs.update_one(
            {"workspace_id": workspace_id, "id": job_id, "status": "running"},
            {"$set": {"status": "failed", "error": (
                "Mailbox replacement needs manual review of prior sends and reply monitoring"
                if isinstance(exc, MailboxIdentityConflict)
                else "Mailbox connection failed. Check permissions and reconnect."
            ),
                      "updated_at": datetime.now(timezone.utc)},
             "$unset": {"authorization_code_enc": "", "code_verifier_enc": ""}},
        )
        return {"status": "failed"}


async def get_ready_mailbox(db, workspace_id: str, sender_account_id: str) -> dict | None:
    """Read-only readiness check safe to call from campaign launch validation."""
    if not is_email_send_pilot_allowed(workspace_id) or not await _paid_sender(db, workspace_id, sender_account_id):
        return None
    mailbox = await db.outreach_mailboxes.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "status": "active", "sync_status": "healthy",
    })
    if not mailbox or not mailbox.get("access_token_enc") or not mailbox.get("refresh_token_enc"):
        return None
    synced_at = _utc(mailbox.get("last_sync_at"))
    if not synced_at or datetime.now(timezone.utc) - synced_at > SYNC_FRESHNESS:
        return None
    return mailbox


async def get_mailbox_access_token(db, mailbox: dict) -> str:
    """Worker-only refresh with a Mongo lease to prevent refresh-token races."""
    now = datetime.now(timezone.utc)
    workspace_id, sender_id = mailbox["workspace_id"], mailbox["sender_account_id"]
    if not await _paid_sender(db, workspace_id, sender_id):
        raise MailboxUnavailable("Paid sender access is unavailable")
    current = await db.outreach_mailboxes.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_id, "status": "active",
    })
    if (not current or current.get("connection_job_id") != mailbox.get("connection_job_id")
            or not current.get("access_token_enc") or not current.get("refresh_token_enc")):
        raise MailboxUnavailable("Mailbox is no longer active")
    mailbox = current
    expiry = _utc(mailbox.get("token_expires_at"))
    if expiry and expiry > now + timedelta(minutes=5):
        return decrypt_strict(mailbox["access_token_enc"])
    nonce = secrets.token_urlsafe(12)
    connection_job_id = mailbox.get("connection_job_id")
    query = {"workspace_id": workspace_id, "sender_account_id": sender_id, "status": "active",
             "connection_job_id": connection_job_id if connection_job_id else {"$exists": False},
             "$or": [{"refresh_lease_until": {"$lt": now}}, {"refresh_lease_until": {"$exists": False}}]}
    claimed = await db.outreach_mailboxes.find_one_and_update(
        query, {"$set": {"refresh_lease_until": now + timedelta(seconds=45), "refresh_lease_nonce": nonce}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise MailboxTransientError("Mailbox token refresh is already in progress")
    try:
        # Another worker may have refreshed between the caller's read and our lease.
        expiry = _utc(claimed.get("token_expires_at"))
        if expiry and expiry > now + timedelta(minutes=5):
            return decrypt_strict(claimed["access_token_enc"])
        config = _provider_config(claimed["provider"])
        payload = {"client_id": config.client_id, "client_secret": config.client_secret,
                   "refresh_token": decrypt_strict(claimed["refresh_token_enc"]), "grant_type": "refresh_token"}
        if config.provider == "microsoft":
            payload["scope"] = " ".join(config.scopes)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(config.token_url, data=payload)
        if response.status_code in {400, 401}:
            await db.outreach_mailboxes.update_one(
                {"workspace_id": workspace_id, "sender_account_id": sender_id, "refresh_lease_nonce": nonce},
                {"$set": {"status": "reauth_required", "updated_at": datetime.now(timezone.utc)},
                 "$unset": {"access_token_enc": "", "refresh_token_enc": "",
                            "refresh_lease_nonce": "", "refresh_lease_until": ""}},
            )
            raise MailboxUnavailable("Mailbox authorization expired; reconnect")
        if response.status_code != 200:
            raise MailboxTransientError("Mailbox provider is temporarily unavailable")
        data = response.json()
        if not isinstance(data, dict) or data.get("error") or not data.get("access_token"):
            raise MailboxTransientError("Mailbox token refresh returned no access token")
        now = datetime.now(timezone.utc)
        updates = {"access_token_enc": encrypt(data["access_token"]),
                   "token_expires_at": now + timedelta(seconds=max(60, int(data.get("expires_in") or 3600))),
                   "updated_at": now}
        if data.get("refresh_token"):
            updates["refresh_token_enc"] = encrypt(data["refresh_token"])
        if not await _paid_sender(db, workspace_id, sender_id):
            raise MailboxUnavailable("Paid sender access ended during token refresh")
        result = await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": sender_id, "status": "active",
             "refresh_lease_nonce": nonce},
            {"$set": updates},
        )
        if not result.modified_count:
            raise MailboxTransientError("Mailbox state changed during token refresh")
        return data["access_token"]
    finally:
        await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": sender_id, "refresh_lease_nonce": nonce},
            {"$unset": {"refresh_lease_nonce": "", "refresh_lease_until": ""}},
        )
