"""
Unravler Automations Engine & API Router — Cluster D (Automation Layer).
Provides reactive event-driven automations linking Audience CRM, Smart Bio,
Campaigns, and External Webhooks (Slack/Discord/Zapier/Email).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB
from utils.email_service import send_email_async
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automations", tags=["automations"])


# ── Supported Triggers & Actions ──────────────────────────────────────────────

VALID_TRIGGER_TYPES = {
    "lead.created",        # When a lead is captured via Smart Bio or manually added
    "deal.stage_changed",  # When a deal stage changes (e.g. to "won" or "contacted")
    "feedback.received",   # When an NPS/star rating is submitted on Smart Bio
    "broadcast.sent",      # When an email broadcast campaign is sent
}

VALID_ACTION_TYPES = {
    "send_email",          # Send automated email via SES/Resend
    "create_deal",         # Auto-create a deal in CRM pipeline
    "dispatch_webhook",    # Outbound webhook to Slack/Discord/Zapier/custom URL
    "tag_lead",            # Update lead tag (e.g. promote to "vip" or "client")
}


# ── Preset Recipes Catalog ───────────────────────────────────────────────────

PRESET_RECIPES = [
    {
        "id": "welcome_email_on_lead",
        "name": "Instant Welcome Email on Lead Capture",
        "description": "Automatically send a personalized welcome email whenever a visitor subscribes on your Smart Bio.",
        "category": "Email & Outreach",
        "icon": "mail",
        "trigger_type": "lead.created",
        "trigger_config": {},
        "action_type": "send_email",
        "action_config": {
            "subject": "Welcome! So glad to have you here 🎉",
            "body": "Hey {{name}},\n\nThank you for connecting with us! We're excited to have you in our community.\n\nWarmly,\n{{creator_name}}",
        },
    },
    {
        "id": "lead_to_deal_pipeline",
        "name": "Auto-Create Deal from High-Intent Leads",
        "description": "Automatically create a new card in your CRM Deals pipeline whenever a new lead arrives.",
        "category": "CRM & Sales",
        "icon": "kanban",
        "trigger_type": "lead.created",
        "trigger_config": {},
        "action_type": "create_deal",
        "action_config": {
            "title": "Bio Lead: {{name}}",
            "stage": "lead",
            "value": 0.0,
            "currency": "INR",
            "priority": "medium",
        },
    },
    {
        "id": "webhook_notification",
        "name": "Instant Slack / Discord Webhook Notification",
        "description": "Post a real-time notification to your team's Slack or Discord channel when a new lead is captured.",
        "category": "Integrations",
        "icon": "webhook",
        "trigger_type": "lead.created",
        "trigger_config": {},
        "action_type": "dispatch_webhook",
        "action_config": {
            "webhook_url": "https://hooks.slack.com/services/...",
        },
    },
    {
        "id": "deal_won_celebration",
        "name": "Customer Onboarding Note on Won Deal",
        "description": "Send a warm onboarding email to the client whenever a deal is moved to the Won stage.",
        "category": "CRM & Sales",
        "icon": "check-circle",
        "trigger_type": "deal.stage_changed",
        "trigger_config": {"target_stage": "won"},
        "action_type": "send_email",
        "action_config": {
            "subject": "Excited to partner together! 🚀",
            "body": "Hey {{contact_name}},\n\nThrilled to officially kick off our collaboration! Here are our next steps.\n\nBest,\n{{creator_name}}",
        },
    },
    {
        "id": "vip_tag_on_5star_rating",
        "name": "Promote to VIP on 5-Star Feedback",
        "description": "Automatically tag any contact as VIP if they leave a 4 or 5-star rating on your bio page.",
        "category": "Audience Intelligence",
        "icon": "star",
        "trigger_type": "feedback.received",
        "trigger_config": {"min_score": 4},
        "action_type": "tag_lead",
        "action_config": {"target_tag": "vip"},
    },
]


# ── Pydantic Models ──────────────────────────────────────────────────────────

class AutomationCreate(BaseModel):
    name: str
    description: str = ""
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    action_type: str
    action_config: dict = Field(default_factory=dict)
    is_active: bool = True


class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    action_type: Optional[str] = None
    action_config: Optional[dict] = None
    is_active: Optional[bool] = None


class TestAutomationRequest(BaseModel):
    __test__ = False
    sample_payload: dict = Field(default_factory=dict)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_workspace_id(current_user: dict) -> str:
    return str(
        current_user.get("default_workspace_id")
        or current_user.get("current_workspace_id")
        or current_user.get("workspace_id")
        or current_user.get("user_id")
        or current_user.get("id")
        or current_user.get("_id")
        or "default"
    )


def _serialize_automation(doc: dict) -> dict:
    created_at = doc.get("created_at")
    last_executed_at = doc.get("last_executed_at")
    return {
        "id": str(doc["_id"]),
        "workspace_id": doc.get("workspace_id", ""),
        "name": doc.get("name", "Untitled Automation"),
        "description": doc.get("description", ""),
        "trigger_type": doc.get("trigger_type", ""),
        "trigger_config": doc.get("trigger_config", {}),
        "action_type": doc.get("action_type", ""),
        "action_config": doc.get("action_config", {}),
        "is_active": doc.get("is_active", True),
        "total_executions": doc.get("total_executions", 0),
        "last_executed_at": last_executed_at.isoformat() if hasattr(last_executed_at, "isoformat") else str(last_executed_at) if last_executed_at else None,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None,
    }


def _serialize_log(doc: dict) -> dict:
    ts = doc.get("timestamp")
    return {
        "id": str(doc["_id"]),
        "automation_id": str(doc.get("automation_id", "")),
        "automation_name": doc.get("automation_name", "Automation"),
        "workspace_id": doc.get("workspace_id", ""),
        "trigger_type": doc.get("trigger_type", ""),
        "action_type": doc.get("action_type", ""),
        "status": doc.get("status", "success"),
        "details": doc.get("details", ""),
        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None,
    }


# ── Execution Engine ─────────────────────────────────────────────────────────

async def dispatch_automation_event(
    event_type: str,
    workspace_id: str,
    payload: dict,
    db: Any,
) -> int:
    """
    Central Automation Engine dispatcher.
    Finds matching active automation rules for (workspace_id, trigger_type)
    and executes configured downstream actions asynchronously.
    """
    if not workspace_id or not event_type:
        return 0

    cursor = db.automations.find({
        "workspace_id": workspace_id,
        "trigger_type": event_type,
        "is_active": True,
    })
    rules = await cursor.to_list(length=50)
    if not rules:
        return 0

    now = datetime.now(timezone.utc)
    executed_count = 0

    for rule in rules:
        trigger_config = rule.get("trigger_config", {})
        action_type = rule.get("action_type")
        action_config = rule.get("action_config", {})
        rule_name = rule.get("name", "Automation")

        # 1. Evaluate Trigger Conditions
        if event_type == "deal.stage_changed":
            target_stage = trigger_config.get("target_stage")
            if target_stage and payload.get("new_stage") != target_stage:
                continue

        if event_type == "feedback.received":
            min_score = trigger_config.get("min_score")
            if min_score and payload.get("score", 0) < min_score:
                continue

        # 2. Execute Action
        action_status = "success"
        action_details = ""

        try:
            if action_type == "send_email":
                to_email = payload.get("email") or payload.get("contact_email")
                if to_email and "@" in to_email:
                    name = payload.get("name") or payload.get("contact_name") or "there"
                    subject = action_config.get("subject", "Hello from Unravler")
                    subject = subject.replace("{{name}}", name).replace("{{contact_name}}", name)

                    raw_body = action_config.get("body", "Thank you for reaching out!")
                    body_text = raw_body.replace("{{name}}", name).replace("{{contact_name}}", name).replace("{{creator_name}}", "Your Creator")
                    body_html = f"<div style='font-family:-apple-system,sans-serif;line-height:1.6;color:#18181b;'><p>{body_text.replace(chr(10), '<br>')}</p></div>"

                    await send_email_async(
                        to=to_email,
                        subject=subject,
                        html=body_html,
                        text=body_text,
                        sender_name="Unravler Automation",
                    )
                    action_details = f"Sent email to {to_email}"
                else:
                    action_status = "failed"
                    action_details = "No recipient email found in event payload"

            elif action_type == "create_deal":
                name = payload.get("name") or payload.get("email", "New Lead")
                title = action_config.get("title", f"Lead: {name}").replace("{{name}}", name)
                deal_doc = {
                    "_id": ObjectId(),
                    "workspace_id": workspace_id,
                    "title": title,
                    "contact_name": payload.get("name", ""),
                    "contact_email": payload.get("email", ""),
                    "value": float(action_config.get("value", 0.0)),
                    "currency": action_config.get("currency", "INR"),
                    "stage": action_config.get("stage", "lead"),
                    "priority": action_config.get("priority", "medium"),
                    "notes": f"Auto-created by automation '{rule_name}' from bio lead capture.",
                    "tags": ["auto-lead", "smart-bio"],
                    "due_date": None,
                    "created_at": now,
                    "updated_at": now,
                }
                await db.deals.insert_one(deal_doc)
                action_details = f"Created deal '{title}' in stage '{deal_doc['stage']}'"

            elif action_type == "dispatch_webhook":
                webhook_url = action_config.get("webhook_url", "").strip()
                if webhook_url and webhook_url.startswith("https://") and is_safe_url(webhook_url):
                    import httpx
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        webhook_body = {
                            "event": event_type,
                            "automation": rule_name,
                            "timestamp": now.isoformat(),
                            "data": payload,
                        }
                        res = await client.post(webhook_url, json=webhook_body)
                        action_details = f"Dispatched webhook to {webhook_url} (HTTP {res.status_code})"
                else:
                    action_status = "failed"
                    action_details = f"Invalid or unsafe webhook URL: {webhook_url}"

            elif action_type == "tag_lead":
                target_tag = action_config.get("target_tag", "vip")
                lead_email = payload.get("email")
                if lead_email:
                    res = await db.workspace_leads.update_many(
                        {"workspace_id": workspace_id, "email": lead_email},
                        {"$set": {"tag": target_tag, "updated_at": now}}
                    )
                    action_details = f"Tagged lead {lead_email} as '{target_tag}' ({res.modified_count} updated)"
                else:
                    action_status = "failed"
                    action_details = "No lead email present in event payload to tag"

            else:
                action_status = "failed"
                action_details = f"Unsupported action type: {action_type}"

        except Exception as exc:
            logger.error("Automation rule '%s' execution failed: %s", rule_name, exc, exc_info=True)
            action_status = "failed"
            action_details = f"Error: {str(exc)}"

        # 3. Log execution
        await db.automation_logs.insert_one({
            "_id": ObjectId(),
            "automation_id": rule["_id"],
            "automation_name": rule_name,
            "workspace_id": workspace_id,
            "trigger_type": event_type,
            "action_type": action_type,
            "status": action_status,
            "details": action_details,
            "timestamp": now,
        })

        # 4. Increment rule executions count
        await db.automations.update_one(
            {"_id": rule["_id"]},
            {
                "$inc": {"total_executions": 1},
                "$set": {"last_executed_at": now},
            }
        )
        executed_count += 1

    return executed_count


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_automations(
    current_user: CurrentUser,
    db: DB,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List all automations for the active workspace."""
    workspace_id = _get_workspace_id(current_user)
    query: dict = {"workspace_id": workspace_id}

    clean_status = status_filter if isinstance(status_filter, str) else None
    if clean_status == "active":
        query["is_active"] = True
    elif clean_status == "paused":
        query["is_active"] = False

    cursor = db.automations.find(query).sort("created_at", -1)
    rules = await cursor.to_list(length=100)

    # Calculate overall stats
    total_count = await db.automations.count_documents({"workspace_id": workspace_id})
    active_count = await db.automations.count_documents({"workspace_id": workspace_id, "is_active": True})
    total_logs = await db.automation_logs.count_documents({"workspace_id": workspace_id})
    successful_logs = await db.automation_logs.count_documents({"workspace_id": workspace_id, "status": "success"})
    success_rate = round((successful_logs / total_logs * 100), 1) if total_logs > 0 else 100.0

    return {
        "ok": True,
        "automations": [_serialize_automation(r) for r in rules],
        "stats": {
            "total_rules": total_count,
            "active_rules": active_count,
            "total_executions": total_logs,
            "success_rate": success_rate,
        }
    }


