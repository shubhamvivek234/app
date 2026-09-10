"""
Unravler Audience Hub — Leads API Router.
Provides a unified CRM-style leads management system for creators and agencies.
Leads are captured via Smart Bio newsletter forms and can also be added manually.
"""
import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])


# ── Pydantic Models ──────────────────────────────────────────────────────────

VALID_TAGS = {"subscriber", "lead", "client", "vip", "archived"}
VALID_SOURCES = {"bio", "inbox", "manual", "import"}


class LeadCreate(BaseModel):
    email: str
    name: str = ""
    phone: str = ""
    tag: str = "subscriber"
    notes: str = ""
    source: str = "manual"


class LeadUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    tag: str | None = None
    notes: str | None = None


# ── Helper ────────────────────────────────────────────────────────────────────

def _serialize_lead(lead: dict) -> dict:
    """Convert a MongoDB lead document to a JSON-safe dict."""
    created_at = lead.get("created_at")
    updated_at = lead.get("updated_at")
    return {
        "id": str(lead["_id"]),
        "email": lead.get("email", ""),
        "name": lead.get("name", ""),
        "phone": lead.get("phone", ""),
        "tag": lead.get("tag", "subscriber"),
        "notes": lead.get("notes", ""),
        "source": lead.get("source", "bio"),
        "source_block_id": lead.get("source_block_id"),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at) if updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_leads(
    current_user: CurrentUser,
    db: DB,
    tag: str | None = Query(None, description="Filter by tag"),
    q: str | None = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """List all leads for the current workspace with optional filtering."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    clean_tag = tag if isinstance(tag, str) else None
    clean_q = q.strip() if isinstance(q, str) and q.strip() else None
    actual_page = page if isinstance(page, int) else 1
    actual_limit = limit if isinstance(limit, int) else 50

    query: dict = {"workspace_id": workspace_id}

    if clean_tag and clean_tag in VALID_TAGS:
        query["tag"] = clean_tag

    if clean_q:
        query["$or"] = [
            {"email": {"$regex": re.escape(clean_q), "$options": "i"}},
            {"name": {"$regex": re.escape(clean_q), "$options": "i"}},
        ]

    skip = (actual_page - 1) * actual_limit
    total = await db.workspace_leads.count_documents(query)
    cursor = db.workspace_leads.find(query).sort("created_at", -1).skip(skip).limit(actual_limit)
    leads = await cursor.to_list(length=actual_limit)

    return {
        "leads": [_serialize_lead(lead) for lead in leads],
        "total": total,
        "page": actual_page,
        "limit": actual_limit,
        "pages": (total + actual_limit - 1) // actual_limit if total > 0 else 1,
    }


@router.get("/stats")
async def get_lead_stats(
    current_user: CurrentUser,
    db: DB,
):
    """Get lead count breakdown by tag."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    pipeline = [
        {"$match": {"workspace_id": workspace_id}},
        {"$group": {"_id": "$tag", "count": {"$sum": 1}}},
    ]
    raw = await db.workspace_leads.aggregate(pipeline).to_list(length=20)

    counts = {tag: 0 for tag in VALID_TAGS}
    total = 0
    for r in raw:
        tag_key = r["_id"] or "subscriber"
        counts[tag_key] = counts.get(tag_key, 0) + r["count"]
        total += r["count"]

    return {
        **counts,
        "total": total,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Manually add a new lead to the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    email = body.email.strip().lower()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid email address.",
        )

    # Check for duplicate
    existing = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A lead with email '{email}' already exists.",
        )

    tag = body.tag if body.tag in VALID_TAGS else "subscriber"
    source = body.source if body.source in VALID_SOURCES else "manual"
    now = datetime.now(timezone.utc)

    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "email": email,
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "tag": tag,
        "notes": body.notes.strip(),
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    await db.workspace_leads.insert_one(doc)
    return _serialize_lead(doc)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    body: LeadUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a lead's tag, name, phone, or notes."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    try:
        oid = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lead ID")

    lead = await db.workspace_leads.find_one({"_id": oid, "workspace_id": workspace_id})
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}

    if body.name is not None:
        update_fields["name"] = body.name.strip()
    if body.email is not None:
        clean_email = body.email.strip().lower()
        if clean_email and "@" in clean_email:
            if clean_email != lead.get("email"):
                dup = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": clean_email, "_id": {"$ne": oid}})
                if dup:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A lead with email '{clean_email}' already exists.")
            update_fields["email"] = clean_email
    if body.phone is not None:
        update_fields["phone"] = body.phone.strip()
    if body.tag is not None:
        if body.tag in VALID_TAGS:
            update_fields["tag"] = body.tag
    if body.notes is not None:
        update_fields["notes"] = body.notes.strip()

    await db.workspace_leads.update_one({"_id": oid}, {"$set": update_fields})
    updated = await db.workspace_leads.find_one({"_id": oid})
    return _serialize_lead(updated)


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a lead from the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    try:
        oid = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lead ID")

    result = await db.workspace_leads.delete_one({"_id": oid, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    return {"ok": True, "message": "Lead deleted successfully"}


@router.get("/export")
async def export_leads_csv(
    current_user: CurrentUser,
    db: DB,
    tag: str | None = Query(None),
):
    """Export leads to CSV with optional tag filter."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    clean_tag = tag if isinstance(tag, str) else None
    query: dict = {"workspace_id": workspace_id}
    if clean_tag and clean_tag in VALID_TAGS:
        query["tag"] = clean_tag

    cursor = db.workspace_leads.find(query).sort("created_at", -1)
    leads = await cursor.to_list(length=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Phone", "Tag", "Source", "Notes", "Created At"])
    for lead in leads:
        ts = lead["created_at"].isoformat() if hasattr(lead["created_at"], "isoformat") else str(lead["created_at"])
        writer.writerow([
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("phone", ""),
            lead.get("tag", "subscriber"),
            lead.get("source", "bio"),
            lead.get("notes", ""),
            ts,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=unravler_leads_{int(datetime.now().timestamp())}.csv"},
    )


@router.post("/import")
async def import_leads_csv(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    db: DB = None,
):
    """Bulk import leads from a CSV file. Expects columns: Name, Email, Phone, Tag, Notes."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a .csv file")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    now = datetime.now(timezone.utc)
    imported = 0
    skipped = 0
    errors = []

    for i, row in enumerate(reader):
        email = (row.get("Email") or row.get("email") or "").strip().lower()
        if not email or "@" not in email:
            errors.append(f"Row {i + 2}: Invalid or missing email")
            skipped += 1
            continue

        existing = await db.workspace_leads.find_one({"workspace_id": workspace_id, "email": email})
        if existing:
            skipped += 1
            continue

        name = (row.get("Name") or row.get("name") or "").strip()
        phone = (row.get("Phone") or row.get("phone") or "").strip()
        tag = (row.get("Tag") or row.get("tag") or "subscriber").strip().lower()
        notes = (row.get("Notes") or row.get("notes") or "").strip()

        if tag not in VALID_TAGS:
            tag = "subscriber"

        await db.workspace_leads.insert_one({
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "email": email,
            "name": name,
            "phone": phone,
            "tag": tag,
            "notes": notes,
            "source": "import",
            "created_at": now,
            "updated_at": now,
        })
        imported += 1

    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10],
        "message": f"Imported {imported} leads, skipped {skipped} duplicates/invalid rows.",
    }
