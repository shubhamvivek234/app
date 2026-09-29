"""
Integrations and Public REST API Router.
Provides customer webhook management, scoped API keys with rate limits and idempotency,
Slack alert integration, and safe public lead ingestion/pause controls.
"""
from datetime import datetime, timezone
import hashlib
import logging
import secrets
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
import httpx

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.crypto import decrypt_secret, encrypt_secret
from outreach.core.event_definitions import WebhookEvent
from outreach.core.event_outbox import record_outbox_event
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.paid_access import get_active_entitlement
from outreach.core.safe_transport import SSRFSecurityError, validate_webhook_url
from outreach.core.slack_notifier import (
    format_slack_test_card,
    send_slack_notification,
    validate_slack_webhook_url,
)
from outreach.core.crm_sync import (
    FORMULA_INJECTION_PREFIXES,
    sanitize_spreadsheet_value,
    sanitize_row_data,
    sync_lead_to_hubspot,
)
from outreach.core.webhook_delivery import replay_delivery
from outreach.core.webhook_dispatcher import dispatch_webhook
from outreach.models import LeadExecutionState, OutreachApiKey, OutreachWebhook
from outreach.core.integrations_pilot import is_integrations_pilot_allowed
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Outreach Integrations & Webhooks"])
public_router = APIRouter(prefix="/public", tags=["Outreach Public REST API"])

ALLOWED_SCOPES = {"campaigns:read", "leads:read", "leads:write"}
MAX_WEBHOOKS_PER_WORKSPACE = 10
MAX_API_KEYS_PER_WORKSPACE = 10


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
    auto_sync_on_reply: bool = Field(default=True)


class SheetsPreviewRequest(BaseModel):
    campaign_id: str
    rows: list[dict[str, Any]]
    column_mapping: dict[str, str] = Field(default_factory=dict)


class SheetsImportRequest(BaseModel):
    campaign_id: str
    rows: list[dict[str, Any]]
    column_mapping: dict[str, str] = Field(default_factory=dict)


# ── Webhooks Management Endpoints ──────────────────────────────────────────

@router.get("/webhooks")
async def list_webhooks(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_webhooks.find({"workspace_id": ws_id}, {"secret_enc": 0})
    return await cursor.to_list(length=100)


@router.post("/webhooks", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("webhook:manage")])
async def create_webhook(
    req: CreateWebhookRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)

    if not is_safe_url(req.target_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook URL: rejected by SSRF security policy",
        )

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
    secret_enc = encrypt_secret(raw_secret)

    webhook_doc = OutreachWebhook(
        workspace_id=ws_id,
        target_url=req.target_url.strip(),
        secret_enc=secret_enc,
        events=filtered_events,
        status="active",
    ).model_dump()

    await db.outreach_webhooks.insert_one(webhook_doc)

    return {
        "id": webhook_doc["id"],
        "target_url": webhook_doc["target_url"],
        "events": webhook_doc["events"],
        "status": webhook_doc["status"],
        "secret": raw_secret,  # Displayed once to user
        "created_at": webhook_doc["created_at"],
    }


@router.post("/webhooks/{webhook_id}/rotate-secret",
             dependencies=[require_permission("webhook:manage")])
