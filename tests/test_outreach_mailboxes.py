"""Mailbox OAuth, provider delivery, and email-finder fail-closed contracts."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from outreach.core.mailbox_connection import (  # noqa: E402
    complete_connection_job,
    consume_oauth_callback,
    get_mailbox_access_token,
    get_ready_mailbox,
    start_mailbox_connection,
)
from outreach.core.mailbox_delivery import _post_provider_message, send_outreach_email  # noqa: E402
from outreach.core.email_finder import find_lead_email, is_lead_email_available  # noqa: E402
from utils.encryption import decrypt_strict  # noqa: E402


WORKSPACE = "workspace-1"
SENDER = "sender-1"
NOW = datetime.now(timezone.utc)


def _paid():
    return {
        "workspace_id": WORKSPACE, "status": "active", "seats": 1,
        "paid_through": NOW + timedelta(days=30),
        "payment_source": "manual_verified_invoice",
    }


def _db():
    db = MagicMock()
    db.outreach_entitlements.find_one = AsyncMock(return_value=_paid())
    db.outreach_accounts.find_one = AsyncMock(return_value={
        "id": SENDER, "workspace_id": WORKSPACE, "status": "active",
    })
    db.outreach_sender_slots.find_one = AsyncMock(return_value={
        "workspace_id": WORKSPACE, "sender_id": SENDER,
    })
    db.outreach_mailboxes.find_one = AsyncMock(return_value=None)
    db.outreach_email_operations.find_one = AsyncMock(return_value=None)
    db.outreach_mailbox_connection_jobs.insert_one = AsyncMock()
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value=None)
    db.outreach_mailbox_connection_jobs.update_many = AsyncMock()
    db.outreach_mailbox_oauth_states.insert_one = AsyncMock()
    return db


@pytest.fixture
def mailbox_env(monkeypatch):
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "gmail-client")
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET", "gmail-secret")
    monkeypatch.setenv("OUTREACH_GMAIL_REDIRECT_URI", "https://api.example.test/api/v1/outreach/mailboxes/gmail/callback")
    monkeypatch.setenv("OUTREACH_MICROSOFT_CLIENT_ID", "microsoft-client")
    monkeypatch.setenv("OUTREACH_MICROSOFT_CLIENT_SECRET", "microsoft-secret")
    monkeypatch.setenv("OUTREACH_MICROSOFT_REDIRECT_URI", "https://api.example.test/api/v1/outreach/mailboxes/microsoft/callback")


@pytest.mark.asyncio
async def test_mailbox_connection_disabled_by_default_rejects_without_db_work(monkeypatch):
    monkeypatch.delenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", raising=False)
    db = _db()
    with pytest.raises(HTTPException) as exc:
        await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    assert exc.value.status_code == 503
    db.outreach_mailbox_oauth_states.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_start_requires_paid_sender_and_uses_one_time_pkce_state(mailbox_env):
    db = _db()
    result = await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    query = parse_qs(urlparse(result["authorization_url"]).query)
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert "gmail.send" in query["scope"][0]
    assert "gmail.readonly" in query["scope"][0]
    assert result["connection_job_id"]
    state_doc = db.outreach_mailbox_oauth_states.insert_one.await_args.args[0]
    assert state_doc["_id"] != query["state"][0]
    assert decrypt_strict(state_doc["code_verifier_enc"])
    assert state_doc["workspace_id"] == WORKSPACE
    assert state_doc["browser_binding_hash"] != result["browser_binding_nonce"]
    assert state_doc["sender_account_id"] == SENDER
    assert state_doc["expires_at"] <= datetime.now(timezone.utc) + timedelta(minutes=11)
    job = db.outreach_mailbox_connection_jobs.insert_one.await_args.args[0]
    assert "authorization_code_enc" not in job
    db.outreach_entitlements.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_second_oauth_start_for_same_sender_is_rejected(mailbox_env):
    db = _db()
    db.outreach_mailbox_connection_jobs.find_one.return_value = {"id": "already-running"}
    with pytest.raises(HTTPException) as exc:
        await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    assert exc.value.status_code == 409
    db.outreach_mailbox_oauth_states.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_pending_authorization_no_longer_blocks_sender(mailbox_env):
    db = _db()
    stale = {"id": "stale-job", "status": "pending",
             "authorization_expires_at": NOW - timedelta(minutes=1)}

    async def expire_pending(query, update):
        assert query["workspace_id"] == WORKSPACE
        assert query["sender_account_id"] == SENDER
        assert update["$set"]["status"] == "failed"
        assert "authorization_code_enc" in update["$unset"]
        stale["status"] = "failed"

    async def find_active(query, projection):
        return stale if stale["status"] in query["status"]["$in"] else None

    db.outreach_mailbox_connection_jobs.update_many = AsyncMock(side_effect=expire_pending)
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(side_effect=find_active)
    await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    inserted = db.outreach_mailbox_connection_jobs.insert_one.await_args.args[0]
    assert inserted["authorization_expires_at"] - inserted["created_at"] == timedelta(minutes=10)


@pytest.mark.asyncio
async def test_stale_queued_and_running_oauth_jobs_are_failed_before_retry(mailbox_env):
    db = _db()
    await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    query = db.outreach_mailbox_connection_jobs.update_many.await_args.args[0]
    stale_cases = query["$or"]
    assert any(case.get("status") == "queued" for case in stale_cases)
    assert any(case.get("status") == "running" for case in stale_cases)


@pytest.mark.asyncio
async def test_oauth_callback_consumes_state_and_queues_only_job_id(mailbox_env):
    db = _db()
    job_id = "job-1"
    db.outreach_mailbox_oauth_states.find_one_and_delete = AsyncMock(return_value={
        "_id": "hash", "job_id": job_id, "provider": "microsoft",
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "code_verifier_enc": "encrypted-verifier", "expires_at": NOW + timedelta(minutes=2),
    })
    db.outreach_mailbox_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("outreach.core.mailbox_connection.enqueue_connection_job") as enqueue:
        result = await consume_oauth_callback(db, "microsoft", "opaque-state", "private-code", browser_binding_nonce="browser-secret")
    assert result == job_id
    filt = db.outreach_mailbox_oauth_states.find_one_and_delete.await_args.args[0]
    assert filt["provider"] == "microsoft"
    assert filt["expires_at"]["$gt"]
    update = db.outreach_mailbox_connection_jobs.update_one.await_args.args[1]["$set"]
    assert decrypt_strict(update["authorization_code_enc"]) == "private-code"
    assert "private-code" not in str(enqueue.call_args)
    enqueue.assert_called_once_with(job_id, WORKSPACE)
    assert filt["browser_binding_hash"]
    db.outreach_mailbox_oauth_states.find_one_and_delete.return_value = None
    with pytest.raises(HTTPException) as exc:
        await consume_oauth_callback(db, "microsoft", "opaque-state", "private-code", browser_binding_nonce="browser-secret")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_without_initiator_cookie_never_consumes_state(mailbox_env):
    db = _db()
    db.outreach_mailbox_oauth_states.find_one_and_delete = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await consume_oauth_callback(db, "gmail", "valid-state", "code", browser_binding_nonce=None)
    assert exc.value.status_code == 400
    db.outreach_mailbox_oauth_states.find_one_and_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_ready_mailbox_requires_fresh_reply_sync_and_paid_sender(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    doc = {
        "workspace_id": WORKSPACE, "sender_account_id": SENDER, "provider": "gmail",
        "email": "sender@example.com", "status": "active", "access_token_enc": "cipher",
        "refresh_token_enc": "cipher", "sync_status": "healthy",
        "last_sync_at": NOW,
    }
    db.outreach_mailboxes.find_one.return_value = doc
    assert (await get_ready_mailbox(db, WORKSPACE, SENDER))["email"] == "sender@example.com"
    doc["last_sync_at"] = NOW - timedelta(hours=1)
    assert await get_ready_mailbox(db, WORKSPACE, SENDER) is None


@pytest.mark.asyncio
async def test_existing_token_cannot_be_used_after_paid_period_ends():
    db = _db()
    db.outreach_entitlements.find_one.return_value = None
    mailbox = {
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "access_token_enc": "cipher", "token_expires_at": NOW + timedelta(hours=1),
    }
    with pytest.raises(Exception, match="Paid sender access"):
        await get_mailbox_access_token(db, mailbox)


@pytest.mark.asyncio
async def test_disconnected_mailbox_snapshot_cannot_use_unexpired_token():
    from outreach.core.mailbox_connection import MailboxUnavailable

    db = _db()
    mailbox = {
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "status": "active", "access_token_enc": "encrypted-token",
        "token_expires_at": NOW + timedelta(hours=1),
        "connection_job_id": "old-connection",
    }
    db.outreach_mailboxes.find_one.return_value = None
    with pytest.raises(MailboxUnavailable, match="Mailbox is no longer active"):
        await get_mailbox_access_token(db, mailbox)


@pytest.mark.asyncio
async def test_expired_mailbox_token_refresh_is_connection_scoped(mailbox_env):
    from types import SimpleNamespace
    from utils.encryption import encrypt

    db = _db()
    mailbox = {
        "workspace_id": WORKSPACE, "sender_account_id": SENDER, "status": "active",
        "provider": "gmail", "connection_job_id": "current-job",
        "access_token_enc": encrypt("old-access"), "refresh_token_enc": encrypt("refresh-token"),
        "token_expires_at": NOW - timedelta(minutes=1),
    }
    db.outreach_mailboxes.find_one = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.find_one_and_update = AsyncMock(return_value=mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    client = AsyncMock()
    client.post.return_value = httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_connection._provider_config", return_value=SimpleNamespace(
        provider="gmail", client_id="client", client_secret="secret", token_url="https://oauth2.googleapis.com/token",
        scopes=(),
    )), patch("outreach.core.mailbox_connection.httpx.AsyncClient", return_value=context):
        token = await get_mailbox_access_token(db, mailbox)
    assert token == "new-access"
    claim_filter = db.outreach_mailboxes.find_one_and_update.await_args.args[0]
    assert claim_filter["connection_job_id"] == "current-job"
    assert decrypt_strict(db.outreach_mailboxes.update_one.await_args_list[0].args[1]["$set"]["access_token_enc"]) == "new-access"


@pytest.mark.asyncio
async def test_oauth_code_exchange_requires_send_and_read_scopes(mailbox_env):
    from outreach.core.mailbox_connection import MailboxUnavailable, ProviderConfig, _token_exchange
    from utils.encryption import encrypt

    config = ProviderConfig(
        provider="gmail", client_id="client", client_secret="secret",
        redirect_uri="https://app.example.test/api/v1/outreach/mailboxes/gmail/callback",
        authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token", scopes=(),
    )
    job = {"authorization_code_enc": encrypt("private-code"),
           "code_verifier_enc": encrypt("private-verifier")}
    client = AsyncMock()
    client.post.return_value = httpx.Response(200, json={
        "access_token": "access",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
    })
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_connection.httpx.AsyncClient", return_value=context):
        result = await _token_exchange(config, job)
        assert result["access_token"] == "access"
        assert client.post.await_args.kwargs["data"]["code"] == "private-code"
        assert client.post.await_args.kwargs["data"]["code_verifier"] == "private-verifier"
        client.post.return_value = httpx.Response(200, json={
            "access_token": "access", "scope": "https://www.googleapis.com/auth/gmail.send",
        })
        with pytest.raises(MailboxUnavailable, match="permissions"):
            await _token_exchange(config, job)


@pytest.mark.asyncio
async def test_provider_mailbox_identity_is_verified_without_trusting_input_email():
    from outreach.core.mailbox_connection import _mailbox_identity

    client = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_connection.httpx.AsyncClient", return_value=context):
        client.get.return_value = httpx.Response(200, json={
            "emailAddress": "Gmail.User@Example.com", "historyId": "history-1",
        })
        gmail = await _mailbox_identity("gmail", "access")
        client.get.return_value = httpx.Response(200, json={
            "id": "graph-user-id", "mail": "Microsoft.User@Example.com",
        })
        microsoft = await _mailbox_identity("microsoft", "access")
    assert gmail == {"email": "gmail.user@example.com", "provider_user_id": "gmail.user@example.com",
                     "history_id": "history-1"}
    assert microsoft == {"email": "microsoft.user@example.com", "provider_user_id": "graph-user-id",
                         "history_id": None}


@pytest.mark.asyncio
async def test_failed_cursor_bootstrap_scrubs_new_mailbox_tokens(mailbox_env, monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_mailbox_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value={
        "id": "job", "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": "gmail", "authorization_code_enc": "cipher", "code_verifier_enc": "cipher",
    })
    db.outreach_mailboxes.update_one = AsyncMock()
    with patch("outreach.core.mailbox_connection._token_exchange", new_callable=AsyncMock,
               return_value={"access_token": "access", "refresh_token": "refresh",
                             "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"}), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "123"}), \
         patch("outreach.core.mailbox_sync.bootstrap_mailbox_sync", new_callable=AsyncMock,
               side_effect=RuntimeError("cursor failed")):
        result = await complete_connection_job(db, WORKSPACE, "job")
    assert result == {"status": "failed"}
    assert any(
        "access_token_enc" in call.args[1].get("$unset", {})
        and "refresh_token_enc" in call.args[1].get("$unset", {})
        for call in db.outreach_mailboxes.update_one.call_args_list
    )
    db.outreach_entitlements.find_one.return_value = None
    assert await get_ready_mailbox(db, WORKSPACE, SENDER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,old_cursor,identity", [
    ("gmail", {"history_id": "old-123"},
     {"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "new-999"}),
    ("microsoft", {"delta_url": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=old"},
     {"email": "sender@example.com", "provider_user_id": "graph-id", "history_id": None}),
])
async def test_reconnect_catches_up_from_saved_cursor_before_becoming_ready(
    mailbox_env, monkeypatch, provider, old_cursor, identity,
):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_mailbox_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value={
        "id": "job", "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": provider, "authorization_code_enc": "cipher", "code_verifier_enc": "cipher",
    })
    old_mailbox = {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
                   "provider": provider, "provider_user_id": identity["provider_user_id"],
                   "email": identity["email"], "refresh_token_enc": "old-refresh",
                   "status": "reauth_required", **old_cursor}
    db.outreach_mailboxes.find_one = AsyncMock(return_value=old_mailbox)
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("outreach.core.mailbox_connection._token_exchange", new_callable=AsyncMock,
               return_value={"access_token": "access", "refresh_token": "refresh", "scope": "mail.send mail.read"}), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value=identity), \
         patch("outreach.core.mailbox_sync.bootstrap_mailbox_sync", new_callable=AsyncMock) as bootstrap, \
         patch("outreach.core.mailbox_sync.sync_mailbox_replies", new_callable=AsyncMock,
               return_value={"status": "healthy"}) as catch_up:
        result = await complete_connection_job(db, WORKSPACE, "job")
    assert result == {"status": "connected"}
    updates = db.outreach_mailboxes.update_one.await_args_list[0].args[1]["$set"]
    assert updates["sync_status"] == "reconnecting"
    for key, value in old_cursor.items():
        assert updates[key] == value
    catch_up.assert_awaited_once_with(db, workspace_id=WORKSPACE, sender_account_id=SENDER)
    bootstrap.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconnect_with_new_mailbox_and_accepted_sends_fails_closed(mailbox_env, monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_mailbox_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value={
        "id": "job", "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": "gmail", "authorization_code_enc": "cipher", "code_verifier_enc": "cipher",
    })
    db.outreach_mailboxes.find_one = AsyncMock(return_value={
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": "gmail", "provider_user_id": "old@example.com",
        "email": "old@example.com", "history_id": "old-123", "refresh_token_enc": "old-refresh",
    })
    db.outreach_email_operations.find_one = AsyncMock(return_value={"status": "accepted", "recipient": "lead@example.com"})
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    with patch("outreach.core.mailbox_connection._token_exchange", new_callable=AsyncMock,
               return_value={"access_token": "access", "refresh_token": "refresh", "scope": "gmail.send gmail.readonly"}), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "new@example.com", "provider_user_id": "new@example.com", "history_id": "new-999"}), \
         patch("outreach.core.mailbox_sync.bootstrap_mailbox_sync", new_callable=AsyncMock) as bootstrap:
        result = await complete_connection_job(db, WORKSPACE, "job")
    assert result == {"status": "failed"}
    assert not any("access_token_enc" in call.args[1].get("$set", {})
                   for call in db.outreach_mailboxes.update_one.call_args_list)
    query = db.outreach_email_operations.find_one.await_args.args[0]
    assert query == {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
                     "status": {"$in": ["dispatching", "uncertain", "accepted"]}}
    bootstrap.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconnect_catch_up_failure_never_marks_mailbox_healthy(mailbox_env, monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_mailbox_connection_jobs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value={
        "id": "job", "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": "gmail", "authorization_code_enc": "cipher", "code_verifier_enc": "cipher",
    })
    db.outreach_mailboxes.find_one = AsyncMock(return_value={
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "provider": "gmail", "provider_user_id": "sender@example.com", "email": "sender@example.com",
        "history_id": "old-123", "refresh_token_enc": "old-refresh",
    })
    db.outreach_mailboxes.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("outreach.core.mailbox_connection._token_exchange", new_callable=AsyncMock,
               return_value={"access_token": "access", "refresh_token": "refresh", "scope": "gmail.send gmail.readonly"}), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "new-999"}), \
         patch("outreach.core.mailbox_sync.sync_mailbox_replies", new_callable=AsyncMock,
               return_value={"status": "stale"}):
        result = await complete_connection_job(db, WORKSPACE, "job")
    assert result == {"status": "failed"}
    assert any("access_token_enc" in call.args[1].get("$unset", {})
               for call in db.outreach_mailboxes.update_one.call_args_list)


@pytest.mark.asyncio
async def test_send_gmail_is_accepted_not_delivered_and_deduplicates_operation(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead-1", "workspace_id": WORKSPACE, "assigned_account_id": SENDER,
        "campaign_id": "campaign-1", "execution_state": "queued",
        "email": "lead@example.com", "has_replied": False,
    })
    db.outreach_campaigns.find_one = AsyncMock(return_value={"status": "active", "is_deleted": False})
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_email_operations.insert_one = AsyncMock()
    db.outreach_email_operations.update_one = AsyncMock()
    mailbox = {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
               "email": "sender@example.com", "provider": "gmail", "status": "active"}
    response = httpx.Response(200, json={"id": "gmail-1", "threadId": "thread-1"})
    with patch("outreach.core.mailbox_delivery.get_ready_mailbox", new_callable=AsyncMock, return_value=mailbox), patch(
        "outreach.core.mailbox_delivery.get_mailbox_access_token", new_callable=AsyncMock, return_value="access-token"
    ), patch("outreach.core.mailbox_delivery._post_provider_message", new_callable=AsyncMock, return_value=response):
        result = await send_outreach_email(
            db, workspace_id=WORKSPACE, sender_account_id=SENDER, lead_id="lead-1",
            to_email="lead@example.com", subject="Hello", body="Plain text",
            operation_id="step-1",
        )
    assert result["status"] == "accepted"
    assert result["provider_message_id"] == "gmail-1"
    assert "delivered" not in result
    op = db.outreach_email_operations.insert_one.await_args.args[0]
    assert op["status"] == "dispatching"
    assert op["message_id"].startswith("<")
    db.outreach_email_operations.insert_one.side_effect = __import__("pymongo").errors.DuplicateKeyError("duplicate")
    db.outreach_email_operations.find_one = AsyncMock(return_value={"status": "dispatching"})
    duplicate = await send_outreach_email(
        db, workspace_id=WORKSPACE, sender_account_id=SENDER, lead_id="lead-1",
        to_email="lead@example.com", subject="Hello", body="Plain text", operation_id="step-1",
    )
    assert duplicate["status"] == "uncertain"


@pytest.mark.asyncio
async def test_gmail_success_response_without_message_id_is_uncertain_not_rejected(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead-1", "workspace_id": WORKSPACE, "assigned_account_id": SENDER,
        "campaign_id": "campaign-1", "execution_state": "queued", "email": "lead@example.com",
    })
    db.outreach_campaigns.find_one = AsyncMock(return_value={"status": "active", "is_deleted": False})
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_email_operations.insert_one = AsyncMock()
    db.outreach_email_operations.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mailbox = {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
               "email": "sender@example.com", "provider": "gmail", "status": "active"}
    with patch("outreach.core.mailbox_delivery.get_ready_mailbox", new_callable=AsyncMock, return_value=mailbox), \
         patch("outreach.core.mailbox_delivery.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access-token"), \
         patch("outreach.core.mailbox_delivery._post_provider_message", new_callable=AsyncMock,
               return_value=httpx.Response(200, json={})):
        result = await send_outreach_email(
            db, workspace_id=WORKSPACE, sender_account_id=SENDER, lead_id="lead-1",
            to_email="lead@example.com", subject="Hello", body="Plain text",
            operation_id="step-malformed-response",
        )
    assert result["status"] == "uncertain"
    assert db.outreach_email_operations.update_one.await_args.args[1]["$set"]["status"] == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,response,expected_status", [
    ("microsoft", httpx.Response(202), "accepted"),
    ("gmail", httpx.Response(401), "failed"),
])
async def test_provider_acceptance_and_definite_auth_rejection(monkeypatch, provider, response, expected_status):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead-1", "workspace_id": WORKSPACE, "assigned_account_id": SENDER,
        "campaign_id": "campaign-1", "execution_state": "queued", "email": "lead@example.com",
    })
    db.outreach_campaigns.find_one = AsyncMock(return_value={"status": "active", "is_deleted": False})
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_email_operations.insert_one = AsyncMock()
    db.outreach_email_operations.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.outreach_mailboxes.update_one = AsyncMock()
    mailbox = {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
               "email": "sender@example.com", "provider": provider, "status": "active"}
    with patch("outreach.core.mailbox_delivery.get_ready_mailbox", new_callable=AsyncMock, return_value=mailbox), \
         patch("outreach.core.mailbox_delivery.get_mailbox_access_token", new_callable=AsyncMock,
               return_value="access-token"), \
         patch("outreach.core.mailbox_delivery._post_provider_message", new_callable=AsyncMock,
               return_value=response):
        result = await send_outreach_email(
            db, workspace_id=WORKSPACE, sender_account_id=SENDER, lead_id="lead-1",
            to_email="lead@example.com", subject="Hello", body="Plain text",
            operation_id=f"step-{provider}-{response.status_code}",
        )
    assert result["status"] == expected_status
    if response.status_code == 401:
        assert db.outreach_mailboxes.update_one.await_args.args[1]["$set"]["status"] == "reauth_required"


@pytest.mark.asyncio
async def test_provider_post_uses_gmail_raw_and_graph_mime_without_passwords():
    client = AsyncMock()
    client.post.return_value = httpx.Response(202)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_delivery.httpx.AsyncClient", return_value=context):
        await _post_provider_message("gmail", "access", b"MIME")
        gmail = client.post.await_args
        await _post_provider_message("microsoft", "access", b"MIME")
        microsoft = client.post.await_args
    assert gmail.args[0].endswith("/messages/send")
    assert gmail.kwargs["json"]["raw"]
    assert microsoft.args[0].endswith("/sendMail")
    assert microsoft.kwargs["headers"]["Content-Type"] == "text/plain"
    assert "password" not in str(gmail) + str(microsoft)


@pytest.mark.asyncio
async def test_email_send_rechecks_campaign_pause_after_token_refresh(monkeypatch):
    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _db()
    db.outreach_leads.find_one = AsyncMock(return_value={
        "id": "lead-1", "workspace_id": WORKSPACE, "assigned_account_id": SENDER,
        "campaign_id": "campaign-1", "execution_state": "queued",
        "email": "lead@example.com", "has_replied": False,
    })
    db.outreach_campaigns.find_one = AsyncMock(side_effect=[
        {"status": "active", "is_deleted": False},
        {"status": "paused", "is_deleted": False},
    ])
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_email_operations.insert_one = AsyncMock()
    db.outreach_email_operations.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mailbox = {"workspace_id": WORKSPACE, "sender_account_id": SENDER,
               "email": "sender@example.com", "provider": "gmail", "status": "active"}
    with patch("outreach.core.mailbox_delivery.get_ready_mailbox", new_callable=AsyncMock, return_value=mailbox), \
         patch("outreach.core.mailbox_delivery.get_mailbox_access_token", new_callable=AsyncMock, return_value="access-token"), \
         patch("outreach.core.mailbox_delivery._post_provider_message", new_callable=AsyncMock) as provider_post:
        result = await send_outreach_email(
            db, workspace_id=WORKSPACE, sender_account_id=SENDER, lead_id="lead-1",
            to_email="lead@example.com", subject="Hello", body="Plain text",
            operation_id="step-2",
        )
    assert result["status"] == "failed"
    provider_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_finder_uses_found_only_and_never_marks_unknown_as_available(monkeypatch):
    monkeypatch.setenv("OUTREACH_HUNTER_ENABLED", "true")
    db = _db()
    lead = {"id": "lead-1", "workspace_id": WORKSPACE,
            "linkedin_url": "https://www.linkedin.com/in/janedoe/", "email": None}
    db.outreach_leads.find_one = AsyncMock(return_value=lead)
    db.outreach_hunter_credentials.find_one = AsyncMock(return_value={"api_key_enc": "secret"})
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    db.outreach_leads.update_one = AsyncMock()
    with patch("outreach.core.email_finder.decrypt_strict", return_value="hunter-key"), patch(
        "outreach.core.email_finder._hunter_found_request", new_callable=AsyncMock,
        return_value={"data": {"email": "jane@example.com", "source_type": "found",
                               "verification": {"status": "valid"}}},
    ) as hunter:
        result = await find_lead_email(db, workspace_id=WORKSPACE, lead_id="lead-1")
    assert result["status"] == "found"
    assert result["email"] == "jane@example.com"
    assert "email-finder/found" in hunter.await_args.args[0]
    assert await is_lead_email_available(db, WORKSPACE, {"email": "lead@example.com"})
    assert not await is_lead_email_available(db, WORKSPACE, {"email": "bad email"})
    db.outreach_email_suppressions.find_one.return_value = {"email": "lead@example.com"}
    assert not await is_lead_email_available(db, WORKSPACE, {"email": "lead@example.com"})
