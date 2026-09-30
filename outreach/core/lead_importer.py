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
from outreach.models import OutreachLead, LeadExecutionState, LeadIdentifiers
from outreach.core.name_cleaner import clean_first_name

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
    "member_urn": ["member_urn", "linkedin_urn", "urn", "profile_urn", "member_id"],
    "sales_lead_urn": ["sales_lead_urn", "sales_urn", "sales_navigator_url", "sales_url", "sales_lead"],
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


def extract_sales_lead_urn(url_or_urn: str) -> str:
    """Extracts a sales profile URN or identifier from a Sales Navigator URL or raw URN."""
    if not url_or_urn:
        return ""
    val = url_or_urn.strip()
    if val.startswith("urn:li:fs_salesProfile:") or val.startswith("urn:li:salesProfile:"):
        return val
    if "sales/lead/" in val:
        match = re.search(r"sales/lead/([^/?#,]+)", val)
        if match:
            return match.group(1).rstrip(",")
    if "sales/people/" in val:
        match = re.search(r"sales/people/([^/?#,]+)", val)
        if match:
            return match.group(1).rstrip(",")
    return ""


def extract_member_urn(val: str) -> str:
    """Extracts standard member URN or numeric ID if present."""
    if not val:
        return ""
    val = val.strip()
    if val.startswith("urn:li:member:") or val.startswith("urn:li:person:"):
        return val
    if re.fullmatch(r"\d{6,14}", val):
        return f"urn:li:member:{val}"
    return ""


def build_lead_identifiers(
    raw_url: str | None = None,
    email: str | None = None,
    member_urn: str | None = None,
    sales_lead_urn: str | None = None,
    vanity_name: str | None = None,
) -> LeadIdentifiers:
    """
    Constructs a complete compound LeadIdentifiers object from available fields,
    normalizing public URLs, vanity handles, Sales Nav URNs, and email addresses.
    """
    cleaned_url = normalize_linkedin_url(raw_url or "") if raw_url else None
    extracted_vanity = extract_vanity_name(cleaned_url) if cleaned_url else (vanity_name or "").strip() or None

    extracted_sales = (
        (sales_lead_urn or "").strip()
        or (extract_sales_lead_urn(raw_url) if raw_url else None)
        or None
    )
    extracted_member = (
        (member_urn or "").strip()
        or (extract_member_urn(raw_url) if raw_url else None)
        or None
    )

    cleaned_email = (email or "").strip().lower() or None
    if cleaned_email and "@" not in cleaned_email:
        cleaned_email = None

    return LeadIdentifiers(
        normalized_url=cleaned_url,
        vanity_name=extracted_vanity,
        member_urn=extracted_member,
        sales_lead_urn=extracted_sales,
        email=cleaned_email,
    )


def extract_candidate_keys(ident: LeadIdentifiers) -> set[str]:
    """Generates distinct lookup keys for batch deduplication."""
    keys: set[str] = set()
    if ident.normalized_url:
        keys.add(f"url:{_dedupe_key(ident.normalized_url)}")
    if ident.vanity_name:
        keys.add(f"vanity:{ident.vanity_name.lower()}")
    if ident.member_urn:
        keys.add(f"member:{ident.member_urn}")
    if ident.sales_lead_urn:
        keys.add(f"sales:{ident.sales_lead_urn}")
    if ident.email:
        keys.add(f"email:{ident.email.lower()}")
    return keys


