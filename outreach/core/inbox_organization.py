"""Workspace-shared conversation organization, independent of reply authority."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any

from bson import Int64
from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.lead_lists import physical_digest
from outreach.core.lead_tags import captured_scope, unique_resource
from outreach.core.suppression import SuppressionDatabase, SuppressionUnavailable, mutate_suppression
from outreach.core.workspace_scope import workspace_scope
from utils.roles import has_permission

MAX_REVISION = 2**53 - 1  # Exact JSON/browser integer; no floating-point revisions.
FIELDS = ("is_starred", "is_archived", "note")
IDENTITIES = ("workspace_id", "id", "account_id", "channel", "conversation_urn", "lead_urn")


def validate_changes(changes: dict) -> dict:
    """Explicit booleans and bounded plain text; empty note clears the note."""
    if not changes or set(changes) - set(FIELDS):
        raise HTTPException(422, "Choose a star, archive or note change")
    for field, value in changes.items():
        if field != "note":
            valid = type(value) is bool
        else:
            valid = (isinstance(value, str) and len(value) <= 4000
                and not any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in value))
        if not valid:
            raise HTTPException(422, "Use booleans and a note of at most 4,000 text characters")
    return dict(changes)


def _metadata(row: dict) -> dict:
    if "inbox_organization" not in row:
        return {"revision": 0, "is_starred": False, "is_archived": False, "note": ""}
    saved = row["inbox_organization"]
    if (not isinstance(saved, dict) or type(saved.get("revision")) not in {int, Int64}
            or not 1 <= saved["revision"] <= MAX_REVISION
            or set(saved) - {"revision", *FIELDS, "updated_at", "updated_by"}):
        raise HTTPException(409, "Conversation organization needs review")
    if "updated_at" in saved:
        stamp = saved["updated_at"]
        if not isinstance(stamp, datetime) or stamp.tzinfo is not None and stamp.utcoffset().total_seconds() != 0:
            raise HTTPException(409, "Conversation organization needs review")
    if "updated_by" in saved and (not isinstance(saved["updated_by"], str) or not 1 <= len(saved["updated_by"].strip()) <= 200):
        raise HTTPException(409, "Conversation organization needs review")
    validate_changes({key: saved.get(key) for key in FIELDS})
    return {**{key: saved[key] for key in FIELDS}, "revision": int(saved["revision"])}


def _identity(row: dict) -> str:
    if row.get("_id") is None:
        raise HTTPException(409, "Conversation identity needs review")
    for field in IDENTITIES:
        value = row.get(field)
        if field in {"workspace_id", "id", "account_id"}:
            valid = isinstance(value, str) and bool(value.strip()) and len(value) <= 200
        else:
            valid = value is None or isinstance(value, str) and len(value) <= 1000
        if not valid:
            raise HTTPException(409, "Conversation identity needs review")
    if (row["account_id"] in {"all", "All"} or (row.get("channel") is not None and row.get("channel") != "linkedin")
            or not any(isinstance(row.get(key), str) and row[key].strip() for key in ("conversation_urn", "lead_urn"))):
        raise HTTPException(409, "Conversation identity needs review")
    return canonical_hash(["inbox-organization-identity-v1", physical_digest(row["_id"]),
        [(key, key in row, row.get(key)) for key in IDENTITIES]])


def public_organization(row: dict) -> dict:
    """Legacy absence is editable; malformed identities/metadata remain held."""
    try:
        metadata = _metadata(row)
        identity = _identity(row)
    except HTTPException:
        return {"editable": False, "review_digest": None, "identity_digest": None,
            "review_reason": "Conversation organization needs review", "revision": None,
            "is_starred": False, "is_archived": False, "note": ""}
    return {**metadata, "editable": True, "identity_digest": identity,
        "review_digest": canonical_hash(["inbox-organization-review-v1", identity, metadata]),
        "updated_at": (row.get("inbox_organization") or {}).get("updated_at")}


async def _authorize(current: SuppressionDatabase, actor: str, authenticated_uid: str | None) -> None:
    """Fence current user and member/owner rows in the metadata transaction."""
    if (not isinstance(actor, str) or not actor.strip()
            or not isinstance(authenticated_uid, str) or not 1 <= len(authenticated_uid.strip()) <= 200):
        raise HTTPException(403, "Inbox access is unavailable")
    database, session = current.database, current.session

    async def unique(collection, query):
        rows = await collection.find(query, session=session).limit(2).to_list(2)
        if len(rows) != 1:
            raise HTTPException(403, "Inbox access is unavailable")
        return rows[0]

    user_scope = {"user_id": actor, "user_id.0": {"$exists": False}}
    user = await unique(database.users, user_scope)
    if user.get("status", "active") != "active":
        raise HTTPException(403, "Inbox access is unavailable")
    uid = user.get("firebase_uid")
    if uid != authenticated_uid or uid is not None and (not isinstance(uid, str) or not uid.strip()):
        raise HTTPException(403, "Inbox access is unavailable")
    if uid and await database.account_erasure_tombstones.find_one(
            {"_id": canonical_hash(["firebase_identity", uid])}, session=session):
        raise HTTPException(403, "Inbox access is unavailable")
    member_scope = {**workspace_scope(current.workspace_id), **user_scope}
    members = await database.workspace_members.find(member_scope, session=session).limit(2).to_list(2)
    if len(members) > 1:
        raise HTTPException(403, "Inbox access is unavailable")
    if members:
        authority, collection, scope = members[0], database.workspace_members, member_scope
        try:
            allowed = authority.get("status", "active") == "active" and has_permission(authority.get("role"), "inbox:manage")
        except (ValueError, TypeError, KeyError):
            allowed = False
        if not allowed:
            raise HTTPException(403, "Inbox management permission is required")
    else:
        scope = {**workspace_scope(current.workspace_id), "owner_id": actor, "owner_id.0": {"$exists": False}}
        authority, collection = await unique(database.workspaces, scope), database.workspaces
    # Native writes cause a retry/denial if status, membership or ownership changes.
    for target, captured, query in ((database.users, user, user_scope), (collection, authority, scope)):
        query = {**query, "_id": captured["_id"], **{
            key: captured[key] if key in captured else {"$exists": False}
            for key in ("status", "role", "firebase_uid", "owner_id")}}
        changed = await target.update_one(query, {"$inc": {"inbox_metadata_authority_revision": 1}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(403, "Inbox access changed; reload before editing")


async def update_organization(db: Any, workspace: str, actor: str, thread_id: str,
                              revision: int, review_digest: str, changes: dict, *, authenticated_uid: str | None) -> dict:
    """Commit only local metadata, ordered with erasure and inbox suppression."""
    changes = validate_changes(changes)
    if (type(revision) is not int or not 0 <= revision < MAX_REVISION
            or not isinstance(review_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", review_digest)):
        raise HTTPException(422, "A current conversation review is required")

    async def save(current):
        await _authorize(current, actor, authenticated_uid)
        row = await unique_resource(current.outreach_inbox_threads, workspace, thread_id)
        if not row:
            raise HTTPException(404, "Conversation not found")
        public = public_organization(row)
        if not public["editable"] or public["revision"] != revision or public["review_digest"] != review_digest:
            raise HTTPException(409, "Conversation changed; reload before editing")
        saved = {**_metadata(row), **changes, "revision": revision + 1,
            "updated_at": datetime.now(timezone.utc), "updated_by": actor}
        query = {**captured_scope(workspace, row), **{
            key: row[key] if key in row else {"$exists": False} for key in (*IDENTITIES, "inbox_organization")}}
        changed = await current.outreach_inbox_threads.update_one(query, {"$set": {"inbox_organization": saved}})
        if changed.matched_count != 1:
            raise HTTPException(409, "Conversation changed; reload before editing")
        return {"thread_id": thread_id, "organization": public_organization({**row, "inbox_organization": saved})}

    try:
        return await mutate_suppression(db, workspace, save)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm the organization change. Reload before retrying.") from None


async def filtered_page(db: Any, workspace: str, query: dict, view: str, skip: int, limit: int) -> list[dict]:
    """Bounded metadata scan uses exactly the public schema for view admission.

    Corrupt organization remains in Inbox/All for review. Full message bodies
    are loaded only for the selected page. This is not a snapshot read or a
    strict byte bound on legacy records.
    """
    fields = {key: 1 for key in (*IDENTITIES, "inbox_organization")}
    candidates = await db.outreach_inbox_threads.find(query, fields).sort([
        ("last_message_at", -1), ("id", 1)]).limit(1001).to_list(1001)
    if len(candidates) > 1000:
        raise HTTPException(422, "This view covers more than 1,000 conversations. Narrow by sender, search or lead tag.")
    selected = []
    for row in candidates:
        public = public_organization(row)
        included = (not public["is_archived"] if view == "inbox" else
            public["is_starred"] and not public["is_archived"] if view == "starred" else public["is_archived"])
        if included:
            selected.append(row)
    page = selected[skip:skip + limit]
    if not page:
        return []
    rows = await db.outreach_inbox_threads.find({**workspace_scope(workspace), "$and": [query],
        "_id": {"$in": [row["_id"] for row in page]}}).to_list(limit)
    by_native = {physical_digest(row["_id"]): row for row in rows}
    result = []
    for candidate in page:
        row = by_native.get(physical_digest(candidate["_id"]))
        captured = [(key, key in candidate, candidate.get(key)) for key in (*IDENTITIES, "inbox_organization")]
        current = [(key, key in row, row.get(key)) for key in (*IDENTITIES, "inbox_organization")] if row else None
        if row is None or physical_digest(current) != physical_digest(captured):
            raise HTTPException(409, "Conversation view changed; reload the inbox")
        result.append(row)
    return result
