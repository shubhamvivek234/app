"""
Integrations and Public REST API Router.
Provides customer webhook management, scoped API keys with rate limits and idempotency,
Slack alert integration, and safe public lead ingestion/pause controls.
"""
from datetime import datetime, timezone
import hashlib
import logging
import secrets
import re
from typing import Annotated, Any, Callable
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
import httpx

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core.workspace_scope import workspace_scope
from outreach.core import integration_custody
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.integration_delivery import IntegrationDelivery
from outreach.core.suppression import SuppressionUnavailable
from outreach.core.event_definitions import WebhookEvent
from outreach.core.event_outbox import record_outbox_event
from outreach.core.lead_importer import normalize_linkedin_url, _host_variants
from outreach.core.paid_access import get_active_entitlement
from outreach.core.safe_transport import SSRFSecurityError, validate_webhook_url
from outreach.core.slack_notifier import validate_slack_webhook_url
from outreach.core.crm_sync import (
    FORMULA_INJECTION_PREFIXES,
    sanitize_spreadsheet_value,
    sanitize_row_data,
)
from outreach.core.webhook_delivery import replay_delivery
from outreach.models import LeadExecutionState, OutreachApiKey, OutreachWebhook
from outreach.core.integrations_pilot import is_integrations_pilot_allowed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Outreach Integrations & Webhooks"])
public_router = APIRouter(prefix="/public", tags=["Outreach Public REST API"])

ALLOWED_SCOPES = {"campaigns:read", "leads:read", "leads:write"}
MAX_WEBHOOKS_PER_WORKSPACE = 10
MAX_API_KEYS_PER_WORKSPACE = 10


async def _save_integration(db, workspace, kind, row, value, previous=None, *, actor=None, api_key=None):
    try:
        policy = integration_custody.policy_digest()
        sealed = await integration_custody.seal(value, row, workspace, kind)
        authority = ({"actor": actor, "permission": "webhook:manage" if kind == "webhook" else "outreach:manage"}
                     if actor else {"api_key_id": (api_key or {}).get("key_id"), "key_hash": (api_key or {}).get("key_hash")})
        await integration_custody.save(db, workspace, kind, {**row, **sealed}, previous=previous, policy=policy, authority=authority)
    except (ValueError, SuppressionUnavailable):
        raise HTTPException(409, "Integration configuration could not be saved; reload and try again") from None


async def _queue_integration(db, workspace, kind, destination, actor, *, lead_id=None, request_id=None):
    import uuid
    if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", request_id)):
        raise HTTPException(400, "A valid Idempotency-Key is required")
    event_id = "manual_" + (request_id or uuid.uuid4().hex)
    try:
        job = await IntegrationDelivery(db).queue(workspace, kind, destination, event_id,
            {"type": "crm.contact_sync" if kind == "hubspot" else "system.ping", "workspace_id": workspace, "data": {}}, actor=actor, lead_id=lead_id)
    except (ValueError, SuppressionUnavailable):
        raise HTTPException(409, "Integration is unavailable or has unresolved work; reload its status") from None
    return {"status": "queued", "delivery_id": job["id"]}


async def _disconnect_integration(db, workspace, kind, destination, authority):
    try:
        return await integration_custody.disconnect(db, workspace, kind, destination, authority=authority)
    except (ValueError, SuppressionUnavailable):
        raise HTTPException(409, "Integration permission changed; reload before disconnecting") from None


def _workspace_id(user: dict) -> str:
    workspace_id = user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=403, detail="An active workspace is required")
    ws_str = str(workspace_id)
    if not is_integrations_pilot_allowed(ws_str):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integrations are not enabled for this workspace in the current pilot",
        )
    return ws_str


# ── DTOs ───────────────────────────────────────────────────────────────────

class CreateWebhookRequest(BaseModel):
    target_url: str = Field(..., description="HTTPS endpoint URL to receive webhook payloads")
    events: list[str] = Field(default_factory=lambda: [
        WebhookEvent.LEAD_REPLIED.value,
        WebhookEvent.CONNECTION_ACCEPTED.value,
    ])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    scopes: list[str] = Field(default_factory=lambda: ["leads:write", "campaigns:read"])


class SlackConfigRequest(BaseModel):
    enabled: bool = True
    webhook_url: str = Field(..., description="Slack Incoming Webhook URL")
    channel_name: str = Field(default="#sales-leads")
    notify_on_replies: bool = True
    notify_on_accepts: bool = True
    daily_digest_enabled: bool = False


