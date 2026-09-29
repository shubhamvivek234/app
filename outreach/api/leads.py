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

import uuid
from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.lead_importer import LeadImporter, normalize_linkedin_url, _host_variants

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
    default_first_name: str | None = None
    default_company_name: str | None = None
    skip_already_contacted: bool = True
    skip_do_not_contact: bool = True
    consent_basis: str = Field(default="user_provided", description="Consent or source basis")


class ImportURLsRequest(BaseModel):
    campaign_id: str
    urls_text: str = Field(..., description="Newline-separated URLs or URL, Name lines")
    default_first_name: str | None = None
    default_company_name: str | None = None
    skip_already_contacted: bool = True
    skip_do_not_contact: bool = True
    require_name: bool = True
    consent_basis: str = Field(default="user_provided", description="Consent or source basis")


class LeadPreviewRequest(BaseModel):
    campaign_id: str
    source_type: str = Field(default="csv", description="'csv' | 'pasted_urls'")
    raw_text: str = Field(..., description="CSV content or newline-separated URLs")
    custom_mapping: dict[str, str] | None = None
    default_first_name: str | None = None
    default_company_name: str | None = None
    skip_already_contacted: bool = True
    skip_do_not_contact: bool = True
    require_name: bool = False


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

@router.post("/preview", dependencies=[require_permission("lead:create")])
async def preview_leads_intake(
    req: LeadPreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Simulates deduplication and validation for CSV or pasted profile URLs.
    Returns row-level errors and counts before committing leads.
    """
    workspace_id = _workspace_id(current_user)
    await _require_campaign(req.campaign_id, current_user, db)

    if req.source_type == "pasted_urls":
        parsed = LeadImporter.parse_pasted_urls(
            text=req.raw_text,
            default_first_name=req.default_first_name,
            default_company_name=req.default_company_name,
            require_name=req.require_name,
        )
    else:
        parsed = LeadImporter.parse_csv_content(
            csv_text=req.raw_text,
            custom_mapping=req.custom_mapping,
            default_first_name=req.default_first_name,
            default_company_name=req.default_company_name,
            include_invalid=True,
        )

    return await LeadImporter.preview_leads(
        leads=parsed,
        campaign_id=req.campaign_id,
        workspace_id=workspace_id,
        db=db,
        skip_already_contacted=req.skip_already_contacted,
        skip_do_not_contact=req.skip_do_not_contact,
        require_name=req.require_name,
    )


@router.post("/import-urls", dependencies=[require_permission("lead:create")])
async def import_leads_urls(
    req: ImportURLsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Parses and ingests user-pasted LinkedIn profile URLs into a campaign with deduplication and DNC checks.
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

    parsed_leads = LeadImporter.parse_pasted_urls(
        text=req.urls_text,
        default_first_name=req.default_first_name,
        default_company_name=req.default_company_name,
        require_name=req.require_name,
    )
    if not parsed_leads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid LinkedIn profile URLs found. Paste at least one URL (e.g. https://linkedin.com/in/username).",
        )

    result = await LeadImporter.ingest_leads(
        leads=parsed_leads,
        campaign_id=req.campaign_id,
        workspace_id=workspace_id,
        db=db,
        skip_already_contacted=req.skip_already_contacted,
        skip_do_not_contact=req.skip_do_not_contact,
        campaign=campaign,
        source="pasted_urls",
        source_metadata={"source_type": "pasted_urls", "consent_basis": req.consent_basis},
        require_name=req.require_name,
        include_rejections=True,
    )

    return result


@router.post("/import-csv", dependencies=[require_permission("lead:create")])
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

    parsed_leads = LeadImporter.parse_csv_content(
        csv_text=req.csv_text,
        custom_mapping=req.custom_mapping,
        default_first_name=req.default_first_name,
        default_company_name=req.default_company_name,
    )
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
        skip_do_not_contact=req.skip_do_not_contact,
        campaign=campaign,
        source="csv",
        source_metadata={"source_type": "csv", "consent_basis": req.consent_basis},
        include_rejections=True,
    )

    return result


@router.post("/import-search", dependencies=[require_permission("lead:create")])
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


@router.delete("/{lead_id}", dependencies=[require_permission("lead:delete")])
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


@router.post("/do-not-contact", dependencies=[require_permission("lead:update")])
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
@router.post("/finder/preview", dependencies=[require_permission("lead:create")])
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


@router.post("/finder/enroll", dependencies=[require_permission("lead:create")])
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


@router.post("/import-post-engagers", dependencies=[require_permission("lead:create")])
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


@router.patch("/{lead_id}/stage", dependencies=[require_permission("lead:update")])
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


# ── Internal Lead Activity & Journey Controls ──────────────────────────────

class AddLeadNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class PauseLeadRequest(BaseModel):
    reason: str | None = None


@router.get("/{lead_id}/activity")
async def get_lead_activity(
    lead_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Internal, workspace-scoped, paginated lead activity API.
    Combines action outcomes, inbound replies, notes, state changes, and current sequence position.
    """
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)
    lead_filter = {
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    }
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.pop("_id", None)

    # 1. Fetch assigned sender account details if present
    sender_name = None
    if lead.get("assigned_account_id") and hasattr(db, "outreach_accounts"):
        account = await db.outreach_accounts.find_one({"id": lead["assigned_account_id"]})
        if account:
            sender_name = account.get("account_name") or account.get("vanity_name")

    # 2. Fetch campaign details if present
    campaign_name = None
    if lead.get("campaign_id") and hasattr(db, "outreach_campaigns"):
        campaign = await db.outreach_campaigns.find_one({"id": lead["campaign_id"]})
        if campaign:
            campaign_name = campaign.get("name")

    # 3. Collect timeline activities
    activities: list[dict[str, Any]] = []

    # (a) Tasks / actions
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        task_res = db.outreach_tasks.find({"lead_id": lead_id, "workspace_id": workspace_id})
        if hasattr(task_res, "sort"):
            task_res = task_res.sort("created_at", -1)
        if hasattr(task_res, "__await__"):
            task_res = await task_res
        if hasattr(task_res, "to_list"):
            tasks = await task_res.to_list(length=100)
        elif isinstance(task_res, list):
            tasks = task_res
        else:
            tasks = []
        for task in tasks:
            activities.append({
                "id": str(task.get("id") or task.get("_id") or ""),
                "kind": "task",
                "task_type": task.get("task_type") or task.get("action_type"),
                "status": task.get("status"),
                "node_id": task.get("node_id"),
                "attempt_id": task.get("attempt_id"),
                "action_outcome": task.get("action_outcome") or task.get("status"),
                "error_reason": task.get("error_reason") or task.get("skip_reason"),
                "timestamp": task.get("resolved_at") or task.get("executed_at") or task.get("created_at"),
            })

    # (b) Inbound/outbound thread messages
    if hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "find_one"):
        thread_res = db.outreach_inbox_threads.find_one({"lead_id": lead_id, "workspace_id": workspace_id})
        if hasattr(thread_res, "__await__"):
            thread_res = await thread_res
        if thread_res and isinstance(thread_res, dict):
            for msg in thread_res.get("messages", []):
                activities.append({
                    "id": str(msg.get("id") or ""),
                    "kind": "message",
                    "sender_type": msg.get("sender_type"),
                    "sender_name": msg.get("sender_name"),
                    "body": msg.get("body"),
                    "is_voice_note": msg.get("is_voice_note", False),
                    "timestamp": msg.get("timestamp"),
                })

    # (c) Notes
    if hasattr(db, "outreach_lead_notes") and hasattr(db.outreach_lead_notes, "find"):
        notes_res = db.outreach_lead_notes.find({"lead_id": lead_id, "workspace_id": workspace_id})
        if hasattr(notes_res, "sort"):
            notes_res = notes_res.sort("created_at", -1)
        if hasattr(notes_res, "__await__"):
            notes_res = await notes_res
        if hasattr(notes_res, "to_list"):
            notes = await notes_res.to_list(length=100)
        elif isinstance(notes_res, list):
            notes = notes_res
        else:
            notes = []
        for note in notes:
            activities.append({
                "id": str(note.get("id") or note.get("_id") or ""),
                "kind": "note",
                "note": note.get("note"),
                "author": note.get("author") or "Team Member",
                "timestamp": note.get("created_at"),
            })

    # (d) Lifecycle state events
    if lead.get("created_at"):
        activities.append({
            "id": f"event_created_{lead_id}",
            "kind": "lifecycle",
            "event": "enrolled",
            "description": f"Lead enrolled in campaign '{campaign_name or 'Outreach'}'",
            "timestamp": lead.get("created_at"),
        })
    if lead.get("accepted_at"):
        activities.append({
            "id": f"event_connected_{lead_id}",
            "kind": "lifecycle",
            "event": "connection_accepted",
            "description": "LinkedIn connection request accepted",
            "timestamp": lead.get("accepted_at"),
        })
    if lead.get("replied_at"):
        activities.append({
            "id": f"event_replied_{lead_id}",
            "kind": "lifecycle",
            "event": "replied",
            "description": f"Lead replied to outreach ({lead.get('pause_reason') or 'touches stopped'})",
            "timestamp": lead.get("replied_at"),
        })

    def _ts_key(act):
        ts = act.get("timestamp")
        if isinstance(ts, datetime):
            return ts.timestamp()
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts).timestamp()
            except Exception:
                return 0.0
        return 0.0

    activities.sort(key=_ts_key, reverse=True)

    total_activities = len(activities)
    paged_activities = activities[skip : skip + limit]

    return {
        "lead": {
            "id": lead["id"],
            "campaign_id": lead.get("campaign_id"),
            "campaign_name": campaign_name,
            "linkedin_url": lead.get("linkedin_url"),
            "first_name": lead.get("first_name"),
            "last_name": lead.get("last_name"),
            "company_name": lead.get("company_name"),
            "job_title": lead.get("job_title"),
            "execution_state": lead.get("execution_state"),
            "pipeline_stage": lead.get("pipeline_stage"),
            "current_node_id": lead.get("current_node_id"),
            "next_action_due_at": lead.get("next_action_due_at"),
            "assigned_account_id": lead.get("assigned_account_id"),
            "assigned_sender_name": sender_name,
            "last_action_taken": lead.get("last_action_taken"),
            "last_action_at": lead.get("last_action_at"),
            "is_connected": lead.get("is_connected", False),
            "accepted_at": lead.get("accepted_at"),
            "has_replied": lead.get("has_replied", False),
            "replied_at": lead.get("replied_at"),
            "pause_reason": lead.get("pause_reason"),
            "source": lead.get("source", "csv"),
            "created_at": lead.get("created_at"),
        },
        "total_activities": total_activities,
        "activities": paged_activities,
        "skip": skip,
        "limit": limit,
    }


