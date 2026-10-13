"""Native Mongo cohort scope, provenance and API/CSV checks; no provider."""
import csv
from datetime import timedelta
import io
import os

import pytest

from outreach.api import analytics
from outreach.core.linkedin_reporting import linkedin_cohort_report
from tests.linkedin_reporting_fixtures import clock, intent, observation
from tests.outreach_native import replica_server, replica_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo is opt-in")]
USER = {"user_id": "actor", "default_workspace_id": "w"}


async def seed(db, kind="send_message"):
    now = clock(); row = intent(now, kind)
    await db.outreach_intents.insert_one(row)
    await db.outreach_event_outbox.insert_one(observation(row, now))
    return now, row


async def report(db, now, **kwargs):
    return await linkedin_cohort_report(db, workspace="w", campaign="c", sender="s",
        start=now - timedelta(days=7), as_of=now, **kwargs)


@pytest.mark.parametrize("field,value", [
    ("workspace_id", "foreign"), ("workspace_id", ["w"]),
    ("campaign_id", "other"), ("campaign_id", ["c"]),
    ("sender_id", "other"), ("sender_id", ["s"]),
])
async def test_native_strict_selected_scope(replica_db, field, value):
    now, _ = await seed(replica_db)
    await replica_db.outreach_intents.update_one({}, {"$set": {field: value}})
    result = await report(replica_db, now)
    assert result["messages"]["denominator"] == 0


@pytest.mark.parametrize("field,value", [
    ("attempt.completed_at", None), ("attempt.completed_at", "2026-10-13"),
    ("attempt.possible_submission_at", None), ("created_at", None),
    ("attempt.outcome", "request_observed"), ("attempt.outcome", "unknown_outcome"),
    ("attempt.provider_result_status", "skipped"), ("attempt.provider_result_status", "confirmed"),
    ("attempt.sender_id", "other"), ("attempt", None),
    ("lead_id", ["l"]), ("action_kind", ["send_message"]),
    ("status", ["executed"]), ("logical_dedup_key", "different"),
    ("sequence_version", True), ("enrollment_id", ["enrollment"]),
    ("resolution", {}), ("resolution", {"decision": "confirmed_sent"}),
    ("resolution", "unproven"), ("resolution", []),
    ("attempt.id", None), ("claim_token", None), ("attempt.owner_token", "replacement"),
    ("legacy_operation_id", "replacement"),
])
async def test_unproven_intent_never_establishes_send_or_rate(replica_db, field, value):
    now, _ = await seed(replica_db)
    await replica_db.outreach_intents.update_one({}, {"$set": {field: value}})
    result = await report(replica_db, now)
    assert result["status"] == "partial" and result["unverified_intents"] == 1
    assert result["messages"]["denominator"] == 0 and result["messages"]["reply_rate"] is None


async def test_human_resolution_and_mutable_task_timestamp_stay_separate(replica_db):
    now, row = await seed(replica_db)
    await replica_db.outreach_intents.update_one({}, {"$set": {"resolution": {"source": "human_assertion"}}})
    await replica_db.outreach_tasks.insert_one({"id": row["legacy_operation_id"], "workspace_id": "w",
        "campaign_id": "c", "lead_id": "l", "account_id": "s", "task_type": "send_message",
        "status": "completed", "updated_at": now})
    result = await report(replica_db, now)
    assert result["human_reported"] == result["unverified_task_records"] == 1
    assert result["messages"]["denominator"] == 0 and result["messages"]["reply_rate"] is None


@pytest.mark.parametrize("status", ["preparing", "dispatching", "uncertain", "resolving"])
async def test_older_unproven_task_history_keeps_rates_unavailable(replica_db, status):
    now, _ = await seed(replica_db)
    await replica_db.outreach_tasks.insert_one({"id": "older:send", "workspace_id": "w", "campaign_id": "c",
        "account_id": "s", "task_type": "send_message", "status": status})
    result = await report(replica_db, now)
    assert result["status"] == "partial" and result["unverified_task_records"] == 1
    assert result["messages"]["denominator"] == 1 and result["messages"]["reply_rate"] is None


@pytest.mark.parametrize("field,value", [
    ("payload.workspace_id", "foreign"), ("payload.id", "replacement"),
    ("payload.type", "lead.connection_accepted"), ("payload.occurred_at", "bad"),
    ("payload.data.lead_id", ["l"]), ("payload.data.sender_account_id", ["s"]),
    ("payload.data.campaign_id", ["c"]), ("type", ["lead.replied"]),
    ("aggregate_id", ["l"]), ("occurred_at", None),
    ("payload.data.channel", None), ("payload.data.channel", ["linkedin"]),
])
async def test_malformed_observation_never_counts(replica_db, field, value):
    now, _ = await seed(replica_db)
    await replica_db.outreach_event_outbox.update_one({}, {"$set": {field: value}})
    result = await report(replica_db, now)
    assert result["messages"]["replied"] == 0
    assert result["status"] == "partial" and result["messages"]["reply_rate"] is None


