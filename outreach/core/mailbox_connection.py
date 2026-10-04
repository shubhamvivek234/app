"""Sender-scoped Gmail and Microsoft mailbox OAuth for the paid outreach pilot.

The API only creates/consumes short-lived OAuth state. Token exchange and
provider profile calls run in the outreach worker, never in a request handler.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from outreach.core.paid_access import _utc, get_active_entitlement
from outreach.core import suppression
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.provider_custody import seal_oauth_secret, open_oauth_secret, seal_mailbox_tokens, open_mailbox_refresh, MailboxAccess, custody_stamp
from outreach.core.session_custody import custody_mode
from celery_workers.shutdown_handler import is_shutting_down
from outreach.core.mailbox_jobs import ACTIVE_JOB_STATES, expire_sender_jobs, claim_job, fail_owned_job, reserve_exchange_budget
from outreach.core.provider_custody import material_digest
from outreach.core.oauth_app_custody import (app_configuration_digest, app_configuration_matches,
    app_identity_digest, validate_app_storage, prepare_app_secret)


GMAIL_SCOPES = (
    "openid", "email", "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
)
MICROSOFT_SCOPES = ("openid", "offline_access", "User.Read", "Mail.Send", "Mail.Read")
STATE_LIFETIME = timedelta(minutes=10)
SYNC_FRESHNESS = timedelta(minutes=10)


class MailboxUnavailable(Exception):
    """No safe sender/mailbox route is presently available."""


class MailboxTransientError(MailboxUnavailable):
    """A proven pre-submission failure may be retried without sending mail."""


class MailboxIdentityConflict(MailboxUnavailable):
    """Changing mailboxes requires human review of prior accepted sends."""


class OAuthRejected(MailboxUnavailable):
    """A received OAuth error definitively rejected this authorization code."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    authorization_url: str
    token_url: str
    scopes: tuple[str, ...]
    app_generation: str = ""


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


def _control_allowed(workspace: str) -> bool:
    return is_mailbox_pilot_allowed(workspace) and not is_shutting_down()


