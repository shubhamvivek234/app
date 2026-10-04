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
    cursor = MagicMock()
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_mailbox_connection_jobs.find.return_value = cursor
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
    db = _connection_db()
    db.outreach_mailbox_connection_jobs.docs[0].update(status="pending",
        authorization_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    assert db.outreach_mailbox_connection_jobs.docs[0]["status"] == "failed"
    inserted = db.outreach_mailbox_connection_jobs.docs[1]
    assert inserted["authorization_expires_at"] - inserted["created_at"] == timedelta(minutes=10)


@pytest.mark.asyncio
async def test_stale_unmarked_running_oauth_job_is_held_before_retry(mailbox_env):
    db = _connection_db()
    row = db.outreach_mailbox_connection_jobs.docs[0]
    row.update(status="running", started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    row.pop("protocol_version")
    row.pop("exchange_state")
    with pytest.raises(HTTPException) as denied:
        await start_mailbox_connection(db, WORKSPACE, "owner-1", SENDER, "gmail")
    assert denied.value.status_code == 409 and row["status"] == "review_required"


@pytest.mark.asyncio
async def test_oauth_callback_consumes_state_and_queues_only_job_id(mailbox_env):
    from tests.outreach_memory import Database
    from utils.encryption import encrypt
    from outreach.core.mailbox_connection import _state_hash
    job_id = "job-1"
    db = Database(outreach_mailbox_oauth_states=[{
        "_id": _state_hash("opaque-state"), "job_id": job_id, "provider": "microsoft",
        "workspace_id": WORKSPACE, "sender_account_id": SENDER,
        "browser_binding_hash": _state_hash("browser-secret"),
        "code_verifier_enc": encrypt("verifier"), "expires_at": datetime.now(timezone.utc) + timedelta(minutes=2),
    }], outreach_mailbox_connection_jobs=[{
        "id": job_id, "workspace_id": WORKSPACE, "sender_account_id": SENDER, "provider": "microsoft", "status": "pending",
    }])
    with patch("outreach.core.mailbox_connection.enqueue_connection_job") as enqueue:
        result = await consume_oauth_callback(db, "microsoft", "opaque-state", "private-code", browser_binding_nonce="browser-secret")
    assert result == job_id and not db.outreach_mailbox_oauth_states.docs
    queued = db.outreach_mailbox_connection_jobs.docs[0]
    assert queued["status"] == "queued" and decrypt_strict(queued["authorization_code_enc"]) == "private-code"
    assert "private-code" not in str(enqueue.call_args)
    enqueue.assert_called_once_with(job_id, WORKSPACE)
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
    doc["last_sync_at"] = NOW + timedelta(hours=1)
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
async def test_disconnected_mailbox_snapshot_cannot_use_unexpired_token(mailbox_env):
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

    from tests.outreach_memory import Database
    mailbox = {
        "workspace_id": WORKSPACE, "sender_account_id": SENDER, "status": "active",
        "provider": "gmail", "provider_user_id": "u", "email": "sender@example.com", "connection_job_id": "current-job",
        "access_token_enc": encrypt("old-access"), "refresh_token_enc": encrypt("refresh-token"),
        "token_expires_at": NOW - timedelta(minutes=1),
    }
    db = Database(outreach_mailboxes=[mailbox])
    client = AsyncMock()
    client.post.return_value = httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_connection._provider_config", return_value=SimpleNamespace(
        provider="gmail", client_id="client", client_secret="secret", token_url="https://oauth2.googleapis.com/token",
        scopes=(),
    )), patch("outreach.core.mailbox_connection.httpx.AsyncClient", return_value=context), patch("outreach.core.mailbox_connection._paid_sender", AsyncMock(return_value=True)):
        token = await get_mailbox_access_token(db, mailbox)
    assert token == "new-access"
    current = db.outreach_mailboxes.docs[0]
    assert current["connection_job_id"] == "current-job"
    assert decrypt_strict(current["access_token_enc"]) == "new-access"
    assert not current.get("refresh_state") and not current.get("refresh_lease_nonce")


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
    job = {"provider": "gmail", "authorization_code_enc": encrypt("private-code"),
           "code_verifier_enc": encrypt("private-verifier")}
    client = AsyncMock()
    client.post.return_value = httpx.Response(200, json={
        "access_token": "access",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
    })
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("outreach.core.mailbox_connection.httpx.AsyncClient", return_value=context), \
         patch("outreach.core.mailbox_connection._provider_config", return_value=config):
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