class PublicLeadEnrollRequest(BaseModel):
    campaign_id: str
    linkedin_url: str
    first_name: str
    last_name: str = ""
    company_name: str = ""
    job_title: str = ""
    email: str | None = None
    custom_variables: dict[str, Any] = Field(default_factory=dict)


class SubscribeRestHookRequest(BaseModel):
    event: str = Field(..., description="Outreach event type to subscribe to (e.g. lead.replied)")
    target_url: str = Field(..., description="HTTPS callback URL provided by Zapier/Make")


class HubSpotConfigRequest(BaseModel):
    access_token: str = Field(..., description="HubSpot Private App Token or OAuth Access Token")
    portal_id: str = Field(..., description="HubSpot Portal / Account ID")
    auto_sync_on_reply: bool = Field(default=False)


class SheetsPreviewRequest(BaseModel):
    campaign_id: str
    rows: list[dict[str, Any]]
    column_mapping: dict[str, str] = Field(default_factory=dict)


class SheetsImportRequest(BaseModel):
    campaign_id: str
    rows: list[dict[str, Any]] = Field(max_length=1000)
    column_mapping: dict[str, str] = Field(default_factory=dict)


# ── Webhooks Management Endpoints ──────────────────────────────────────────

@router.get("/webhooks")
async def list_webhooks(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    public_fields = ('id', 'workspace_id', 'target_url', 'events', 'status', 'consecutive_failures',
                     'last_delivery_at', 'created_at', 'updated_at')
    cursor = db.outreach_webhooks.find(workspace_scope(ws_id), {"secret_enc": 0, "_id": 0})
    return [{key: row[key] for key in public_fields if key in row}
            for row in await cursor.to_list(length=100)]


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    req: CreateWebhookRequest,
    current_user: dict = require_outreach_permission('webhook:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)

    # Validate URL using safe transport rules (HTTPS only, no SSRF)
    try:
        validate_webhook_url(req.target_url)
    except SSRFSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook URL: {exc}",
        )

    # Enforce workspace webhook limit
    count_res = await db.outreach_webhooks.count_documents({"workspace_id": ws_id})
    count = count_res if isinstance(count_res, int) else 0
    if count >= MAX_WEBHOOKS_PER_WORKSPACE:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace reached the limit of {MAX_WEBHOOKS_PER_WORKSPACE} webhooks",
        )

    # Validate event subscriptions against frozen catalog
    valid_events = {e.value for e in WebhookEvent}
    filtered_events = [ev for ev in req.events if ev in valid_events]
    if not filtered_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least one valid event required from: {list(valid_events)}",
        )

    raw_secret = f"whsec_{secrets.token_hex(24)}"
    webhook_doc = OutreachWebhook(
        workspace_id=ws_id,
        target_url=req.target_url.strip(),
        secret_enc="",
        events=filtered_events,
        status="active",
    ).model_dump()

    await _save_integration(db, ws_id, "webhook", webhook_doc, raw_secret, actor=current_user.get("user_id"))

    return {
        "id": webhook_doc["id"],
        "target_url": webhook_doc["target_url"],
        "events": webhook_doc["events"],
        "status": webhook_doc["status"],
        "secret": raw_secret,  # Displayed once to user
        "created_at": webhook_doc["created_at"],
    }


