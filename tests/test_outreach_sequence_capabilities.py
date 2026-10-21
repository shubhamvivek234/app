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
        "execution_state": "queued", "current_node_id": "step_a", **(waiting or {}),
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
    if node_type == 'if_connected':
        # A positive-control graph needs actual referenced successors.
        db.outreach_sequences.find_one.return_value['compiled_dag']['nodes'].update({
            key: {'id':key,'type':'visit_profile','delay_hours':0,'config':{},'branches':{},'next_default':None}
            for key in ('yes','no')})
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


def test_dripify_parity_variables_and_pipe_fallbacks():
    from outreach.core.dag_compiler import interpolate_template

    lead = {
        "first_name": "Maya",
        "last_name": "Lin",
        "company_name": "Acme AI",
        "job_title": "VP of Sales",
        "connections_count": 840,
        "top_skill": "Enterprise SaaS",
        "company_location": "Austin, TX",
        "school": "Stanford University",
        "years_in_company": "3 years",
        "years_in_role": "2 years",
        "mutual_connections": "12",
    }
    tpl = (
        "Hi {{first_name}}, saw you lead {{position}} at {{company}} in {{company_location}} "
        "with {{number_of_connections}} connections and {{top_skill}} expertise "
        "(fallback: {{missing_var | 'default_val'}})."
    )
    rendered = interpolate_template(tpl, lead)
    assert rendered == (
        "Hi Maya, saw you lead VP of Sales at Acme AI in Austin, TX "
        "with 840 connections and Enterprise SaaS expertise (fallback: default_val)."
    )


def test_activity_control_governor_scales_by_age_connections_and_tier():
    from outreach.core.safety_shield import WarmUpGovernor

    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    # New account (3 days old) with < 100 connections
    low_conn_account = {
        "warmup_started_at": now - timedelta(days=3),
        "connections_count": 50,
        "premium_product": "classic",
        "limits": {"connection_invites": 75, "messages": 150, "profile_visits": 150},
    }
    low_limits = WarmUpGovernor.get_activity_control_limits(low_conn_account, now=now)
    assert low_limits["connection_invites"] <= 10
    assert low_limits["messages"] <= 25

    # Mature account (30 days old) with 1,200 connections & Sales Navigator
    mature_sn_account = {
        "warmup_started_at": now - timedelta(days=30),
        "connections_count": 1200,
        "premium_product": "sales_navigator",
        "limits": {"connection_invites": 75, "messages": 150, "profile_visits": 150},
    }
    mature_limits = WarmUpGovernor.get_activity_control_limits(mature_sn_account, now=now)
    assert mature_limits["connection_invites"] == 75
    assert mature_limits["messages"] == 150
    assert mature_limits["profile_visits"] == 150


def test_extended_sequence_capabilities_support_follow_comment_and_gated_actions(monkeypatch):
    from outreach.core.sequence_capabilities import sequence_capabilities

    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    base_catalog = {entry["type"]: entry for entry in sequence_capabilities()}
    assert base_catalog["follow"]["supported"] is True
    assert base_catalog["follow"]["live_enabled"] is True
    assert base_catalog["comment_last_post"]["supported"] is True
    assert base_catalog["comment_last_post"]["live_enabled"] is True

    monkeypatch.setenv("OUTREACH_EXTENDED_SEQUENCE_ACTIONS_ENABLED", "true")
    ext_catalog = {entry["type"]: entry for entry in sequence_capabilities()}
    assert ext_catalog["endorse_skills"]["supported"] is True
    assert ext_catalog["inmail"]["supported"] is True
    assert ext_catalog["open_profile_check"]["supported"] is True
    assert ext_catalog["withdraw_invite"]["supported"] is True


