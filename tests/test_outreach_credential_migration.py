"""Drained migration changes custody only, preserves generation and saved receipts."""
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest

from outreach.core.credential_migration import CredentialMigration
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.inbox_freshness import credential_generation
from outreach.core.sender_execution import SenderExecution
from outreach.core.session_custody import account_session
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped
from outreach.core.crypto import encrypt_secret


@pytest.fixture
def migration_db(scoped):
    return Database(outreach_accounts=[{"workspace_id": "w", "id": "a", "status": "paused",
        "session_cookie_enc": encrypt_secret("private-cookie"), "jsession_id": encrypt_secret("ajax:csrf"), "li_a_enc": "",
        "inbox_sync": {"status": "complete"}}],
        outreach_sender_execution=[{**SenderExecution.scope("w", "a"), "status": "idle",
            "permission": {"latched": True, "expires_at": datetime.now(timezone.utc)}}])


@pytest.mark.asyncio
async def test_exact_drained_migration_preserves_identity_and_does_not_resume(migration_db, monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    service = CredentialMigration(migration_db)
    original = migration_db.outreach_accounts.docs[0].copy()
    view = await service.inspect("w", "a")
    assert "private-cookie" not in str(view) and "gAAAAA" not in str(view)
    result = await service.migrate("w", "a", "operator", view["digest"], workers_drained=True)
    assert result["status"] == "completed"
    account = migration_db.outreach_accounts.docs[0]
    assert account["status"] == "paused" and account["inbox_sync"]["status"] == "required"
    assert credential_generation(account) == credential_generation(original)
    assert (await account_session(account))["li_at"] == "private-cookie"
    assert migration_db.outreach_sender_execution.docs[0]["permission"]["latched"]
    assert "private-cookie" not in str(migration_db.outreach_credential_migrations.docs)
    monkeypatch.setattr("outreach.core.session_custody.configured_custody", lambda: (_ for _ in ()).throw(AssertionError("No replay")))
    assert (await service.migrate("w", "a", "operator", view["digest"], workers_drained=True))["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["no_drain", "live", "permission", "owner", "unknown", "connection", "campaign", "stale", "plaintext"])
async def test_unsafe_or_stale_migration_denies_before_key_service(migration_db, monkeypatch, reason):
    service = CredentialMigration(migration_db)
    view = await service.inspect("w", "a")
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    if reason == "live": monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    if reason == "permission": migration_db.outreach_sender_execution.docs[0]["permission"]["latched"] = False
    if reason == "owner": migration_db.outreach_sender_execution.docs[0]["owner_token"] = "owner"
    if reason == "unknown": migration_db.outreach_physical_requests.docs.append({"workspace_id": "w", "sender_id": "a", "status": "unknown_outcome"})
    if reason == "connection": migration_db.outreach_connection_locks.docs.append({"workspace_id": "w", "_id": "a"})
    if reason == "campaign": migration_db.outreach_campaigns.docs.append({"workspace_id": "w", "sender_account_ids": ["a"], "status": "active"})
    if reason == "stale": migration_db.outreach_accounts.docs[0]["status"] = "disconnected"
    if reason == "plaintext": migration_db.outreach_accounts.docs[0]["session_cookie_enc"] = "plaintext"
    monkeypatch.setattr("outreach.core.session_custody.configured_custody", lambda: (_ for _ in ()).throw(AssertionError("Must deny before KMS")))
    with pytest.raises(CustodyUnavailable):
        await service.migrate("w", "a", "operator", view["digest"], workers_drained=reason != "no_drain")
    assert not migration_db.outreach_credential_migrations.docs


@pytest.mark.asyncio
async def test_context_changes_during_sealing_discard_replacement_without_write(migration_db, scoped, monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    service = CredentialMigration(migration_db)
    view = await service.inspect("w", "a")
    original = scoped.seal
    async def change(secret, context):
        migration_db.outreach_accounts.docs[0]["credential_generation"] = "replacement"
        return await original(secret, context)
    monkeypatch.setattr(scoped, "seal", change)
    with pytest.raises(CustodyUnavailable):
        await service.migrate("w", "a", "operator", view["digest"], workers_drained=True)
    assert migration_db.outreach_accounts.docs[0]["session_cookie_enc"].startswith("gAAAAA")
    assert not migration_db.outreach_credential_migrations.docs


@pytest.mark.asyncio
async def test_private_cli_migration_prints_only_sanitized_receipt(migration_db, monkeypatch, capsys):
    import json
    from argparse import Namespace
    from outreach.ops.pilot import _run_db
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    await _run_db(Namespace(command='inspect-credential-custody', workspace='w', sender='a'), migration_db)
    view = json.loads(capsys.readouterr().out)
    args = Namespace(command='migrate-credential-custody', workspace='w', sender='a', operator='local-reviewer',
        review_digest=view['digest'], workers_drained='I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS')
    await _run_db(args, migration_db)
    output = capsys.readouterr().out
    assert json.loads(output)['current_matches']
    assert 'private-cookie' not in output and 'uc1:' not in output and 'gAAAAA' not in output
    args.workers_drained = 'incorrect'
    with pytest.raises(CustodyUnavailable): await _run_db(args, migration_db)


@pytest.mark.asyncio
async def test_saved_receipt_reports_current_replacement_without_rewrapping(migration_db, monkeypatch):
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    service = CredentialMigration(migration_db)
    view = await service.inspect('w', 'a')
    await service.migrate('w', 'a', 'operator', view['digest'], workers_drained=True)
    migration_db.outreach_accounts.docs[0]['credential_generation'] = 'replaced'
    monkeypatch.setattr('outreach.core.credential_migration.seal_installed', AsyncMock(side_effect=AssertionError('No replay')))
    assert not (await service.migrate('w', 'a', 'operator', view['digest'], workers_drained=True))['current_matches']
