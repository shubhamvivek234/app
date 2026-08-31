import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator

from api.deps import CurrentUser, DB, require_permission
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["user-webhooks"])

_MAX_WEBHOOKS_PER_WORKSPACE = 15
_SUPPORTED_EVENTS = {
    "post.published",
    "post.failed",
    "post.dlq",
    "post.scheduled",
    "post.cancelled",
    "account.disconnected",
    "post.approval_requested",
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
    signing_secret: str | None = None
    last_delivery_status: int | None = None
    last_delivery_at: datetime | None = None


class TestWebhookResponse(BaseModel):
    success: bool
    status_code: int | None = None
    latency_ms: int
    response_preview: str
    error: str | None = None


class WebhookDeliveryItem(BaseModel):
    id: str
    event: str
    status_code: int | None
    latency_ms: int
    success: bool
    timestamp: datetime
    error: str | None = None


# ── Helper formatters for Slack / Discord ─────────────────────────────────────

def _is_slack_webhook(url: str) -> bool:
    return "hooks.slack.com" in url


def _is_discord_webhook(url: str) -> bool:
    return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


def _format_slack_payload(event: str, payload: dict) -> dict:
    title = payload.get("title") or payload.get("content", "Social Post")[:60]
    platforms = ", ".join(payload.get("platforms", [])) or "All connected"
    status_emoji = "🚀" if "published" in event else "⚠️" if "failed" in event else "📅"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{status_emoji} Unravler: {event}", "emoji": True}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Post:* {title}\n*Platforms:* {platforms}\n*Status:* `{payload.get('status', 'processed')}`"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Event ID: `{payload.get('post_id', 'evt_test')}` | Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    }
                ]
            }
        ]
    }


def _format_discord_payload(event: str, payload: dict) -> dict:
    title = payload.get("title") or payload.get("content", "Social Post")[:60]
    platforms = ", ".join(payload.get("platforms", [])) or "All connected"
    color = 0x10B981 if "published" in event else 0xEF4444 if "failed" in event else 0x6366F1

    return {
        "embeds": [
            {
                "title": f"Unravler: {event}",
                "description": f"**Post:** {title}\n**Platforms:** {platforms}\n**Status:** `{payload.get('status', 'processed')}`",
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Unravler Social Automation"}
            }
        ]
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/webhooks/endpoints",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("webhook:manage")],
)
async def register_webhook(
    body: WebhookEndpointCreate,
    current_user: CurrentUser,
    db: DB,
) -> WebhookEndpointResponse:
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    count = await db.webhook_endpoints.count_documents(
        {"workspace_id": workspace_id, "active": True}
    )
    if count >= _MAX_WEBHOOKS_PER_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {_MAX_WEBHOOKS_PER_WORKSPACE} active webhook endpoints per workspace",
        )

    signing_secret = f"whsec_{secrets.token_hex(24)}"
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
        "last_delivery_status": None,
        "last_delivery_at": None,
    }
    await db.webhook_endpoints.insert_one(doc)

    logger.info(
        "Webhook endpoint registered: workspace=%s url=%s events=%s",
        workspace_id, str(body.url), body.events,
    )

    # Return signing_secret strictly in creation response so user can store it
    return WebhookEndpointResponse(
        id=str(doc["_id"]),
        url=str(body.url),
        events=body.events,
        description=body.description,
        created_at=now,
        active=True,
        signing_secret=signing_secret,
        last_delivery_status=None,
        last_delivery_at=None,
    )


@router.get("/webhooks/endpoints", response_model=list[WebhookEndpointResponse],
            dependencies=[require_permission("webhook:manage")])
async def list_webhooks(current_user: CurrentUser, db: DB) -> list[WebhookEndpointResponse]:
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.webhook_endpoints.find(
        {"workspace_id": workspace_id, "active": True},
        {"signing_secret_hash": 0},
    ).sort("created_at", -1)
    docs = await cursor.to_list(length=_MAX_WEBHOOKS_PER_WORKSPACE)
    return [
        WebhookEndpointResponse(
            id=str(d["_id"]),
            url=d["url"],
            events=d.get("events", []),
            description=d.get("description", ""),
            created_at=d["created_at"],
            active=d.get("active", True),
            signing_secret=None,
            last_delivery_status=d.get("last_delivery_status"),
            last_delivery_at=d.get("last_delivery_at"),
        )
        for d in docs
    ]


