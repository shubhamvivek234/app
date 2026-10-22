"""Workspace-funded Hunter email discovery and shared email suppression.

Only Hunter's publicly found (non-inferred) endpoint is used. An address being
present is not proof of delivery; unknown/accept-all verification is not used.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from outreach.core.provider_custody import prepare_finder_key


logger = logging.getLogger(__name__)
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


async def _hunter_found_request(url: str, params: dict, *, envelope) -> dict:
    if url != HUNTER_FOUND_URL:
        raise ValueError("Unexpected email discovery endpoint")
    envelope.assert_finder(params)
    async with httpx.AsyncClient(timeout=25) as client:
        response = await envelope.call("GET", url, lambda: client.get(url, params=params), action="finder", side_effect=True)
    if response.status_code == 404:
        return {"data": {"email": None}}
    if response.status_code != 200:
        return {"errors": [{"reason": "Provider rejected lookup"}]}
    return response.json()


async def _project_discovery(db, operation: dict, result: dict, *, recovering: bool = False) -> bool:
    if result.get("status") != "found":
        return False
    ws, email = operation["workspace_id"], result["email"]
    if await db.outreach_email_suppressions.find_one({"workspace_id": ws, "email": email}, {"_id": 1}):
        return False
    snapshot = dict(operation["lead_snapshot"])
    if recovering:
        snapshot["execution_state"] = {"$in": [snapshot.get("execution_state"), "waiting_trigger"]}
    changed = await db.outreach_leads.update_one({"workspace_id": ws, "id": operation["lead_id"],
        **snapshot, "has_replied": {"$ne": True}, "do_not_contact": {"$ne": True},
        "is_suppressed": {"$ne": True}, "email_opted_out": {"$ne": True},
        "$or": [{"email": None}, {"email": ""}, {"email": {"$exists": False}}]}, {
        "$set": {"email": email, "email_source": "hunter_found", "email_verification_status": "valid",
            "email_source_urls": result.get("source_urls") or [], "email_verified_at": datetime.now(timezone.utc),
            "email_found_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}})
    return bool(changed.matched_count)


async def find_lead_email(db, *, workspace_id: str, lead_id: str,
                         sender_account_id: str | None = None, operation_id: str | None = None) -> dict:
    from outreach.core.provider_boundary import create_provider_envelope
    from outreach.core.provider_operations import ProviderOperations
    from outreach.core.request_guard import RequestDenied, current_request_parent

    lead = await db.outreach_leads.find_one({"workspace_id": workspace_id, "id": lead_id})
    if not lead:
        raise RequestDenied("lead_changed")
    if await is_lead_email_available(db, workspace_id, lead):
        return {"status": "found", "email": normalize_email(lead["email"]),
            "source": lead.get("email_source") or "provided", "verification": lead.get("email_verification_status") or "not_verified"}
    if normalize_email(lead.get("email")):
        raise RequestDenied("lead_suppressed")
    if not sender_account_id or lead.get("assigned_account_id") != sender_account_id or not operation_id or len(operation_id) > 200:
        raise RequestDenied("provider_context_missing")
    operations = ProviderOperations(db, "outreach_email_discoveries")
    key = f"finder:{workspace_id}:{operation_id}"
    prior = await operations.prior(workspace_id, key)
    if prior and prior.get("status") != "not_submitted":
        if prior.get("status") in {"dispatching", "uncertain"}:
            result = await operations.repair(prior)
            if not result:
                return {"status": "uncertain", "reason": "Previous lookup requires reconciliation"}
        else:
            result = {key: prior[key] for key in ("status", "email", "verification", "source_urls") if key in prior}
        if result.get("status") == "found":
            await _project_discovery(db, prior, result)
        return result
    handle = _linkedin_handle(lead.get("linkedin_url"))
    if not handle:
        raise RequestDenied("lookup_target_invalid")
    credential = await db.outreach_hunter_credentials.find_one({"workspace_id": workspace_id})
    if not credential or not credential.get("api_key_enc"):
        raise RequestDenied("finder_unavailable")
    envelope = await create_provider_envelope(db, workspace_id, sender_account_id, "email_find", credential, operation_id, lead_id)
    prepared = await prepare_finder_key(credential, workspace_id)
    envelope.bind_finder(prepared)
    envelope.finder_handle = handle
    snapshot = {name: lead.get(name) for name in ("campaign_id", "assigned_account_id", "enrollment_id", "current_node_id",
        "authorized_revision", "sequence_version", "execution_state", "linkedin_url")}
    op = {"_id": key, "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "lead_id": lead_id, "source": "email_find", "logical_operation_id": operation_id,
        "credential_generation": envelope.generation, "account_generation": envelope.account_generation, "lead_snapshot": snapshot}
    if not await operations.claim(op):
        return {"status": "uncertain", "reason": "Previous lookup requires reconciliation"}
    try:
        payload = await _hunter_found_request(HUNTER_FOUND_URL, {
            "linkedin_handle": handle, "api_key": prepared.value}, envelope=envelope)
        data = payload.get("data") or {}
        email = normalize_email(data.get("email")) if isinstance(data, dict) else None
        verification = data.get("verification") or {} if isinstance(data, dict) else {}
        found = bool(email and data.get("source_type") == "found" and isinstance(verification, dict) and verification.get("status") == "valid")
        sources = data.get("sources") or [] if isinstance(data, dict) else []
        urls = [item["uri"][:2048] for item in sources[:3] if isinstance(item, dict) and isinstance(item.get("uri"), str)] if isinstance(sources, list) else []
        result = {"status": "failed" if payload.get("error") or payload.get("errors") else "found" if found else "not_found",
            "email": email if found else None, "verification": "valid" if found else None, "source_urls": urls if found else []}
        if not await operations.finish(workspace_id, key, result):
            return {"status": "uncertain", "reason": "Lookup confirmation needs reconciliation"}
        if found:
            await _project_discovery(db, op, result)
        return result
    except RequestDenied as exc:
        parent = current_request_parent()
        if parent and not parent.mutation_attempted:
            await operations.finish(workspace_id, key, {"status": "not_submitted", "reason": exc.reason})
            raise
        await operations.finish(workspace_id, key, {"status": "uncertain"})
        return {"status": "uncertain"}
    except Exception as exc:
        parent = current_request_parent()
        possible = bool(parent and parent.mutation_attempted)
        logger.warning("Email finder lookup failed for workspace=%s possible=%s (%s)", workspace_id, possible, type(exc).__name__)
        try:
            await operations.finish(workspace_id, key, {"status": "uncertain" if possible else "not_submitted"})
        except Exception as fin_exc:
            logger.debug("Email finder operation finish skipped (%s)", type(fin_exc).__name__)
        if not possible:
            raise RequestDenied("finder_unavailable") from None
        return {"status": "uncertain", "reason": "Provider lookup outcome is unknown"}


async def suppress_email(db, *, workspace_id: str, email: str, reason: str, lead_id: str | None = None) -> bool:
    from outreach.core.suppression import mutate_suppression
    normalized = normalize_email(email)
    if not normalized:
        return False
    now = datetime.now(timezone.utc)
    async def save(current):
        await current.outreach_email_suppressions.update_one(
            {"workspace_id": workspace_id, "email": normalized},
            {"$set": {"reason": reason, "updated_at": now},
             "$setOnInsert": {"lead_id": lead_id, "created_at": now}}, upsert=True)
    await mutate_suppression(db, workspace_id, save)
    return True
