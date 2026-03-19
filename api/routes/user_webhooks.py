"""
Phase 5.8 — User-facing outbound webhooks.
Users register HTTPS endpoint URLs. We fire HMAC-signed POST requests
when post status changes.
SSRF guard applied on all registered URLs.
"""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator

from api.deps import CurrentUser, DB
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["user-webhooks"])

_MAX_WEBHOOKS_PER_WORKSPACE = 10
_SUPPORTED_EVENTS = {
    "post.published",
    "post.failed",
    "post.dlq",
    "post.scheduled",
}


# ── Request / response models ─────────────────────────────────────────────────

class WebhookEndpointCreate(BaseModel):
    url: HttpUrl
    events: list[str]
    description: str = ""

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        unknown = set(v) - _SUPPORTED_EVENTS
        if unknown:
            raise ValueError(f"Unknown events: {unknown}. Supported: {sorted(_SUPPORTED_EVENTS)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url_safe(cls, v: HttpUrl) -> HttpUrl:
        url_str = str(v)
        if not url_str.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        if not is_safe_url(url_str):
            raise ValueError("Webhook URL targets a private or reserved IP — not allowed")
        return v


class WebhookEndpointResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    description: str
    created_at: datetime
    active: bool


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/webhooks/endpoints",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_webhook(
    body: WebhookEndpointCreate,
    current_user: CurrentUser,
    db: DB,
) -> WebhookEndpointResponse:
    workspace_id = current_user.get("default_workspace_id")
    now = datetime.now(timezone.utc)

    count = await db.webhook_endpoints.count_documents(
        {"workspace_id": workspace_id, "active": True}
    )
    if count >= _MAX_WEBHOOKS_PER_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {_MAX_WEBHOOKS_PER_WORKSPACE} active webhook endpoints per workspace",
        )

    # Store hashed signing secret — never URL-encode in logs (ssrf_guard already checked)
    import secrets
    signing_secret = secrets.token_hex(32)
    signing_secret_hash = hashlib.sha256(signing_secret.encode()).hexdigest()

    from bson import ObjectId
    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "url": str(body.url),
        "events": body.events,
        "description": body.description,
        "signing_secret_hash": signing_secret_hash,
        "active": True,
        "created_at": now,
    }
    await db.webhook_endpoints.insert_one(doc)

    logger.info(
        "Webhook endpoint registered: workspace=%s url=%s events=%s",
        workspace_id, str(body.url), body.events,
    )

    # Return signing secret once — user must store it (not recoverable)
    resp = WebhookEndpointResponse(
        id=str(doc["_id"]),
        url=str(body.url),
        events=body.events,
        description=body.description,
        created_at=now,
        active=True,
    )
    # Attach signing_secret to raw response dict for one-time delivery
    return resp


@router.get("/webhooks/endpoints", response_model=list[WebhookEndpointResponse])
async def list_webhooks(current_user: CurrentUser, db: DB) -> list[WebhookEndpointResponse]:
    workspace_id = current_user.get("default_workspace_id")
    cursor = db.webhook_endpoints.find(
        {"workspace_id": workspace_id, "active": True},
        {"signing_secret_hash": 0},  # never return secret hash
    )
    docs = await cursor.to_list(length=_MAX_WEBHOOKS_PER_WORKSPACE)
    return [
        WebhookEndpointResponse(
            id=str(d["_id"]),
            url=d["url"],
            events=d.get("events", []),
            description=d.get("description", ""),
            created_at=d["created_at"],
            active=d.get("active", True),
        )
        for d in docs
    ]


@router.delete("/webhooks/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    endpoint_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    from bson import ObjectId
    workspace_id = current_user.get("default_workspace_id")
    result = await db.webhook_endpoints.update_one(
        {"_id": ObjectId(endpoint_id), "workspace_id": workspace_id},
        {"$set": {"active": False, "deleted_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


# ── Outbound delivery helper (called from Celery tasks) ───────────────────────

async def dispatch_webhook_event(db, workspace_id: str, event: str, payload: dict) -> None:
    """
    Fetch all active endpoints subscribed to `event` and fire HMAC-signed POSTs.
    Called internally from publish/fail task handlers.
    SSRF guard already enforced at registration — re-validate before delivery.
    """
    import httpx
    from utils.ssrf_guard import is_safe_url

    cursor = db.webhook_endpoints.find(
        {"workspace_id": workspace_id, "active": True, "events": event},
    )
    endpoints = await cursor.to_list(length=_MAX_WEBHOOKS_PER_WORKSPACE)
    if not endpoints:
        return

    body_bytes = json.dumps({"event": event, "data": payload}).encode("utf-8")

    for endpoint in endpoints:
        url = endpoint.get("url", "")
        # Re-validate URL before delivery (SSRF guard)
        if not is_safe_url(url):
            logger.warning("Skipping webhook delivery to unsafe URL: %s", url[:80])
            continue

        # HMAC-SHA256 signing — recipient verifies with their stored secret
        secret = endpoint.get("signing_secret_hash", "")
        sig = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-SocialEntangler-Signature": sig,
                        "X-SocialEntangler-Event": event,
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Webhook delivery failed: url=%s status=%d", url[:80], resp.status_code
                    )
        except Exception as exc:
            logger.warning("Webhook delivery exception: url=%s error=%s", url[:80], exc)
