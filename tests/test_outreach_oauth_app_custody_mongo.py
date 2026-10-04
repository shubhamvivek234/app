"""Actual transactions with scoped app secrets and configuration/identity races."""
from datetime import datetime, timedelta, timezone
import os
from unittest.mock import AsyncMock
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import pytest_asyncio

from outreach.core import mailbox_connection as connection, suppression
from outreach.core.oauth_app_custody import app_configuration_digest, app_identity_digest
from outreach.core.provider_custody import seal_oauth_secret
from tests.test_outreach_mailbox_job_lifecycle import lifecycle, http_context
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_oauth_app_custody import app_env, install_app

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable replica set is opt-in")]


@pytest_asyncio.fixture
async def apps_mongo(lifecycle, scoped, app_env, monkeypatch):
    config = await install_app(monkeypatch)
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    row["app_config_digest"] = app_configuration_digest(config)
    row["authorization_code_enc"] = await seal_oauth_secret("code", row, "w", "a", "oauth_code")
    row["code_verifier_enc"] = await seal_oauth_secret("pkce", row, "w", "a", "oauth_pkce")
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27028", tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client["test_unravler_oauth_app_" + uuid.uuid4().hex]
    await db.outreach_mailbox_connection_jobs.insert_one(row)
    try:
        yield db, config
    finally:
        await client.drop_database(db.name)
        client.close()


async def test_scoped_app_install_and_lost_ack_receipt_never_reopens_or_replays(apps_mongo, scoped, monkeypatch):
    db, config = apps_mongo
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def lost(*args):
        result = await mutate(*args)
        if args[-1].__name__ == "install": raise TimeoutError("lost local acknowledgement")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", lost)
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "connected"}
    mailbox = await db.outreach_mailboxes.find_one({"workspace_id": "w"})
    assert mailbox["oauth_app_identity_digest"] == app_identity_digest(config)
    assert http.post.await_args.kwargs["data"]["client_secret"] == "private-app-secret"
    monkeypatch.setattr(scoped, "open", AsyncMock(side_effect=AssertionError("No receipt replay")))
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "already_claimed"}
    http.post.assert_awaited_once()


@pytest.mark.parametrize("change", ["job_proof", "config_before_permit", "config_after_permit", "config_at_install"])
async def test_transaction_boundaries_preserve_noncall_or_unknown_evidence(apps_mongo, monkeypatch, change):
    db, config = apps_mongo
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def raced(*args):
        callback = args[-1]
        row = await db.outreach_mailbox_connection_jobs.find_one({"workspace_id": "w"})
        if callback.__name__ == "check" and row["exchange_state"] == "preparing":
            if change == "job_proof":
                await db.outreach_mailbox_connection_jobs.update_one({"workspace_id": "w"}, {"$set": {"app_config_digest": "replacement"}})
            if change == "config_before_permit":
                monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
        if callback.__name__ == "install" and change == "config_at_install":
            monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
        result = await mutate(*args)
        if callback.__name__ == "check" and row["exchange_state"] == "preparing" and change == "config_after_permit":
            monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", raced)
    expected = "failed" if change in {"job_proof", "config_before_permit"} else "review_required"
    assert await connection.complete_connection_job(db, "w", "job") == {"status": expected}
    assert not await db.outreach_mailboxes.find_one({"workspace_id": "w"})
    row = await db.outreach_mailbox_connection_jobs.find_one({"workspace_id": "w"})
    assert row["exchange_state"] == ("not_submitted" if expected == "failed" else "unknown")
    budget = await db.outreach_mailbox_exchange_budgets.find_one({"workspace_id": "w"})
    assert (budget or {}).get("used", 0) == (0 if expected == "failed" else 1)
    if change == "config_at_install": http.post.assert_awaited_once()
    else: http.post.assert_not_awaited()


@pytest.mark.parametrize("phase", ["before_permit", "after_permit", "install"])
async def test_refresh_app_identity_or_config_race_never_overwrites(apps_mongo, monkeypatch, phase):
    from outreach.core.provider_custody import seal_mailbox_tokens
    db, config = apps_mongo
    mailbox = {"workspace_id": "w", "sender_account_id": "a", "provider": "gmail", "provider_user_id": "u",
        "email": "sender@example.test", "connection_job_id": "connected", "status": "active",
        "token_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        "oauth_app_identity_digest": app_identity_digest(config)}
    mailbox.update(await seal_mailbox_tokens({"access_token": "old-access", "refresh_token": "refresh"}, mailbox, "w", "a"))
    await db.outreach_mailboxes.insert_one(mailbox)
    http = http_context(monkeypatch)
    mutate = suppression.mutate_suppression
    async def raced(*args):
        callback = args[-1]
        if callback.__name__ == "authorize" and phase == "before_permit":
            await db.outreach_mailboxes.update_one({"workspace_id": "w"}, {"$set": {"oauth_app_identity_digest": "replacement"}})
        if callback.__name__ == "install" and phase == "install":
            monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
        result = await mutate(*args)
        if callback.__name__ == "authorize" and phase == "after_permit":
            monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
        return result
    monkeypatch.setattr(suppression, "mutate_suppression", raced)
    with pytest.raises(connection.MailboxUnavailable): await connection.get_mailbox_access_token(db, mailbox)
    current = await db.outreach_mailboxes.find_one({"workspace_id": "w"})
    assert current["access_token_enc"] == mailbox["access_token_enc"]
    if phase == "before_permit":
        # This competing row is not ours to clear or mark unknown.
        assert current["oauth_app_identity_digest"] == "replacement"
    else:
        assert current["refresh_state"] == "unknown"
        with pytest.raises(connection.MailboxUnavailable): await connection.get_mailbox_access_token(db, current)
    if phase == "install": http.post.assert_awaited_once()
    else: http.post.assert_not_awaited()


async def test_app_key_operations_never_enter_transaction_callbacks(apps_mongo, scoped, monkeypatch):
    db, _ = apps_mongo
    inside = False
    mutate = suppression.mutate_suppression
    async def watched(database, workspace, callback):
        async def wrapped(current):
            nonlocal inside
            inside = True
            try: return await callback(current)
            finally: inside = False
        return await mutate(database, workspace, wrapped)
    opening, sealing = scoped.open, scoped.seal
    async def checked_open(*args):
        assert not inside
        return await opening(*args)
    async def checked_seal(*args):
        assert not inside
        return await sealing(*args)
    monkeypatch.setattr(suppression, "mutate_suppression", watched)
    monkeypatch.setattr(scoped, "open", checked_open)
    monkeypatch.setattr(scoped, "seal", checked_seal)
    http_context(monkeypatch)
    assert await connection.complete_connection_job(db, "w", "job") == {"status": "connected"}
