"""Opt-in, currently authorized reads of one recorded encrypted content pair.

Successful reads write existing guard/user/role authority counters. They do not
capture, repair, restore, create indexes, grant execution or prove completeness.
Content leaves this service only after its owning snapshot transaction commits.
"""
from datetime import timezone
import os
import re
from typing import Any, NoReturn

from bson import BSON, Int64
from fastapi import HTTPException

from outreach.core import template_governance as governance, template_history as history
from outreach.core import template_history_storage as storage
from outreach.core import template_graph_snapshots as graphs, template_metadata_snapshots as metadata
from outreach.core.suppression import SuppressionDatabase, mutate_suppression
from outreach.core.template_snapshot_capture import canonical_json
from outreach.core.workspace_scope import workspace_scope
from utils import encryption

SETTING = 'OUTREACH_TEMPLATE_SNAPSHOT_READS_ENABLED'
MAX_RESPONSE_BYTES = 160 * 1024
RESPONSE_HEADERS = {'Cache-Control': 'no-store, private', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff'}


def _hold() -> NoReturn:
    raise HTTPException(409, 'Recorded template content changed or needs review')


def require_enabled() -> None:
    """Capture activation does not implicitly expose historical plaintext."""
    if os.getenv(SETTING, 'false') != 'true':
        raise HTTPException(503, 'Recorded template content reads are unavailable')


def validate_reference(workspace: str, actor: str, uid: str, template_id: str, identity: str,
                       checkpoint_id: str, history_digest: str) -> None:
    """References locate data; they never confer access or discover identities."""
    history.scope_digest(workspace, actor, uid, template_id, identity)
    if any(type(value) is not str or re.fullmatch(history.HEX, value) is None
           for value in (checkpoint_id, history_digest)):
        raise HTTPException(422, 'A valid recorded content reference is required')


def _time(value: Any) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def content_payload(checkpoint: dict, history_digest: str, terminal_recorded: bool,
                    metadata_row: dict, graph_row: dict) -> dict:
    """Render only the selected allowlists after both strict codecs validate."""
    if (type(history_digest) is not str or re.fullmatch(history.HEX, history_digest) is None
            or type(terminal_recorded) is not bool):
        _hold()
    text = metadata.open_snapshot(metadata_row, checkpoint)
    graph = graphs.open_snapshot(graph_row, checkpoint)
    result = {'contract_version': 1, 'status': 'available', 'workspace_id': checkpoint['workspace_id'],
        'template_id': checkpoint['template_id'], 'identity_digest': checkpoint['identity_digest'],
        'checkpoint_id': checkpoint['_id'], 'revision': int(checkpoint['revision']),
        'review_digest': checkpoint['review_digest'], 'history_digest': history_digest,
        'checkpoint_event': checkpoint['event'], 'metadata': text, 'graph': graph,
        'snapshot_audit': {kind: {'snapshot_id': row['_id'], 'recorded_by': row['recorded_by'],
            'recorded_at': _time(row['recorded_at'])} for kind, row in (('metadata', metadata_row), ('graph', graph_row))},
        'terminal_recorded': terminal_recorded, 'capture_complete': False,
        'restore_available': False, 'execution_authorized': False}
    if len(canonical_json(result).encode('utf-8')) > MAX_RESPONSE_BYTES:
        _hold()
    return result


async def _indexes(current: Any) -> list[dict]:
    return [await storage.require_history_index(current.database[name])
        for name in ('outreach_template_revisions', metadata.COLLECTION, graphs.COLLECTION)]


async def _point(current: Any, codec: Any, checkpoint: dict) -> dict | None:
    # Do not filter by _id or public template ID: conflicting/aliased same-native
    # revision candidates must hold, rather than hiding behind the expected ID.
    pipeline = [{'$match': {**workspace_scope(current.workspace_id),
        'identity_digest': checkpoint['identity_digest'], 'revision': int(checkpoint['revision'])}}, {'$limit': 2},
        {'$project': {'_id': 0, 'bytes': {'$bsonSize': '$$ROOT'}, 'row': {'$cond': [
            {'$lte': [{'$bsonSize': '$$ROOT'}, codec.MAX_ROW_BYTES]}, '$$ROOT', None]}}}]
    wrapped = await current.database[codec.COLLECTION].aggregate(pipeline, session=current.session,
        hint=storage.INDEX_NAME, collation={'locale': 'simple'}, maxTimeMS=2000, batchSize=2).to_list(2)
    if len(wrapped) > 1:
        _hold()
    if not wrapped:
        return None
    value = wrapped[0]
    if (type(value) is not dict or set(value) != {'row', 'bytes'}
            or type(value['bytes']) not in {int, Int64} or not 0 < value['bytes'] <= codec.MAX_ROW_BYTES
            or type(value['row']) is not dict or value['bytes'] != len(BSON.encode(value['row']))):
        _hold()
    return value['row']


async def read_content(db: Any, workspace: str, actor: str, uid: str, template_id: str,
                       identity: str, checkpoint_id: str, history_digest: str) -> dict:
    """Read one pair, including deleted originals, under current read authority."""
    validate_reference(workspace, actor, uid, template_id, identity, checkpoint_id, history_digest)
    require_enabled()
    if db is None or isinstance(db, SuppressionDatabase):
        raise HTTPException(503, 'Recorded template content is unavailable')
    async def inspect(current):
        require_enabled()
        await governance.authorize_read(current, actor, uid)
        before = await _indexes(current)
        rows = await history._load_rows(current, workspace, identity)
        ordered, digest = history.prepare_history(rows, workspace, template_id, identity)
        if digest != history_digest:
            _hold()
        selected = [row for row in ordered if row['_id'] == checkpoint_id]
        if len(selected) != 1:
            raise HTTPException(404, 'Recorded content checkpoint is unavailable')
        checkpoint = selected[0]
        if checkpoint['event'] == 'deleted':
            _hold()
        meta = await _point(current, metadata, checkpoint)
        graph = await _point(current, graphs, checkpoint)
        if meta is None and graph is None:
            raise HTTPException(404, 'No paired content snapshot is recorded at this checkpoint')
        if meta is None or graph is None:
            _hold()
        try:
            encryption.validate_encryption_key()
        except Exception:
            raise HTTPException(503, 'Recorded content decryption is unavailable') from None
        result = content_payload(checkpoint, digest, any(row['event'] == 'deleted' for row in ordered), meta, graph)
        if await _indexes(current) != before:
            _hold()
        require_enabled()
        return result
    try:
        result = await mutate_suppression(db, workspace, inspect)
        require_enabled()
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Could not confirm recorded content access; reload history before retrying') from None
