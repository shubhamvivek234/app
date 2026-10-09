"""Fake physical providers with real approval/permission and receipt controls."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from outreach.core.provider_boundary import ProviderEnvelope, provider_generation
from outreach.core.request_guard import RequestDenied, request_parent
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.mailbox_delivery import _mime_message
from outreach.core.sender_execution import SenderExecution
from tests.test_outreach_execution_outbox import execution_db


async def ready(monkeypatch, provider="gmail", source="email_send"):
    from outreach.core import provider_boundary as module
    from cryptography.fernet import Fernet
    from utils import encryption
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    db = execution_db()
    account = db.outreach_accounts.docs[0]
    from utils.encryption import encrypt
    encrypted_key = encrypt("fake-hunter-key")
    resource = {"workspace_id": "w", "sender_account_id": "a", "provider": provider, "provider_user_id": "u",
                "email": "sender@example.com", "connection_job_id": "mailbox-generation", "status": "active", "api_key_enc": encrypted_key}
    await db.outreach_mailboxes.insert_one(resource)
    await db.outreach_hunter_credentials.insert_one({"workspace_id": "w", "api_key_enc": encrypted_key})
    db.outreach_leads.docs[0]["email"] = "lead@example.com"
    if source == "email_send":
        db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"].update(type="send_email", config={"subject": "Hello", "body": "Reviewed body"})
        binding = await sequence_binding(db, "w", "l")
        record = await ContentApproval(db).ensure(binding)
        await ContentApproval(db).decide("w", record["_id"], "human", "approve", revision=1)
    else:
        db.outreach_leads.docs[0].pop("email", None)
        db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["type"] = "find_email"
        binding = None
    monkeypatch.setattr(module, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(module, "is_shutting_down", lambda: False)
    monkeypatch.setattr(module, "get_active_entitlement", AsyncMock(return_value={"status": "active"}))
    monkeypatch.setattr(module, "get_ready_mailbox", AsyncMock(side_effect=lambda *args: db.outreach_mailboxes.docs[0]))
    monkeypatch.setattr(module, "is_email_send_pilot_allowed", lambda ws: True)
    monkeypatch.setenv("OUTREACH_HUNTER_ENABLED", "true")
    envelope = ProviderEnvelope(db, "w", "a", account, source, resource, operation_id="l:n", lead_id="l")
    if source == "email_find":
        from outreach.core.email_finder import _linkedin_handle
        envelope.finder_handle = _linkedin_handle(db.outreach_leads.docs[0]["linkedin_url"])
    # This helper constructs an in-memory fixture. Real callers re-grant on the
    # replica set; fake data uses only the callback, with no transaction fallback.
    await ExecutionPermission(db)._grant("w", "a", provider_generation(account, resource, source), [source], "operator")
    guard = SenderExecution(db)
    await guard.acquire("w", "a", "owner")
    await guard.begin("w", "a", "owner")
    return db, envelope, binding


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,response", [("gmail", httpx.Response(200, json={"id": "message"})), ("microsoft", httpx.Response(202))])
async def test_provider_specific_acceptance_records_receipt_without_delivery_claim(monkeypatch, provider, response):
    db, envelope, binding = await ready(monkeypatch, provider)
    factory = AsyncMock(return_value=response)
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        envelope.assert_email(_mime_message("sender@example.com", "lead@example.com", "Hello", "Reviewed body", "m"))
        await envelope.call("POST", envelope.endpoint, factory, action="email")
    factory.assert_awaited_once()
    receipt = db.outreach_physical_requests.docs[0]
    assert receipt["status"] == "response_received"
    assert receipt["provider_outcome"]["status"] == "accepted"
    assert "access-token" not in str(receipt) and "encrypted-key" not in str(receipt)


@pytest.mark.asyncio
async def test_actual_mime_content_must_match_approval_before_provider_call(monkeypatch):
    db, envelope, binding = await ready(monkeypatch)
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        with pytest.raises(RequestDenied):
            envelope.assert_email(_mime_message("sender@example.com", "other@example.com", "Hello", "Unreviewed", "m"))


@pytest.mark.asyncio
async def test_mailbox_reconnect_after_token_capture_blocks_old_token(monkeypatch):
    db, envelope, binding = await ready(monkeypatch)
    db.outreach_mailboxes.docs[0]["connection_job_id"] = "new-generation"
    factory = AsyncMock()
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        with pytest.raises(RequestDenied):
            await envelope.call("POST", envelope.endpoint, factory, action="email")
    factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_content_revocation_after_sender_cas_blocks_email(monkeypatch):
    db, envelope, binding = await ready(monkeypatch)
    write = db.outreach_sender_execution.find_one_and_update
    record = db.outreach_content_approvals.docs[0]
    async def revoke_after_permission(query, update, **kwargs):
        result = await write(query, update, **kwargs)
        if update.get("$set", {}).get("physical_request_token"):
            await ContentApproval(db).decide("w", record["_id"], "human", "revoke", revision=2)
        return result
    monkeypatch.setattr(db.outreach_sender_execution, "find_one_and_update", revoke_after_permission)
    factory = AsyncMock()
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        with pytest.raises(RequestDenied):
            await envelope.call("POST", envelope.endpoint, factory, action="email")
    factory.assert_not_awaited()
    assert db.outreach_physical_requests.docs[0]["status"] == "not_submitted"


@pytest.mark.asyncio
async def test_billable_finder_timeout_latches_and_cannot_repeat(monkeypatch):
    db, envelope, binding = await ready(monkeypatch, source="email_find")
    factory = AsyncMock(side_effect=httpx.ReadTimeout("fake timeout"))
    with request_parent("owner", AsyncMock(return_value=None)):
        with pytest.raises(httpx.ReadTimeout):
            await envelope.call("GET", envelope.endpoint, factory, action="finder", side_effect=True)
        with pytest.raises(RequestDenied):
            await envelope.call("GET", envelope.endpoint, factory, action="finder", side_effect=True)
    factory.assert_awaited_once()
    assert db.outreach_physical_requests.docs[0]["mutation"] is True
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"


@pytest.mark.asyncio
async def test_provider_budget_respects_tighter_campaign_limit(monkeypatch):
    db, envelope, binding = await ready(monkeypatch)
    db.outreach_accounts.docs[0]["limits"] = {"email_sends": 100}
    db.outreach_campaigns.docs[0]["limits"] = {"email_sends": 1}
    factory = AsyncMock(return_value=httpx.Response(200, json={"id": "m"}))
    with request_parent("owner", AsyncMock(return_value=None), approval_binding=binding):
        await envelope.call("POST", envelope.endpoint, factory, action="email")
        envelope.operation_id = "second-logical-action"
        with pytest.raises(RequestDenied, match="physical_action_cap"):
            await envelope.call("POST", envelope.endpoint, factory, action="email")
    factory.assert_awaited_once()
    assert db.outreach_provider_budgets.docs[0]["count"] == 1
