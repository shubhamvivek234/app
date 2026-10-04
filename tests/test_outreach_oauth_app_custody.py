"""Application OAuth secrets stay scoped, worker-only and rotation fenced."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from outreach.core import mailbox_connection as connection
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_mailbox_job_lifecycle import lifecycle, http_context

ORIGINAL_PROVIDER_CONFIG = connection._provider_config


@pytest.fixture
def app_env(monkeypatch):
    monkeypatch.setattr(connection, "_provider_config", ORIGINAL_PROVIDER_CONFIG)
    for provider in ("GMAIL", "MICROSOFT"):
        prefix = f"OUTREACH_{provider}"
        monkeypatch.setenv(f"{prefix}_CLIENT_ID", f"{provider.lower()}-app")
        monkeypatch.setenv(f"{prefix}_REDIRECT_URI", f"https://api.example.test/outreach/mailboxes/{provider.lower()}/callback")
        for suffix in ("CLIENT_SECRET", "CLIENT_SECRET_ENC", "CLIENT_SECRET_GENERATION"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.setenv("OUTREACH_MICROSOFT_TENANT", "common")


async def install_app(monkeypatch, provider="gmail"):
    from outreach.core.oauth_app_custody import seal_app_secret
    envelope = await seal_app_secret("private-app-secret", provider, f"{provider}-app", "rotation-1")
    prefix = f"OUTREACH_{provider.upper()}"
    monkeypatch.setenv(f"{prefix}_CLIENT_SECRET_ENC", envelope)
    monkeypatch.setenv(f"{prefix}_CLIENT_SECRET_GENERATION", "rotation-1")
    return connection._provider_config(provider)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gmail", "microsoft"])
async def test_scoped_app_secret_roundtrip_and_private_configuration(scoped, app_env, monkeypatch, provider):
    from outreach.core.oauth_app_custody import prepare_app_secret
    config = await install_app(monkeypatch, provider)
    before = len(scoped.provider.calls)
    assert connection._provider_config(provider) == config
    assert len(scoped.provider.calls) == before  # configuration inspection never unwraps
    prepared = await prepare_app_secret(config)
    assert prepared.value == "private-app-secret" and prepared.matches()
    assert "private-app-secret" not in repr(prepared) + repr(config)
    assert scoped.provider.calls[-1][1]["purpose"] == "oauth_app_secret"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["provider", "client_id", "app_generation", "environment"])
async def test_cross_application_scope_denies_without_fallback(scoped, app_env, monkeypatch, field):
    from outreach.core.oauth_app_custody import prepare_app_secret
    config = await install_app(monkeypatch)
    if field == "environment":
        monkeypatch.setenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", "other-environment")
    else:
        config = replace(config, **{field: "microsoft" if field == "provider" else "other"})
    with pytest.raises(CustodyUnavailable):
        await prepare_app_secret(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["plaintext", "both", "missing_generation", "legacy_downgrade", "oversize"])
async def test_configuration_rejects_ambiguous_or_unscoped_storage(scoped, app_env, monkeypatch, case):
    await install_app(monkeypatch)
    if case in {"plaintext", "both"}:
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET", "plain-secret")
    if case == "plaintext":
        monkeypatch.delenv("OUTREACH_GMAIL_CLIENT_SECRET_ENC")
    if case == "missing_generation":
        monkeypatch.delenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION")
    if case == "legacy_downgrade":
        monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    if case == "oversize":
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_ENC", "uc1:" + "x" * 60001)
    with pytest.raises(connection.MailboxUnavailable):
        connection._provider_config("gmail")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["generation", "cipher", "client", "redirect", "tenant", "key", "role", "mode", "environment", "value"])
async def test_prepared_secret_rechecks_full_config_and_policy(scoped, app_env, monkeypatch, change):
    from outreach.core.oauth_app_custody import prepare_app_secret
    config = await install_app(monkeypatch, "microsoft")
    prepared = await prepare_app_secret(config)
    names = {"generation": "OUTREACH_MICROSOFT_CLIENT_SECRET_GENERATION", "cipher": "OUTREACH_MICROSOFT_CLIENT_SECRET_ENC",
             "client": "OUTREACH_MICROSOFT_CLIENT_ID", "redirect": "OUTREACH_MICROSOFT_REDIRECT_URI",
             "tenant": "OUTREACH_MICROSOFT_TENANT", "key": "OUTREACH_KMS_KEY_ARN", "role": "OUTREACH_KMS_ROLE_ID",
             "mode": "OUTREACH_CREDENTIAL_CUSTODY_MODE", "environment": "OUTREACH_CUSTODY_ENVIRONMENT_ID"}
    if change == "value":
        object.__setattr__(prepared, "value", "replacement")
    else:
        monkeypatch.setenv(names[change], "organizations" if change == "tenant" else "replacement")
    assert not prepared.matches()


@pytest.mark.asyncio
async def test_app_rotation_during_key_open_is_denied(scoped, app_env, monkeypatch):
    from outreach.core.oauth_app_custody import prepare_app_secret
    config = await install_app(monkeypatch)
    opening = scoped.open
    async def rotated(*args):
        value = await opening(*args)
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "rotation-2")
        return value
    monkeypatch.setattr(scoped, "open", rotated)
    with pytest.raises(CustodyUnavailable):
        await prepare_app_secret(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["open", "seal"])
async def test_key_errors_are_sanitized_and_sealing_policy_cannot_change(scoped, app_env, monkeypatch, operation):
    from outreach.core.oauth_app_custody import prepare_app_secret, seal_app_secret
    config = await install_app(monkeypatch)
    if operation == "open":
        monkeypatch.setattr(scoped.provider, "unwrap", AsyncMock(side_effect=RuntimeError("private-key-error")))
        with pytest.raises(CustodyUnavailable) as error: await prepare_app_secret(config)
        assert "private-key-error" not in str(error.value)
    else:
        sealing = scoped.seal
        async def changed(*args):
            result = await sealing(*args)
            monkeypatch.setenv("OUTREACH_KMS_KEY_ARN", "replacement")
            return result
        monkeypatch.setattr(scoped, "seal", changed)
        with pytest.raises(CustodyUnavailable): await seal_app_secret("secret", "gmail", "gmail-app", "generation")


@pytest.mark.parametrize("provider,client", [("unknown", "app"), ("gmail", ""), ("gmail", " leading"), ("gmail", "x" * 1025), ("gmail", "bad\nvalue")])
def test_app_context_requires_bounded_application_identity(scoped, provider, client):
    from outreach.core.oauth_app_custody import app_context
    with pytest.raises(CustodyUnavailable): app_context(provider, client, "generation")


@pytest.mark.asyncio
async def test_private_sealing_requires_opt_in_mode(app_env, monkeypatch):
    from outreach.core.oauth_app_custody import seal_app_secret
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    with pytest.raises(CustodyUnavailable): await seal_app_secret("secret", "gmail", "app", "generation")


@pytest.mark.asyncio
async def test_legacy_default_is_plain_and_never_calls_key_service(app_env, monkeypatch):
    from outreach.core import session_custody
    from outreach.core.oauth_app_custody import prepare_app_secret
    monkeypatch.delenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", raising=False)
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET", "legacy-secret")
    monkeypatch.setattr(session_custody, "configured_custody", lambda: (_ for _ in ()).throw(AssertionError("No AWS")))
    prepared = await prepare_app_secret(connection._provider_config("gmail"))
    assert prepared.value == "legacy-secret" and prepared.matches()


@pytest.mark.asyncio
async def test_new_authorization_pins_config_and_never_opens_app_secret(lifecycle, app_env, monkeypatch):
    from outreach.core.oauth_app_custody import app_configuration_digest
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    monkeypatch.setenv("OUTREACH_MAILBOX_CONNECTION_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "gmail-app")
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET", "legacy-secret")
    monkeypatch.setenv("OUTREACH_GMAIL_REDIRECT_URI", "https://api.example.test/outreach/mailboxes/gmail/callback")
    monkeypatch.setattr(connection, "_paid_sender", AsyncMock(return_value=True))
    monkeypatch.setattr(connection, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    lifecycle.outreach_mailbox_connection_jobs.docs.clear()
    result = await connection.start_mailbox_connection(lifecycle, "w", "user", "a", "gmail")
    job = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    assert job["app_config_digest"] == app_configuration_digest(connection._provider_config("gmail"))
    assert "legacy-secret" not in str(job) + str(result)


@pytest.mark.asyncio
async def test_kms_authorization_opens_only_pending_pkce_at_start_and_app_secret_in_worker(lifecycle, scoped, app_env, monkeypatch):
    from outreach.core.oauth_app_custody import app_identity_digest
    from urllib.parse import parse_qs, urlparse
    config = await install_app(monkeypatch)
    lifecycle.outreach_mailbox_connection_jobs.docs.clear()
    before = len(scoped.provider.calls)
    result = await connection.start_mailbox_connection(lifecycle, "w", "user", "a", "gmail")
    assert [ctx["purpose"] for _, ctx in scoped.provider.calls[before:]] == ["oauth_pkce"]
    monkeypatch.setattr(connection, "enqueue_connection_job", lambda *_: None)
    state = parse_qs(urlparse(result["authorization_url"]).query)["state"][0]
    await connection.consume_oauth_callback(lifecycle, "gmail", state, "private-code",
        browser_binding_nonce=result["browser_binding_nonce"])
    http = http_context(monkeypatch)
    assert await connection.complete_connection_job(lifecycle, "w", result["connection_job_id"]) == {"status": "connected"}
    assert http.post.await_args.kwargs["data"]["client_secret"] == "private-app-secret"
    assert lifecycle.outreach_mailboxes.docs[0]["oauth_app_identity_digest"] == app_identity_digest(config)
    assert "private-app-secret" not in str(lifecycle.outreach_mailbox_connection_jobs.docs)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["app_open", "code_open", "pkce_storage"])
async def test_config_rotation_during_key_work_never_submits(lifecycle, scoped, app_env, monkeypatch, phase):
    from outreach.core.provider_custody import seal_oauth_secret
    from outreach.core.oauth_app_custody import app_configuration_digest
    config = await install_app(monkeypatch)
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    row["app_config_digest"] = app_configuration_digest(config)
    row["authorization_code_enc"] = await seal_oauth_secret("private-code", row, "w", "a", "oauth_code")
    row["code_verifier_enc"] = await seal_oauth_secret("private-pkce", row, "w", "a", "oauth_pkce")
    http = http_context(monkeypatch)
    if phase == "pkce_storage":
        lifecycle.outreach_mailbox_connection_jobs.docs.clear()
        sealing = scoped.seal
        async def changed(*args):
            result = await sealing(*args)
            monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
            return result
        monkeypatch.setattr(scoped, "seal", changed)
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await connection.start_mailbox_connection(lifecycle, "w", "user", "a", "gmail")
        assert not lifecycle.outreach_mailbox_connection_jobs.docs
    else:
        opening = scoped.open
        async def changed(envelope, context):
            value = await opening(envelope, context)
            if context.purpose == ("oauth_app_secret" if phase == "app_open" else "oauth_code"):
                monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
            return value
        monkeypatch.setattr(scoped, "open", changed)
        assert await connection.complete_connection_job(lifecycle, "w", "job") == {"status": "failed"}
        assert row["exchange_state"] == "not_submitted"
    http.post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["same_app_rotation", "different_app", "different_tenant", "unproven"])
async def test_mailbox_refresh_requires_stable_app_identity(scoped, app_env, monkeypatch, case):
    from outreach.core.oauth_app_custody import app_identity_digest, seal_app_secret
    from tests.test_outreach_mailbox_custody_integration import mailbox_db
    from copy import deepcopy
    provider = "microsoft" if case == "different_tenant" else "gmail"
    config = await install_app(monkeypatch, provider)
    db = await mailbox_db(monkeypatch, provider=provider, expired=True)
    row = db.outreach_mailboxes.docs[0]
    row["oauth_app_identity_digest"] = app_identity_digest(config)
    if case == "same_app_rotation":
        envelope = await seal_app_secret("rotated-app-secret", provider, config.client_id, "rotation-2")
        monkeypatch.setenv(f"OUTREACH_{provider.upper()}_CLIENT_SECRET_ENC", envelope)
        monkeypatch.setenv(f"OUTREACH_{provider.upper()}_CLIENT_SECRET_GENERATION", "rotation-2")
    elif case == "different_app":
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "replacement-app")
    elif case == "different_tenant":
        monkeypatch.setenv("OUTREACH_MICROSOFT_TENANT", "organizations")
    else:
        row.pop("oauth_app_identity_digest")
    http = http_context(monkeypatch)
    if case == "same_app_rotation":
        token = await connection.get_mailbox_access_token(db, deepcopy(row))
        assert token.secret.value == "private-access"
        assert http.post.await_args.kwargs["data"]["client_secret"] == "rotated-app-secret"
        assert row["oauth_app_identity_digest"] == app_identity_digest(config)
    else:
        with pytest.raises(connection.MailboxUnavailable):
            await connection.get_mailbox_access_token(db, deepcopy(row))
        http.post.assert_not_awaited()
        assert not row.get("refresh_state") and not row.get("refresh_lease_nonce")


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["during_open", "after_permit", "after_response"])
async def test_refresh_rotation_preserves_original_unknown_hold(scoped, app_env, monkeypatch, phase):
    from outreach.core.oauth_app_custody import app_identity_digest
    from tests.test_outreach_mailbox_custody_integration import mailbox_db
    from copy import deepcopy
    config = await install_app(monkeypatch)
    db = await mailbox_db(monkeypatch, expired=True)
    row = db.outreach_mailboxes.docs[0]
    row["oauth_app_identity_digest"] = app_identity_digest(config)
    old = row["access_token_enc"]
    http = http_context(monkeypatch)
    def rotate():
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_SECRET_GENERATION", "replacement")
    if phase == "during_open":
        opening = scoped.open
        async def changed(envelope, context):
            result = await opening(envelope, context)
            if context.purpose == "oauth_app_secret": rotate()
            return result
        monkeypatch.setattr(scoped, "open", changed)
    elif phase == "after_permit":
        async def enter():
            rotate()
            return http
        http_context(monkeypatch, enter=enter)
    else:
        async def response(*args, **kwargs):
            rotate()
            return httpx.Response(200, json={"access_token": "replacement-access", "expires_in": 3600})
        http.post.side_effect = response
    with pytest.raises(connection.MailboxUnavailable):
        await connection.get_mailbox_access_token(db, deepcopy(row))
    assert row["access_token_enc"] == old
    if phase == "during_open":
        assert not row.get("refresh_state")
    else:
        assert row["refresh_state"] == "unknown"
        with pytest.raises(connection.MailboxUnavailable):
            await connection.get_mailbox_access_token(db, deepcopy(row))
    if phase == "after_response": http.post.assert_awaited_once()
    else: http.post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", ["same_app", "other_app", "missing"])
async def test_reconnect_without_new_refresh_cannot_relabel_old_app_token(lifecycle, scoped, app_env, monkeypatch, proof):
    from copy import deepcopy
    from outreach.core.oauth_app_custody import app_configuration_digest, app_identity_digest
    from outreach.core.provider_custody import seal_oauth_secret, open_mailbox_refresh
    from tests.test_outreach_mailbox_custody_integration import mailbox_db
    config = await install_app(monkeypatch)
    old_db = await mailbox_db(monkeypatch)
    old = old_db.outreach_mailboxes.docs[0]
    old["history_id"] = "cursor"
    if proof != "missing":
        old["oauth_app_identity_digest"] = app_identity_digest(config) if proof == "same_app" else "other-app"
    lifecycle.outreach_mailboxes.docs.append(old)
    before = deepcopy(old)
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    row["app_config_digest"] = app_configuration_digest(config)
    row["authorization_code_enc"] = await seal_oauth_secret("code", row, "w", "a", "oauth_code")
    row["code_verifier_enc"] = await seal_oauth_secret("pkce", row, "w", "a", "oauth_pkce")
    http = http_context(monkeypatch)
    http.post.return_value = httpx.Response(200, json={"access_token": "new-access",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"})
    monkeypatch.setattr(connection, "_mailbox_identity", AsyncMock(return_value={"provider_user_id": "u",
        "email": "sender@example.com", "history_id": "cursor"}))
    result = await connection.complete_connection_job(lifecycle, "w", "job")
    if proof == "same_app":
        assert result == {"status": "connected"}
        assert await open_mailbox_refresh(lifecycle.outreach_mailboxes.docs[0], "w", "a") == "private-refresh"
    else:
        assert result == {"status": "review_required"}
        assert lifecycle.outreach_mailboxes.docs[0] == before
        await connection.complete_connection_job(lifecycle, "w", "job")
    http.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_unproven_kms_job_denies_before_app_key_open(scoped, app_env, monkeypatch):
    from outreach.core.oauth_app_custody import prepare_app_secret
    config = await install_app(monkeypatch)
    count = len(scoped.provider.calls)
    with pytest.raises(CustodyUnavailable):
        await prepare_app_secret(config, job={"provider": "gmail"})
    assert len(scoped.provider.calls) == count


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["before_exchange", "after_permit", "after_response"])
async def test_oauth_rotation_denies_or_holds_without_replay(lifecycle, monkeypatch, stage):
    from outreach.core.oauth_app_custody import app_configuration_digest
    from types import SimpleNamespace
    config = connection._provider_config("gmail")
    lifecycle.outreach_mailbox_connection_jobs.docs[0]["app_config_digest"] = app_configuration_digest(config)
    def rotate():
        monkeypatch.setattr(connection, "_provider_config", lambda _: SimpleNamespace(**{**vars(config), "client_secret": "replacement"}))
    http = http_context(monkeypatch)
    if stage == "before_exchange":
        rotate()
    elif stage == "after_permit":
        async def enter():
            rotate()
            return http
        http_context(monkeypatch, enter=enter)
    else:
        async def response(*args, **kwargs):
            rotate()
            return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh",
                "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"})
        http.post.side_effect = response
    result = await connection.complete_connection_job(lifecycle, "w", "job")
    assert result["status"] == ("failed" if stage == "before_exchange" else "review_required")
    assert not lifecycle.outreach_mailboxes.docs
    if stage != "after_response":
        http.post.assert_not_awaited()
    else:
        http.post.assert_awaited_once()
    await connection.complete_connection_job(lifecycle, "w", "job")
    if stage == "after_response":
        http.post.assert_awaited_once()
