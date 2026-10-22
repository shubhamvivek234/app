"""Bounded observations associated with original, recorded LinkedIn sends."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.authorization import canonical_hash
from outreach.core.workspace_scope import workspace_scope

logger = logging.getLogger(__name__)
MAX_TASKS = 10_000
MAX_INTENTS = 10_000
MAX_EVENTS = 20_000
READ_SECONDS = 10
ATTRIBUTION_DAYS = 30
BASIS = "first_recorded_provider_acceptance_per_campaign_lead_sender_action"
OUTCOME_BASIS = "stored_linkedin_outbox_observation_time_association"
KINDS = {"connection_request": ("requests", "invite_sent", "lead.connection_accepted"),
         "send_message": ("messages", "message_sent", "lead.replied")}


def _date(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 200


def _scope(workspace: str, campaign: str | None, sender: str | None, sender_field: str) -> dict:
    query = workspace_scope(workspace)
    for field, selected in (("campaign_id", campaign), (sender_field, sender)):
        if selected and selected != "all":
            query.update({field: selected, field + ".0": {"$exists": False}})
    return query


async def _rows(collection, query: dict, fields: tuple[str, ...] | dict, maximum: int) -> list[dict]:
    projection = fields if isinstance(fields, dict) else {field: 1 for field in fields}
    rows = await collection.find(query, projection).limit(maximum + 1).to_list(length=maximum + 1)
    if not isinstance(rows, list) or len(rows) > maximum or any(not isinstance(row, dict) for row in rows):
        raise ValueError("LinkedIn reporting capacity or source contract exceeded")
    return rows


def _result(start: datetime, as_of: datetime, days: int, available: bool) -> dict:
    count = 0 if available else None
    result = {"basis": BASIS, "outcome_basis": OUTCOME_BASIS, "attribution_window_days": days,
        "period_start": start.isoformat(), "as_of": as_of.isoformat(),
        "status": "recorded" if available else "unavailable",
        "unverified_intents": count, "unverified_task_records": count, "unverified_events": count,
        "human_reported": count,
        "message": "Recorded observations associated by campaign, lead and sender; this does not prove causation or provider outcome time."}
    for group, outcome, rate in (("requests", "accepted", "acceptance_rate"), ("messages", "replied", "reply_rate")):
        result[group] = {"denominator": count, outcome: count, rate: None,
                         "matured_denominator": count, "open_window_denominator": count}
    return result


async def _build(db: AsyncIOMotorDatabase, workspace: str, campaign: str | None, sender: str | None,
                 start: datetime, as_of: datetime, days: int) -> dict:
    result = _result(start, as_of, days, True)
    intents = await _rows(db.outreach_intents, {**_scope(workspace, campaign, sender, "sender_id"),
        "action_kind": {"$in": list(KINDS)}},
        {**{field: 1 for field in ("_id", "workspace_id", "campaign_id", "sender_id", "lead_id", "action_kind", "enrollment_id",
         "sequence_version", "node_id", "logical_dedup_key", "legacy_operation_id", "created_at", "status",
         "claim_token", "attempt.id", "attempt.owner_token",
         "resolution.source", "attempt.sender_id", "attempt.possible_submission_at", "attempt.completed_at",
         "attempt.outcome", "attempt.provider_result_status")},
         "_resolution_type": {"$type": "$resolution"}}, MAX_INTENTS)
    first: dict[tuple[str, str, str, str], datetime] = {}
    task_bindings: set[tuple[str, str, str, str, str]] = set()
    for intent in intents:
        kind = intent.get("action_kind")
        if not isinstance(kind, str) or kind not in KINDS:
            result["unverified_intents"] += 1
            continue
        attempt = intent.get("attempt")
        if (intent.get("_resolution_type") not in (None, "missing", "null")
                or "resolution" in intent and intent["resolution"] is not None):
            marker = intent.get("resolution")
            result["human_reported" if isinstance(marker, dict) and marker.get("source") == "human_assertion"
                   else "unverified_intents"] += 1
            continue
        if intent.get("status") in ("pending", "claimed", "failed", "canceled") and not attempt:
            continue
        fields = tuple(intent.get(field) for field in ("campaign_id", "lead_id", "sender_id", "enrollment_id", "node_id", "legacy_operation_id"))
        version = intent.get("sequence_version")
        valid = (intent.get("workspace_id") == workspace and all(_identity(value) for value in fields)
                 and type(version) is int and version >= 1 and isinstance(attempt, dict))
        if valid:
            campaign_id, lead_id, sender_id, enrollment, node, operation = fields
            expected = canonical_hash([workspace, enrollment, version, node, kind])
            created = _date(intent.get("created_at"))
            possible = _date(attempt.get("possible_submission_at"))
            at = _date(attempt.get("completed_at"))
            valid = (intent.get("_id") == intent.get("logical_dedup_key") == expected
                and intent.get("status") == "executed" and attempt.get("sender_id") == sender_id
                and _identity(attempt.get("id")) and _identity(intent.get("claim_token"))
                and attempt.get("owner_token") == intent["claim_token"]
                and operation == f"{lead_id}:{node}"
                and attempt.get("outcome") == "provider_accepted"
                and attempt.get("provider_result_status") == KINDS[kind][1]
                and created is not None and possible is not None and at is not None
                and created <= possible <= at <= as_of)
        if not valid:
            result["unverified_intents"] += 1
            continue
        # Select the lifetime minimum BEFORE selecting the period. A follow-up
        # or reenrollment never resets this recipient/sender/campaign cohort.
        key = (campaign_id, lead_id, sender_id, kind)
        first[key] = min(at, first.get(key, at))
        task_bindings.add((campaign_id, lead_id, sender_id, operation, kind))

    tasks = await _rows(db.outreach_tasks, {
        **_scope(workspace, campaign, sender, "account_id"),
        "task_type": {"$in": list(KINDS)}, "status": {"$in": ["completed", "accepted", "provider_accepted",
            "preparing", "dispatching", "uncertain", "resolving"]}},
        ("id", "campaign_id", "lead_id", "account_id", "task_type", "status"), MAX_TASKS)
    for task in tasks:
        binding = tuple(task.get(field) for field in ("campaign_id", "lead_id", "account_id", "id", "task_type"))
        if (not all(_identity(value) for value in binding) or binding not in task_bindings
                or not isinstance(task.get("task_type"), str) or task["task_type"] not in KINDS
                or not isinstance(task.get("status"), str)):
            result["unverified_task_records"] += 1

    cohort = {key: at for key, at in first.items() if start <= at <= as_of}
    outcomes: set[tuple[str, str, str, str]] = set()
    if cohort:
        event_query = {**workspace_scope(workspace), "type": {"$in": [item[2] for item in KINDS.values()]},
                       "aggregate_id": {"$in": list({key[1] for key in cohort})}}
        events = await _rows(db.outreach_event_outbox, event_query,
            ("id", "workspace_id", "type", "aggregate_id", "occurred_at", "payload.id", "payload.type",
             "payload.workspace_id", "payload.occurred_at", "payload.data.channel", "payload.data.lead_id",
             "payload.data.campaign_id", "payload.data.sender_account_id"), MAX_EVENTS)
        for event in events:
            payload = event.get("payload")
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                result["unverified_events"] += 1
                continue
            event_type = event.get("type")
            kind = next((name for name, values in KINDS.items() if event_type == values[2]), None)
            references = tuple(data.get(field) for field in ("campaign_id", "lead_id", "sender_account_id"))
            if not all(_identity(value) for value in references) or not kind:
                result["unverified_events"] += 1
                continue
            key = (*references, kind)
            if key not in cohort:
                continue
            if not _identity(data.get("channel")):
                result["unverified_events"] += 1
                continue
            if data["channel"] != "linkedin":
                continue
            at = _date(event.get("occurred_at"))
            envelope_at = None
            if isinstance(payload.get("occurred_at"), str):
                try:
                    envelope_at = _date(datetime.fromisoformat(payload["occurred_at"]))
                    envelope_at = envelope_at.replace(microsecond=envelope_at.microsecond // 1000 * 1000)
                except ValueError as exc:
                    logger.debug("LinkedIn reporting event occurred_at parse rejected for event=%s (%s)", event.get("id"), type(exc).__name__)
            if (not _identity(event.get("id")) or event.get("workspace_id") != workspace
                    or event.get("aggregate_id") != references[1]
                    or payload.get("workspace_id") != workspace or payload.get("type") != event_type
                    or payload.get("id") != event["id"] or not at
                    or envelope_at != at.replace(microsecond=at.microsecond // 1000 * 1000)):
                result["unverified_events"] += 1
                continue
            if cohort[key] <= at <= min(as_of, cohort[key] + timedelta(days=days)):
                outcomes.add(key)

    for key, at in cohort.items():
        group = result[KINDS[key[3]][0]]
        group["denominator"] += 1
        group["accepted" if key[3] == "connection_request" else "replied"] += int(key in outcomes)
        group["matured_denominator" if at + timedelta(days=days) <= as_of else "open_window_denominator"] += 1
    partial = any(result[key] for key in ("unverified_intents", "unverified_task_records", "unverified_events", "human_reported"))
    if partial:
        result["status"] = "partial"
        result["message"] += " Some selected history is unproven; rates are unavailable and counts cover usable records only."
    else:
        for group_name, outcome, rate in (("requests", "accepted", "acceptance_rate"), ("messages", "replied", "reply_rate")):
            group = result[group_name]
            if group["denominator"]:
                group[rate] = round(group[outcome] / group["denominator"] * 100, 1)
    return result


async def linkedin_cohort_report(db: AsyncIOMotorDatabase, *, workspace: str, campaign: str | None, sender: str | None,
                                 start: datetime, as_of: datetime, attribution_days: int = ATTRIBUTION_DAYS) -> dict:
    """Observe recorded history without repair, grants, secrets or transport."""
    if type(attribution_days) is not int or not 1 <= attribution_days <= 90:
        raise ValueError("attribution_days must be between 1 and 90")
    start, as_of = _date(start), _date(as_of)
    if not start or not as_of or start > as_of:
        raise ValueError("valid UTC cohort bounds are required")
    try:
        return await asyncio.wait_for(_build(db, workspace, campaign, sender, start, as_of, attribution_days), READ_SECONDS)
    except Exception as exc:
        logger.warning("LinkedIn reporting unavailable (%s)", type(exc).__name__)
        return _result(start, as_of, attribution_days, False)
