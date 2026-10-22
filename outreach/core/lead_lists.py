"""Campaign audience metadata. Membership never creates an enrollment or send path."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
import re
import uuid
from typing import Any

from bson import json_util
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.core.lead_tags import clean_tag_name, captured_scope, require_exact_rows, unique_resource
from outreach.core.search_sources import unverified_search_lead
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.workspace_scope import workspace_scope

MAX_LISTS = 50
MAX_MEMBERS = 100
LIST_ID = re.compile(r"^list_[0-9a-f]{64}$")
MEMBER_ID = re.compile(r"^[0-9a-f]{64}$")


def clean_name(value: str) -> tuple[str, str]:
    try:
        return clean_tag_name(value)
    except HTTPException:
        raise HTTPException(422, "Audience list name must contain 1–60 printable characters") from None


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise HTTPException(422, "Invalid campaign or contact identifier")
    return value


def request_identity(workspace: str, campaign: str, request: str) -> str:
    if not isinstance(request, str) or len(request) != 36:
        raise HTTPException(422, "A request UUID is required")
    try:
        request = str(uuid.UUID(request))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "A request UUID is required") from None
    return "list_" + canonical_hash(["manual-audience", workspace, campaign, request])


def list_identifier(value: str) -> str:
    if not isinstance(value, str) or not LIST_ID.fullmatch(value):
        raise HTTPException(422, "Invalid audience list identifier")
    return value


def physical_digest(value: Any) -> str:
    return canonical_hash(json_util.dumps(value, json_options=json_util.CANONICAL_JSON_OPTIONS))


def review_digest(row: dict) -> str:
    return canonical_hash(["audience-review-v1", row["workspace_id"], row["id"], physical_digest(row["_id"]),
        row["campaign_native_digest"], row["revision"]])


def public_list(row: dict) -> dict:
    if (not isinstance(row, dict) or not isinstance(row.get("id"), str) or not LIST_ID.fullmatch(row["id"])
            or type(row.get("revision")) is not int or row["revision"] < 1
            or not isinstance(row.get("source_kind"), str) or row["source_kind"] not in {"manual", "legacy_unknown"}
            or row.get("collection_state") != {"manual": "not_collected", "legacy_unknown": "unknown"}.get(row.get("source_kind"))
            or row.get("source_fingerprint") is not None or row.get("requested_limit") is not None
            or not isinstance(row.get("campaign_native_digest"), str) or not MEMBER_ID.fullmatch(row["campaign_native_digest"])
            or not isinstance(row.get("name"), str) or not row["name"].strip()
            or not isinstance(row.get("campaign_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", row["campaign_id"])):
        raise HTTPException(503, "Audience list metadata needs review")
    return {**{key: row.get(key) for key in ("id", "campaign_id", "name", "revision", "source_kind",
        "collection_state", "source_fingerprint", "requested_limit", "created_at", "updated_at")},
        "archived": "archived_at" in row, "collection_verified": False, "review_digest": review_digest(row),
        "legacy_adoption": {key: row["migration"].get(key) for key in ("status", "processed_count")}
            if isinstance(row.get("migration"), dict) else None}


async def campaign_record(db: Any, workspace: str, campaign: str, *, writing: bool = False) -> dict:
    identifier(campaign)
    row = await unique_resource(db.outreach_campaigns, workspace, campaign)
    if not row or row.get("is_deleted") or row.get("status") == "deleted":
        raise HTTPException(404, "Campaign not found")
    if writing and row.get("status") == "warming_up":
        raise HTTPException(409, "Cancel conditional launch before editing its audience lists")
    return row


async def list_record(db: Any, workspace: str, list_id: str, *, writing: bool = False) -> tuple[dict, dict]:
    list_identifier(list_id)
    row = await unique_resource(db.outreach_lead_lists, workspace, list_id)
    if not row:
        raise HTTPException(404, "Audience list not found")
    public_list(row)
    campaign = await campaign_record(db, workspace, row.get("campaign_id"), writing=writing)
    if row["campaign_native_digest"] != physical_digest(campaign["_id"]):
        raise HTTPException(409, "Audience list belongs to an older campaign record; review its identity")
    if writing and "archived_at" in row:
        raise HTTPException(409, "Archived audience lists cannot be edited")
    return row, campaign


async def commit(db: Any, workspace: str, operation: Any) -> Any:
    try:
        return await mutate_suppression(db, workspace, operation)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm audience changes; reload before retrying") from None
    except DuplicateKeyError:
        raise HTTPException(409, "Audience identity changed; reload before retrying") from None


async def touch_campaign(db: Any, workspace: str, campaign: dict) -> None:
    changed = await db.outreach_campaigns.update_one(captured_scope(workspace, campaign),
        {"$inc": {"audience_metadata_revision": 1}})
    if changed.matched_count != 1:
        raise HTTPException(409, "Campaign changed during audience review")


async def inventory(db: Any, workspace: str, campaign: str, include_archived: bool = False) -> dict:
    parent = await campaign_record(db, workspace, campaign)
    query = {**workspace_scope(workspace), "campaign_id": campaign, "campaign_id.0": {"$exists": False}}
    rows = await db.outreach_lead_lists.find(query).sort("id", 1).limit(MAX_LISTS + 1).to_list(MAX_LISTS + 1)
    if len(rows) > MAX_LISTS or len({row.get("id") for row in rows if isinstance(row.get("id"), str)}) != len(rows):
        raise HTTPException(503, "Audience list inventory needs review")
    for row in rows:
        public_list(row)
        if row["campaign_native_digest"] != physical_digest(parent["_id"]):
            raise HTTPException(409, "Audience inventory has an older campaign identity; review before use")
    return {"lists": [public_list(row) for row in rows if include_archived or "archived_at" not in row],
        "membership_controls_execution": False}


async def create_list(db: Any, workspace: str, actor: str, campaign: str, name: str, request: str) -> dict:
    identifier(campaign)
    display, normalized = clean_name(name)
    identity = request_identity(workspace, campaign, request)
    digest = canonical_hash([campaign, display])

    async def save(current):
        parent = await campaign_record(current, workspace, campaign, writing=True)
        existing = await unique_resource(current.outreach_lead_lists, workspace, identity)
        if existing:
            if (existing.get("creation_digest") != digest or existing.get("campaign_id") != campaign
                    or existing.get("campaign_native_digest") != physical_digest(parent["_id"])):
                raise HTTPException(409, "The list request was already used for different content")
            return public_list(existing)
        scope = {**workspace_scope(workspace), "campaign_id": campaign, "campaign_id.0": {"$exists": False}}
        if await current.outreach_lead_lists.count_documents(scope) >= MAX_LISTS:
            raise HTTPException(422, "This campaign has reached its 50-list limit")
        if await current.outreach_lead_lists.find_one({**scope, "name_normalized": normalized}):
            raise HTTPException(409, "An audience list with this name already exists, including archived lists")
        now = datetime.now(timezone.utc)
        row = {"id": identity, "workspace_id": workspace, "campaign_id": campaign, "name": display,
            "campaign_native_digest": physical_digest(parent["_id"]),
            "name_normalized": normalized, "source_kind": "manual", "collection_state": "not_collected",
            "source_fingerprint": None, "requested_limit": None, "creation_digest": digest,
            "revision": 1, "created_by": actor, "created_at": now, "updated_at": now}
        await touch_campaign(current, workspace, parent)
        await current.outreach_lead_lists.insert_one(row)
        return public_list(await unique_resource(current.outreach_lead_lists, workspace, identity))
    return await commit(db, workspace, save)


async def edit_list(db: Any, workspace: str, list_id: str, revision: int, *, name: str | None = None, archive: bool = False,
                    expected_review: str | None = None) -> dict:
    if type(revision) is not int or revision < 1:
        raise HTTPException(422, "A current list revision is required")
    display, normalized = clean_name(name) if not archive else (None, None)
    async def save(current):
        row, parent = await list_record(current, workspace, list_id, writing=True)
        if row["revision"] != revision or expected_review is not None and review_digest(row) != expected_review:
            raise HTTPException(409, "Audience list changed; reload before editing")
        values = {"updated_at": datetime.now(timezone.utc)}
        if archive:
            values["archived_at"] = values["updated_at"]
        else:
            if await current.outreach_lead_lists.find_one({**workspace_scope(workspace),
                    "campaign_id": row["campaign_id"], "name_normalized": normalized, "id": {"$ne": list_id}}):
                raise HTTPException(409, "An audience list with this name already exists")
            values.update(name=display, name_normalized=normalized)
        await touch_campaign(current, workspace, parent)
        changed = await current.outreach_lead_lists.update_one({**captured_scope(workspace, row), "revision": revision},
            {"$set": values, "$inc": {"revision": 1}})
        if changed.matched_count != 1:
            raise HTTPException(409, "Audience list changed during review")
        return public_list(await unique_resource(current.outreach_lead_lists, workspace, list_id))
    return await commit(db, workspace, save)


def membership_scope(workspace: str, row: dict) -> dict:
    return {**workspace_scope(workspace), "campaign_id": row["campaign_id"], "campaign_id.0": {"$exists": False},
            "list_id": row["id"], "list_id.0": {"$exists": False}}


def validate_member(row: dict, workspace: str, list_row: dict) -> None:
    lead_id = row.get("lead_id")
    if not isinstance(lead_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", lead_id):
        raise HTTPException(503, "Audience membership identity needs review")
    expected = canonical_hash([workspace, list_row["id"], lead_id])
    if (row.get("id") != expected or row.get("_id") != expected
            or row.get("list_native_digest") != physical_digest(list_row["_id"])
            or not isinstance(row.get("lead_native_digest"), str) or not MEMBER_ID.fullmatch(row["lead_native_digest"])):
        raise HTTPException(503, "Audience membership identity needs review")


async def selected_leads(db: Any, workspace: str, identifiers: list[str], *, allow_missing: bool = False) -> dict[str, dict]:
    rows = await db.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": identifiers},
        "id.0": {"$exists": False}}).limit(len(identifiers) + 1).to_list(len(identifiers) + 1)
    require_exact_rows(rows, identifiers, allow_missing=allow_missing)
    return {row["id"]: row for row in rows}


async def selected_members(db: Any, workspace: str, row: dict, lead_ids: list[str]) -> dict[str, dict]:
    records = await db.outreach_lead_list_members.find({**membership_scope(workspace, row),
        "lead_id": {"$in": lead_ids}, "lead_id.0": {"$exists": False}}).limit(len(lead_ids) + 1).to_list(len(lead_ids) + 1)
    require_exact_rows([{"id": item.get("lead_id")} for item in records], lead_ids, allow_missing=True)
    for item in records:
        validate_member(item, workspace, row)
    return {item["lead_id"]: item for item in records}


async def add_member(db: Any, workspace: str, actor: str, row: dict, lead: dict, known: dict[str, dict]) -> bool:
    existing = known.get(lead["id"])
    if existing and existing.get("lead_native_digest") != physical_digest(lead["_id"]):
        raise HTTPException(409, "Audience membership identity needs review")
    if existing:
        return False
    identity = canonical_hash([workspace, row["id"], lead["id"]])
    await db.outreach_lead_list_members.insert_one({"workspace_id": workspace, "campaign_id": row["campaign_id"],
        "list_id": row["id"], "lead_id": lead["id"], "_id": identity, "id": identity,
        "list_native_digest": physical_digest(row["_id"]),
        "lead_native_digest": physical_digest(lead["_id"]), "created_by": actor,
        "created_at": datetime.now(timezone.utc)})
    return True


async def change_members(db: Any, workspace: str, actor: str, list_id: str, revision: int,
                         lead_ids: list[str], operation: str, *, expected_review: str | None = None) -> dict:
    if type(revision) is not int or revision < 1 or operation not in {"add", "remove"}:
        raise HTTPException(422, "Invalid audience membership change")
    if not isinstance(lead_ids, list) or not 1 <= len(lead_ids) <= MAX_MEMBERS:
        raise HTTPException(422, "Select 1–100 distinct contacts")
    for lead_id in lead_ids:
        identifier(lead_id)
    if len(set(lead_ids)) != len(lead_ids):
        raise HTTPException(422, "Select distinct contacts")
    async def save(current):
        row, parent = await list_record(current, workspace, list_id, writing=True)
        if row["revision"] != revision or expected_review is not None and review_digest(row) != expected_review:
            raise HTTPException(409, "Audience list changed; reload before editing")
        scope = membership_scope(workspace, row)
        changed = 0
        if operation == "add":
            selected = await selected_leads(current, workspace, lead_ids)
            known = await selected_members(current, workspace, row, lead_ids)
            for lead_id in lead_ids:
                lead = selected.get(lead_id)
                if not lead or lead.get("campaign_id") != row["campaign_id"] or not isinstance(lead.get("campaign_id"), str):
                    raise HTTPException(404, "A selected campaign contact was not found")
                changed += await add_member(current, workspace, actor, row, lead, known)
        else:
            removed = await current.outreach_lead_list_members.delete_many({**scope, "lead_id": {"$in": lead_ids},
                "lead_id.0": {"$exists": False}})
            changed = removed.deleted_count
        await touch_campaign(current, workspace, parent)
        updated = await current.outreach_lead_lists.update_one({**captured_scope(workspace, row), "revision": revision},
            {"$inc": {"revision": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})
        if updated.matched_count != 1:
            raise HTTPException(409, "Audience list changed during membership update")
        return {"id": list_id, "revision": revision + 1, "modified_count": changed, "execution_changed": False}
    return await commit(db, workspace, save)


async def members(db: Any, workspace: str, list_id: str, *, after: str | None = None, limit: int = 50) -> dict:
    row, _ = await list_record(db, workspace, list_id)
    if (type(limit) is not int or not 1 <= limit <= MAX_MEMBERS
            or after is not None and (not isinstance(after, str) or not MEMBER_ID.fullmatch(after))):
        raise HTTPException(422, "Invalid membership page")
    scope = membership_scope(workspace, row)
    query = {**scope, **({"id": {"$gt": after}} if after else {})}
    records = await db.outreach_lead_list_members.find(query).sort("id", 1).limit(limit + 1).to_list(limit + 1)
    for member in records[:limit]:
        validate_member(member, workspace, row)
    selected = await selected_leads(db, workspace, [item["lead_id"] for item in records[:limit]], allow_missing=True) if records else {}
    items = []
    for member in records[:limit]:
        validate_member(member, workspace, row)
        lead = selected.get(member["lead_id"])
        available = bool(lead and lead.get("campaign_id") == row["campaign_id"]
                         and physical_digest(lead["_id"]) == member["lead_native_digest"])
        items.append({"id": member["id"], "lead_id": member["lead_id"],
            "status": "source_review" if available and unverified_search_lead(lead) else "available" if available else "orphaned",
            "contact": {key: lead.get(key) for key in ("first_name", "last_name", "linkedin_url")} if available else None})
    return {"list": public_list(row), "members": items, "membership_count": await db.outreach_lead_list_members.count_documents(scope),
        "next_cursor": items[-1]["id"] if len(records) > limit and items else None,
        "membership_controls_execution": False, "complete_collection": False}


async def adopt_existing(db: Any, workspace: str, actor: str, campaign: str, revision: int, writers_drained: bool) -> dict:
    """Explicit bounded metadata backfill under an operator's drain assertion."""
    identifier(campaign)
    if writers_drained is not True or type(revision) is not int or revision < 0:
        raise HTTPException(422, "Assert drained enrollment writers and supply the current list revision (0 initially)")
    identity = "list_" + canonical_hash(["existing-audience", workspace, campaign])
    async def save(current):
        parent = await campaign_record(current, workspace, campaign, writing=True)
        scope = {**workspace_scope(workspace), "campaign_id": campaign, "campaign_id.0": {"$exists": False}}
        # Unsupported identities cannot be silently skipped as completed history.
        if await current.outreach_leads.find_one({**scope, "$or": [
                {"id": {"$not": {"$type": "string"}}}, {"id.0": {"$exists": True}}]}):
            raise HTTPException(409, "Existing audience has malformed contact identities; review before backfill")
        row = await unique_resource(current.outreach_lead_lists, workspace, identity)
        if row:
            public_list(row)
            if ("archived_at" in row or row.get("source_kind") != "legacy_unknown" or row["revision"] != revision
                    or row.get("campaign_id") != campaign or row.get("campaign_native_digest") != physical_digest(parent["_id"])):
                raise HTTPException(409, "Existing audience list changed; reload before backfill")
            migration = row.get("migration")
            if (not isinstance(migration, dict) or set(migration) != {"cursor", "upper_bound", "processed_count", "status"}
                    or type(migration.get("processed_count")) is not int
                    or migration["processed_count"] < 0
                    or not isinstance(migration.get("status"), str)
                    or migration.get("status") not in {"pending", "selected_scope_complete"}
                    or any(migration.get(key) is not None and (not isinstance(migration[key], str)
                        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", migration[key])) for key in ("cursor", "upper_bound"))
                    or migration.get("cursor") is not None and (migration.get("upper_bound") is None
                        or migration["cursor"] > migration["upper_bound"])
                    or (migration["processed_count"] > 0) != (migration.get("cursor") is not None)
                    or migration["status"] == "selected_scope_complete" and migration.get("cursor") != migration.get("upper_bound")):
                raise HTTPException(409, "Existing audience checkpoint needs review")
            if migration["status"] == "selected_scope_complete":
                return public_list(row)
        else:
            if revision != 0:
                raise HTTPException(409, "Existing audience list is not initialized")
            if (await current.outreach_lead_lists.count_documents(scope) >= MAX_LISTS
                    or await current.outreach_lead_lists.find_one({**scope, "name_normalized": "existing audience"})):
                raise HTTPException(409, "Rename the conflicting list or review list capacity before backfill")
            last = await current.outreach_leads.find(scope).sort("id", -1).limit(1).to_list(1)
            migration = {"cursor": None, "upper_bound": last[0]["id"] if last else None,
                "processed_count": 0, "status": "pending"}
            now = datetime.now(timezone.utc)
            row = {"id": identity, "workspace_id": workspace, "campaign_id": campaign,
                "campaign_native_digest": physical_digest(parent["_id"]),
                "name": "Existing audience", "name_normalized": "existing audience", "revision": 1,
                "source_kind": "legacy_unknown", "collection_state": "unknown", "source_fingerprint": None,
                "requested_limit": None, "created_by": actor, "created_at": now, "updated_at": now, "migration": migration}
            await current.outreach_lead_lists.insert_one(row)
        bounds = {"$lte": migration["upper_bound"]}
        if migration.get("cursor") is not None:
            bounds["$gt"] = migration["cursor"]
        records = (await current.outreach_leads.find({**scope, "id": bounds}).sort("id", 1)
            .limit(MAX_MEMBERS + 1).to_list(MAX_MEMBERS + 1)) if migration["upper_bound"] is not None else []
        batch_ids = [lead["id"] for lead in records[:MAX_MEMBERS]]
        exact = await selected_leads(current, workspace, batch_ids) if batch_ids else {}
        known = await selected_members(current, workspace, row, batch_ids) if batch_ids else {}
        for lead in records[:MAX_MEMBERS]:
            identifier(lead["id"])
            selected = exact.get(lead["id"])
            if not selected or selected["_id"] != lead["_id"]:
                raise HTTPException(409, "Existing audience has ambiguous contact identities")
            await add_member(current, workspace, actor, row, lead, known)
        progress = {**migration, "cursor": records[min(len(records), MAX_MEMBERS) - 1]["id"] if records else migration.get("cursor"),
            "processed_count": migration["processed_count"] + min(len(records), MAX_MEMBERS),
            "status": "pending" if len(records) > MAX_MEMBERS else "selected_scope_complete"}
        if progress["status"] == "selected_scope_complete" and progress["cursor"] != progress["upper_bound"]:
            raise HTTPException(409, "Existing audience changed after its captured upper bound; review the drain")
        await touch_campaign(current, workspace, parent)
        updated = await current.outreach_lead_lists.update_one({**captured_scope(workspace, row), "revision": row["revision"]},
            {"$set": {"migration": progress, "updated_at": datetime.now(timezone.utc)}, "$inc": {"revision": 1}})
        if updated.matched_count != 1:
            raise HTTPException(409, "Existing audience changed during backfill")
        return public_list(await unique_resource(current.outreach_lead_lists, workspace, identity))
    return await commit(db, workspace, save)
