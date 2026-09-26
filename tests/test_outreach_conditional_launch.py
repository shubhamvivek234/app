"""Conditional warm-up activation keeps the existing all-leads gate."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from api.deps import get_current_user
from db.mongo import get_db

from outreach.api.campaigns import (
    ArmWarmupRequest,
    _evaluate_warmup,
    arm_warmup_campaign,
    router as campaigns_router,
)
from celery_workers.tasks.outreach import _run_warmup_launches


USER = {"user_id": "owner", "default_workspace_id": "workspace_1"}


@pytest.mark.asyncio
async def test_conditional_launch_http_feature_gate_is_off_by_default(monkeypatch):
    monkeypatch.delenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(campaigns_router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        feature = await client.get("/api/v1/outreach/campaigns/features/conditional-launch")
        arm = await client.post("/api/v1/outreach/campaigns/campaign_1/arm-warmup",
                                json={"engage_list_id": "list_1", "warmup_hours": 24})
    assert feature.status_code == 200
    assert feature.json() == {"enabled": False}
    assert arm.status_code == 403


class Cursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, length=10000):
        return self.items[:length]


def gate_db(now, engaged=True):
    db = SimpleNamespace()
    db.outreach_engage_lists = SimpleNamespace(find=lambda query: Cursor([
        {"id": "list_1", "name": "Cohort", "warmup_hours": 24},
    ]))
    db.outreach_engage_contacts = SimpleNamespace(find=lambda query: Cursor([
        {"id": "contact_1", "profile_url": "https://www.linkedin.com/in/alex/"},
    ]))
    db.outreach_engage_posts = SimpleNamespace(find=lambda query: Cursor([
        {"contact_id": "contact_1", "status": "liked", "liked_at": now - timedelta(hours=25)},
    ] if engaged else []))
    db.outreach_leads = SimpleNamespace(find=lambda query: Cursor([
        {"id": "lead_1", "linkedin_url": "https://www.linkedin.com/in/alex/"},
        {"id": "lead_2", "linkedin_url": "https://www.linkedin.com/in/sam/"},
    ]))
    return db


@pytest.mark.asyncio
async def test_warmup_requires_confirmed_engagement_for_every_lead():
    now = datetime.now(timezone.utc)
    db = gate_db(now)
    result = await _evaluate_warmup("campaign_1", "workspace_1", db, now=now)
    assert result["missing_count"] == 1
    assert result["ready"] is False
    # Adding a second confirmed action makes the entire cohort eligible.
    db.outreach_engage_contacts.find = lambda query: Cursor([
        {"id": "contact_1", "profile_url": "https://www.linkedin.com/in/alex/"},
        {"id": "contact_2", "profile_url": "https://www.linkedin.com/in/sam/"},
    ])
    db.outreach_engage_posts.find = lambda query: Cursor([
        {"contact_id": "contact_1", "status": "liked", "liked_at": now - timedelta(hours=25)},
        {"contact_id": "contact_2", "status": "commented", "commented_at": now - timedelta(hours=25)},
    ])
    result = await _evaluate_warmup("campaign_1", "workspace_1", db, now=now)
    assert result["missing_count"] == 0
    assert result["ready"] is True
    db.outreach_leads.find = lambda query: Cursor([
        {"id": "lead_1", "linkedin_url": "https://linkedin.com/in/alex/"},
    ])
    assert (await _evaluate_warmup("campaign_1", "workspace_1", db, now=now))["missing_count"] == 0


@pytest.mark.asyncio
async def test_warmup_waits_for_full_cooldown_and_rejects_legacy_status():
    now = datetime.now(timezone.utc)
    db = gate_db(now)
    db.outreach_leads.find = lambda query: Cursor([
        {"id": "lead_1", "linkedin_url": "https://www.linkedin.com/in/alex/"},
    ])
    db.outreach_engage_posts.find = lambda query: Cursor([
        {"contact_id": "contact_1", "status": "liked", "liked_at": now - timedelta(hours=2)},
    ])
    assert (await _evaluate_warmup("campaign_1", "workspace_1", db, now=now))["ready"] is False
    db.outreach_engage_posts.find = lambda query: Cursor([
        {"contact_id": "contact_1", "status": "liked"},
    ])
    assert (await _evaluate_warmup("campaign_1", "workspace_1", db, now=now))["missing_count"] == 1


@pytest.mark.asyncio
async def test_conditional_gate_uses_only_the_selected_engage_list():
    now = datetime.now(timezone.utc)
    db = gate_db(now)
    db.outreach_engage_lists.find = lambda query: Cursor([
        {"id": "selected", "warmup_hours": 24},
        {"id": "other", "warmup_hours": 24},
    ])
    db.outreach_engage_contacts.find = lambda query: Cursor([
        {"id": "contact_1", "profile_url": "https://www.linkedin.com/in/alex/"},
    ])
    db.outreach_engage_posts.find = lambda query: Cursor(
        [{"contact_id": "contact_1", "status": "liked", "liked_at": now - timedelta(hours=25)}]
        if query["list_id"] == "other" else []
    )
    db.outreach_leads.find = lambda query: Cursor([
        {"id": "lead_1", "linkedin_url": "https://www.linkedin.com/in/alex/"},
    ])
    gate = await _evaluate_warmup("campaign_1", "workspace_1", db, now=now, required_list_id="selected")
    assert gate["ready"] is False
    assert gate["missing_count"] == 1


@pytest.mark.asyncio
async def test_unrelated_contact_does_not_extend_cohort_cooldown():
    now = datetime.now(timezone.utc)
    db = gate_db(now)
    db.outreach_engage_contacts.find = lambda query: Cursor([
        {"id": "contact_1", "profile_url": "https://www.linkedin.com/in/alex/"},
        {"id": "contact_2", "profile_url": "https://www.linkedin.com/in/other/"},
    ])
    db.outreach_engage_posts.find = lambda query: Cursor([
        {"contact_id": "contact_1", "status": "liked", "liked_at": now - timedelta(hours=25)},
        {"contact_id": "contact_2", "status": "liked", "liked_at": now - timedelta(minutes=5)},
    ])
    db.outreach_leads.find = lambda query: Cursor([
        {"id": "lead_1", "linkedin_url": "https://www.linkedin.com/in/alex/"},
    ])
    gate = await _evaluate_warmup("campaign_1", "workspace_1", db, now=now)
    assert gate["ready"] is True


@pytest.mark.asyncio
async def test_arming_requires_feature_flag_and_workspace_list(monkeypatch):
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(find_one=AsyncMock(return_value={
            "id": "campaign_1", "status": "draft", "workspace_id": "workspace_1",
            "sender_account_ids": ["sender_1"], "schedule": {"days": [1]},
        }), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
        outreach_engage_lists=SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock()),
        outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={"nodes": [{"id": "start"}]})),
    )
    req = ArmWarmupRequest(engage_list_id="list_1", warmup_hours=24)
    monkeypatch.delenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", raising=False)
    with pytest.raises(HTTPException) as disabled:
        await arm_warmup_campaign("campaign_1", req, current_user=USER, db=db)
    assert disabled.value.status_code == 403
    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    with pytest.raises(HTTPException) as missing:
        await arm_warmup_campaign("campaign_1", req, current_user=USER, db=db)
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_arming_records_explicit_cohort_and_does_not_launch(monkeypatch):
    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(find_one=AsyncMock(return_value={
            "id": "campaign_1", "status": "draft", "workspace_id": "workspace_1",
            "sender_account_ids": ["sender_1"],
        }), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
        outreach_engage_lists=SimpleNamespace(find_one=AsyncMock(return_value={
            "id": "list_1", "workspace_id": "workspace_1", "campaign_id": None,
        }), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
        outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={
            "nodes": [{"id": "start"}], "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        })),
    )
    result = await arm_warmup_campaign(
        "campaign_1", ArmWarmupRequest(engage_list_id="list_1", warmup_hours=48),
        current_user=USER, db=db,
    )
    assert result["status"] == "warming_up"
    saved = db.outreach_campaigns.update_one.await_args_list[0].args[1]["$set"]
    assert saved["auto_launch_lead_ids"] == ["lead_1"]
    assert saved["auto_launch_enabled"] is False
    assert db.outreach_campaigns.update_one.await_args_list[-1].args[1]["$set"]["auto_launch_enabled"] is True
    assert db.outreach_engage_lists.update_one.await_args.args[1]["$set"]["warmup_hours"] == 48


@pytest.mark.asyncio
async def test_failed_cohort_link_never_leaves_auto_launch_armed(monkeypatch):
    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(
            find_one=AsyncMock(return_value={
                "id": "campaign_1", "status": "draft", "workspace_id": "workspace_1",
                "sender_account_ids": ["sender_1"],
            }), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
        outreach_engage_lists=SimpleNamespace(
            find_one=AsyncMock(return_value={
                "id": "list_1", "workspace_id": "workspace_1", "campaign_id": None,
            }), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=0))),
        outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={
            "nodes": [{"id": "start"}], "updated_at": datetime.now(timezone.utc),
        })),
    )
    with pytest.raises(HTTPException) as error:
        await arm_warmup_campaign(
            "campaign_1", ArmWarmupRequest(engage_list_id="list_1"), current_user=USER, db=db,
        )
    assert error.value.status_code == 409
    updates = db.outreach_campaigns.update_one.await_args_list
    assert updates[0].args[1]["$set"]["auto_launch_enabled"] is False
    assert updates[-1].args[1]["$set"]["status"] == "draft"


@pytest.mark.asyncio
async def test_scheduler_does_nothing_when_conditional_launch_is_disabled(monkeypatch):
    monkeypatch.delenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", raising=False)
    db = SimpleNamespace(outreach_campaigns=SimpleNamespace(find=AsyncMock()))
    result = await _run_warmup_launches(db)
    assert result["disabled"] is True
    db.outreach_campaigns.find.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_never_launches_before_all_leads_are_ready(monkeypatch):
    from unittest.mock import patch

    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    campaign = {"id": "campaign_1", "workspace_id": "workspace_1", "status": "warming_up",
                "auto_launch_enabled": True, "auto_launch_claim_id": "claim_1"}
    db = SimpleNamespace(outreach_campaigns=SimpleNamespace(
        find=lambda query: Cursor([campaign]),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        find_one=AsyncMock(return_value=campaign),
    ))
    with patch("celery_workers.tasks.outreach._evaluate_warmup", new_callable=AsyncMock) as gate, \
         patch("celery_workers.tasks.outreach._launch_campaign_impl", new_callable=AsyncMock) as launch:
        gate.return_value = {"ready": False, "missing_count": 1, "ready_at": None, "linked_lists_count": 1}
        result = await _run_warmup_launches(db)
    assert result["launched"] == 0
    assert result["waiting"] == 1
    assert result["failed"] == 0
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_rechecks_sender_and_uses_shared_launch_validation(monkeypatch):
    from unittest.mock import patch

    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    campaign = {
        "id": "campaign_1", "workspace_id": "workspace_1", "user_id": "owner",
        "status": "warming_up", "auto_launch_enabled": True,
        "auto_launch_lead_ids": ["lead_1"], "auto_launch_sequence_updated_at": stamp,
        "auto_launch_list_id": "list_1", "schedule": {"days": [0]},
    }
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(
            find=lambda query: Cursor([campaign]),
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
            find_one=AsyncMock(return_value=campaign),
        ),
        outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={"updated_at": stamp})),
    )
    with patch("celery_workers.tasks.outreach._evaluate_warmup", new_callable=AsyncMock) as gate, \
         patch("celery_workers.tasks.outreach.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("celery_workers.tasks.outreach._verify_auto_launch_senders", new_callable=AsyncMock) as verify, \
         patch("celery_workers.tasks.outreach._launch_campaign_impl", new_callable=AsyncMock) as launch:
        gate.return_value = {"ready": True, "missing_count": 0, "ready_at": stamp, "linked_lists_count": 1}
        result = await _run_warmup_launches(db)
    assert result["launched"] == 1
    verify.assert_awaited_once()
    launch.assert_awaited_once()
    assert launch.await_args.kwargs["auto_launch_claim_id"]


@pytest.mark.asyncio
async def test_scheduler_waits_outside_working_hours(monkeypatch):
    from unittest.mock import patch

    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    campaign = {
        "id": "campaign_1", "workspace_id": "workspace_1", "status": "warming_up",
        "auto_launch_enabled": True, "auto_launch_list_id": "list_1",
        "schedule": {"days": [0]},
    }
    db = SimpleNamespace(outreach_campaigns=SimpleNamespace(
        find=lambda query: Cursor([campaign]),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        find_one=AsyncMock(return_value=campaign),
    ), outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={"updated_at": None})))
    with patch("celery_workers.tasks.outreach._evaluate_warmup", new_callable=AsyncMock) as gate, \
         patch("celery_workers.tasks.outreach.OutboundRateLimiter.is_within_working_hours", return_value=False), \
         patch("celery_workers.tasks.outreach._verify_auto_launch_senders", new_callable=AsyncMock) as verify, \
         patch("celery_workers.tasks.outreach._launch_campaign_impl", new_callable=AsyncMock) as launch:
        gate.return_value = {"ready": True, "missing_count": 0, "ready_at": datetime.now(timezone.utc), "linked_lists_count": 1}
        result = await _run_warmup_launches(db)
    assert result["launched"] == 0
    assert result["waiting"] == 1
    assert result["failed"] == 0
    verify.assert_not_awaited()
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sender_verification_error_does_not_expose_proxy_secrets(monkeypatch, caplog):
    from unittest.mock import patch

    monkeypatch.setenv("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", "true")
    stamp = datetime.now(timezone.utc) - timedelta(days=1)
    campaign = {
        "id": "campaign_1", "workspace_id": "workspace_1", "user_id": "owner",
        "status": "warming_up", "auto_launch_enabled": True, "auto_launch_list_id": "list_1",
        "auto_launch_lead_ids": ["lead_1"], "auto_launch_sequence_updated_at": stamp,
    }
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(
            find=lambda query: Cursor([campaign]),
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
            find_one=AsyncMock(return_value=campaign),
        ),
        outreach_leads=SimpleNamespace(find=lambda query: Cursor([{"id": "lead_1"}])),
        outreach_sequences=SimpleNamespace(find_one=AsyncMock(return_value={"updated_at": stamp})),
    )
    with patch("celery_workers.tasks.outreach._evaluate_warmup", new_callable=AsyncMock) as gate, \
         patch("celery_workers.tasks.outreach.OutboundRateLimiter.is_within_working_hours", return_value=True), \
         patch("celery_workers.tasks.outreach._verify_auto_launch_senders", new_callable=AsyncMock) as verify:
        gate.return_value = {"ready": True, "missing_count": 0, "ready_at": stamp, "linked_lists_count": 1}
        verify.side_effect = RuntimeError("proxy://user:secret@example.com")
        result = await _run_warmup_launches(db)
    assert result["failed"] == 1
    visible_errors = [call.args[1].get("$set", {}).get("auto_launch_error", "")
                      for call in db.outreach_campaigns.update_one.await_args_list]
    assert all("secret" not in error for error in visible_errors)
    assert "secret" not in caplog.text