def _connection_db(provider="gmail", mailbox=None):
    from tests.outreach_memory import Database
    from tests.test_outreach_mailbox_job_lifecycle import job_row
    return Database(outreach_entitlements=[_paid()],
        outreach_accounts=[{"workspace_id": WORKSPACE, "id": SENDER, "status": "active"}],
        outreach_sender_slots=[{"workspace_id": WORKSPACE, "sender_id": SENDER}],
        outreach_mailbox_connection_jobs=[job_row(workspace_id=WORKSPACE, sender_account_id=SENDER, provider=provider)],
        outreach_mailboxes=[mailbox] if mailbox else [])


async def _mock_exchange(config, job, *, preflight):
    await preflight()
    return {"access_token": "access", "refresh_token": "refresh", "scope": "send read"}


@pytest.mark.asyncio
async def test_cursor_bootstrap_is_independent_of_committed_oauth_install(mailbox_env, monkeypatch):
    db = _connection_db()
    with patch("outreach.core.mailbox_connection._token_exchange", side_effect=_mock_exchange), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "123"}), \
         patch("outreach.core.mailbox_sync.bootstrap_mailbox_sync", new_callable=AsyncMock,
               side_effect=RuntimeError("cursor failed")) as bootstrap:
        assert await complete_connection_job(db, WORKSPACE, "job") == {"status": "connected"}
    bootstrap.assert_not_awaited()
    mailbox = db.outreach_mailboxes.docs[0]
    assert mailbox["sync_status"] == "initializing" and decrypt_strict(mailbox["access_token_enc"]) == "access"
    assert await get_ready_mailbox(db, WORKSPACE, SENDER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,old_cursor,identity", [
    ("gmail", {"history_id": "old-123"},
     {"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "new-999"}),
    ("microsoft", {"delta_url": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=old"},
     {"email": "sender@example.com", "provider_user_id": "graph-id", "history_id": None}),
])
async def test_reconnect_preserves_saved_cursor_for_independent_catchup(mailbox_env, provider, old_cursor, identity):
    old = {"workspace_id": WORKSPACE, "sender_account_id": SENDER, "provider": provider,
        "provider_user_id": identity["provider_user_id"], "email": identity["email"],
        "status": "reauth_required", **old_cursor}
    db = _connection_db(provider, old)
    with patch("outreach.core.mailbox_connection._token_exchange", side_effect=_mock_exchange), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock, return_value=identity), \
         patch("outreach.core.mailbox_sync.bootstrap_mailbox_sync", new_callable=AsyncMock) as bootstrap, \
         patch("outreach.core.mailbox_sync.sync_mailbox_replies", new_callable=AsyncMock) as catchup:
        assert await complete_connection_job(db, WORKSPACE, "job") == {"status": "connected"}
    saved = db.outreach_mailboxes.docs[0]
    assert saved["sync_status"] == "reconnecting"
    for key, value in old_cursor.items(): assert saved[key] == value
    bootstrap.assert_not_awaited()
    catchup.assert_not_awaited()
    assert await get_ready_mailbox(db, WORKSPACE, SENDER) is None


@pytest.mark.asyncio
async def test_reconnect_with_new_mailbox_and_accepted_sends_is_held_for_review(mailbox_env):
    old = {"workspace_id": WORKSPACE, "sender_account_id": SENDER, "provider": "gmail",
        "provider_user_id": "old@example.com", "email": "old@example.com", "history_id": "old-123", "status": "reauth_required"}
    db = _connection_db(mailbox=old)
    db.outreach_email_operations.docs.append({"workspace_id": WORKSPACE, "sender_account_id": SENDER, "status": "accepted"})
    with patch("outreach.core.mailbox_connection._token_exchange", side_effect=_mock_exchange), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "new@example.com", "provider_user_id": "new@example.com", "history_id": "new-999"}):
        assert await complete_connection_job(db, WORKSPACE, "job") == {"status": "review_required"}
    assert db.outreach_mailboxes.docs[0] == old
    assert not db.outreach_mailbox_connection_jobs.docs[0].get("authorization_code_enc")


