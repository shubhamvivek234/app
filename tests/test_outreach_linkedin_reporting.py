"""Cohort calculations and unavailable states, with fake read-only sources."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from outreach.core import linkedin_reporting as reporting
from tests.linkedin_reporting_fixtures import clock, intent, observation
from tests.outreach_memory import Database

pytestmark = pytest.mark.asyncio


async def report(db, now, **kwargs):
    return await reporting.linkedin_cohort_report(db, workspace="w", campaign="c", sender="s",
        start=now - timedelta(days=7), as_of=now, **kwargs)


async def test_lifetime_first_precedes_period_even_when_followup_is_recent():
    now = clock()
    old, followup = intent(now, age=20), intent(now, node="followup", age=1)
    db = Database(outreach_intents=[followup, old], outreach_event_outbox=[observation(old, now)])
    result = await report(db, now)
    assert result["messages"]["denominator"] == result["messages"]["replied"] == 0
    assert result["messages"]["reply_rate"] is None


async def test_original_provider_confirmation_survives_repaired_task_and_missing_lead():
    now = clock(); row = intent(now)
    db = Database(outreach_intents=[row], outreach_tasks=[{"id": row["legacy_operation_id"],
        "workspace_id": "w", "campaign_id": "c", "lead_id": "l", "account_id": "s",
        "task_type": "send_message", "status": "completed", "updated_at": now}],
        outreach_event_outbox=[observation(row, now)])
    before = deepcopy(db.collections)
    result = await report(db, now)
    assert result["messages"]["denominator"] == result["messages"]["replied"] == 1
    assert result["messages"]["reply_rate"] == 100
    assert all(collection.docs == before[name].docs for name, collection in db.collections.items() if name in before)


async def test_cross_channel_lead_flags_never_supply_linkedin_outcomes():
    now = clock(); row = intent(now)
    db = Database(outreach_intents=[row], outreach_leads=[{"id": "l", "workspace_id": "w",
        "has_replied": True, "replied_at": now}], outreach_event_outbox=[observation(row, now, channel="email")])
    result = await report(db, now)
    assert result["messages"]["denominator"] == 1
    assert result["messages"]["replied"] == 0


@pytest.mark.parametrize("age,observed_age,expected", [(2, 1, 1), (2, 3, 0), (2, -1, 0), (40, 1, 0), (31, 1, 1)])
async def test_observations_use_send_window_and_fixed_as_of(age, observed_age, expected):
    now = clock(); row = intent(now, age=age)
    result = await reporting.linkedin_cohort_report(Database(outreach_intents=[row],
        outreach_event_outbox=[observation(row, now - timedelta(days=observed_age))]),
        workspace="w", campaign="c", sender="s", start=now - timedelta(days=60), as_of=now)
    assert result["messages"]["replied"] == expected
    assert result["messages"]["matured_denominator"] == int(age >= 30)


async def test_repeated_sends_and_events_do_not_duplicate_denominator_or_outcome():
    now = clock(); row = intent(now)
    result = await report(Database(outreach_intents=[row, intent(now, node="followup", age=1)],
        outreach_event_outbox=[observation(row, now), observation(row, now, key="evt_duplicate")]), now)
    assert result["messages"]["denominator"] == result["messages"]["replied"] == 1


@pytest.mark.parametrize("maximum", ["MAX_INTENTS", "MAX_TASKS", "MAX_EVENTS"])
async def test_overflow_returns_null_counts_and_rates(monkeypatch, maximum):
    now = clock(); row = intent(now)
    db = Database(outreach_intents=[row], outreach_tasks=[{"workspace_id": "w", "campaign_id": "c",
        "account_id": "s", "task_type": "send_message", "status": "completed"}],
        outreach_event_outbox=[observation(row, now)])
    monkeypatch.setattr(reporting, maximum, 0)
    result = await report(db, now)
    assert result["status"] == "unavailable" and result["messages"]["denominator"] is None


async def test_read_failure_is_sanitized_and_unavailable(monkeypatch):
    monkeypatch.setattr(reporting, "_build", AsyncMock(side_effect=RuntimeError("sensitive-source-message")))
    result = await report(Database(), clock())
    assert result["status"] == "unavailable"
    assert "sensitive-source-message" not in str(result)


async def test_read_deadline_is_enforced(monkeypatch):
    async def slow(*args):
        await asyncio.sleep(2)
    monkeypatch.setattr(reporting, "_build", slow)
    monkeypatch.setattr(reporting, "READ_SECONDS", 0.01)
    assert (await report(Database(), clock()))["status"] == "unavailable"


@pytest.mark.parametrize("days", [0, 91, True, "30"])
async def test_invalid_window_denies(days):
    with pytest.raises(ValueError):
        await report(Database(), clock(), attribution_days=days)


async def test_invalid_bounds_deny():
    now = clock()
    with pytest.raises(ValueError):
        await reporting.linkedin_cohort_report(Database(), workspace="w", campaign=None, sender=None,
            start=now, as_of=now - timedelta(seconds=1))