@router.post("/{lead_id}/notes", dependencies=[require_permission("lead:update")])
async def add_lead_note(
    lead_id: str,
    req: AddLeadNoteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Adds an internal note to the lead's activity history."""
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)
    lead_filter = {
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    }
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    note_doc = {
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "note": req.note.strip(),
        "author": current_user.get("name") or current_user.get("email") or "Operator",
        "created_at": datetime.now(timezone.utc),
    }

    if hasattr(db, "outreach_lead_notes"):
        await db.outreach_lead_notes.insert_one(note_doc)

    return {"status": "success", "note": note_doc}


@router.post("/{lead_id}/pause", dependencies=[require_permission("lead:update")])
async def pause_lead(
    lead_id: str,
    req: PauseLeadRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Pauses sequence execution for a specific lead and cancels pending tasks."""
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)
    lead_filter = {
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    }
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    pause_reason = req.reason or "Manually paused by operator"
    await db.outreach_leads.update_one(
        lead_filter,
        {"$set": {"execution_state": "paused", "pause_reason": pause_reason, "updated_at": datetime.now(timezone.utc)}}
    )

    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "update_many"):
        await db.outreach_tasks.update_many(
            {"lead_id": lead_id, "workspace_id": workspace_id, "status": "pending"},
            {"$set": {"status": "skipped", "skip_reason": f"Lead paused: {pause_reason}", "resolved_at": datetime.now(timezone.utc)}}
        )

    return {"status": "paused", "lead_id": lead_id, "pause_reason": pause_reason}


@router.post("/{lead_id}/resume", dependencies=[require_permission("lead:update")])
async def resume_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Safely resumes a paused or replied lead after preflight checks:
    - Verifies lead is not on Do-Not-Contact list
    - Verifies no uncertain provider tasks exist requiring Action Review
    - Verifies assigned sender is healthy
    """
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)
    lead_filter = {
        "id": lead_id,
        "$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}],
    }
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # 1. Suppression check: Do-Not-Contact list
    cleaned_url = normalize_linkedin_url(lead.get("linkedin_url", ""))
    if cleaned_url and hasattr(db, "outreach_do_not_contact"):
        dnc = await db.outreach_do_not_contact.find_one({
            "workspace_id": workspace_id,
            "linkedin_url": {"$in": list(_host_variants(cleaned_url))},
        })
        if dnc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot resume lead: this profile is on the workspace Do-Not-Contact exclusion list.",
            )

    # 2. Action provenance preflight: block if any uncertain tasks exist
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "count_documents"):
        count_res = db.outreach_tasks.count_documents({
            "lead_id": lead_id,
            "workspace_id": workspace_id,
            "status": "uncertain",
        })
        if hasattr(count_res, "__await__"):
            count_res = await count_res
        if isinstance(count_res, (int, float)) and int(count_res) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot resume lead: {int(count_res)} action has an uncertain outcome requiring Action Review.",
            )

    # 3. Sender health check if assigned
    if lead.get("assigned_account_id") and hasattr(db, "outreach_accounts"):
        sender = await db.outreach_accounts.find_one({
            "id": lead["assigned_account_id"],
            "workspace_id": workspace_id,
            "status": "active",
        })
        if not sender:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot resume lead: assigned sender account is inactive or disconnected.",
            )

    # 4. Safe resume
    await db.outreach_leads.update_one(
        lead_filter,
        {
            "$set": {
                "execution_state": "queued",
                "pause_reason": None,
                "has_replied": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return {"status": "resumed", "lead_id": lead_id, "execution_state": "queued"}