@pytest.mark.asyncio
async def test_reconnect_never_marks_mailbox_healthy_before_separate_catchup(mailbox_env):
    old = {"workspace_id": WORKSPACE, "sender_account_id": SENDER, "provider": "gmail",
        "provider_user_id": "sender@example.com", "email": "sender@example.com", "history_id": "old-123", "status": "reauth_required"}
    db = _connection_db(mailbox=old)
    with patch("outreach.core.mailbox_connection._token_exchange", side_effect=_mock_exchange), \
         patch("outreach.core.mailbox_connection._mailbox_identity", new_callable=AsyncMock,
               return_value={"email": "sender@example.com", "provider_user_id": "sender@example.com", "history_id": "new-999"}):
        assert await complete_connection_job(db, WORKSPACE, "job") == {"status": "connected"}
    assert db.outreach_mailboxes.docs[0]["sync_status"] == "reconnecting"
    assert not db.outreach_mailboxes.docs[0]["last_sync_at"]
    assert db.outreach_mailboxes.docs[0]["access_token_enc"]


async def _provider_fixture(monkeypatch, response, provider="gmail", source="email_send"):
    from tests.test_outreach_provider_boundary import ready
    db, envelope, binding = await ready(monkeypatch, provider, source)
    monkeypatch.setattr("outreach.core.mailbox_delivery.get_ready_mailbox", AsyncMock(side_effect=lambda *args: db.outreach_mailboxes.docs[0]))
    monkeypatch.setattr("outreach.core.mailbox_delivery.get_mailbox_access_token", AsyncMock(return_value="fake-access"))
    client = AsyncMock()
    client.post.return_value = response
    client.get.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: context)
    return db, binding, client


async def _send_fixture(db, binding):
    from outreach.core.request_guard import request_parent
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        return await send_outreach_email(db, workspace_id="w", sender_account_id="a", lead_id="l",
            to_email="lead@example.com", subject="Hello", body="Reviewed body", operation_id="l:n")


@pytest.mark.asyncio
async def test_send_gmail_is_accepted_not_delivered_and_deduplicates_operation(monkeypatch):
    db, binding, client = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": "message", "threadId": "thread"}))
    result = await _send_fixture(db, binding)
    assert result == {"status": "accepted", "provider_message_id": "message", "provider_thread_id": "thread"}
    assert (await _send_fixture(db, binding))["status"] == "accepted"
    client.post.assert_awaited_once()
    assert db.outreach_email_operations.docs[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_gmail_success_response_without_message_id_is_uncertain_not_rejected(monkeypatch):
    db, binding, client = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": ""}))
    assert (await _send_fixture(db, binding))["status"] == "uncertain"
    assert (await _send_fixture(db, binding))["status"] == "uncertain"
    client.post.assert_awaited_once()
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,response,expected_status", [
    ("microsoft", httpx.Response(202), "accepted"), ("gmail", httpx.Response(401), "failed")])
async def test_provider_acceptance_and_definite_auth_rejection(monkeypatch, provider, response, expected_status):
    db, binding, client = await _provider_fixture(monkeypatch, response, provider)
    assert (await _send_fixture(db, binding))["status"] == expected_status
    client.post.assert_awaited_once()
    if response.status_code == 401:
        assert db.outreach_mailboxes.docs[0]["status"] == "reauth_required"


@pytest.mark.asyncio
async def test_provider_post_uses_gmail_raw_and_graph_mime_without_passwords():
    client = AsyncMock()
    client.post.return_value = httpx.Response(202)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    envelope = MagicMock(spec=["assert_email", "assert_bearer", "call"])
    async def allow(method, path, factory, **kwargs):
        return await factory()
    envelope.call = allow  # Isolate HTTP formatting; envelope policy has separate tests.
    with patch("outreach.core.mailbox_delivery.httpx.AsyncClient", return_value=context):
        await _post_provider_message("gmail", "access", b"MIME", envelope=envelope)
        gmail = client.post.await_args
        await _post_provider_message("microsoft", "access", b"MIME", envelope=envelope)
        microsoft = client.post.await_args
    assert gmail.args[0].endswith("/messages/send") and gmail.kwargs["json"]["raw"]
    assert microsoft.args[0].endswith("/sendMail")
    assert microsoft.kwargs["headers"]["Content-Type"] == "text/plain"


