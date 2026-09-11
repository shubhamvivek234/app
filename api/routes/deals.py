"""
Unravler Audience Hub — Deals API Router.
Brand deal / client project pipeline tracker for creators and agencies.
Stages: lead → contacted → proposal → negotiation → won | lost
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deals", tags=["deals"])


# ── Pydantic Models ──────────────────────────────────────────────────────────

VALID_STAGES = {"lead", "contacted", "proposal", "negotiation", "won", "lost"}
VALID_PRIORITIES = {"low", "medium", "high"}


class DealCreate(BaseModel):
    title: str = Field(..., max_length=200)
    contact_name: str = ""
    contact_email: str = ""
    value: float = 0
    currency: str = "INR"
    stage: str = "lead"
    priority: str = "medium"
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    due_date: datetime | None = None


class DealUpdate(BaseModel):
    title: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    value: float | None = None
    currency: str | None = None
    stage: str | None = None
    priority: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    due_date: datetime | None = None


# ── Helper ────────────────────────────────────────────────────────────────────

def _serialize_deal(deal: dict) -> dict:
    """Convert a MongoDB deal document to a JSON-safe dict."""
    created_at = deal.get("created_at")
    updated_at = deal.get("updated_at")
    due_date = deal.get("due_date")
    return {
        "id": str(deal["_id"]),
        "title": deal.get("title", ""),
        "contact_name": deal.get("contact_name", ""),
        "contact_email": deal.get("contact_email", ""),
        "value": deal.get("value", 0),
        "currency": deal.get("currency", "INR"),
        "stage": deal.get("stage", "lead"),
        "priority": deal.get("priority", "medium"),
        "notes": deal.get("notes", ""),
        "tags": deal.get("tags", []),
        "due_date": due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date) if due_date else None,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at) if updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_deals(
    current_user: CurrentUser,
    db: DB,
    stage: str | None = Query(None),
    priority: str | None = Query(None),
):
    """List all deals for the current workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    clean_stage = stage if isinstance(stage, str) else None
    clean_priority = priority if isinstance(priority, str) else None
    query: dict = {"workspace_id": workspace_id}
    if clean_stage and clean_stage in VALID_STAGES:
        query["stage"] = clean_stage
    if clean_priority and clean_priority in VALID_PRIORITIES:
        query["priority"] = clean_priority

    cursor = db.deals.find(query).sort("updated_at", -1)
    deals = await cursor.to_list(length=500)

    return {
        "deals": [_serialize_deal(d) for d in deals],
        "total": len(deals),
    }


@router.get("/stats")
async def get_deal_stats(
    current_user: CurrentUser,
    db: DB,
):
    """Get deal pipeline statistics."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    pipeline = [
        {"$match": {"workspace_id": workspace_id}},
        {"$group": {
            "_id": "$stage",
            "count": {"$sum": 1},
            "total_value": {"$sum": "$value"},
        }},
    ]
    raw = await db.deals.aggregate(pipeline).to_list(length=20)

    stages = {s: {"count": 0, "value": 0} for s in VALID_STAGES}
    total_count = 0
    total_value = 0
    won_value = 0

    for r in raw:
        stage_key = r["_id"] or "lead"
        if stage_key in stages:
            stages[stage_key] = {"count": r["count"], "value": r["total_value"]}
        total_count += r["count"]
        total_value += r["total_value"]
        if stage_key == "won":
            won_value = r["total_value"]

    return {
        "stages": stages,
        "total_deals": total_count,
        "total_pipeline_value": total_value,
        "won_value": won_value,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new deal in the pipeline."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    stage = body.stage if body.stage in VALID_STAGES else "lead"
    priority = body.priority if body.priority in VALID_PRIORITIES else "medium"
    now = datetime.now(timezone.utc)

    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "title": body.title.strip(),
        "contact_name": body.contact_name.strip(),
        "contact_email": body.contact_email.strip().lower() if body.contact_email else "",
        "value": max(0, body.value),
        "currency": body.currency.upper()[:3] if body.currency else "INR",
        "stage": stage,
        "priority": priority,
        "notes": body.notes.strip(),
        "tags": [t.strip().lower() for t in body.tags[:10]],
        "due_date": body.due_date,
        "created_at": now,
        "updated_at": now,
    }
    await db.deals.insert_one(doc)
    return _serialize_deal(doc)


@router.patch("/{deal_id}")
async def update_deal(
    deal_id: str,
    body: DealUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a deal (change stage, value, etc.)."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    try:
        oid = ObjectId(deal_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid deal ID")

    deal = await db.deals.find_one({"_id": oid, "workspace_id": workspace_id})
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}

    if body.title is not None:
        update_fields["title"] = body.title.strip()
    if body.contact_name is not None:
        update_fields["contact_name"] = body.contact_name.strip()
    if body.contact_email is not None:
        update_fields["contact_email"] = body.contact_email.strip().lower()
    if body.value is not None:
        update_fields["value"] = max(0, body.value)
    if body.currency is not None:
        update_fields["currency"] = body.currency.upper()[:3]
    if body.stage is not None and body.stage in VALID_STAGES:
        update_fields["stage"] = body.stage
    if body.priority is not None and body.priority in VALID_PRIORITIES:
        update_fields["priority"] = body.priority
    if body.notes is not None:
        update_fields["notes"] = body.notes.strip()
    if body.tags is not None:
        update_fields["tags"] = [t.strip().lower() for t in body.tags[:10]]
    if body.due_date is not None:
        update_fields["due_date"] = body.due_date

    await db.deals.update_one({"_id": oid}, {"$set": update_fields})
    updated = await db.deals.find_one({"_id": oid})

    if body.stage is not None and body.stage in VALID_STAGES and body.stage != deal.get("stage"):
        try:
            from api.routes.automations import dispatch_automation_event
            await dispatch_automation_event(
                "deal.stage_changed",
                workspace_id,
                {
                    "deal_id": deal_id,
                    "title": updated.get("title", ""),
                    "contact_name": updated.get("contact_name", ""),
                    "contact_email": updated.get("contact_email", ""),
                    "old_stage": deal.get("stage"),
                    "new_stage": body.stage,
                    "value": updated.get("value", 0),
                    "currency": updated.get("currency", "INR"),
                },
                db,
            )
        except Exception as exc:
            logger.warning("Failed to dispatch automation for deal.stage_changed: %s", exc)

    return _serialize_deal(updated)


@router.delete("/{deal_id}")
async def delete_deal(
    deal_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a deal from the pipeline."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]

    try:
        oid = ObjectId(deal_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid deal ID")

    result = await db.deals.delete_one({"_id": oid, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    return {"ok": True, "message": "Deal deleted successfully"}
