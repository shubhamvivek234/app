"""Guarded, digest-only history pages; successful reads write authority counters.

No template/checkpoint content, indexes, grants or restore state is written.
Pages validate the complete bounded recorded lineage in one snapshot; cursors
are unsigned context locators, not capabilities or evidence outside the backup.
"""
import logging
logger = logging.getLogger(__name__)
import base64
from datetime import timezone
import hashlib
import json
import re
from typing import Any

from bson import BSON, Int64
from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core import template_governance as governance
from outreach.core import template_history_storage as storage
from outreach.core.suppression import mutate_suppression
from outreach.core.template_revision_checkpoints import MAX_CHECKPOINTS, validate_checkpoint

MAX_HISTORY_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 65536
MAX_PAGE_SIZE = 25
HEX = r'[0-9a-f]{64}'


def _hold() -> None:
    raise HTTPException(409, 'Template history changed or needs review; reload its first page')


def scope_digest(workspace: str, actor: str, uid: str, template_id: str, identity: str) -> str:
    if (any(type(x) is not str for x in (workspace, actor, uid, template_id, identity))
            or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', template_id)
            or not re.fullmatch(HEX, identity)):
        raise HTTPException(422, 'A valid template history reference is required')
    governance.review_scope(workspace, actor, uid)
    return canonical_hash(['template-history-scope-v1', workspace, actor, uid, template_id, identity])


def prepare_history(rows: list, workspace: str, template_id: str, identity: str) -> tuple[list, str]:
    if type(rows) is not list or len(rows) > MAX_CHECKPOINTS:
        _hold()
    if not rows:
        raise HTTPException(404, 'No recorded history exists for this native template identity')
    ordinary, terminals, size = {}, [], 0
    for row in rows:
        if type(row) is not dict or type(row.get('revision')) not in {int, Int64}:
            _hold()
        validate_checkpoint(row, workspace, template_id, identity, int(row['revision']))
        encoded = BSON.encode(row)
        size += len(encoded)
        if len(encoded) > storage.MAX_ROW_BYTES or size > MAX_HISTORY_BYTES:
            _hold()
        if row['event'] == 'deleted':
            terminals.append(row)
        elif int(row['revision']) in ordinary:
            _hold()
        else:
            ordinary[int(row['revision'])] = row
    if not ordinary or len(terminals) > 1 or (0 in ordinary and any(r['event'] == 'created' for r in ordinary.values())):
        _hold()
    for row in ordinary.values():
        if row['event'] in {'metadata', 'graph'}:
            parent = ordinary.get(int(row['predecessor_revision']))
            if parent is None or parent['review_digest'] != row['predecessor_review_digest']:
                _hold()
    if terminals:
        terminal = terminals[0]; parent = ordinary.get(int(terminal['revision']))
        if (parent is None or int(terminal['revision']) != max(ordinary)
                or parent['review_digest'] != terminal['predecessor_review_digest']):
            _hold()
    ordered = sorted(rows, key=lambda r: (int(r['revision']), r['event'] == 'deleted', r['_id']))
    digest = canonical_hash(['template-history-snapshot-v1', workspace, template_id, identity,
        [hashlib.sha256(BSON.encode(row)).hexdigest() for row in ordered]])
    return ordered, digest


def encode_cursor(scope: str, digest: str, after: str, size: int) -> str:
    value = {'contract_version': 1, 'scope_digest': scope, 'history_digest': digest, 'after_id': after, 'page_size': size}
    raw = json.dumps(value, separators=(',', ':'), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(token: str, scope: str, size: int) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate key')
            result[key] = value
        return result
    try:
        if type(token) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,768}', token):
            raise ValueError('Invalid cursor')
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
        if (type(value) is not dict or set(value) != {'contract_version', 'scope_digest', 'history_digest', 'after_id', 'page_size'}
                or type(value['contract_version']) is not int or value['contract_version'] != 1
                or type(value['page_size']) is not int or value['page_size'] != size
                or any(type(value[k]) is not str or not re.fullmatch(HEX, value[k]) for k in ('scope_digest', 'history_digest', 'after_id'))
                or encode_cursor(value['scope_digest'], value['history_digest'], value['after_id'], value['page_size']) != token):
            raise ValueError('Invalid cursor contract')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HTTPException(422, 'Invalid template history cursor') from None
    if value['scope_digest'] != scope:
        raise HTTPException(403, 'Template history account or workspace changed')
    return value


