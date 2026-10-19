"""Reviewed, database-only custom-template name/description edits.

The shared transaction writes current authority counters and the template row.
The shared replacement appends minimal immutable revision checkpoints. The
legacy PATCH has no durable outcome receipt; the recoverable update service
owns its separate atomic receipt. Unknown legacy
commits must be inspected, never automatically replayed with a newer review.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

from bson import BSON
from fastapi import HTTPException

from outreach.core import template_governance as governance
from outreach.core.authorization import canonical_hash
from outreach.core.lead_tags import unique_resource
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.workspace_scope import workspace_scope
from outreach.core.template_revision_checkpoints import append_metadata_checkpoints


def validate_metadata(name: str, description: str) -> tuple[str, str]:
    """Accept exact bounded Unicode text, without coercion or normalization."""
    if (type(name) is not str or not name.strip() or len(name) > 100
            or type(description) is not str or len(description) > 1000
            or '\x00' in name or '\x00' in description):
        raise HTTPException(422, 'Template name and description need valid bounded text')
    try:
        name.encode('utf-8'); description.encode('utf-8')
    except UnicodeEncodeError:
        raise HTTPException(422, 'Template text must contain valid Unicode') from None
    return name, description


def metadata_scope(workspace: str, actor: str, authenticated_uid: str) -> str:
    """Bind this edit review to its original actor and resolved workspace."""
    if any(type(value) is not str or not value.strip() or not 1 <= len(value) <= 200
           for value in (workspace, actor, authenticated_uid)):
        raise HTTPException(403, 'Template access is unavailable')
    return canonical_hash(['template-metadata-scope-v1', workspace, actor, authenticated_uid])


def metadata_review(row: dict, workspace: str, actor: str, authenticated_uid: str) -> dict:
    """Pure metadata from the original full BSON row; never update authority."""
    unavailable = {'contract_version': 1, 'reviewable': False, 'workspace_id': workspace,
        'revision': None, 'identity_digest': None, 'review_digest': None, 'scope_digest': None,
        'update_authorized': False, 'execution_authorized': False}
    try:
        scope = metadata_scope(workspace, actor, authenticated_uid)
        validate_metadata(row.get('name'), row.get('description', ''))
        review = governance.template_review(row, workspace)
        if (not review['reviewable'] or review['revision'] >= governance.MAX_REVISION
                or any(type(row.get(key)) is not str for key in ('id', 'workspace_id', 'user_id'))):
            return unavailable
    except (HTTPException, AttributeError, TypeError):
        return unavailable
    return {**unavailable, 'reviewable': True, 'revision': review['revision'],
        'identity_digest': review['identity_digest'], 'review_digest': review['review_digest'], 'scope_digest': scope}


def prepare_metadata_update(workspace: str, actor: str, authenticated_uid: str, template_id: str,
                            revision: int, review_digest: str, identity_digest: str,
                            name: str, description: str, scope_digest: str) -> dict:
    """Validate one original metadata edit independently of transaction ownership."""
    name, description = validate_metadata(name, description)
    if (type(template_id) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', template_id)
            or type(revision) is not int or not 0 <= revision < governance.MAX_REVISION
            or any(type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value)
                   for value in (review_digest, identity_digest, scope_digest))):
        raise HTTPException(422, 'A current template metadata review is required')
    if scope_digest != metadata_scope(workspace, actor, authenticated_uid):
        raise HTTPException(403, 'Template account or workspace changed; reload before editing')
    return {'contract_version': 1, 'workspace_id': workspace, 'revision': revision,
        'review_digest': review_digest, 'identity_digest': identity_digest, 'scope_digest': scope_digest,
        'template_id': template_id, 'name': name, 'description': description}


async def _replace_metadata(current: Any, workspace: str, actor: str, authenticated_uid: str,
                            operation: dict, timestamp: datetime) -> dict:
    """Apply within the caller's shared transaction after its authority fence.

    Both callers validate the original operation, acquire the workspace guard
    and authorize_update before invoking this helper. Failures propagate to the
    owning transaction, including a later historical-receipt insertion failure.
    """
    template_id = operation['template_id']
    original_review = {key: operation[key] for key in ('contract_version', 'workspace_id',
        'revision', 'review_digest', 'identity_digest', 'scope_digest')}
    row = await unique_resource(current.outreach_templates, workspace, template_id)
    if row is None:
        raise HTTPException(404, 'Reviewed template is unavailable; reload before editing')
    reviewed = metadata_review(row, workspace, actor, authenticated_uid)
    if not reviewed['reviewable'] or any(reviewed[key] != value for key, value in original_review.items()):
        raise HTTPException(409, 'Template changed; reload before editing')
    fields = {'name': operation['name'], 'description': operation['description'],
        'template_revision': operation['revision'] + 1,
        'metadata_updated_at': timestamp, 'metadata_updated_by': actor}
    expected = {**deepcopy(row), **fields}
    raw_review = governance.template_review(expected, workspace)
    if not raw_review['reviewable']:
        raise HTTPException(422, 'Updated template record exceeds the supported bound')
    query = {**workspace_scope(workspace), 'id': template_id, '_id': row['_id'],
        '$expr': {'$eq': ['$$ROOT', {'$literal': deepcopy(row)}]}}
    changed = await current.outreach_templates.replace_one(query, deepcopy(expected))
    if changed.matched_count != 1:
        raise HTTPException(409, 'Template changed; reload before editing')
    saved = await current.outreach_templates.find_one({**workspace_scope(workspace), '_id': row['_id']})
    if saved is None or BSON.encode(saved) != BSON.encode(expected):
        raise HTTPException(409, 'Could not verify updated template; reload before editing')
    await append_metadata_checkpoints(current, row, saved, actor, timestamp)
    from outreach.core.template_mutation_snapshots import capture_mutation
    await capture_mutation(current, (row, saved), actor, authenticated_uid, timestamp, event='metadata')
    return {**original_review, 'status': 'updated', 'template_id': template_id,
        'name': operation['name'], 'description': operation['description'],
        'new_revision': operation['revision'] + 1, 'new_review_digest': raw_review['review_digest']}


async def update_metadata(db: Any, workspace: str, actor: str, template_id: str,
                          revision: int, review_digest: str, identity_digest: str,
                          name: str, description: str, *, authenticated_uid: str, scope_digest: str) -> dict:
    """CAS one original native template and fence current role/UID/erasure."""
    operation = prepare_metadata_update(workspace, actor, authenticated_uid, template_id,
        revision, review_digest, identity_digest, name, description, scope_digest)
    now = datetime.now(timezone.utc)
    timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)

    async def update(current):
        await governance.authorize_update(current, actor, authenticated_uid)
        return await _replace_metadata(current, workspace, actor, authenticated_uid, operation, timestamp)

    try:
        return await mutate_suppression(db, workspace, update)
    except SuppressionUnavailable:
        raise HTTPException(503, 'Could not confirm template update. Reload and review before another edit.') from None