@pytest.mark.parametrize("field,value", [
    ("workspace_id", "foreign"), ("workspace_id", ["w"]),
    ("payload.data.channel", "email"), ("payload.data.sender_account_id", "other"),
    ("payload.data.campaign_id", "other"), ("payload.data.lead_id", "other"),
])
async def test_foreign_or_email_observations_do_not_supply_linkedin_outcomes(replica_db, field, value):
    now, _ = await seed(replica_db)
    await replica_db.outreach_event_outbox.update_one({}, {"$set": {field: value}})
    result = await report(replica_db, now)
    assert result["messages"]["denominator"] == 1 and result["messages"]["replied"] == 0


async def test_native_original_first_before_period_and_delayed_projection_repairs(replica_db):
    now, row = await seed(replica_db)
    old = intent(now, node="original", age=20)
    await replica_db.outreach_intents.insert_one(old)
    await replica_db.outreach_tasks.insert_one({"id": old["legacy_operation_id"], "workspace_id": "w",
        "campaign_id": "c", "lead_id": "l", "account_id": "s", "task_type": "send_message",
        "status": "completed", "updated_at": now})
    result = await report(replica_db, now)
    assert result["status"] == "recorded" and result["messages"]["denominator"] == 0


async def test_denominator_survives_lead_deletion_or_reassignment(replica_db):
    now, _ = await seed(replica_db)
    await replica_db.outreach_leads.insert_one({"id": "l", "workspace_id": "w", "assigned_account_id": "replacement"})
    result = await report(replica_db, now)
    assert result["messages"]["denominator"] == result["messages"]["replied"] == 1
    await replica_db.outreach_leads.delete_many({})
    assert (await report(replica_db, now))["messages"] == result["messages"]


async def test_multi_sender_and_campaign_identity_never_crossjoins(replica_db):
    now, _ = await seed(replica_db)
    other = intent(now, node="other", sender="other")
    await replica_db.outreach_intents.insert_one(other)
    result = await linkedin_cohort_report(replica_db, workspace="w", campaign="all", sender="all",
        start=now - timedelta(days=7), as_of=now)
    assert result["messages"]["denominator"] == 2 and result["messages"]["replied"] == 1
    assert result["messages"]["reply_rate"] == 50


async def test_bson_millisecond_envelope_preserves_original_observation(replica_db):
    now, row = await seed(replica_db)
    at = now.replace(microsecond=123456)
    await replica_db.outreach_event_outbox.delete_many({})
    await replica_db.outreach_event_outbox.insert_one(observation(row, at))
    result = await report(replica_db, now + timedelta(seconds=1))
    assert result["status"] == "recorded" and result["messages"]["replied"] == 1


async def test_api_and_csv_separate_period_activity_and_original_cohort(replica_db):
    now, row = await seed(replica_db, "connection_request")
    await replica_db.outreach_campaigns.insert_one({"id": "c", "workspace_id": "w"})
    await replica_db.outreach_accounts.insert_one({"id": "s", "workspace_id": "w", "status": "active"})
    await replica_db.outreach_tasks.insert_one({"id": row["legacy_operation_id"], "workspace_id": "w",
        "campaign_id": "c", "lead_id": "l", "account_id": "s", "task_type": "connection_request",
        "status": "completed", "updated_at": now})
    await replica_db.outreach_leads.insert_many([{"id": name, "workspace_id": "w", "campaign_id": "c",
        "assigned_account_id": "s", "is_connected": True, "accepted_at": now} for name in ("old1", "old2")])
    before = {name: await replica_db[name].find({}).to_list(length=100) for name in await replica_db.list_collection_names()}
    result = await analytics.get_outreach_analytics(campaign_id="c", sender_account_id="s", timeframe="7d", current_user=USER, db=replica_db)
    assert result["kpis"]["requests"]["period_activity"] == {"sent": 1, "accepted": 2}
    assert result["kpis"]["requests"]["acceptance_rate"] == 100
    response = await analytics.export_outreach_analytics(campaign_id="c", sender_account_id="s", timeframe="7d", current_user=USER, db=replica_db)
    content = "".join([part.decode() if isinstance(part, bytes) else part async for part in response.body_iterator])
    rows = list(csv.DictReader(io.StringIO(content)))
    assert len(rows) == 7
    assert all(day["linkedin_request_cohort_rate"] == "100.0" for day in rows)
    assert all(day["linkedin_cohort_status"] == "recorded" for day in rows)
    assert all(day["linkedin_summary_scope"] == "selected_period_summary_repeated_on_each_daily_row" for day in rows)
    after = {name: await replica_db[name].find({}).to_list(length=100) for name in await replica_db.list_collection_names()}
    assert after == before