def _deadlines_live(deadlines: list) -> bool:
    return all(_utc(value) and _utc(value) > datetime.now(timezone.utc) for value in deadlines)


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
    plaintext = os.getenv(f"{prefix}_CLIENT_SECRET", "").strip()
    encrypted = os.getenv(f"{prefix}_CLIENT_SECRET_ENC", "").strip()
    generation = os.getenv(f"{prefix}_CLIENT_SECRET_GENERATION", "").strip()
    try:
        mode = custody_mode()
        if (mode == "kms_v1" and plaintext) or (mode == "legacy_fernet" and encrypted):
            raise CustodyUnavailable("OAuth application secret source is ambiguous or incompatible")
        client_secret = encrypted if mode == "kms_v1" else plaintext
    except CustodyUnavailable:
        raise MailboxUnavailable("Mailbox OAuth application custody is unavailable") from None
    redirect_uri = os.getenv(f"{prefix}_REDIRECT_URI", "").strip()
    if not (client_id and client_secret and redirect_uri.startswith("https://")):
        raise MailboxUnavailable(f"{provider.title()} mailbox OAuth is not configured")
    if not redirect_uri.endswith(f"/outreach/mailboxes/{provider}/callback"):
        raise MailboxUnavailable("Mailbox OAuth callback configuration is invalid")
    config = ProviderConfig(provider, client_id, client_secret, redirect_uri,
                            authorization_url, token_url, scopes, generation)
    try:
        validate_app_storage(config)
    except CustodyUnavailable:
        raise MailboxUnavailable("Mailbox OAuth application custody is unavailable") from None
    return config


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
    """Expire unused codes, reclaim proven preparation and hold ambiguous workers."""
    await expire_sender_jobs(db, workspace_id, sender_account_id)


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
        "status": {"$in": list(ACTIVE_JOB_STATES)},
    }, {"_id": 1})
    if in_progress:
        raise HTTPException(status_code=409, detail="This sender already has a mailbox connection in progress")
    state = secrets.token_urlsafe(36)
    verifier = secrets.token_urlsafe(64)
    browser_nonce = secrets.token_urlsafe(32)
    job_id = f"mbx_{secrets.token_urlsafe(18)}"
    job = {"id": job_id, "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "user_id": user_id, "provider": provider, "status": "pending", "created_at": now,
        "protocol_version": 2, "exchange_state": "pending", "app_config_digest": app_configuration_digest(config),
        "authorization_expires_at": now + STATE_LIFETIME, "next_recovery_at": now + STATE_LIFETIME}
    try:
        async def preflight(current):
            fenced = AuthorityDatabase(current.database, current.session, job_id) if isinstance(current, suppression.SuppressionDatabase) else current
            if (not app_configuration_matches(config, job['app_config_digest'])
                    or not await _paid_sender(fenced, workspace_id, sender_account_id)):
                raise MailboxUnavailable("Paid sender changed before mailbox authorization")
        await suppression.mutate_suppression(db, workspace_id, preflight)
        sealed = await seal_oauth_secret(verifier, job, workspace_id, sender_account_id, "oauth_pkce")
        async def save(current):
            await preflight(current)
            if await current.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id,
                    "sender_account_id": sender_account_id, "status": {"$in": list(ACTIVE_JOB_STATES)}}):
                raise HTTPException(409, "This sender already has a mailbox connection in progress or review")
            if datetime.now(timezone.utc) >= job["authorization_expires_at"]:
                raise MailboxUnavailable("Mailbox authorization expired before storage")
            await current.outreach_mailbox_connection_jobs.insert_one(job)
            await current.outreach_mailbox_oauth_states.insert_one({"_id": _state_hash(state), "job_id": job_id,
                "workspace_id": workspace_id, "sender_account_id": sender_account_id, "user_id": user_id,
                "provider": provider, "code_verifier_enc": sealed, "browser_binding_hash": _state_hash(browser_nonce),
                "created_at": now, "expires_at": job["authorization_expires_at"]})
        await suppression.mutate_suppression(db, workspace_id, save)
    except DuplicateKeyError:
        raise HTTPException(409, "This sender already has a mailbox connection in progress") from None
    except (CustodyUnavailable, suppression.SuppressionUnavailable, MailboxUnavailable):
        raise HTTPException(503, "Encrypted mailbox authorization is unavailable; retry after review") from None
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
    lookup = {"_id": _state_hash(state), "provider": provider, "expires_at": {"$gt": now},
        "browser_binding_hash": _state_hash(browser_binding_nonce)}
    state_doc = await db.outreach_mailbox_oauth_states.find_one(lookup)
    if not state_doc:
        raise HTTPException(400, "Mailbox authorization expired or was already used")
    from outreach.core.erasure import require_open_workspace
    workspace_id = state_doc.get('workspace_id')
    await require_open_workspace({'default_workspace_id': workspace_id}, db)
    job_id, sender = state_doc.get('job_id'), state_doc.get('sender_account_id')
    if not all(isinstance(value, str) and value for value in (workspace_id, job_id, sender)):
        raise HTTPException(400, 'Mailbox authorization context is unavailable')
    metadata = {**state_doc, "id": job_id}
    try:
        async def verify(current):
            if not _control_allowed(workspace_id): raise CustodyUnavailable('Mailbox configuration changed')
        await suppression.mutate_suppression(db, workspace_id, verify)
        custody = custody_stamp()
        encrypted = await seal_oauth_secret(code, metadata, workspace_id, sender, "oauth_code") if code and not error else None
        async def consume(current):
            await verify(current)
            if custody_stamp() != custody: raise CustodyUnavailable('OAuth custody configuration changed')
            fenced = AuthorityDatabase(current.database, current.session, job_id) if isinstance(current, suppression.SuppressionDatabase) else current
            fresh = await fenced.outreach_mailbox_oauth_states.find_one({**lookup, "workspace_id": workspace_id,
                "expires_at": {"$gt": datetime.now(timezone.utc)}})
            job = await fenced.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id,
                "sender_account_id": sender, "provider": provider, "status": "pending"})
            if not fresh or not job or fresh.get("code_verifier_enc") != state_doc.get("code_verifier_enc"):
                raise HTTPException(400, "Mailbox authorization expired or was already used")
            deleted = await current.outreach_mailbox_oauth_states.delete_one({**lookup, "workspace_id": workspace_id})
            if deleted.deleted_count != 1: raise HTTPException(400, "Mailbox authorization could not be consumed")
            changes = {"status": "queued", "authorization_code_enc": encrypted,
                "code_verifier_enc": state_doc["code_verifier_enc"], "protocol_version": 2, "exchange_state": "pending",
                "next_publish_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)} if encrypted else {
                "status": "failed", "error": "Mailbox authorization was declined or incomplete", "updated_at": datetime.now(timezone.utc)}
            changed = await current.outreach_mailbox_connection_jobs.update_one({"workspace_id": workspace_id, "id": job_id,
                "status": "pending"}, {"$set": changes})
            if changed.matched_count != 1: raise HTTPException(400, "Mailbox authorization could not be claimed")
        await suppression.mutate_suppression(db, workspace_id, consume)
    except (CustodyUnavailable, suppression.SuppressionUnavailable):
        raise HTTPException(503, "Encrypted mailbox authorization is unavailable") from None
    if not encrypted: return job_id
    try:
        enqueue_connection_job(job_id, workspace_id)
    except Exception:
        # The committed due reference survives broker failure; beat republishes.
        # Codes stay encrypted and still obey their original use deadline.
        pass
    return job_id