def make_page(rows: list, workspace: str, template_id: str, identity: str, actor: str, uid: str,
               *, page_size: int = 20, cursor: str | None = None) -> dict:
    scope = scope_digest(workspace, actor, uid, template_id, identity)
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise HTTPException(422, 'Template history page size must be between 1 and 25')
    reference = decode_cursor(cursor, scope, page_size) if cursor is not None else None
    if reference is not None and not rows:
        _hold()
    ordered, digest = prepare_history(rows, workspace, template_id, identity)
    start = 0
    if reference is not None:
        if reference['history_digest'] != digest:
            _hold()
        indexes = [i for i, row in enumerate(ordered) if row['_id'] == reference['after_id']]
        if len(indexes) != 1:
            _hold()
        start = indexes[0] + 1
    selected = ordered[start:start + page_size]
    items = [{'checkpoint_id': row['_id'], 'revision': int(row['revision']), 'event': row['event'],
        'review_digest': row['review_digest'], 'predecessor_revision': None if row['predecessor_revision'] is None else int(row['predecessor_revision']),
        'predecessor_review_digest': row['predecessor_review_digest'], 'recorded_by': row['recorded_by'],
        'recorded_at': row['recorded_at'].replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}
        for row in selected]
    result = {'contract_version': 1, 'workspace_id': workspace, 'template_id': template_id, 'identity_digest': identity,
        'history_digest': digest, 'record_count': len(ordered), 'items': items,
        'next_cursor': encode_cursor(scope, digest, selected[-1]['_id'], page_size) if start + len(selected) < len(ordered) else None,
        'terminal_recorded': any(row['event'] == 'deleted' for row in ordered), 'capture_complete': False,
        'content_available': False, 'restore_available': False, 'execution_authorized': False}
    if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > MAX_RESPONSE_BYTES:
        _hold()
    return result


async def _load_rows(current: Any, workspace: str, identity: str) -> list:
    wrapped = await current.database.outreach_template_revisions.aggregate(
        storage.history_pipeline(workspace, identity, MAX_CHECKPOINTS + 1), session=current.session,
        hint=storage.INDEX_NAME, collation={'locale': 'simple'}, maxTimeMS=2000, batchSize=50).to_list(MAX_CHECKPOINTS + 1)
    rows, size = [], 0
    for item in wrapped:
        if (type(item) is not dict or set(item) != {'row', 'bytes'} or type(item['bytes']) not in {int, Int64}
                or not 0 < item['bytes'] <= storage.MAX_ROW_BYTES or type(item['row']) is not dict
                or item['bytes'] != len(BSON.encode(item['row']))):
            _hold()
        size += int(item['bytes'])
        if size > MAX_HISTORY_BYTES:
            _hold()
        rows.append(item['row'])
    return rows


async def read_history(db: Any, workspace: str, actor: str, uid: str, template_id: str, identity: str,
                        *, page_size: int = 20, cursor: str | None = None) -> dict:
    scope_digest(workspace, actor, uid, template_id, identity)
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise HTTPException(422, 'Template history page size must be between 1 and 25')
    if db is None:
        raise HTTPException(503, 'Template history is unavailable')
    async def inspect(current):
        await governance.authorize_read(current, actor, uid)
        collection = current.database.outreach_template_revisions
        before = await storage.require_history_index(collection)
        rows = await _load_rows(current, workspace, identity)
        page = make_page(rows, workspace, template_id, identity, actor, uid, page_size=page_size, cursor=cursor)
        if await storage.require_history_index(collection) != before:
            _hold()
        return page
    try:
        return await mutate_suppression(db, workspace, inspect)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Template history is unavailable; reload before continuing') from None
