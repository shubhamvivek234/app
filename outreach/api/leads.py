"""
Phase 3: Leads CRM API endpoints.
Provides bulk import, search ingestion, CRM filtering, and Do-Not-Contact management.
"""
import logging
import csv
import io
import json
import re
from typing import Annotated, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

import uuid
from outreach.api.dependencies import require_outreach_permission as _lead_permission, workspace_id as _workspace_id
from db.mongo import get_db
from outreach.core.sequence_versions import load_sequence
from outreach.core.workspace_scope import workspace_scope
from outreach.core.import_context import (
    capture_import_scope, verify_import_scope, scoped_result, import_job_scope, check_job_scope, job_campaign_binding,
)
from outreach.core.lead_importer import (
    LeadImporter,
    normalize_linkedin_url,
    _host_variants,
    build_lead_identifiers,
    check_compound_suppression,
)
from outreach.core.name_cleaner import clean_first_name
from outreach.core.search_sources import (
    SearchSourceError, require_search_collection, search_source_capabilities,
    unverified_search_lead, UNVERIFIED_LEAD,
)
from outreach.core.paid_access import get_active_entitlement
from outreach.models import LeadExecutionState, SearchImportJob, SearchImportJobStatus, SearchImportStopReason
from outreach.core.lead_tags import (
    active_tag_map,
    assign_tags,
    create_tag as create_canonical_tag,
    edit_tag,
    hydrate_lead_tags,
    migrate_legacy_tags,
    validate_tag_id,
    stored_ids,
    stored_revision,
    unique_resource,
    captured_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["LinkedIn Outreach Leads CRM"])


def _user_id(current_user: dict) -> str:
    return str(current_user.get("user_id") or current_user.get("id") or current_user.get("_id") or "")


def _lead_filter(lead_id: str, current_user: dict) -> dict[str, Any]:
    """Creator identity never substitutes for the authorized workspace."""
    return {"id": lead_id, **workspace_scope(_workspace_id(current_user))}


