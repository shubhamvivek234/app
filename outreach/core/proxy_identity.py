"""Permanent, digest-only physical IP exclusion for participating managed imports.

These system guards, like invoice exclusion digests, survive tenant erasure.
They attest local assignment, not vendor ownership or historical raw writers.
"""
from __future__ import annotations

import ipaddress
from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.suppression import SuppressionDatabase


def raw_options(db: Any) -> tuple[Any, dict]:
    """Use the existing transaction session for cross-tenant uniqueness only."""
    if isinstance(db, (SuppressionDatabase, AuthorityDatabase)):
        return db.database, {'session': db.session}
    return db, {}


def identity(host: str, workspace: str, asset: str, provider: str) -> dict[str, str]:
    address = ipaddress.IPv4Address(host)
    if not address.is_global or str(address) != host or not workspace or not asset:
        raise ValueError('A public physical proxy identity is required')
    return {'_id': canonical_hash(['managed-proxy-ip-v1', host]),
            'binding_digest': canonical_hash([workspace, asset, provider])}


async def touch_restore_fence(raw: Any, ip_digest: str, **options) -> None:
    """Serialize even absent global negatives without inventing asset ownership."""
    await raw.account_proxy_ip_restore_fences.update_one({'_id': ip_digest},
        {'$inc': {'revision': 1}}, upsert=True, **options)


async def restore_ip_allowed(db: Any, host: str) -> bool:
    """Negative-only legacy check; absence supplies no positive ownership proof.

    Canonical IPv4 includes loopback for the existing isolated transport drills;
    this helper grants no network permission. Import still requires public IPs.
    """
    if not isinstance(host, str):
        return False
    try:
        if str(ipaddress.IPv4Address(host)) != host:
            return False
    except ValueError:
        return False
    key = canonical_hash(['managed-proxy-ip-v1', host])
    raw, options = raw_options(db)
    if options:
        await touch_restore_fence(raw, key, **options)
    saved = await raw.account_proxy_ip_guards.find_one({'_id': key}, **options)
    if saved and options:
        result = await raw.account_proxy_ip_guards.update_one({'_id': key},
            {'$inc': {'dispatch_fence_revision': 1}}, **options)
        if result.matched_count != 1:
            raise ValueError('Physical IP exclusion authority changed')
    return not saved or 'restore_reuse_blocked' not in saved


async def check_restore_ips(db: Any, workspace: str, hosts: list[str], *, captured=None) -> None:
    """Guarded negative admission before outside-transaction key/health work."""
    from outreach.core import restore_epoch, suppression
    async def check(current):
        proof = await restore_epoch.positive(current, workspace, captured=captured)
        for host in set(hosts):
            if not await restore_ip_allowed(current, host):
                raise ValueError('Physical IP requires restore reconciliation')
        proof.assert_live()
    await suppression.mutate_suppression(db, workspace, check)


async def require_ip_binding(db: Any, row: dict, workspace: str, *, claim: bool = False) -> bool:
    """Check the permanent claim and reject any currently visible legacy alias.

Global reads expose only collision presence. Writes use the caller's snapshot
transaction; duplicate-key aborts must propagate to its transaction helper.
"""
    proof = identity(row.get('host'), workspace, row.get('_id'), row.get('provider'))
    if not await restore_ip_allowed(db, row['host']):
        return False
    raw, options = raw_options(db)
    if claim:
        existing = await raw.outreach_proxy_inventory.find_one({'_id': row['_id']}, **options)
        if existing and (existing.get('last_workspace_id') != workspace
                or existing.get('workspace_id', workspace) != workspace
                or any(existing.get(key) != row.get(key) for key in ('provider', 'host', 'port', 'username', 'country_code'))):
            raise ValueError('Existing physical asset requires drained ownership review')
    # An older inventory alias is not silently adopted, even in the same tenant.
    if await raw.outreach_proxy_inventory.count_documents(
            {'host': row['host'], '_id': {'$ne': row['_id']}}, **options):
        raise ValueError('Physical IP assignment is ambiguous; drained review is required')
    collection = raw.account_proxy_ip_guards
    if claim:
        await collection.update_one({'_id': proof['_id']}, {'$setOnInsert': proof}, upsert=True, **options)
    saved = await collection.find_one({'_id': proof['_id']}, **options)
    return bool(saved and saved.get('binding_digest') == proof['binding_digest'])
