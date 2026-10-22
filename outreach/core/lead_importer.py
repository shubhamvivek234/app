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
from fastapi import HTTPException
from outreach.models import OutreachLead, LeadExecutionState, LeadIdentifiers, generate_uuid
from outreach.core.name_cleaner import clean_first_name
from outreach.core.workspace_scope import workspace_scope
from outreach.core.import_context import ImportScope, check_campaign_scope

logger = logging.getLogger(__name__)
MAX_ADMISSION_ROWS = 1000

# Common header aliases for automated column discovery
COLUMN_ALIASES = {
    "linkedin_url": [
        "linkedin", "linkedin_url", "profile_url", "linkedin profile", "url",
        "linkedin url", "linkedin profile url", "linkedin_profile", "linkedin profile link",
        "person linkedin url", "contact linkedin",
    ],
    "first_name": ["first_name", "first name", "firstname", "first", "given name"],
    "last_name": ["last_name", "last name", "lastname", "last", "surname"],
    "full_name": ["full_name", "full name", "fullname", "name", "contact_name", "person_name", "prospect_name"],
    "company_name": ["company", "company_name", "company name", "organization", "employer"],
    "job_title": ["title", "job_title", "job title", "position", "role", "headline"],
    "headline": ["headline", "linkedin_headline", "profile_headline"],
    "industry": ["industry", "sector", "vertical"],
    "location": ["location", "city", "country", "geo", "region"],
    "company_location": ["company_location", "company location", "hq_location", "company_hq", "company city"],
    "connections_count": ["connections_count", "connections", "number_of_connections", "number of connections", "followers"],
    "top_skill": ["top_skill", "top skill", "skills", "primary_skill", "skill"],
    "summary": ["summary", "about", "bio", "linkedin_summary"],
    "school": ["school", "education", "university", "college", "alma_mater"],
    "years_in_company": ["years_in_company", "years in company", "company_tenure"],
    "years_in_role": ["years_in_role", "years in role", "role_tenure"],
    "mutual_connections": ["mutual_connections", "mutual connections", "shared_connections"],
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


def normalize_any_linkedin_profile_url(raw_url: str) -> str:
    """
    Normalizes any LinkedIn profile URL across Standard (/in/, /pub/),
    Sales Navigator (/sales/lead/, /sales/people/), and Recruiter (/talent/profile/, /talent/hire/.../profile/).
    """
    standard = normalize_linkedin_url(raw_url)
    if standard:
        return standard
    if not raw_url:
        return ""
    raw = raw_url.strip()
    raw = re.sub(r"\?.*$", "", raw)
    if raw.lower().startswith("http://"):
        raw = "https://" + raw[7:]
    elif not raw.lower().startswith("https://"):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if host not in {"linkedin.com", "www.linkedin.com"}:
        return ""
    path = (parsed.path or "").rstrip("/")
    # Public /pub/<slug> profile URLs
    pub_match = re.match(r"^/pub/([A-Za-z0-9._-]+)(?:/.*)?$", path)
    if pub_match and pub_match.group(1) not in {".", ".."}:
        return f"https://{host}/in/{pub_match.group(1).lower()}"
    # Sales Navigator profile URLs (/sales/lead/<id> or /sales/people/<id>)
    sales_match = re.match(r"^/sales/(?:lead|people)/([^/?#]+)$", path, re.IGNORECASE)
    if sales_match:
        token = sales_match.group(1).split(",")[0].strip()
        if token and re.fullmatch(r"[A-Za-z0-9._:-]+", token):
            return f"https://{host}/sales/lead/{token}"
    # LinkedIn Recruiter profile URLs (/talent/profile/<id> or /talent/hire/<proj>/profile/<id>)
    recruiter_match = re.match(r"^/talent/(?:hire/[^/]+/)?profile/([^/?#]+)$", path, re.IGNORECASE)
    if recruiter_match:
        token = recruiter_match.group(1).split(",")[0].strip()
        if token and re.fullmatch(r"[A-Za-z0-9._:-]+", token):
            return f"https://{host}/talent/profile/{token}"
    return ""


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
    """Extracts a sales/recruiter profile URN or identifier from a Sales Navigator / Recruiter URL or raw URN."""
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
    if "talent/profile/" in val:
        match = re.search(r"talent/profile/([^/?#,]+)", val)
        if match:
            return match.group(1).rstrip(",")
    if "/profile/" in val and "talent/hire/" in val:
        match = re.search(r"talent/hire/[^/]+/profile/([^/?#,]+)", val)
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


def intake_identifiers(lead: dict[str, Any]) -> tuple[LeadIdentifiers, set[str], LeadIdentifiers]:
    """Keep saved aliases and canonical current identities distinct through storage."""
    current = build_lead_identifiers(
        raw_url=lead.get("linkedin_url") or lead.get("raw_url"), email=lead.get("email"),
        member_urn=lead.get("member_urn") or lead.get("linkedin_urn"),
        sales_lead_urn=lead.get("sales_lead_urn"), vanity_name=lead.get("vanity_name"))
    saved = lead.get("identifiers")
    if isinstance(saved, dict):
        saved = LeadIdentifiers(**saved)
    if not isinstance(saved, LeadIdentifiers):
        saved = LeadIdentifiers()
    saved = LeadIdentifiers(**{
        key: (normalize_linkedin_url(value) or None) if key == "normalized_url" else
        (value.strip().lower() or None) if key in {"email", "vanity_name"} else (value.strip() or None)
        for key, value in saved.model_dump().items() if value
    })
    # Saved identities can still be useful after profile discovery changes a URL.
    # Empty/partial saved values must not erase the current URL/email identity.
    identifiers = LeadIdentifiers(**{key: value or current.model_dump()[key]
        for key, value in saved.model_dump().items()})
    keys = extract_candidate_keys(identifiers) | extract_candidate_keys(current)
    for field, argument in (("vanity_name", "vanity_name"), ("linkedin_urn", "member_urn")):
        if isinstance(lead.get(field), str) and lead[field].strip():
            keys.update(extract_candidate_keys(build_lead_identifiers(**{argument: lead[field]})))
    return identifiers, keys, current


def intake_names(lead: dict[str, Any]) -> tuple[str, str, str]:
    """An explicit empty edited name must not resurrect its original value."""
    first = (lead.get("first_name") or "").strip()
    raw = lead.get("raw_first_name")
    raw = raw if isinstance(raw, str) else first
    edited = lead.get("cleaned_first_name")
    cleaned = edited.strip() if isinstance(edited, str) else clean_first_name(raw)
    effective = cleaned if isinstance(edited, str) else cleaned or first
    return raw, cleaned, effective


async def check_compound_suppression(
    workspace_id: str,
    candidates: list[dict[str, Any] | LeadIdentifiers],
    db: AsyncIOMotorDatabase,
    collection_name: str = "outreach_do_not_contact",
    extra_filter: dict[str, Any] | None = None,
    max_matches: int | None = None,
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
            if isinstance(c.get("identifiers"), (dict, LeadIdentifiers)):
                candidate_ids.append(intake_identifiers(c)[0])
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

    # Discovery/reconnection may update current fields after import. Keep both
    # the saved identity aliases and current fields in the exclusion query.
    candidate_owners = list(range(len(candidate_ids)))
    for idx, candidate in enumerate(candidates):
        if isinstance(candidate, dict) and isinstance(candidate.get("identifiers"), (dict, LeadIdentifiers)):
            candidate_ids.append(build_lead_identifiers(
                raw_url=candidate.get("linkedin_url") or candidate.get("raw_url"), email=candidate.get("email"),
                member_urn=candidate.get("member_urn") or candidate.get("linkedin_urn"),
                sales_lead_urn=candidate.get("sales_lead_urn"), vanity_name=candidate.get("vanity_name")))
            candidate_owners.append(idx)

    # A discovered explicit handle can differ from the handle extracted from
    # the current URL. Keep both aliases rather than letting URL precedence
    # discard an identity used by a later DNC or reply stop.
    for idx, candidate in enumerate(candidates):
        if isinstance(candidate, dict) and isinstance(candidate.get("vanity_name"), str) and candidate["vanity_name"].strip():
            candidate_ids.append(build_lead_identifiers(vanity_name=candidate["vanity_name"]))
            candidate_owners.append(idx)
        if isinstance(candidate, dict) and isinstance(candidate.get("linkedin_urn"), str) and candidate["linkedin_urn"].strip():
            candidate_ids.append(build_lead_identifiers(member_urn=candidate["linkedin_urn"]))
            candidate_owners.append(idx)

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

    query: dict[str, Any] = {**workspace_scope(workspace_id), "$or": clauses}
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
        if max_matches is None:
            matched_docs = await _fetch_cursor_docs(collection.find(query), length=None)
        else:
            projection = {key: 1 for key in ("identifiers", "linkedin_url", "vanity_name", "member_urn", "linkedin_urn", "sales_lead_urn", "email", "reason")}
            matched_docs = await _fetch_cursor_docs(collection.find(query, projection).limit(max_matches + 1), length=max_matches + 1)
            if len(matched_docs) > max_matches:
                raise HTTPException(503, "Contact exclusion history exceeds this review's bound; no import was confirmed")
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
    for position, ident in enumerate(candidate_ids):
        idx = candidate_owners[position]
        if idx in suppressed:
            continue
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
            except Exception as exc:
                logger.debug("Pasted URL CSV row parser fallback (%s)", type(exc).__name__)
                row = [c.strip() for c in line.split(delimiter)]
            row = [col.strip() for col in row if col is not None]
            if not row:
                continue

            # Handle space-separated URL and names if single unquoted column
            if len(row) == 1 and " " in row[0]:
                words = row[0].split()
                if "linkedin.com" in words[0].lower() or normalize_any_linkedin_profile_url(words[0]):
                    row = [words[0], " ".join(words[1:])]

            # Identify column with LinkedIn URL
            url_idx = -1
            for idx, col in enumerate(row):
                if "linkedin.com" in col.lower() or normalize_any_linkedin_profile_url(col):
                    url_idx = idx
                    break

            if url_idx != -1:
                raw_url = row[url_idx]
                other_cols = [c for i, c in enumerate(row) if i != url_idx and c]
            else:
                raw_url = row[0]
                other_cols = row[1:]

            cleaned_url = normalize_linkedin_url(raw_url) or normalize_any_linkedin_profile_url(raw_url)
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

            cleaned_url = normalize_linkedin_url(raw_url or "") or normalize_any_linkedin_profile_url(raw_url or "")
            if not cleaned_url and not include_invalid:
                continue

            raw_first = (row.get(header_mapping.get("first_name", "")) or "").strip()
            raw_last = (row.get(header_mapping.get("last_name", "")) or "").strip()
            if not raw_first and "full_name" in header_mapping:
                full_val = (row.get(header_mapping["full_name"]) or "").strip()
                if full_val:
                    parts = full_val.split(maxsplit=1)
                    raw_first = parts[0]
                    if not raw_last and len(parts) > 1:
                        raw_last = parts[1]
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
                "last_name": raw_last,
                "company_name": company_name,
                "job_title": (row.get(header_mapping.get("job_title", "")) or "").strip(),
                "headline": (row.get(header_mapping.get("headline", "")) or "").strip(),
                "industry": (row.get(header_mapping.get("industry", "")) or "").strip(),
                "location": (row.get(header_mapping.get("location", "")) or "").strip(),
                "company_location": (row.get(header_mapping.get("company_location", "")) or "").strip(),
                "connections_count": (row.get(header_mapping.get("connections_count", "")) or "").strip() or None,
                "top_skill": (row.get(header_mapping.get("top_skill", "")) or "").strip(),
                "summary": (row.get(header_mapping.get("summary", "")) or "").strip(),
                "school": (row.get(header_mapping.get("school", "")) or "").strip(),
                "years_in_company": (row.get(header_mapping.get("years_in_company", "")) or "").strip(),
                "years_in_role": (row.get(header_mapping.get("years_in_role", "")) or "").strip(),
                "mutual_connections": (row.get(header_mapping.get("mutual_connections", "")) or "").strip(),
                "email": email,
                "phone": (row.get(header_mapping.get("phone", "")) or "").strip() or None,
                "identifiers": identifiers.model_dump(),
                "custom_variables": {},
                "source": "csv",
            }
            if vanity:
                lead_data["custom_variables"]["vanity_handle"] = vanity

            # Collect any additional columns as custom variables for dynamic template tags
            core_fields = {
                "linkedin_url", "first_name", "last_name", "full_name",
                "company_name", "job_title", "location", "email", "phone",
                "member_urn", "sales_lead_urn",
            }
            mapped_values = {col for key, col in header_mapping.items() if key in core_fields}
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
        _match_limit: int | None = None,
        skip_team_campaign_leads: bool | None = None,
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

        if skip_team_campaign_leads is None and hasattr(db, "outreach_campaigns"):
            try:
                c_doc = await db.outreach_campaigns.find_one({"id": campaign_id, **workspace_scope(workspace_id)})
                if isinstance(c_doc, dict):
                    skip_team_campaign_leads = bool(c_doc.get("skip_team_campaign_leads"))
            except Exception as exc:
                logger.debug("Campaign team deduplication setting lookup skipped for campaign=%s (%s)", campaign_id, type(exc).__name__)
                skip_team_campaign_leads = False
        skip_team = bool(skip_team_campaign_leads)

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
            max_matches=_match_limit,
        )

        # 2. Fetch cross-campaign contacted leads or team campaign leads if enabled (compound)
        cross_campaign_dupes = {}
        if skip_already_contacted:
            cross_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"last_action_at": {"$ne": None}},
                max_matches=_match_limit,
            )
        team_campaign_dupes = {}
        if skip_team:
            team_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"campaign_id": {"$ne": campaign_id}},
                max_matches=_match_limit,
            )

        # 3. Fetch Do-Not-Contact records (compound)
        dnc_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_do_not_contact",
            max_matches=_match_limit,
        )

        email_matches = await check_compound_suppression(
            workspace_id=workspace_id, candidates=leads, db=db, collection_name="outreach_email_suppressions",
            max_matches=_match_limit)

        # 4. Fetch Withdrawn Invites within 21-day reinvite block window (compound)
        now_dt = datetime.now(timezone.utc)
        withdrawn_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_withdrawn_invites",
            extra_filter={"reinvite_blocked_until": {"$gt": now_dt}},
            max_matches=_match_limit,
        )

        rows: list[dict[str, Any]] = []
        seen_batch_keys: set[str] = set()

        for idx, lead in enumerate(leads, start=1):
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            cleaned_url = (
                normalize_linkedin_url(lead.get("linkedin_url") or raw_url)
                or normalize_any_linkedin_profile_url(lead.get("linkedin_url") or raw_url)
            )
            raw_first, cleaned_first, first_name = intake_names(lead)
            vanity = (lead.get("vanity_name") or extract_vanity_name(cleaned_url)).strip().lower()

            ident, cand_keys, current_ident = intake_identifiers(lead)

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
            elif skip_team and (idx - 1) in team_campaign_dupes:
                status = "rejected"
                rejection_code = "duplicate_team_campaign"
                match_info = team_campaign_dupes[idx - 1]
                error_reason = f"Lead is already enrolled in another team member's campaign in this workspace (matched by {match_info.get('matched_by', 'identifier')})"
            elif (idx - 1) in dnc_matches:
                status = "rejected"
                rejection_code = "do_not_contact"
                match_info = dnc_matches[idx - 1]
                error_reason = f"Lead is on the Do-Not-Contact exclusion list ({match_info.get('reason', 'Manual exclusion')})"
            elif (idx - 1) in email_matches:
                status = "rejected"
                rejection_code = "email_suppressed"
                error_reason = "Email is on the workspace suppression list"
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
                "first_name": first_name,
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "job_title": lead.get("job_title", ""),
                "location": lead.get("location", ""),
                "email": (lead.get("email") or "").strip().lower() or None,
                "phone": lead.get("phone"),
                "status": status,
                "rejection_code": rejection_code,
                "error_reason": error_reason,
                "custom_variables": lead.get("custom_variables", {}),
                "identifiers": ident.model_dump(),
                "member_urn": current_ident.member_urn,
                "linkedin_urn": (lead.get("linkedin_urn") or current_ident.member_urn or "").strip() or None,
                "sales_lead_urn": current_ident.sales_lead_urn,
            })

        valid_count = sum(1 for r in rows if r["status"] == "valid")
        duplicate_count = sum(1 for r in rows if r["rejection_code"] in {"duplicate_batch", "duplicate_campaign", "duplicate_team_campaign"})
        contacted_count = sum(1 for r in rows if r["rejection_code"] == "duplicate_contacted")
        dnc_count = sum(1 for r in rows if r["rejection_code"] in {"do_not_contact", "email_suppressed"})
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
        *,
        _ordered: bool = False,
        _staged_rows: list[dict[str, Any]] | None = None,
        _record_decisions: bool = False,
        _match_limit: int | None = None,
        _import_scope: ImportScope | None = None,
        skip_team_campaign_leads: bool | None = None,
    ) -> dict[str, Any]:
        """
        Deduplicates and bulk-inserts parsed leads into MongoDB for the given campaign.
        Enforces compound dedupe/DNC rules across URL, vanity, member URN, Sales Nav URN, and email.
        """
        if len(leads) > MAX_ADMISSION_ROWS:
            raise HTTPException(422, f"Import at most {MAX_ADMISSION_ROWS} contacts at a time.")
        if not _ordered:
            from outreach.core.suppression import mutate_suppression, SuppressionUnavailable
            async def admit(current):
                return await LeadImporter.ingest_leads(leads, campaign_id, workspace_id, current,
                    skip_already_contacted, skip_do_not_contact, None, source, source_metadata,
                    require_name, include_rejections, _ordered=True, _staged_rows=_staged_rows, _record_decisions=_record_decisions, _match_limit=_match_limit, _import_scope=_import_scope, skip_team_campaign_leads=skip_team_campaign_leads)
            try:
                return await mutate_suppression(db, workspace_id, admit)
            except SuppressionUnavailable:
                raise HTTPException(503, "Could not confirm this import. Reload campaign contacts before retrying.") from None

        # Caller snapshots are advisory only. Admission uses the transaction's current parent.
        from outreach.core.search_sources import ensure_intake_provenance
        await ensure_intake_provenance(db, workspace_id, leads, source)
        campaign = await db.outreach_campaigns.find_one({
            "id": campaign_id, **workspace_scope(workspace_id), "is_deleted": {"$ne": True}})
        if not isinstance(campaign, dict):
            raise HTTPException(404, "Campaign not found")
        if _import_scope is not None:
            if type(_import_scope) is not ImportScope:
                raise HTTPException(503, "Import context needs review")
            owners = await db.outreach_campaigns.find({"id": campaign_id, **workspace_scope(workspace_id),
                "is_deleted": {"$ne": True}}, {"_id": 1}).limit(2).to_list(2)
            if len(owners) != 1:
                raise HTTPException(409, "Import campaign identity changed; review it again")
            check_campaign_scope(_import_scope, campaign)
        if campaign.get("status") not in {"draft", "paused", "active"}:
            raise HTTPException(409, "Campaign cannot accept contacts in its current state.")
        if campaign.get("launch_claim_token"):
            raise HTTPException(409, "Campaign launch is being prepared. Wait for its outcome before importing contacts.")
        if campaign.get("status") == "active":
            linked_list = await db.outreach_engage_lists.find_one({
                **workspace_scope(workspace_id), "campaign_id": campaign_id, "is_deleted": {"$ne": True}})
            if campaign.get("engage_list_id") or linked_list:
                raise HTTPException(409, "Pause this campaign before changing its engagement contacts.")
        # Write the parent so concurrent status/config edits conflict with admission's snapshot.
        parent = await db.outreach_campaigns.update_one({
            "id": campaign_id, **workspace_scope(workspace_id), "status": campaign["status"],
            **({"_id": campaign["_id"]} if _import_scope is not None else {}),
            "is_deleted": {"$ne": True}}, {"$inc": {"lead_admission_revision": 1}})
        if getattr(parent, "matched_count", 0) != 1:
            raise HTTPException(409, "Campaign changed. Reload before importing contacts.")

        if not leads:
            res = {"imported_count": 0, "skipped_count": 0, "duplicates_count": 0, "total_submitted": 0, "lead_ids": []}
            if _record_decisions:
                res["row_results"] = []
            if include_rejections:
                res["rejections"] = []
            return res

        active_senders = []
        if campaign and campaign.get("status") == "active":
            configured_sender_ids = list(campaign.get("sender_account_ids", []))
            if (not configured_sender_ids or len(configured_sender_ids) > 100
                    or any(not isinstance(value, str) or not value for value in configured_sender_ids)
                    or len(set(configured_sender_ids)) != len(configured_sender_ids)):
                raise HTTPException(409, "Campaign sender assignment needs review before importing contacts.")
            active_sender_docs = await _fetch_cursor_docs(
                db.outreach_accounts.find({
                    "id": {"$in": configured_sender_ids},
                    **workspace_scope(workspace_id),
                    "status": "active",
                    "is_deleted": {"$ne": True},
                }),
                length=100,
            )
            active_senders = sorted(account["id"] for account in active_sender_docs if account.get("id"))
            if set(active_senders) != set(configured_sender_ids):
                raise HTTPException(409, "Campaign sender assignment is no longer ready.")
            for account in active_sender_docs:
                checked = await db.outreach_accounts.update_one({
                    "id": account["id"], **workspace_scope(workspace_id), "status": "active",
                    "is_deleted": {"$ne": True}}, {"$inc": {"lead_admission_revision": 1}})
                if getattr(checked, "matched_count", 0) != 1:
                    raise HTTPException(409, "Campaign sender changed before importing contacts.")
        assigned_offset = 0
        root_node_id = None
        root_due = None
        if active_senders:
            count_res = db.outreach_leads.count_documents({
                "campaign_id": campaign_id,
                **workspace_scope(workspace_id),
                "assigned_account_id": {"$in": active_senders},
            })
            if hasattr(count_res, "__await__"):
                count_res = await count_res
            assigned_offset = count_res if isinstance(count_res, (int, float)) else 0
            from outreach.core.sequence_versions import load_sequence
            sequence = await load_sequence(db, workspace_id, campaign_id, campaign=campaign)
            from outreach.core.sequence_preview import validate_pinned_sequence, successor_fields
            from outreach.core.sequence_contract import DAGValidationError
            try:
                inspected = validate_pinned_sequence(sequence)
                root_ids = inspected['root_node_ids']
                root_node_id = root_ids[0]
                revision, version = campaign.get("authorization_revision"), sequence.get("version")
                if type(revision) is not int or revision < 1 or type(version) is not int or version < 1:
                    raise DAGValidationError('Campaign sequence authorization needs review.')
                root_base = datetime.now(timezone.utc)
                warmup = campaign.get('warmup_until')
                if warmup is not None:
                    if not isinstance(warmup, datetime):
                        raise DAGValidationError('Campaign warm-up timing needs review.')
                    if warmup.tzinfo is None:
                        warmup = warmup.replace(tzinfo=timezone.utc)
                    root_base = max(root_base, warmup)
                root_due = successor_fields(inspected, root_node_id, root_base)['next_action_due_at']
            except DAGValidationError:
                raise HTTPException(409, 'Review and save the campaign sequence before importing active contacts') from None



        # 1. Fetch existing leads in this campaign for deduplication (compound)
        campaign_dupes = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_leads",
            extra_filter={"campaign_id": campaign_id, **({"id": {"$nin": [row["id"] for row in _staged_rows]}} if _staged_rows else {})},
            max_matches=_match_limit,
        )

        # 2. Fetch cross-campaign contacted leads or team campaign leads if enabled (compound)
        cross_campaign_dupes = {}
        if skip_already_contacted:
            cross_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"last_action_at": {"$ne": None}},
                max_matches=_match_limit,
            )
        skip_team = bool(skip_team_campaign_leads) if skip_team_campaign_leads is not None else bool(campaign.get("skip_team_campaign_leads"))
        team_campaign_dupes = {}
        if skip_team:
            team_campaign_dupes = await check_compound_suppression(
                workspace_id=workspace_id,
                candidates=leads,
                db=db,
                collection_name="outreach_leads",
                extra_filter={"campaign_id": {"$ne": campaign_id}},
                max_matches=_match_limit,
            )

        # 3. Fetch Do-Not-Contact records (mandatory compound check)
        dnc_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_do_not_contact",
            max_matches=_match_limit,
        )
        email_matches = await check_compound_suppression(
            workspace_id=workspace_id, candidates=leads, db=db, collection_name="outreach_email_suppressions", max_matches=_match_limit)

        # 4. Fetch Withdrawn Invites within 21-day reinvite block window (mandatory compound check)
        now_dt = datetime.now(timezone.utc)
        withdrawn_matches = await check_compound_suppression(
            workspace_id=workspace_id,
            candidates=leads,
            db=db,
            collection_name="outreach_withdrawn_invites",
            extra_filter={"reinvite_blocked_until": {"$gt": now_dt}},
            max_matches=_match_limit,
        )

        to_insert: list[dict[str, Any]] = []
        seen_batch_keys: set[str] = set()
        rejections: list[dict[str, Any]] = []
        duplicates_count = 0
        skipped_count = 0

        decisions: list[dict[str, Any]] = []
        def reject(record: dict[str, Any]) -> None:
            rejections.append(record)
            if _record_decisions:
                decisions.append({"row_number": idx + 1, "status": "excluded", "rejection_code": record["rejection_code"]})

        for idx, lead in enumerate(leads):
            raw_url = lead.get("raw_url") or lead.get("linkedin_url") or ""
            url = (
                normalize_linkedin_url(lead.get("linkedin_url", "") or raw_url)
                or normalize_any_linkedin_profile_url(lead.get("linkedin_url", "") or raw_url)
            )
            raw_first, cleaned_first, first_name = intake_names(lead)
            vanity = (lead.get("vanity_name") or extract_vanity_name(url)).strip().lower()

            ident, cand_keys, current_ident = intake_identifiers(lead)

            if not url:
                skipped_count += 1
                reject({
                    "linkedin_url": raw_url,
                    "first_name": first_name,
                    "rejection_code": "invalid_url",
                    "reason": f"Invalid LinkedIn profile URL '{raw_url}'",
                })
                continue

            if require_name and not first_name:
                skipped_count += 1
                reject({
                    "linkedin_url": url,
                    "first_name": "",
                    "rejection_code": "missing_name",
                    "reason": "First name is required for outreach personalization",
                })
                continue

            # Deduplicate within batch
            if cand_keys and (cand_keys & seen_batch_keys):
                duplicates_count += 1
                reject({
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
                reject({
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
                reject({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_contacted",
                    "reason": f"Already contacted in another campaign (matched by {match_info.get('matched_by', 'identifier')})",
                })
                continue

            # Deduplicate against team members' campaigns in the workspace (Dripify Team Management)
            if skip_team and idx in team_campaign_dupes:
                duplicates_count += 1
                match_info = team_campaign_dupes[idx]
                reject({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "duplicate_team_campaign",
                    "reason": f"Already enrolled in another team member's campaign in this workspace (matched by {match_info.get('matched_by', 'identifier')})",
                })
                continue

            # Check Do-Not-Contact list (always mandatory)
            if idx in dnc_matches:
                skipped_count += 1
                match_info = dnc_matches[idx]
                reject({
                    "linkedin_url": url,
                    "first_name": first_name,
                    "rejection_code": "do_not_contact",
                    "reason": f"Found on Do-Not-Contact exclusion list ({match_info.get('reason', 'Manual exclusion')})",
                })
                continue

            # Check Withdrawn Invites cooldown (mandatory)
            if idx in email_matches:
                skipped_count += 1
                reject({"linkedin_url": url, "first_name": first_name,
                    "rejection_code": "email_suppressed", "reason": "Email is on the workspace suppression list"})
                continue

            if idx in withdrawn_matches:
                skipped_count += 1
                match_info = withdrawn_matches[idx]
                reject({
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
            initial_tags = list(lead.get("tags") or [])
            list_name_tag = str(meta.get("list_name") or "").strip()
            if list_name_tag and list_name_tag not in initial_tags:
                initial_tags.append(list_name_tag)

            lead_doc = OutreachLead(
                campaign_id=campaign_id,
                workspace_id=workspace_id,
                enrollment_id=generate_uuid(),
                assigned_account_id=assigned_account_id,
                current_node_id=root_node_id,
                next_action_due_at=root_due,
                linkedin_url=url,
                linkedin_urn=(lead.get("linkedin_urn") or current_ident.member_urn or ident.member_urn or "").strip() or None,
                identifiers=ident,
                raw_first_name=raw_first,
                cleaned_first_name=cleaned_first,
                first_name=first_name,
                last_name=lead.get("last_name", ""),
                company_name=lead.get("company_name", ""),
                job_title=lead.get("job_title", ""),
                location=lead.get("location", ""),
                email=(lead.get("email") or "").strip().lower() or None,
                phone=lead.get("phone"),
                source=source,
                source_metadata=meta,
                tags=initial_tags,
                custom_variables=lead.get("custom_variables", {}),
                execution_state=LeadExecutionState.QUEUED,
                created_at=datetime.now(timezone.utc),
            ).model_dump()
            # The existing compound lookup reads these current fields separately
            # from identifiers, which retains saved aliases after profile changes.
            lead_doc.update({"member_urn": current_ident.member_urn,
                "sales_lead_urn": current_ident.sales_lead_urn, "vanity_name": vanity or None})

            if active_senders:
                lead_doc["authorized_revision"] = revision
                lead_doc["sequence_version"] = version
            if _staged_rows is not None:
                original = _staged_rows[idx]
                lead_doc = {**original, **lead_doc, "id": original["id"],
                    "import_job_id": original["import_job_id"],
                    "created_at": original.get("created_at", lead_doc["created_at"]), "staged_at": None}
                if not active_senders:
                    lead_doc.pop("authorized_revision", None)
                    lead_doc.pop("sequence_version", None)
            to_insert.append(lead_doc)
            if _record_decisions:
                decisions.append({"row_number": idx + 1, "status": "imported", "lead_id": lead_doc["id"]})

        if to_insert:
            if _staged_rows is None:
                await db.outreach_leads.insert_many(to_insert)
            else:
                for document in to_insert:
                    saved = await db.outreach_leads.replace_one({
                        "id": document["id"], **workspace_scope(workspace_id), "campaign_id": campaign_id,
                        "import_job_id": document["import_job_id"], "execution_state": LeadExecutionState.STAGED.value}, document)
                    if getattr(saved, "matched_count", 0) != 1:
                        raise HTTPException(409, "Staged contacts changed. Reload before importing.")
            # Update campaign lead count
            await db.outreach_campaigns.update_one(
                {"id": campaign_id, **workspace_scope(workspace_id)},
                {"$inc": {"leads_count": len(to_insert)}, "$set": {"updated_at": datetime.now(timezone.utc)}}
            )
            from outreach.core.event_outbox import record_outbox_event
            from outreach.core.event_definitions import WebhookEvent
            for document in to_insert:
                await record_outbox_event(db, workspace_id, WebhookEvent.LEAD_CREATED, document["id"],
                    f"lead.created:{document['id']}", {"lead_id": document["id"], "campaign_id": campaign_id,
                    "linkedin_url": document["linkedin_url"], "channel": "linkedin", "source_status": "confirmed"})

        logger.info(
            "Campaign %s: Imported %s leads via %s (skipped: %s, duplicates: %s)",
            campaign_id, len(to_insert), source, skipped_count, duplicates_count,
        )

        res = {
            "imported_count": len(to_insert),
            "skipped_count": skipped_count,
            "duplicates_count": duplicates_count,
            "total_submitted": len(leads),
            "lead_ids": [document["id"] for document in to_insert],
        }
        if _record_decisions:
            res["row_results"] = decisions
        if include_rejections:
            res["rejections"] = rejections
        return res
