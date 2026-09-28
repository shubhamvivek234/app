"""Workspace-funded Hunter email discovery and shared email suppression.

Only Hunter's publicly found (non-inferred) endpoint is used. An address being
present is not proof of delivery; unknown/accept-all verification is not used.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from utils.encryption import decrypt_strict


HUNTER_FOUND_URL = "https://api.hunter.io/v2/email-finder/found"
_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$")
_VANITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,99}$")


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL_RE.fullmatch(value) or ".." in value:
        return None
    return value


async def is_lead_email_available(db, workspace_id: str, lead: dict) -> bool:
    """Available means usable by policy, never a delivery guarantee."""
    email = normalize_email(lead.get("email"))
    if not email or lead.get("email_verification_status") in {"invalid", "unknown", "accept_all", "disposable"}:
        return False
    if lead.get("email_opted_out") or lead.get("has_replied"):
        return False
    suppressed = await db.outreach_email_suppressions.find_one({
        "workspace_id": workspace_id, "email": email,
    }, {"_id": 1})
    return not bool(suppressed)


def _linkedin_handle(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}:
        return None
    pieces = parsed.path.strip("/").split("/")
    if len(pieces) != 2 or pieces[0] != "in" or not _VANITY_RE.fullmatch(pieces[1]):
        return None
    return pieces[1]


async def _hunter_found_request(url: str, params: dict) -> dict:
    # Fixed provider host; never fetch a user-controlled URL.
    if url != HUNTER_FOUND_URL:
        raise ValueError("Unexpected email discovery endpoint")
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(url, params=params)
    if response.status_code == 404:
        return {"data": {"email": None}}
    if response.status_code != 200:
        raise RuntimeError("Email discovery provider is unavailable")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("errors") or payload.get("error"):
        raise RuntimeError("Email discovery provider returned an error")
    return payload


async def find_lead_email(db, *, workspace_id: str, lead_id: str) -> dict:
    """Run from a worker; never interpret provider failures as no address."""
    if os.getenv("OUTREACH_HUNTER_ENABLED", "false").strip().lower() not in {"true", "1"}:
        return {"status": "unavailable", "reason": "Email discovery is not enabled"}
    lead = await db.outreach_leads.find_one({"workspace_id": workspace_id, "id": lead_id})
    if not lead:
        return {"status": "unavailable", "reason": "Lead was not found"}
    if await is_lead_email_available(db, workspace_id, lead):
        return {"status": "found", "email": normalize_email(lead["email"]),
                "source": lead.get("email_source") or "provided", "verification": lead.get("email_verification_status") or "not_verified"}
    if normalize_email(lead.get("email")):
        return {"status": "unavailable", "reason": "Lead email is suppressed or unverified"}
    handle = _linkedin_handle(lead.get("linkedin_url"))
    if not handle:
        return {"status": "unavailable", "reason": "Lead has no usable LinkedIn profile handle"}
    credential = await db.outreach_hunter_credentials.find_one({"workspace_id": workspace_id})
    if not credential or not credential.get("api_key_enc"):
        return {"status": "unavailable", "reason": "Connect a Hunter API key first"}
    try:
        payload = await _hunter_found_request(HUNTER_FOUND_URL, {
            "linkedin_handle": handle, "api_key": decrypt_strict(credential["api_key_enc"]),
        })
    except Exception:
        return {"status": "unavailable", "reason": "Email discovery could not be completed"}
    data = payload.get("data") or {}
    if not isinstance(data, dict) or data.get("error"):
        return {"status": "unavailable", "reason": "Email discovery returned invalid data"}
    email = normalize_email(data.get("email"))
    if not email:
        return {"status": "not_found"}
    verification = data.get("verification") or {}
    verification_status = verification.get("status") if isinstance(verification, dict) else None
    if data.get("source_type") != "found" or verification_status != "valid":
        return {"status": "not_found", "reason": "No verified public-source address"}
    if await db.outreach_email_suppressions.find_one({"workspace_id": workspace_id, "email": email}, {"_id": 1}):
        return {"status": "unavailable", "reason": "Email is on the workspace suppression list"}
    sources = data.get("sources") or []
    source_urls = [source.get("uri") for source in sources[:3]
                   if isinstance(source, dict) and isinstance(source.get("uri"), str)]
    now = datetime.now(timezone.utc)
    changed = await db.outreach_leads.update_one(
        {"workspace_id": workspace_id, "id": lead_id, "$or": [{"email": None}, {"email": ""}, {"email": {"$exists": False}}]},
        {"$set": {"email": email, "email_source": "hunter_found", "email_verification_status": "valid",
                  "email_source_urls": source_urls, "email_verified_at": now,
                  "email_found_at": now, "updated_at": now}},
    )
    if not getattr(changed, "modified_count", 0):
        return {"status": "unavailable", "reason": "Lead email changed during discovery"}
    return {"status": "found", "email": email, "source": "hunter_found", "verification": "valid"}


async def suppress_email(db, *, workspace_id: str, email: str, reason: str, lead_id: str | None = None) -> bool:
    normalized = normalize_email(email)
    if not normalized:
        return False
    now = datetime.now(timezone.utc)
    await db.outreach_email_suppressions.update_one(
        {"workspace_id": workspace_id, "email": normalized},
        {"$set": {"reason": reason, "updated_at": now},
         "$setOnInsert": {"lead_id": lead_id, "created_at": now}}, upsert=True,
    )
    return True
