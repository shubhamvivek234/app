"""
Phase 3: Lead Ingestion, Parsing, Normalization & Deduplication CRM Engine.
Supports CSV parsing with automatic column discovery, search URL ingest, and Do-Not-Contact exclusion.
"""
import re
import csv
import io
import logging
from typing import Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from outreach.models import OutreachLead, LeadExecutionState

logger = logging.getLogger(__name__)

# Common header aliases for automated column discovery
COLUMN_ALIASES = {
    "linkedin_url": [
        "linkedin", "linkedin_url", "profile_url", "linkedin profile", "url",
        "linkedin url", "linkedin profile url", "linkedin_profile", "linkedin profile link",
        "person linkedin url", "contact linkedin",
    ],
    "first_name": ["first_name", "first name", "firstname", "first", "given name"],
    "last_name": ["last_name", "last name", "lastname", "last", "surname"],
    "company_name": ["company", "company_name", "company name", "organization", "employer"],
    "job_title": ["title", "job_title", "job title", "position", "role", "headline"],
    "location": ["location", "city", "country", "geo", "region"],
    "email": ["email", "e-mail", "email_address", "work_email"],
    "phone": ["phone", "phone_number", "mobile", "telephone"],
}


def normalize_linkedin_url(raw_url: str) -> str:
    """Cleans and standardizes a LinkedIn profile URL for reliable deduplication."""
    if not raw_url:
        return ""
    url = raw_url.strip().lower()
    # Strip tracking query params (?miniProfileUrn=..., ?trk=...)
    url = re.sub(r"\?.*$", "", url)
    # Strip trailing slash
    url = url.rstrip("/")
    # Ensure proper https prefix
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url
    return url


def detect_csv_headers(header_row: list[str]) -> dict[str, str]:
    """
    Intelligently maps CSV column headers to standardized lead attributes.
    Returns { field_name: csv_header_name }.
    """
    mapping = {}
    normalized_headers = {h.strip().lower(): h for h in header_row if h}

    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized_headers:
                mapping[field] = normalized_headers[alias]
                break

    # Fuzzy fallback for linkedin_url if not explicitly mapped
    if "linkedin_url" not in mapping:
        for norm_h, orig_h in normalized_headers.items():
            if "linkedin" in norm_h:
                mapping["linkedin_url"] = orig_h
                break

    return mapping


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 50000) -> list[dict[str, Any]]:
    """Helper to safely fetch documents across Motor cursor and test mock variants."""
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


