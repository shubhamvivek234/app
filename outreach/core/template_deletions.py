"""Atomic reviewed deletions and minimal historical outcome receipts.

Mutation, retry and status all write current authority/guard counters. A receipt
confirms an original recorded application deletion, not current template state,
immutable content history, a provider outcome or execution authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable

from bson import BSON, Int64
from fastapi import HTTPException

from outreach.core import template_governance as governance
from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.template_saves import UUID_PATTERN, HEX_PATTERN
from outreach.core.workspace_scope import workspace_scope

MAX_INPUT_BYTES = 8192
PUBLIC_FIELDS = ('contract_version', 'workspace_id', 'request_id', 'scope_digest', 'input_digest',
    'status', 'template_id', 'revision', 'review_digest', 'identity_digest', 'review_scope_digest',
)
RECORD_FIELDS = frozenset(PUBLIC_FIELDS) | {'_id', 'actor_id', 'created_at'}


def input_digest(content: str) -> str:
    """Stable envelope validation precedes any historical receipt lookup."""
    if type(content) is not str or not content:
        raise HTTPException(422, 'Original template deletion input is required')
    try:
        encoded = content.encode('utf-8')
    except UnicodeError:
        raise HTTPException(422, 'Template deletion input is invalid') from None
    if len(encoded) > MAX_INPUT_BYTES:
        raise HTTPException(422, 'Template deletion exceeds the supported input bound')
    return hashlib.sha256(encoded).hexdigest()


def deletion_context(workspace: str, actor: str, uid: str) -> dict:
    """Read-only correlation; all outcome reads still fence current authority."""
    governance.review_scope(workspace, actor, uid)
    return {'contract_version': 1, 'workspace_id': workspace,
        'scope_digest': canonical_hash(['template-deletion-scope-v1', workspace, actor, uid]),
        'execution_authorized': False}


def control_scope(workspace: str, actor: str, uid: str, request_id: str) -> dict:
    context = deletion_context(workspace, actor, uid)
    if type(request_id) is not str or not re.fullmatch(UUID_PATTERN, request_id):
        raise HTTPException(422, 'An original template deletion reference is required')
    return {'_id': canonical_hash(['template-deletion-v1', context['scope_digest'], request_id]),
        'workspace_id': workspace, 'actor_id': actor, 'request_id': request_id,
        'scope_digest': context['scope_digest']}


def _verify_scope(workspace: str, actor: str, uid: str, scope_digest: str, digest: str) -> None:
    if (type(scope_digest) is not str
            or scope_digest != deletion_context(workspace, actor, uid)['scope_digest']):
        raise HTTPException(403, 'Template deletion account or workspace changed')
    if type(digest) is not str or not re.fullmatch(HEX_PATTERN, digest):
        raise HTTPException(422, 'An exact original deletion input digest is required')


def prepare_deletion(content: str, workspace: str, actor: str, uid: str) -> dict:
    """Parse only a new original deletion; historical receipts precede policy."""
    input_digest(content)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate deletion key')
            result[key] = value
        return result
    try:
        data = json.loads(content, object_pairs_hook=pairs)
        fields = {'contract_version', 'workspace_id', 'revision', 'review_digest',
            'identity_digest', 'scope_digest', 'template_id'}
        if (type(data) is not dict or set(data) != fields
                or type(data['contract_version']) is not int or data['contract_version'] != 1
                or type(data['workspace_id']) is not str or data['workspace_id'] != workspace
                or type(data['template_id']) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', data['template_id'])
                or type(data['revision']) is not int or not 0 <= data['revision'] <= governance.MAX_REVISION
                or any(type(data[key]) is not str or not re.fullmatch(HEX_PATTERN, data[key])
                    for key in ('review_digest', 'identity_digest', 'scope_digest'))):
            raise ValueError('Unsupported deletion contract')
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, 'Template deletion needs its complete original review') from None
    if data['scope_digest'] != governance.review_scope(workspace, actor, uid):
        raise HTTPException(403, 'Template review account or workspace changed')
    return {key:value for key,value in data.items() if key not in {'contract_version', 'workspace_id'}}


def public_receipt(row: dict, scope: dict, expected_review_scope: str) -> dict:
    """Reject malformed historical records before disclosing reference-only data."""
    if (type(row) is not dict or set(row) != RECORD_FIELDS
            or any(type(row.get(key)) is not str or row[key] != value for key,value in scope.items())
            or type(row.get('contract_version')) is not int or row['contract_version'] != 1
            or type(row.get('status')) is not str or row['status'] != 'deleted'
            or type(row.get('template_id')) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', row['template_id'])
            or any(type(row.get(key)) is not str or not re.fullmatch(HEX_PATTERN, row[key])
                for key in ('input_digest', 'review_digest', 'identity_digest', 'review_scope_digest'))
            or row['review_scope_digest'] != expected_review_scope
            or type(row.get('revision')) not in {int, Int64} or not 0 <= row['revision'] <= governance.MAX_REVISION
            or type(row.get('created_at')) is not datetime or row['created_at'].microsecond % 1000
            or row['created_at'].utcoffset() not in (None, timezone.utc.utcoffset(None))):
        raise HTTPException(503, 'Original template deletion status needs review; retain its reference')
    return {key:row[key] for key in PUBLIC_FIELDS}


async def _commit(db: Any, workspace: str, operation: Callable) -> dict:
    if db is None:
        raise HTTPException(503, 'Original template deletion status is unavailable')
    try:
        return await mutate_suppression(db, workspace, operation)
    except SuppressionUnavailable:
        raise HTTPException(503, 'Template deletion is unconfirmed. Check its original deletion status.') from None


async def inspect_deletion(db: Any, workspace: str, actor: str, uid: str,
                         request_id: str, scope_digest: str, expected_digest: str) -> dict:
    """Read a historical result under current deletion/UID/erasure authority."""
    _verify_scope(workspace, actor, uid, scope_digest, expected_digest)
    scope = control_scope(workspace, actor, uid, request_id)
    async def inspect(current):
        await governance.authorize_delete(current, actor, uid)
        row = await current.outreach_template_deletions.find_one({**scope, **workspace_scope(workspace)})
        if row is None:
            raise HTTPException(404, 'Deletion remains unconfirmed. Retain the original reference and check again.')
        receipt = public_receipt(row, scope, governance.review_scope(workspace, actor, uid))
        if receipt['input_digest'] != expected_digest:
            raise HTTPException(409, 'Original deletion reference belongs to different input')
        return receipt
    return await _commit(db, workspace, inspect)


async def save_deletion(db: Any, workspace: str, actor: str, uid: str, request_id: str,
                      scope_digest: str, content_json: str, expected_digest: str) -> dict:
    """Commit original native deletion and minimal historical receipt together."""
    _verify_scope(workspace, actor, uid, scope_digest, expected_digest)
    scope = control_scope(workspace, actor, uid, request_id)
    digest = input_digest(content_json)
    if digest != expected_digest:
        raise HTTPException(422, 'Template deletion input changed')
    async def update(current):
        await governance.authorize_delete(current, actor, uid)
        previous = await current.outreach_template_deletions.find_one({**scope, **workspace_scope(workspace)})
        if previous is not None:
            receipt = public_receipt(previous, scope, governance.review_scope(workspace, actor, uid))
            if receipt['input_digest'] != digest:
                raise HTTPException(409, 'Original deletion reference belongs to different input')
            return receipt
        operation = prepare_deletion(content_json, workspace, actor, uid)
        now = datetime.now(timezone.utc)
        timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
        result = await governance._remove_reviewed(current, workspace, **operation,
            actor=actor, authenticated_uid=uid, timestamp=timestamp)
        row = {**scope, 'contract_version': 1, 'input_digest': digest, 'status': 'deleted',
            **{key:result[key] for key in ('template_id', 'revision', 'review_digest', 'identity_digest')},
            'review_scope_digest': operation['scope_digest'], 'created_at': timestamp}
        await current.outreach_template_deletions.insert_one(row)
        stored = await current.outreach_template_deletions.find_one({**scope, **workspace_scope(workspace)})
        receipt = public_receipt(stored, scope, governance.review_scope(workspace, actor, uid))
        if BSON.encode(stored) != BSON.encode(row):
            raise HTTPException(503, 'Stored template deletion changed; retain its original reference')
        return receipt
    return await _commit(db, workspace, update)