def _campaign_filter(campaign_id: str, current_user: dict) -> dict[str, Any]:
    return {
        "id": campaign_id,
        **workspace_scope(_workspace_id(current_user)),
        "is_deleted": {"$ne": True},
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
    require_name: bool = Field(default=False, strict=True)
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


class ImportStagedRequest(BaseModel):
    campaign_id: str
    leads: list[dict[str, Any]] = Field(..., min_length=1, max_length=1000, description="Staged lead objects from preview")
    skip_already_contacted: bool = True
    skip_do_not_contact: bool = True
    require_name: bool = False
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
    sender_account_id: str | None = None
    search_type: str = Field(default="basic", description="'basic' | 'sales_nav' | 'post_engagers'")
    max_leads: int = Field(default=100, ge=1, le=2500)


class CommitStagedLeadsRequest(BaseModel):
    selected_lead_ids: list[str] | None = None
    name_overrides: dict[str, str] | None = None


class DoNotContactRequest(BaseModel):
    linkedin_url: str | None = None
    email: str | None = None
    member_urn: str | None = None
    sales_lead_urn: str | None = None
    vanity_name: str | None = None
    reason: str | None = None


class BlockLeadRequest(BaseModel):
    reason: str = Field(default="Manual exclusion from lead profile", min_length=1, max_length=500)


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


class CreateLeadTagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class UpdateLeadTagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(..., pattern=r"^#[0-9a-fA-F]{6}$")
    revision: int = Field(..., ge=1, strict=True)


class LeadTagMutationRequest(BaseModel):
    tag_id: str
    operation: str = Field(..., pattern=r"^(add|remove)$")
    revision: int = Field(..., ge=0, strict=True)


class BulkLeadTagMutationRequest(BaseModel):
    lead_ids: list[str] = Field(..., min_length=1, max_length=200)
    tag_id: str
    operation: str = Field(..., pattern=r"^(add|remove)$")


class LeadSelectionRequest(BaseModel):
    lead_ids: list[str] = Field(..., min_length=1, max_length=200)
    allow_contacted: bool = Field(default=False, strict=True)


class LeadSelectionDraftRequest(LeadSelectionRequest):
    name: str = Field(..., min_length=1, max_length=100)
    request_id: uuid.UUID
    review_digest: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    request_scope: str = Field(..., pattern=r"^[0-9a-f]{64}$")


# ── Endpoints ──────────────────────────────────────────────────────────────

def _selection_request_scope(current_user: dict) -> str:
    from outreach.core.authorization import canonical_hash
    return canonical_hash(["lead_selection", _workspace_id(current_user), _user_id(current_user)])


@router.get("/selection/context")
async def lead_selection_context(current_user: dict = _lead_permission("lead:read")):
    """Recover an unresolved request even when its source leads no longer exist."""
    return {"request_scope": _selection_request_scope(current_user)}

@router.post("/selection/preview")
async def preview_lead_selection(
    req: LeadSelectionRequest,
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    from outreach.core.lead_selection import selection_preview
    result = await selection_preview(db, _workspace_id(current_user), req.lead_ids, req.allow_contacted)
    return {**result, "request_scope": _selection_request_scope(current_user)}


@router.post("/selection/draft")
async def create_lead_selection_draft(
    req: LeadSelectionDraftRequest,
    current_user: dict = _lead_permission("lead:create"),
    campaign_user: dict = _lead_permission("campaign:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    from outreach.core.lead_selection import create_selection_draft
    workspace = _workspace_id(current_user)
    if _workspace_id(campaign_user) != workspace or _user_id(campaign_user) != _user_id(current_user):
        raise HTTPException(403, "Campaign and lead permissions must use the same workspace")
    if req.request_scope != _selection_request_scope(current_user):
        raise HTTPException(403, "Workspace or account changed. Return to the original workspace to confirm this draft request.")
    return await create_selection_draft(db, workspace, _user_id(current_user), req.lead_ids,
        req.allow_contacted, req.name, str(req.request_id), req.review_digest)

@router.get("/import-context")
async def import_request_context(
    campaign_id: str = Query(..., min_length=1, max_length=200),
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Current advisory scope; no execution permission or historical result."""
    context = await capture_import_scope(db, current_user, campaign_id)
    return JSONResponse(context.public, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/preview")
async def preview_leads_intake(
    req: LeadPreviewRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    Simulates deduplication and validation for CSV or pasted profile URLs.
    Returns row-level errors and counts before committing leads.
    """
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
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

    return scoped_result(context, await LeadImporter.preview_leads(
        leads=parsed,
        campaign_id=req.campaign_id,
        workspace_id=workspace_id,
        db=db,
        skip_already_contacted=req.skip_already_contacted,
        skip_do_not_contact=req.skip_do_not_contact,
        require_name=req.require_name,
    ))


@router.post("/preview-staged")
async def preview_edited_leads(
    req: ImportStagedRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """Recheck edited rows against current exclusions before confirming intake."""
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
    await _require_campaign(req.campaign_id, current_user, db)
    from outreach.core.search_sources import ensure_intake_provenance
    await ensure_intake_provenance(db, _workspace_id(current_user), req.leads, "staged_preview")
    return scoped_result(context, await LeadImporter.preview_leads(req.leads, req.campaign_id, _workspace_id(current_user), db,
        skip_already_contacted=req.skip_already_contacted, skip_do_not_contact=True,
        require_name=req.require_name))


@router.post("/import-urls")
async def import_leads_urls(
    req: ImportURLsRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    Parses and ingests user-pasted LinkedIn profile URLs into a campaign with deduplication and DNC checks.
    """
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
    workspace_id = _workspace_id(current_user)
    campaign = await _require_campaign(req.campaign_id, current_user, db)
    if campaign.get("status") == "warming_up":
        raise HTTPException(status_code=409, detail="Pause conditional launch before changing its lead cohort")
    if campaign.get("status") == "active":
        linked_list_count = await db.outreach_engage_lists.count_documents({
            "campaign_id": req.campaign_id, **workspace_scope(workspace_id),
        })
        if linked_list_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This active campaign has an Engage warm-up list. Import into a new draft campaign so new contacts complete warm-up before launch.",
            )
        sender_count = await db.outreach_accounts.count_documents({
            "id": {"$in": campaign.get("sender_account_ids", [])},
            **workspace_scope(workspace_id),
            "status": "active",
        })
        sequence = await load_sequence(db, workspace_id, req.campaign_id, campaign=campaign)
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
        _import_scope=context,
    )

    return scoped_result(context, result)


@router.post("/import-csv")
async def import_leads_csv(
    req: ImportCSVRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    Parses and ingests a CSV list of LinkedIn leads into a specific campaign with deduplication.
    """
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
    workspace_id = _workspace_id(current_user)
    campaign = await _require_campaign(req.campaign_id, current_user, db)
    if campaign.get("status") == "warming_up":
        raise HTTPException(status_code=409, detail="Pause conditional launch before changing its lead cohort")
    if campaign.get("status") == "active":
        linked_list_count = await db.outreach_engage_lists.count_documents({
            "campaign_id": req.campaign_id, **workspace_scope(workspace_id),
        })
        if linked_list_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This active campaign has an Engage warm-up list. Import into a new draft campaign so new contacts complete warm-up before launch.",
            )
        sender_count = await db.outreach_accounts.count_documents({
            "id": {"$in": campaign.get("sender_account_ids", [])},
            **workspace_scope(workspace_id),
            "status": "active",
        })
        sequence = await load_sequence(db, workspace_id, req.campaign_id, campaign=campaign)
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
        include_invalid=True,
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
        require_name=req.require_name,
        include_rejections=True,
        _import_scope=context,
    )

    return scoped_result(context, result)


@router.post("/import-staged")
async def import_leads_staged(
    req: ImportStagedRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    Ingests reviewed and staged leads into a campaign with user-edited names, compound deduplication, and DNC suppression.
    """
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
    workspace_id = _workspace_id(current_user)
    campaign = await _require_campaign(req.campaign_id, current_user, db)
    if campaign.get("status") == "warming_up":
        raise HTTPException(status_code=409, detail="Pause conditional launch before changing its lead cohort")
    if campaign.get("status") == "active":
        linked_list_count = await db.outreach_engage_lists.count_documents({
            "campaign_id": req.campaign_id, **workspace_scope(workspace_id),
        })
        if linked_list_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This active campaign has an Engage warm-up list. Import into a new draft campaign so new contacts complete warm-up before launch.",
            )
        sender_count = await db.outreach_accounts.count_documents({
            "id": {"$in": campaign.get("sender_account_ids", [])},
            **workspace_scope(workspace_id),
            "status": "active",
        })
        sequence = await load_sequence(db, workspace_id, req.campaign_id, campaign=campaign)
        if not sender_count or not (sequence or {}).get("compiled_dag", {}).get("root_node_ids"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This campaign needs an active sender and a valid sequence before more contacts can be imported.",
            )

    if not req.leads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No leads provided for import.",
        )

    result = await LeadImporter.ingest_leads(
        leads=req.leads,
        campaign_id=req.campaign_id,
        workspace_id=workspace_id,
        db=db,
        skip_already_contacted=req.skip_already_contacted,
        skip_do_not_contact=req.skip_do_not_contact,
        campaign=campaign,
        source="staged_preview",
        source_metadata={"source_type": "staged_preview", "consent_basis": req.consent_basis},
        require_name=req.require_name,
        include_rejections=True,
        _import_scope=context,
    )

    return scoped_result(context, result)


@router.get("/import-sources")
async def get_import_sources(current_user: dict = _lead_permission("lead:read")):
    return search_source_capabilities()


@router.post("/import-search")
async def import_search_url(
    req: ImportSearchRequest,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    1-Click LinkedIn Search & Sales Navigator URL lead extraction.
    Performs strict preflight safety checks, provisions SearchImportJob, and dispatches crawl_page.
    """
    context = await verify_import_scope(db, current_user, req.campaign_id, import_scope)
    campaign = await _require_campaign(req.campaign_id, current_user, db)
    workspace_id = _workspace_id(current_user)
    if req.search_type not in {"basic", "sales_nav"}:
        raise HTTPException(422, "Unsupported search source")
    try:
        parsed_search = require_search_collection(req.search_url)
    except SearchSourceError as exc:
        raise HTTPException(501 if exc.code == "search_source_review_required" else 422, str(exc)) from None

    # 1. Active paid subscription & seat check
    if not await get_active_entitlement(db, workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active paid outreach subscription required for LinkedIn search lead extraction.",
        )

    # 2. Sender chosen by user (NO auto-select)
    if not req.sender_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A sender account must be selected to crawl this search. Auto-selection is disabled for safety.",
        )

    sender = await db.outreach_accounts.find_one({
        "id": req.sender_account_id,
        **workspace_scope(workspace_id),
        "is_deleted": {"$ne": True},
    })
    if not sender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Selected sender account not found in workspace.",
        )
    if sender.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sender account status is '{sender.get('status')}'. Sender must be active to import searches.",
        )

    # 3. URL parsing & classification
    clean_url = parsed_search["clean_url"]

    # 4. Sales Nav seat check for sales_nav URLs
    search_type = parsed_search["search_type"]
    if search_type == "sales_nav":
        prem_prod = sender.get("premium_product")
        has_li_a = bool(sender.get("li_a_enc"))
        if prem_prod not in ("sales_navigator", "recruiter") or not has_li_a:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The selected sender does not have a Sales Navigator seat or session cookie. Connect a Sales Navigator seat in Settings to import Sales Navigator searches.",
            )

    # 5. Dedicated ISP IP proxy lease check
    lease = await db.outreach_proxy_leases.find_one({
        **workspace_scope(workspace_id),
        "sender_id": req.sender_account_id,
    })
    inventory = await db.outreach_proxy_inventory.find_one({"_id": lease["_id"]}) if lease else None
    if not lease or not inventory or inventory.get("status") != "available":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sender does not have an active dedicated proxy lease. Direct host egress is prohibited for account safety.",
        )

    # 6. Unique active import check for this sender
    existing_active = await db.outreach_import_jobs.find_one({
        **workspace_scope(workspace_id),
        "sender_account_id": req.sender_account_id,
        "status": {"$in": [SearchImportJobStatus.QUEUED.value, SearchImportJobStatus.CRAWLING.value]},
    })
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active search import job is already running for this sender. Please wait for it to complete or cancel it before starting another.",
        )

    # 7. Configure page size and target caps
    page_size = 25 if search_type == "sales_nav" else 10
    max_cap = 2500 if search_type == "sales_nav" else 1000
    clamped_target = min(req.max_leads, max_cap)

    job = SearchImportJob(
        workspace_id=workspace_id,
        campaign_id=req.campaign_id,
        sender_account_id=req.sender_account_id,
        search_url=clean_url,
        search_type=search_type,
        cursor=0,
        page_size=page_size,
        target_count=clamped_target,
        status=SearchImportJobStatus.QUEUED,
    )
    job_dict = job.model_dump()
    if context is None:
        await db.outreach_import_jobs.insert_one(job_dict)
    else:
        from outreach.core.suppression import mutate_suppression, SuppressionUnavailable
        job_dict['_import_campaign_native'] = job_campaign_binding(context)
        async def save_scoped_job(current):
            await verify_import_scope(current, current_user, req.campaign_id, context.digest)
            parent = await current.outreach_campaigns.update_one({
                'id': req.campaign_id, **workspace_scope(workspace_id),
                '_id': campaign['_id'], 'is_deleted': {'$ne': True}}, {'$inc': {'lead_admission_revision': 1}})
            if parent.matched_count != 1:
                raise HTTPException(409, 'Import campaign changed before saving the search job')
            await current.outreach_import_jobs.insert_one(job_dict)
        try:
            await mutate_suppression(db, workspace_id, save_scoped_job)
        except SuppressionUnavailable:
            raise HTTPException(503, 'Search job outcome is unconfirmed; review original campaign before retrying') from None

    # 8. Dispatch page 1 task
    from celery_workers.tasks.outreach import crawl_page
    try:
        crawl_page.delay(job.id, 0, job.lease_token)
    except Exception as exc:
        logger.warning("Search job saved; initial page publication deferred (%s)", type(exc).__name__)

    if "_id" in job_dict:
        del job_dict["_id"]
    return scoped_result(context, job_dict)