async def check_compound_suppression(
    workspace_id: str,
    candidates: list[dict[str, Any] | LeadIdentifiers],
    db: AsyncIOMotorDatabase,
    collection_name: str = "outreach_do_not_contact",
    extra_filter: dict[str, Any] | None = None,
) -> dict[int, dict[str, str]]:
    """
    Evaluates candidates against a target collection (e.g. outreach_do_not_contact, outreach_leads)
    using an indexed compound query across all populated keys:
    normalized_url (and host variants), vanity_name, member_urn, sales_lead_urn, and email.

    Returns a dict mapping candidate index (0-based) to match details:
    { candidate_index: {"matched_by": field_name, "matched_value": val, "reason": reason} }
    """
    if not candidates:
        return {}

    candidate_ids: list[LeadIdentifiers] = []
    for c in candidates:
        if isinstance(c, LeadIdentifiers):
            candidate_ids.append(c)
        elif isinstance(c, dict):
            if "identifiers" in c and isinstance(c["identifiers"], dict):
                candidate_ids.append(LeadIdentifiers(**c["identifiers"]))
            elif "identifiers" in c and isinstance(c["identifiers"], LeadIdentifiers):
                candidate_ids.append(c["identifiers"])
            else:
                candidate_ids.append(build_lead_identifiers(
                    raw_url=c.get("linkedin_url") or c.get("raw_url"),
                    email=c.get("email"),
                    member_urn=c.get("member_urn") or c.get("linkedin_urn"),
                    sales_lead_urn=c.get("sales_lead_urn"),
                    vanity_name=c.get("vanity_name"),
                ))
        else:
            candidate_ids.append(LeadIdentifiers())

    all_urls: set[str] = set()
    all_vanities: set[str] = set()
    all_members: set[str] = set()
    all_sales: set[str] = set()
    all_emails: set[str] = set()

    for ident in candidate_ids:
        if ident.normalized_url:
            all_urls.update(_host_variants(ident.normalized_url))
        if ident.vanity_name:
            all_vanities.add(ident.vanity_name.lower())
        if ident.member_urn:
            all_members.add(ident.member_urn)
        if ident.sales_lead_urn:
            all_sales.add(ident.sales_lead_urn)
        if ident.email:
            all_emails.add(ident.email.lower())

    clauses: list[dict[str, Any]] = []
    if all_urls:
        url_list = list(all_urls)
        clauses.append({"identifiers.normalized_url": {"$in": url_list}})
        clauses.append({"linkedin_url": {"$in": url_list}})
    if all_vanities:
        vanity_list = list(all_vanities)
        clauses.append({"identifiers.vanity_name": {"$in": vanity_list}})
        clauses.append({"vanity_name": {"$in": vanity_list}})
        for v in vanity_list:
            clauses.append({"linkedin_url": {"$in": list(_host_variants(f"https://linkedin.com/in/{v}"))}})
    if all_members:
        member_list = list(all_members)
        clauses.append({"identifiers.member_urn": {"$in": member_list}})
        clauses.append({"member_urn": {"$in": member_list}})
        clauses.append({"linkedin_urn": {"$in": member_list}})
    if all_sales:
        sales_list = list(all_sales)
        clauses.append({"identifiers.sales_lead_urn": {"$in": sales_list}})
        clauses.append({"sales_lead_urn": {"$in": sales_list}})
    if all_emails:
        email_list = list(all_emails)
        clauses.append({"identifiers.email": {"$in": email_list}})
        clauses.append({"email": {"$in": email_list}})

    if not clauses:
        return {}

    query: dict[str, Any] = {"workspace_id": workspace_id, "$or": clauses}
    if extra_filter:
        query.update(extra_filter)

    collection = getattr(db, collection_name, None)
    if collection is None:
        return {}

    if not hasattr(collection, "find") and hasattr(collection, "find_one"):
        doc_or_coro = collection.find_one(query)
        doc = await doc_or_coro if hasattr(doc_or_coro, "__await__") else doc_or_coro
        matched_docs = [doc] if doc else []
    else:
        matched_docs = await _fetch_cursor_docs(collection.find(query), length=None)
    if not matched_docs:
        return {}

    found_urls: set[str] = set()
    found_vanities: set[str] = set()
    found_members: set[str] = set()
    found_sales: set[str] = set()
    found_emails: set[str] = set()
    doc_reasons: dict[str, str] = {}

    for doc in matched_docs:
        reason = doc.get("reason") or "Matched suppression record"
        if doc.get("linkedin_url"):
            url_norm = _dedupe_key(doc["linkedin_url"])
            if url_norm:
                found_urls.add(url_norm)
                doc_reasons[f"url:{url_norm}"] = reason
            v = extract_vanity_name(doc["linkedin_url"])
            if v:
                found_vanities.add(v.lower())
                doc_reasons[f"vanity:{v.lower()}"] = reason
        if doc.get("vanity_name"):
            v = doc["vanity_name"].lower()
            found_vanities.add(v)
            doc_reasons[f"vanity:{v}"] = reason
        if doc.get("member_urn"):
            found_members.add(doc["member_urn"])
            doc_reasons[f"member:{doc['member_urn']}"] = reason
        if doc.get("linkedin_urn"):
            found_members.add(doc["linkedin_urn"])
            doc_reasons[f"member:{doc['linkedin_urn']}"] = reason
        if doc.get("sales_lead_urn"):
            found_sales.add(doc["sales_lead_urn"])
            doc_reasons[f"sales:{doc['sales_lead_urn']}"] = reason
        if doc.get("email"):
            em = doc["email"].lower()
            found_emails.add(em)
            doc_reasons[f"email:{em}"] = reason

        ident = doc.get("identifiers")
        if isinstance(ident, dict):
            if ident.get("normalized_url"):
                u_norm = _dedupe_key(ident["normalized_url"])
                if u_norm:
                    found_urls.add(u_norm)
                    doc_reasons[f"url:{u_norm}"] = reason
            if ident.get("vanity_name"):
                v = ident["vanity_name"].lower()
                found_vanities.add(v)
                doc_reasons[f"vanity:{v}"] = reason
            if ident.get("member_urn"):
                found_members.add(ident["member_urn"])
                doc_reasons[f"member:{ident['member_urn']}"] = reason
            if ident.get("sales_lead_urn"):
                found_sales.add(ident["sales_lead_urn"])
                doc_reasons[f"sales:{ident['sales_lead_urn']}"] = reason
            if ident.get("email"):
                em = ident["email"].lower()
                found_emails.add(em)
                doc_reasons[f"email:{em}"] = reason

    suppressed: dict[int, dict[str, str]] = {}
    for idx, ident in enumerate(candidate_ids):
        if ident.normalized_url and _dedupe_key(ident.normalized_url) in found_urls:
            key = f"url:{_dedupe_key(ident.normalized_url)}"
            suppressed[idx] = {
                "matched_by": "normalized_url",
                "matched_value": ident.normalized_url,
                "reason": doc_reasons.get(key, "Matched by LinkedIn URL"),
            }
            continue

        if ident.vanity_name and ident.vanity_name.lower() in found_vanities:
            key = f"vanity:{ident.vanity_name.lower()}"
            suppressed[idx] = {
                "matched_by": "vanity_name",
                "matched_value": ident.vanity_name,
                "reason": doc_reasons.get(key, "Matched by LinkedIn vanity handle"),
            }
            continue

        if ident.member_urn and ident.member_urn in found_members:
            key = f"member:{ident.member_urn}"
            suppressed[idx] = {
                "matched_by": "member_urn",
                "matched_value": ident.member_urn,
                "reason": doc_reasons.get(key, "Matched by LinkedIn member URN"),
            }
            continue

        if ident.sales_lead_urn and ident.sales_lead_urn in found_sales:
            key = f"sales:{ident.sales_lead_urn}"
            suppressed[idx] = {
                "matched_by": "sales_lead_urn",
                "matched_value": ident.sales_lead_urn,
                "reason": doc_reasons.get(key, "Matched by Sales Navigator identifier"),
            }
            continue

        if ident.email and ident.email.lower() in found_emails:
            key = f"email:{ident.email.lower()}"
            suppressed[idx] = {
                "matched_by": "email",
                "matched_value": ident.email,
                "reason": doc_reasons.get(key, "Matched by email address"),
            }
            continue

    return suppressed


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

            raw_first = first_name
            cleaned_first = clean_first_name(raw_first)
            identifiers = build_lead_identifiers(
                raw_url=cleaned_url or raw_url,
                vanity_name=vanity,
            )

            lead_data = {
                "raw_url": raw_url,
                "linkedin_url": cleaned_url,
                "vanity_name": vanity,
                "raw_first_name": raw_first,
                "cleaned_first_name": cleaned_first,
                "first_name": cleaned_first or raw_first,
                "last_name": last_name,
                "company_name": company_name,
                "job_title": job_title,
                "location": "",
                "email": None,
                "phone": None,
                "identifiers": identifiers.model_dump(),
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

            raw_first = (row.get(header_mapping.get("first_name", "")) or "").strip()
            if not raw_first and default_first_name:
                raw_first = default_first_name.strip()
            cleaned_first = clean_first_name(raw_first)

            company_name = (row.get(header_mapping.get("company_name", "")) or "").strip()
            if not company_name and default_company_name:
                company_name = default_company_name.strip()

            vanity = extract_vanity_name(cleaned_url)
            member_urn = (row.get(header_mapping.get("member_urn", "")) or "").strip() or None
            sales_lead_urn = (row.get(header_mapping.get("sales_lead_urn", "")) or "").strip() or None
            email = (row.get(header_mapping.get("email", "")) or "").strip() or None

            identifiers = build_lead_identifiers(
                raw_url=cleaned_url or raw_url,
                email=email,
                member_urn=member_urn,
                sales_lead_urn=sales_lead_urn,
                vanity_name=vanity,
            )

            lead_data = {
                "raw_url": raw_url or "",
                "linkedin_url": cleaned_url,
                "vanity_name": vanity,
                "raw_first_name": raw_first,
                "cleaned_first_name": cleaned_first,
                "first_name": cleaned_first or raw_first,
                "last_name": (row.get(header_mapping.get("last_name", "")) or "").strip(),
                "company_name": company_name,
                "job_title": (row.get(header_mapping.get("job_title", "")) or "").strip(),
                "location": (row.get(header_mapping.get("location", "")) or "").strip(),
                "email": email,
                "phone": (row.get(header_mapping.get("phone", "")) or "").strip() or None,
                "identifiers": identifiers.model_dump(),
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

        # 1. Fetch existing leads in this campaign (compound)
        campaign_dupes = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_leads",
            extra_filter={"campaign_id": campaign_id},
        )

        # 2. Fetch cross-campaign contacted leads if enabled (compound)
        cross_campaign_dupes = {}
        if skip_already_contacted:
            cross_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"last_action_at": {"$ne": None}},
            )

        # 3. Fetch Do-Not-Contact records (compound)
        dnc_matches = {}
        if skip_do_not_contact:
            dnc_matches = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_do_not_contact",
            )

        # 4. Fetch Withdrawn Invites within 21-day reinvite block window (compound)
        now_dt = datetime.now(timezone.utc)
        withdrawn_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_withdrawn_invites",
            extra_filter={"reinvite_blocked_until": {"$gt": now_dt}},
        )

        rows: list[dict[str, Any]] = []
        seen_batch_keys: set[str] = set()

        for idx, lead in enumerate(leads, start=1):
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            cleaned_url = normalize_linkedin_url(lead.get("linkedin_url") or raw_url)
            first_name = (lead.get("first_name") or "").strip()
            raw_first = lead.get("raw_first_name") or first_name
            cleaned_first = lead.get("cleaned_first_name") or clean_first_name(raw_first)
            vanity = lead.get("vanity_name") or extract_vanity_name(cleaned_url)

            # Build candidate identifiers
            if "identifiers" in lead and isinstance(lead["identifiers"], dict):
                ident = LeadIdentifiers(**lead["identifiers"])
            else:
                ident = build_lead_identifiers(
                    raw_url=cleaned_url or raw_url,
                    email=lead.get("email"),
                    member_urn=lead.get("member_urn") or lead.get("linkedin_urn"),
                    sales_lead_urn=lead.get("sales_lead_urn"),
                    vanity_name=vanity,
                )

            cand_keys = extract_candidate_keys(ident)

            status = "valid"
            rejection_code = None
            error_reason = None

            if not cleaned_url:
                status = "rejected"
                rejection_code = "invalid_url"
                error_reason = f"Invalid LinkedIn profile URL '{raw_url}'. Expected format: https://linkedin.com/in/username"
            elif require_name and not (cleaned_first or first_name):
                status = "rejected"
                rejection_code = "missing_name"
                error_reason = "First name is required. Specify 'URL, First, Last' or supply a fallback name."
            elif cand_keys and (cand_keys & seen_batch_keys):
                status = "rejected"
                rejection_code = "duplicate_batch"
                error_reason = "Duplicate profile URL or contact identifier in this import batch"
            elif (idx - 1) in campaign_dupes:
                status = "rejected"
                rejection_code = "duplicate_campaign"
                match_info = campaign_dupes[idx - 1]
                error_reason = f"Lead is already enrolled in this campaign (matched by {match_info.get('matched_by', 'identifier')})"
            elif skip_already_contacted and (idx - 1) in cross_campaign_dupes:
                status = "rejected"
                rejection_code = "duplicate_contacted"
                match_info = cross_campaign_dupes[idx - 1]
                error_reason = f"Lead was already contacted in another workspace campaign (matched by {match_info.get('matched_by', 'identifier')})"
            elif skip_do_not_contact and (idx - 1) in dnc_matches:
                status = "rejected"
                rejection_code = "do_not_contact"
                match_info = dnc_matches[idx - 1]
                error_reason = f"Lead is on the Do-Not-Contact exclusion list ({match_info.get('reason', 'Manual exclusion')})"
            elif (idx - 1) in withdrawn_matches:
                status = "rejected"
                rejection_code = "withdrawn_cooldown"
                match_info = withdrawn_matches[idx - 1]
                error_reason = f"Invitation recently withdrawn; LinkedIn blocks re-inviting for 21 days ({match_info.get('reason', 'Withdrawn cooldown')})"
            else:
                seen_batch_keys.update(cand_keys)

            rows.append({
                "row_number": idx,
                "raw_url": raw_url,
                "linkedin_url": cleaned_url or raw_url,
                "vanity_name": vanity,
                "raw_first_name": raw_first,
                "cleaned_first_name": cleaned_first,
                "first_name": cleaned_first or raw_first,
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "job_title": lead.get("job_title", ""),
                "email": lead.get("email"),
                "phone": lead.get("phone"),
                "status": status,
                "rejection_code": rejection_code,
                "error_reason": error_reason,
                "custom_variables": lead.get("custom_variables", {}),
                "identifiers": ident.model_dump(),
            })

        valid_count = sum(1 for r in rows if r["status"] == "valid")
        duplicate_count = sum(1 for r in rows if r["rejection_code"] in {"duplicate_batch", "duplicate_campaign"})
        contacted_count = sum(1 for r in rows if r["rejection_code"] == "duplicate_contacted")
        dnc_count = sum(1 for r in rows if r["rejection_code"] == "do_not_contact")
        withdrawn_count = sum(1 for r in rows if r["rejection_code"] == "withdrawn_cooldown")
        invalid_count = sum(1 for r in rows if r["rejection_code"] in {"invalid_url", "missing_name"})

        return {
            "total_submitted": len(leads),
            "valid_count": valid_count,
            "duplicate_count": duplicate_count,
            "contacted_count": contacted_count,
            "dnc_count": dnc_count,
            "withdrawn_count": withdrawn_count,
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
        Enforces compound dedupe/DNC rules across URL, vanity, member URN, Sales Nav URN, and email.
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

        # 1. Fetch existing leads in this campaign for deduplication (compound)
        campaign_dupes = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_leads",
            extra_filter={"campaign_id": campaign_id},
        )

        # 2. Fetch cross-campaign contacted leads if enabled (compound)
        cross_campaign_dupes = {}
        if skip_already_contacted:
            cross_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"last_action_at": {"$ne": None}},
            )

        # 3. Fetch Do-Not-Contact records (mandatory compound check)
        dnc_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_do_not_contact",
        )

        # 4. Fetch Withdrawn Invites within 21-day reinvite block window (mandatory compound check)
        now_dt = datetime.now(timezone.utc)
        withdrawn_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_withdrawn_invites",
            extra_filter={"reinvite_blocked_until": {"$gt": now_dt}},
        )

        to_insert: list[dict[str, Any]] = []
        seen_batch_keys: set[str] = set()
        rejections: list[dict[str, Any]] = []
        duplicates_count = 0
        skipped_count = 0

        for idx, lead in enumerate(leads):
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            url = normalize_linkedin_url(lead.get("linkedin_url", "") or raw_url)
            first_name = (lead.get("first_name") or "").strip()
            raw_first = lead.get("raw_first_name") or first_name
            cleaned_first = lead.get("cleaned_first_name") or clean_first_name(raw_first)
            vanity = lead.get("vanity_name") or extract_vanity_name(url)

            if "identifiers" in lead and isinstance(lead["identifiers"], dict):
                ident = LeadIdentifiers(**lead["identifiers"])
            else:
                ident = build_lead_identifiers(
                    raw_url=url or raw_url,
                    email=lead.get("email"),
                    member_urn=lead.get("member_urn") or lead.get("linkedin_urn"),
                    sales_lead_urn=lead.get("sales_lead_urn"),
                    vanity_name=vanity,
                )

            cand_keys = extract_candidate_keys(ident)

            if not url:
                skipped_count += 1
                rejections.append({
                    "linkedin_url": raw_url,
                    "first_name": first_name,
                    "rejection_code": "invalid_url",
                    "reason": f"Invalid LinkedIn profile URL '{raw_url}'",
                })
                continue

            if require_name and not (cleaned_first or first_name):
                skipped_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": "",
                    "rejection_code": "missing_name",
                    "reason": "First name is required for outreach personalization",
                })
                continue

            # Deduplicate within batch
            if cand_keys and (cand_keys & seen_batch_keys):
                duplicates_count += 1
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_batch",
                    "reason": "Duplicate profile URL or identifier in this import batch",
                })
                continue

            # Deduplicate against campaign
            if idx in campaign_dupes:
                duplicates_count += 1
                match_info = campaign_dupes[idx]
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_campaign",
                    "reason": f"Already enrolled in this campaign (matched by {match_info.get('matched_by', 'identifier')})",
                })
                continue

            # Deduplicate against previous campaigns
            if skip_already_contacted and idx in cross_campaign_dupes:
                skipped_count += 1
                match_info = cross_campaign_dupes[idx]
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_contacted",
                    "reason": f"Already contacted in another campaign (matched by {match_info.get('matched_by', 'identifier')})",
                })
                continue

            # Check Do-Not-Contact list (always mandatory)
            if idx in dnc_matches:
                skipped_count += 1
                match_info = dnc_matches[idx]
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "do_not_contact",
                    "reason": f"Found on Do-Not-Contact exclusion list ({match_info.get('reason', 'Manual exclusion')})",
                })
                continue

            # Check Withdrawn Invites cooldown (mandatory)
            if idx in withdrawn_matches:
                skipped_count += 1
                match_info = withdrawn_matches[idx]
                rejections.append({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "withdrawn_cooldown",
                    "reason": f"Invitation recently withdrawn; LinkedIn blocks re-inviting for 21 days ({match_info.get('reason', 'Withdrawn cooldown')})",
                })
                continue

            seen_batch_keys.update(cand_keys)

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
                linkedin_urn=ident.member_urn or lead.get("linkedin_urn"),
                identifiers=ident,
                raw_first_name=raw_first,
                cleaned_first_name=cleaned_first,
                first_name=cleaned_first or raw_first or first_name,
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
