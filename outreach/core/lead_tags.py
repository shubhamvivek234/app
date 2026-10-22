"""Canonical CRM tags. Metadata edits never grant campaign execution authority."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from outreach.core.suppression import SuppressionUnavailable
from outreach.core.workspace_scope import workspace_scope

TAG_ID_RE = re.compile(r"^tag_[0-9a-f]{24}$")
MAX_TAGS_PER_LEAD = 50
MAX_WORKSPACE_TAGS = 500
MAX_MIGRATION_LABELS = 100

DEFAULT_SALES_TAGS: tuple[dict[str, str], ...] = (
    {"name": "Interested", "color": "#10b981"},
    {"name": "Very interested", "color": "#059669"},
    {"name": "High priority", "color": "#ef4444"},
    {"name": "Wrong timing", "color": "#f59e0b"},
    {"name": "Not interested", "color": "#6b7280"},
    {"name": "Ghosted", "color": "#8b5cf6"},
    {"name": "Meeting booked", "color": "#3b82f6"},
)


def clean_tag_name(value: str) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", value or "").split())
    if not display or len(display) > 60 or any(unicodedata.category(ch).startswith("C") for ch in display):
        raise HTTPException(422, "Tag name must contain 1–60 printable characters")
    return display, display.casefold()


def validate_tag_id(value: str) -> str:
    if not isinstance(value, str) or not TAG_ID_RE.fullmatch(value):
        raise HTTPException(422, "Invalid tag id")
    return value


def resource_scope(workspace: str, identifier: str) -> dict:
    return {**workspace_scope(workspace), "id": identifier, "id.0": {"$exists": False}}


def require_exact_rows(rows: list[dict], identifiers: list[str], *, allow_missing: bool = False) -> None:
    """A matching count cannot establish one physical record per public ID."""
    found = [row.get("id") for row in rows]
    if any(not isinstance(value, str) for value in found) or len(set(found)) != len(found):
        raise HTTPException(409, "Duplicate record identities require review")
    if not set(found).issubset(identifiers) or (not allow_missing and set(found) != set(identifiers)):
        raise HTTPException(404, "One or more selected records were not found")


async def unique_resource(collection: Any, workspace: str, identifier: str) -> dict | None:
    rows = await collection.find(resource_scope(workspace, identifier)).limit(2).to_list(length=2)
    require_exact_rows(rows, [identifier], allow_missing=True)
    return rows[0] if rows else None


def captured_scope(workspace: str, row: dict) -> dict:
    """Bind writes to the physical record read, including test records without _id."""
    return {**resource_scope(workspace, row["id"]),
            "_id": row["_id"] if "_id" in row else {"$exists": False}}


def assignment_scope(workspace: str, row: dict) -> dict:
    return {**captured_scope(workspace, row), **{
        key: row[key] if key in row else {"$exists": False} for key in ("tag_ids", "tag_revision")}}


def stored_ids(lead: dict) -> list[str]:
    ids = lead.get("tag_ids", [])
    if not isinstance(ids, list) or len(ids) > MAX_TAGS_PER_LEAD or len(set(x for x in ids if isinstance(x, str))) != len(ids):
        raise HTTPException(409, "Lead tags require repair before editing")
    for identifier in ids:
        validate_tag_id(identifier)
    return ids


def stored_revision(lead: dict) -> int:
    revision = lead.get("tag_revision", 0)
    if type(revision) is not int or revision < 0:
        raise HTTPException(409, "Lead tags require repair before editing")
    return revision


def public_tag(doc: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(doc.get("id"), str) or not TAG_ID_RE.fullmatch(doc["id"])
            or not isinstance(doc.get("name"), str) or not doc["name"].strip()
            or not isinstance(doc.get("color"), str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", doc["color"])
            or type(doc.get("revision")) is not int or doc["revision"] < 1):
        raise HTTPException(503, "Tag definitions are unavailable; contact support")
    return {**{key: doc.get(key) for key in ("id", "name", "color", "revision", "created_at", "updated_at")},
            "archived": "archived_at" in doc}


async def active_tag_map(db: Any, workspace: str, tag_ids: list[str] | None = None, *, include_archived: bool = False) -> dict[str, dict]:
    query = workspace_scope(workspace)
    if not include_archived:
        query["archived_at"] = {"$exists": False}
    if tag_ids is not None:
        if not tag_ids:
            return {}
        query["id"] = {"$in": list(dict.fromkeys(tag_ids))}
    rows = await db.outreach_lead_tags.find(query).sort([("name_normalized", 1), ("id", 1)]).limit(MAX_WORKSPACE_TAGS + 1).to_list(length=MAX_WORKSPACE_TAGS + 1)
    if len(rows) > MAX_WORKSPACE_TAGS:
        raise HTTPException(503, "Tag inventory exceeds the supported limit")
    return {row["id"]: public_tag(row) for row in rows}


async def hydrate_lead_tags(db: Any, workspace: str, leads: list[dict]) -> None:
    identifiers = list({identifier for lead in leads for identifier in stored_ids(lead)})
    definitions = await active_tag_map(db, workspace, identifiers, include_archived=True)
    for lead in leads:
        # Archived assignment IDs remain in storage/history; only active
        # definitions become visible badges.
        lead["tag_ids"] = stored_ids(lead)
        lead["tag_revision"] = stored_revision(lead)
        lead["tags"] = [definitions[identifier] for identifier in lead["tag_ids"] if identifier in definitions and not definitions[identifier]["archived"]]
        lead["archived_tags"] = [definitions[identifier] for identifier in lead["tag_ids"] if identifier in definitions and definitions[identifier]["archived"]]


async def _commit(db: Any, workspace: str, operation: Any) -> Any:
    from outreach.core.suppression import mutate_suppression
    try:
        return await mutate_suppression(db, workspace, operation)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm tag changes. Reload before retrying.") from None


async def create_tag(db: Any, workspace: str, actor: str, name: str, color: str) -> dict:
    display, normalized = clean_tag_name(name)
    identifier = "tag_" + uuid.uuid4().hex[:24]

    async def save(current):
        scope = workspace_scope(workspace)
        if await current.outreach_lead_tags.find_one({**scope, "name_normalized": normalized}):
            raise HTTPException(409, "A tag with this name already exists, including archived tags")
        if await current.outreach_lead_tags.count_documents(scope) >= MAX_WORKSPACE_TAGS:
            raise HTTPException(422, "This workspace has reached its 500-tag limit")
        now = datetime.now(timezone.utc)
        doc = {"id": identifier, "workspace_id": workspace, "name": display,
               "name_normalized": normalized, "color": color.lower(), "revision": 1,
               "created_by": actor, "created_at": now, "updated_at": now}
        await current.outreach_lead_tags.insert_one(doc)
        return public_tag(doc)

    return await _commit(db, workspace, save)


async def seed_default_tags(db: Any, workspace: str, actor: str) -> list[dict]:
    """Explicitly seeds preset sales tags if they do not already exist in the workspace."""
    async def save(current):
        scope = workspace_scope(workspace)
        existing = await current.outreach_lead_tags.find(scope).limit(MAX_WORKSPACE_TAGS + 1).to_list(length=MAX_WORKSPACE_TAGS + 1)
        existing_norm = {row.get("name_normalized") for row in existing}
        now = datetime.now(timezone.utc)
        for preset in DEFAULT_SALES_TAGS:
            display, normalized = clean_tag_name(preset["name"])
            if normalized in existing_norm:
                continue
            if len(existing_norm) >= MAX_WORKSPACE_TAGS:
                break
            identifier = "tag_" + uuid.uuid4().hex[:24]
            doc = {
                "id": identifier,
                "workspace_id": workspace,
                "name": display,
                "name_normalized": normalized,
                "color": preset["color"].lower(),
                "revision": 1,
                "created_by": actor,
                "created_at": now,
                "updated_at": now,
            }
            await current.outreach_lead_tags.insert_one(doc)
            existing_norm.add(normalized)
        active = await active_tag_map(current, workspace)
        return list(active.values())

    return await _commit(db, workspace, save)


async def edit_tag(db: Any, workspace: str, identifier: str, revision: int,
                   name: str | None = None, color: str | None = None, *, archive: bool = False) -> dict:
    validate_tag_id(identifier)
    display, normalized = clean_tag_name(name) if not archive else (None, None)

    async def save(current):
        scope = resource_scope(workspace, identifier)
        tag = await current.outreach_lead_tags.find_one(scope)
        if not tag:
            raise HTTPException(404, "Tag not found")
        public_tag(tag)
        if tag["revision"] != revision or "archived_at" in tag:
            raise HTTPException(409, "Tag changed; reload before editing again")
        now = datetime.now(timezone.utc)
        values = {"updated_at": now}
        if archive:
            values["archived_at"] = now
        else:
            duplicate = await current.outreach_lead_tags.find_one({**workspace_scope(workspace), "name_normalized": normalized, "id": {"$ne": identifier}})
            if duplicate:
                raise HTTPException(409, "A tag with this name already exists, including archived tags")
            values.update(name=display, name_normalized=normalized, color=color.lower())
        await current.outreach_lead_tags.update_one({**scope, "revision": revision}, {"$set": values, "$inc": {"revision": 1}})
        tag.update(values, revision=revision + 1)
        return {"status": "archived", "tag_id": identifier} if archive else public_tag(tag)

    return await _commit(db, workspace, save)


async def assign_tags(db: Any, workspace: str, lead_ids: list[str], tag_id: str,
                      operation: str, revision: int | None = None) -> dict:
    validate_tag_id(tag_id)
    if operation not in {"add", "remove"}:
        raise HTTPException(422, "Choose add or remove")
    if not 1 <= len(lead_ids) <= 200 or len(set(lead_ids)) != len(lead_ids) or any(not isinstance(x, str) or not x.strip() or len(x) > 200 for x in lead_ids):
        raise HTTPException(422, "Select 1–200 unique lead ids")

    async def save(current):
        tag = await current.outreach_lead_tags.find_one(resource_scope(workspace, tag_id))
        if not tag or (operation == "add" and "archived_at" in tag):
            raise HTTPException(404, "Tag not found")
        public_tag(tag)
        rows = await current.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": lead_ids}, "id.0": {"$exists": False}}).to_list(length=201)
        require_exact_rows(rows, lead_ids)
        changed = 0
        for row in rows:
            ids, current_revision = stored_ids(row), stored_revision(row)
            if revision is not None and revision != current_revision:
                raise HTTPException(409, "Lead tags changed; reload before editing again")
            if operation == "add" and tag_id not in ids and len(ids) >= MAX_TAGS_PER_LEAD:
                raise HTTPException(422, "A lead can have at most 50 tags")
        now = datetime.now(timezone.utc)
        for row in rows:
            ids = stored_ids(row)
            if (operation == "add") == (tag_id in ids):
                continue
            operator = "$addToSet" if operation == "add" else "$pull"
            result = await current.outreach_leads.update_one(assignment_scope(workspace, row), {
                operator: {"tag_ids": tag_id}, "$inc": {"tag_revision": 1}, "$set": {"tags_updated_at": now}})
            if result.matched_count != 1:
                raise HTTPException(409, "A selected lead changed; reload before editing again")
            changed += 1
        return {"status": "updated", "matched_count": len(rows), "modified_count": changed}

    return await _commit(db, workspace, save)


async def hydrate_thread_tags(db: Any, workspace: str, threads: list[dict]) -> None:
    ids = list({thread["lead_id"] for thread in threads if isinstance(thread.get("lead_id"), str) and thread["lead_id"]})
    leads = await db.outreach_leads.find({**workspace_scope(workspace), "id": {"$in": ids}, "id.0": {"$exists": False}}).to_list(length=len(ids) + 1) if ids else []
    require_exact_rows(leads, ids, allow_missing=True)
    await hydrate_lead_tags(db, workspace, leads)
    by_id = {lead["id"]: lead for lead in leads}
    for thread in threads:
        legacy = thread.get("tags") or []
        thread["legacy_tags"] = [name for name in legacy if isinstance(name, str)] if isinstance(legacy, list) else []
        lead = by_id.get(thread.get("lead_id")) if isinstance(thread.get("lead_id"), str) else None
        thread.update(
            tag_ids=lead["tag_ids"] if lead else [],
            tag_revision=lead["tag_revision"] if lead else 0,
            tags=lead["tags"] if lead else [],
            tags_editable=bool(lead),
            lead_execution_state=lead.get("execution_state") if lead else None,
            lead_pause_reason=lead.get("pause_reason") if lead else None,
        )


async def migrate_legacy_tags(db: Any, workspace: str, actor: str, after_id: str = "") -> dict:
    """Explicit, bounded adoption. Unlinked/malformed labels remain untouched."""
    async def save(current):
        query = {**workspace_scope(workspace), "tags.0": {"$exists": True}, "id": {"$type": "string", "$gt": after_id}, "id.0": {"$exists": False}}
        rows = await current.outreach_inbox_threads.find(query).sort("id", 1).limit(101).to_list(length=101)
        definitions_by_id = await active_tag_map(current, workspace, include_archived=True)
        definitions_by_name = {clean_tag_name(tag["name"])[1]: tag for tag in definitions_by_id.values()}
        processed, skipped, visited, label_work = 0, [], [], 0
        for thread in rows[:100]:
            lead_id, names = thread.get("lead_id"), thread.get("tags")
            work = min(len(names), MAX_TAGS_PER_LEAD) if isinstance(names, list) else 1
            if visited and label_work + work > MAX_MIGRATION_LABELS:
                break
            label_work += work
            visited.append(thread)
            if not isinstance(lead_id, str) or not lead_id:
                skipped.append({"thread_id": thread["id"], "reason": "No linked CRM lead"})
                continue
            try:
                exact_thread = await unique_resource(current.outreach_inbox_threads, workspace, thread["id"])
                lead = await unique_resource(current.outreach_leads, workspace, lead_id)
                if not exact_thread or not lead or not isinstance(names, list) or len(names) > MAX_TAGS_PER_LEAD or any(not isinstance(name, str) for name in names):
                    raise HTTPException(409, "Linked lead or labels require review")
                normalized_names = dict(clean_tag_name(name)[::-1] for name in names)
                ids = stored_ids(lead)
                stored_revision(lead)
            except HTTPException:
                skipped.append({"thread_id": thread["id"], "reason": "Labels require review"})
                continue
            definitions = []
            for normalized, display in normalized_names.items():
                tag = definitions_by_name.get(normalized)
                definitions.append((display, tag))
            if (any(tag is not None and tag["archived"] for _, tag in definitions)
                    or len(ids) + sum(tag is None or tag.get("id") not in ids for _, tag in definitions) > MAX_TAGS_PER_LEAD
                    or len(definitions_by_id) + sum(tag is None for _, tag in definitions) > MAX_WORKSPACE_TAGS):
                skipped.append({"thread_id": thread["id"], "reason": "Archived tag or lead tag limit requires review"})
                continue
            for display, tag in definitions:
                if tag is None:
                    old = await current.outreach_inbox_tags.find_one({**workspace_scope(workspace), "name": display})
                    color = old.get("color") if old else None
                    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                        color = "#6366f1"
                    tag = await create_tag(current, workspace, actor, display, color)
                    definitions_by_name[clean_tag_name(display)[1]] = tag
                    definitions_by_id[tag["id"]] = tag
                if tag["id"] not in ids:
                    ids = [*ids, tag["id"]]
            now = datetime.now(timezone.utc)
            if ids != stored_ids(lead):
                assigned = await current.outreach_leads.update_one(assignment_scope(workspace, lead), {
                    "$set": {"tag_ids": ids, "tags_updated_at": now}, "$inc": {"tag_revision": 1}})
                if assigned.matched_count != 1:
                    raise HTTPException(409, "Linked lead changed; reload before importing")
            result = await current.outreach_inbox_threads.update_one({**captured_scope(workspace, thread), "tags": names, "lead_id": lead_id}, {
                "$unset": {"tags": ""}, "$set": {"legacy_tag_migration": {"original_names": names, "lead_id": lead_id, "at": now}}})
            if result.matched_count != 1:
                raise HTTPException(409, "Legacy labels changed; reload before importing")
            processed += 1
        return {"migrated_threads": processed, "skipped": skipped, "has_more": len(rows) > len(visited),
                "next_after_id": visited[-1]["id"] if visited else after_id}

    return await _commit(db, workspace, save)