@router.delete("/webhooks/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("webhook:manage")])
async def delete_webhook(
    endpoint_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    from bson import ObjectId
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(endpoint_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    result = await db.webhook_endpoints.update_one(
        {"_id": oid, "workspace_id": workspace_id},
        {"$set": {"active": False, "deleted_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


@router.post("/webhooks/endpoints/{endpoint_id}/test", response_model=TestWebhookResponse,
             dependencies=[require_permission("webhook:manage")])
async def test_webhook_endpoint(
    endpoint_id: str,
    current_user: CurrentUser,
    db: DB,
) -> TestWebhookResponse:
    """Send an immediate test event payload to verify endpoint connectivity."""
    import httpx
    from bson import ObjectId

    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(endpoint_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    endpoint = await db.webhook_endpoints.find_one({"_id": oid, "workspace_id": workspace_id, "active": True})
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    url = endpoint.get("url", "")
    if not is_safe_url(url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe webhook destination")

    sample_event = endpoint.get("events", ["post.published"])[0]
    sample_payload = {
        "event": sample_event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_id": workspace_id,
        "data": {
            "post_id": f"test_{int(time.time())}",
            "title": "🎉 Test Webhook Delivery from Unravler",
            "content": "This is a verified test event dispatched from Unravler Webhooks engine.",
            "status": "published",
            "platforms": ["instagram", "linkedin", "twitter"],
            "published_at": datetime.now(timezone.utc).isoformat(),
            "is_test": True,
        }
    }

    headers = {"Content-Type": "application/json"}
    if _is_slack_webhook(url):
        req_body = json.dumps(_format_slack_payload(sample_event, sample_payload["data"])).encode("utf-8")
    elif _is_discord_webhook(url):
        req_body = json.dumps(_format_discord_payload(sample_event, sample_payload["data"])).encode("utf-8")
    else:
        req_body = json.dumps(sample_payload).encode("utf-8")
        secret = endpoint.get("signing_secret_hash", "")
        sig = "sha256=" + hmac.new(secret.encode(), req_body, hashlib.sha256).hexdigest()
        headers["X-Unravler-Signature"] = sig
        headers["X-Unravler-Event"] = sample_event

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=req_body, headers=headers)
            latency = int((time.time() - start_time) * 1000)

            # Record in delivery history
            now = datetime.now(timezone.utc)
            await db.webhook_deliveries.insert_one({
                "_id": ObjectId(),
                "endpoint_id": endpoint_id,
                "workspace_id": workspace_id,
                "event": sample_event,
                "status_code": resp.status_code,
                "latency_ms": latency,
                "success": resp.status_code < 400,
                "timestamp": now,
                "error": None if resp.status_code < 400 else f"HTTP {resp.status_code}",
            })
            await db.webhook_endpoints.update_one(
                {"_id": oid},
                {"$set": {"last_delivery_status": resp.status_code, "last_delivery_at": now}},
            )

            return TestWebhookResponse(
                success=resp.status_code < 400,
                status_code=resp.status_code,
                latency_ms=latency,
                response_preview=resp.text[:300] if resp.text else "No response body",
                error=None if resp.status_code < 400 else f"Target returned status {resp.status_code}",
            )
    except Exception as exc:
        latency = int((time.time() - start_time) * 1000)
        return TestWebhookResponse(
            success=False,
            status_code=None,
            latency_ms=latency,
            response_preview="",
            error=str(exc),
        )


@router.get("/webhooks/endpoints/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryItem],
            dependencies=[require_permission("webhook:manage")])
async def get_webhook_deliveries(
    endpoint_id: str,
    current_user: CurrentUser,
    db: DB,
) -> list[WebhookDeliveryItem]:
    """Retrieve recent delivery logs for an endpoint."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.webhook_deliveries.find(
        {"endpoint_id": endpoint_id, "workspace_id": workspace_id}
    ).sort("timestamp", -1).limit(20)
    docs = await cursor.to_list(length=20)
    return [
        WebhookDeliveryItem(
            id=str(d["_id"]),
            event=d.get("event", "event"),
            status_code=d.get("status_code"),
            latency_ms=d.get("latency_ms", 0),
            success=d.get("success", False),
            timestamp=d.get("timestamp", datetime.now(timezone.utc)),
            error=d.get("error"),
        )
        for d in docs
    ]


# ── Outbound delivery helper (called from Celery & API pipelines) ────────────

async def dispatch_webhook_event(db, workspace_id: str, event: str, payload: dict) -> None:
    """
    Fetch all active endpoints subscribed to `event` and fire signed POSTs.
    Supports Slack blocks and Discord embeds automatically.
    """
    import httpx
    from bson import ObjectId

    if not workspace_id:
        return

    cursor = db.webhook_endpoints.find(
        {"workspace_id": workspace_id, "active": True, "events": event},
    )
    endpoints = await cursor.to_list(length=_MAX_WEBHOOKS_PER_WORKSPACE)
    if not endpoints:
        return

    now = datetime.now(timezone.utc)
    full_event_data = {
        "event": event,
        "timestamp": now.isoformat(),
        "workspace_id": workspace_id,
        "data": payload,
    }

    for endpoint in endpoints:
        url = endpoint.get("url", "")
        if not url or not is_safe_url(url):
            continue

        endpoint_id = str(endpoint["_id"])
        headers = {"Content-Type": "application/json"}

        if _is_slack_webhook(url):
            body_bytes = json.dumps(_format_slack_payload(event, payload)).encode("utf-8")
        elif _is_discord_webhook(url):
            body_bytes = json.dumps(_format_discord_payload(event, payload)).encode("utf-8")
        else:
            body_bytes = json.dumps(full_event_data).encode("utf-8")
            secret = endpoint.get("signing_secret_hash", "")
            sig = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Unravler-Signature"] = sig
            headers["X-Unravler-Event"] = event

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
                latency = int((time.time() - start_time) * 1000)

                await db.webhook_deliveries.insert_one({
                    "_id": ObjectId(),
                    "endpoint_id": endpoint_id,
                    "workspace_id": workspace_id,
                    "event": event,
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "success": resp.status_code < 400,
                    "timestamp": now,
                    "error": None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                })
                await db.webhook_endpoints.update_one(
                    {"_id": endpoint["_id"]},
                    {"$set": {"last_delivery_status": resp.status_code, "last_delivery_at": now}},
                )
        except Exception as exc:
            latency = int((time.time() - start_time) * 1000)
            logger.warning("Webhook dispatch failed to %s: %s", url[:80], exc)
            try:
                await db.webhook_deliveries.insert_one({
                    "_id": ObjectId(),
                    "endpoint_id": endpoint_id,
                    "workspace_id": workspace_id,
                    "event": event,
                    "status_code": None,
                    "latency_ms": latency,
                    "success": False,
                    "timestamp": now,
                    "error": str(exc),
                })
            except Exception:
                pass


# ── Inbound Webhooks (n8n, Make.com, Zapier, Custom Automation) ──────────────

class InboundPostRequest(BaseModel):
    content: str
    title: str | None = None
    platforms: list[str] | None = None
    media_urls: list[str] | None = None
    scheduled_time: str | None = None
    first_comment: str | None = None
    publish_now: bool = False
    timezone: str = "UTC"


@router.post("/webhooks/inbound/post", status_code=status.HTTP_201_CREATED)
async def inbound_create_post(
    body: InboundPostRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Inbound webhook trigger for low-code automation (n8n, Make.com, Zapier).
    Instantly drafts or schedules a post across connected platforms.
    """
    from bson import ObjectId
    from api.task_queue import enqueue_task

    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)

    # Resolve platforms (fallback to all connected accounts if not specified)
    platforms = body.platforms
    if not platforms:
        accounts = await db.social_accounts.find(
            {"user_id": user_id, "is_active": True},
            {"platform": 1, "account_id": 1}
        ).to_list(length=50)
        platforms = list(set([acc["platform"] for acc in accounts if acc.get("platform")]))

    if not platforms:
        platforms = ["twitter"]

    post_status = "scheduled" if (body.scheduled_time and not body.publish_now) else "draft"
    if body.publish_now:
        post_status = "queued"

    scheduled_dt = None
    if body.scheduled_time:
        try:
            scheduled_dt = datetime.fromisoformat(body.scheduled_time.replace("Z", "+00:00"))
        except Exception:
            scheduled_dt = None

    post_id = str(ObjectId())
    doc = {
        "id": post_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "content": body.content,
        "title": body.title,
        "platforms": platforms,
        "media_urls": body.media_urls or [],
        "scheduled_time": scheduled_dt,
        "timezone": body.timezone,
        "status": post_status,
        "first_comment": body.first_comment,
        "first_comment_enabled": bool(body.first_comment),
        "first_comment_status": None,
        "platform_results": {p: {"status": "pending"} for p in platforms},
        "status_history": [{"status": post_status, "timestamp": now, "actor": "inbound_webhook"}],
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }

    await db.posts.insert_one(doc)

    if body.publish_now:
        try:
            enqueue_task(
                "celery_workers.tasks.publish.publish_post",
                kwargs={"post_id": post_id, "version": 1},
                queue="high_priority",
            )
        except Exception as exc:
            logger.warning("Failed to enqueue publish for inbound webhook: %s", exc)

    return {
        "success": True,
        "post_id": post_id,
        "status": post_status,
        "platforms": platforms,
        "created_at": now.isoformat(),
    }