def test_ab_testing_deterministic_variant_selection_and_preview():
    from outreach.core.dag_compiler import DAGCompiler, select_step_variant
    from outreach.core.sequence_preview import analyze_sequence

    node = {
        "id": "msg_step_1",
        "type": "send_message",
        "delay_hours": 24,
        "config": {
            "body": "Default body",
            "variants": [
                {"id": "A", "body": "Hi {{first_name}}, variant A"},
                {"id": "B", "body": "Hi {{first_name}}, variant B"},
                {"id": "C", "body": "Hi {{first_name}}, variant C"},
            ],
        },
    }
    lead_1 = {"id": "lead_alpha", "linkedin_url": "https://linkedin.com/in/alpha"}

    vid_1a, cfg_1a = select_step_variant(node, lead_1)
    vid_1b, cfg_1b = select_step_variant(node, lead_1)
    assert vid_1a == vid_1b
    assert cfg_1a["body"] == cfg_1b["body"]
    assert vid_1a in {"A", "B", "C"}

    # Respects sticky pre-assigned variant on lead
    lead_sticky = {"id": "lead_alpha", "ab_variants_assigned": {"msg_step_1": "C"}}
    vid_sticky, cfg_sticky = select_step_variant(node, lead_sticky)
    assert vid_sticky == "C"
    assert cfg_sticky["body"] == "Hi {{first_name}}, variant C"

    # Sequence preview validates all A/B/C variants
    compiled = DAGCompiler.validate_and_compile([node], [])
    analysis = analyze_sequence(compiled)
    assert [i for i in analysis["issues"] if i["severity"] == "error"] == []


def test_withdraw_invite_21_day_cooldown_validation(monkeypatch):
    from outreach.core.dag_compiler import DAGCompiler
    from outreach.core.sequence_preview import analyze_sequence

    monkeypatch.setenv("OUTREACH_EXTENDED_SEQUENCE_ACTIONS_ENABLED", "true")
    # Reconnect after withdraw with only 48 hours (< 504 hours / 21 days) -> error
    nodes = [
        {"id": "n1", "type": "connection_request", "delay_hours": 0, "config": {"note": ""}},
        {"id": "n2", "type": "withdraw_invite", "delay_hours": 72, "config": {}},
        {"id": "n3", "type": "connection_request", "delay_hours": 48, "config": {"note": ""}},
    ]
    edges = [
        {"source": "n1", "target": "n2", "condition_type": "negative"},
        {"source": "n2", "target": "n3", "condition_type": "default"},
    ]
    res_short = analyze_sequence(DAGCompiler.validate_and_compile(nodes, edges))
    error_codes = {e["code"] for e in res_short["issues"] if e["severity"] == "error"}
    assert "reconnect_before_21_days" in error_codes

    # Reconnect after withdraw with 504 hours (21 days) -> valid
    nodes[2]["delay_hours"] = 504
    res_ok = analyze_sequence(DAGCompiler.validate_and_compile(nodes, edges))
    assert "reconnect_before_21_days" not in {e["code"] for e in res_ok["issues"] if e["severity"] == "error"}


@pytest.mark.asyncio
async def test_weekly_invite_limit_isolates_connection_invites_only():
    from outreach.core.safety_shield import SafetyShield
    from outreach.core.rate_limiter import OutboundRateLimiter

    assert SafetyShield.is_weekly_invite_limit_error("You've reached the weekly invitation limit") is True
    assert SafetyShield.is_weekly_invite_limit_error("Normal network timeout") is False

    now = datetime.now(timezone.utc)
    future_reset = now + timedelta(days=4)
    account = {
        "id": "acc_1",
        "workspace_id": "ws_1",
        "status": "active",
        "weekly_invite_limit_reached": True,
        "weekly_invite_reset_at": future_reset,
        "limits": {"connection_invites": 40, "messages": 80, "profile_visits": 100},
        "counters": {"date": now.strftime("%Y-%m-%d"), "connection_invites": 5, "messages": 10, "profile_visits": 10},
    }

    class _UpdateResult:
        matched_count = 1

    class _FakeAccounts:
        async def update_one(self, filt, update):
            return _UpdateResult()

    class _FakeDB:
        outreach_accounts = _FakeAccounts()

    # Connection invites are blocked while weekly invite cap is active
    allowed_invite = await OutboundRateLimiter.check_and_increment_daily_limit(account, "connection_invites", _FakeDB())
    assert allowed_invite is False

    # Direct messages and profile visits continue unaffected!
    allowed_message = await OutboundRateLimiter.check_and_increment_daily_limit(account, "messages", _FakeDB())
    assert allowed_message is True


def test_custom_name_scrubber_strips_user_terms():
    from outreach.core.name_cleaner import clean_first_name

    cleaned = clean_first_name("Dr. Elena (Hiring!) Ex-Meta", custom_scrub_terms=["Dr.", "Ex-Meta"])
    assert cleaned == "Elena"