@router.get("/import-jobs/{job_id}")
async def get_import_job(
    job_id: str,
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """Fetches real-time status and pacing metrics for a search import job."""
    workspace_id = _workspace_id(current_user)
    job, context = await import_job_scope(db, current_user, job_id, import_scope)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    if "_id" in job:
        del job["_id"]
    return scoped_result(context, job)


@router.post("/import-jobs/{job_id}/cancel")
async def cancel_import_job(
    job_id: str,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """Gracefully halts a running search import job."""
    workspace_id = _workspace_id(current_user)
    job, context = await import_job_scope(db, current_user, job_id, import_scope)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")

    if job.get("status") in (SearchImportJobStatus.COMPLETED.value, SearchImportJobStatus.STOPPED.value, SearchImportJobStatus.FAILED.value):
        return scoped_result(context, {"status": job.get("status"), "message": "Job is already completed or stopped."})

    result = await db.outreach_import_jobs.update_one(
        {"id": job_id, **workspace_scope(workspace_id),
         **({"_id": job["_id"], "campaign_id": context.campaign,
             "_import_campaign_native": job_campaign_binding(context)} if context is not None else {}), 'status': job.get('status'),
         'lease_token': job['lease_token'] if 'lease_token' in job else {'$exists': False}},
        {
            "$set": {
                "status": SearchImportJobStatus.STOPPED.value,
                "stop_reason": SearchImportStopReason.CANCELLED.value,
                "user_error_message": "Search import cancelled by user.",
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count != 1:
        current = await db.outreach_import_jobs.find_one({'id': job_id, **workspace_scope(workspace_id),
            **({'_id': job['_id']} if context is not None else {})})
        if current and context is not None:
            await verify_import_scope(db, current_user, context.campaign, context.digest)
            check_job_scope(context, current)
        if current and current.get('status') in {'stopped', 'completed', 'failed'}:
            return scoped_result(context, {'status': current['status'], 'message': 'Search job is already terminal.'})
        raise HTTPException(409, 'Search job changed. Reload its status before requesting cancellation again.')
    return scoped_result(context, {"status": "stopped", "message": "Search import cancelled."})


@router.get("/import-jobs/{job_id}/staged")
async def get_staged_leads_for_job(
    job_id: str,
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """Retrieves all staged leads imported by this job for preview and review."""
    workspace_id = _workspace_id(current_user)
    context = None
    if import_scope is not None:
        job, context = await import_job_scope(db, current_user, job_id, import_scope)
        if not job:
            raise HTTPException(404, "Import job not found")
    cursor = db.outreach_leads.find({
        "import_job_id": job_id,
        **({"campaign_id": context.campaign} if context is not None else {}),
        **workspace_scope(workspace_id),
        "execution_state": LeadExecutionState.STAGED.value,
    })
    leads = await cursor.to_list(length=3000)
    for l in leads:
        if "_id" in l:
            del l["_id"]
    return scoped_result(context, {"leads": leads, "count": len(leads)})


@router.post("/import-jobs/{job_id}/commit")
async def commit_staged_leads(
    job_id: str,
    req: CommitStagedLeadsRequest | None = None,
    current_user: dict = _lead_permission("lead:create"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    import_scope: Annotated[str | None, Header(alias="X-Outreach-Import-Scope", pattern=r"^[0-9a-f]{64}$")] = None,
):
    """
    Promotes staged leads into active 'queued' campaign leads after user review.
    Clears staged_at to avoid 30-day TTL expiration.
    """
    workspace_id = _workspace_id(current_user)
    from outreach.core.suppression import mutate_suppression, SuppressionUnavailable
    from outreach.core.lead_importer import MAX_ADMISSION_ROWS
    initial_job, context = await import_job_scope(db, current_user, job_id, import_scope)
    if not initial_job:
        raise HTTPException(404, "Import job not found")
    await _require_campaign(initial_job["campaign_id"], current_user, db)
    try:
        require_search_collection(initial_job.get("search_url", ""))
    except SearchSourceError:
        raise HTTPException(409, UNVERIFIED_LEAD) from None

    async def promote(current):
        job = await current.outreach_import_jobs.find_one({"id": job_id, **workspace_scope(workspace_id),
            **({"_id": initial_job["_id"]} if context is not None else {})})
        if not job:
            raise HTTPException(404, "Import job not found")
        if context is not None:
            check_job_scope(context, job)
        query = {"import_job_id": job_id, "campaign_id": job["campaign_id"],
                 **workspace_scope(workspace_id), "execution_state": LeadExecutionState.STAGED.value}
        if req and req.selected_lead_ids:
            query["id"] = {"$in": req.selected_lead_ids}
        rows = await current.outreach_leads.find(query).sort("id", 1).to_list(length=MAX_ADMISSION_ROWS + 1)
        if len(rows) > MAX_ADMISSION_ROWS:
            raise HTTPException(422, f"Select at most {MAX_ADMISSION_ROWS} staged contacts at a time.")
        candidates = []
        for row in rows:
            candidate = dict(row)
            if req and row["id"] in (req.name_overrides or {}):
                name = req.name_overrides[row["id"]].strip()
                candidate.update(first_name=name, raw_first_name=name, cleaned_first_name=name)
            candidates.append(candidate)
        result = await LeadImporter.ingest_leads(candidates, job["campaign_id"], workspace_id, current,
            source="linkedin_search", include_rejections=True, _ordered=True, _staged_rows=rows, _import_scope=context)
        return {"status": "committed", "enrolled_count": result["imported_count"],
                "campaign_id": job["campaign_id"], "rejections": result.get("rejections", [])}
    try:
        return scoped_result(context, await mutate_suppression(db, workspace_id, promote))
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm enrollment. Reload campaign contacts before retrying.") from None


async def _lead_query(
    campaign_id: str | None,
    execution_state: str | None,
    pipeline_stage: str | None,
    search: str | None,
    location: str | None,
    current_user: dict,
    db: AsyncIOMotorDatabase,
    tag_ids: str | None = None,
    untagged: bool = False,
) -> dict[str, Any]:
    workspace_id = _workspace_id(current_user)

    clauses: list[dict[str, Any]] = [workspace_scope(workspace_id)]

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

    if tag_ids and len(tag_ids) > 1500:
        raise HTTPException(422, "Choose at most 50 tag filters")
    requested_tags = [validate_tag_id(value.strip()) for value in (tag_ids or "").split(",") if value.strip()]
    requested_tags = list(dict.fromkeys(requested_tags))
    if requested_tags and untagged:
        raise HTTPException(status_code=422, detail="Choose tags or untagged, not both")
    if requested_tags:
        definitions = await active_tag_map(db, workspace_id, requested_tags)
        if len(definitions) != len(requested_tags):
            raise HTTPException(status_code=404, detail="One or more tags were not found")
        clauses.append({"tag_ids": {"$all": requested_tags}})
    elif untagged:
        active_ids = list(await active_tag_map(db, workspace_id))
        clauses.append({"tag_ids": {"$nin": active_ids}})

    return {"$and": clauses} if len(clauses) > 1 else clauses[0]


@router.get("")
async def list_leads(
    campaign_id: str | None = None,
    execution_state: str | None = None,
    pipeline_stage: str | None = None,
    search: str | None = None,
    location: str | None = None,
    tag_ids: str | None = None,
    untagged: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Returns filterable, paginated leads for the active workspace."""
    query = await _lead_query(campaign_id, execution_state, pipeline_stage, search, location, current_user, db, tag_ids, untagged)

    total = await db.outreach_leads.count_documents(query)
    cursor = db.outreach_leads.find(query).sort([("created_at", -1), ("id", -1)]).skip(skip).limit(limit)
    leads = await cursor.to_list(length=limit)

    for l in leads:
        l.pop("_id", None)
    await hydrate_lead_tags(db, _workspace_id(current_user), leads)
    exclusions = await check_compound_suppression(_workspace_id(current_user), leads, db)
    for index, lead in enumerate(leads):
        lead["do_not_contact"] = bool(lead.get("do_not_contact")) or index in exclusions

    return {
        "leads": leads,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


EXPORT_COLUMNS = (
    "first_name", "last_name", "linkedin_url", "company_name", "job_title",
    "location", "email", "phone", "campaign_id", "pipeline_stage",
    "execution_state", "tags", "created_at", "last_action_taken", "last_action_at", "custom_variables",
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
    tag_ids: str | None = None,
    untagged: bool = False,
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Export every matching workspace lead, independent of the current UI page."""
    workspace_id = _workspace_id(current_user)
    query = await _lead_query(campaign_id, execution_state, pipeline_stage, search, location, current_user, db, tag_ids, untagged)
    definitions = await active_tag_map(db, workspace_id, include_archived=True)

    async def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        cursor = db.outreach_leads.find(query).sort([("created_at", -1), ("id", -1)])
        async for lead in cursor:
            try:
                ids = stored_ids(lead)
                stored_revision(lead)
                if any(identifier not in definitions for identifier in ids):
                    raise HTTPException(409, "Unknown tag assignment")
                lead["tags"] = "; ".join(definitions[identifier]["name"] for identifier in ids if not definitions[identifier]["archived"])
            except HTTPException:
                lead["tags"] = "Unavailable: tag assignments require review"
            writer.writerow([_safe_csv_cell(lead.get(field)) for field in EXPORT_COLUMNS])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="outreach-leads.csv"',
    })


@router.get("/tags")
async def list_lead_tags(
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    definitions = await active_tag_map(db, _workspace_id(current_user))
    return list(definitions.values())


@router.post("/tags/import-legacy")
async def import_legacy_lead_tags(
    after_id: str = Query(default="", max_length=200),
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await migrate_legacy_tags(db, _workspace_id(current_user), _user_id(current_user), after_id)


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_lead_tag(
    req: CreateLeadTagRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await create_canonical_tag(db, _workspace_id(current_user), _user_id(current_user), req.name, req.color)


@router.patch("/tags/{tag_id}")
async def update_lead_tag(
    tag_id: str,
    req: UpdateLeadTagRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await edit_tag(db, _workspace_id(current_user), tag_id, req.revision, req.name, req.color)


@router.delete("/tags/{tag_id}")
async def archive_lead_tag(
    tag_id: str,
    revision: int = Query(..., ge=1),
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await edit_tag(db, _workspace_id(current_user), tag_id, revision, archive=True)


@router.patch("/{lead_id}/tags")
async def mutate_lead_tag(
    lead_id: str,
    req: LeadTagMutationRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace = _workspace_id(current_user)
    result = await assign_tags(db, workspace, [lead_id], req.tag_id, req.operation, req.revision)
    lead = await unique_resource(db.outreach_leads, workspace, lead_id)
    if not lead:
        raise HTTPException(409, "Lead changed; reload its tags")
    lead.pop("_id", None)
    await hydrate_lead_tags(db, workspace, [lead])
    return {**result, "lead": {key: lead[key] for key in ("id", "tag_ids", "tag_revision", "tags", "archived_tags")}}


@router.post("/tags/bulk")
async def bulk_mutate_lead_tags(
    req: BulkLeadTagMutationRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await assign_tags(db, _workspace_id(current_user), req.lead_ids, req.tag_id, req.operation)


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: dict = _lead_permission("lead:delete"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a lead from the CRM and updates campaign count."""
    lead_filter = _lead_filter(lead_id, current_user)
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
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Adds a contact (by URL, email, vanity, or URN) to the global Do-Not-Contact exclusion list."""
    workspace_id = _workspace_id(current_user)
    identifiers = build_lead_identifiers(
        raw_url=req.linkedin_url,
        email=req.email,
        member_urn=req.member_urn,
        sales_lead_urn=req.sales_lead_urn,
        vanity_name=req.vanity_name,
    )
    if not (identifiers.normalized_url or identifiers.email or identifiers.member_urn or identifiers.sales_lead_urn or identifiers.vanity_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one valid contact identifier (LinkedIn URL, email, vanity, or URN) must be provided",
        )

    primary_key = (
        identifiers.normalized_url
        or identifiers.email
        or identifiers.member_urn
        or identifiers.sales_lead_urn
        or identifiers.vanity_name
    )

    doc = {
        "workspace_id": workspace_id,
        "linkedin_url": identifiers.normalized_url or req.linkedin_url or "",
        "vanity_name": identifiers.vanity_name or "",
        "member_urn": identifiers.member_urn or "",
        "sales_lead_urn": identifiers.sales_lead_urn or "",
        "email": identifiers.email or "",
        "identifiers": identifiers.model_dump(),
        "reason": req.reason or "Manual exclusion",
        "created_at": datetime.now(timezone.utc),
    }

    from outreach.core.authorization import canonical_hash
    query = {**workspace_scope(workspace_id), "_id": canonical_hash([workspace_id, "dnc", identifiers.model_dump()])}

    from outreach.core.suppression import mutate_suppression, SuppressionUnavailable
    async def save(current):
        created_at = doc["created_at"]
        values = {key: value for key, value in doc.items() if key != "created_at"}
        await current.outreach_do_not_contact.update_one(query,
            {"$set": values, "$setOnInsert": {"created_at": created_at}}, upsert=True)
    try:
        await mutate_suppression(db, workspace_id, save)
    except SuppressionUnavailable:
        raise HTTPException(status_code=503, detail="Do-Not-Contact could not be saved. Please retry.") from None

    return {"status": "success", "message": f"{primary_key} added to Do-Not-Contact list"}


@router.get("/do-not-contact")
async def list_do_not_contact(
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Lists all URLs on the Do-Not-Contact exclusion list for the workspace."""
    workspace_id = _workspace_id(current_user)
    cursor = db.outreach_do_not_contact.find(workspace_scope(workspace_id)).sort("created_at", -1)
    dnc_list = await cursor.to_list(length=1000)
    for d in dnc_list:
        d.pop("_id", None)
    return dnc_list


@router.post("/{lead_id}/do-not-contact")
async def block_lead(
    lead_id: str,
    req: BlockLeadRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Exclude the stored current and original aliases in one ordered transaction."""
    from outreach.core.lead_tags import _commit
    workspace = _workspace_id(current_user)

    async def save(current):
        lead = await unique_resource(current.outreach_leads, workspace, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        original = lead.get("identifiers") if isinstance(lead.get("identifiers"), dict) else {}
        aliases = [
            ("linkedin_url", lead.get("linkedin_url")), ("email", lead.get("email")),
            ("member_urn", lead.get("member_urn")), ("member_urn", lead.get("linkedin_urn")),
            ("sales_lead_urn", lead.get("sales_lead_urn")), ("vanity_name", lead.get("vanity_name")),
            ("linkedin_url", original.get("normalized_url")), ("email", original.get("email")),
            ("member_urn", original.get("member_urn")), ("sales_lead_urn", original.get("sales_lead_urn")),
            ("vanity_name", original.get("vanity_name")),
        ]
        saved = 0
        for field, value in aliases:
            if not isinstance(value, str) or not value.strip():
                continue
            # Normalize each alias independently. URL-derived handles and current
            # member_urn precedence must not erase another reviewed identity.
            normalized = build_lead_identifiers(**{("raw_url" if field == "linkedin_url" else field): value})
            if not any(normalized.model_dump().values()):
                continue
            await add_do_not_contact(DoNotContactRequest(**{field: value}, reason=req.reason),
                                     current_user=current_user, db=current)
            saved += 1
        if not saved:
            raise HTTPException(422, "This lead has no contact identifiers to exclude")
        changed = await current.outreach_leads.update_one(captured_scope(workspace, lead), {"$set": {
            "do_not_contact": True, "do_not_contact_at": datetime.now(timezone.utc)}})
        if changed.matched_count != 1:
            raise HTTPException(409, "Lead changed; reload before excluding it")
        return {"status": "excluded", "lead_id": lead_id}

    return await _commit(db, workspace, save)


# ── Lead Finder & Post Engagers ────────────────────────────────────────────
@router.post("/finder/preview")
async def preview_lead_finder(
    req: LeadFinderPreviewRequest,
    current_user: dict = _lead_permission("lead:create"),
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
    current_user: dict = _lead_permission("lead:create"),
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
    current_user: dict = _lead_permission("lead:create"),
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
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Updates the CRM pipeline stage for a lead (Kanban / Vertical Stack support).
    Allowed stages: unassigned, in_campaign, contacted, replied, call_booked.
    """
    lead_filter = _lead_filter(lead_id, current_user)

    valid_stages = ["unassigned", "in_campaign", "contacted", "replied", "call_booked"]
    if req.pipeline_stage not in valid_stages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid pipeline stage. Must be one of: {valid_stages}",
        )

    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    result = await db.outreach_leads.update_one(
        lead_filter,
        {"$set": {"pipeline_stage": req.pipeline_stage, "updated_at": datetime.now(timezone.utc)},
         "$unset": {"campaign_delete_operation": "", "deleted_pipeline_stage": "", "previous_campaign_id": ""}},
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
    current_user: dict = _lead_permission("lead:read"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Internal, workspace-scoped, paginated lead activity API.
    Combines action outcomes, inbound replies, notes, state changes, and current sequence position.
    """
    workspace_id = _workspace_id(current_user)
    lead = await unique_resource(db.outreach_leads, workspace_id, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.pop("_id", None)

    # 1. Fetch assigned sender account details if present
    sender_name = None
    if lead.get("assigned_account_id") and hasattr(db, "outreach_accounts"):
        account = await db.outreach_accounts.find_one({"id": lead["assigned_account_id"], **workspace_scope(workspace_id)})
        if account:
            sender_name = account.get("account_name") or account.get("vanity_name")

    # 2. Fetch campaign details if present
    campaign_name = None
    if lead.get("campaign_id") and hasattr(db, "outreach_campaigns"):
        campaign = await db.outreach_campaigns.find_one(_campaign_filter(lead["campaign_id"], current_user))
        if campaign:
            campaign_name = campaign.get("name")

    # 3. Collect timeline activities
    activities: list[dict[str, Any]] = []

    # (a) Tasks / actions
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        task_res = db.outreach_tasks.find({"lead_id": lead_id, **workspace_scope(workspace_id)})
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
        thread_res = db.outreach_inbox_threads.find_one({"lead_id": lead_id, **workspace_scope(workspace_id)})
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
        notes_res = db.outreach_lead_notes.find({"lead_id": lead_id, **workspace_scope(workspace_id)})
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
    await hydrate_lead_tags(db, workspace_id, [lead])
    exclusions = await check_compound_suppression(workspace_id, [lead], db)

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
            "tag_ids": lead["tag_ids"],
            "tag_revision": lead["tag_revision"],
            "tags": lead["tags"],
            "archived_tags": lead["archived_tags"],
            "do_not_contact": bool(lead.get("do_not_contact")) or 0 in exclusions,
        },
        "total_activities": total_activities,
        "activities": paged_activities,
        "skip": skip,
        "limit": limit,
    }


@router.post("/{lead_id}/notes")
async def add_lead_note(
    lead_id: str,
    req: AddLeadNoteRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Adds an internal note to the lead's activity history."""
    workspace_id = _workspace_id(current_user)
    user_id = _user_id(current_user)
    lead_filter = _lead_filter(lead_id, current_user)
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


@router.post("/{lead_id}/pause")
async def pause_lead(
    lead_id: str,
    req: PauseLeadRequest,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Pauses sequence execution for a specific lead and cancels pending tasks."""
    workspace_id = _workspace_id(current_user)
    lead_filter = _lead_filter(lead_id, current_user)
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    state = lead.get("execution_state")
    if state == "staged" or state is not None and not isinstance(state, str):
        raise HTTPException(409, "Staged contacts must remain in source review; they cannot be paused into enrollment.")

    pause_reason = req.reason or "Manually paused by operator"
    state_match = ({"$eq": state, "$type": "string"} if isinstance(state, str) else
                   {"$type": "null", "$exists": True} if "execution_state" in lead else {"$exists": False})
    changed = await db.outreach_leads.update_one(
        {**lead_filter, "execution_state": state_match, "execution_state.0": {"$exists": False},
         **({"_id": lead["_id"]} if "_id" in lead else {})},
        {"$set": {"execution_state": "paused", "pause_reason": pause_reason, "updated_at": datetime.now(timezone.utc)}}
    )
    if not changed.matched_count:
        raise HTTPException(409, "Contact state changed; refresh before pausing.")

    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "update_many"):
        await db.outreach_tasks.update_many(
            {"lead_id": lead_id, **workspace_scope(workspace_id), "status": "pending"},
            {"$set": {"status": "skipped", "skip_reason": f"Lead paused: {pause_reason}", "resolved_at": datetime.now(timezone.utc)}}
        )

    return {"status": "paused", "lead_id": lead_id, "pause_reason": pause_reason}


@router.post("/{lead_id}/resume")
async def resume_lead(
    lead_id: str,
    current_user: dict = _lead_permission("lead:update"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Safely resumes a paused or replied lead after preflight checks:
    - Verifies lead is not on Do-Not-Contact list
    - Verifies no uncertain provider tasks exist requiring Action Review
    - Verifies assigned sender is healthy
    """
    workspace_id = _workspace_id(current_user)
    lead_filter = _lead_filter(lead_id, current_user)
    lead = await db.outreach_leads.find_one(lead_filter)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # 1. Suppression check: Do-Not-Contact list (compound)
    if unverified_search_lead(lead):
        raise HTTPException(409, UNVERIFIED_LEAD)
    if hasattr(db, "outreach_do_not_contact"):
        suppressed = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=[lead],
            db=db,
            collection_name="outreach_do_not_contact",
        )
        if suppressed:
            reason = suppressed[0].get("reason", "Manual exclusion")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot resume lead: this profile is on the workspace Do-Not-Contact exclusion list ({reason}).",
            )

    # 2. Action provenance preflight: block if any uncertain tasks exist
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "count_documents"):
        count_res = db.outreach_tasks.count_documents({
            "lead_id": lead_id,
            **workspace_scope(workspace_id),
            "status": {"$in": ["uncertain", "resolving"]},
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
            **workspace_scope(workspace_id),
            "status": "active",
        })
        if not sender:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot resume lead: assigned sender account is inactive or disconnected.",
            )

    # 4. Safe resume
    from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY
    changed = await db.outreach_leads.update_one(
        {**lead_filter, "$nor": [SEARCH_PROVENANCE_QUERY]},
        {
            "$set": {
                "execution_state": "queued",
                "pause_reason": None,
                "has_replied": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if not changed.matched_count:
        raise HTTPException(409, "Contact source changed; refresh before resuming.")

    return {"status": "resumed", "lead_id": lead_id, "execution_state": "queued"}
