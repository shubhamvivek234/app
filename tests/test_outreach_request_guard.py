"""Shared physical request controls, with fake transport and isolated authority."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from tests.outreach_memory import Database
from outreach.core.request_guard import PhysicalBudget, RequestDenied, RequestEnvelope
from outreach.core.execution_permission import ExecutionPermission

NOW = datetime(2026, 10, 2, 10, tzinfo=timezone.utc)


def database():
    return Database(outreach_accounts=[{"id": "a", "workspace_id": "w", "status": "active", "credential_generation": "g"}])


async def grant(db, sources=("sequence", "sync", "search", "inbox_reply", "engage"), **kw):
    return await ExecutionPermission(db).grant("w", "a", "g", list(sources), "operator", now=NOW, **kw)


@pytest.mark.asyncio
async def test_budget_concurrent_reservations_do_not_exceed_sender_cap():
    db = database()
    budget = PhysicalBudget(db)
    config = {"request_budget": {"hourly_cap": 4, "daily_cap": 8, "reserved_hourly": 1, "reserved_daily": 1}}
    results = await asyncio.gather(*(budget.reserve("w", "a", "sequence", "read", config, now=NOW) for _ in range(15)))
    assert sum(result[0] for result in results) == 3
    assert (await budget.reserve("w", "a", "sync", "read", config, now=NOW))[0]
    assert not (await budget.reserve("w", "a", "sync", "read", config, now=NOW))[0]
    assert (await budget.reserve("another-workspace", "a", "sequence", "read", config, now=NOW))[0]


@pytest.mark.asyncio
async def test_budget_hour_rollover_preserves_daily_and_action_caps():
    db = database()
    config = {"request_budget": {"hourly_cap": 20, "daily_cap": 20, "action_caps": {"message": 1}}}
    budget = PhysicalBudget(db)
    assert (await budget.reserve("w", "a", "sequence", "message", config, now=NOW))[0]
    assert not (await budget.reserve("w", "a", "inbox_reply", "message", config, now=NOW + timedelta(hours=1)))[0]
    assert (await budget.reserve("w", "a", "sequence", "message", config, now=NOW + timedelta(days=1)))[0]


@pytest.mark.asyncio
async def test_budget_database_error_denies_without_memory_fallback(monkeypatch):
    db = database()
    monkeypatch.setattr(db.outreach_request_budgets, "insert_one", AsyncMock(side_effect=RuntimeError("offline")))
    assert await PhysicalBudget(db).reserve("w", "a", "search", "read", {}, now=NOW) == (False, 30, "budget_authority_unavailable")


@pytest.mark.asyncio
async def test_permission_expiry_scope_generation_and_latch():
    db = database()
    permission = ExecutionPermission(db)
    await grant(db, sources=("sync",))
    assert await permission.allowed("w", "a", "g", "sync", now=NOW)
    assert not await permission.allowed("w", "a", "g", "sequence", now=NOW)
    assert not await permission.allowed("other", "a", "g", "sync", now=NOW)
    assert not await permission.allowed("w", "a", "new-generation", "sync", now=NOW)
    assert not await permission.allowed("w", "a", "g", "sync", now=NOW + timedelta(seconds=60))
    await permission.revoke("w", "a", "operator", "manual_stop", now=NOW)
    with pytest.raises(ValueError, match="latched"):
        await grant(db)
    await grant(db, clear_latch=True)
    assert await permission.allowed("w", "a", "g", "sync", now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, 61, -1])
async def test_permission_cannot_issue_invalid_duration(ttl):
    with pytest.raises(ValueError):
        await grant(database(), ttl_seconds=ttl)


@pytest.mark.asyncio
async def test_missing_permission_never_invokes_transport(monkeypatch):
    db = database()
    envelope = RequestEnvelope(db, "w", "a", "g", "search", "http://proxy:8000")
    transport = AsyncMock()
    with pytest.raises(RequestDenied):
        await envelope.call("GET", "/search/blended", transport, now=NOW)
    transport.assert_not_awaited()


async def ready_envelope(monkeypatch, source="sequence"):
    from outreach.core import request_guard
    db = database()
    await grant(db)
    monkeypatch.setattr(request_guard, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(request_guard, "is_shutting_down", lambda: False)
    monkeypatch.setattr(RequestEnvelope, "_proxy_matches", lambda self, account: True)
    # These existing tests isolate physical permission/budget behavior; exact
    # approval and payload matching have separate non-stubbed integration tests.
    monkeypatch.setattr(RequestEnvelope, "_validate_content", AsyncMock(return_value=None))
    monkeypatch.setattr(RequestEnvelope, "_authorize_content", AsyncMock(return_value=None))
    return db, RequestEnvelope(db, "w", "a", "g", source, "http://proxy:8000")


@pytest.mark.asyncio
async def test_every_physical_subrequest_consumes_budget(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    transport = AsyncMock(return_value=httpx.Response(200, json={"elements": []}))
    await envelope.call("GET", "/identity/profiles/x/profileView", transport, now=NOW)
    await envelope.call("GET", "/messaging/conversations", transport, now=NOW)
    doc = db.outreach_request_budgets.docs[0]
    assert doc["daily_total"] == 2
    assert transport.await_count == 2
    assert len(db.outreach_physical_requests.docs) == 2


@pytest.mark.asyncio
async def test_mutation_timeout_latches_sender_and_permission(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch, "inbox_reply")
    transport = AsyncMock(side_effect=httpx.ReadTimeout("transport failed"))
    with pytest.raises(httpx.ReadTimeout):
        await envelope.call("POST", "/messaging/conversations/t/events", transport, action="message", now=NOW)
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"
    assert db.outreach_execution_permissions.docs[0]["latched"]
    with pytest.raises(RequestDenied):
        await envelope.call("POST", "/messaging/conversations/t/events", transport, action="message", now=NOW)
    assert transport.await_count == 1


@pytest.mark.asyncio
async def test_read_timeout_releases_sender_but_still_charges_budget(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    with pytest.raises(httpx.ReadTimeout):
        await envelope.call("GET", "/search/blended", AsyncMock(side_effect=httpx.ReadTimeout("failed")), now=NOW)
    assert db.outreach_sender_execution.docs[0]["status"] == "idle"
    assert db.outreach_request_budgets.docs[0]["daily_total"] == 1


@pytest.mark.asyncio
async def test_reply_revoked_during_preparation_prevents_transport(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    from outreach.core import request_guard
    reserve = request_guard.PhysicalBudget.reserve
    async def reserve_then_revoke(*args, **kwargs):
        result = await reserve(*args, **kwargs)
        await ExecutionPermission(db).revoke("w", "a", "operator", "stop", now=NOW)
        return result
    monkeypatch.setattr(request_guard.PhysicalBudget, "reserve", reserve_then_revoke)
    transport = AsyncMock()
    with pytest.raises(RequestDenied):
        await envelope.call("POST", "/messaging/conversations", transport, action="message", now=NOW)
    transport.assert_not_awaited()
    assert db.outreach_sender_execution.docs[0]["status"] == "idle"


@pytest.mark.asyncio
async def test_live_voyager_without_envelope_never_opens_socket(monkeypatch):
    from outreach.engine.voyager_client import VoyagerClient
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    network = AsyncMock()
    client = VoyagerClient(li_at="AQ-test-cookie", jsession_id="csrf", proxy_url="http://proxy:8000")
    with pytest.raises(RequestDenied):
        await client._request(network, "GET", "https://www.linkedin.com/voyager/api/me")
    network.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_ownership_is_shared_and_preserved(monkeypatch):
    from outreach.core.request_guard import request_parent
    from outreach.core.sender_execution import SenderExecution
    db, envelope = await ready_envelope(monkeypatch)
    guard = SenderExecution(db)
    assert await guard.acquire("w", "a", "parent", now=NOW)
    assert await guard.begin("w", "a", "parent", now=NOW)
    validator = AsyncMock(return_value=None)
    transport = AsyncMock(return_value=httpx.Response(200, json={}))
    with request_parent("parent", validator):
        await envelope.call("GET", "/identity/profiles/x", transport, now=NOW)
        await envelope.call("POST", "/messaging/conversations", transport, action="message", now=NOW)
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"
    assert validator.await_count == 6
    assert not await guard.acquire("w", "a", "search", now=NOW)


@pytest.mark.asyncio
async def test_cancellation_after_mutation_start_latches_sender(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    with pytest.raises(asyncio.CancelledError):
        await envelope.call("POST", "/messaging/conversations", AsyncMock(side_effect=asyncio.CancelledError), action="message", now=NOW)
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"


@pytest.mark.asyncio
async def test_live_gate_and_generation_change_prevent_network(monkeypatch):
    from outreach.core import request_guard
    db, envelope = await ready_envelope(monkeypatch)
    transport = AsyncMock()
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: False)
    with pytest.raises(RequestDenied, match="execution_disabled"):
        await envelope.call("GET", "/messaging/conversations", transport, now=NOW)
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: True)
    db.outreach_accounts.docs[0]["credential_generation"] = "replacement"
    with pytest.raises(RequestDenied, match="sender_changed"):
        await envelope.call("GET", "/messaging/conversations", transport, now=NOW)
    transport.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_replacement_after_evidence_prevents_socket(monkeypatch):
    from outreach.core.request_guard import request_parent
    from outreach.core.sender_execution import SenderExecution
    db, envelope = await ready_envelope(monkeypatch)
    guard = SenderExecution(db)
    await guard.acquire("w", "a", "parent", now=NOW)
    await guard.begin("w", "a", "parent", now=NOW)
    insert = db.outreach_physical_requests.insert_one
    async def replace_owner(doc):
        await insert(doc)
        await guard.release("w", "a", "parent")
        await guard.acquire("w", "a", "replacement", now=NOW)
        await guard.begin("w", "a", "replacement", now=NOW)
    monkeypatch.setattr(db.outreach_physical_requests, "insert_one", replace_owner)
    transport = AsyncMock()
    with request_parent("parent", AsyncMock(return_value=None)), pytest.raises(RequestDenied, match="sender_owner_changed"):
        await envelope.call("POST", "/messaging/conversations", transport, action="message", now=NOW)
    transport.assert_not_awaited()
    assert db.outreach_sender_execution.docs[0]["owner_token"] == "replacement"


@pytest.mark.asyncio
async def test_revoke_during_final_context_validation_blocks_transport(monkeypatch):
    from outreach.core.request_guard import request_parent
    from outreach.core.sender_execution import SenderExecution
    db, envelope = await ready_envelope(monkeypatch)
    guard = SenderExecution(db)
    await guard.acquire("w", "a", "parent", now=NOW)
    await guard.begin("w", "a", "parent", now=NOW)
    count = 0
    async def context_check():
        nonlocal count
        count += 1
        if count == 3:
            await ExecutionPermission(db).revoke("w", "a", "operator", "final_stop", now=NOW)
        return None
    transport = AsyncMock()
    with request_parent("parent", context_check), pytest.raises(RequestDenied):
        await envelope.call("POST", "/messaging/conversations", transport, action="message", now=NOW)
    transport.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 429])
async def test_ambiguous_mutation_response_latches_and_blocks_new_grant(monkeypatch, status):
    db, envelope = await ready_envelope(monkeypatch)
    with pytest.raises(RuntimeError):
        await envelope.call("POST", "/messaging/conversations", AsyncMock(return_value=httpx.Response(status, json={})), action="message", now=NOW)
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"
    with pytest.raises(ValueError, match="requires review"):
        await grant(db, clear_latch=True)


@pytest.mark.asyncio
async def test_actual_voyager_voice_uses_voice_cap_and_proxy_binding(monkeypatch):
    from outreach.engine.voyager_client import VoyagerClient
    db, envelope = await ready_envelope(monkeypatch)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    client = VoyagerClient(li_at="AQ-cookie", jsession_id="csrf", proxy_url="http://different-proxy:8000", request_envelope=envelope)
    network = AsyncMock()
    with pytest.raises(RequestDenied):
        await client._request(network, "POST", "https://www.linkedin.com/voyager/api/messaging/conversations", action="voice")
    network.post.assert_not_awaited()
    client.proxy_url = envelope.proxy_url
    db.outreach_accounts.docs[0]["request_budget"] = {"action_caps": {"voice": 0}}
    # Use NOW's grant but real method's clock; bind expiry to the current test clock.
    await ExecutionPermission(db).grant("w", "a", "g", ["sequence"], "operator")
    import hashlib
    envelope.approval_binding = {"action": "voice_note", "recipient": "urn:recipient", "content": {"body": "", "audio_digest": hashlib.sha256(b"fake-audio").hexdigest()}}
    with pytest.raises(RequestDenied, match="physical_action_cap"):
        await client.send_voice_note("urn:recipient", b"fake-audio")
    assert not db.outreach_physical_requests.docs


@pytest.mark.asyncio
async def test_voyager_transport_exception_cannot_expose_secrets(monkeypatch, caplog):
    from outreach.engine.voyager_client import VoyagerClient
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    client = VoyagerClient(li_at="AQ-cookie", jsession_id="csrf", proxy_url="http://proxy:8000")
    client.request_envelope = type("Reviewed", (), {"assert_content": lambda *args: None})()
    monkeypatch.setattr(client, "_request", AsyncMock(side_effect=RuntimeError("li_at=SECRET_COOKIE https://user:SECRET_PROXY@host")))
    result = await client.send_direct_message("urn:recipient", "Hello")
    assert "SECRET_COOKIE" not in str(result) + caplog.text
    assert "SECRET_PROXY" not in str(result) + caplog.text


@pytest.mark.asyncio
async def test_operator_review_preserves_original_evidence_and_never_regrants(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    with pytest.raises(httpx.ReadTimeout):
        await envelope.call("POST", "/messaging/conversations", AsyncMock(side_effect=httpx.ReadTimeout("failed")), action="message", now=NOW)
    record = db.outreach_physical_requests.docs[0]
    permission = ExecutionPermission(db)
    with pytest.raises(ValueError):
        await permission.resolve_request("w", "a", record["_id"], "operator", "confirmed_sent", "Reviewed actual provider conversation", workers_drained=False, now=NOW)
    await permission.resolve_request("w", "a", record["_id"], "operator", "confirmed_sent", "Reviewed actual provider conversation", workers_drained=True, now=NOW)
    assert db.outreach_physical_requests.docs[0]["original_status"] == "unknown_outcome"
    assert db.outreach_physical_requests.docs[0]["resolution"]["provenance"] == "human_assertion"
    assert db.outreach_sender_execution.docs[0]["status"] == "idle"
    assert not await permission.allowed("w", "a", "g", "sequence", now=NOW)


@pytest.mark.asyncio
async def test_permission_projection_cannot_authorize_execution():
    db = database()
    await grant(db)
    db.outreach_sender_execution.docs[0]["permission"]["latched"] = True
    assert not await ExecutionPermission(db).allowed("w", "a", "g", "sequence", now=NOW)


@pytest.mark.asyncio
async def test_expiry_during_final_database_await_blocks_socket_and_refunds_action(monkeypatch):
    from outreach.core import request_guard
    db, envelope = await ready_envelope(monkeypatch)
    current = NOW
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current
    monkeypatch.setattr(request_guard, "datetime", Clock)
    update = db.outreach_sender_execution.find_one_and_update
    async def delayed_boundary(*args, **kwargs):
        nonlocal current
        doc = await update(*args, **kwargs)
        current = NOW + timedelta(seconds=61)
        return doc
    monkeypatch.setattr(db.outreach_sender_execution, "find_one_and_update", delayed_boundary)
    transport = AsyncMock()
    with pytest.raises(RequestDenied, match="execution_permission_required"):
        await envelope.call("POST", "/messaging/conversations", transport, action="message")
    transport.assert_not_awaited()
    assert db.outreach_request_budgets.docs[0]["actions"]["message"] == 0
    assert db.outreach_request_budgets.docs[0]["daily_total"] == 1


@pytest.mark.asyncio
async def test_business_action_limits_share_all_sources_and_refund_once(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch)
    db.outreach_accounts.docs[0]["limits"] = {"messages": 1}
    budget = PhysicalBudget(db)
    config = db.outreach_accounts.docs[0]
    assert (await budget.reserve("w", "a", "sequence", "message", config, now=NOW, request_id="no-call"))[0]
    assert not (await budget.reserve("w", "a", "inbox_reply", "message", config, now=NOW))[0]
    await budget.refund_non_call("w", "a", "no-call", "message", NOW.strftime("%Y%m%d"))
    await budget.refund_non_call("w", "a", "no-call", "message", NOW.strftime("%Y%m%d"))
    assert db.outreach_request_budgets.docs[0]["actions"]["message"] == 0
    assert (await budget.reserve("w", "a", "inbox_reply", "message", config, now=NOW))[0]
    assert not (await budget.reserve("w", "a", "sequence", "message", config, now=NOW))[0]


@pytest.mark.asyncio
async def test_legacy_today_counts_are_carried_into_new_action_budget():
    db = database()
    config = {"limits": {"messages": 1}, "counters": {"date": NOW.strftime("%Y-%m-%d"), "messages": 1}}
    assert not (await PhysicalBudget(db).reserve("w", "a", "sequence", "message", config, now=NOW))[0]
    config["counters"]["date"] = "2026-10-01"
    assert (await PhysicalBudget(db).reserve("w", "a", "sequence", "message", config, now=NOW))[0]


@pytest.mark.asyncio
async def test_verify_read_before_migration_cannot_ignore_legacy_action_floor():
    db = database()
    budget = PhysicalBudget(db)
    assert (await budget.reserve("w", "a", "verify", "read", {}, now=NOW))[0]
    config = {"limits": {"messages": 1}, "counters": {"date": NOW.strftime("%Y-%m-%d"), "messages": 1}}
    assert not (await budget.reserve("w", "a", "sequence", "message", config, now=NOW))[0]


@pytest.mark.asyncio
async def test_completed_engage_submission_cannot_replay_after_reporting_failure(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch, "engage")
    envelope.operation_id = "engage:post"
    transport = AsyncMock(return_value=httpx.Response(200, json={}))
    await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    # A reporting write outside this boundary may fail. Reusing the operation
    # must preserve evidence and never call the provider twice.
    with pytest.raises(RequestDenied, match="physical_action_already_attempted"):
        await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    assert transport.await_count == 1
    assert db.outreach_physical_requests.docs[0]["status"] == "response_received"
    assert db.outreach_request_budgets.docs[0]["actions"]["comment"] == 1


@pytest.mark.asyncio
async def test_denied_retry_of_stable_unknown_operation_cannot_refund_sent_allowance(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch, "engage")
    envelope.operation_id = "engage:post"
    transport = AsyncMock(side_effect=httpx.ReadTimeout("failed"))
    with pytest.raises(httpx.ReadTimeout):
        await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    with pytest.raises(RequestDenied):
        await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    assert db.outreach_request_budgets.docs[0]["actions"]["comment"] == 1
    assert transport.await_count == 1


@pytest.mark.asyncio
async def test_physical_total_deadline_cancels_hung_mutation_and_latches(monkeypatch):
    from outreach.core import request_guard
    db, envelope = await ready_envelope(monkeypatch)
    monkeypatch.setattr(request_guard, "REQUEST_TIMEOUT_SECONDS", 0.001)
    async def hung():
        await asyncio.Event().wait()
    with pytest.raises(TimeoutError):
        await envelope.call("POST", "/messaging/conversations", hung, action="message", now=NOW)
    assert db.outreach_physical_requests.docs[0]["status"] == "unknown_outcome"
    assert db.outreach_sender_execution.docs[0]["status"] == "in_flight"


@pytest.mark.asyncio
async def test_session_authenticator_rejects_actual_envelope_proxy_mismatch(monkeypatch):
    from outreach.engine.session_authenticator import SessionAuthenticator
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    with pytest.raises(RequestDenied):
        await SessionAuthenticator.validate_session_cookie("AQ-cookie", jsession_id="csrf", proxy_url="http://different:8000",
            request_envelope=type("Envelope", (), {"proxy_url": "http://authorized:8000"})())


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["valid", "slot_missing", "country_changed", "lease_missing"])
async def test_pending_verification_checks_reserved_capacity_at_physical_boundary(monkeypatch, state):
    from outreach.core import request_guard, managed_proxy
    from outreach.models import ProxyConfig
    db = database()
    db.outreach_connection_jobs.docs = [{"id": "j", "workspace_id": "w", "sender_id": "a", "status": "running", "proxy_id": "p", "country_code": "US", "created_at": NOW}]
    db.outreach_sender_slots.docs = [{"workspace_id": "w", "sender_id": "a"}] if state != "slot_missing" else []
    db.outreach_proxy_leases.docs = [{"_id": "p", "workspace_id": "w", "sender_id": "a"}] if state != "lease_missing" else []
    db.outreach_proxy_inventory.docs = [{"_id": "p", "status": "available", "last_workspace_id": "w",
        "country_code": "GB" if state == "country_changed" else "US", "expires_at": NOW + timedelta(days=1)}]
    proxy = ProxyConfig(proxy_id="p", host="proxy", port=8000, username="", password_enc="", country_code="US")
    monkeypatch.setattr(managed_proxy, "_proxy_from_inventory", lambda row: proxy)
    monkeypatch.setattr(request_guard, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    monkeypatch.setattr(request_guard, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(request_guard, "is_shutting_down", lambda: False)
    await ExecutionPermission(db).grant("w", "a", "pending:j", ["verify"], "operator", now=NOW)
    envelope = RequestEnvelope(db, "w", "a", "pending:j", "verify", "http://proxy:8000", connection_job_id="j")
    transport = AsyncMock(return_value=httpx.Response(200, json={"elements": []}))
    if state == "valid":
        await envelope.call("GET", "/me", transport, now=NOW)
        transport.assert_awaited_once()
    else:
        with pytest.raises(RequestDenied):
            await envelope.call("GET", "/me", transport, now=NOW)
        transport.assert_not_awaited()


@pytest.mark.asyncio
async def test_stable_engage_operation_retries_only_proven_non_submission(monkeypatch):
    db, envelope = await ready_envelope(monkeypatch, "engage")
    envelope.operation_id = "engage:post"
    validations = 0
    async def temporary_denial():
        nonlocal validations
        validations += 1
        return "sender_changed" if validations == 2 else None
    envelope.authority_validator = temporary_denial
    transport = AsyncMock(return_value=httpx.Response(200, json={}))
    with pytest.raises(RequestDenied, match="sender_changed"):
        await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    transport.assert_not_awaited()
    assert db.outreach_physical_requests.docs[0]["status"] == "not_submitted"
    await envelope.call("POST", "/feed/comments", transport, action="comment", now=NOW)
    transport.assert_awaited_once()
    record = db.outreach_physical_requests.docs[0]
    assert record["status"] == "response_received"
    assert record["non_call_history"][0]["status"] == "not_submitted"
    assert db.outreach_request_budgets.docs[0]["actions"]["comment"] == 1
