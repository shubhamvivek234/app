"""Explicit, non-destructive index preparation for digest history reads.

No startup or customer request installs indexes. TTL, partial or conflicting
definitions hold preparation/readiness; this module never drops or repairs one.
"""
import logging
logger = logging.getLogger(__name__)
from typing import Any

from fastapi import HTTPException

from outreach.core.workspace_scope import workspace_scope

INDEX_NAME = 'template_history_identity_v1'
INDEX_KEYS = [('workspace_id', 1), ('identity_digest', 1), ('revision', 1), ('_id', 1)]
MAX_ROW_BYTES = 4096


def _unavailable() -> None:
    raise HTTPException(503, 'Template history storage needs preparation or review')


def validate_indexes(indexes: dict) -> dict:
    if (type(indexes) is not dict or any(type(row) is not dict or 'expireAfterSeconds' in row for row in indexes.values())
            or INDEX_NAME not in indexes):
        _unavailable()
    row = indexes[INDEX_NAME]
    keys = row.get('key')
    if (type(keys) is not list or len(keys) != len(INDEX_KEYS)
            or any(type(pair) not in {tuple, list} or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not int
                or tuple(pair) != expected for pair, expected in zip(keys, INDEX_KEYS))
            or any(row.get(flag, False) is not False for flag in ('unique', 'sparse', 'hidden', 'prepareUnique'))
            or 'partialFilterExpression' in row
            or row.get('collation', {'locale': 'simple'}) != {'locale': 'simple'}):
        _unavailable()
    return {'name': INDEX_NAME, 'keys': INDEX_KEYS, 'collation': {'locale': 'simple'}}


async def require_history_index(collection: Any) -> dict:
    return validate_indexes(await collection.index_information())


async def ensure_history_index(db: Any) -> dict:
    """Administrative source entry point; callers separately authorize cutover."""
    return await prepare_index(db.outreach_template_revisions)


async def prepare_index(collection: Any) -> dict:
    """Explicit preparation for a history collection; never called by readers."""
    indexes = await collection.index_information()
    if any('expireAfterSeconds' in row for row in indexes.values()):
        _unavailable()
    if INDEX_NAME not in indexes:
        await collection.create_index(INDEX_KEYS, name=INDEX_NAME, unique=False, collation={'locale': 'simple'})
    return await require_history_index(collection)


def history_pipeline(workspace: str, identity: str, limit: int) -> list[dict]:
    """Return minimal sentinels for oversized rows, including oversized native IDs."""
    return [{'$match': {**workspace_scope(workspace), 'identity_digest': identity}}, {'$limit': limit},
        {'$project': {'_id': 0, 'bytes': {'$bsonSize': '$$ROOT'}, 'row': {'$cond': [
            {'$lte': [{'$bsonSize': '$$ROOT'}, MAX_ROW_BYTES]}, '$$ROOT', None]}}}]
