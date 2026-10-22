"""Bounded private stopped integration control; operator drain is an assertion."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from datetime import datetime
import re
from typing import Any, Awaitable, Callable
from outreach.core import erasure, integration_custody as custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.integration_delivery import _utc, now
from outreach.core.integrations_pilot import integrations_enabled
from outreach.core.paid_access import live_actions_enabled
from outreach.core.voice_policy import preparation_enabled
from outreach.core.voice_studio import enabled as studio_enabled

LIMIT = 100
HEX = re.compile(r'[a-f0-9]{64}\Z')


def flags_off() -> bool:
    return not (integrations_enabled() or live_actions_enabled() or studio_enabled() or preparation_enabled())


def reference(value: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError('A bounded record reference is required')


def require_review(operator: str, evidence: str, digest: str, drained: bool) -> None:
    if (drained is not True or not flags_off() or not isinstance(digest, str) or not HEX.fullmatch(digest)
            or not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 256
            or not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 2000
            or any(ord(char) < 32 or ord(char) == 127 for char in operator + evidence)):
        raise ValueError('Disabled flags, exact inspection and identified all-writer/cache drain are required')


def stable(value: Any) -> Any:
    """Normalize BSON UTC/millisecond timestamps and omit read-fence counters."""
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key != 'dispatch_fence_revision'}
    if isinstance(value, list):
        return [stable(item) for item in value]
    if isinstance(value, datetime):
        return _utc(value).replace(microsecond=value.microsecond // 1000 * 1000)
    return value


def fenced(current: Any) -> Any:
    return (AuthorityDatabase(current.database, current.session, 'integration_private_control')
        if isinstance(current, suppression.SuppressionDatabase) else current)


async def control(db: Any, workspace: str, callback: Callable[[Any], Awaitable[dict]]) -> dict:
    # No retry fallback on an unknown commit. Closed workspaces use the same
    # guard via the private stop-only path and never recreate authority.
    if await erasure.workspace_is_open(db, workspace):
        return await suppression.mutate_suppression(db, workspace, callback)
    return await erasure._control(db, workspace, callback)


async def snapshot(current: Any, workspace: str, kind: str, resource: str) -> dict:
    reference(workspace); reference(resource)
    scope = custody.resource_scope(workspace, kind, resource)
    if kind != 'webhook' and resource != kind:
        raise ValueError('The exact configured provider resource is required')
    source = await custody.collection(current, kind).find_one(scope)
    result = {'workspace_id': workspace, 'kind': kind, 'resource': resource, 'source': stable(source),
        'policy': custody.policy_digest(), 'flags_off': flags_off(),
        'workspace_open': await erasure.workspace_is_open(current, workspace)}
    result['resource_control'] = stable(await current.outreach_integration_controls.find_one(
        custody.control_scope(workspace, kind, resource)))
    destination = ({'$or': [{'destination_type': 'webhook'},
        {'destination_type': None, 'custody_protocol_version': {'$ne': 2}}]} if kind == 'webhook'
        else {'destination_type': kind})
    for name, collection, query in (
        ('jobs', 'outreach_webhook_deliveries', {'destination_id': resource, **destination,
            'status': {'$in': ['pending', 'retry', 'preparing', 'possible', 'received', 'held_received', 'review_required', 'leased']}}),
        ('writer_jobs', 'outreach_webhook_deliveries', {'status': {'$in': ['preparing', 'possible', 'received', 'leased']}}),
        ('accounts', 'outreach_accounts', {}),
        ('campaigns', 'outreach_campaigns', {'status': {'$in': ['active', 'warming_up']}}),
        ('executions', 'outreach_sender_execution', {}),
        ('permissions', 'outreach_execution_permissions', {})):
        result[name] = stable(await getattr(current, collection).find({'workspace_id': workspace, **query})
            .sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1))
    return result


def blockers(view: dict, target: str | None = None) -> list[str]:
    reasons = []
    if not view['flags_off']: reasons.append('provider_flags_enabled')
    for name in ('jobs', 'writer_jobs', 'accounts', 'campaigns', 'executions', 'permissions'):
        if len(view[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
    ids = [row.get('id') for row in view['accounts']]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        reasons.append('sender_identity_unproven')
    for row in view['writer_jobs']:
        if row.get('id') == target: continue
        if row.get('status') in {'preparing', 'possible', 'received', 'leased'}:
            expiry = _utc(row.get('leased_until'))
            if not expiry or expiry > now(): reasons.append('other_integration_writer_live_or_unproven')
    for row in view['executions']:
        expiry = _utc(row.get('expires_at'))
        if row.get('status') != 'idle' and expiry and expiry > now(): reasons.append('sender_worker_lease_live')
    return sorted(set(reasons))


async def stop(current: Any, view: dict, operator: str, reason: str) -> None:
    """Stop existing authority before exact local repair; preserve physical tokens."""
    workspace, stamp = view['workspace_id'], now()
    for row in view['accounts']:
        await current.outreach_accounts.update_one({'workspace_id': workspace, '_id': row['_id']},
            {'$set': {'status': 'paused' if view['workspace_open'] else 'disconnected', 'updated_at': stamp}})
    for row in view['campaigns']:
        await current.outreach_campaigns.update_one({'workspace_id': workspace, '_id': row['_id']},
            {'$set': {'status': 'paused', 'auto_launch_enabled': False, 'updated_at': stamp}, '$inc': {'authorization_revision': 1}})
    for name, rows in (('outreach_sender_execution', view['executions']), ('outreach_execution_permissions', view['permissions'])):
        changes = {'latched': True, 'expires_at': stamp, 'stop_reason': reason, 'stopped_by': operator}
        update = ({'$set': {'permission.'+key: value for key, value in changes.items()}, '$inc': {'permission_revision': 1}}
            if name == 'outreach_sender_execution' else {'$set': changes})
        for row in rows:
            await getattr(current, name).update_one({'workspace_id': workspace, '_id': row['_id']}, update)
    if view['source']:
        scope = custody.resource_scope(workspace, view['kind'], view['resource'])
        changed = await custody.collection(current, view['kind']).update_one({**scope, '_id': view['source']['_id']},
            {'$set': {'status': 'paused', 'integration_review_required': True, 'updated_at': stamp}})
        if changed.matched_count != 1: raise ValueError('Integration resource changed during stop')
    if view['workspace_open']:
        await current.outreach_integration_controls.update_one(
            custody.control_scope(workspace, view['kind'], view['resource']),
            {'$set': {'latched': True, 'at': stamp, 'reason': reason, 'operator_digest': canonical_hash(operator),
                'activation_allowed': False}}, upsert=True)
    destination = ({'$or': [{'destination_type': 'webhook'},
        {'destination_type': None, 'custody_protocol_version': {'$ne': 2}}]} if view['kind'] == 'webhook'
        else {'destination_type': view['kind']})
    await current.outreach_webhook_deliveries.update_many({'workspace_id': workspace,
        **destination, 'destination_id': view['resource'], 'status': {'$in': ['pending', 'retry']}},
        {'$set': {'status': 'cancelled', 'active_slot': None, 'updated_at': stamp}})


def material(row: dict | None, workspace: str, kind: str) -> str | None:
    try:
        return custody.material_digest(row, workspace, kind) if row else None
    except (TypeError, ValueError, AttributeError):
        return None