@pytest.mark.asyncio
async def test_email_send_rechecks_campaign_pause_after_token_refresh(monkeypatch):
    from outreach.core.request_guard import RequestDenied
    db, binding, client = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": "m"}))
    async def refresh(*args):
        db.outreach_campaigns.docs[0]["status"] = "paused"
        return "fake-access"
    monkeypatch.setattr("outreach.core.mailbox_delivery.get_mailbox_access_token", refresh)
    with pytest.raises(RequestDenied):
        await _send_fixture(db, binding)
    client.post.assert_not_awaited()
    assert db.outreach_email_operations.docs[0]["status"] == "not_submitted"


@pytest.mark.asyncio
async def test_email_finder_uses_found_only_and_never_marks_unknown_as_available(monkeypatch):
    from outreach.core.request_guard import request_parent
    response = httpx.Response(200, json={"data": {"email": "jane@example.com", "source_type": "found", "verification": {"status": "valid"}}})
    db, _, client = await _provider_fixture(monkeypatch, response, source="email_find")
    with request_parent("owner", AsyncMock(return_value=None)):
        result = await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n")
    assert result["status"] == "found" and result["email"] == "jane@example.com"
    assert client.get.await_args.args[0].endswith("/email-finder/found")
    assert db.outreach_leads.docs[0]["email"] == "jane@example.com"
    assert not await is_lead_email_available(db, "w", {"email": "bad email"})
    await db.outreach_email_suppressions.insert_one({"workspace_id": "w", "email": "jane@example.com"})
    assert not await is_lead_email_available(db, "w", db.outreach_leads.docs[0])


@pytest.mark.asyncio
async def test_accepted_email_receipt_repairs_lost_confirmation_without_second_post(monkeypatch):
    db, binding, client = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": "m"}))
    write = db.outreach_email_operations.update_one
    async def fail_confirmation(query, update, **kwargs):
        if update.get("$set", {}).get("status") == "accepted" and not update["$set"].get("repaired_from_physical_receipt"):
            raise RuntimeError("fake confirmation outage")
        return await write(query, update, **kwargs)
    monkeypatch.setattr(db.outreach_email_operations, "update_one", fail_confirmation)
    assert (await _send_fixture(db, binding))["status"] == "uncertain"
    assert (await _send_fixture(db, binding))["status"] == "accepted"
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_finder_profile_edit_during_request_cannot_attach_old_result(monkeypatch):
    from outreach.core.request_guard import request_parent
    response = httpx.Response(200, json={"data": {"email": "old@example.com", "source_type": "found", "verification": {"status": "valid"}}})
    db, _, client = await _provider_fixture(monkeypatch, response, source="email_find")
    async def edit(*args, **kwargs):
        db.outreach_leads.docs[0]["linkedin_url"] = "https://www.linkedin.com/in/another-person"
        return response
    client.get.side_effect = edit
    with request_parent("owner", AsyncMock(return_value=None)):
        assert (await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n"))["status"] == "found"
    assert not db.outreach_leads.docs[0].get("email")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401])
async def test_old_mailbox_refresh_cannot_overwrite_or_scrub_reconnected_credentials(monkeypatch, status):
    monkeypatch.setenv('OUTREACH_MAILBOX_CONNECTION_ENABLED', 'true')
    from outreach.core import mailbox_connection as module
    from tests.outreach_memory import Database
    from types import SimpleNamespace
    from utils.encryption import encrypt
    mailbox = {"workspace_id": "w", "sender_account_id": "a", "provider": "gmail", "provider_user_id": "u",
        "email": "old@example.com", "connection_job_id": "old", "status": "active",
        "access_token_enc": encrypt("old-access"), "refresh_token_enc": encrypt("old-refresh"), "token_expires_at": NOW}
    db = Database(outreach_mailboxes=[mailbox])
    monkeypatch.setattr(module, "_paid_sender", AsyncMock(return_value=True))
    monkeypatch.setattr(module, "_provider_config", lambda value: SimpleNamespace(provider="gmail", client_id="fake", client_secret="fake", token_url="https://example.invalid/token"))
    async def reconnect(*args, **kwargs):
        db.outreach_mailboxes.docs[0].update(connection_job_id="new", email="new@example.com", access_token_enc="new-access",
            refresh_token_enc="new-refresh", refresh_lease_nonce="new-lease")
        return httpx.Response(status, json={"access_token": "stale-token"})
    client = AsyncMock()
    client.post.side_effect = reconnect
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: context)
    with pytest.raises(module.MailboxUnavailable):
        await get_mailbox_access_token(db, mailbox)
    current = db.outreach_mailboxes.docs[0]
    assert current["access_token_enc"] == "new-access" and current["refresh_token_enc"] == "new-refresh"
    assert current["status"] == "active" and current["refresh_lease_nonce"] == "new-lease"


