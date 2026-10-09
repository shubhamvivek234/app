"""Durable integration delivery entrypoint and conservative legacy quarantine."""
from datetime import datetime, timezone
from typing import Any
import httpx
from outreach.core.integration_delivery import IntegrationDelivery


async def dispatch_due_deliveries(db: Any, *, batch_size: int = 20, lease_seconds: int = 30,
        safe_client: httpx.AsyncClient | None = None, allow_private_for_tests: bool = False) -> dict[str, int]:
    """Discover references; old copied-credential jobs never authorize a new send.

    Legacy parameters stay accepted for existing callers. Current HTTP runs only
    through the prepared adapter; a supplied client cannot bypass its authority.
    """
    old = await db.outreach_webhook_deliveries.update_many({"custody_protocol_version": {"$ne": 2},
        "status": {"$in": ["pending", "retry", "leased"]}}, {"$set": {"status": "review_required",
        "error_sanitized": "Legacy delivery requires drained review", "updated_at": datetime.now(timezone.utc)}})
    counts = await IntegrationDelivery(db).dispatch_due(batch_size=batch_size)
    return {"delivered": counts["delivered"], "retried": counts["retry"],
        "failed": counts["failed"], "dead_letter": 0,
        "review_required": counts["review_required"] + old.modified_count,
        "cancelled": counts["cancelled"]}


async def replay_delivery(db: Any, workspace_id: str, delivery_id: str, actor_id: str) -> dict[str, Any]:
    """Original submission evidence can never be reset into a sendable job."""
    delivery = await db.outreach_webhook_deliveries.find_one({"id": delivery_id, "workspace_id": workspace_id})
    if not delivery:
        raise ValueError("Delivery not found")
    raise ValueError("Original delivery cannot be replayed; review it before a separately authorized request")
