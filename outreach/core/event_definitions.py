"""
Outreach Event Definitions and Versioned Envelope.
Defines frozen event catalog and structured payload contracts.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class WebhookEvent(str, Enum):
    """
    Frozen catalog of authoritative outreach lifecycle events.
    Do not add unverified, speculative, or inferred event types.
    """
    LEAD_CREATED = "lead.created"
    LEAD_REPLIED = "lead.replied"
    CONNECTION_ACCEPTED = "lead.connection_accepted"
    LEAD_STAGE_CHANGED = "lead.stage_changed"
    CAMPAIGN_PAUSED = "campaign.paused"
    EMAIL_ACCEPTED = "email.accepted"


class OutboxEventEnvelope(BaseModel):
    """
    Standardized, versioned event envelope for external delivery.
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    type: str
    version: int = 1
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    workspace_id: str
    data: dict[str, Any] = Field(default_factory=dict)


def create_event_envelope(
    workspace_id: str,
    event_type: WebhookEvent | str,
    data: dict[str, Any],
    *,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    version: int = 1,
) -> OutboxEventEnvelope:
    """Helper to construct a validated event envelope."""
    type_str = event_type.value if isinstance(event_type, WebhookEvent) else str(event_type)
    ts = (occurred_at or datetime.now(timezone.utc)).isoformat()
    kwargs = {
        "type": type_str,
        "version": version,
        "occurred_at": ts,
        "workspace_id": workspace_id,
        "data": data,
    }
    if event_id:
        kwargs["id"] = event_id
    return OutboxEventEnvelope(**kwargs)
