"""Append-only digest checkpoints for guarded creation, edits and deletion.

Observed baselines do not prove creation or complete history. No template
content, Firebase UID, restoration or execution authority is retained here.
The caller must already fence mutation authority in the shared transaction.
"""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timezone
import re
from typing import Any, NoReturn

from bson import BSON, Int64
from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionDatabase
from outreach.core.template_governance import MAX_REVISION, template_review
from outreach.core.workspace_scope import workspace_scope

FIELDS = frozenset({'_id', 'contract_version', 'workspace_id', 'template_id', 'identity_digest',
    'revision', 'review_digest', 'event', 'predecessor_revision', 'predecessor_review_digest', 'recorded_at', 'recorded_by'})
MAX_CHECKPOINTS = 1000


def _deny() -> NoReturn:
    raise HTTPException(409, 'Template revision checkpoints need review before editing')


def _hex(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _id(workspace: str, identity: str, revision: int) -> str:
    return canonical_hash(['template-revision-checkpoint-v1', workspace, identity, int(revision)])


def _deletion_id(workspace: str, identity: str, revision: int) -> str:
    return canonical_hash(['template-deletion-checkpoint-v1', workspace, identity, int(revision)])


def _deletion_digest(workspace: str, template_id: str, identity: str, revision: int, parent: str) -> str:
    return canonical_hash(['template-deletion-result-v1', workspace, template_id, identity, revision, parent])


def validate_checkpoint(row: dict, workspace: str, template_id: str, identity: str, revision: int) -> dict:
    """Validate stored native scalars and exact context without repairing them."""
    if (any(type(value) is not str for value in (workspace, template_id, identity))
            or type(revision) is not int or not 0 <= revision <= MAX_REVISION):
        _deny()
    if (type(row) is not dict or set(row) != FIELDS
            or type(row.get('contract_version')) is not int or row['contract_version'] != 1
            or any(type(row.get(key)) is not str or row[key] != value for key, value in (
                ('workspace_id', workspace), ('template_id', template_id), ('identity_digest', identity)))
            or not _hex(identity) or not 1 <= len(workspace) <= 200 or not workspace.strip()
            or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', template_id)
            or type(row.get('revision')) not in {int, Int64} or not 0 <= row['revision'] <= MAX_REVISION
            or row['revision'] != revision or not _hex(row.get('review_digest'))
            or type(row.get('_id')) is not str
            or row['_id'] != (_deletion_id(workspace, identity, revision) if row.get('event') == 'deleted' else _id(workspace, identity, revision))
            or type(row.get('event')) is not str or row['event'] not in {'observed', 'created', 'metadata', 'graph', 'deleted'}
            or type(row.get('recorded_by')) is not str or not row['recorded_by'].strip() or len(row['recorded_by']) > 200
            or type(row.get('recorded_at')) is not datetime or row['recorded_at'].microsecond % 1000
            or row['recorded_at'].utcoffset() not in (None, timezone.utc.utcoffset(None))):
        _deny()
    if row['event'] in {'observed', 'created'}:
        if (row['predecessor_revision'] is not None or row['predecessor_review_digest'] is not None
                or row['event'] == 'created' and revision != 1):
            _deny()
    elif row['event'] == 'deleted':
        if (type(row['predecessor_revision']) not in {int, Int64} or row['predecessor_revision'] != revision
                or not _hex(row['predecessor_review_digest'])
                or row['review_digest'] != _deletion_digest(workspace, template_id, identity, revision, row['predecessor_review_digest'])):
            _deny()
    elif (revision < 1 or type(row['predecessor_revision']) not in {int, Int64}
            or row['predecessor_revision'] != revision - 1 or not _hex(row['predecessor_review_digest'])):
        _deny()
    return row


def checkpoint_for(row: dict, actor: str, timestamp: datetime, *, predecessor: dict | None = None,
                   event: str | None = None) -> dict:
    review = template_review(row, row.get('workspace_id'))
    if not review['reviewable'] or any(type(row.get(key)) is not str for key in ('workspace_id', 'id', 'user_id')):
        _deny()
    selected_event = ('metadata' if predecessor is not None else 'observed') if event is None else event
    if (type(selected_event) is not str or selected_event not in {'observed', 'created', 'metadata', 'graph'}
            or (selected_event in {'metadata', 'graph'}) != (predecessor is not None)):
        _deny()
    previous = None
    if predecessor is not None:
        previous = template_review(predecessor, row['workspace_id'])
        if (not previous['reviewable'] or previous['identity_digest'] != review['identity_digest']
                or previous['revision'] + 1 != review['revision']):
            _deny()
    value = {'_id': _id(row['workspace_id'], review['identity_digest'], review['revision']), 'contract_version': 1,
        'workspace_id': row['workspace_id'], 'template_id': row['id'], 'identity_digest': review['identity_digest'],
        'revision': review['revision'], 'review_digest': review['review_digest'],
        'event': selected_event, 'recorded_at': timestamp, 'recorded_by': actor,
        'predecessor_revision': previous['revision'] if previous else None,
        'predecessor_review_digest': previous['review_digest'] if previous else None}
    return validate_checkpoint(value, row['workspace_id'], row['id'], review['identity_digest'], review['revision'])


def deletion_checkpoint_for(row: dict, actor: str, timestamp: datetime) -> dict:
    """Bind a terminal outcome to the original; it is not a content revision."""
    baseline = checkpoint_for(row, actor, timestamp)
    workspace, template_id, identity, revision = (baseline[k] for k in ('workspace_id', 'template_id', 'identity_digest', 'revision'))
    value = {**baseline, '_id': _deletion_id(workspace, identity, revision), 'event': 'deleted',
        'predecessor_revision': revision, 'predecessor_review_digest': baseline['review_digest'],
        'review_digest': _deletion_digest(workspace, template_id, identity, revision, baseline['review_digest'])}
    return validate_checkpoint(value, workspace, template_id, identity, revision)


def _require_transaction(current: SuppressionDatabase, row: dict) -> None:
    if (not isinstance(current, SuppressionDatabase) or current.session is None
            or current.session.in_transaction is not True or type(row) is not dict
            or row.get('workspace_id') != current.workspace_id):
        _deny()


async def _insert_verified(current: SuppressionDatabase, value: dict) -> None:
    await current.outreach_template_revisions.insert_one(value)
    stored = await current.outreach_template_revisions.find_one({**workspace_scope(current.workspace_id), '_id': value['_id']})
    if stored is None or BSON.encode(stored) != BSON.encode(value):
        _deny()


async def append_creation_checkpoint(current: SuppressionDatabase, row: dict,
                                      actor: str, timestamp: datetime) -> None:
    """Record an actually inserted, read-back revision one; never backfill it."""
    _require_transaction(current, row)
    value = checkpoint_for(row, actor, timestamp, event='created')
    scope = {**workspace_scope(current.workspace_id), 'identity_digest': value['identity_digest']}
    # Any same-native history, even malformed, contradicts a new creation.
    if MAX_CHECKPOINTS < 1 or await current.outreach_template_revisions.find(scope).limit(1).to_list(1):
        _deny()
    await _insert_verified(current, value)


async def _append_result(current: SuppressionDatabase, before: dict, result: dict,
                         actor: str, timestamp: datetime) -> None:
    """Record a verified original/replacement inside its owning transaction.

    Only absent baseline/result rows are inserted. A known baseline is preserved
    byte-for-byte; differing hashes or future/malformed records hold restored data.
    """
    _require_transaction(current, before)
    baseline = checkpoint_for(before, actor, timestamp)
    collection = current.outreach_template_revisions
    # Inspect identity independently of redundant public ID and revision types.
    # The cap bounds returned rows after reading, not scanned work or BSON bytes.
    scope = {**workspace_scope(current.workspace_id), 'identity_digest': baseline['identity_digest']}
    retained = await collection.find(scope).limit(MAX_CHECKPOINTS + 1).to_list(MAX_CHECKPOINTS + 1)
    if len(retained) > MAX_CHECKPOINTS:
        _deny()
    by_revision = {}
    for item in retained:
        if type(item) is not dict or type(item.get('revision')) not in {int, Int64}:
            _deny()
        revision = int(item['revision'])
        validate_checkpoint(item, current.workspace_id, baseline['template_id'], baseline['identity_digest'], revision)
        # A terminal may intentionally share its parent's revision. Any such
        # history holds a restored native record, even at a newer revision.
        if item['event'] == 'deleted' or revision > baseline['revision'] or revision in by_revision:
            _deny()
        by_revision[revision] = item
    if any(item['event'] == 'created' for item in retained) and 0 in by_revision:
        _deny()
    for item in retained:
        if item['event'] in {'metadata', 'graph'}:
            parent = by_revision.get(int(item['predecessor_revision']))
            if parent is None or parent['review_digest'] != item['predecessor_review_digest']:
                _deny()
    original = by_revision.get(baseline['revision'])
    if len(retained) + (1 if original is None else 0) + 1 > MAX_CHECKPOINTS:
        _deny()
    if original is None:
        await _insert_verified(current, baseline)
    else:
        validate_checkpoint(original, current.workspace_id, baseline['template_id'], baseline['identity_digest'], baseline['revision'])
        if original['review_digest'] != baseline['review_digest']:
            _deny()
    await _insert_verified(current, result)


async def _append_change_checkpoints(current: SuppressionDatabase, before: dict, after: dict,
                                     actor: str, timestamp: datetime, event: str) -> None:
    _require_transaction(current, before)
    result = checkpoint_for(after, actor, timestamp, predecessor=before, event=event)
    await _append_result(current, before, result, actor, timestamp)


async def append_deletion_checkpoints(current: SuppressionDatabase, before: dict,
                                      actor: str, timestamp: datetime) -> None:
    """Append only after the caller verified literal deletion and native absence."""
    _require_transaction(current, before)
    result = deletion_checkpoint_for(before, actor, timestamp)
    await _append_result(current, before, result, actor, timestamp)


async def append_metadata_checkpoints(current: SuppressionDatabase, before: dict, after: dict,
                                      actor: str, timestamp: datetime) -> None:
    await _append_change_checkpoints(current, before, after, actor, timestamp, 'metadata')


async def append_graph_checkpoints(current: SuppressionDatabase, before: dict, after: dict,
                                   actor: str, timestamp: datetime) -> None:
    await _append_change_checkpoints(current, before, after, actor, timestamp, 'graph')
