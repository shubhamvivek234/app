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
from urllib.parse import urlparse
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
    # Ensure proper https prefix
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.hostname not in {"linkedin.com", "www.linkedin.com"}:
        return ""
    path = parsed.path.rstrip("/")
    parts = path.split("/")
    if len(parts) < 3 or parts[1] != "in" or not parts[2]:
        return ""
    if not re.fullmatch(r"[a-z0-9._-]+", parts[2]) or parts[2] in {".", ".."}:
        return ""
    return f"https://{parsed.hostname}/in/{parts[2]}"


def extract_vanity_name(raw_url: str) -> str:
    """Extracts the vanity handle (e.g., 'john-doe') from a LinkedIn profile URL."""
    normalized = normalize_linkedin_url(raw_url)
    if not normalized:
        return ""
    parts = normalized.split("/in/")
    if len(parts) > 1:
        return parts[1].split("/")[0]
    return ""


def _dedupe_key(raw_url: str) -> str:
    """Treat www and bare LinkedIn hosts as the same profile."""
    return normalize_linkedin_url(raw_url).replace("https://www.linkedin.com/", "https://linkedin.com/")


def _host_variants(url: str) -> set[str]:
    bare = _dedupe_key(url)
    return {bare, bare.replace("https://linkedin.com/", "https://www.linkedin.com/")}


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


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int | None = 50000) -> list[dict[str, Any]]:
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
    Supports CSV parsing, manual pasted profile URLs, and pre-ingestion validation.
    """

    @staticmethod
    def parse_pasted_urls(
        text: str,
        default_first_name: str | None = None,
        default_company_name: str | None = None,
        require_name: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Parses line-by-line user pasted LinkedIn URLs with optional comma/tab-separated metadata.
        Format per line:
          - https://linkedin.com/in/username
          - https://linkedin.com/in/username, First Last
          - https://linkedin.com/in/username, First, Last
          - https://linkedin.com/in/username, First, Last, Company, Title
        Never invents profile details. Extracts vanity handle from valid URLs.
        """
        parsed_leads: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Detect delimiter
            delimiter = "\t" if "\t" in line else ","
            try:
                reader = csv.reader([line], delimiter=delimiter)
                row = next(reader, [])
            except Exception:
                row = [c.strip() for c in line.split(delimiter)]
            row = [col.strip() for col in row if col is not None]
            if not row:
                continue

            # Handle space-separated URL and names if single unquoted column
            if len(row) == 1 and " " in row[0]:
                words = row[0].split()
                if "linkedin.com" in words[0].lower() or normalize_linkedin_url(words[0]):
                    row = [words[0], " ".join(words[1:])]

            # Identify column with LinkedIn URL
            url_idx = -1
            for idx, col in enumerate(row):
                if "linkedin.com" in col.lower() or normalize_linkedin_url(col):
                    url_idx = idx
                    break

            if url_idx != -1:
                raw_url = row[url_idx]
                other_cols = [c for i, c in enumerate(row) if i != url_idx and c]
            else:
                raw_url = row[0]
                other_cols = row[1:]

            cleaned_url = normalize_linkedin_url(raw_url)
            vanity = extract_vanity_name(cleaned_url)

            first_name = ""
            last_name = ""
            company_name = (default_company_name or "").strip()
            job_title = ""

            if other_cols:
                if len(other_cols) == 1:
                    parts = other_cols[0].split(maxsplit=1)
                    first_name = parts[0]
                    if len(parts) > 1:
                        last_name = parts[1]
                elif len(other_cols) == 2:
                    if " " in other_cols[0]:
                        parts = other_cols[0].split(maxsplit=1)
                        first_name = parts[0]
                        last_name = parts[1]
                        company_name = other_cols[1]
                    else:
                        first_name = other_cols[0]
                        last_name = other_cols[1]
                elif len(other_cols) == 3:
                    if " " in other_cols[0]:
                        parts = other_cols[0].split(maxsplit=1)
                        first_name = parts[0]
                        last_name = parts[1]
                        company_name = other_cols[1]
                        job_title = other_cols[2]
                    else:
                        first_name = other_cols[0]
                        last_name = other_cols[1]
                        company_name = other_cols[2]
                elif len(other_cols) >= 4:
                    if " " in other_cols[0]:
                        parts = other_cols[0].split(maxsplit=1)
                        first_name = parts[0]
                        last_name = parts[1]
                        company_name = other_cols[1]
                        job_title = other_cols[2]
                    else:
                        first_name = other_cols[0]
                        last_name = other_cols[1]
                        company_name = other_cols[2]
                        job_title = other_cols[3]

            if not first_name and default_first_name:
                first_name = default_first_name.strip()

            lead_data = {
                "raw_url": raw_url,
                "linkedin_url": cleaned_url,
                "vanity_name": vanity,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company_name,
                "job_title": job_title,
                "location": "",
                "email": None,
                "phone": None,
                "custom_variables": {"vanity_handle": vanity} if vanity else {},
                "source": "pasted_urls",
            }
            parsed_leads.append(lead_data)

        return parsed_leads

    @staticmethod
    def parse_csv_content(
        csv_text: str,
        custom_mapping: dict[str, str] | None = None,
        default_first_name: str | None = None,
        default_company_name: str | None = None,
        include_invalid: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Parses raw CSV string into normalized lead dictionaries.
        """
        f = io.StringIO(csv_text.lstrip("\ufeff"))
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

            cleaned_url = normalize_linkedin_url(raw_url or "")
            if not cleaned_url and not include_invalid:
                continue

            first_name = (row.get(header_mapping.get("first_name", "")) or "").strip()
            if not first_name and default_first_name:
                first_name = default_first_name.strip()

            company_name = (row.get(header_mapping.get("company_name", "")) or "").strip()
            if not company_name and default_company_name:
                company_name = default_company_name.strip()

            vanity = extract_vanity_name(cleaned_url)

            lead_data = {
                "raw_url": raw_url or "",
                "linkedin_url": cleaned_url,
                "vanity_name": vanity,
                "first_name": first_name,
                "last_name": (row.get(header_mapping.get("last_name", "")) or "").strip(),
                "company_name": company_name,
                "job_title": (row.get(header_mapping.get("job_title", "")) or "").strip(),
                "location": (row.get(header_mapping.get("location", "")) or "").strip(),
                "email": (row.get(header_mapping.get("email", "")) or "").strip() or None,
                "phone": (row.get(header_mapping.get("phone", "")) or "").strip() or None,
                "custom_variables": {},
                "source": "csv",
            }
            if vanity:
                lead_data["custom_variables"]["vanity_handle"] = vanity

            # Collect any additional columns as custom variables for dynamic template tags
            mapped_values = set(header_mapping.values())
            for col_name, val in row.items():
                if col_name and col_name not in mapped_values and isinstance(val, str) and val:
                    lead_data["custom_variables"][col_name.strip()] = val.strip()

            parsed_leads.append(lead_data)

        return parsed_leads

    @staticmethod
    async def preview_leads(
        leads: list[dict[str, Any]],
        campaign_id: str,
        workspace_id: str,
        db: AsyncIOMotorDatabase,
        skip_already_contacted: bool = True,
        skip_do_not_contact: bool = True,
        require_name: bool = False,
    ) -> dict[str, Any]:
        """
        Validates lead intake preview against deduplication, DNC, and field requirements.
        Returns row-level statuses and summary counts before committing ingestion.
        """
        if not leads:
            return {
                "total_submitted": 0,
                "valid_count": 0,
                "duplicate_count": 0,
                "contacted_count": 0,
                "dnc_count": 0,
                "invalid_count": 0,
                "rows": [],
            }

        candidate_urls: set[str] = set()
        for lead in leads:
            url = normalize_linkedin_url(lead.get("linkedin_url", "") or lead.get("raw_url", ""))
            if url:
                candidate_urls.update(_host_variants(url))

        # 1. Fetch existing leads in this campaign
        existing_campaign_leads = await _fetch_cursor_docs(
            db.outreach_leads.find({
                "campaign_id": campaign_id,
                "workspace_id": workspace_id,
                "linkedin_url": {"$in": list(candidate_urls)},
            }, {"linkedin_url": 1}),
            length=max(len(candidate_urls), 1),
        )
        existing_urls = {_dedupe_key(doc["linkedin_url"]) for doc in existing_campaign_leads if "linkedin_url" in doc}

        # 2. Fetch cross-campaign contacted leads if enabled
        cross_campaign_urls = set()
        if skip_already_contacted:
            contacted_docs = await _fetch_cursor_docs(
                db.outreach_leads.find(
                    {
                        "workspace_id": workspace_id,
                        "last_action_at": {"$ne": None},
                        "linkedin_url": {"$in": list(candidate_urls)},
                    },
                    {"linkedin_url": 1},
                ),
                length=None,
            )
            cross_campaign_urls = {_dedupe_key(doc["linkedin_url"]) for doc in contacted_docs if "linkedin_url" in doc}

        # 3. Fetch Do-Not-Contact URLs
        dnc_urls = set()
        if skip_do_not_contact:
            dnc_docs = await _fetch_cursor_docs(
                db.outreach_do_not_contact.find({
                    "workspace_id": workspace_id,
                    "linkedin_url": {"$in": list(candidate_urls)},
                }, {"linkedin_url": 1}),
                length=max(len(candidate_urls), 1),
            )
            dnc_urls = {_dedupe_key(doc["linkedin_url"]) for doc in dnc_docs if "linkedin_url" in doc}

        rows: list[dict[str, Any]] = []
        seen_in_batch: set[str] = set()

        for idx, lead in enumerate(leads, start=1):
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            cleaned_url = normalize_linkedin_url(lead.get("linkedin_url") or raw_url)
            first_name = (lead.get("first_name") or "").strip()

            status = "valid"
            rejection_code = None
            error_reason = None

            if not cleaned_url:
                status = "rejected"
                rejection_code = "invalid_url"
                error_reason = f"Invalid LinkedIn profile URL '{raw_url}'. Expected format: https://linkedin.com/in/username"
            elif require_name and not first_name:
                status = "rejected"
                rejection_code = "missing_name"
                error_reason = "First name is required. Specify 'URL, First, Last' or supply a fallback name."
            else:
                key = _dedupe_key(cleaned_url)
                if key in seen_in_batch:
                    status = "rejected"
                    rejection_code = "duplicate_batch"
                    error_reason = "Duplicate profile URL in this import batch"
                elif key in existing_urls:
                    status = "rejected"
                    rejection_code = "duplicate_campaign"
                    error_reason = "Lead is already enrolled in this campaign"
                elif skip_already_contacted and key in cross_campaign_urls:
                    status = "rejected"
                    rejection_code = "duplicate_contacted"
                    error_reason = "Lead was already contacted in another workspace campaign"
                elif skip_do_not_contact and key in dnc_urls:
                    status = "rejected"
                    rejection_code = "do_not_contact"
                    error_reason = "Lead is on the Do-Not-Contact exclusion list"
                else:
                    seen_in_batch.add(key)

            rows.append({
                "row_number": idx,
                "raw_url": raw_url,
                "linkedin_url": cleaned_url or raw_url,
                "vanity_name": lead.get("vanity_name") or extract_vanity_name(cleaned_url),
                "first_name": first_name,
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "job_title": lead.get("job_title", ""),
                "status": status,
                "rejection_code": rejection_code,
                "error_reason": error_reason,
                "custom_variables": lead.get("custom_variables", {}),
            })

        valid_count = sum(1 for r in rows if r["status"] == "valid")
        duplicate_count = sum(1 for r in rows if r["rejection_code"] in {"duplicate_batch", "duplicate_campaign"})
        contacted_count = sum(1 for r in rows if r["rejection_code"] == "duplicate_contacted")
        dnc_count = sum(1 for r in rows if r["rejection_code"] == "do_not_contact")
        invalid_count = sum(1 for r in rows if r["rejection_code"] in {"invalid_url", "missing_name"})

        return {
            "total_submitted": len(leads),
            "valid_count": valid_count,
            "duplicate_count": duplicate_count,
            "contacted_count": contacted_count,
            "dnc_count": dnc_count,
            "invalid_count": invalid_count,
            "rows": rows,
        }

    @staticmethod
    async def ingest_leads(
        leads: list[dict[str, Any]],
        campaign_id: str,
        workspace_id: str,
        db: AsyncIOMotorDatabase,
        skip_already_contacted: bool = True,
        skip_do_not_contact: bool = True,
        campaign: dict[str, Any] | None = None,
        source: str = "csv",
        source_metadata: dict[str, Any] | None = None,
        require_name: bool = False,
        include_rejections: bool = False,
    ) -> dict[str, Any]:
        """
        Deduplicates and bulk-inserts parsed leads into MongoDB for the given campaign.
        Enforces identical dedupe/DNC rules as preview_leads.
        """
        if not leads:
            res = {"imported_count": 0, "skipped_count": 0, "duplicates_count": 0, "total_submitted": 0}
            if include_rejections:
                res["rejections"] = []
            return res

        if campaign is None:
            campaign = await db.outreach_campaigns.find_one({
                "id": campaign_id,
                "workspace_id": workspace_id,
                "is_deleted": {"$ne": True},
            })
        if not isinstance(campaign, dict):
            campaign = {}
        active_senders = []
        if campaign and campaign.get("status") == "active":
            configured_sender_ids = list(campaign.get("sender_account_ids", []))
            active_sender_docs = await _fetch_cursor_docs(
                db.outreach_accounts.find({
                    "id": {"$in": configured_sender_ids},
                    "workspace_id": workspace_id,
                    "status": "active",
                }),
                length=100,
            )
            active_senders = [account["id"] for account in active_sender_docs if account.get("id")]
        assigned_offset = 0
        root_node_id = None
        if active_senders:
            count_res = db.outreach_leads.count_documents({
                "campaign_id": campaign_id,
                "assigned_account_id": {"$in": active_senders},
            })
            if hasattr(count_res, "__await__"):
                count_res = await count_res
            assigned_offset = count_res if isinstance(count_res, (int, float)) else 0
            sequence = await db.outreach_sequences.find_one({
                "campaign_id": campaign_id,
                "is_deleted": {"$ne": True},
            })
            root_ids = (sequence or {}).get("compiled_dag", {}).get("root_node_ids", [])
            root_node_id = root_ids[0] if root_ids else None

        candidate_urls: set[str] = set()
        for lead in leads:
            url = normalize_linkedin_url(lead.get("linkedin_url", "") or lead.get("raw_url", ""))
            if url:
                candidate_urls.update(_host_variants(url))

        # 1. Fetch existing leads in this campaign for deduplication
        existing_campaign_leads = await _fetch_cursor_docs(
            db.outreach_leads.find({
                "campaign_id": campaign_id,
                "workspace_id": workspace_id,
                "linkedin_url": {"$in": list(candidate_urls)},
            }, {"linkedin_url": 1}),
            length=max(len(candidate_urls), 1),
        )
        existing_urls = {_dedupe_key(doc["linkedin_url"]) for doc in existing_campaign_leads if "linkedin_url" in doc}

        # 2. Fetch cross-campaign contacted leads if enabled
        cross_campaign_urls = set()
        if skip_already_contacted:
            contacted_docs = await _fetch_cursor_docs(
                db.outreach_leads.find(
                    {
                        "workspace_id": workspace_id,
                        "last_action_at": {"$ne": None},
                        "linkedin_url": {"$in": list(candidate_urls)},
                    },
                    {"linkedin_url": 1},
                ),
                length=None,
            )
            cross_campaign_urls = {_dedupe_key(doc["linkedin_url"]) for doc in contacted_docs if "linkedin_url" in doc}

        # 3. Fetch Do-Not-Contact URLs
        dnc_urls = set()
        dnc_docs = await _fetch_cursor_docs(
            db.outreach_do_not_contact.find({
                "workspace_id": workspace_id,
                "linkedin_url": {"$in": list(candidate_urls)},
            }, {"linkedin_url": 1}),
            length=max(len(candidate_urls), 1),
        )
        dnc_urls = {_dedupe_key(doc["linkedin_url"]) for doc in dnc_docs if "linkedin_url" in doc}

        to_insert: list[dict[str, Any]] = []
        seen_in_batch: set[str] = set()
        rejections: list[dict[str, Any]] = []
        duplicates_count = 0
        skipped_count = 0

        for lead in leads:
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            url = normalize_linkedin_url(lead.get("linkedin_url", "") or raw_url)
            first_name = (lead.get("first_name") or "").strip()

            if not url:
                skipped_count += 1
                rejections.append({
                    "linkedin_url": raw_url,
                    "first_name": first_name,
                    "rejection_code": "invalid_url",
                    "reason": f"Invalid LinkedIn profile URL '{raw_url}'",
                })
                continue

            if require_name and not first_name:
                skipped_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": "",
                    "rejection_code": "missing_name",
                    "reason": "First name is required for outreach personalization",
                })
                continue

            # Deduplicate within batch
            key = _dedupe_key(url)
            if key in seen_in_batch:
                duplicates_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_batch",
                    "reason": "Duplicate profile URL in this import batch",
                })
                continue
            seen_in_batch.add(key)

            # Deduplicate against campaign
            if key in existing_urls:
                duplicates_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_campaign",
                    "reason": "Already enrolled in this campaign",
                })
                continue

            # Deduplicate against previous campaigns
            if skip_already_contacted and key in cross_campaign_urls:
                skipped_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_contacted",
                    "reason": "Already contacted in another campaign",
                })
                continue

            # Check Do-Not-Contact list
            if key in dnc_urls:
                skipped_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "do_not_contact",
                    "reason": "Found on Do-Not-Contact exclusion list",
                })
                continue

            assigned_account_id = active_senders[(assigned_offset + len(to_insert)) % len(active_senders)] if active_senders else None
            meta = dict(source_metadata or {})
            meta.setdefault("source_type", source)
            meta.setdefault("consent_basis", "user_provided")
            meta.setdefault("imported_at", datetime.now(timezone.utc).isoformat())

            lead_doc = OutreachLead(
                campaign_id=campaign_id,
                workspace_id=workspace_id,
                assigned_account_id=assigned_account_id,
                current_node_id=root_node_id,
                linkedin_url=url,
                first_name=first_name,
                last_name=lead.get("last_name", ""),
                company_name=lead.get("company_name", ""),
                job_title=lead.get("job_title", ""),
                location=lead.get("location", ""),
                email=lead.get("email"),
                phone=lead.get("phone"),
                source=source,
                source_metadata=meta,
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
            "Campaign %s: Imported %s leads via %s (skipped: %s, duplicates: %s)",
            campaign_id, len(to_insert), source, skipped_count, duplicates_count,
        )

        res = {
            "imported_count": len(to_insert),
            "skipped_count": skipped_count,
            "duplicates_count": duplicates_count,
            "total_submitted": len(leads),
        }
        if include_rejections:
            res["rejections"] = rejections
        return res
