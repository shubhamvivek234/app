"""Durable OAuth publication, exact owners and interruption fencing; no providers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio
import os
from cryptography.fernet import Fernet

import httpx
import pytest
from fastapi import HTTPException

from outreach.core import mailbox_connection as connection
from tests.outreach_memory import Database
from utils.encryption import encrypt

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())


def job_row(**changes):
    now = datetime.now(timezone.utc)
    return {"id": "job", "workspace_id": "w", "sender_account_id": "a", "provider": "gmail",
        "protocol_version": 2, "status": "queued", "exchange_state": "pending",
        "created_at": now, "updated_at": now, "authorization_expires_at": now + timedelta(minutes=10),
        "next_publish_at": now, "authorization_code_enc": encrypt("private-code"),
        "code_verifier_enc": encrypt("private-verifier"), **changes}


@pytest.fixture
def lifecycle(monkeypatch):
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "false")
    monkeypatch.setattr(connection, "is_shutting_down", lambda: False)
    monkeypatch.setattr(connection, "_paid_sender", AsyncMock(return_value=True))
    monkeypatch.setattr(connection, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    monkeypatch.setattr(connection, "_provider_config", lambda _: SimpleNamespace(provider="gmail", client_id="local",
        client_secret="local-secret", redirect_uri="https://local.invalid/callback", scopes=(),
        authorization_url="https://accounts.google.com/authorize", token_url="https://local.invalid/token"))
    return Database(outreach_mailbox_connection_jobs=[job_row()])


def http_context(monkeypatch, *, failure=None, enter=None):
    http = AsyncMock()
    http.post.return_value = httpx.Response(200, json={"access_token": "private-access", "refresh_token": "private-refresh",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"})
    http.get.return_value = httpx.Response(200, json={"emailAddress": "sender@example.com", "historyId": "cursor"})
    if failure is not None:
        http.post.side_effect = failure
    ctx = AsyncMock()
    ctx.__aenter__.return_value = http
    if enter:
        ctx.__aenter__.side_effect = enter
    monkeypatch.setattr(connection.httpx, "AsyncClient", lambda **_: ctx)
    return http


@pytest.mark.asyncio
async def test_callback_broker_failure_preserves_due_encrypted_job(lifecycle, monkeypatch):
    db = lifecycle
    row = db.outreach_mailbox_connection_jobs.docs[0]
    row["status"] = "pending"
    nonce, state = "browser", "state"
    db.outreach_mailbox_oauth_states.docs.append({"_id": connection._state_hash(state), "job_id": "job",
        "workspace_id": "w", "sender_account_id": "a", "provider": "gmail", "code_verifier_enc": encrypt("verifier"),
        "browser_binding_hash": connection._state_hash(nonce), "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)})
    monkeypatch.setattr(connection, "enqueue_connection_job", lambda *_: (_ for _ in ()).throw(RuntimeError("private broker error")))
    assert await connection.consume_oauth_callback(db, "gmail", state, "code", browser_binding_nonce=nonce) == "job"
    saved = db.outreach_mailbox_connection_jobs.docs[0]
    assert saved["status"] == "queued" and saved["next_publish_at"] <= datetime.now(timezone.utc)
    assert saved["authorization_code_enc"] and saved["code_verifier_enc"]
    assert "private broker error" not in str(saved)


@pytest.mark.asyncio
async def test_due_publisher_failure_is_fair_and_reference_only(lifecycle):
    from outreach.core.mailbox_jobs import publish_due_jobs
    db = lifecycle
    db.outreach_mailbox_connection_jobs.docs.append(job_row(id="other", workspace_id="other-workspace", sender_account_id="b"))
    sent = []
    def publish(job, workspace):
        sent.append((job, workspace))
        if job == "job": raise RuntimeError("local broker failed")
    result = await publish_due_jobs(db, publish)
    assert result == {"published": 1, "failed": 1}
    assert sent == [("job", "w"), ("other", "other-workspace")]
    assert all(row["status"] == "queued" and row["next_publish_at"] > datetime.now(timezone.utc)
        for row in db.outreach_mailbox_connection_jobs.docs)
    assert await publish_due_jobs(db, publish) == {"published": 0, "failed": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout("private provider failure"), asyncio.CancelledError()])
async def test_exchange_interruption_keeps_hold_and_cannot_replay(lifecycle, monkeypatch, failure):
    db = lifecycle
    http = http_context(monkeypatch, failure=failure)
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError): await connection.complete_connection_job(db, "w", "job")
    else:
        assert (await connection.complete_connection_job(db, "w", "job"))["status"] == "review_required"
    row = db.outreach_mailbox_connection_jobs.docs[0]
    assert row["exchange_state"] in {"possible", "unknown"}
    row["lease_until"] = datetime.now(timezone.utc) - timedelta(days=1)
    await connection._expire_abandoned_connection_jobs(db, "w", "a", datetime.now(timezone.utc))
    assert row["status"] == "review_required" and not row.get("expires_at")
    await connection.complete_connection_job(db, "w", "job")
    http.post.assert_awaited_once()
    with pytest.raises(HTTPException) as blocked: await connection.start_mailbox_connection(db, "w", "user", "a", "gmail")
    assert blocked.value.status_code == 409


@pytest.mark.asyncio
async def test_possible_is_saved_before_transport_and_duplicate_worker_cannot_post(lifecycle, monkeypatch):
    db = lifecycle
    http = http_context(monkeypatch)
    async def post(*args, **kwargs):
        saved = db.outreach_mailbox_connection_jobs.docs[0]
        assert saved["exchange_state"] == "possible" and saved["connection_owner"]
        assert (await connection.complete_connection_job(db, "w", "job"))["status"] == "already_claimed"
        return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh",
            "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"})
    http.post.side_effect = post
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "connected"}
    row = db.outreach_mailbox_connection_jobs.docs[0]
    mailbox = db.outreach_mailboxes.docs[0]
    assert row["exchange_state"] == "installed" and row["installed_generation"] == mailbox["custody_generation"]
    assert not row.get("authorization_code_enc") and not row.get("code_verifier_enc")
    assert mailbox["sync_status"] == "initializing"
    http.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["preparing", "possible", "unknown", None])
async def test_stale_worker_recovery_only_requeues_proven_preparing(lifecycle, stage):
    from outreach.core.mailbox_jobs import recover_due_jobs
    db = lifecycle
    row = db.outreach_mailbox_connection_jobs.docs[0]
    row.update(status="running", exchange_state=stage, connection_owner="old",
        lease_until=datetime.now(timezone.utc) - timedelta(seconds=1), started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    await recover_due_jobs(db)
    if stage == "preparing":
        assert row["status"] == "queued" and not row.get("connection_owner")
    else:
        assert row["status"] == "review_required"


@pytest.mark.asyncio
async def test_expired_authorization_and_disabled_controls_never_construct_http(lifecycle, monkeypatch):
    db = lifecycle
    db.outreach_mailbox_connection_jobs.docs[0]["authorization_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    factory = AsyncMock(side_effect=AssertionError("No provider"))
    monkeypatch.setattr(connection.httpx, "AsyncClient", factory)
    assert (await connection.complete_connection_job(db, "w", "job"))["status"] == "failed"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_installed_commit_ack_loss_preserves_tokens_and_never_exchanges_again(lifecycle, monkeypatch):
    from outreach.core import suppression
    db = lifecycle
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == "install": raise TimeoutError("local lost acknowledgement")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", lost)
    assert (await connection.complete_connection_job(db, "w", "job"))["status"] == "connected"
    mailbox = db.outreach_mailboxes.docs[0]
    assert mailbox["access_token_enc"] and mailbox["refresh_token_enc"] and mailbox["status"] == "active"
    await connection.complete_connection_job(db, "w", "job")
    http.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_keeps_possible_evidence_and_blocks_reconnect(lifecycle):
    from outreach.api.mailboxes import disconnect_mailbox
    db = lifecycle
    row = db.outreach_mailbox_connection_jobs.docs[0]
    row.update(status="running", exchange_state="possible", connection_owner="owner")
    db.outreach_mailboxes.docs.append({"workspace_id": "w", "sender_account_id": "a", "status": "active",
        "access_token_enc": "old", "refresh_token_enc": "old"})
    assert await disconnect_mailbox("a", current_user={"default_workspace_id": "w"}, db=db) == {"status": "disconnected"}
    assert row["status"] == "review_required" and row["exchange_state"] == "possible"
    assert not row.get("authorization_code_enc")


@pytest.mark.asyncio
async def test_worker_preparation_replacement_during_open_never_calls_provider(lifecycle, monkeypatch):
    db = lifecycle
    opening = connection.open_oauth_secret
    async def replace(*args):
        result = await opening(*args)
        db.outreach_mailbox_connection_jobs.docs[0]["connection_owner"] = "replacement"
        return result
    monkeypatch.setattr(connection, "open_oauth_secret", replace)
    http = http_context(monkeypatch)
    await connection.complete_connection_job(db, "w", "job")
    http.post.assert_not_awaited()
    assert db.outreach_mailbox_connection_jobs.docs[0]["connection_owner"] == "replacement"


@pytest.mark.asyncio
@pytest.mark.parametrize("response,expected", [
    (httpx.Response(400, json={"error": "invalid_grant"}), "failed"),
    (httpx.Response(401, json={"error": "invalid_client"}), "failed"),
    (httpx.Response(400, text="private unparsed response"), "review_required"),
    (httpx.Response(500, json={"error": "temporary"}), "review_required"),
    (httpx.Response(200, json={"access_token": None}), "review_required"),
])
async def test_only_received_oauth_rejection_can_close_possible_exchange(lifecycle, monkeypatch, response, expected):
    http = http_context(monkeypatch)
    http.post.return_value = response
    assert (await connection.complete_connection_job(lifecycle, "w", "job"))["status"] == expected
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    assert row["exchange_state"] == ("rejected" if expected == "failed" else "unknown")
    assert not row.get("authorization_code_enc") and not row.get("code_verifier_enc")
    assert lifecycle.outreach_mailbox_exchange_budgets.docs[0]["used"] == 1


@pytest.mark.asyncio
async def test_daily_budget_blocks_a_new_exchange_without_consuming_another_call(lifecycle, monkeypatch):
    from outreach.core.mailbox_jobs import reserve_exchange_budget, DAILY_EXCHANGE_LIMIT
    now = datetime.now(timezone.utc)
    for _ in range(DAILY_EXCHANGE_LIMIT): await reserve_exchange_budget(lifecycle, "w", "a", now)
    http = http_context(monkeypatch)
    assert (await connection.complete_connection_job(lifecycle, "w", "job"))["status"] == "failed"
    http.post.assert_not_awaited()
    assert lifecycle.outreach_mailbox_exchange_budgets.docs[0]["used"] == DAILY_EXCHANGE_LIMIT


@pytest.mark.asyncio
async def test_paid_expiry_keeps_ambiguous_job_review_after_reactivation(lifecycle):
    from outreach.core.paid_access import expire_due_entitlements
    db = lifecycle
    row = db.outreach_mailbox_connection_jobs.docs[0]
    row.update(status="running", exchange_state="possible", connection_owner="owner")
    db.outreach_entitlements.docs.append({"workspace_id": "w", "status": "active",
        "paid_through": datetime.now(timezone.utc) - timedelta(seconds=1)})
    # The old in-memory fake needs the historical delete-many fixture only;
    # actual ordering/retention is tested again over a replica set.
    db.outreach_mailbox_oauth_states.delete_many = AsyncMock()
    assert await expire_due_entitlements(db) == 1
    assert row["status"] == "review_required" and row["exchange_state"] == "possible"
    db.outreach_entitlements.docs[0].update(status="active", paid_through=datetime.now(timezone.utc) + timedelta(days=30))
    with pytest.raises(HTTPException) as denied: await connection.start_mailbox_connection(db, "w", "user", "a", "gmail")
    assert denied.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["publish", "recover"])
async def test_disabled_or_closed_prefix_does_not_starve_later_jobs(lifecycle, monkeypatch, scheduler):
    from outreach.core import mailbox_jobs, erasure, suppression
    db = lifecycle
    rows = [job_row(id=f"blocked-{i}", workspace_id=f"closed-{i}") for i in range(50)] + [job_row(id="good")]
    for row in rows:
        row["next_recovery_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    if scheduler == "recover":
        for row in rows:
            row.update(status="running", exchange_state="preparing", connection_owner="old",
                lease_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    db.outreach_mailbox_connection_jobs.docs = rows
    async def control(database, workspace, operation): return await operation(database)
    monkeypatch.setattr(erasure, "_control", control)
    mutate = suppression.mutate_suppression
    async def closed(database, workspace, operation):
        if workspace.startswith("closed"): raise suppression.SuppressionUnavailable("Stopped")
        return await mutate(database, workspace, operation)
    monkeypatch.setattr(suppression, "mutate_suppression", closed)
    calls = []
    if scheduler == "publish":
        monkeypatch.setattr(connection, "_control_allowed", lambda ws: not ws.startswith("closed"))
        await mailbox_jobs.publish_due_jobs(db, lambda *args: calls.append(args))
        await mailbox_jobs.publish_due_jobs(db, lambda *args: calls.append(args))
        assert calls == [("good", "w")]
    else:
        assert (await mailbox_jobs.recover_due_jobs(db))["recovered"] == 0
        assert (await mailbox_jobs.recover_due_jobs(db))["recovered"] == 1
        assert rows[-1]["status"] == "queued"


@pytest.mark.asyncio
async def test_current_controls_and_code_deadline_change_on_client_entry_never_post(lifecycle, monkeypatch):
    http = AsyncMock()
    async def revoked():
        monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "false")
        return http
    http_context(monkeypatch, enter=revoked)
    assert (await connection.complete_connection_job(lifecycle, "w", "job"))["status"] == "review_required"
    http.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_stopped_job_api_returns_only_sanitized_review_reason(lifecycle):
    from outreach.api.mailboxes import get_mailbox_connection_job
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    row.update(status="review_required")
    result = await get_mailbox_connection_job("job", current_user={"default_workspace_id": "w"}, db=lifecycle)
    assert result["status"] == "review_required" and "operator review" in result["error"]
    assert "authorization_code_enc" not in str(result) and "code_verifier_enc" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [{'access_token': 5}, {'expires_in': 0}])
async def test_malformed_token_response_is_held_before_profile_http(lifecycle, monkeypatch, invalid):
    http = http_context(monkeypatch)
    http.post.return_value = httpx.Response(200, json={'access_token': 'access', 'refresh_token': 'refresh',
        'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly', **invalid})
    assert await connection.complete_connection_job(lifecycle, 'w', 'job') == {'status': 'review_required'}
    http.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_token_lifetime_is_not_extended_by_profile_or_key_work(lifecycle, monkeypatch):
    http = http_context(monkeypatch)
    before = datetime.now(timezone.utc)
    async def response(*args, **kwargs):
        class Later:
            @staticmethod
            def now(_): return datetime.now(timezone.utc) + timedelta(seconds=20)
        monkeypatch.setattr(connection, 'datetime', Later)
        return httpx.Response(200, json={'access_token': 'access', 'refresh_token': 'refresh', 'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly'})
    http.post.side_effect = response
    assert await connection.complete_connection_job(lifecycle, 'w', 'job') == {'status': 'connected'}
    assert lifecycle.outreach_mailboxes.docs[0]['token_expires_at'] < before + timedelta(seconds=3601)


@pytest.mark.asyncio
async def test_global_index_setup_secures_oauth_retention_before_other_builds(monkeypatch):
    from unittest.mock import MagicMock
    from db import indexes
    order = []
    async def retention(_): order.append('oauth_retention')
    async def other(*args, **kwargs): order.append('other_index')
    monkeypatch.setattr(indexes, 'ensure_mailbox_job_indexes', retention)
    monkeypatch.setattr(indexes, 'ensure_mailbox_sync_indexes', other)
    monkeypatch.setattr(indexes, 'ensure_voice_studio_indexes', other)
    monkeypatch.setattr(indexes, '_safe_create_index', other)
    monkeypatch.setenv('DB_NAME', 'local-index-fixture')
    await indexes.create_all_indexes(MagicMock())
    assert order[0] == 'oauth_retention' and order.count('oauth_retention') == 1
