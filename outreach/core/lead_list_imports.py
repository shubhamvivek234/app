"""Reference-only, cancellable CSV/profile admission into a reviewed audience list."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import csv
from datetime import datetime, timezone
import io
import re
from itertools import islice
from typing import Any
import uuid

from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.lead_importer import LeadImporter, detect_csv_headers
from outreach.core import lead_lists as lists
from outreach.core.lead_tags import captured_scope
from outreach.core.workspace_scope import workspace_scope

CONTRACT_VERSION = 1
MAX_IMPORT_ROWS = 100
MAX_CSV_COLUMNS = 100


def request_scope(workspace: str, actor: str) -> str:
    return canonical_hash(["audience-import-v1", workspace, actor])


def control_scope(workspace: str, actor: str, request_id: str) -> dict:
    if not isinstance(workspace, str) or not workspace or not isinstance(actor, str) or not actor:
        raise HTTPException(403, "Workspace and account identity are required")
    if not isinstance(request_id, str) or len(request_id) != 36:
        raise HTTPException(422, "An import request UUID is required")
    try:
        request_id = str(uuid.UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "An import request UUID is required") from None
    return {**workspace_scope(workspace), "actor_id": actor, "actor_id.0": {"$exists": False},
        "_id": canonical_hash([request_scope(workspace, actor), request_id]), "request_id": request_id,
        "request_id.0": {"$exists": False}}


def verify_scope(workspace: str, actor: str, expected: str) -> None:
    if expected != request_scope(workspace, actor):
        raise HTTPException(403, "Workspace or account changed. Return to the original workspace to check this request.")


CONTEXT_FIELDS = ("workspace_id", "actor_id", "request_id", "request_scope", "list_id", "campaign_id", "list_name",
    "list_native_digest", "campaign_native_digest", "campaign_status", "campaign_authorization_revision",
    "review_digest", "original_revision", "contract_version", "parsed_digest", "input_digest", "requested_rows")


def context_digest(row: dict) -> str:
    return canonical_hash(["audience-import-context-v1", [row.get(key) for key in CONTEXT_FIELDS]])


def public_receipt(row: dict) -> dict:
    """Only bounded, internally consistent database evidence is reportable."""
    def needs_review():
        raise HTTPException(503, "Import request needs review")
    if not isinstance(row, dict):
        needs_review()
    for key in ("workspace_id", "actor_id", "request_id", "request_scope", "status"):
        if not isinstance(row.get(key), str) or not row[key]:
            needs_review()
    try:
        scope = control_scope(row["workspace_id"], row["actor_id"], row["request_id"])
    except HTTPException:
        needs_review()
    if (row.get("_id") != scope["_id"] or row["request_id"] != scope["request_id"] or row["request_scope"] != request_scope(row["workspace_id"], row["actor_id"])
            or row["status"] not in {"pending", "completed", "cancelled"}
            or type(row.get("contract_version")) is not int or row["contract_version"] < 1):
        needs_review()
    def timestamp(key):
        value = row.get(key)
        # Mongo's default codec returns naive UTC; aware non-UTC data is denied.
        return isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset().total_seconds() == 0)
    if not timestamp("created_at"):
        needs_review()
    if row["status"] == "cancelled" and not timestamp("cancelled_at"):
        needs_review()
    if row["status"] != "completed" and row.get("result") is not None:
        needs_review()
    if row["status"] == "pending" or "input_digest" in row:
        for key in ("input_digest", "parsed_digest", "list_native_digest", "campaign_native_digest", "review_digest"):
            if not isinstance(row.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                needs_review()
        if (type(row.get("original_revision")) is not int or row["original_revision"] < 1
                or type(row.get("requested_rows")) is not int or not 1 <= row["requested_rows"] <= MAX_IMPORT_ROWS
                or not isinstance(row.get("list_id"), str) or not lists.LIST_ID.fullmatch(row["list_id"])
                or not isinstance(row.get("campaign_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", row["campaign_id"])
                or not isinstance(row.get("list_name"), str) or not 1 <= len(row["list_name"]) <= 60):
            needs_review()
        expected_review = canonical_hash(["audience-review-v1", row["workspace_id"], row["list_id"],
            row["list_native_digest"], row["campaign_native_digest"], row["original_revision"]])
        if (row["review_digest"] != expected_review or row.get("context_digest") != context_digest(row)
                or not isinstance(row.get("campaign_status"), str) or row["campaign_status"] not in {"draft", "paused"}
                or row.get("campaign_authorization_revision") is not None and
                (type(row["campaign_authorization_revision"]) is not int or row["campaign_authorization_revision"] < 0)):
            needs_review()
    elif any(row.get(key) is not None for key in ("list_id", "campaign_id", "list_name", "requested_rows", "context_digest")):
        needs_review()
    if row["status"] == "completed":
        result = row.get("result")
        if not timestamp("completed_at") or "input_digest" not in row or not isinstance(result, dict):
            needs_review()
        counts = ("imported_count", "skipped_count", "duplicates_count", "membership_added_count", "requested_rows", "considered_rows", "list_revision")
        if set(result) != set(counts) | {"lead_ids", "row_results", "more_rows_in_source", "collection_verified"} or any(type(result.get(key)) is not int or result[key] < 0 for key in counts):
            needs_review()
        ids, decisions = result.get("lead_ids"), result.get("row_results")
        if (not isinstance(ids, list) or len(ids) > MAX_IMPORT_ROWS or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", v) for v in ids)
                or len(set(ids)) != len(ids) or not isinstance(decisions, list) or len(decisions) > MAX_IMPORT_ROWS
                or not 1 <= result["considered_rows"] <= result["requested_rows"] == row["requested_rows"]
                or len(decisions) != result["considered_rows"] or len(ids) != result["imported_count"]
                or result["membership_added_count"] != len(ids) or result["list_revision"] != row["original_revision"] + 1
                or result["imported_count"] + result["skipped_count"] + result["duplicates_count"] != len(decisions)
                or type(result.get("more_rows_in_source")) is not bool or result.get("collection_verified") is not False):
            needs_review()
        imported, skipped, duplicates = [], 0, 0
        codes = {"invalid_url", "missing_name", "duplicate_batch", "duplicate_campaign", "duplicate_contacted", "do_not_contact", "email_suppressed", "withdrawn_cooldown"}
        for index, item in enumerate(decisions, 1):
            if not isinstance(item, dict) or type(item.get("row_number")) is not int or item["row_number"] != index:
                needs_review()
            if item.get("status") == "imported" and set(item) == {"row_number", "status", "lead_id"}:
                imported.append(item["lead_id"])
            elif item.get("status") == "excluded" and set(item) == {"row_number", "status", "rejection_code"} and isinstance(item["rejection_code"], str) and item["rejection_code"] in codes:
                if item["rejection_code"] in {"duplicate_batch", "duplicate_campaign"}:
                    duplicates += 1
                else:
                    skipped += 1
            else:
                needs_review()
        if imported != ids or skipped != result["skipped_count"] or duplicates != result["duplicates_count"]:
            needs_review()
    return {key: row.get(key) for key in ("request_id", "request_scope", "status", "list_id", "campaign_id",
        "list_name", "requested_rows", "created_at", "completed_at", "cancelled_at", "result")}


def pending_scope(scope: dict, row: dict) -> dict:
    return {**scope, "status": "pending", **{key: row[key] for key in (
        "input_digest", "parsed_digest", "contract_version", "original_revision", "review_digest", "created_at", "context_digest")}}


def validate_input_bounds(payload: dict) -> None:
    """Validate before hashing, including direct internal callers."""
    quantity = payload.get("quantity")
    if type(quantity) is not int or not 1 <= quantity <= MAX_IMPORT_ROWS:
        raise HTTPException(422, "Review 1–100 input rows at a time")
    raw = payload.get("raw_text")
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 2_000_000:
            raise HTTPException(422, "Import text must be at most 2 MB")
    except UnicodeError:
        raise HTTPException(422, "Import text must be valid UTF-8") from None
    defaults = {key: payload.get(key) for key in ("default_first_name", "default_company_name")}
    for key, maximum in (("default_first_name", 100), ("default_company_name", 200)):
        value = defaults[key]
        if value is not None and (not isinstance(value, str) or len(value) > maximum or any(not ch.isprintable() for ch in value)):
            raise HTTPException(422, "Default names must contain printable text")
    if payload.get("source_type") not in ("csv", "pasted_urls"):
        raise HTTPException(422, "Use CSV or public LinkedIn profile URLs")
    for key in ("require_name", "skip_already_contacted"):
        if type(payload.get(key)) is not bool:
            raise HTTPException(422, "Explicit import options are required")
    overrides = payload.get("name_overrides", {})
    if not isinstance(overrides, dict) or len(overrides) > MAX_IMPORT_ROWS:
        raise HTTPException(422, "Too many edited names")
    for key, name in overrides.items():
        if not isinstance(key, str) or not re.fullmatch(r"(?:[1-9]|[1-9][0-9]|100)", key):
            raise HTTPException(422, "Edited names require canonical row numbers 1–100")
        if not isinstance(name, str) or len(name) > 100 or any(not ch.isprintable() for ch in name):
            raise HTTPException(422, "Edited first names must be printable and at most 100 characters")
    allowed = {"source_type", "raw_text", "quantity", "require_name", "skip_already_contacted", "default_first_name",
        "default_company_name", "name_overrides", "request_id", "request_scope", "campaign_id", "revision", "review_digest"}
    if set(payload) - allowed:
        raise HTTPException(422, "Unsupported import fields")


def parsed_source(payload: dict) -> tuple[list[dict], bool]:
    """Read only the selected prefix plus one sentinel, including invalid records."""
    validate_input_bounds(payload)
    quantity, raw = payload["quantity"], payload["raw_text"]
    defaults = {key: payload.get(key) for key in ("default_first_name", "default_company_name")}
    more = False
    try:
        if payload["source_type"] == "csv":
            reader = csv.reader(io.StringIO(raw.lstrip("\ufeff")))
            header = next(reader, None)
            if len(header or []) > MAX_CSV_COLUMNS:
                raise HTTPException(422, "CSV supports at most 100 columns in this reviewed import")
            if not header:
                raise HTTPException(422, "CSV needs a header and contact rows")
            selected = io.StringIO()
            writer = csv.writer(selected)
            writer.writerow(header)
            mapping = detect_csv_headers(header)
            transport_columns = {mapping[key] for key in ("member_urn", "sales_lead_urn") if key in mapping}
            for index, row in enumerate(islice((item for item in reader if item), quantity + 1)):
                if index == quantity:
                    more = True
                    break
                if len(row) > MAX_CSV_COLUMNS:
                    raise HTTPException(422, "CSV supports at most 100 columns in this reviewed import")
                if any(name in transport_columns and value.strip() for name, value in zip(header, row)):
                    raise HTTPException(422, "Public-profile imports cannot accept transport recipient IDs. Remove member/URN columns; verified identity resolution is not available.")
                writer.writerow(row)
            rows = LeadImporter.parse_csv_content(selected.getvalue(), include_invalid=True, **defaults)
        elif payload["source_type"] == "pasted_urls":
            # Match the parser's full Unicode splitlines contract without
            # materializing the unselected suffix.
            lines = (match.group() for match in re.finditer(r"[^\n\r\v\f\x1c-\x1e\x85\u2028\u2029]+", raw) if match.group().strip())
            selected_lines = []
            for index, line in enumerate(islice(lines, quantity + 1)):
                if index == quantity:
                    more = True
                    break
                selected_lines.append(line)
            selected = "\n".join(selected_lines)
            rows = LeadImporter.parse_pasted_urls(selected, require_name=False, **defaults)
        else:
            raise HTTPException(422, "Use CSV or public LinkedIn profile URLs")
    except (csv.Error, UnicodeError, ValueError):
        raise HTTPException(422, "Could not read this source; check its format and size") from None
    rows = rows[:quantity]
    if any(row.get("identifiers", {}).get(key) for row in rows for key in ("member_urn", "sales_lead_urn")):
        raise HTTPException(422, "Public-profile imports require public URLs without supplied transport recipient IDs")
    for key, name in payload.get("name_overrides", {}).items():
        if int(key) > len(rows):
            raise HTTPException(422, "Edited name refers to an unreviewed row")
        rows[int(key) - 1].update(first_name=name.strip(), cleaned_first_name=name.strip(), raw_first_name=name.strip())
    if not rows:
        raise HTTPException(422, "No contact rows were supplied")
    return rows, more


async def preview_import(db: Any, workspace: str, actor: str, list_id: str, payload: dict) -> dict:
    row, parent = await lists.list_record(db, workspace, list_id, writing=True)
    if not isinstance(parent.get("status"), str) or parent["status"] not in {"draft", "paused"}:
        raise HTTPException(409, "Pause this campaign before importing contacts into an audience list")
    rows, more = parsed_source(payload)
    preview = await LeadImporter.preview_leads(rows, row["campaign_id"], workspace, db,
        skip_already_contacted=payload["skip_already_contacted"], skip_do_not_contact=True, require_name=payload["require_name"], _match_limit=1000)
    return {**preview, "list": lists.public_list(row), "request_scope": request_scope(workspace, actor),
        "more_rows_in_source": more, "selected_rows": len(rows), "quantity": payload["quantity"]}


async def inspect_import(db: Any, workspace: str, actor: str, request_id: str, expected_scope: str) -> dict:
    verify_scope(workspace, actor, expected_scope)
    row = await db.outreach_lead_list_imports.find_one(control_scope(workspace, actor, request_id))
    if not row:
        raise HTTPException(404, "No saved status is available yet. Keep this request reference and check again or cancel it.")
    return public_receipt(row)


async def cancel_import(db: Any, workspace: str, actor: str, request_id: str, expected_scope: str) -> dict:
    verify_scope(workspace, actor, expected_scope)
    scope = control_scope(workspace, actor, request_id)
    async def cancel(current):
        row = await current.outreach_lead_list_imports.find_one(scope)
        if row:
            public_receipt(row)
            if row["status"] != "pending":
                return public_receipt(row)
            changed = await current.outreach_lead_list_imports.update_one(pending_scope(scope, row),
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)}})
            if changed.matched_count != 1:
                raise HTTPException(409, "Import request changed; check its original status")
        else:
            # A cancellation tombstone orders ahead of an in-flight phase-one
            # insert. It cannot claim or undo a completed import.
            await current.outreach_lead_list_imports.insert_one({"_id": scope["_id"], "workspace_id": workspace,
                "actor_id": actor, "request_id": scope["request_id"], "request_scope": expected_scope,
                "status": "cancelled", "contract_version": CONTRACT_VERSION,
                "created_at": datetime.now(timezone.utc), "cancelled_at": datetime.now(timezone.utc)})
        return public_receipt(await current.outreach_lead_list_imports.find_one(scope))
    return await lists.commit(db, workspace, cancel)


async def import_contacts(db: Any, workspace: str, actor: str, list_id: str, payload: dict) -> dict:
    verify_scope(workspace, actor, payload["request_scope"])
    scope = control_scope(workspace, actor, payload["request_id"])
    validate_input_bounds(payload)
    lists.list_identifier(list_id)
    lists.identifier(payload["campaign_id"])
    if type(payload.get("revision")) is not int or payload["revision"] < 1 or not isinstance(payload.get("review_digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", payload["review_digest"]):
        raise HTTPException(422, "A reviewed audience revision is required")
    digest = canonical_hash(["audience-import-input-v1", list_id, payload])
    previous = await db.outreach_lead_list_imports.find_one(scope)
    if previous:
        public_receipt(previous)
        if previous["status"] == "cancelled":
            return public_receipt(previous)
        if previous.get("input_digest") != digest:
            raise HTTPException(409, "This import request was already used for different content")
        if previous["status"] == "completed":
            return public_receipt(previous)
    rows, more = parsed_source(payload)
    parsed_digest = canonical_hash(rows)

    async def begin(current):
        saved = await current.outreach_lead_list_imports.find_one(scope)
        if saved:
            public_receipt(saved)
            if saved["status"] == "cancelled":
                return saved
            if saved.get("input_digest") != digest:
                raise HTTPException(409, "This import request was already used for different content")
            return saved
        row, parent = await lists.list_record(current, workspace, list_id, writing=True)
        if (row["campaign_id"] != payload["campaign_id"] or lists.review_digest(row) != payload["review_digest"]
                or row["revision"] != payload["revision"]):
            raise HTTPException(409, "Audience list changed; review the import again")
        if not isinstance(parent.get("status"), str) or parent["status"] not in {"draft", "paused"}:
            raise HTTPException(409, "Pause this campaign before importing contacts into an audience list")
        if parent.get("authorization_revision") is not None and (type(parent["authorization_revision"]) is not int or parent["authorization_revision"] < 0):
            raise HTTPException(503, "Campaign authorization needs review")
        control = {"_id": scope["_id"], "workspace_id": workspace, "actor_id": actor, "request_id": scope["request_id"],
            "request_scope": payload["request_scope"], "list_id": list_id, "campaign_id": row["campaign_id"],
            "list_native_digest": lists.physical_digest(row["_id"]), "list_name": row["name"],
            "campaign_native_digest": row["campaign_native_digest"], "campaign_status": parent["status"],
            "campaign_authorization_revision": parent.get("authorization_revision"), "review_digest": payload["review_digest"],
            "original_revision": row["revision"], "contract_version": CONTRACT_VERSION, "parsed_digest": parsed_digest,
            "input_digest": digest, "requested_rows": payload["quantity"], "status": "pending", "created_at": datetime.now(timezone.utc)}
        control["context_digest"] = context_digest(control)
        await lists.touch_campaign(current, workspace, parent)
        await current.outreach_lead_list_imports.insert_one(control)
        return control
    control = await lists.commit(db, workspace, begin)
    if control["status"] != "pending":
        return public_receipt(control)

    async def finish(current):
        saved = await current.outreach_lead_list_imports.find_one(scope)
        public_receipt(saved)
        if saved["status"] != "pending":
            return public_receipt(saved)
        if (saved.get("input_digest") != digest or saved.get("contract_version") != CONTRACT_VERSION
                or saved.get("parsed_digest") != parsed_digest):
            raise HTTPException(409, "Import parsing contract changed; keep this request for review")
        row, parent = await lists.list_record(current, workspace, list_id, writing=True)
        if (saved["list_id"] != list_id or saved["campaign_id"] != payload["campaign_id"] or saved["campaign_id"] != row["campaign_id"]
                or saved["list_name"] != row["name"] or lists.review_digest(row) != saved["review_digest"] or row["revision"] != saved["original_revision"]
                or lists.physical_digest(row["_id"]) != saved["list_native_digest"]
                or row["campaign_native_digest"] != saved["campaign_native_digest"]
                or not isinstance(parent.get("status"), str) or parent.get("status") != saved["campaign_status"] or parent.get("status") not in {"draft", "paused"}
                or type(parent.get("authorization_revision")) is not type(saved["campaign_authorization_revision"])
                or parent.get("authorization_revision") != saved["campaign_authorization_revision"]):
            raise HTTPException(409, "Campaign or audience changed; check or cancel this request before reviewing again")
        admitted = await LeadImporter.ingest_leads(rows, row["campaign_id"], workspace, current,
            skip_already_contacted=payload["skip_already_contacted"], require_name=payload["require_name"],
            source=payload["source_type"], source_metadata={"source_type": payload["source_type"], "consent_basis": "user_provided"},
            _ordered=True, _record_decisions=True, _match_limit=1000)
        selected = await lists.selected_leads(current, workspace, admitted["lead_ids"]) if admitted["lead_ids"] else {}
        known = await lists.selected_members(current, workspace, row, admitted["lead_ids"]) if admitted["lead_ids"] else {}
        for lead in selected.values():
            await lists.add_member(current, workspace, actor, row, lead, known)
        changed = await current.outreach_lead_lists.update_one({**captured_scope(workspace, row), "revision": row["revision"]},
            {"$inc": {"revision": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})
        if changed.matched_count != 1:
            raise HTTPException(409, "Audience list changed during import")
        await lists.touch_campaign(current, workspace, parent)
        result = {key: admitted[key] for key in ("imported_count", "skipped_count", "duplicates_count", "lead_ids", "row_results")}
        result.update(membership_added_count=len(selected), requested_rows=payload["quantity"], considered_rows=len(rows),
            more_rows_in_source=more, collection_verified=False, list_revision=row["revision"] + 1)
        done = await current.outreach_lead_list_imports.update_one(pending_scope(scope, saved),
            {"$set": {"status": "completed", "result": result, "completed_at": datetime.now(timezone.utc)}})
        if done.matched_count != 1:
            raise HTTPException(409, "Import request changed before completion")
        return public_receipt(await current.outreach_lead_list_imports.find_one(scope))
    return await lists.commit(db, workspace, finish)
