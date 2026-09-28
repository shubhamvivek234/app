"""Sequence capability and execution safety regressions."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from outreach.core.dag_compiler import DAGCompiler, DAGValidationError


pytestmark = pytest.mark.usefixtures("outreach_paid_gate_stub")


def test_capability_catalog_distinguishes_code_support_from_live_gate(monkeypatch):
    from outreach.core.sequence_capabilities import sequence_capabilities

    monkeypatch.delenv("OUTREACH_LIVE_ACTIONS_ENABLED", raising=False)
    catalog = {entry["type"]: entry for entry in sequence_capabilities()}
    assert catalog["connection_request"]["supported"] is True
    assert catalog["connection_request"]["builder_available"] is True
    assert catalog["connection_request"]["live_enabled"] is False
    assert catalog["endorse_skills"]["builder_available"] is False
    assert catalog["endorse_skills"]["reason"]


def test_condition_requires_explicit_boolean_edges():
    nodes = [
        {"id": "if", "type": "if_email_available"},
        {"id": "yes", "type": "send_email"},
        {"id": "no", "type": "visit_profile"},
    ]
    edges = [
        {"source": "if", "target": "yes", "sourceHandle": "yes"},
        {"source": "if", "target": "no", "sourceHandle": "no"},
    ]
    compiled = DAGCompiler.validate_and_compile(nodes, edges)
    assert compiled["nodes"]["if"]["branches"] == {"positive": "yes", "negative": "no"}

    edges[0].pop("sourceHandle")
    with pytest.raises(DAGValidationError, match="Yes/No"):
        DAGCompiler.validate_and_compile(nodes, edges)


def _runner_db(node_type="connection_request", *, waiting=None):
    db = MagicMock()
    lead = {
        "id": "lead_a", "workspace_id": "ws_a", "campaign_id": "camp_a",
        "linkedin_url": "https://www.linkedin.com/in/person-a/", "assigned_account_id": "sender_a",
        "execution_state": "queued", **(waiting or {}),
    }
    db.outreach_leads.find_one = AsyncMock(return_value=lead)
    db.outreach_leads.update_one = AsyncMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value={"id": "camp_a", "status": "active", "schedule": {}})
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_accounts.find_one = AsyncMock(return_value={"id": "sender_a", "status": "active", "user_id": "u_a"})
    db.outreach_accounts.update_one = AsyncMock()
    db.outreach_sequences.find_one = AsyncMock(return_value={
        "compiled_dag": {"root_node_ids": ["step_a"], "nodes": {"step_a": {
            "id": "step_a", "type": node_type, "config": {}, "next_default": None,
            "branches": {"positive": "yes", "negative": "no"} if node_type == "if_connected" else {},
        }}},
    })
    db.outreach_tasks.insert_one = AsyncMock()
    db.outreach_tasks.update_one = AsyncMock()
    db.outreach_tasks.find_one = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_duplicate_dispatch_claim_never_resends_linkedin_action():
    from outreach.tasks.sequence_executor import SequenceExecutor

    db = _runner_db()
    db.outreach_tasks.insert_one.side_effect = DuplicateKeyError("already claimed")
    db.outreach_tasks.find_one.side_effect = [None, {"status": "dispatching"}]
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock, return_value=True), \
         patch("outreach.tasks.sequence_executor.VoyagerClient") as voyager:
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "action_uncertain"
    voyager.return_value.send_connection_invite.assert_not_called()
    assert any(
        call.args[1].get("$set", {}).get("execution_state") == "waiting_trigger"
        for call in db.outreach_leads.update_one.call_args_list
    )


@pytest.mark.asyncio
async def test_unknown_connection_signal_never_takes_no_branch():
    from outreach.tasks.sequence_executor import SequenceExecutor

    db = _runner_db("if_connected")
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.VoyagerClient") as voyager:
        voyager.return_value.check_connection_status_strict = AsyncMock(return_value=None)
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "condition_unknown"
    assert all(
        call.args[1].get("$set", {}).get("current_node_id") != "no"
        for call in db.outreach_leads.update_one.call_args_list
    )


@pytest.mark.asyncio
async def test_expired_unknown_connection_signal_stops_for_manual_review():
    from outreach.tasks.sequence_executor import SequenceExecutor

    db = _runner_db("if_connected", waiting={
        "waiting_for_connection_at": datetime.now(timezone.utc) - timedelta(days=4),
    })
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.VoyagerClient") as voyager:
        voyager.return_value.check_connection_status_strict = AsyncMock(return_value=None)
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "condition_needs_review"
    updates = db.outreach_leads.update_one.await_args.args[1]["$set"]
    assert updates["execution_state"] == "waiting_trigger"
    assert updates["next_action_due_at"] is None
    assert "current_node_id" not in updates


@pytest.mark.asyncio
async def test_deterministic_email_rejection_fails_lead_without_campaign_quarantine(monkeypatch):
    from outreach.tasks.sequence_executor import SequenceExecutor

    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _runner_db("send_email")
    db.outreach_leads.find_one.return_value.update({"email": "lead@example.com"})
    db.outreach_sequences.find_one.return_value["compiled_dag"]["nodes"]["step_a"]["config"] = {
        "subject": "Hello", "body": "Hi there",
    }
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.email_finder.is_lead_email_available", new_callable=AsyncMock, return_value=True), \
         patch("outreach.core.mailbox_connection.get_ready_mailbox", new_callable=AsyncMock, return_value={"provider": "gmail"}), \
         patch("outreach.core.mailbox_delivery.send_outreach_email", new_callable=AsyncMock,
               return_value={"status": "failed", "reason": "Provider rejected the message"}):
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "action_failed"
    assert db.outreach_tasks.update_one.await_args.args[1]["$set"]["status"] == "failed"
    db.outreach_campaigns.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_mailbox_defers_worker_instead_of_hot_looping(monkeypatch):
    from celery_workers.tasks.outreach import _run_due_steps

    monkeypatch.setenv("DB_NAME", "outreach_test")
    db = MagicMock()
    db.outreach_campaigns.distinct = AsyncMock(return_value=["camp_a"])
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{
        "id": "lead_a", "workspace_id": "ws_a", "campaign_id": "camp_a",
    }])
    db.outreach_leads.find.return_value = cursor
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    with patch("celery_workers.tasks.outreach.get_client", new_callable=AsyncMock,
               return_value={"outreach_test": db}), \
         patch("celery_workers.tasks.outreach.is_shutting_down", return_value=False), \
         patch("celery_workers.tasks.outreach.sequence_dispatch_enabled", return_value=True), \
         patch("outreach.tasks.sequence_executor.SequenceExecutor.execute_lead_step", new_callable=AsyncMock,
               return_value={"status": "mailbox_unavailable"}):
        result = await _run_due_steps()

    assert result["deferred"] == 1
    updates = [call.args[1].get("$set", {}) for call in db.outreach_leads.update_one.await_args_list]
    assert any(update.get("next_action_due_at", datetime.min.replace(tzinfo=timezone.utc))
               > datetime.now(timezone.utc) for update in updates)


@pytest.mark.asyncio
async def test_manually_confirmed_email_advances_without_resend_or_second_quota(monkeypatch):
    from outreach.tasks.sequence_executor import SequenceExecutor

    monkeypatch.setenv("OUTREACH_EMAIL_SEND_ENABLED", "true")
    monkeypatch.setenv("OUTREACH_EMAIL_SYNC_ENABLED", "true")
    db = _runner_db("send_email")
    db.outreach_leads.find_one.return_value.update({"email": "lead@example.com"})
    db.outreach_sequences.find_one.return_value["compiled_dag"]["nodes"]["step_a"]["config"] = {
        "subject": "Hello", "body": "Hi there",
    }
    db.outreach_tasks.find_one = AsyncMock(return_value={"status": "accepted"})
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.OutboundRateLimiter.check_and_increment_daily_limit", new_callable=AsyncMock) as quota, \
         patch("outreach.core.email_finder.is_lead_email_available", new_callable=AsyncMock) as email_check, \
         patch("outreach.core.mailbox_connection.get_ready_mailbox", new_callable=AsyncMock) as mailbox_check, \
         patch("outreach.core.mailbox_delivery.send_outreach_email", new_callable=AsyncMock) as provider_send:
        result = await SequenceExecutor.execute_lead_step("lead_a", db)

    assert result["status"] == "success"
    quota.assert_not_awaited()
    email_check.assert_not_awaited()
    mailbox_check.assert_not_awaited()
    provider_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_only_sender_never_needs_a_linkedin_cookie(monkeypatch):
    from outreach.tasks.sequence_executor import SequenceExecutor

    monkeypatch.setenv("OUTREACH_HUNTER_ENABLED", "true")
    db = _runner_db("find_email")
    db.outreach_accounts.find_one.return_value = {
        "id": "sender_a", "workspace_id": "ws_a", "status": "active", "user_id": "u_a",
    }
    with patch("outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("outreach.tasks.sequence_executor.VoyagerClient") as voyager, \
         patch("outreach.core.email_finder.find_lead_email", new_callable=AsyncMock,
               return_value={"status": "not_found"}):
        result = await SequenceExecutor.execute_lead_step("lead_a", db)
    assert result["status"] == "success"
    voyager.assert_not_called()
