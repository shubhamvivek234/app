"""
Phase 3: Leads CRM API endpoints.
Provides bulk import, search ingestion, CRM filtering, and Do-Not-Contact management.
"""
import logging
import csv
import io
import json
import re
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.lead_importer import LeadImporter, normalize_linkedin_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["LinkedIn Outreach Leads CRM"])


def _user_id(current_user: dict) -> str:
    return str(current_user.get("user_id") or current_user.get("id") or current_user.get("_id") or "")


def _workspace_id(current_user: dict) -> str:
    return str(
        current_user.get("default_workspace_id")
        or current_user.get("current_workspace_id")
        or current_user.get("workspace_id")
        or _user_id(current_user)
        or "default_ws"
    )


def _campaign_filter(campaign_id: str, current_user: dict) -> dict[str, Any]:
    user_id = _user_id(current_user)
    return {
        "id": campaign_id,
        "is_deleted": {"$ne": True},
        "$or": [
            {"user_id": user_id},
            {"workspace_id": _workspace_id(current_user)},
            {"workspace_id": user_id},
        ],
    }


async def _require_campaign(campaign_id: str, current_user: dict, db: AsyncIOMotorDatabase) -> dict:
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


# ── DTOs ───────────────────────────────────────────────────────────────────

class ImportCSVRequest(BaseModel):
    campaign_id: str
    csv_text: str = Field(..., description="Raw CSV content string")
    custom_mapping: dict[str, str] | None = None
    skip_already_contacted: bool = True
    skip_do_not_contact: bool = True


class ImportSearchRequest(BaseModel):
    campaign_id: str
    search_url: str
    search_type: str = Field(default="basic", description="'basic' | 'sales_nav' | 'post_engagers'")
    max_leads: int = Field(default=100, le=1000)


class DoNotContactRequest(BaseModel):
    linkedin_url: str
    reason: str | None = None


class LeadFinderPreviewRequest(BaseModel):
    title: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    connection_degree: str | None = None
    has_posted_recently: bool = False
    changed_jobs: bool = False
    mentioned_in_news: bool = False
    keywords: str | None = None
    limit: int = Field(default=15, ge=1, le=50)


class LeadFinderEnrollRequest(BaseModel):
    campaign_id: str
    leads: list[dict[str, Any]]


class ImportPostEngagersRequest(BaseModel):
    campaign_id: str
    post_url: str
    push_option: str = Field(default="Only existing comments/likes", description="Push option")
    export_likes: bool = True
    export_comments: bool = True
    max_leads: int = Field(default=50, le=500)


class UpdateLeadStageRequest(BaseModel):
    pipeline_stage: str = Field(..., description="'unassigned' | 'in_campaign' | 'contacted' | 'replied' | 'call_booked'")


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/import-csv")
async def import_leads_csv(
    req: ImportCSVRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Parses and ingests a CSV list of LinkedIn leads into a specific campaign with deduplication.
    """
    workspace_id = _workspace_id(current_user)
    campaign = await _require_campaign(req.campaign_id, current_user, db)
    if campaign.get("status") == "warming_up":
        raise HTTPException(status_code=409, detail="Pause conditional launch before changing its lead cohort")
    if campaign.get("status") == "active":
        linked_list_count = await db.outreach_engage_lists.count_documents({
            "campaign_id": req.campaign_id, "workspace_id": workspace_id,
        })
        if linked_list_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This active campaign has an Engage warm-up list. Import into a new draft campaign so new contacts complete warm-up before launch.",
            )
        sender_count = await db.outreach_accounts.count_documents({
            "id": {"$in": campaign.get("sender_account_ids", [])},
            "workspace_id": workspace_id,
            "status": "active",
        })
        sequence = await db.outreach_sequences.find_one({
            "campaign_id": req.campaign_id, "is_deleted": {"$ne": True},
        })
        if not sender_count or not (sequence or {}).get("compiled_dag", {}).get("root_node_ids"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This campaign needs an active sender and a valid sequence before more contacts can be imported.",
            )

    parsed_leads = LeadImporter.parse_csv_content(req.csv_text, req.custom_mapping)
    if not parsed_leads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid LinkedIn leads found in CSV. Ensure at least one column contains LinkedIn profile URLs.",
        )

    result = await LeadImporter.ingest_leads(
        leads=parsed_leads,
        campaign_id=req.campaign_id,
        workspace_id=workspace_id,
        db=db,
        skip_already_contacted=req.skip_already_contacted,
        skip_do_not_contact=True,
        campaign=campaign,
    )

    return result


@router.post("/import-search")
async def import_search_url(
    req: ImportSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Reject unsupported extraction instead of enrolling fabricated prospects."""
    await _require_campaign(req.campaign_id, current_user, db)

    clean_url = req.search_url.strip()
    if not clean_url or "linkedin.com" not in clean_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must be a valid LinkedIn search URL")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="LinkedIn search, event, and group extraction is not connected yet. Import a verified CSV instead.",
    )


