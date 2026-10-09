"""Metadata-only current Webshare review lineage; ciphertext storage may rewrap."""
from __future__ import annotations
from typing import Any

from outreach.core.authorization import canonical_hash

FIELDS = ('root_import_basis_digest', 'proxy_lifecycle_revision', 'proxy_lifecycle_review_id')
ADOPTION_FIELDS = ('proxy_adoption_id', 'proxy_adoption_source_digest')


def adoption_material(row: dict) -> str:
    return canonical_hash([row.get('_id'), row.get('workspace_id'),
        *(row.get(field) for field in ADOPTION_FIELDS),
        row.get('root_import_basis_digest', row.get('import_basis_digest'))])


async def valid_adoption(db: Any, row: dict, workspace: str) -> bool:
    from outreach.core.proxy_migration import HEX
    if not any(field in row for field in ADOPTION_FIELDS):
        return await db.outreach_proxy_adoptions.find_one({'workspace_id': workspace, 'proxy_id': row['_id']}) is None
    if any(not isinstance(row.get(field), str) or not HEX.fullmatch(row[field]) for field in ADOPTION_FIELDS):
        return False
    receipt = await db.outreach_proxy_adoptions.find_one({
        'workspace_id': workspace, 'proxy_id': row['_id'], '_id': row['proxy_adoption_id']})
    return bool(receipt and row.get('workspace_id') == workspace and receipt.get('status') == 'completed'
        and receipt.get('source_digest') == row['proxy_adoption_source_digest']
        and receipt.get('adopted_basis_digest') == row.get('root_import_basis_digest', row.get('import_basis_digest')))


def material(row: dict) -> str:
    """Bind the current verified basis and lineage, independent of storage format."""
    return canonical_hash({key: row.get(key) for key in ('_id', 'workspace_id', 'import_basis_digest', *FIELDS)})


async def valid_history(db: Any, row: dict, workspace: str) -> bool:
    if row.get('provider') == 'webshare_plan' and not await valid_adoption(db, row, workspace):
        return False
    if not any(key in row for key in FIELDS):
        # Missing markers are original only when no participating lifecycle
        # journal exists. A raw field removal cannot downgrade reviewed history.
        return await db.outreach_proxy_lifecycle_reviews.find_one({
            'workspace_id': workspace, 'proxy_id': row['_id']}) is None
    from outreach.core.proxy_migration import HEX
    revision = row.get('proxy_lifecycle_revision')
    if (type(revision) is not int or not 1 <= revision <= 1_000_000
            or any(not isinstance(row.get(key), str) or not HEX.fullmatch(row[key])
                   for key in ('root_import_basis_digest', 'proxy_lifecycle_review_id'))
            or row.get('workspace_id') != workspace):
        return False
    receipt = await db.outreach_proxy_lifecycle_reviews.find_one({
        '_id': row['proxy_lifecycle_review_id'], 'workspace_id': workspace, 'proxy_id': row['_id']})
    return bool(receipt and receipt.get('status') == 'completed'
        and receipt.get('revision') == revision and receipt.get('root_import_basis_digest') == row['root_import_basis_digest']
        and receipt.get('after_basis_digest') == material(row)
        and receipt.get('generation_digest') == canonical_hash(row.get('credential_generation')))
