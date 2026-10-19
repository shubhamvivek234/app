"""Atomic custom-template creation and reference-only historical save receipts.

Status reads fence current authority with counter writes in the shared guard.
Receipts prove this application's recorded creation, not current existence,
provider outcomes, content approval or permission to execute a sequence.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Callable

from bson import BSON, ObjectId
from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.template_governance import review_scope, template_review, authorize_create
from outreach.core.lead_tags import unique_resource
from outreach.core.workspace_scope import workspace_scope
from outreach.core.template_revision_checkpoints import append_creation_checkpoint

UUID_PATTERN = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
HEX_PATTERN = r'[0-9a-f]{64}'
MAX_INPUT_BYTES = 1_048_576
PUBLIC_FIELDS = ('contract_version', 'workspace_id', 'request_id', 'scope_digest',
    'input_digest', 'status', 'template_id', 'template_revision',
    'template_identity_digest', 'template_review_digest')
RECORD_FIELDS = frozenset(PUBLIC_FIELDS) | {'_id', 'actor_id', 'created_at'}


def input_digest(content_json: str) -> str:
    """Bind the exact original UTF-8 JSON serialization, including whitespace."""
    if not isinstance(content_json, str) or not content_json:
        raise HTTPException(422, 'A template save input is required')
    try:
        encoded = content_json.encode('utf-8')
    except UnicodeError:
        raise HTTPException(422, 'Template save input is invalid') from None
    if len(encoded) > MAX_INPUT_BYTES:
        raise HTTPException(422, 'Template save input exceeds 1MB')
    return hashlib.sha256(encoded).hexdigest()


def save_context(workspace: str, actor: str, uid: str) -> dict:
    """Read-only correlation metadata; mutation/status still recheck authority."""
    if any(type(value) is not str for value in (workspace, actor, uid)):
        raise HTTPException(403, 'Template save access is unavailable')
    review_scope(workspace, actor, uid)
    return {'contract_version': 1, 'workspace_id': workspace,
        'scope_digest': canonical_hash(['template-save-scope-v1', workspace, actor, uid]),
        'execution_authorized': False}


def control_scope(workspace: str, actor: str, uid: str, request_id: str) -> dict:
    context = save_context(workspace, actor, uid)
    if not isinstance(request_id, str) or not re.fullmatch(UUID_PATTERN, request_id):
        raise HTTPException(422, 'A valid original save reference is required')
    return {'_id': canonical_hash(['template-save-v1', context['scope_digest'], request_id]),
        'workspace_id': workspace, 'actor_id': actor, 'request_id': request_id,
        'scope_digest': context['scope_digest']}


def public_receipt(row: dict, scope: dict) -> dict:
    """Validate recorded scope and schema before disclosing a minimal receipt."""
    if (not isinstance(row, dict) or set(row) != RECORD_FIELDS
            or any(type(row.get(key)) is not str or row[key] != value for key, value in scope.items())
            or type(row.get('contract_version')) is not int or row['contract_version'] != 1
            or type(row.get('template_revision')) is not int or row['template_revision'] != 1
            or type(row.get('status')) is not str or row['status'] != 'saved'
            or type(row.get('template_id')) is not str
            or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', row['template_id'])
            or any(type(row.get(key)) is not str or not re.fullmatch(HEX_PATTERN, row[key])
                   for key in ('input_digest', 'template_identity_digest', 'template_review_digest'))
            or not isinstance(row.get('created_at'), datetime)
            or row['created_at'].microsecond % 1000 != 0
            or row['created_at'].utcoffset() not in (None, timezone.utc.utcoffset(None))):
        raise HTTPException(503, 'Saved template status needs review; keep its original reference')
    return {key: row[key] for key in PUBLIC_FIELDS}


async def _commit(db: Any, workspace: str, operation: Callable) -> dict:
    if db is None:
        raise HTTPException(503, 'Template save status is unavailable')
    try:
        return await mutate_suppression(db, workspace, operation)
    except SuppressionUnavailable:
        raise HTTPException(503, 'Template save is unconfirmed. Check its original save status before saving again.') from None


def _verify_scope(workspace: str, actor: str, uid: str, scope_digest: str) -> None:
    if scope_digest != save_context(workspace, actor, uid)['scope_digest']:
        raise HTTPException(403, 'Template save account or workspace changed')


async def inspect_save(db: Any, workspace: str, actor: str, uid: str,
                       request_id: str, scope_digest: str) -> dict:
    """Recover only the original receipt under current creation permission."""
    _verify_scope(workspace, actor, uid, scope_digest)
    scope = control_scope(workspace, actor, uid, request_id)

    async def inspect(current):
        await authorize_create(current, actor, uid)
        row = await current.outreach_template_saves.find_one({**scope, **workspace_scope(workspace)})
        if row is None:
            raise HTTPException(404, 'Save is still unconfirmed. Keep the original reference and check again.')
        return public_receipt(row, scope)

    return await _commit(db, workspace, inspect)


async def save_template(db: Any, workspace: str, actor: str, uid: str, request_id: str,
                        scope_digest: str, content_json: str, expected_digest: str,
                        build: Callable[[], dict]) -> dict:
    """Commit creation and receipt together; original replay never recreates it.

Compilation runs only for a new request. A completed original receipt survives
compiler upgrades and later deletion. Unknown transaction outcomes are held;
the browser can explicitly read status without replaying this callback.
"""
    _verify_scope(workspace, actor, uid, scope_digest)
    scope = control_scope(workspace, actor, uid, request_id)
    digest = input_digest(content_json)
    if digest != expected_digest:
        raise HTTPException(422, 'Template save input changed')
    prepared = None

    async def save(current):
        nonlocal prepared
        await authorize_create(current, actor, uid)
        previous = await current.outreach_template_saves.find_one({**scope, **workspace_scope(workspace)})
        if previous is not None:
            receipt = public_receipt(previous, scope)
            if receipt['input_digest'] != digest:
                raise HTTPException(409, 'This save reference already belongs to different content')
            return receipt
        if prepared is None:
            prepared = {**deepcopy(build()), '_id': ObjectId(), 'template_revision': 1}
        expected_review = template_review(prepared, workspace)
        if not expected_review['reviewable'] or prepared.get('user_id') != actor:
            raise HTTPException(422, 'A valid custom template is required')
        if await unique_resource(current.outreach_templates, workspace, prepared['id']) is not None:
            raise HTTPException(409, 'Template identity is already in use; keep this save reference')
        await current.outreach_templates.insert_one(deepcopy(prepared))
        stored = await current.outreach_templates.find_one({**workspace_scope(workspace), '_id': prepared['_id']})
        review = template_review(stored, workspace)
        if stored is None or BSON.encode(stored) != BSON.encode(prepared) or review != expected_review:
            raise HTTPException(503, 'Stored template needs review; keep this save reference')
        now = datetime.now(timezone.utc)
        timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
        await append_creation_checkpoint(current, stored, actor, timestamp)
        row = {**scope, 'contract_version': 1, 'input_digest': digest, 'status': 'saved',
            'template_id': prepared['id'], 'template_revision': 1,
            'template_identity_digest': review['identity_digest'], 'template_review_digest': review['review_digest'],
            'created_at': timestamp}
        await current.outreach_template_saves.insert_one(row)
        stored_receipt = await current.outreach_template_saves.find_one({**scope, **workspace_scope(workspace)})
        receipt = public_receipt(stored_receipt, scope)
        if BSON.encode(stored_receipt) != BSON.encode(row):
            raise HTTPException(503, 'Stored template save changed; keep its original reference')
        return receipt

    return await _commit(db, workspace, save)
