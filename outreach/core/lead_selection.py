"""Review selected CRM records before creating a new, inactive campaign draft."""
from datetime import datetime, timezone
import hashlib

from bson import BSON
from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.lead_importer import LeadImporter, check_compound_suppression, normalize_linkedin_url
from outreach.core.lead_tags import _commit, stored_ids, stored_revision, require_exact_rows, unique_resource, captured_scope
from outreach.core.workspace_scope import workspace_scope
from outreach.models import OutreachCampaign
from outreach.core.search_sources import unverified_search_lead

EMAIL_FIELDS = ("email_opted_out", "email_verification_status", "email_source", "email_source_urls", "email_verified_at", "email_found_at")
COPY_FIELDS = ("linkedin_url", "linkedin_urn", "member_urn", "sales_lead_urn", "vanity_name", "identifiers", "first_name", "last_name",
               "company_name", "job_title", "location", "email", "phone", "custom_variables", *EMAIL_FIELDS)
REVIEW_FIELDS = (*COPY_FIELDS, "id", "tag_ids", "tag_revision", "has_replied", "replied_at",
                 "execution_state", "do_not_contact", "is_suppressed", "last_action_at",
                 "import_job_id", "staged_at", "source", "source_metadata", "search_source_review_required")


async def selection_preview(db, workspace: str, lead_ids: list[str], allow_contacted: bool) -> dict:
    if not 1 <= len(lead_ids) <= 200 or len(set(lead_ids)) != len(lead_ids) or any(not value.strip() or len(value) > 200 for value in lead_ids):
        raise HTTPException(422, "Select 1–200 unique leads")
    rows = await db.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": lead_ids}, "id.0": {"$exists": False}}).sort("id", 1).to_list(length=201)
    require_exact_rows(rows, lead_ids)
    # A response recorded in another enrollment also excludes the identity.
    replied = await check_compound_suppression(workspace, rows, db, collection_name="outreach_leads",
        extra_filter={"$and": [{"$or": [{"has_replied": True}, {"execution_state": "replied"}, {"replied_at": {"$ne": None}}]}]})
    suppressed = await check_compound_suppression(workspace, rows, db, collection_name="outreach_email_suppressions")
    source_suppressed = await check_compound_suppression(workspace, rows, db, collection_name="outreach_leads",
        extra_filter={"$and": [{"$or": [{"email_opted_out": True}, {"do_not_contact": True}, {"is_suppressed": True}]}]})
    result = await LeadImporter.preview_leads(rows, "selection_preview", workspace, db,
        skip_already_contacted=not allow_contacted, skip_do_not_contact=True)
    for index, (source, row) in enumerate(zip(rows, result["rows"])):
        stored_ids(source)
        stored_revision(source)
        if unverified_search_lead(source):
            row.update(status="rejected", rejection_code="search_source_unverified", error_reason="This contact's search source needs review before enrollment")
        elif index in replied or source.get("has_replied") or source.get("replied_at") or source.get("execution_state") == "replied":
            row.update(status="rejected", rejection_code="reply_recorded", error_reason="A reply is recorded for this contact; review it in Inbox")
        elif index in suppressed or index in source_suppressed or source.get("do_not_contact") or source.get("is_suppressed") or source.get("email_opted_out"):
            row.update(status="rejected", rejection_code="suppressed", error_reason="This contact is suppressed")
        row["source_lead_id"] = source["id"]
    result["valid_count"] = sum(row["status"] == "valid" for row in result["rows"])
    result["excluded_count"] = len(rows) - result["valid_count"]
    result["review_digest"] = canonical_hash({"workspace": workspace, "allow_contacted": allow_contacted,
        "sources": [{**{key: row.get(key) for key in REVIEW_FIELDS},
            "physical_record_digest": hashlib.sha256(BSON.encode({"_id": row["_id"]} if "_id" in row else {})).hexdigest()} for row in rows],
        "decisions": [(row["source_lead_id"], row["status"], row.get("rejection_code")) for row in result["rows"]]})
    return result