async def _token_exchange(config: ProviderConfig, job: dict, *, preflight=None) -> dict:
    custody = custody_stamp()
    app_secret = await prepare_app_secret(config, job=job)
    data = {
        "client_id": config.client_id, "client_secret": app_secret.value,
        "redirect_uri": config.redirect_uri, "grant_type": "authorization_code",
        "code": await open_oauth_secret(job["authorization_code_enc"], job, job.get("workspace_id"), job.get("sender_account_id"), "oauth_code"),
        "code_verifier": await open_oauth_secret(job["code_verifier_enc"], job, job.get("workspace_id"), job.get("sender_account_id"), "oauth_pkce"),
    }
    if config.provider == "microsoft":
        data["scope"] = " ".join(config.scopes)
    deadline = _utc(job.get("authorization_expires_at"))
    if custody_mode() == "kms_v1" and (not deadline or deadline <= datetime.now(timezone.utc) or not preflight):
        raise MailboxUnavailable("Mailbox authorization custody expired or is unguarded")
    if not app_secret.matches():
        raise MailboxUnavailable('Mailbox OAuth application changed before authorization')
    deadlines = (await preflight() or []) if preflight else []
    async with httpx.AsyncClient(timeout=20) as client:
        if not app_secret.matches() or custody_stamp() != custody or preflight and (not _deadlines_live(deadlines) or not _control_allowed(job['workspace_id']) or deadline and deadline <= datetime.now(timezone.utc)):
            raise MailboxUnavailable('Mailbox authorization changed before transport')
        response = await client.post(config.token_url, data=data)
    if response.status_code != 200:
        if response.status_code in {400, 401}:
            try:
                rejected = response.json()
            except ValueError:
                rejected = None
            if isinstance(rejected, dict) and isinstance(rejected.get("error"), str) and rejected["error"]:
                raise OAuthRejected("Provider rejected mailbox authorization; reconnect")
        raise MailboxUnavailable("Provider authorization failed; reconnect this mailbox")
    payload = response.json()
    if (not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("access_token"), str)
            or not payload["access_token"]):
        raise MailboxUnavailable("Provider did not grant mailbox access")
    if payload.get("refresh_token") is not None and (
            not isinstance(payload["refresh_token"], str) or not payload["refresh_token"]):
        raise MailboxUnavailable("Provider returned invalid offline mailbox access")
    lifetime = payload.get("expires_in", 3600)
    try:
        seconds = int(lifetime)
    except (ValueError, TypeError, OverflowError):
        raise MailboxUnavailable("Provider returned invalid mailbox token lifetime") from None
    if isinstance(lifetime, bool) or not 0 < seconds <= 86400:
        raise MailboxUnavailable("Provider returned invalid mailbox token lifetime")
    payload["expires_in"] = seconds
    granted = set(str(payload.get("scope") or "").lower().split())
    required = ({"https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"}
                if config.provider == "gmail" else {"mail.send", "mail.read"})
    if not required.issubset(granted):
        raise MailboxUnavailable("Required send and reply permissions were not granted")
    return payload