async def _lead_query(
    campaign_id: str | None,
    execution_state: str | None,
    pipeline_stage: str | None,
    search: str | None,
    location: str | None,
    current_user: dict,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)

    clauses: list[dict[str, Any]] = [
        {"$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}]}
    ]

    if campaign_id:
        await _require_campaign(campaign_id, current_user, db)
        clauses.append({"campaign_id": campaign_id})
    if execution_state:
        clauses.append({"execution_state": execution_state})
    if pipeline_stage:
        clauses.append({"pipeline_stage": pipeline_stage})
    if search:
        escaped = re.escape(search.strip()[:100])
        clauses.append({
            "$or": [
                {"first_name": {"$regex": escaped, "$options": "i"}},
                {"last_name": {"$regex": escaped, "$options": "i"}},
                {"company_name": {"$regex": escaped, "$options": "i"}},
                {"job_title": {"$regex": escaped, "$options": "i"}},
            ]
        })
    if location:
        escaped_location = re.escape(location.strip()[:100])
        clauses.append({"$or": [
            {"location": {"$regex": escaped_location, "$options": "i"}},
            {"country_code": {"$regex": escaped_location, "$options": "i"}},
        ]})

    return {"$and": clauses} if len(clauses) > 1 else clauses[0]


@router.get("")
async def list_leads(
    campaign_id: str | None = None,
    execution_state: str | None = None,
    pipeline_stage: str | None = None,
    search: str | None = None,
    location: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Returns filterable, paginated leads for the active workspace."""
    query = await _lead_query(campaign_id, execution_state, pipeline_stage, search, location, current_user, db)

    total = await db.outreach_leads.count_documents(query)
    cursor = db.outreach_leads.find(query).sort([("created_at", -1), ("id", -1)]).skip(skip).limit(limit)
    leads = await cursor.to_list(length=limit)

    for l in leads:
        l.pop("_id", None)

    return {
        "leads": leads,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


EXPORT_COLUMNS = (
    "first_name", "last_name", "linkedin_url", "company_name", "job_title",
    "location", "email", "phone", "campaign_id", "pipeline_stage",
    "execution_state", "created_at", "last_action_taken", "last_action_at", "custom_variables",
)


def _safe_csv_cell(value: Any) -> str:
    if isinstance(value, datetime):
        value = value.isoformat()
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@router.get("/export")
async def export_leads(
    campaign_id: str | None = None,
    execution_state: str | None = None,
    pipeline_stage: str | None = None,
    search: str | None = None,
    location: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Export every matching workspace lead, independent of the current UI page."""
    query = await _lead_query(campaign_id, execution_state, pipeline_stage, search, location, current_user, db)

    async def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        cursor = db.outreach_leads.find(query).sort([("created_at", -1), ("id", -1)])
        async for lead in cursor:
            writer.writerow([_safe_csv_cell(lead.get(field)) for field in EXPORT_COLUMNS])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="outreach-leads.csv"',
    })


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a lead from the CRM and updates campaign count."""
    user_id = _user_id(current_user)
    workspace_id = _workspace_id(current_user)
    lead_filter = {
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    }
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if lead.get("campaign_id"):
        campaign = await _require_campaign(lead["campaign_id"], current_user, db)
        if campaign.get("status") == "warming_up":
            raise HTTPException(status_code=409, detail="Pause conditional launch before removing a lead")

    result = await db.outreach_leads.delete_one({
        **lead_filter,
        "execution_claimed_at": {"$exists": False},
    })
    if not result.deleted_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This contact is currently being processed. Retry after the action finishes.",
        )
    if lead.get("campaign_id"):
        await db.outreach_campaigns.update_one(
            _campaign_filter(lead["campaign_id"], current_user),
            {"$inc": {"leads_count": -1}}
        )

    return {"status": "success", "message": "Lead removed"}


@router.post("/do-not-contact")
async def add_do_not_contact(
    req: DoNotContactRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Adds a LinkedIn profile URL to the global Do-Not-Contact exclusion list."""
    workspace_id = _workspace_id(current_user)
    cleaned_url = normalize_linkedin_url(req.linkedin_url)
    if not cleaned_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid LinkedIn profile URL")

    doc = {
        "workspace_id": workspace_id,
        "linkedin_url": cleaned_url,
        "reason": req.reason or "Manual exclusion",
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_do_not_contact.update_one(
        {"workspace_id": workspace_id, "linkedin_url": cleaned_url},
        {"$set": doc},
        upsert=True,
    )

    return {"status": "success", "message": f"{cleaned_url} added to Do-Not-Contact list"}


@router.get("/do-not-contact")
async def list_do_not_contact(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists all URLs on the Do-Not-Contact exclusion list for the workspace."""
    workspace_id = _workspace_id(current_user)
    cursor = db.outreach_do_not_contact.find({"workspace_id": workspace_id}).sort("created_at", -1)
    dnc_list = await cursor.to_list(length=1000)
    for d in dnc_list:
        d.pop("_id", None)
    return dnc_list


# ── Lead Finder & Post Engagers ────────────────────────────────────────────
@router.post("/finder/preview")
async def preview_lead_finder(
    req: LeadFinderPreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Live LinkedIn search is unavailable; never present seed data as prospects."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Live LinkedIn Lead Finder is not connected yet. Import verified prospects from a CSV instead.",
    )


@router.post("/finder/enroll")
async def enroll_finder_leads(
    req: LeadFinderEnrollRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Keep enrollment closed until finder results come from a verified source."""
    await _require_campaign(req.campaign_id, current_user, db)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Lead Finder enrollment is disabled until live, verified LinkedIn results are available.",
    )


@router.post("/import-post-engagers")
async def import_post_engagers(
    req: ImportPostEngagersRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Reject unsupported extraction instead of inventing post-engager profiles."""
    await _require_campaign(req.campaign_id, current_user, db)

    clean_url = req.post_url.strip()
    if not clean_url or "linkedin.com" not in clean_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must be a valid LinkedIn post URL")

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="LinkedIn post-engager extraction is not connected yet. Import verified prospects from a CSV instead.",
    )


@router.patch("/{lead_id}/stage")
async def update_lead_stage(
    lead_id: str,
    req: UpdateLeadStageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Updates the CRM pipeline stage for a lead (Kanban / Vertical Stack support).
    Allowed stages: unassigned, in_campaign, contacted, replied, call_booked.
    """
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)

    valid_stages = ["unassigned", "in_campaign", "contacted", "replied", "call_booked"]
    if req.pipeline_stage not in valid_stages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid pipeline stage. Must be one of: {valid_stages}",
        )

    lead = await db.outreach_leads.find_one({
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    })
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    result = await db.outreach_leads.update_one(
        {
            "id": lead_id,
            "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
        },
        {"$set": {"pipeline_stage": req.pipeline_stage, "updated_at": datetime.now(timezone.utc)}},
    )

    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    return {
        "status": "updated",
        "lead_id": lead_id,
        "pipeline_stage": req.pipeline_stage,
    }
