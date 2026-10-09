"""
Transactional Event Outbox Pattern for Outreach Integrations.
Guarantees at-least-once event delivery with atomic persistence and deduplicated fan-out.
"""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import uuid

from pymongo.errors import DuplicateKeyError
from outreach.core.event_definitions import (
    OutboxEventEnvelope,
    WebhookEvent,
    create_event_envelope,
)
from outreach.core.integrations_pilot import is_integrations_pilot_allowed

logger = logging.getLogger(__name__)


async def record_outbox_event(
    db: Any,
    workspace_id: str,
    event_type: WebhookEvent | str,
    aggregate_id: str,
    dedupe_key: str,
    data: dict[str, Any],
    *,
    session: Any = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Persist an event to the transactional outbox collection.
    Deduplication key prevents recording duplicate events for the same source transition.
    Safe to call within a MongoDB multi-document transaction session.
    """
    now = occurred_at or datetime.now(timezone.utc)
    from outreach.core.erasure import workspace_is_open
    if not await workspace_is_open(db, workspace_id):
        raise ValueError("Workspace is closed for erasure")
    type_str = event_type.value if isinstance(event_type, WebhookEvent) else str(event_type)
    event_id = f"evt_{uuid.uuid4().hex}"

    envelope = create_event_envelope(
        workspace_id=workspace_id,
        event_type=type_str,
        data=data,
        event_id=event_id,
        occurred_at=now,
    )

    doc = {
        "id": event_id,
        "workspace_id": workspace_id,
        "dedupe_key": dedupe_key,
        "type": type_str,
        "version": envelope.version,
        "aggregate_id": aggregate_id,
        "occurred_at": now,
        "payload": envelope.model_dump(),
        "status": "pending",  # pending, leased, dispatched
        "lease_id": None,
        "leased_until": None,
        "created_at": now,
        "dispatched_at": None,
    }

    from outreach.core.suppression import SuppressionDatabase
    if isinstance(db, SuppressionDatabase):
        # The workspace guard orders reply writers. Reuse dedup evidence rather
        # than catching a duplicate insert that aborts the enclosing transaction.
        scope = {"workspace_id": workspace_id, "dedupe_key": dedupe_key}
        await db.outreach_event_outbox.update_one(scope, {"$setOnInsert": doc}, upsert=True)
        saved = await db.outreach_event_outbox.find_one(scope)
        if not saved:
            raise RuntimeError("Reply event was not persisted")
        return saved

    try:
        kwargs = {"session": session} if session else {}
        await db.outreach_event_outbox.insert_one(doc, **kwargs)
        return doc
    except DuplicateKeyError:
        logger.info(
            "Outbox event with dedupe_key '%s' already exists in workspace '%s'; returning existing.",
            dedupe_key,
            workspace_id,
        )
        existing = await db.outreach_event_outbox.find_one(
            {"workspace_id": workspace_id, "dedupe_key": dedupe_key},
            session=session,
        )
        return existing or doc


async def scan_and_fanout_outbox(
    db: Any,
    *,
    batch_size: int = 50,
    lease_seconds: int = 60,
) -> dict[str, int]:
    """
    Scan pending outbox events using atomic leases, find matching active
    webhook subscriptions, and idempotently create delivery records.
    """
    now = datetime.now(timezone.utc)
    lease_id = uuid.uuid4().hex
    leased_until = now + timedelta(seconds=lease_seconds)

    dispatched_count = 0
    deliveries_created = 0

    # Find pending or expired-lease outbox events
    query = {
        "$or": [
            {"status": "pending"},
            {"status": "leased", "leased_until": {"$lt": now}},
        ]
    }

    for _ in range(batch_size):
        # Claim event atomically
        event = await db.outreach_event_outbox.find_one_and_update(
            query,
            {"$set": {"status": "leased", "lease_id": lease_id, "leased_until": leased_until}},
        )
        if not event:
            break

        workspace_id = event["workspace_id"]
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(db, workspace_id):
            await db.outreach_event_outbox.update_one({"_id": event["_id"], "workspace_id": workspace_id}, {
                "$set": {"status": "suppressed", "suppressed_reason": "erasure_requested", "resolved_at": now}})
            continue
        if not is_integrations_pilot_allowed(workspace_id):
            await db.outreach_event_outbox.update_one(
                {"_id": event["_id"]},
                {"$set": {"status": "suppressed", "suppressed_reason": "Integrations not enabled for workspace in current pilot", "resolved_at": now}},
            )
            continue

        event_type = event["type"]

        # Query all active webhook endpoints subscribed to this event in the workspace
        cursor = db.outreach_webhooks.find({
            "workspace_id": workspace_id,
            "status": "active",
            "events": event_type,
        })
        active_webhooks = await cursor.to_list(length=100)

        from outreach.core.integration_delivery import IntegrationDelivery
        service = IntegrationDelivery(db)
        for webhook in active_webhooks:
            try:
                delivery = await service.queue(workspace_id, "webhook", webhook["id"],
                    event["id"], event["payload"], expected_source=webhook)
                deliveries_created += int(delivery["newly_queued"])
            except ValueError:
                # A disconnected/changed destination cannot authorize old fanout.
                continue

        # Check active Slack integration fan-out
        slack_doc = None
        if hasattr(db, "outreach_integrations"):
            find_res = db.outreach_integrations.find_one({
                "workspace_id": workspace_id,
                "provider": "slack",
                "status": "connected",
            })
            import inspect
            if inspect.isawaitable(find_res):
                slack_doc = await find_res
            elif isinstance(find_res, dict):
                slack_doc = find_res

        if slack_doc and slack_doc.get("access_token_enc"):
            meta = slack_doc.get("metadata", {})
            should_notify_slack = False
            if event_type == "lead.replied" and meta.get("notify_on_replies", True):
                should_notify_slack = True
            elif event_type == "lead.connection_accepted" and meta.get("notify_on_accepts", True):
                should_notify_slack = True
            elif event_type == "campaign.paused":
                should_notify_slack = True

            if should_notify_slack:
                try:
                    delivery = await service.queue(workspace_id, "slack", "slack", event["id"],
                        event["payload"], expected_source=slack_doc)
                    deliveries_created += int(delivery["newly_queued"])
                except ValueError:
                    pass

        # Mark event as dispatched
        await db.outreach_event_outbox.update_one(
            {"id": event["id"], "workspace_id": workspace_id, "lease_id": lease_id},
            {"$set": {
                "status": "dispatched",
                "dispatched_at": datetime.now(timezone.utc),
                "lease_id": None,
                "leased_until": None,
            }},
        )
        dispatched_count += 1

    return {
        "dispatched_events": dispatched_count,
        "deliveries_created": deliveries_created,
    }