async def rotate_webhook_secret(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    raw_secret = f"whsec_{secrets.token_hex(24)}"
    secret_enc = encrypt_secret(raw_secret)

    res = await db.outreach_webhooks.update_one(
        {"id": webhook_id, "workspace_id": ws_id},
        {"$set": {"secret_enc": secret_enc, "updated_at": datetime.now(timezone.utc)}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"status": "rotated", "webhook_id": webhook_id, "new_secret": raw_secret}


@router.delete("/webhooks/{webhook_id}", dependencies=[require_permission("webhook:manage")])
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    res = await db.outreach_webhooks.delete_one({"id": webhook_id, "workspace_id": ws_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Webhook not found")
    # Cancel any pending deliveries for this webhook
    await db.outreach_webhook_deliveries.delete_many({
        "destination_id": webhook_id,
        "workspace_id": ws_id,
        "status": "pending",
    })
    return {"status": "deleted", "webhook_id": webhook_id}


@router.get("/webhooks/{webhook_id}/deliveries")
async def list_webhook_deliveries(
    webhook_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_webhook_deliveries.find(
        {"destination_id": webhook_id, "workspace_id": ws_id},
        {"secret_enc": 0},
    ).sort("created_at", -1).skip(skip).limit(limit)

    deliveries = await cursor.to_list(length=limit)
    total = await db.outreach_webhook_deliveries.count_documents({
        "destination_id": webhook_id, "workspace_id": ws_id,
    })
    return {"deliveries": deliveries, "total": total, "skip": skip, "limit": limit}


@router.post("/deliveries/{delivery_id}/replay",
             dependencies=[require_permission("webhook:manage")])
async def replay_failed_delivery(
    delivery_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    actor_id = current_user.get("user_id") or "user"
    try:
        return await replay_delivery(db, ws_id, delivery_id, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/webhooks/{webhook_id}/test", dependencies=[require_permission("webhook:manage")])
async def test_webhook_ping(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    whk = await db.outreach_webhooks.find_one({"id": webhook_id, "workspace_id": ws_id})
    if not whk:
        raise HTTPException(status_code=404, detail="Webhook not found")

    secret = decrypt_secret(whk.get("secret_enc", "")) if whk.get("secret_enc") else ""
    ping_data = {
        "event": "ping",
        "ping_time": datetime.now(timezone.utc).isoformat(),
        "workspace_id": ws_id,
        "message": "Unravler webhook verification ping",
    }
    result = await dispatch_webhook(whk["target_url"], secret, "system.ping", ping_data)
    return result


# ── API Key Management Endpoints ───────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_api_keys.find(
        {"workspace_id": ws_id, "revoked_at": None},
        {"key_hash": 0},
    ).sort("created_at", -1)
    return await cursor.to_list(length=50)


@router.post("/api-keys", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("api_key:manage")])
async def create_api_key(
    req: CreateApiKeyRequest,
    current_user: dict = Depends(get_current_user),
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


@router.delete("/api-keys/{key_id}", dependencies=[require_permission("api_key:manage")])
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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


@router.post("/slack", dependencies=[require_permission("outreach:manage")])
async def update_slack_config(
    req: SlackConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    try:
        clean_url = validate_slack_webhook_url(req.webhook_url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    now = datetime.now(timezone.utc)
    await db.outreach_integrations.update_one(
        {"workspace_id": ws_id, "provider": "slack"},
        {
            "$set": {
                "status": "connected" if req.enabled else "disabled",
                "access_token_enc": encrypt_secret(clean_url),
                "metadata": {
                    "channel_name": req.channel_name,
                    "notify_on_replies": req.notify_on_replies,
                    "notify_on_accepts": req.notify_on_accepts,
                    "daily_digest_enabled": req.daily_digest_enabled,
                },
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {"status": "saved", "connected": req.enabled}


@router.post("/slack/test", dependencies=[require_permission("outreach:manage")])
async def test_slack_notification(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "slack"})
    if not doc or not doc.get("access_token_enc"):
        raise HTTPException(status_code=400, detail="Slack integration is not configured")

    webhook_url = decrypt_secret(doc["access_token_enc"])
    test_card = format_slack_test_card()
    success, code, err = await send_slack_notification(webhook_url, test_card)
    if not success:
        raise HTTPException(status_code=502, detail=err or "Failed to deliver Slack test card")
    return {"success": True, "status_code": code}


@router.delete("/slack", dependencies=[require_permission("outreach:manage")])
async def delete_slack_config(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    await db.outreach_integrations.delete_one({"workspace_id": ws_id, "provider": "slack"})
    return {"status": "disconnected"}


# ── HubSpot CRM Endpoints ──────────────────────────────────────────────────

@router.get("/hubspot")
async def get_hubspot_config(
    current_user: dict = Depends(get_current_user),
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
        "auto_sync_on_reply": meta.get("auto_sync_on_reply", True),
        "last_sync_at": doc.get("last_sync_at"),
    }


@router.post("/hubspot", dependencies=[require_permission("outreach:manage")])
async def update_hubspot_config(
    req: HubSpotConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    clean_token = req.access_token.strip()
    clean_portal = req.portal_id.strip()
    if not clean_token or not clean_portal:
        raise HTTPException(status_code=400, detail="Both access token and portal ID are required")

    now = datetime.now(timezone.utc)
    await db.outreach_integrations.update_one(
        {"workspace_id": ws_id, "provider": "hubspot"},
        {
            "$set": {
                "status": "connected",
                "access_token_enc": encrypt_secret(clean_token),
                "metadata": {
                    "portal_id": clean_portal,
                    "auto_sync_on_reply": req.auto_sync_on_reply,
                },
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {"status": "saved", "connected": True, "portal_id": clean_portal}


@router.delete("/hubspot", dependencies=[require_permission("outreach:manage")])
async def delete_hubspot_config(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    await db.outreach_integrations.delete_one({"workspace_id": ws_id, "provider": "hubspot"})
    return {"status": "disconnected"}


@router.post("/hubspot/sync-lead/{lead_id}", dependencies=[require_permission("lead:update")])
async def manual_sync_lead_hubspot(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "hubspot", "status": "connected"})
    if not doc or not doc.get("access_token_enc"):
        raise HTTPException(status_code=400, detail="HubSpot integration is not connected")

    token = decrypt_secret(doc["access_token_enc"])
    portal_id = doc.get("metadata", {}).get("portal_id", "")
    try:
        res = await sync_lead_to_hubspot(
            db=db,
            workspace_id=ws_id,
            lead_id=lead_id,
            access_token=token,
            portal_id=portal_id,
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HubSpot sync failed: {str(exc)[:150]}")


# ── Google Sheets / CSV Import Endpoints ───────────────────────────────────

@router.post("/sheets/preview", dependencies=[require_permission("lead:create")])
async def preview_sheets_import(
    req: SheetsPreviewRequest,
    current_user: dict = Depends(get_current_user),
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

    valid_rows = []
    duplicate_rows = 0
    formula_neutralized_count = 0

    for raw_row in req.rows:
        row = sanitize_row_data(raw_row)
        for k, v in raw_row.items():
            if isinstance(v, str) and v.strip().startswith(FORMULA_INJECTION_PREFIXES):
                formula_neutralized_count += 1

        url_key = req.column_mapping.get("linkedin_url", "linkedin_url")
        email_key = req.column_mapping.get("email", "email")

        url_val = normalize_linkedin_url(str(row.get(url_key, "")))
        email_val = str(row.get(email_key, "")).strip().lower()

        if (url_val and url_val in existing_urls) or (email_val and email_val in existing_emails):
            duplicate_rows += 1
        else:
            valid_rows.append(row)

    return {
        "total_rows": len(req.rows),
        "valid_count": len(valid_rows),
        "duplicate_count": duplicate_rows,
        "formula_neutralized_count": formula_neutralized_count,
        "sample_preview": valid_rows[:5],
    }


@router.post("/sheets/import", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("lead:create")])
async def import_sheets_leads(
    req: SheetsImportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Import spreadsheet leads into campaign with formula injection defense,
    suppression list enforcement, warm-up lock checks, and outbox emission.
    """
    ws_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one({
        "id": req.campaign_id,
        "workspace_id": ws_id,
        "is_deleted": {"$ne": True},
    })
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.get("status") == "warming_up":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is armed in warm-up state; lead import is locked.",
        )

    # Fetch suppressions
    suppressions = await db.outreach_email_suppressions.find({"workspace_id": ws_id}).to_list(length=5000)
    suppressed_emails = {s.get("email", "").lower() for s in suppressions if s.get("email")}

    mapping = req.column_mapping
    url_key = mapping.get("linkedin_url", "linkedin_url")
    fn_key = mapping.get("first_name", "first_name")
    ln_key = mapping.get("last_name", "last_name")
    comp_key = mapping.get("company_name", "company_name")
    title_key = mapping.get("job_title", "job_title")
    email_key = mapping.get("email", "email")

    enrolled = 0
    skipped_duplicate = 0
    skipped_suppressed = 0
    now = datetime.now(timezone.utc)

    for raw_row in req.rows:
        row = sanitize_row_data(raw_row)
        raw_url = str(row.get(url_key, ""))
        clean_url = normalize_linkedin_url(raw_url)
        if not clean_url:
            continue

        raw_email = str(row.get(email_key, "")).strip().lower()
        if raw_email and raw_email in suppressed_emails:
            skipped_suppressed += 1
            continue

        # Check existing lead in campaign
        existing = await db.outreach_leads.find_one({
            "campaign_id": req.campaign_id,
            "workspace_id": ws_id,
            "linkedin_url": clean_url,
        })
        if existing:
            skipped_duplicate += 1
            continue

        lead_id = f"lead_{uuid.uuid4().hex[:12]}"
        lead_doc = {
            "id": lead_id,
            "workspace_id": ws_id,
            "campaign_id": req.campaign_id,
            "linkedin_url": clean_url,
            "first_name": str(row.get(fn_key, "")).strip() or "Contact",
            "last_name": str(row.get(ln_key, "")).strip(),
            "company_name": str(row.get(comp_key, "")).strip(),
            "job_title": str(row.get(title_key, "")).strip(),
            "email": raw_email or None,
            "pipeline_stage": "new",
            "execution_state": LeadExecutionState.PENDING.value,
            "source": "google_sheets",
            "created_at": now,
            "updated_at": now,
        }
        await db.outreach_leads.insert_one(lead_doc)
        enrolled += 1

        # Emit outbox event
        await record_outbox_event(
            db=db,
            workspace_id=ws_id,
            event_type=WebhookEvent.LEAD_CREATED,
            aggregate_id=lead_id,
            dedupe_key=f"lead.created:{lead_id}",
            data={
                "lead_id": lead_id,
                "campaign_id": req.campaign_id,
                "linkedin_url": clean_url,
                "channel": "linkedin",
                "source_status": "confirmed",
            },
        )

    # Update campaign leads count
    if enrolled > 0:
        await db.outreach_campaigns.update_one(
            {"id": req.campaign_id, "workspace_id": ws_id},
            {"$inc": {"leads_count": enrolled}},
        )

    return {
        "status": "imported",
        "enrolled_count": enrolled,
        "skipped_duplicate": skipped_duplicate,
        "skipped_suppressed": skipped_suppressed,
    }


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid Idempotency-Key header is required (1-128 chars)",
        )

    # Validate campaign exists and is not deleted
    campaign = await db.outreach_campaigns.find_one({
        "id": req.campaign_id,
        "workspace_id": workspace_id,
        "is_deleted": {"$ne": True},
    })
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found in this workspace")

    # Guard: warm-up campaigns cannot receive direct external lead imports
    if campaign.get("status") == "warming_up":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot enroll leads into a campaign currently undergoing warm-up",
        )

    # Validate and normalize LinkedIn profile URL
    clean_url = normalize_linkedin_url(req.linkedin_url)
    if not clean_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid LinkedIn personal profile URL is required (e.g. https://linkedin.com/in/username)",
        )

    # Check suppression list if email provided
    if req.email:
        clean_email = req.email.strip().lower()
        is_suppressed = await db.outreach_email_suppressions.find_one({
            "workspace_id": workspace_id, "email": clean_email,
        })
        if is_suppressed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email address '{clean_email}' is on the workspace suppression list",
            )

    # Idempotent deduplication check: return existing if already enrolled
    existing = await db.outreach_leads.find_one({
        "workspace_id": workspace_id,
        "campaign_id": req.campaign_id,
        "linkedin_url": clean_url,
    })
    if existing:
        return {
            "status": "already_enrolled",
            "lead_id": existing["id"],
            "campaign_id": req.campaign_id,
        }

    now = datetime.now(timezone.utc)
    from uuid import uuid4
    lead_id = f"lead_{uuid4().hex[:12]}"

    lead_doc = {
        "id": lead_id,
        "workspace_id": workspace_id,
        "campaign_id": req.campaign_id,
        "linkedin_url": clean_url,
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "company_name": req.company_name.strip(),
        "job_title": req.job_title.strip(),
        "email": req.email.strip() if req.email else None,
        "custom_variables": req.custom_variables,
        "execution_state": LeadExecutionState.QUEUED.value,
        "pipeline_stage": "in_campaign",
        "created_at": now,
        "updated_at": now,
    }

    await db.outreach_leads.insert_one(lead_doc)
    await db.outreach_campaigns.update_one(
        {"id": req.campaign_id, "workspace_id": workspace_id},
        {"$inc": {"leads_count": 1}},
    )

    # Emit durable event to outbox
    await record_outbox_event(
        db=db,
        workspace_id=workspace_id,
        event_type=WebhookEvent.LEAD_CREATED,
        aggregate_id=lead_id,
        dedupe_key=f"lead.created:{lead_id}",
        data={
            "lead_id": lead_id,
            "campaign_id": req.campaign_id,
            "linkedin_url": clean_url,
            "channel": "linkedin",
            "source_status": "confirmed",
        },
    )

    return {"status": "enrolled", "lead_id": lead_id, "campaign_id": req.campaign_id}


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

    now = datetime.now(timezone.utc)
    await db.outreach_leads.update_one(
        {"id": lead_id, "workspace_id": workspace_id},
        {"$set": {
            "execution_state": LeadExecutionState.FAILED.value,
            "failure_reason": "Lead stopped via Public API request",
            "next_action_due_at": None,
            "updated_at": now,
        }},
    )

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
        validated_url = validate_webhook_url(req.target_url)
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
        "secret_enc": encrypt_secret(secret),
        "source": "rest_hook",
        "created_at": now,
        "consecutive_failures": 0,
        "last_delivery_at": None,
    }
    await db.outreach_webhooks.insert_one(hook_doc)
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
    res = await db.outreach_webhooks.delete_one({"id": hook_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
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