async def _mailbox_identity(provider: str, access_token: str, *, preflight=None) -> dict:
    url = ("https://gmail.googleapis.com/gmail/v1/users/me/profile" if provider == "gmail"
           else "https://graph.microsoft.com/v1.0/me?$select=id,mail,userPrincipalName")
    async with httpx.AsyncClient(timeout=20) as client:
        if preflight: await preflight()
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
    owner = secrets.token_urlsafe(18)
    job = await claim_job(db, workspace_id, job_id, owner)
    if not job:
        return {"status": "already_claimed"}
    if job.get("status") == "failed": return {"status": "failed"}
    install_generation = None
    custody = custody_stamp()
    try:
        if not await _paid_sender(db, workspace_id, job["sender_account_id"]):
            raise MailboxUnavailable("Paid sender access is unavailable")
        config = _provider_config(job["provider"])
        app_digest = app_configuration_digest(config)
        if (job.get('app_config_digest') and job['app_config_digest'] != app_digest
                or custody_mode() == 'kms_v1' and not job.get('app_config_digest')):
            raise MailboxUnavailable('Mailbox authorization application changed or is unproven')
        async def exchange_preflight(*, authorize=False):
            async def check(current):
                fenced = AuthorityDatabase(current.database, current.session, owner) if isinstance(current, suppression.SuppressionDatabase) else current
                live = await fenced.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id,
                    "status": "running", "connection_owner": owner})
                if (not live or not app_configuration_matches(config, app_digest) or custody_stamp() != custody or not _control_allowed(workspace_id)
                        or any(live.get(name) != job.get(name) for name in ('app_config_digest', 'authorization_code_enc', 'code_verifier_enc', 'provider', 'sender_account_id'))
                        or not _utc(live.get('authorization_expires_at')) or _utc(live['authorization_expires_at']) <= datetime.now(timezone.utc)
                        or not _utc(live.get('lease_until')) or _utc(live['lease_until']) <= datetime.now(timezone.utc)
                        or not await _paid_sender(fenced, workspace_id, job["sender_account_id"])):
                    raise MailboxUnavailable("Mailbox authorization owner changed")
                if authorize:
                    await reserve_exchange_budget(current, workspace_id, job['sender_account_id'], datetime.now(timezone.utc))
                    changed = await current.outreach_mailbox_connection_jobs.update_one({"workspace_id": workspace_id,
                        "id": job_id, "status": "running", "connection_owner": owner, "exchange_state": "preparing"},
                        {"$set": {"exchange_state": "possible", "exchange_submitted_at": datetime.now(timezone.utc)}})
                    if changed.matched_count != 1: raise MailboxUnavailable("Mailbox exchange is already submitted or held")
                return [*(list(fenced.deadlines) if isinstance(fenced, AuthorityDatabase) else []),
                    live['lease_until'], live['authorization_expires_at']]
            deadlines = await suppression.mutate_suppression(db, workspace_id, check)
            if not app_configuration_matches(config, app_digest) or not _deadlines_live(deadlines) or custody_stamp() != custody or not _control_allowed(workspace_id):
                raise MailboxUnavailable('Mailbox authorization expired after commit')
            return deadlines
        async def authorize_exchange():
            return await exchange_preflight(authorize=True)
        tokens = await _token_exchange(config, job, preflight=authorize_exchange)
        await exchange_preflight()
        identity = await _mailbox_identity(config.provider, tokens["access_token"], preflight=exchange_preflight)
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
            if (not same_mailbox or not old.get("refresh_token_enc")
                    or old.get('oauth_app_identity_digest') != app_identity_digest(config)):
                raise MailboxUnavailable("Offline mailbox access was not granted; reconnect and approve access")
            refresh_value = await open_mailbox_refresh(old, workspace_id, job["sender_account_id"])
        else:
            refresh_value = tokens["refresh_token"]
        if not await _paid_sender(db, workspace_id, job["sender_account_id"]):
            raise MailboxUnavailable("Paid sender access ended during mailbox connection")
        current_job = await db.outreach_mailbox_connection_jobs.find_one({
            "workspace_id": workspace_id, "id": job_id, "status": "running", "connection_owner": owner,
        }, {"_id": 1})
        if not current_job:
            raise MailboxUnavailable("Mailbox connection was canceled")
        now = datetime.now(timezone.utc)
        updates = {
            "provider": config.provider, "provider_user_id": identity["provider_user_id"],
            "oauth_app_identity_digest": app_identity_digest(config),
            "email": identity["email"], "status": "active", "token_expires_at": _utc(job['started_at']) + timedelta(seconds=int(tokens.get("expires_in") or 3600)),
            "scopes": str(tokens.get("scope") or "").split(),
            "sync_status": "reconnecting" if saved_cursor else "initializing",
            "last_sync_at": None,
            "connected_at": now, "updated_at": now, "connection_job_id": job_id,
        }
        updates.update(await seal_mailbox_tokens({"access_token": tokens["access_token"], "refresh_token": refresh_value},
            {"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"], **updates}, workspace_id, job["sender_account_id"]))
        install_generation = updates['custody_generation']
        if config.provider == "gmail":
            updates["history_id"] = saved_cursor or identity.get("history_id")
            obsolete_cursor = "delta_url"
        else:
            if saved_cursor:
                updates["delta_url"] = saved_cursor
            obsolete_cursor = "history_id"
        unset_fields = {obsolete_cursor: "", "refresh_lease_nonce": "", "refresh_lease_until": ""}
        if config.provider == "microsoft" and not saved_cursor:
            unset_fields["delta_url"] = ""
        async def install(current):
            from outreach.core.credential_migration import _stable
            fenced = AuthorityDatabase(current.database, current.session, owner) if isinstance(current, suppression.SuppressionDatabase) else current
            live = await fenced.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id,
                "status": "running", "connection_owner": owner})
            prior = await fenced.outreach_mailboxes.find_one({"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"]})
            if (not live or not app_configuration_matches(config, app_digest) or custody_stamp() != custody or not _control_allowed(workspace_id) or not await _paid_sender(fenced, workspace_id, job["sender_account_id"])
                    or live.get('exchange_state') not in {'preparing', 'possible'}
                    or any(live.get(name) != job.get(name) for name in ('app_config_digest', 'authorization_code_enc', 'code_verifier_enc', 'provider', 'sender_account_id'))
                    or not _utc(live.get('authorization_expires_at')) or _utc(live['authorization_expires_at']) <= datetime.now(timezone.utc)
                    or not _utc(live.get('lease_until')) or _utc(live['lease_until']) <= datetime.now(timezone.utc)
                    or _stable(prior) != _stable(old)):
                raise MailboxUnavailable("Mailbox owner changed before credential installation")
            await current.outreach_mailboxes.update_one({"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"]},
                {"$set": updates, "$unset": {**unset_fields, "refresh_state": "", "refresh_submitted_at": ""},
                    "$setOnInsert": {"created_at": now}}, upsert=True)
            receipt = await current.outreach_mailbox_connection_jobs.update_one({"workspace_id": workspace_id, "id": job_id,
                "status": "running", "connection_owner": owner}, {"$set": {"status": "connected", "exchange_state": "installed",
                    "installed_generation": install_generation, "installed_material_digest": material_digest(
                        {"workspace_id": workspace_id, "sender_account_id": job["sender_account_id"], **updates}, "mailbox"),
                    "installed_at": now, "updated_at": now}, "$unset": {"authorization_code_enc": "", "code_verifier_enc": "",
                        "expires_at": "", "lease_until": ""}})
            if receipt.matched_count != 1: raise MailboxUnavailable("Mailbox installation receipt owner changed")
        await suppression.mutate_suppression(db, workspace_id, install)
        # OAuth installation is complete. Independent polling initializes or
        # catches up from the preserved cursor; healthy freshness still gates send.
        return {"status": "connected"}
    except Exception as exc:
        # A lost commit acknowledgement cannot revoke a committed installation.
        saved = await db.outreach_mailbox_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id,
            "status": "connected", "connection_owner": owner, "exchange_state": "installed"})
        if saved: return {"status": "connected"}
        return await fail_owned_job(db, job, rejected=isinstance(exc, OAuthRejected))


async def get_ready_mailbox(db, workspace_id: str, sender_account_id: str) -> dict | None:
    """Read-only readiness check safe to call from campaign launch validation."""
    if not is_email_send_pilot_allowed(workspace_id) or not await _paid_sender(db, workspace_id, sender_account_id):
        return None
    mailbox = await db.outreach_mailboxes.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "status": "active", "sync_status": "healthy",
    })
    if (not mailbox or not mailbox.get("access_token_enc") or not mailbox.get("refresh_token_enc")
            or mailbox.get("refresh_state") in {"possible", "unknown"}):
        return None
    synced_at = _utc(mailbox.get("last_sync_at"))
    now = datetime.now(timezone.utc)
    if not synced_at or synced_at > now or now - synced_at > SYNC_FRESHNESS:
        return None
    return mailbox


async def get_mailbox_access_token(db, mailbox: dict, *, parent_preflight=None, parent_allowed=None) -> str | MailboxAccess:
    """Worker-only access preparation; uncertain refreshes remain held."""
    from outreach.core.mailbox_refresh import get_access
    return await get_access(db, mailbox, parent_preflight=parent_preflight, parent_allowed=parent_allowed)