async def create_selection_draft(db, workspace: str, actor: str, lead_ids: list[str],
                                 allow_contacted: bool, name: str, request_id: str, review_digest: str) -> dict:
    name = name.strip()
    if not name or len(name) > 100:
        raise HTTPException(422, "Enter a campaign name of 1–100 characters")
    identifier = "followup_" + canonical_hash([workspace, actor, request_id])
    request_digest = canonical_hash([sorted(lead_ids), allow_contacted, name, review_digest])

    async def save(current):
        existing = await unique_resource(current.outreach_campaigns, workspace, identifier)
        if existing:
            if existing.get("selection_request_digest") != request_digest:
                raise HTTPException(409, "This request already belongs to another reviewed selection")
            if existing.get("is_deleted"):
                raise HTTPException(410, "This follow-up draft was deleted; start a new review")
            return {"campaign_id": identifier, "name": existing["name"], "status": "draft_created",
                    "imported_count": existing["selection_imported_count"], "reused_request": True}
        preview = await selection_preview(current, workspace, lead_ids, allow_contacted)
        if preview["review_digest"] != review_digest:
            raise HTTPException(409, "Selected leads or exclusions changed. Review the selection again.")
        accepted_ids = [row["source_lead_id"] for row in preview["rows"] if row["status"] == "valid"]
        if not accepted_ids:
            raise HTTPException(409, "No eligible leads remain in this selection")
        sources = await current.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": accepted_ids}, "id.0": {"$exists": False}}).sort("id", 1).to_list(length=201)
        require_exact_rows(sources, accepted_ids)
        campaign = OutreachCampaign(workspace_id=workspace, user_id=actor, name=name).model_dump()
        campaign.update(id=identifier, selection_request_digest=request_digest, draft_step=1,
                        draft_progress=20, next_step_label="Next: configure sequence", sender_account_ids=[], status="draft")
        await current.outreach_campaigns.insert_one(campaign)
        candidates = [{key: source.get(key) for key in COPY_FIELDS if key in source} for source in sources]
        imported = await LeadImporter.ingest_leads(candidates, identifier, workspace, current,
            skip_already_contacted=not allow_contacted, source="crm_selection",
            source_metadata={"selection_request_id": request_id, "review_digest": review_digest},
            include_rejections=True, _ordered=True)
        if imported["imported_count"] != len(sources):
            raise HTTPException(409, "Lead admission changed. Review the selection again.")
        by_url = {normalize_linkedin_url(source.get("linkedin_url")): source for source in sources}
        enrolled = await current.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": imported["lead_ids"]}, "id.0": {"$exists": False}}).to_list(length=201)
        require_exact_rows(enrolled, imported["lead_ids"])
        for lead in enrolled:
            source = by_url.get(lead.get("linkedin_url"))
            if source is None:
                raise HTTPException(409, "Could not preserve the reviewed lead origin")
            values = {
                "tag_ids": stored_ids(source), "tag_revision": 0,
                "source_metadata.origin_lead_id": source["id"]}
            # Intake prefers saved identifiers for provider routing. Preserve the
            # reviewed current aliases as well, so later suppressions still match
            # both original and subsequently discovered identities.
            values.update({key: source[key] for key in ("linkedin_urn", "member_urn", "sales_lead_urn", "vanity_name", *EMAIL_FIELDS) if key in source})
            updated = await current.outreach_leads.update_one(captured_scope(workspace, lead), {"$set": values})
            if updated.matched_count != 1:
                raise HTTPException(409, "Enrolled lead changed; review the selection again")
        saved = await current.outreach_campaigns.update_one(captured_scope(workspace, campaign), {"$set": {
            "selection_imported_count": imported["imported_count"], "selection_reviewed_at": datetime.now(timezone.utc)}})
        if saved.matched_count != 1:
            raise HTTPException(409, "Draft changed; review the selection again")
        return {"campaign_id": identifier, "name": name, "status": "draft_created", "imported_count": imported["imported_count"], "reused_request": False}

    return await _commit(db, workspace, save)