@router.get("/recipes")
async def get_preset_recipes():
    """Retrieve catalog of pre-built automation recipes."""
    return {
        "ok": True,
        "recipes": PRESET_RECIPES,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new automation rule for the current workspace."""
    workspace_id = _get_workspace_id(current_user)

    if body.trigger_type not in VALID_TRIGGER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trigger_type. Must be one of {sorted(VALID_TRIGGER_TYPES)}",
        )

    if body.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_type. Must be one of {sorted(VALID_ACTION_TYPES)}",
        )

    now = datetime.now(timezone.utc)
    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "name": body.name.strip() or "Untitled Automation",
        "description": body.description.strip(),
        "trigger_type": body.trigger_type,
        "trigger_config": body.trigger_config,
        "action_type": body.action_type,
        "action_config": body.action_config,
        "is_active": body.is_active,
        "total_executions": 0,
        "last_executed_at": None,
        "created_at": now,
        "updated_at": now,
    }

    await db.automations.insert_one(doc)
    return {
        "ok": True,
        "automation": _serialize_automation(doc),
        "message": f"Automation '{doc['name']}' created successfully.",
    }


@router.get("/logs")
async def get_automation_logs(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
):
    """List execution history logs for workspace automations."""
    workspace_id = _get_workspace_id(current_user)
    cursor = db.automation_logs.find({"workspace_id": workspace_id}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return {
        "ok": True,
        "logs": [_serialize_log(d) for d in docs],
    }


@router.get("/{automation_id}")
async def get_automation(
    automation_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Fetch single automation rule by ID."""
    workspace_id = _get_workspace_id(current_user)
    if not ObjectId.is_valid(automation_id):
        raise HTTPException(status_code=400, detail="Invalid automation ID")

    doc = await db.automations.find_one({"_id": ObjectId(automation_id), "workspace_id": workspace_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Automation rule not found")

    return {"ok": True, "automation": _serialize_automation(doc)}


@router.patch("/{automation_id}")
async def update_automation(
    automation_id: str,
    body: AutomationUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update automation rule settings or toggle active state."""
    workspace_id = _get_workspace_id(current_user)
    if not ObjectId.is_valid(automation_id):
        raise HTTPException(status_code=400, detail="Invalid automation ID")

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        update_fields["name"] = body.name.strip()
    if body.description is not None:
        update_fields["description"] = body.description.strip()
    if body.trigger_type is not None:
        if body.trigger_type not in VALID_TRIGGER_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid trigger_type: {body.trigger_type}")
        update_fields["trigger_type"] = body.trigger_type
    if body.trigger_config is not None:
        update_fields["trigger_config"] = body.trigger_config
    if body.action_type is not None:
        if body.action_type not in VALID_ACTION_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid action_type: {body.action_type}")
        update_fields["action_type"] = body.action_type
    if body.action_config is not None:
        update_fields["action_config"] = body.action_config
    if body.is_active is not None:
        update_fields["is_active"] = body.is_active

    res = await db.automations.find_one_and_update(
        {"_id": ObjectId(automation_id), "workspace_id": workspace_id},
        {"$set": update_fields},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Automation not found")

    return {
        "ok": True,
        "automation": _serialize_automation(res),
        "message": "Automation updated successfully.",
    }


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete an automation rule."""
    workspace_id = _get_workspace_id(current_user)
    if not ObjectId.is_valid(automation_id):
        raise HTTPException(status_code=400, detail="Invalid automation ID")

    res = await db.automations.delete_one({"_id": ObjectId(automation_id), "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")

    return {"ok": True, "message": "Automation rule deleted successfully."}


@router.post("/{automation_id}/test")
async def simulate_automation_test(
    automation_id: str,
    body: TestAutomationRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Execute a dry-run test fire of a specific automation rule."""
    workspace_id = _get_workspace_id(current_user)
    if not ObjectId.is_valid(automation_id):
        raise HTTPException(status_code=400, detail="Invalid automation ID")

    rule = await db.automations.find_one({"_id": ObjectId(automation_id), "workspace_id": workspace_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Automation not found")

    sample_payload = body.sample_payload or {
        "email": current_user.get("email") or "test@example.com",
        "name": current_user.get("display_name") or "Sample Contact",
        "score": 5,
        "new_stage": "won",
    }

    # Execute single rule logic
    action_type = rule.get("action_type")
    rule_name = rule.get("name")
    now = datetime.now(timezone.utc)

    action_details = f"Test execution for '{rule_name}' with action '{action_type}'"
    simulated_result = {
        "ok": True,
        "success": True,
        "dry_run": True,
        "rule_id": automation_id,
        "rule_name": rule_name,
        "trigger_type": rule.get("trigger_type"),
        "action_type": action_type,
        "simulated": True,
        "details": action_details,
        "timestamp": now.isoformat(),
    }

    # Record test log
    await db.automation_logs.insert_one({
        "_id": ObjectId(),
        "automation_id": rule["_id"],
        "automation_name": f"[TEST] {rule_name}",
        "workspace_id": workspace_id,
        "trigger_type": rule.get("trigger_type"),
        "action_type": action_type,
        "status": "success",
        "is_dry_run": True,
        "details": f"Dry-run test fired manually by creator: {action_details}",
        "timestamp": now,
    })

    return simulated_result
