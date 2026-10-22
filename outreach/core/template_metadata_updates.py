"""Atomic reviewed metadata updates and minimal historical outcome receipts.

Mutation, retry and status all write current authority/guard counters. A receipt
confirms an original recorded application update, not current template state,
immutable content history, a provider outcome or execution authority.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable

from bson import BSON, Int64
from fastapi import HTTPException

from outreach.core import template_metadata as metadata
from outreach.core import template_governance as governance
from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.template_saves import UUID_PATTERN, HEX_PATTERN
from outreach.core.workspace_scope import workspace_scope

MAX_INPUT_BYTES = 8192
PUBLIC_FIELDS = ('contract_version', 'workspace_id', 'request_id', 'scope_digest', 'input_digest',
    'status', 'template_id', 'revision', 'review_digest', 'identity_digest', 'review_scope_digest',
    'new_revision', 'new_review_digest')
RECORD_FIELDS = frozenset(PUBLIC_FIELDS) | {'_id', 'actor_id', 'created_at'}


def input_digest(content: str) -> str:
    """Stable envelope validation precedes any historical receipt lookup."""
    if type(content) is not str or not content:
        raise HTTPException(422, 'Original template update input is required')
    try:
        encoded = content.encode('utf-8')
    except UnicodeError:
        raise HTTPException(422, 'Template update input is invalid') from None
    if len(encoded) > MAX_INPUT_BYTES:
        raise HTTPException(422, 'Template update exceeds the supported input bound')
    return hashlib.sha256(encoded).hexdigest()


def update_context(workspace: str, actor: str, uid: str) -> dict:
    """Read-only correlation; all outcome reads still fence current authority."""
    metadata.metadata_scope(workspace, actor, uid)
    return {'contract_version': 1, 'workspace_id': workspace,
        'scope_digest': canonical_hash(['template-metadata-update-scope-v1', workspace, actor, uid]),
        'execution_authorized': False}


def control_scope(workspace: str, actor: str, uid: str, request_id: str) -> dict:
    context = update_context(workspace, actor, uid)
    if type(request_id) is not str or not re.fullmatch(UUID_PATTERN, request_id):
        raise HTTPException(422, 'An original template update reference is required')
    return {'_id': canonical_hash(['template-metadata-update-v1', context['scope_digest'], request_id]),
        'workspace_id': workspace, 'actor_id': actor, 'request_id': request_id,
        'scope_digest': context['scope_digest']}


def _verify_scope(workspace: str, actor: str, uid: str, scope_digest: str, digest: str) -> None:
    if (type(scope_digest) is not str
            or scope_digest != update_context(workspace, actor, uid)['scope_digest']):
        raise HTTPException(403, 'Template update account or workspace changed')
    if type(digest) is not str or not re.fullmatch(HEX_PATTERN, digest):
        raise HTTPException(422, 'An exact original update input digest is required')


def prepare_update(content: str, workspace: str, actor: str, uid: str) -> dict:
    """Version1 parser is used only when no original completed receipt exists."""
    input_digest(content)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate update key')
            result[key] = value
        return result
    try:
        data = json.loads(content, object_pairs_hook=pairs)
        fields = {'contract_version', 'workspace_id', 'revision', 'review_digest',
            'identity_digest', 'scope_digest', 'template_id', 'name', 'description'}
        if (type(data) is not dict or set(data) != fields
                or type(data['contract_version']) is not int or data['contract_version'] != 1
                or type(data['workspace_id']) is not str or data['workspace_id'] != workspace):
            raise ValueError('Unsupported update contract')
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, 'Template update input needs its complete original review') from None
    return metadata.prepare_metadata_update(workspace, actor, uid,
        **{key:value for key,value in data.items() if key not in {'contract_version', 'workspace_id'}})


def public_receipt(row: dict, scope: dict, expected_review_scope: str) -> dict:
    """Reject malformed historical records before disclosing reference-only data."""
    if (type(row) is not dict or set(row) != RECORD_FIELDS
            or any(type(row.get(key)) is not str or row[key] != value for key,value in scope.items())
            or type(row.get('contract_version')) is not int or row['contract_version'] != 1
            or type(row.get('status')) is not str or row['status'] != 'updated'
            or type(row.get('template_id')) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', row['template_id'])
            or any(type(row.get(key)) is not str or not re.fullmatch(HEX_PATTERN, row[key])
                for key in ('input_digest', 'review_digest', 'identity_digest', 'review_scope_digest', 'new_review_digest'))
            or row['review_scope_digest'] != expected_review_scope
            or type(row.get('revision')) not in {int, Int64} or not 0 <= row['revision'] < governance.MAX_REVISION
            or type(row.get('new_revision')) not in {int, Int64} or row['new_revision'] != row['revision'] + 1
            or type(row.get('created_at')) is not datetime or row['created_at'].microsecond % 1000
            or row['created_at'].utcoffset() not in (None, timezone.utc.utcoffset(None))):
        raise HTTPException(503, 'Original template update status needs review; retain its reference')
    return {key:row[key] for key in PUBLIC_FIELDS}


async def _commit(db: Any, workspace: str, operation: Callable) -> dict:
    if db is None:
        raise HTTPException(503, 'Original template update status is unavailable')
    try:
        return await mutate_suppression(db, workspace, operation)
    except SuppressionUnavailable:
        raise HTTPException(503, 'Template update is unconfirmed. Check its original update status.') from None


async def inspect_update(db: Any, workspace: str, actor: str, uid: str,
                         request_id: str, scope_digest: str, expected_digest: str) -> dict:
    """Read a historical result under current update/UID/erasure authority."""
    _verify_scope(workspace, actor, uid, scope_digest, expected_digest)
    scope = control_scope(workspace, actor, uid, request_id)
    async def inspect(current):
        await governance.authorize_update(current, actor, uid)
        row = await current.outreach_template_metadata_updates.find_one({**scope, **workspace_scope(workspace)})
        if row is None:
            raise HTTPException(404, 'Update remains unconfirmed. Retain the original reference and check again.')
        receipt = public_receipt(row, scope, metadata.metadata_scope(workspace, actor, uid))
        if receipt['input_digest'] != expected_digest:
            raise HTTPException(409, 'Original update reference belongs to different input')
        return receipt
    return await _commit(db, workspace, inspect)


async def save_update(db: Any, workspace: str, actor: str, uid: str, request_id: str,
                      scope_digest: str, content_json: str, expected_digest: str) -> dict:
    """Commit original metadata CAS and minimal historical receipt together."""
    _verify_scope(workspace, actor, uid, scope_digest, expected_digest)
    scope = control_scope(workspace, actor, uid, request_id)
    digest = input_digest(content_json)
    if digest != expected_digest:
        raise HTTPException(422, 'Template update input changed')
    async def update(current):
        await governance.authorize_update(current, actor, uid)
        previous = await current.outreach_template_metadata_updates.find_one({**scope, **workspace_scope(workspace)})
        if previous is not None:
            receipt = public_receipt(previous, scope, metadata.metadata_scope(workspace, actor, uid))
            if receipt['input_digest'] != digest:
                raise HTTPException(409, 'Original update reference belongs to different input')
            return receipt
        operation = prepare_update(content_json, workspace, actor, uid)
        now = datetime.now(timezone.utc)
        timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
        result = await metadata._replace_metadata(current, workspace, actor, uid, operation, timestamp)
        row = {**scope, 'contract_version': 1, 'input_digest': digest, 'status': 'updated',
            **{key:result[key] for key in ('template_id', 'revision', 'review_digest', 'identity_digest', 'new_revision', 'new_review_digest')},
            'review_scope_digest': operation['scope_digest'], 'created_at': timestamp}
        await current.outreach_template_metadata_updates.insert_one(row)
        stored = await current.outreach_template_metadata_updates.find_one({**scope, **workspace_scope(workspace)})
        receipt = public_receipt(stored, scope, metadata.metadata_scope(workspace, actor, uid))
        if BSON.encode(stored) != BSON.encode(row):
            raise HTTPException(503, 'Stored template update changed; retain its original reference')
        return receipt
    return await _commit(db, workspace, update)