class LeadImporter:
    """
    Parses and ingests leads into campaigns while enforcing deduplication and safety rules.
    """

    @staticmethod
    def parse_csv_content(csv_text: str, custom_mapping: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """
        Parses raw CSV string into normalized lead dictionaries.
        """
        f = io.StringIO(csv_text)
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []

        header_mapping = custom_mapping or detect_csv_headers(reader.fieldnames)
        parsed_leads: list[dict[str, Any]] = []

        for row in reader:
            # Must find a LinkedIn URL to be considered a valid outreach lead
            raw_url = ""
            if "linkedin_url" in header_mapping:
                raw_url = row.get(header_mapping["linkedin_url"], "")
            elif "url" in row:
                raw_url = row.get("url", "")

            cleaned_url = normalize_linkedin_url(raw_url)
            if not cleaned_url or "linkedin.com" not in cleaned_url:
                continue

            lead_data = {
                "linkedin_url": cleaned_url,
                "first_name": row.get(header_mapping.get("first_name", ""), "").strip(),
                "last_name": row.get(header_mapping.get("last_name", ""), "").strip(),
                "company_name": row.get(header_mapping.get("company_name", ""), "").strip(),
                "job_title": row.get(header_mapping.get("job_title", ""), "").strip(),
                "location": row.get(header_mapping.get("location", ""), "").strip(),
                "email": row.get(header_mapping.get("email", ""), "").strip() or None,
                "phone": row.get(header_mapping.get("phone", ""), "").strip() or None,
                "custom_variables": {},
            }

            # Collect any additional columns as custom variables for dynamic template tags
            mapped_values = set(header_mapping.values())
            for col_name, val in row.items():
                if col_name and col_name not in mapped_values and val:
                    lead_data["custom_variables"][col_name.strip()] = val.strip()

            parsed_leads.append(lead_data)

        return parsed_leads

    @staticmethod
    async def ingest_leads(
        leads: list[dict[str, Any]],
        campaign_id: str,
        workspace_id: str,
        db: AsyncIOMotorDatabase,
        skip_already_contacted: bool = True,
        skip_do_not_contact: bool = True,
    ) -> dict[str, Any]:
        """
        Deduplicates and bulk-inserts parsed leads into MongoDB for the given campaign.
        """
        if not leads:
            return {"imported_count": 0, "skipped_count": 0, "duplicates_count": 0}

        # 1. Fetch existing leads in this campaign for deduplication
        existing_campaign_leads = await _fetch_cursor_docs(
            db.outreach_leads.find({"campaign_id": campaign_id}, {"linkedin_url": 1}),
            length=50000,
        )
        existing_urls = {doc["linkedin_url"] for doc in existing_campaign_leads if "linkedin_url" in doc}

        # 2. Fetch cross-campaign contacted leads if enabled
        cross_campaign_urls = set()
        if skip_already_contacted:
            contacted_docs = await _fetch_cursor_docs(
                db.outreach_leads.find(
                    {"workspace_id": workspace_id, "execution_state": {"$nin": [LeadExecutionState.QUEUED]}},
                    {"linkedin_url": 1},
                ),
                length=50000,
            )
            cross_campaign_urls = {doc["linkedin_url"] for doc in contacted_docs if "linkedin_url" in doc}

        # 3. Fetch Do-Not-Contact URLs
        dnc_urls = set()
        if skip_do_not_contact:
            dnc_docs = await _fetch_cursor_docs(
                db.outreach_do_not_contact.find({"workspace_id": workspace_id}, {"linkedin_url": 1}),
                length=10000,
            )
            dnc_urls = {doc["linkedin_url"] for doc in dnc_docs if "linkedin_url" in doc}

        to_insert: list[dict[str, Any]] = []
        seen_in_batch: set[str] = set()
        duplicates_count = 0
        skipped_count = 0

        for lead in leads:
            url = lead["linkedin_url"]

            # Deduplicate within batch
            if url in seen_in_batch:
                duplicates_count += 1
                continue
            seen_in_batch.add(url)

            # Deduplicate against campaign
            if url in existing_urls:
                duplicates_count += 1
                continue

            # Deduplicate against previous campaigns
            if skip_already_contacted and url in cross_campaign_urls:
                skipped_count += 1
                continue

            # Check Do-Not-Contact list
            if skip_do_not_contact and url in dnc_urls:
                skipped_count += 1
                continue

            lead_doc = OutreachLead(
                campaign_id=campaign_id,
                workspace_id=workspace_id,
                linkedin_url=url,
                first_name=lead.get("first_name", ""),
                last_name=lead.get("last_name", ""),
                company_name=lead.get("company_name", ""),
                job_title=lead.get("job_title", ""),
                location=lead.get("location", ""),
                email=lead.get("email"),
                phone=lead.get("phone"),
                custom_variables=lead.get("custom_variables", {}),
                execution_state=LeadExecutionState.QUEUED,
                created_at=datetime.now(timezone.utc),
            ).model_dump()

            to_insert.append(lead_doc)

        if to_insert:
            await db.outreach_leads.insert_many(to_insert)
            # Update campaign lead count
            await db.outreach_campaigns.update_one(
                {"id": campaign_id},
                {"$inc": {"leads_count": len(to_insert)}, "$set": {"updated_at": datetime.now(timezone.utc)}}
            )

        logger.info(
            "Campaign %s: Imported %s leads (skipped: %s, duplicates: %s)",
            campaign_id, len(to_insert), skipped_count, duplicates_count,
        )

        return {
            "imported_count": len(to_insert),
            "skipped_count": skipped_count,
            "duplicates_count": duplicates_count,
            "total_submitted": len(leads),
        }
