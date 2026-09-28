"""
Integrations API: Webhooks, Public API keys, and third-party connectors (Slack, Zapier, Make).
Allows external tools to subscribe to outreach events and programmatically inject leads.
"""
from datetime import datetime, timezone
import hashlib
import logging
import secrets
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
import httpx

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.crypto import encrypt_secret
from outreach.core.webhook_dispatcher import dispatch_webhook
from outreach.models import OutreachApiKey, OutreachWebhook, WebhookEvent
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Outreach Integrations & Webhooks"])
public_router = APIRouter(prefix="/public", tags=["Outreach Public REST API"])


def _workspace_id(user: dict) -> str:
    workspace_id = user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=403, detail="An active workspace is required")
    return str(workspace_id)


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


# ── Webhooks Management ───────────────────────────────────────────────────

@router.get("/webhooks")
async def list_webhooks(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_webhooks.find({"workspace_id": ws_id}, {"secret_enc": 0})
    return await cursor.to_list(length=100)


@router.post("/webhooks", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("campaign:create")])
async def create_webhook(
    req: CreateWebhookRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    if not is_safe_url(req.target_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target URL rejected by security policy (SSRF protection). Must be a valid public address.",
        )

    # Generate a cryptographically secure signing secret
    raw_secret = f"whsec_{secrets.token_hex(24)}"
    secret_enc = encrypt_secret(raw_secret)

    webhook_doc = OutreachWebhook(
        workspace_id=ws_id,
        target_url=req.target_url.strip(),
        secret_enc=secret_enc,
        events=req.events,
        status="active",
    ).model_dump()

    await db.outreach_webhooks.insert_one(webhook_doc)

    # Return the raw secret ONCE upon creation
    return {
        "id": webhook_doc["id"],
        "workspace_id": ws_id,
        "target_url": webhook_doc["target_url"],
        "events": webhook_doc["events"],
        "secret": raw_secret,
        "created_at": webhook_doc["created_at"],
    }


@router.delete("/webhooks/{webhook_id}", dependencies=[require_permission("campaign:create")])
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    res = await db.outreach_webhooks.delete_one({"id": webhook_id, "workspace_id": ws_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return {"status": "deleted", "webhook_id": webhook_id}


@router.post("/webhooks/{webhook_id}/test", dependencies=[require_permission("campaign:create")])
async def test_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    whk = await db.outreach_webhooks.find_one({"id": webhook_id, "workspace_id": ws_id})
    if not whk:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    from outreach.core.crypto import decrypt_secret
    secret = decrypt_secret(whk.get("secret_enc", ""))
    test_data = {
        "test": True,
        "message": "Ping from Unravler Outreach Webhook Dispatcher",
        "workspace_id": ws_id,
    }
    result = await dispatch_webhook(whk["target_url"], secret, "test.ping", test_data)
    return result


# ── API Keys Management ───────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    cursor = db.outreach_api_keys.find({"workspace_id": ws_id}, {"key_hash": 0})
    return await cursor.to_list(length=50)


@router.post("/api-keys", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("billing:manage")])
async def create_api_key(
    req: CreateApiKeyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    token = secrets.token_hex(24)
    raw_api_key = f"unr_live_{token}"
    key_prefix = raw_api_key[:13]
    key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()

    key_doc = OutreachApiKey(
        workspace_id=ws_id,
        name=req.name.strip(),
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=req.scopes,
    ).model_dump()

    await db.outreach_api_keys.insert_one(key_doc)

    return {
        "id": key_doc["id"],
        "name": key_doc["name"],
        "key_prefix": key_prefix,
        "api_key": raw_api_key,  # Returned only on creation
        "scopes": key_doc["scopes"],
        "created_at": key_doc["created_at"],
    }


@router.delete("/api-keys/{key_id}", dependencies=[require_permission("billing:manage")])
async def delete_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    res = await db.outreach_api_keys.delete_one({"id": key_id, "workspace_id": ws_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}


# ── Slack Configuration ───────────────────────────────────────────────────

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


@router.post("/slack", dependencies=[require_permission("campaign:create")])
async def update_slack_config(
    req: SlackConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    if not is_safe_url(req.webhook_url):
        raise HTTPException(status_code=400, detail="Invalid Slack webhook URL")

    now = datetime.now(timezone.utc)
    await db.outreach_integrations.update_one(
        {"workspace_id": ws_id, "provider": "slack"},
        {
            "$set": {
                "status": "connected" if req.enabled else "disabled",
                "access_token_enc": encrypt_secret(req.webhook_url.strip()),
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


@router.post("/slack/test", dependencies=[require_permission("campaign:create")])
async def test_slack_notification(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ws_id = _workspace_id(current_user)
    doc = await db.outreach_integrations.find_one({"workspace_id": ws_id, "provider": "slack"})
    if not doc or not doc.get("access_token_enc"):
        raise HTTPException(status_code=400, detail="Slack integration is not configured")

    from outreach.core.crypto import decrypt_secret
    webhook_url = decrypt_secret(doc["access_token_enc"])

    payload = {
        "text": "🎉 *Unravler Outreach Test Alert*\nYour Slack integration is connected and working!",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🎉 *Unravler Outreach Test Alert*\nYour Slack integration is connected and working! Real-time prospect replies and connection alerts will appear here."
                }
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(webhook_url, json=payload)
        return {"success": 200 <= resp.status_code < 300, "status_code": resp.status_code}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to post to Slack webhook: {str(exc)[:150]}")


# ── Public REST API (For Zapier, Make, and External Scripts) ───────────────

async def authenticate_api_key(
    authorization: str = Header(..., description="Bearer unr_live_..."),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> str:
    """Validates public API key and returns authenticated workspace_id."""
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format")

    raw_key = parts[1].strip()
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_doc = await db.outreach_api_keys.find_one({"key_hash": key_hash})
    if not key_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")

    # Update last_used_at in background
    await db.outreach_api_keys.update_one(
        {"_id": key_doc["_id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc)}}
    )
    return key_doc["workspace_id"]


@public_router.get("/campaigns")
async def public_list_campaigns(
    workspace_id: str = Depends(authenticate_api_key),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List active outreach campaigns in the workspace."""
    cursor = db.outreach_campaigns.find(
        {"workspace_id": workspace_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "stats": 1, "created_at": 1},
    )
    return await cursor.to_list(length=100)


@public_router.post("/leads", status_code=status.HTTP_201_CREATED)
async def public_enroll_lead(
    req: PublicLeadEnrollRequest,
    workspace_id: str = Depends(authenticate_api_key),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Enrolls a lead from Zapier, Make, or custom API scripts into a campaign."""
    campaign = await db.outreach_campaigns.find_one({
        "id": req.campaign_id,
        "workspace_id": workspace_id,
        "is_deleted": {"$ne": True},
    })
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found in this workspace")

    from outreach.models import OutreachLead, LeadState
    from outreach.core.lead_importer import normalize_linkedin_url

    clean_url = normalize_linkedin_url(req.linkedin_url)
    existing = await db.outreach_leads.find_one({
        "workspace_id": workspace_id,
        "campaign_id": req.campaign_id,
        "linkedin_url": clean_url,
    })
    if existing:
        return {"status": "already_enrolled", "lead_id": existing["id"]}

    lead = OutreachLead(
        workspace_id=workspace_id,
        campaign_id=req.campaign_id,
        linkedin_url=clean_url,
        first_name=req.first_name.strip(),
        last_name=req.last_name.strip(),
        company_name=req.company_name.strip(),
        title=req.job_title.strip(),
        email=req.email,
        custom_variables=req.custom_variables,
        state=LeadState.QUEUED,
    ).model_dump()

    await db.outreach_leads.insert_one(lead)
    lead.pop("_id", None)
    return {"status": "enrolled", "lead_id": lead["id"]}
