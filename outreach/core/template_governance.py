"""Native review and guarded custom-template deletion.

Pure review grants no authority. Saves and deletions fence current user/role
records and mutate templates inside the shared workspace transaction.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from bson import BSON, Int64, ObjectId
from bson.errors import BSONError
from fastapi import HTTPException

from outreach.core.workspace_scope import workspace_scope
from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionDatabase, SuppressionUnavailable, mutate_suppression
from outreach.core.lead_tags import unique_resource
from utils.roles import has_permission

MAX_REVISION = 2**53 - 1
MAX_RECORD_BYTES = 1_048_576


def template_review(row: dict, workspace: str) -> dict:
    """Bind review to the received native BSON record; legacy absence is zero.

    Encoding limits accepted record size after loading, not database read bytes.
    This fingerprint is neither a signature nor a deletion/execution grant.
    """
    unavailable = {"contract_version": 1, "reviewable": False, "revision": None,
                   "identity_digest": None, "review_digest": None,
                   "deletion_authorized": False, "execution_authorized": False}
    try:
        native = row.get("_id")
        revision = row.get("template_revision", 0)
        if (not isinstance(workspace, str) or not workspace.strip() or not 1 <= len(workspace) <= 200
                or row.get("workspace_id") != workspace
                or not isinstance(row.get("workspace_id"), str)
                or not (isinstance(native, ObjectId) or isinstance(native, str) and bool(native.strip()) and 1 <= len(native) <= 200)
                or not isinstance(row.get("id"), str) or not re.fullmatch(r"tpl_custom_[0-9a-f]{10}", row["id"])
                or row.get("is_custom") is not True
                or not isinstance(row.get("user_id"), str) or not row["user_id"].strip() or not 1 <= len(row["user_id"]) <= 200
                or type(revision) not in {int, Int64} or not 0 <= revision <= MAX_REVISION):
            return unavailable
        raw = BSON.encode(row)
        if len(raw) > MAX_RECORD_BYTES:
            return unavailable
    except (AttributeError, TypeError, ValueError, OverflowError, BSONError, RecursionError):
        return unavailable
    return {**unavailable, "reviewable": True, "revision": int(revision),
            "identity_digest": hashlib.sha256(BSON.encode({"_id": native, "workspace_id": workspace, "id": row["id"]})).hexdigest(),
            "review_digest": hashlib.sha256(raw).hexdigest()}


def review_scope(workspace: str, actor: str, authenticated_uid: str) -> str:
    """Correlate the original browser review to admitted actor/workspace/UID."""
    if any(not isinstance(value, str) or not value.strip() or not 1 <= len(value) <= 200
           for value in (workspace, actor, authenticated_uid)):
        raise HTTPException(403, "Template access is unavailable")
    return canonical_hash(["template-delete-scope-v1", workspace, actor, authenticated_uid])


def scoped_review(row: dict, workspace: str, actor: str, authenticated_uid: str) -> dict:
    """Read-only context metadata; deletion still requires current authority."""
    review = template_review(row, workspace)
    try:
        scope = review_scope(workspace, actor, authenticated_uid)
    except HTTPException:
        return {"contract_version": 1, "reviewable": False, "revision": None,
                "identity_digest": None, "review_digest": None, "scope_digest": None,
                "deletion_authorized": False, "execution_authorized": False}
    return {**review, "workspace_id": workspace, "scope_digest": scope}


def deletion_precondition(row: dict, workspace: str, revision: int, digest: str) -> dict[str, Any]:
    """Produce a literal full-record CAS after comparing the captured review.

    Mongo equality is not strict BSON-byte equality. The later transactional
    consumer must reread/compare the digest before this CAS and deny ambiguity.
    """
    if (type(revision) is not int or not 0 <= revision <= MAX_REVISION
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise HTTPException(422, "A current template review is required")
    review = template_review(row, workspace)
    if not review["reviewable"] or review["revision"] != revision or review["review_digest"] != digest:
        raise HTTPException(409, "Template changed; reload before deleting")
    return {**workspace_scope(workspace), "id": row["id"], "id.0": {"$exists": False},
            "_id": row["_id"], "$expr": {"$eq": ["$$ROOT", {"$literal": deepcopy(row)}]}}


async def _authorize(current: SuppressionDatabase, actor: str, authenticated_uid: str, permission: str) -> None:
    """Fence original identity and current role inside the caller transaction."""
    if (not isinstance(actor, str) or not actor.strip() or not 1 <= len(actor) <= 200
            or not isinstance(authenticated_uid, str) or not authenticated_uid.strip() or not 1 <= len(authenticated_uid) <= 200):
        raise HTTPException(403, "Template access is unavailable")
    database, session = current.database, current.session

    async def unique(collection, query):
        rows = await collection.find(query, session=session).limit(2).to_list(2)
        if len(rows) != 1:
            raise HTTPException(403, "Template access is unavailable")
        return rows[0]

    user_scope = {"user_id": actor, "user_id.0": {"$exists": False}}
    user = await unique(database.users, user_scope)
    if user.get("status", "active") != "active" or user.get("firebase_uid") != authenticated_uid:
        raise HTTPException(403, "Template access is unavailable")
    # Include malformed array aliases in this bounded ambiguity check. A
    # different public user ID with the same admitted UID must also deny.
    identity = await unique(database.users, {"firebase_uid": authenticated_uid})
    if identity["_id"] != user["_id"] or identity.get("firebase_uid") != authenticated_uid:
        raise HTTPException(403, "Template access is unavailable")
    if await database.account_erasure_tombstones.find_one(
            {"_id": canonical_hash(["firebase_identity", authenticated_uid])}, session=session):
        raise HTTPException(403, "Template access is unavailable")
    member_scope = {**workspace_scope(current.workspace_id), **user_scope}
    members = await database.workspace_members.find(member_scope, session=session).limit(2).to_list(2)
    if len(members) > 1:
        raise HTTPException(403, "Template access is unavailable")
    if members:
        authority, collection, scope = members[0], database.workspace_members, member_scope
        try:
            allowed = authority.get("status", "active") == "active" and has_permission(authority.get("role"), permission)
        except (ValueError, TypeError, KeyError):
            allowed = False
        if not allowed:
            raise HTTPException(403, "Template permission is required")
    else:
        scope = workspace_scope(current.workspace_id)
        authority, collection = await unique(database.workspaces, scope), database.workspaces
        if authority.get("status", "active") != "active" or authority.get("owner_id") != actor:
            raise HTTPException(403, "Template access is unavailable")
    for target, captured, query in ((database.users, user, user_scope), (collection, authority, scope)):
        exact = {**query, "_id": captured["_id"], **{
            key: captured[key] if key in captured else {"$exists": False}
            for key in ("status", "role", "firebase_uid", "owner_id")}}
        changed = await target.update_one(exact, {"$inc": {"template_authority_revision": 1}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(403, "Template access changed; reload before editing")


async def authorize_delete(current: SuppressionDatabase, actor: str, authenticated_uid: str) -> None:
    """Deletion authority is valid only inside the same workspace transaction."""
    await _authorize(current, actor, authenticated_uid, "sequence:delete")


async def authorize_create(current: SuppressionDatabase, actor: str, authenticated_uid: str) -> None:
    """Creation/status authority is valid only inside the caller transaction."""
    await _authorize(current, actor, authenticated_uid, "sequence:create")


async def authorize_update(current: SuppressionDatabase, actor: str, authenticated_uid: str) -> None:
    """Metadata editing authority is fenced inside the caller transaction."""
    await _authorize(current, actor, authenticated_uid, "sequence:update")


async def authorize_read(current: SuppressionDatabase, actor: str, authenticated_uid: str) -> None:
    """History reads fence current authority with counters and strict snapshot observations."""
    from outreach.core.template_access import inspect_access

    await _authorize(current, actor, authenticated_uid, 'sequence:read')
    await inspect_access(current.database, current.workspace_id, actor, authenticated_uid, session=current.session)


async def create_template(db: Any, workspace: str, actor: str, doc: dict, *, authenticated_uid: str) -> dict:
    """Coordinate new template insertions with deletion and erasure.

    This is not a durable client-request receipt or an idempotent save endpoint.
    The prepared public/native identity stays stable on definitely aborted
    database retries; unknown commits are not replayed by the shared guard.
    """
    # Checkpoints use this module's review contract; defer the reverse import.
    from outreach.core.template_revision_checkpoints import append_creation_checkpoint
    from outreach.core.template_mutation_snapshots import capture_mutation

    review_scope(workspace, actor, authenticated_uid)
    prepared = {**deepcopy(doc), "_id": ObjectId(), "template_revision": 1}
    if not template_review(prepared, workspace)["reviewable"] or prepared.get("user_id") != actor:
        raise HTTPException(422, "A valid custom template is required")

    async def save(current):
        await _authorize(current, actor, authenticated_uid, "sequence:create")
        if await unique_resource(current.outreach_templates, workspace, prepared["id"]) is not None:
            raise HTTPException(409, "Template identity already exists; reload before saving again")
        await current.outreach_templates.insert_one(deepcopy(prepared))
        stored = await current.outreach_templates.find_one({**workspace_scope(workspace), '_id': prepared['_id']})
        if stored is None or BSON.encode(stored) != BSON.encode(prepared):
            raise HTTPException(409, 'Could not verify saved template; reload before saving again')
        now = datetime.now(timezone.utc)
        timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
        await append_creation_checkpoint(current, stored, actor, timestamp)
        await capture_mutation(current, (stored,), actor, authenticated_uid, timestamp, event='created')
        return {key: value for key, value in prepared.items() if key != "_id"}

    try:
        return await mutate_suppression(db, workspace, save)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm template save. Reload templates before retrying.") from None


async def delete_template(db: Any, workspace: str, actor: str, template_id: str,
                          revision: int, review_digest: str, identity_digest: str, *,
                          authenticated_uid: str, scope_digest: str) -> dict:
    """Delete one reviewed native record without replaying unknown commits."""
    if (not isinstance(template_id, str) or not re.fullmatch(r"tpl_custom_[0-9a-f]{10}", template_id)
            or type(revision) is not int or not 0 <= revision <= MAX_REVISION
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in (review_digest, identity_digest, scope_digest))):
        raise HTTPException(422, "A current custom-template review is required")
    if scope_digest != review_scope(workspace, actor, authenticated_uid):
        raise HTTPException(403, "Template review account or workspace changed; reload before deleting")
    now = datetime.now(timezone.utc)
    timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)

    async def remove(current):
        await authorize_delete(current, actor, authenticated_uid)
        return await _remove_reviewed(current, workspace, template_id, revision, review_digest, identity_digest, scope_digest,
            actor=actor, authenticated_uid=authenticated_uid, timestamp=timestamp)

    try:
        return await mutate_suppression(db, workspace, remove)
    except SuppressionUnavailable:
        raise HTTPException(503, "Could not confirm template deletion. Reload before another deletion.") from None


async def _remove_reviewed(current: SuppressionDatabase, workspace: str, template_id: str,
                           revision: int, review_digest: str, identity_digest: str, scope_digest: str, *,
                           actor: str, authenticated_uid: str, timestamp: datetime) -> dict:
    """Caller fences current authority; deletion and digest terminal commit together."""
    # The checkpoint module uses this module's native review contract.
    from outreach.core.template_revision_checkpoints import append_deletion_checkpoints
    from outreach.core.template_mutation_snapshots import capture_mutation

    row = await unique_resource(current.outreach_templates, workspace, template_id)
    if row is None:
        raise HTTPException(404, "Reviewed template is unavailable; reload before another deletion")
    public = template_review(row, workspace)
    if public["identity_digest"] != identity_digest:
        raise HTTPException(409, "Template identity changed; reload before deleting")
    query = deletion_precondition(row, workspace, revision, review_digest)
    result = await current.outreach_templates.delete_one(query)
    if result.deleted_count != 1:
        raise HTTPException(409, "Template changed; reload before deleting")
    if await current.outreach_templates.find_one({**workspace_scope(workspace), '_id': row['_id']}) is not None:
        raise HTTPException(503, "Original template deletion is unconfirmed")
    await append_deletion_checkpoints(current, row, actor, timestamp)
    await capture_mutation(current, (row,), actor, authenticated_uid, timestamp, event='deleted')
    return {"contract_version": 1, "status": "deleted", "template_id": template_id,
            "workspace_id": workspace, "revision": revision, "review_digest": review_digest,
            "identity_digest": identity_digest, "scope_digest": scope_digest}
