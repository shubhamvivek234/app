"""
Unravler Broadcasts API Router — Cluster B (Monetization Engine).
Handles email campaigns to captured leads, template catalogs, test dispatches,
and direct WhatsApp outreach links.
"""
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB
from api.data.email_templates import EMAIL_TEMPLATES
from utils.email_service import send_email_async, get_email_service_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])


# ── Pydantic Models ──────────────────────────────────────────────────────────

VALID_TARGET_TAGS = {"all", "subscriber", "lead", "client", "vip", "archived"}


class BroadcastCreate(BaseModel):
    name: str = ""
    subject: str
    preview_text: str = ""
    target_tag: str = "all"
    body_markdown: str = ""
    body_html: str = ""
    template_id: Optional[str] = None
    is_draft: bool = False


class BroadcastUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    preview_text: Optional[str] = None
    target_tag: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    template_id: Optional[str] = None
    is_draft: Optional[bool] = None


class EmailPreviewRequest(BaseModel):
    subject: str
    body_html: str
    body_markdown: str = ""
    target_email: Optional[str] = None


class WhatsAppLinksRequest(BaseModel):
    template_message: str
    target_tag: str = "all"


# ── Helper ────────────────────────────────────────────────────────────────────

def _serialize_broadcast(b: dict) -> dict:
    created_at = b.get("created_at")
    sent_at = b.get("sent_at")
    return {
        "id": str(b["_id"]),
        "workspace_id": b.get("workspace_id", ""),
        "name": b.get("name") or b.get("subject", "Untitled Broadcast"),
        "subject": b.get("subject", ""),
        "preview_text": b.get("preview_text", ""),
        "target_tag": b.get("target_tag", "all"),
        "body_markdown": b.get("body_markdown", ""),
        "body_html": b.get("body_html", ""),
        "template_id": b.get("template_id"),
        "status": b.get("status", "draft"),
        "recipients_count": b.get("recipients_count", 0),
        "delivered_count": b.get("delivered_count", 0),
        "failed_count": b.get("failed_count", 0),
        "open_count": b.get("open_count", 0),
        "click_count": b.get("click_count", 0),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None,
        "sent_at": sent_at.isoformat() if hasattr(sent_at, "isoformat") else str(sent_at) if sent_at else None,
    }


