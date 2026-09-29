"""
CRM and Spreadsheet Integration Module.
Provides one-way HubSpot contact synchronization, external object mapping,
and Google Sheets/CSV preview with formula injection defense.
"""
from datetime import datetime, timezone
import logging
import re
from typing import Any
import uuid

import httpx
from pymongo.errors import DuplicateKeyError

from outreach.core.safe_transport import create_safe_client

logger = logging.getLogger(__name__)

# Dangerous leading characters in spreadsheets (CSV / Sheets formula injection)
FORMULA_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_spreadsheet_value(value: Any) -> Any:
    """
    Sanitize spreadsheet string values against CSV/Formula Injection (CWE-1236).
    If a string begins with =, +, -, @, or tab/return, prepend a single quote
    so spreadsheet engines treat it strictly as text literal.
    """
    if not isinstance(value, str):
        return value

    # Check raw string for tab/return escape characters before strip
    if value.startswith(("\t", "\r")):
        return "'" + value.lstrip("\t\r ")

    stripped = value.strip()
    if not stripped:
        return ""

    if stripped.startswith(("=", "+", "-", "@")):
        # Prepend single quote to neutralize formula evaluation
        return "'" + stripped

    return stripped


def sanitize_row_data(row: dict[str, Any]) -> dict[str, Any]:
    """Sanitize all string values within a row dict."""
    return {k: sanitize_spreadsheet_value(v) for k, v in row.items()}


async def sync_lead_to_hubspot(
    db: Any,
    *,
    workspace_id: str,
    lead_id: str,
    access_token: str,
    portal_id: str,
    safe_client: httpx.AsyncClient | None = None,
    allow_private_for_tests: bool = False,
) -> dict[str, Any]:
    """
    Idempotently synchronize an Unravler outreach lead to HubSpot as a CRM Contact.
    Stores external mapping in outreach_external_mappings to prevent duplicate creation.
    Never overwrites CRM fields with empty values.
    """
    lead = await db.outreach_leads.find_one({"id": lead_id, "workspace_id": workspace_id})
    if not lead:
        raise ValueError(f"Lead {lead_id} not found in workspace {workspace_id}")

    # Check existing external mapping
    mapping = await db.outreach_external_mappings.find_one({
        "workspace_id": workspace_id,
        "provider": "hubspot",
        "external_account_id": portal_id,
        "object_type": "contact",
        "internal_id": lead_id,
    })

    client = safe_client or create_safe_client(allow_private_for_tests=allow_private_for_tests)
    should_close = safe_client is None

    # Construct HubSpot properties
    properties: dict[str, str] = {}
    if lead.get("email"):
        properties["email"] = lead["email"].strip()
    if lead.get("first_name"):
        properties["firstname"] = lead["first_name"].strip()
    if lead.get("last_name"):
        properties["lastname"] = lead["last_name"].strip()
    if lead.get("company_name"):
        properties["company"] = lead["company_name"].strip()
    if lead.get("job_title"):
        properties["jobtitle"] = lead["job_title"].strip()
    if lead.get("linkedin_url"):
        properties["website"] = lead["linkedin_url"].strip()

    # Map Unravler status to HubSpot lead status
    stage = lead.get("pipeline_stage", "new")
    status_map = {
        "new": "NEW",
        "contacted": "IN_PROGRESS",
        "replied": "OPEN",
        "interested": "QUALIFIED",
        "not_interested": "UNQUALIFIED",
    }
    properties["hs_lead_status"] = status_map.get(stage, "OPEN")

    now = datetime.now(timezone.utc)
    hubspot_contact_id = None

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        if mapping and mapping.get("external_id"):
            # Update existing contact
            hubspot_contact_id = mapping["external_id"]
            url = f"https://api.hubapi.com/crm/v3/objects/contacts/{hubspot_contact_id}"
            resp = await client.patch(url, json={"properties": properties}, headers=headers)
            if not (200 <= resp.status_code < 300):
                raise RuntimeError(f"HubSpot PATCH failed ({resp.status_code}): {resp.text[:120]}")
        else:
            # Create new contact
            url = "https://api.hubapi.com/crm/v3/objects/contacts"
            resp = await client.post(url, json={"properties": properties}, headers=headers)
            if resp.status_code == 409:
                # Contact already exists in HubSpot by email; extract existing ID
                err_json = resp.json()
                # Typical HubSpot 409 message: "Contact already exists. Existing ID: 12345"
                match = re.search(r"Existing ID:\s*(\d+)", err_json.get("message", ""))
                if match:
                    hubspot_contact_id = match.group(1)
                    # Update existing contact with new properties
                    patch_url = f"https://api.hubapi.com/crm/v3/objects/contacts/{hubspot_contact_id}"
                    await client.patch(patch_url, json={"properties": properties}, headers=headers)
                else:
                    raise RuntimeError(f"HubSpot 409 Conflict: {err_json.get('message', '')}")
            elif not (200 <= resp.status_code < 300):
                raise RuntimeError(f"HubSpot POST failed ({resp.status_code}): {resp.text[:120]}")
            else:
                contact_data = resp.json()
                hubspot_contact_id = str(contact_data.get("id"))

        # Save/update external mapping
        mapping_doc = {
            "id": f"map_{uuid.uuid4().hex[:12]}",
            "workspace_id": workspace_id,
            "provider": "hubspot",
            "external_account_id": portal_id,
            "object_type": "contact",
            "internal_id": lead_id,
            "external_id": hubspot_contact_id,
            "synced_at": now,
            "status": "synced",
        }
        await db.outreach_external_mappings.update_one(
            {
                "workspace_id": workspace_id,
                "provider": "hubspot",
                "external_account_id": portal_id,
                "object_type": "contact",
                "internal_id": lead_id,
            },
            {"$set": mapping_doc},
            upsert=True,
        )

        return {
            "status": "synced",
            "hubspot_contact_id": hubspot_contact_id,
            "lead_id": lead_id,
            "synced_at": now.isoformat(),
        }

    finally:
        if should_close:
            await client.aclose()