@pytest.mark.asyncio
async def test_finder_timeout_keeps_stable_operation_unknown_and_does_not_spend_again(monkeypatch):
    from outreach.core.request_guard import request_parent
    db, _, client = await _provider_fixture(monkeypatch, httpx.Response(200), source="email_find")
    client.get.side_effect = httpx.ReadTimeout("fake timeout")
    with request_parent("owner", AsyncMock(return_value=None)):
        for _ in range(2):
            assert (await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n"))["status"] == "uncertain"
    client.get.assert_awaited_once()
    assert db.outreach_email_discoveries.docs[0]["status"] == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [httpx.Response(404), httpx.Response(200, json={"data": {"email": "guessed@example.com", "source_type": "inferred", "verification": {"status": "valid"}}}), httpx.Response(200, json={"data": {"email": "unknown@example.com", "source_type": "found", "verification": {"status": "unknown"}}})])
async def test_finder_non_found_outcomes_are_durable_without_email_projection(monkeypatch, response):
    from outreach.core.request_guard import request_parent
    db, _, client = await _provider_fixture(monkeypatch, response, source="email_find")
    with request_parent("owner", AsyncMock(return_value=None)):
        for _ in range(2):
            assert (await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n"))["status"] == "not_found"
    client.get.assert_awaited_once()
    assert not db.outreach_leads.docs[0].get("email")


@pytest.mark.asyncio
async def test_proven_noncall_email_operation_can_reclaim_with_a_new_explicit_permission(monkeypatch):
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.request_guard import RequestDenied
    from outreach.core.provider_boundary import provider_generation
    db, binding, client = await _provider_fixture(monkeypatch, httpx.Response(200, json={"id": "m"}))
    await ExecutionPermission(db).revoke("w", "a", "human", "stop")
    with pytest.raises(RequestDenied):
        await _send_fixture(db, binding)
    assert db.outreach_email_operations.docs[0]["status"] == "not_submitted"
    await ExecutionPermission(db).grant("w", "a", provider_generation(db.outreach_accounts.docs[0], db.outreach_mailboxes.docs[0], "email_send"), ["email_send"], "human", clear_latch=True)
    assert (await _send_fixture(db, binding))["status"] == "accepted"
    client.post.assert_awaited_once()
    assert len(db.outreach_email_operations.docs[0]["non_call_history"]) == 1


@pytest.mark.asyncio
async def test_proven_noncall_finder_can_reclaim_without_repeating_an_attempt(monkeypatch):
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.provider_boundary import provider_generation
    from outreach.core.request_guard import RequestDenied, request_parent
    db, _, client = await _provider_fixture(monkeypatch, httpx.Response(404), source="email_find")
    await ExecutionPermission(db).revoke("w", "a", "human", "stop")
    with request_parent("owner", AsyncMock(return_value=None)):
        with pytest.raises(RequestDenied):
            await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n")
        await ExecutionPermission(db).grant("w", "a", provider_generation(db.outreach_accounts.docs[0], db.outreach_hunter_credentials.docs[0], "email_find"), ["email_find"], "human", clear_latch=True)
        assert (await find_lead_email(db, workspace_id="w", lead_id="l", sender_account_id="a", operation_id="l:n"))["status"] == "not_found"
    client.get.assert_awaited_once()
    assert len(db.outreach_email_discoveries.docs[0]["non_call_history"]) == 1