@router.post("/webhooks/{webhook_id}/rotate-secret")
async def rotate_webhook_secret(
    webhook_id: str,
    current_user: dict = require_outreach_permission('webhook:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    previous = await db.outreach_webhooks.find_one({"id": webhook_id, "workspace_id": ws_id})
    if not previous:
        raise HTTPException(status_code=404, detail="Webhook not found")
    raw_secret = f"whsec_{secrets.token_hex(24)}"
    row = {key: value for key, value in previous.items() if key != "_id"}
    row["updated_at"] = datetime.now(timezone.utc)
    await _save_integration(db, ws_id, "webhook", row, raw_secret, previous, actor=current_user.get("user_id"))

    return {"status": "rotated", "webhook_id": webhook_id, "new_secret": raw_secret}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: dict = require_outreach_permission('webhook:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    removed = await _disconnect_integration(db, ws_id, "webhook", webhook_id, authority={"actor": current_user.get("user_id")})
    if not removed:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deleted", "webhook_id": webhook_id}


@router.get("/webhooks/{webhook_id}/deliveries")
async def list_webhook_deliveries(
    webhook_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_webhook_deliveries.find(
        {"destination_id": webhook_id, "workspace_id": ws_id},
        {"secret_enc": 0, "target_url_enc": 0, "payload": 0, "credential_digest": 0, "policy_digest": 0,
         "immutable_digest": 0, "receipt": 0, "receipt_digest": 0, "attempt_receipts": 0, "lease_id": 0},
    ).sort("created_at", -1).skip(skip).limit(limit)

    deliveries = await cursor.to_list(length=limit)
    total = await db.outreach_webhook_deliveries.count_documents({
        "destination_id": webhook_id, "workspace_id": ws_id,
    })
    return {"deliveries": deliveries, "total": total, "skip": skip, "limit": limit}


@router.post("/deliveries/{delivery_id}/replay")
async def replay_failed_delivery(
    delivery_id: str,
    current_user: dict = require_outreach_permission('webhook:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    actor_id = current_user.get("user_id") or "user"
    try:
        return await replay_delivery(db, ws_id, delivery_id, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/webhooks/{webhook_id}/test", status_code=202)
async def test_webhook_ping(
    webhook_id: str,
    current_user: dict = require_outreach_permission('webhook:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
    request_id: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    ws_id = _workspace_id(current_user)
    whk = await db.outreach_webhooks.find_one({"id": webhook_id, "workspace_id": ws_id})
    if not whk:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return await _queue_integration(db, ws_id, "webhook", webhook_id, current_user.get("user_id"), request_id=request_id)


@router.get("/deliveries/{delivery_id}/status")
async def get_integration_delivery_status(
    delivery_id: str,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    return await IntegrationDelivery(db)._result(IntegrationDelivery.scope(ws_id, delivery_id))


# ── API Key Management Endpoints ───────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_api_keys.find(
        {**workspace_scope(ws_id), "revoked_at": None},
        {"key_hash": 0, "_id": 0},
    ).sort("created_at", -1)
    public_fields = ('id', 'workspace_id', 'name', 'key_prefix', 'scopes', 'last_used_at', 'created_at')
    return [{key: row[key] for key in public_fields if key in row}
            for row in await cursor.to_list(length=50)]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    req: CreateApiKeyRequest,
    current_user: dict = require_outreach_permission('api_key:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)

    # Validate scopes against allowed set
    invalid_scopes = set(req.scopes) - ALLOWED_SCOPES
    if invalid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scopes: {invalid_scopes}. Allowed: {ALLOWED_SCOPES}",
        )

    active_res = await db.outreach_api_keys.count_documents({
        "workspace_id": ws_id, "revoked_at": None,
    })
    active_count = active_res if isinstance(active_res, int) else 0
    if active_count >= MAX_API_KEYS_PER_WORKSPACE:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace reached the limit of {MAX_API_KEYS_PER_WORKSPACE} active API keys",
        )

    # Generate high-entropy 32-byte key prefixed with unr_live_
    raw_token = secrets.token_urlsafe(32)
    raw_key = f"unr_live_{raw_token}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = raw_key[:16] + "..."

    now = datetime.now(timezone.utc)
    key_doc = {
        "id": f"key_{secrets.token_hex(8)}",
        "workspace_id": ws_id,
        "name": req.name.strip(),
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "scopes": req.scopes,
        "created_by": current_user.get("user_id"),
        "created_at": now,
        "last_used_at": None,
        "revoked_at": None,
        "expires_at": None,
    }

    await db.outreach_api_keys.insert_one(key_doc)

    return {
        "id": key_doc["id"],
        "name": key_doc["name"],
        "key_prefix": key_prefix,
        "scopes": key_doc["scopes"],
        "api_key": raw_key,  # Returned only once
        "created_at": key_doc["created_at"],
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    current_user: dict = require_outreach_permission('api_key:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    res = await db.outreach_api_keys.update_one(
        {"id": key_id, "workspace_id": ws_id, "revoked_at": None},
        {"$set": {"revoked_at": datetime.now(timezone.utc)}},
    )
    if not res.modified_count:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    return {"status": "revoked", "key_id": key_id}


# ── Slack Configuration Endpoints ──────────────────────────────────────────

@router.get("/slack")
async def get_slack_config(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "slack"})
    if not doc:
        return {"connected": False}
    meta = doc.get("metadata", {})
    return {
        "connected": doc.get("status") == "connected",
        "channel_name": meta.get("channel_name", "#sales-leads"),
        "notify_on_replies": meta.get("notify_on_replies", True),
        "notify_on_accepts": meta.get("notify_on_accepts", True),
        "daily_digest_enabled": meta.get("daily_digest_enabled", False),
    }


@router.post("/slack")
async def update_slack_config(
    req: SlackConfigRequest,
    current_user: dict = require_outreach_permission('outreach:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    try:
        clean_url = validate_slack_webhook_url(req.webhook_url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    now = datetime.now(timezone.utc)
    previous = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "slack"})
    row = {"workspace_id": ws_id, "provider": "slack", "created_at": (previous or {}).get("created_at", now),
                "status": "connected" if req.enabled else "disabled",
                "metadata": {
                    "channel_name": req.channel_name,
                    "notify_on_replies": req.notify_on_replies,
                    "notify_on_accepts": req.notify_on_accepts,
                    "daily_digest_enabled": req.daily_digest_enabled,
                },
                "updated_at": now,
    }
    await _save_integration(db, ws_id, "slack", row, clean_url, previous, actor=current_user.get("user_id"))
    return {"status": "saved", "connected": req.enabled}


@router.post("/slack/test", status_code=202)
async def test_slack_notification(
    current_user: dict = require_outreach_permission('outreach:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
    request_id: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "slack"})
    if not doc or not doc.get("access_token_enc"):
        raise HTTPException(status_code=400, detail="Slack integration is not configured")

    return await _queue_integration(db, ws_id, "slack", "slack", current_user.get("user_id"), request_id=request_id)


@router.delete("/slack")
async def delete_slack_config(
    current_user: dict = require_outreach_permission('outreach:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    await _disconnect_integration(db, ws_id, "slack", "slack", authority={"actor": current_user.get("user_id"), "permission": "outreach:manage"})
    return {"status": "disconnected"}


# ── HubSpot CRM Endpoints ──────────────────────────────────────────────────

@router.get("/hubspot")
async def get_hubspot_config(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "hubspot"})
    if not doc or doc.get("status") == "disconnected":
        return {"connected": False}
    meta = doc.get("metadata", {})
    return {
        "connected": doc.get("status") == "connected",
        "portal_id": meta.get("portal_id"),
        "auto_sync_on_reply": False,
        "auto_sync_available": False,
        "last_sync_at": doc.get("last_sync_at"),
    }


@router.post("/hubspot")
async def update_hubspot_config(
    req: HubSpotConfigRequest,
    current_user: dict = require_outreach_permission('outreach:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    if req.auto_sync_on_reply:
        raise HTTPException(409, "Automatic reply syncing is not available; use manual synchronization")
    clean_token = req.access_token.strip()
    clean_portal = req.portal_id.strip()
    if not clean_token or not clean_portal:
        raise HTTPException(status_code=400, detail="Both access token and portal ID are required")

    now = datetime.now(timezone.utc)
    previous = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "hubspot"})
    row = {"workspace_id": ws_id, "provider": "hubspot", "created_at": (previous or {}).get("created_at", now),
                "status": "connected",
                "metadata": {
                    "portal_id": clean_portal,
                    "auto_sync_on_reply": req.auto_sync_on_reply,
                },
                "updated_at": now,
    }
    await _save_integration(db, ws_id, "hubspot", row, clean_token, previous, actor=current_user.get("user_id"))
    return {"status": "saved", "connected": True, "portal_id": clean_portal}


@router.delete("/hubspot")
async def delete_hubspot_config(
    current_user: dict = require_outreach_permission('outreach:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    await _disconnect_integration(db, ws_id, "hubspot", "hubspot", authority={"actor": current_user.get("user_id"), "permission": "outreach:manage"})
    return {"status": "disconnected"}


@router.post("/hubspot/sync-lead/{lead_id}", status_code=202)
async def manual_sync_lead_hubspot(
    lead_id: str,
    current_user: dict = require_outreach_permission('lead:update'),
    db: AsyncIOMotorDatabase = Depends(get_db),
    request_id: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "hubspot", "status": "connected"})
    if not doc or not doc.get("access_token_enc"):
        raise HTTPException(status_code=400, detail="HubSpot integration is not connected")

    return await _queue_integration(db, ws_id, "hubspot", "hubspot", current_user.get("user_id"), lead_id=lead_id, request_id=request_id)


# ── Google Sheets / CSV Import Endpoints ───────────────────────────────────

@router.post("/sheets/preview")
async def preview_sheets_import(
    req: SheetsPreviewRequest,
    current_user: dict = require_outreach_permission('lead:create'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Preview spreadsheet rows, validate columns, neutralize formula injection,
    and detect duplicates against the target campaign.
    """
    ws_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one({
        "id": req.campaign_id,
        "workspace_id": ws_id,
        "is_deleted": {"$ne": True},
    })
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Fetch existing lead URLs/emails in this campaign
    existing_cursor = db.outreach_leads.find(
        {"campaign_id": req.campaign_id, "workspace_id": ws_id},
        {"linkedin_url": 1, "email": 1},
    )
    existing_leads = await existing_cursor.to_list(length=10000)
    existing_urls = {l.get("linkedin_url") for l in existing_leads if l.get("linkedin_url")}
    existing_emails = {l.get("email").lower() for l in existing_leads if l.get("email")}

    from outreach.core.lead_importer import normalize_any_linkedin_profile_url

    valid_rows = []
    duplicate_rows = 0
    invalid_rows = 0
    formula_neutralized_count = 0

    for raw_row in req.rows:
        row = sanitize_row_data(raw_row)
        for k, v in raw_row.items():
            if isinstance(v, str) and v.strip().startswith(FORMULA_INJECTION_PREFIXES):
                formula_neutralized_count += 1

        url_key = req.column_mapping.get("linkedin_url", "linkedin_url")
        email_key = req.column_mapping.get("email", "email")

        url_val = normalize_any_linkedin_profile_url(str(row.get(url_key, ""))) or normalize_linkedin_url(str(row.get(url_key, "")))
        email_val = str(row.get(email_key, "")).strip().lower()

        if not url_val:
            invalid_rows += 1
        elif (url_val and url_val in existing_urls) or (email_val and email_val in existing_emails):
            duplicate_rows += 1
        else:
            valid_rows.append(row)

    return {
        "total_rows": len(req.rows),
        "valid_count": len(valid_rows),
        "duplicate_count": duplicate_rows,
        "invalid_count": invalid_rows,
        "formula_neutralized_count": formula_neutralized_count,
        "sample_preview": valid_rows[:5],
    }


@router.post("/sheets/import", status_code=status.HTTP_201_CREATED)
async def import_sheets_leads(
    req: SheetsImportRequest,
    current_user: dict = require_outreach_permission('lead:create'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Import spreadsheet leads into campaign with formula injection defense,
    suppression list enforcement, warm-up lock checks, and outbox emission.
    """
    ws_id = _workspace_id(current_user)
    from outreach.core.lead_importer import LeadImporter
    fields = ("linkedin_url", "first_name", "last_name", "company_name", "job_title", "email")
    rows = []
    for raw in req.rows:
        row = sanitize_row_data(raw)
        rows.append({field: str(row.get(req.column_mapping.get(field, field), "") or "").strip() for field in fields})
    result = await LeadImporter.ingest_leads(rows, req.campaign_id, ws_id, db,
        source="google_sheets", include_rejections=True)
    return {"status": "imported", "enrolled_count": result["imported_count"],
            "skipped_duplicate": result["duplicates_count"],
            "skipped_suppressed": sum(row["rejection_code"] in {"email_suppressed", "do_not_contact", "withdrawn_cooldown"}
                                      for row in result["rejections"]),
            "skipped_count": result["skipped_count"], "rejections": result["rejections"]}


# ── Public REST API Authentication & Rate Limiting ─────────────────────────

# In-memory rate-limiter fallback: {key_hash: (count, window_start)}
_RATE_LIMIT_BUCKET: dict[str, tuple[int, float]] = {}


async def authenticate_api_key(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> str:
    """Authenticates API key and returns workspace_id."""
    raw_key = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_key = parts[1].strip()
    elif x_api_key:
        raw_key = x_api_key.strip()

    if not raw_key or not raw_key.startswith("unr_live_"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid API key required")

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_doc = await db.outreach_api_keys.find_one({"key_hash": key_hash})
    if not key_doc or key_doc.get("revoked_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    ws_id = key_doc["workspace_id"]
    from outreach.core.erasure import require_open_workspace
    await require_open_workspace({"workspace_id": ws_id}, db)
    if not is_integrations_pilot_allowed(ws_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integrations are not enabled for this workspace in the current pilot",
        )
    return ws_id


def require_api_key_scope(required_scope: str) -> Callable:
    """Dependency factory checking API key authentication, scope, and rate limits."""
    async def _authenticator(
        request: Request,
        response: Response,
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
        db: AsyncIOMotorDatabase = Depends(get_db),
    ) -> dict[str, Any]:
        raw_key = None
        if authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_key = parts[1].strip()
        elif x_api_key:
            raw_key = x_api_key.strip()

        if not raw_key or not raw_key.startswith("unr_live_") or len(raw_key) < 30:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid API key required (Bearer unr_live_...)",
            )

        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_doc = await db.outreach_api_keys.find_one({"key_hash": key_hash})
        if not key_doc or key_doc.get("revoked_at"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
            )

        # Check key expiry
        now = datetime.now(timezone.utc)
        if key_doc.get("expires_at") and key_doc["expires_at"] < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
            )

        # Check scope entitlement
        key_scopes = set(key_doc.get("scopes", []))
        if required_scope not in key_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope '{required_scope}'",
            )

        workspace_id = key_doc["workspace_id"]
        from outreach.core.erasure import require_open_workspace
        await require_open_workspace({"workspace_id": workspace_id}, db)
        if not is_integrations_pilot_allowed(workspace_id):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Integrations are not enabled for this workspace in the current pilot",
            )

        # Simple 60 requests/minute sliding window rate limiting
        now_ts = now.timestamp()
        bucket = _RATE_LIMIT_BUCKET.get(key_hash, (0, now_ts))
        count, window_start = bucket
        if now_ts - window_start > 60:
            count = 1
            window_start = now_ts
        else:
            count += 1

        _RATE_LIMIT_BUCKET[key_hash] = (count, window_start)
        if count > 60:
            response.headers["Retry-After"] = "60"
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Maximum 60 requests per minute.",
            )

        # Record last_used_at asynchronously
        await db.outreach_api_keys.update_one(
            {"_id": key_doc["_id"]},
            {"$set": {"last_used_at": now}},
        )

        return {
            "workspace_id": workspace_id,
            "key_id": key_doc.get("id"),
            "key_hash": key_hash,
            "scopes": list(key_scopes),
        }

    return _authenticator


# ── Public Endpoints ───────────────────────────────────────────────────────

@public_router.get("/campaigns")
async def public_list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    auth: dict = Depends(require_api_key_scope("campaigns:read")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List active outreach campaigns in the workspace (sanitized public fields)."""
    workspace_id = auth["workspace_id"]
    cursor = db.outreach_campaigns.find(
        {"workspace_id": workspace_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "leads_count": 1, "created_at": 1},
    ).sort("created_at", -1).skip(skip).limit(limit)

    campaigns = await cursor.to_list(length=limit)
    total = await db.outreach_campaigns.count_documents({
        "workspace_id": workspace_id, "is_deleted": {"$ne": True},
    })
    return {"items": campaigns, "total": total, "skip": skip, "limit": limit}


@public_router.post("/leads", status_code=status.HTTP_201_CREATED)
async def public_enroll_lead(
    req: PublicLeadEnrollRequest,
    idempotency_key: str = Header(..., description="Unique client request ID (e.g. UUID)"),
    auth: dict = Depends(require_api_key_scope("leads:write")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Enrolls a lead into an active campaign with strict normalization,
    suppression checking, warm-up lock protection, and idempotency.
    """
    workspace_id = auth["workspace_id"]
    clean_idempotency = idempotency_key.strip()
    if not clean_idempotency or len(clean_idempotency) > 128:
        raise HTTPException(400, "Valid Idempotency-Key header is required (1-128 chars)")
    clean_url = normalize_linkedin_url(req.linkedin_url)
    if not clean_url:
        raise HTTPException(400, "A valid LinkedIn personal profile URL is required")
    from outreach.core.authorization import canonical_hash
    from outreach.core.lead_importer import LeadImporter
    from outreach.core.suppression import mutate_suppression
    request_id = canonical_hash(["lead_admission", workspace_id, auth.get("key_id"), auth.get("key_hash"), clean_idempotency])
    digest = canonical_hash(req.model_dump())

    def check_deadline(key):
        expires = key.get("expires_at")
        if expires is not None:
            if not isinstance(expires, datetime):
                raise HTTPException(401, "Invalid API key expiry")
            deadline = expires.astimezone(timezone.utc) if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
            if deadline <= datetime.now(timezone.utc):
                raise HTTPException(401, "API key has expired")
        if not is_integrations_pilot_allowed(workspace_id):
            raise HTTPException(503, "Integrations are not enabled for this workspace in the current pilot")

    async def enroll(current):
        # Keep the public-key boundary separate from authenticated browser authority.
        key = await current.outreach_api_keys.find_one({**workspace_scope(workspace_id),
            "id": auth.get("key_id"), "key_hash": auth.get("key_hash"), "revoked_at": None})
        now = datetime.now(timezone.utc)
        expires = (key or {}).get("expires_at")
        if (not key or not isinstance(auth.get("key_id"), str) or not auth.get("key_hash")
                or "leads:write" not in key.get("scopes", [])):
            raise HTTPException(401, "Invalid or revoked API key")
        check_deadline(key)
        checked = await current.outreach_api_keys.update_one({**workspace_scope(workspace_id),
            "id": key["id"], "key_hash": key["key_hash"], "revoked_at": None,
            "scopes": key["scopes"], "expires_at": expires if "expires_at" in key else {"$exists": False}},
            {"$inc": {"lead_admission_revision": 1}})
        if getattr(checked, "matched_count", 0) != 1:
            raise HTTPException(401, "API key changed before enrollment")
        receipt_scope = {"_id": request_id, **workspace_scope(workspace_id)}
        receipt = await current.outreach_lead_admissions.find_one(receipt_scope)
        if receipt:
            if receipt.get("request_digest") != digest:
                raise HTTPException(409, "Idempotency-Key is already bound to a different enrollment request")
            check_deadline(key)
            return receipt["result"]
        row = {**req.model_dump(), "linkedin_url": clean_url}
        result = await LeadImporter.ingest_leads([row], req.campaign_id, workspace_id, current,
            source="public_api", include_rejections=True, _ordered=True)
        if result["imported_count"]:
            response = {"status": "enrolled", "lead_id": result["lead_ids"][0], "campaign_id": req.campaign_id}
        elif result["duplicates_count"]:
            existing = await current.outreach_leads.find_one({**workspace_scope(workspace_id),
                "campaign_id": req.campaign_id, "linkedin_url": {"$in": list(_host_variants(clean_url))},
                "execution_state": {"$ne": "staged"}})
            if not existing:
                raise HTTPException(409, "An existing recipient identity needs review before enrollment")
            response = {"status": "already_enrolled", "lead_id": existing["id"], "campaign_id": req.campaign_id}
        else:
            raise HTTPException(400, result["rejections"][0]["reason"] if result["rejections"] else "Contact cannot be enrolled")
        await current.outreach_lead_admissions.insert_one({"_id": request_id, "workspace_id": workspace_id,
            "request_digest": digest, "result": response, "created_at": now})
        check_deadline(key)
        return response
    try:
        return await mutate_suppression(db, workspace_id, enroll)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm enrollment. Retry with the same Idempotency-Key.") from None


@public_router.post("/leads/{lead_id}/pause")
async def public_pause_lead(
    lead_id: str,
    auth: dict = Depends(require_api_key_scope("leads:write")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Safely stop/pause a lead's execution sequence across all channels."""
    workspace_id = auth["workspace_id"]
    lead = await db.outreach_leads.find_one({"id": lead_id, "workspace_id": workspace_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY, UNVERIFIED_LEAD, unverified_search_lead
    if unverified_search_lead(lead):
        raise HTTPException(409, UNVERIFIED_LEAD)
    now = datetime.now(timezone.utc)
    changed = await db.outreach_leads.update_one(
        {"id": lead_id, "workspace_id": workspace_id, "$nor": [SEARCH_PROVENANCE_QUERY]},
        {"$set": {
            "execution_state": LeadExecutionState.FAILED.value,
            "failure_reason": "Lead stopped via Public API request",
            "next_action_due_at": None,
            "updated_at": now,
        }},
    )
    if not changed.matched_count:
        raise HTTPException(409, "Contact source changed; refresh before pausing.")

    await record_outbox_event(
        db=db,
        workspace_id=workspace_id,
        event_type=WebhookEvent.LEAD_STAGE_CHANGED,
        aggregate_id=lead_id,
        dedupe_key=f"lead.paused:{lead_id}:{int(now.timestamp())}",
        data={
            "lead_id": lead_id,
            "campaign_id": lead.get("campaign_id"),
            "previous_state": lead.get("execution_state"),
            "new_state": "stopped",
            "source_status": "confirmed",
        },
    )

    return {"status": "paused", "lead_id": lead_id}


@public_router.get("/leads/{lead_id}/history")
async def public_lead_history(
    lead_id: str,
    auth: dict = Depends(require_api_key_scope("leads:read")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Retrieve sanitized history of confirmed actions for a lead."""
    workspace_id = auth["workspace_id"]
    lead = await db.outreach_leads.find_one(
        {"id": lead_id, "workspace_id": workspace_id},
        {"_id": 0, "id": 1, "campaign_id": 1, "execution_state": 1, "pipeline_stage": 1, "created_at": 1},
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    cursor = db.outreach_tasks.find(
        {"lead_id": lead_id, "workspace_id": workspace_id},
        {"_id": 0, "id": 1, "task_type": 1, "status": 1, "resolved_at": 1, "created_at": 1},
    ).sort("created_at", -1)

    tasks = await cursor.to_list(length=100)
    return {"lead": lead, "history": tasks}


# ── Zapier / Make REST Hooks Endpoints ─────────────────────────────────────

@public_router.post("/hooks/subscribe", status_code=status.HTTP_201_CREATED)
async def public_subscribe_hook(
    req: SubscribeRestHookRequest,
    auth: dict = Depends(require_api_key_scope("leads:read")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Subscribes a Zapier or Make REST Hook to a verified outreach event.
    Enforces HTTPS and SSRF/DNS safety on the callback destination.
    """
    workspace_id = auth["workspace_id"]
    try:
        validate_webhook_url(req.target_url)
        validated_url = req.target_url.strip()
    except SSRFSecurityError as ssrf_err:
        raise HTTPException(status_code=400, detail=f"Invalid callback destination: {ssrf_err}")

    valid_events = {e.value for e in WebhookEvent}
    if req.event not in valid_events:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event '{req.event}'. Allowed: {sorted(list(valid_events))}",
        )

    count = await db.outreach_webhooks.count_documents({"workspace_id": workspace_id})
    if count >= MAX_WEBHOOKS_PER_WORKSPACE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_WEBHOOKS_PER_WORKSPACE} webhooks/hooks allowed per workspace",
        )

    import uuid
    hook_id = f"hook_{uuid.uuid4().hex[:12]}"
    secret = secrets.token_hex(24)
    now = datetime.now(timezone.utc)

    hook_doc = {
        "id": hook_id,
        "workspace_id": workspace_id,
        "target_url": validated_url,
        "events": [req.event],
        "status": "active",
        "secret_enc": "",
        "source": "rest_hook",
        "created_at": now,
        "consecutive_failures": 0,
        "last_delivery_at": None,
    }
    await _save_integration(db, workspace_id, "webhook", hook_doc, secret, api_key=auth)
    return {"id": hook_id, "event": req.event, "target_url": validated_url}


@public_router.delete("/hooks/unsubscribe/{hook_id}")
async def public_unsubscribe_hook(
    hook_id: str,
    auth: dict = Depends(require_api_key_scope("leads:read")),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Unsubscribes and cleans up a Zapier/Make REST hook subscription.
    """
    workspace_id = auth["workspace_id"]
    removed = await _disconnect_integration(db, workspace_id, "webhook", hook_id, authority={"api_key_id": auth.get("key_id"), "key_hash": auth.get("key_hash")})
    if not removed:
        raise HTTPException(status_code=404, detail="Hook subscription not found")
    return {"status": "unsubscribed", "id": hook_id}


@public_router.get("/hooks/sample")
async def public_hook_sample(
    event: str = Query("lead.replied", description="Event type for schema discovery"),
    auth: dict = Depends(require_api_key_scope("leads:read")),
):
    """
    Returns a schema-compliant mock sample event for Zapier/Make field mapping
    during workflow recipe configuration.
    """
    valid_events = {e.value for e in WebhookEvent}
    if event not in valid_events:
        raise HTTPException(status_code=400, detail=f"Invalid event '{event}'. Allowed: {sorted(list(valid_events))}")

    samples = {
        "lead.replied": {
            "id": "evt_sample_01",
            "type": "lead.replied",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "lead_id": "lead_sample_abc123",
                "campaign_id": "camp_sample_xyz789",
                "linkedin_url": "https://www.linkedin.com/in/alex-rivera-sample",
                "channel": "linkedin",
                "source_status": "confirmed",
            },
        },
        "lead.connection_accepted": {
            "id": "evt_sample_02",
            "type": "lead.connection_accepted",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "lead_id": "lead_sample_abc123",
                "campaign_id": "camp_sample_xyz789",
                "linkedin_url": "https://www.linkedin.com/in/alex-rivera-sample",
                "channel": "linkedin",
                "source_status": "confirmed",
            },
        },
        "lead.created": {
            "id": "evt_sample_03",
            "type": "lead.created",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "lead_id": "lead_sample_abc123",
                "campaign_id": "camp_sample_xyz789",
                "linkedin_url": "https://www.linkedin.com/in/alex-rivera-sample",
                "channel": "linkedin",
                "source_status": "confirmed",
            },
        },
        "campaign.paused": {
            "id": "evt_sample_04",
            "type": "campaign.paused",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "campaign_id": "camp_sample_xyz789",
                "source_status": "confirmed",
            },
        },
        "email.accepted": {
            "id": "evt_sample_05",
            "type": "email.accepted",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "lead_id": "lead_sample_abc123",
                "campaign_id": "camp_sample_xyz789",
                "channel": "email",
                "recipient": "alex.rivera@example.com",
                "source_status": "confirmed",
            },
        },
        "lead.stage_changed": {
            "id": "evt_sample_06",
            "type": "lead.stage_changed",
            "version": 1,
            "occurred_at": "2026-09-29T12:00:00Z",
            "workspace_id": auth["workspace_id"],
            "data": {
                "lead_id": "lead_sample_abc123",
                "campaign_id": "camp_sample_xyz789",
                "previous_state": "in_progress",
                "new_state": "stopped",
                "source_status": "confirmed",
            },
        },
    }

    return samples.get(event, samples["lead.replied"])
