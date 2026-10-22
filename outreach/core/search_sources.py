"""Fail-closed search contracts; parser support never grants collection authority."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import HTTPException

from outreach.core.workspace_scope import workspace_scope

COLLECTION_UNAVAILABLE = (
    "LinkedIn search imports are unavailable while audience filters and result schemas are verified. "
    "Use CSV or public LinkedIn profile URLs. Existing search records are retained for review."
)
UNVERIFIED_LEAD = "This contact's search source has not been verified. Review its source before enrolling or restarting outreach."
SOURCE_TYPES = ("basic", "sales_nav", "recruiter", "connections", "events")
RECRUITER_GRADUATION_BATCHES = (
    "1990-2000",
    "2001-2005",
    "2006-2010",
    "2011-2015",
    "2016-2020",
    "2021-Present",
)
SOURCE_LIMITS_METADATA: dict[str, dict[str, Any]] = {
    "basic": {
        "type": "basic",
        "label": "Basic LinkedIn Search",
        "direct_url": "https://www.linkedin.com/search/results/people/",
        "max_profiles": 1000,
        "max_pages": 100,
        "page_size": 10,
        "limit_explanation": (
            "LinkedIn displays up to 100 pages of 10 profiles (1,000 profiles max per search). "
            "Narrow your filters if total results exceed 1,000."
        ),
    },
    "sales_nav": {
        "type": "sales_nav",
        "label": "LinkedIn Sales Navigator",
        "direct_url": "https://www.linkedin.com/sales/search/people",
        "max_profiles": 2500,
        "max_pages": 99,
        "page_size": 25,
        "limit_explanation": (
            "Sales Navigator displays up to 99 pages of 25 profiles (2,500 profiles max per search). "
            "Use filters like 'Changed jobs in last 90 days' or Geography to narrow below 2,500."
        ),
    },
    "recruiter": {
        "type": "recruiter",
        "label": "LinkedIn Recruiter / Recruiter Lite",
        "direct_url": "https://www.linkedin.com/talent/",
        "max_profiles": 1000,
        "max_pages": 40,
        "page_size": 25,
        "supports_pipeline_tab": True,
        "graduation_year_batches": list(RECRUITER_GRADUATION_BATCHES),
        "limit_explanation": (
            "LinkedIn Recruiter displays up to 40 pages of 25 profiles (1,000 profiles max). "
            "Supports both Talent Pool Search and Project Pipeline tabs. Use Graduation Year batches to split pools >1,000."
        ),
    },
    "connections": {
        "type": "connections",
        "label": "My Network · Recent 1st-Degree Connections",
        "direct_url": "https://www.linkedin.com/mynetwork/invite-connect/connections/",
        "batching_search_url": "https://www.linkedin.com/search/results/people/?network=%5B%22F%22%5D",
        "max_profiles": 1000,
        "max_pages": 100,
        "page_size": 10,
        "sort_order": "most_recent_first",
        "limit_explanation": (
            "Imports up to 1,000 1st-degree connections starting from your most recently added connections at the top. "
            "For >1,000 connections, use 1st-Degree Search Batching by location."
        ),
    },
    "events": {
        "type": "events",
        "label": "LinkedIn Event Attendees",
        "direct_url": "https://www.linkedin.com/mynetwork/network-manager/events/",
        "events_search_url": "https://www.linkedin.com/search/results/events/",
        "max_profiles": 1000,
        "max_pages": 100,
        "page_size": 10,
        "requires_event_attendance": True,
        "event_batches": ["United States", "United Kingdom & Europe", "Founders & C-Suite", "VP & Directors"],
        "limit_explanation": (
            "LinkedIn displays up to 100 pages of 10 event attendees (1,000 profiles max). "
            "You must click 'Attend' on the LinkedIn event first to unlock its attendee list. "
            "For events with >1,000 attendees, filter by Location or Title."
        ),
    },
}


def classify_linkedin_source_url(value: str) -> dict[str, Any]:
    """
    Classifies a LinkedIn lead-sourcing URL across the 5 Dripify LinkedIn channels
    (Basic Search, Sales Navigator, Recruiter/Pipeline, My Network 1st-Degree Connections, LinkedIn Event Attendees)
    and returns exact pagination/profile caps and batching guidance.
    """
    if not isinstance(value, str) or not value.strip():
        return {
            "is_valid": False,
            "error_code": "empty_url",
            "message": "Enter an HTTPS LinkedIn Search, Sales Navigator, Recruiter, My Network Connections, or Event Attendees URL.",
            "sources_metadata": SOURCE_LIMITS_METADATA,
        }
    raw = value.strip()
    if len(raw) > 4096 or any(ord(ch) <= 32 or ord(ch) == 127 for ch in raw):
        return {
            "is_valid": False,
            "error_code": "invalid_url",
            "message": "URL contains invalid control characters or exceeds maximum length.",
            "sources_metadata": SOURCE_LIMITS_METADATA,
        }
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return {
            "is_valid": False,
            "error_code": "invalid_url",
            "message": "Malformed URL.",
            "sources_metadata": SOURCE_LIMITS_METADATA,
        }
    host = (parsed.netloc or "").lower()
    if parsed.scheme != "https" or host not in {"linkedin.com", "www.linkedin.com"}:
        return {
            "is_valid": False,
            "error_code": "unsupported_host",
            "message": "URL must be an HTTPS link on linkedin.com or www.linkedin.com.",
            "sources_metadata": SOURCE_LIMITS_METADATA,
        }
    path = (parsed.path or "").rstrip("/")
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_dict = dict(query_pairs)

    # 1. Basic LinkedIn People Search (including Event Attendees `eventAttending` and 1st-degree `network=["F"]` batching)
    if path == "/search/results/people":
        if "eventAttending" in query_dict or "eventattending" in raw.lower():
            meta = SOURCE_LIMITS_METADATA["events"]
            keywords = query_dict.get("keywords", "").strip()
            return {
                "is_valid": True,
                "source_type": "events",
                "sub_source": "event_attendees_search",
                "label": meta["label"],
                "direct_url": meta["direct_url"],
                "events_search_url": meta["events_search_url"],
                "max_profiles": meta["max_profiles"],
                "max_pages": meta["max_pages"],
                "page_size": meta["page_size"],
                "requires_event_attendance": True,
                "is_event_attendees_search": True,
                "is_first_degree_batch": False,
                "event_batches": meta["event_batches"],
                "keywords": keywords,
                "limit_explanation": meta["limit_explanation"],
                "clean_url": raw,
            }
        meta = SOURCE_LIMITS_METADATA["basic"]
        net_val = query_dict.get("network", "")
        is_first_degree = '"F"' in net_val or "%22F%22" in raw or net_val == "F"
        keywords = query_dict.get("keywords", "").strip()
        return {
            "is_valid": True,
            "source_type": "basic",
            "sub_source": "first_degree_search_batch" if is_first_degree else "people_search",
            "label": "1st-Degree Connections Batch Search" if is_first_degree else meta["label"],
            "direct_url": meta["direct_url"],
            "max_profiles": meta["max_profiles"],
            "max_pages": meta["max_pages"],
            "page_size": meta["page_size"],
            "is_first_degree_batch": is_first_degree,
            "keywords": keywords,
            "limit_explanation": meta["limit_explanation"],
            "clean_url": raw,
        }

    # 2. LinkedIn Sales Navigator (People Search or Saved Lead List)
    if path.startswith("/sales/search/people") or path.startswith("/sales/lists/people"):
        meta = SOURCE_LIMITS_METADATA["sales_nav"]
        sub_source = "saved_list" if path.startswith("/sales/lists/people") else "lead_search"
        return {
            "is_valid": True,
            "source_type": "sales_nav",
            "sub_source": sub_source,
            "label": "Sales Navigator Saved Lead List" if sub_source == "saved_list" else meta["label"],
            "direct_url": meta["direct_url"],
            "max_profiles": meta["max_profiles"],
            "max_pages": meta["max_pages"],
            "page_size": meta["page_size"],
            "is_first_degree_batch": False,
            "limit_explanation": meta["limit_explanation"],
            "clean_url": raw,
        }

    # 3. LinkedIn Recruiter / Recruiter Lite (Talent Search or Project Pipeline Tab)
    if path.startswith("/talent/search") or path.startswith("/talent/hire/"):
        meta = SOURCE_LIMITS_METADATA["recruiter"]
        is_pipeline = "/pipeline" in path
        sub_source = "pipeline" if is_pipeline else "talent_search"
        return {
            "is_valid": True,
            "source_type": "recruiter",
            "sub_source": sub_source,
            "label": "LinkedIn Recruiter · Project Pipeline" if is_pipeline else meta["label"],
            "direct_url": meta["direct_url"],
            "max_profiles": meta["max_profiles"],
            "max_pages": meta["max_pages"],
            "page_size": meta["page_size"],
            "is_first_degree_batch": False,
            "graduation_year_batches": meta["graduation_year_batches"],
            "limit_explanation": meta["limit_explanation"],
            "clean_url": raw,
        }

    # 4. My Network · Recent 1st-Degree Connections
    if path == "/mynetwork/invite-connect/connections":
        meta = SOURCE_LIMITS_METADATA["connections"]
        return {
            "is_valid": True,
            "source_type": "connections",
            "sub_source": "recent_connections",
            "label": meta["label"],
            "direct_url": meta["direct_url"],
            "batching_search_url": meta["batching_search_url"],
            "max_profiles": meta["max_profiles"],
            "max_pages": meta["max_pages"],
            "page_size": meta["page_size"],
            "sort_order": meta["sort_order"],
            "is_first_degree_batch": True,
            "limit_explanation": meta["limit_explanation"],
            "clean_url": raw,
        }

    # 5. LinkedIn Event Page or My Network Events Manager
    if path.startswith("/events/") or path == "/mynetwork/network-manager/events":
        meta = SOURCE_LIMITS_METADATA["events"]
        return {
            "is_valid": True,
            "source_type": "events",
            "sub_source": "event_page",
            "label": meta["label"],
            "direct_url": meta["direct_url"],
            "events_search_url": meta["events_search_url"],
            "max_profiles": meta["max_profiles"],
            "max_pages": meta["max_pages"],
            "page_size": meta["page_size"],
            "requires_event_attendance": True,
            "is_event_attendees_search": True,
            "is_first_degree_batch": False,
            "event_batches": meta["event_batches"],
            "limit_explanation": meta["limit_explanation"],
            "clean_url": raw,
        }

    return {
        "is_valid": False,
        "error_code": "unsupported_path",
        "message": (
            "Unsupported LinkedIn URL path. Use Basic People Search (/search/results/people/), "
            "Sales Navigator (/sales/search/people), LinkedIn Recruiter (/talent/search or /talent/hire/.../pipeline), "
            "My Network Connections (/mynetwork/invite-connect/connections/), or LinkedIn Event Attendees (/events/... or /search/results/people/?eventAttending=...)."
        ),
        "sources_metadata": SOURCE_LIMITS_METADATA,
    }
SEARCH_PROVENANCE_QUERY = {"$or": [
    {"import_job_id": {"$ne": None}}, {"staged_at": {"$ne": None}}, {"execution_state": "staged"},
    {"source": "linkedin_search"}, {"source_metadata.source_type": "linkedin_search"},
    {"source.0": {"$exists": True}}, {"source": {"$not": {"$type": "string"}, "$ne": None}},
    {"source_metadata.0": {"$exists": True}}, {"source_metadata": {"$not": {"$type": "object"}, "$ne": None}},
    {"source_metadata.source_type.0": {"$exists": True}},
    {"source_metadata.source_type": {"$not": {"$type": "string"}, "$ne": None}},
    {"execution_state.0": {"$exists": True}}, {"execution_state": {"$not": {"$type": "string"}, "$ne": None}},
    {"search_source_review_required": {"$exists": True}},
]}


class SearchSourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def parse_search_source(value: str) -> dict[str, Any]:
    """Recognize only the bounded keyword-only contract; reject filter loss."""
    message = "Use an HTTPS LinkedIn People search URL with only a keywords parameter. Filtered and premium searches are not supported yet."
    if not isinstance(value, str):
        raise SearchSourceError("invalid_search_url", message)
    value = value.strip()
    if (not value or len(value) > 4096 or any(ord(ch) <= 32 or ord(ch) == 127 for ch in value)
            or "#" in value or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise SearchSourceError("invalid_search_url", message)
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or url.netloc.lower() not in {"linkedin.com", "www.linkedin.com"}
                or url.path not in {"/search/results/people", "/search/results/people/"}):
            raise ValueError("Unsupported source")
        pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True, errors="strict", max_num_fields=16)
    except (ValueError, UnicodeError):
        raise SearchSourceError("invalid_search_url", message) from None
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)) or set(keys) - {"keywords", "origin"}:
        raise SearchSourceError("unsupported_search_filters", message)
    params = dict(pairs)
    if "origin" in params and params["origin"] not in {"FACETED_SEARCH", "GLOBAL_SEARCH_HEADER", "SWITCH_SEARCH_VERTICAL"}:
        raise SearchSourceError("unsupported_search_filters", message)
    keywords = params.get("keywords", "")
    if (not 1 <= len(keywords) <= 200 or not keywords.strip() or keywords != keywords.strip()
            or any(not (ch.isalnum() or ch in " -'._") for ch in keywords)):
        raise SearchSourceError("unsupported_search_keywords", "Search keywords contain unsupported syntax or exceed 200 characters.")
    return {"is_valid": True, "is_sales_nav": False, "search_type": "basic", "keywords": keywords,
            "raw_query_params": {"keywords": keywords},
            "clean_url": "https://www.linkedin.com/search/results/people/?" + urlencode({"keywords": keywords}, quote_via=quote)}


def search_source_capabilities() -> dict:
    return {"contract_version": 1, "sources": [{"type": kind,
        "parser_supported": kind == "basic", "collection_available": False,
        "reason": COLLECTION_UNAVAILABLE} for kind in SOURCE_TYPES]}


def require_search_collection(value: str) -> dict:
    parsed = parse_search_source(value)
    capability = next(row for row in search_source_capabilities()["sources"] if row["type"] == parsed["search_type"])
    if not capability["collection_available"]:
        raise SearchSourceError("search_source_review_required", capability["reason"])
    return parsed


def unverified_search_lead(lead: dict) -> bool:
    metadata = lead.get("source_metadata")
    source = lead.get("source")
    state = lead.get("execution_state")
    if (source is not None and not isinstance(source, str)
            or state is not None and not isinstance(state, str)
            or metadata is not None and not isinstance(metadata, dict)
            or isinstance(metadata, dict) and metadata.get("source_type") is not None and not isinstance(metadata["source_type"], str)):
        return True
    return (any(lead.get(key) is not None for key in ("import_job_id", "staged_at")) or "search_source_review_required" in lead
            or lead.get("execution_state") == "staged" or lead.get("source") == "linkedin_search"
            or isinstance(metadata, dict) and metadata.get("source_type") == "linkedin_search")


async def ensure_intake_provenance(db: Any, workspace: str, rows: list[dict], source: str) -> None:
    """Do not launder server-known search records through generic intake."""
    if source == "linkedin_search" or any(unverified_search_lead(row) for row in rows):
        raise HTTPException(409, UNVERIFIED_LEAD)
    identifiers = list({row["id"] for row in rows if isinstance(row.get("id"), str)})
    if identifiers:
        stored = await db.outreach_leads.find_one({**workspace_scope(workspace),
            "id": {"$in": identifiers}, "id.0": {"$exists": False}, **SEARCH_PROVENANCE_QUERY})
        if stored:
            raise HTTPException(409, UNVERIFIED_LEAD)


async def retain_search_source_hold(db: Any, workspace: str, target: dict) -> None:
    """Inside a stop/evidence transaction, preserve markers before state projection."""
    await db.outreach_leads.update_many({**workspace_scope(workspace),
        "$and": [target, SEARCH_PROVENANCE_QUERY]},
        {"$set": {"search_source_review_required": True}})


def validate_search_page(data: Any, *, start: int = 0) -> int | None:
    """Unknown/malformed evidence cannot become a zero or fabricated total."""
    def invalid() -> None:
        raise SearchSourceError("search_response_unverified", "Search response could not be verified; saved contacts are retained for review.")
    if (not isinstance(data, dict) or data.get("errors") or data.get("error")
            or not isinstance(data.get("elements"), list)):
        invalid()
    for key in ("status", "statusCode"):
        if key in data and (type(data[key]) is not int or not 200 <= data[key] < 300):
            invalid()
    totals = []
    for container, key in (("metadata", "totalResultCount"), ("paging", "total")):
        if container in data:
            if not isinstance(data[container], dict):
                invalid()
            if key in data[container]:
                total = data[container][key]
                if type(total) is not int or total < 0:
                    invalid()
                totals.append(total)
    if len(set(totals)) > 1:
        invalid()
    total = totals[0] if totals else None
    if total is not None and total < start + len(data["elements"]):
        invalid()
    if (not data["elements"] and total != 0) or (data["elements"] and total == 0):
        invalid()
    for row in data["elements"]:
        if not isinstance(row, dict):
            invalid()
        target = row.get("searchHorizontalResult", row)
        if not isinstance(target, dict):
            invalid()
        title = target.get("title", {})
        if (not isinstance(title, dict) or not isinstance(title.get("text", ""), str)
                or not isinstance(target.get("name", ""), str)):
            invalid()
        if not (title.get("text") or target.get("name", "")).strip():
            invalid()
        for field in ("navigationUrl", "url", "targetUrn", "entityUrn"):
            if field in target and not isinstance(target[field], str):
                invalid()
        for field in ("primarySubtitle", "secondarySubtitle"):
            if field in target and (not isinstance(target[field], (str, dict))
                    or isinstance(target[field], dict) and not isinstance(target[field].get("text", ""), str)):
                invalid()
    return total
