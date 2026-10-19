"""Opt-in encrypted revision pairs inside the template mutation's transaction.

The trusted caller owns the workspace guard, current mutation permission and
literal source CAS/readbacks. No transaction, index, receipt or grant is created
here. Old writers must drain before coordinated activation; this process setting
is not a distributed cutover fence or a claim of complete historical capture.
"""
from datetime import datetime, timezone
import os
from typing import Any, NoReturn

from bson import BSON, Int64, ObjectId
from fastapi import HTTPException

from outreach.core import template_governance as governance, template_history as history
from outreach.core import template_history_storage as storage
from outreach.core import template_graph_snapshots as graphs, template_metadata_snapshots as metadata
from outreach.core.lead_tags import unique_resource
from outreach.core.suppression import SuppressionDatabase
from outreach.core.template_access import inspect_access
from outreach.core.template_snapshot_capture import canonical_json
from outreach.core.workspace_scope import workspace_scope

SETTING = 'OUTREACH_TEMPLATE_SNAPSHOTS_ENABLED'
# Accepted retained-plus-new BSON across BOTH kinds. This follows each bounded
# loader, and is not a physical network/server-work or whole-transaction limit.
MAX_BATCH_BYTES = 8 * 1024 * 1024


def _hold() -> NoReturn:
    raise HTTPException(409, 'Template snapshot capture needs review')


def capture_enabled() -> bool:
    """Only an explicit server setting activates new automatic captures."""
    value = os.getenv(SETTING, 'false')
    if value not in {'true', 'false'}:
        raise HTTPException(503, 'Template snapshot capture configuration needs review')
    return value == 'true'


def _reviews(current: SuppressionDatabase, sources: tuple[dict, ...], timestamp: datetime,
             event: str) -> list[dict]:
    if (type(sources) is not tuple or type(event) is not str
            or event not in {'created', 'metadata', 'graph', 'deleted'}
            or len(sources) != (2 if event in {'metadata', 'graph'} else 1)
            or type(timestamp) is not datetime or timestamp.microsecond % 1000
            or timestamp.utcoffset() not in (None, timezone.utc.utcoffset(None))):
        _hold()
    reviews = []
    for source in sources:
        if (type(source) is not dict or type(source.get('_id')) not in {str, ObjectId}
                or any(type(source.get(key)) is not str for key in ('id', 'workspace_id', 'user_id'))
                or source['workspace_id'] != current.workspace_id):
            _hold()
        review = governance.template_review(source, current.workspace_id)
        if not review['reviewable']:
            _hold()
        reviews.append(review)
    if event == 'created' and reviews[0]['revision'] != 1:
        _hold()
    if len(sources) == 2 and (
            reviews[0]['identity_digest'] != reviews[1]['identity_digest']
            or sources[0]['id'] != sources[1]['id']
            or reviews[0]['revision'] + 1 != reviews[1]['revision']):
        _hold()
    return reviews


async def _indexes(current: SuppressionDatabase) -> None:
    for name in ('outreach_template_revisions', metadata.COLLECTION, graphs.COLLECTION):
        await storage.require_history_index(current.database[name])


async def capture_mutation(current: Any, sources: tuple[dict, ...], actor: str, uid: str,
                           timestamp: datetime, *, event: str) -> None:
    """Capture creation, both edit images, or pre-delete content atomically.

Only actual new mutations call this hook, after checkpoint/source verification
and before their receipt insertion. A completed original receipt bypasses it.
Missing prerequisites hold enabled mutations; disabled rollout does no reads.
"""
    if not capture_enabled():
        return
    if (not isinstance(current, SuppressionDatabase) or current.session is None
            or current.session.in_transaction is not True
            or current.session.client is not current.database.client):
        _hold()
    try:
        reviews = _reviews(current, sources, timestamp, event)
        workspace = current.workspace_id
        await inspect_access(current.database, workspace, actor, uid, session=current.session)
        live = await unique_resource(current.outreach_templates, workspace, sources[-1]['id'])
        if event == 'deleted':
            if live is not None:
                _hold()
        elif live is None or BSON.encode(live) != BSON.encode(sources[-1]):
            _hold()
        await _indexes(current)
        retained = await history._load_rows(current, workspace, reviews[-1]['identity_digest'])
        ordered, _ = history.prepare_history(retained, workspace, sources[-1]['id'], reviews[-1]['identity_digest'])
        terminals = [row for row in ordered if row['event'] == 'deleted']
        if bool(terminals) != (event == 'deleted'):
            _hold()
        parents = {int(row['revision']): row for row in ordered if row['event'] != 'deleted'}
        if not parents or max(parents) != reviews[-1]['revision']:
            _hold()
        checkpoints = []
        for review in reviews:
            checkpoint = parents.get(review['revision'])
            if checkpoint is None or checkpoint['review_digest'] != review['review_digest']:
                _hold()
            checkpoints.append(checkpoint)
        if event != 'deleted' and checkpoints[-1]['event'] != event:
            _hold()
        if event == 'deleted' and (len(terminals) != 1
                or terminals[0]['revision'] != reviews[-1]['revision']
                or terminals[0]['predecessor_review_digest'] != reviews[-1]['review_digest']):
            _hold()
        planned = []
        total = 0
        for codec, project in ((metadata, metadata._metadata), (graphs, graphs.project_graph)):
            rows, size = await codec._retained(current, workspace, reviews[-1]['identity_digest'])
            total += size
            existing = {}
            for row in rows:
                if type(row.get('revision')) not in {int, Int64} or int(row['revision']) not in parents:
                    _hold()
                content = codec.open_snapshot(row, parents[int(row['revision'])])
                if row['_id'] in existing:
                    _hold()
                existing[row['_id']] = (row, canonical_json(content))
            additions = 0
            for source, checkpoint in zip(sources, checkpoints):
                expected = canonical_json(project(source))
                previous = existing.get(codec._id(checkpoint))
                if previous is not None:
                    if previous[1] != expected:
                        _hold()
                    continue
                row = codec.seal(source, checkpoint, actor, timestamp)
                additions += 1
                total += len(BSON.encode(row))
                planned.append((codec, row, checkpoint, expected))
            if len(rows) + additions > codec.MAX_SNAPSHOTS:
                _hold()
            if size + sum(len(BSON.encode(row)) for selected, row, _, _ in planned if selected is codec) > codec.MAX_TOTAL_BYTES:
                _hold()
        if total > MAX_BATCH_BYTES:
            _hold()
        # Every kind's schema/key/retention/capacity is checked before insertion.
        # Any subsequent failure still aborts ALL work in the owning transaction.
        for codec, row, checkpoint, expected in planned:
            await current[codec.COLLECTION].insert_one(row)
            stored = await current[codec.COLLECTION].find_one({**workspace_scope(workspace), '_id': row['_id']})
            if (stored is None or BSON.encode(stored) != BSON.encode(row)
                    or canonical_json(codec.open_snapshot(stored, checkpoint)) != expected):
                _hold()
        await _indexes(current)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Could not confirm template snapshot capture; retain the original operation reference') from None
