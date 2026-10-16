"""Fail-closed search contracts; parser support never grants collection authority."""
from __future__ import annotations

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
