"""Public worker boundaries defer known non-calls and preserve uncertainty."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from tests.outreach_memory import Database
from tests.test_outreach_execution_outbox import execution_db, stub_transport
from outreach.core.request_guard import RequestDenied


@pytest.mark.asyncio
async def test_sequence_denial_is_known_not_submitted(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    client.send_direct_message.side_effect = RequestDenied("execution_permission_required")
    result = await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w")
    assert result["not_submitted"]
    assert result["status"] == "execution_permission_required"
    assert db.outreach_intents.docs[0]["status"] == "pending"
    assert db.outreach_campaigns.docs[0]["status"] == "active"
    assert (await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w"))["status"] == "action_busy"
    assert executor.OutboundRateLimiter.check_and_increment_daily_limit.await_count == 0


@pytest.mark.asyncio
async def test_sequence_condition_denial_defers_instead_of_failing(monkeypatch):
    executor, client = stub_transport(monkeypatch)
    db = execution_db()
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["type"] = "if_connected"
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["branches"] = {"positive": "end"}
    client.check_connection_status_strict = AsyncMock(side_effect=RequestDenied("sender_busy", 5))
    result = await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w")
    assert result["status"] == "request_deferred"
    assert result["retry_after"] == 5
    assert db.outreach_leads.docs[0]["execution_state"] == "queued"


@pytest.mark.asyncio
async def test_auto_withdraw_cannot_fabricate_provider_completion():
    from outreach.core.safety_shield import SafetyShield
    db = Database(outreach_accounts=[{"id": "a", "workspace_id": "w", "auto_withdraw_enabled": True, "status": "active"}],
                  outreach_leads=[{"id": "l", "workspace_id": "w", "assigned_account_id": "a", "created_at": datetime.now(timezone.utc) - timedelta(days=30)}])
    assert await SafetyShield.withdraw_stale_invitations("a", db, workspace_id="w") == 0
    assert not db.outreach_leads.docs[0].get("invitation_withdrawn")
    assert not db.outreach_withdrawn_invites.docs


@pytest.mark.asyncio
async def test_crawler_future_due_page_cannot_claim_or_call(monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    db = Database(outreach_import_jobs=[{"id": "job", "workspace_id": "w", "status": "queued", "lease_token": "lease", "cursor": 0,
        "next_page_due_at": datetime.now(timezone.utc) + timedelta(hours=2)}])
    assert (await worker._crawl_page("job", 0, "lease", db=db))["status"] == "job_not_found_or_cancelled"
    assert db.outreach_import_jobs.docs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_crawler_publisher_failure_preserves_durable_due_job(monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(worker.crawl_page, "delay", lambda *args: (_ for _ in ()).throw(RuntimeError("broker offline")))
    due = datetime.now(timezone.utc) - timedelta(seconds=1)
    db = Database(outreach_import_jobs=[{"id": "job", "workspace_id": "w", "status": "queued", "lease_token": "lease", "cursor": 0, "next_page_due_at": due}])
    assert (await worker._dispatch_due_search_pages(db=db))["published"] == 0
    assert db.outreach_import_jobs.docs[0]["next_page_due_at"] == due
    assert db.outreach_import_jobs.docs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_verification_waits_for_operator_permission_without_discarding_pending_secrets(monkeypatch):
    from celery_workers.tasks import outreach as worker
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.models import ProxyConfig
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    monkeypatch.setattr(worker, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    monkeypatch.setattr(worker, "_proxy_from_inventory", lambda row: ProxyConfig(proxy_id="p", host="191.116.125.248", port=8000, username="", password_enc="", country_code="US"))
    monkeypatch.setattr(ExecutionPermission, "allowed", AsyncMock(return_value=False))
    health = AsyncMock(return_value=True)
    monkeypatch.setattr(worker.JITProxyManager, "test_proxy_health", health)
    db = Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "sender_id": "a", "status": "queued", "proxy_id": "p",
        "country_code": "US", "li_at_enc": "encrypted-pending", "jsession_id_enc": "encrypted-csrf", "created_at": datetime.now(timezone.utc), "created_slot": True, "new_proxy_reservation": True}],
        outreach_sender_slots=[{"workspace_id": "w", "sender_id": "a"}],
        outreach_connection_locks=[{"_id": "a", "job_id": "j", "workspace_id": "w"}],
        outreach_proxy_leases=[{"_id": "p", "workspace_id": "w", "sender_id": "a"}],
        outreach_proxy_inventory=[{"_id": "p", "last_workspace_id": "w", "status": "available", "country_code": "US", "host": "191.116.125.248", "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}])
    result = await worker._verify_sender_connection("j", "w", "trace", db=db)
    assert result["status"] == "deferred"
    assert db.outreach_connection_jobs.docs[0]["status"] == "queued"
    assert db.outreach_connection_jobs.docs[0]["li_at_enc"] == "encrypted-pending"
    assert db.outreach_connection_locks.docs
    assert db.outreach_sender_slots.docs and db.outreach_proxy_leases.docs
    health.assert_not_awaited()


@pytest.mark.asyncio
async def test_verification_future_due_job_does_not_claim(monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    db = Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "status": "queued",
        "next_verification_due_at": datetime.now(timezone.utc) + timedelta(hours=1)}])
    assert (await worker._verify_sender_connection("j", "w", "trace", db=db))["status"] == "already_claimed"
    assert db.outreach_connection_jobs.docs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_verification_publisher_failure_keeps_pending_job(monkeypatch):
    from celery_workers.tasks import outreach as worker
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    monkeypatch.setattr(worker.verify_sender_connection, "delay", lambda *args: (_ for _ in ()).throw(RuntimeError("broker offline")))
    due = datetime.now(timezone.utc) - timedelta(seconds=1)
    db = Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "status": "queued", "trace_id": "trace",
        "created_at": datetime.now(timezone.utc), "next_verification_due_at": due, "li_at_enc": "encrypted-pending"}])
    assert (await worker._dispatch_due_verifications(db=db))["published"] == 0
    assert db.outreach_connection_jobs.docs[0]["li_at_enc"] == "encrypted-pending"
    assert db.outreach_connection_jobs.docs[0]["next_verification_due_at"] == due


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ["before_activation", "before_failure_cleanup"])
async def test_verification_cannot_activate_or_clean_up_after_losing_job_owner(monkeypatch, race):
    from celery_workers.tasks import outreach as worker
    from outreach.models import ProxyConfig
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    monkeypatch.setattr(worker, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    monkeypatch.setattr(worker.ExecutionPermission, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(worker, "pending_session", AsyncMock(return_value={"li_at": "local-cookie", "jsession_id": "ajax:local", "li_a": ""}))
    monkeypatch.setattr(worker, "_proxy_from_inventory", lambda row: ProxyConfig(proxy_id="p", host="191.116.125.248", port=8000, username="", password_enc="", country_code="US"))
    monkeypatch.setattr(worker.JITProxyManager, "test_proxy_health", AsyncMock(return_value=True))
    release = AsyncMock()
    monkeypatch.setattr(worker, "release_sender_reservation", release)
    db = Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "sender_id": "a", "user_id": "u", "status": "queued", "proxy_id": "p",
        "country_code": "US", "li_at_enc": "encrypted-pending", "jsession_id_enc": "encrypted-csrf", "created_at": datetime.now(timezone.utc), "created_slot": True, "new_proxy_reservation": True}],
        outreach_sender_slots=[{"workspace_id": "w", "sender_id": "a"}],
        outreach_connection_locks=[{"_id": "a", "job_id": "j", "workspace_id": "w"}],
        outreach_proxy_leases=[{"_id": "p", "workspace_id": "w", "sender_id": "a"}],
        outreach_proxy_inventory=[{"_id": "p", "last_workspace_id": "w", "status": "available", "country_code": "US", "host": "191.116.125.248", "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}])
    inventory_find = db.outreach_proxy_inventory.find_one
    checks = 0
    async def raced_inventory(*args, **kwargs):
        nonlocal checks
        checks += 1
        result = await inventory_find(*args, **kwargs)
        if checks == 2 and race == "before_activation":
            db.outreach_connection_jobs.docs[0]["status"] = "failed"
        return result
    monkeypatch.setattr(db.outreach_proxy_inventory, "find_one", raced_inventory)
    async def verify(**kwargs):
        if race == "before_failure_cleanup":
            db.outreach_connection_jobs.docs[0]["status"] = "failed"
            raise RuntimeError("old worker lost ownership")
        return {"linkedin_urn": "urn:li:person:one", "account_name": "Pilot"}
    monkeypatch.setattr(worker.SessionAuthenticator, "validate_session_cookie", verify)
    assert (await worker._verify_sender_connection("j", "w", "trace", db=db))["status"] == "connection_job_expired"
    assert not db.outreach_accounts.docs
    release.assert_not_awaited()
    assert db.outreach_sender_slots.docs


@pytest.mark.asyncio
async def test_unknown_credential_write_retains_finalization_evidence_and_assets(monkeypatch):
    from celery_workers.tasks import outreach as worker
    from outreach.models import ProxyConfig
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setattr(worker, "live_actions_enabled", lambda: True)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    monkeypatch.setattr(worker, "get_active_entitlement", AsyncMock(return_value={"seats": 1}))
    monkeypatch.setattr(worker.ExecutionPermission, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(worker, "pending_session", AsyncMock(return_value={"li_at": "local-cookie", "jsession_id": "ajax:local", "li_a": ""}))
    monkeypatch.setattr(worker, "_proxy_from_inventory", lambda row: ProxyConfig(proxy_id="p", host="191.116.125.248", port=8000, username="", password_enc="", country_code="US"))
    monkeypatch.setattr(worker.JITProxyManager, "test_proxy_health", AsyncMock(return_value=True))
    monkeypatch.setattr(worker.SessionAuthenticator, "validate_session_cookie", AsyncMock(return_value={"linkedin_urn": "urn:li:person:one"}))
    created = datetime.now(timezone.utc) - timedelta(minutes=1)
    db = Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "sender_id": "a", "user_id": "u", "status": "queued", "proxy_id": "p",
        "country_code": "US", "li_at_enc": "encrypted-pending", "jsession_id_enc": "encrypted-csrf", "created_slot": True,
        "new_proxy_reservation": True, "created_at": created}],
        outreach_sender_slots=[{"workspace_id": "w", "sender_id": "a"}],
        outreach_connection_locks=[{"_id": "a", "job_id": "j", "workspace_id": "w"}],
        outreach_proxy_leases=[{"_id": "p", "workspace_id": "w", "sender_id": "a"}],
        outreach_proxy_inventory=[{"_id": "p", "last_workspace_id": "w", "status": "available", "country_code": "US", "host": "191.116.125.248", "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}])
    insert = db.outreach_accounts.insert_one
    async def committed_without_ack(doc):
        await insert(doc)
        raise RuntimeError("acknowledgement lost")
    monkeypatch.setattr(db.outreach_accounts, "insert_one", committed_without_ack)
    assert (await worker._verify_sender_connection("j", "w", "trace", db=db))["status"] == "finalization_review_required"
    job = db.outreach_connection_jobs.docs[0]
    assert job["status"] == "finalizing" and job["needs_operator_repair"]
    assert "created_at" not in job and job["custody_started_at"] == created
    assert "li_at_enc" not in job
    assert job["credential_generation"] == db.outreach_accounts.docs[0]["connection_finalization"]["generation"]
    assert not db.outreach_accounts.docs[0].get("session_cookie_enc")
    assert db.outreach_proxy_leases.docs and db.outreach_sender_slots.docs and db.outreach_connection_locks.docs
    assert (await worker._clean_stale_connections(db=db))["cleaned"] == 0
    with pytest.raises(ValueError, match="finalization"):
        await worker.ExecutionPermission(db).grant("w", "a", job["credential_generation"], ["sync"], "operator", clear_latch=True)