def _render_personalized(template_str: str, name: str, creator_name: str) -> str:
    rendered = template_str.replace("{{name}}", name or "there")
    rendered = rendered.replace("{{creator_name}}", creator_name or "Your Creator")
    rendered = rendered.replace("{name}", name or "there")
    rendered = rendered.replace("{creator_name}", creator_name or "Your Creator")
    return rendered


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_broadcasts(
    current_user: CurrentUser,
    db: DB,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List all broadcasts for the current workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    query: dict = {"workspace_id": workspace_id}
    clean_status = status_filter if isinstance(status_filter, str) else None
    if clean_status:
        query["status"] = clean_status

    cursor = db.broadcasts.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return {
        "ok": True,
        "broadcasts": [_serialize_broadcast(doc) for doc in docs],
    }


@router.get("/stats")
async def get_broadcast_stats(
    current_user: CurrentUser,
    db: DB,
):
    """Overall broadcast metrics and email delivery status for the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    total_broadcasts = await db.broadcasts.count_documents({"workspace_id": workspace_id})
    sent_broadcasts = await db.broadcasts.count_documents({"workspace_id": workspace_id, "status": "sent"})

    pipeline = [
        {"$match": {"workspace_id": workspace_id, "status": "sent"}},
        {"$group": {
            "_id": None,
            "total_delivered": {"$sum": "$delivered_count"},
            "total_recipients": {"$sum": "$recipients_count"},
            "total_opens": {"$sum": "$open_count"},
        }}
    ]
    agg_result = await db.broadcasts.aggregate(pipeline).to_list(length=1)
    total_delivered = agg_result[0]["total_delivered"] if agg_result else 0
    total_recipients = agg_result[0]["total_recipients"] if agg_result else 0

    total_subscribers = await db.workspace_leads.count_documents({"workspace_id": workspace_id})
    delivery_rate = round((total_delivered / total_recipients * 100), 1) if total_recipients > 0 else 100.0

    provider_status = get_email_service_status()

    return {
        "ok": True,
        "total_campaigns": total_broadcasts,
        "sent_campaigns": sent_broadcasts,
        "total_delivered": total_delivered,
        "total_subscribers": total_subscribers,
        "delivery_rate": delivery_rate,
        "email_service": {
            "provider": provider_status.get("provider", "mock"),
            "configured": provider_status.get("configured", False),
            "sender_email": provider_status.get("sender_email"),
        }
    }


@router.get("/templates")
async def list_templates():
    """Return pre-built responsive email templates catalog."""
    return {
        "ok": True,
        "templates": EMAIL_TEMPLATES,
    }


@router.get("/{broadcast_id}")
async def get_broadcast(
    broadcast_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Retrieve details of a single broadcast."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(broadcast_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")

    doc = await db.broadcasts.find_one({"_id": oid, "workspace_id": workspace_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    return {
        "ok": True,
        "broadcast": _serialize_broadcast(doc),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    body: BroadcastCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new broadcast campaign (draft or ready)."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    # Estimate recipient count
    lead_query: dict = {"workspace_id": workspace_id}
    if body.target_tag and body.target_tag != "all":
        lead_query["tag"] = body.target_tag
    estimated_recipients = await db.workspace_leads.count_documents(lead_query)

    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "name": body.name or body.subject,
        "subject": body.subject,
        "preview_text": body.preview_text,
        "target_tag": body.target_tag if body.target_tag in VALID_TARGET_TAGS else "all",
        "body_markdown": body.body_markdown,
        "body_html": body.body_html or f"<p>{body.body_markdown}</p>",
        "template_id": body.template_id,
        "status": "draft" if body.is_draft else "ready",
        "recipients_count": estimated_recipients,
        "delivered_count": 0,
        "failed_count": 0,
        "open_count": 0,
        "click_count": 0,
        "created_at": now,
        "sent_at": None,
    }
    await db.broadcasts.insert_one(doc)
    return {
        "ok": True,
        "broadcast": _serialize_broadcast(doc),
        "message": "Broadcast created successfully",
    }


@router.patch("/{broadcast_id}")
async def update_broadcast(
    broadcast_id: str,
    body: BroadcastUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a broadcast campaign before dispatch."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(broadcast_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")

    existing = await db.broadcasts.find_one({"_id": oid, "workspace_id": workspace_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    if existing.get("status") == "sent":
        raise HTTPException(status_code=400, detail="Cannot edit a broadcast that has already been sent")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.subject is not None:
        updates["subject"] = body.subject
    if body.preview_text is not None:
        updates["preview_text"] = body.preview_text
    if body.target_tag is not None and body.target_tag in VALID_TARGET_TAGS:
        updates["target_tag"] = body.target_tag
        lead_query = {"workspace_id": workspace_id}
        if body.target_tag != "all":
            lead_query["tag"] = body.target_tag
        updates["recipients_count"] = await db.workspace_leads.count_documents(lead_query)
    if body.body_markdown is not None:
        updates["body_markdown"] = body.body_markdown
    if body.body_html is not None:
        updates["body_html"] = body.body_html
    if body.template_id is not None:
        updates["template_id"] = body.template_id
    if body.is_draft is not None:
        updates["status"] = "draft" if body.is_draft else "ready"

    if updates:
        await db.broadcasts.update_one({"_id": oid}, {"$set": updates})

    updated_doc = await db.broadcasts.find_one({"_id": oid})
    return {
        "ok": True,
        "broadcast": _serialize_broadcast(updated_doc),
        "message": "Broadcast updated successfully",
    }


@router.post("/{broadcast_id}/send")
async def send_broadcast(
    broadcast_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """
    Dispatch a broadcast campaign to all leads matching the targeted audience tag.
    Uses unified email service (SES/Resend with mock fallback).
    """
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(broadcast_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")

    broadcast = await db.broadcasts.find_one({"_id": oid, "workspace_id": workspace_id})
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    target_tag = broadcast.get("target_tag", "all")
    lead_query: dict = {"workspace_id": workspace_id}
    if target_tag and target_tag != "all":
        lead_query["tag"] = target_tag

    cursor = db.workspace_leads.find(lead_query)
    leads = await cursor.to_list(length=1000)

    if not leads:
        raise HTTPException(
            status_code=400,
            detail=f"No leads found matching tag '{target_tag}'. Add leads in the Audience Hub before sending.",
        )

    creator_name = current_user.get("display_name") or current_user.get("name") or "Your Creator"
    subject_raw = broadcast.get("subject", "Update from Unravler")
    html_raw = broadcast.get("body_html") or f"<p>{broadcast.get('body_markdown', '')}</p>"
    text_raw = broadcast.get("body_markdown") or broadcast.get("subject", "")

    success_count = 0
    fail_count = 0

    # Dispatch emails (batched to prevent overwhelming connections)
    for lead in leads:
        lead_email = lead.get("email")
        if not lead_email or "@" not in lead_email:
            fail_count += 1
            continue

        lead_name = lead.get("name") or "there"
        p_subject = _render_personalized(subject_raw, lead_name, creator_name)
        p_html = _render_personalized(html_raw, lead_name, creator_name)
        p_text = _render_personalized(text_raw, lead_name, creator_name)

        sent = await send_email_async(
            to=lead_email,
            subject=p_subject,
            html=p_html,
            text=p_text,
            sender_name=creator_name,
        )
        if sent:
            success_count += 1
        else:
            fail_count += 1

    now = datetime.now(timezone.utc)
    await db.broadcasts.update_one(
        {"_id": oid},
        {"$set": {
            "status": "sent",
            "sent_at": now,
            "recipients_count": len(leads),
            "delivered_count": success_count,
            "failed_count": fail_count,
        }}
    )

    updated_doc = await db.broadcasts.find_one({"_id": oid})
    return {
        "ok": True,
        "message": f"Broadcast successfully dispatched to {success_count} recipients ({fail_count} skipped/failed).",
        "broadcast": _serialize_broadcast(updated_doc),
    }


@router.post("/test-send")
async def send_test_email(
    body: EmailPreviewRequest,
    current_user: CurrentUser,
):
    """Deliver an instant test preview email to the current user's email."""
    recipient_email = (body.target_email or current_user.get("email") or "").strip()
    if not recipient_email or "@" not in recipient_email:
        raise HTTPException(status_code=400, detail="No valid test recipient email address available.")

    creator_name = current_user.get("display_name") or current_user.get("name") or "Your Creator"
    test_subject = f"[PREVIEW] {_render_personalized(body.subject, 'Preview User', creator_name)}"
    test_html = _render_personalized(body.body_html, "Preview User", creator_name)
    test_text = _render_personalized(body.body_markdown or body.subject, "Preview User", creator_name)

    sent = await send_email_async(
        to=recipient_email,
        subject=test_subject,
        html=test_html,
        text=test_text,
        sender_name=creator_name,
    )
    if not sent:
        return {
            "ok": True,
            "delivered": False,
            "simulated": True,
            "recipient": recipient_email,
            "message": "Email delivery simulated (mock mode or unconfigured provider). In production, set SENDER_EMAIL and SES or Resend keys.",
        }

    return {
        "ok": True,
        "delivered": True,
        "recipient": recipient_email,
        "message": f"Test preview email sent to {recipient_email}.",
    }


@router.delete("/{broadcast_id}")
async def delete_broadcast(
    broadcast_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a broadcast record."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(broadcast_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")

    res = await db.broadcasts.delete_one({"_id": oid, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    return {"ok": True, "message": "Broadcast deleted successfully"}


@router.post("/whatsapp-links")
async def generate_whatsapp_outreach_links(
    body: WhatsAppLinksRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Generate one-click WhatsApp click-to-chat links for leads with phone numbers.
    Personalizes {{name}} and {{creator_name}} into url-encoded wa.me links.
    """
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    target_tag = body.target_tag or "all"
    creator_name = current_user.get("display_name") or current_user.get("name") or "Your Creator"

    lead_query: dict = {"workspace_id": workspace_id}
    if target_tag != "all":
        lead_query["tag"] = target_tag

    cursor = db.workspace_leads.find(lead_query)
    leads = await cursor.to_list(length=500)

    results = []
    leads_with_phone = 0

    for lead in leads:
        raw_phone = lead.get("phone", "") or ""
        # Clean non-digit characters except leading plus
        clean_phone = re.sub(r"[^\d+]", "", raw_phone)
        clean_phone = clean_phone.lstrip("+")
        lead_name = lead.get("name") or "there"

        personalized_msg = _render_personalized(body.template_message, lead_name, creator_name)
        encoded_msg = urllib.parse.quote(personalized_msg)

        has_phone = bool(clean_phone and len(clean_phone) >= 7)
        if has_phone:
            leads_with_phone += 1
            wa_link = f"https://wa.me/{clean_phone}?text={encoded_msg}"
        else:
            wa_link = None

        results.append({
            "lead_id": str(lead["_id"]),
            "name": lead_name,
            "email": lead.get("email", ""),
            "phone": raw_phone,
            "clean_phone": clean_phone if has_phone else None,
            "tag": lead.get("tag", "subscriber"),
            "has_phone": has_phone,
            "wa_link": wa_link,
            "personalized_preview": personalized_msg,
        })

    return {
        "ok": True,
        "total_leads": len(leads),
        "leads_with_phone": leads_with_phone,
        "outreach_items": results,
    }
