"""Record externally performed Webshare renewal/password change after exact drain.

No purchase, vendor request, activation or ownership adoption occurs here.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
import uuid

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from outreach.core.proxy_custody import policy, seal_proxy_password
from outreach.core.proxy_migration import ProxyMigration, HEX, _authority, _material, _reference, _stable, flags_off
from outreach.core.proxy_lifecycle_proof import material, valid_history
from outreach.core.session_custody import custody_mode
from outreach.core.webshare_provisioning import _basis, _time

MAX_TERM_DAYS = 366
OPERATIONS = ('renew', 'rotate')


def now() -> datetime:
    return datetime.now(timezone.utc)


def _target(value: Any, *, eligible: bool = True) -> datetime:
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError('timezone')
        value = _time(value)
        current = now()
        if eligible and not current < value <= current + timedelta(days=MAX_TERM_DAYS):
            raise ValueError('term')
        return value
    except (ValueError, TypeError):
        raise CustodyUnavailable('An explicit future verified provider term within366days is required') from None


def _password(value: Any) -> str:
    try:
        if (not isinstance(value, str) or not 1 <= len(value.encode('utf-8')) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError('password')
        return value
    except (ValueError, UnicodeError):
        raise CustodyUnavailable('A bounded hidden provider password is required') from None


def _current(view: dict) -> str:
    return canonical_hash([_material(view), material(view['inventory'] or {})])


def _final(view: dict, row: dict) -> None:
    """Pure last check after all awaited work in the installation callback."""
    if (not flags_off() or view['policy_digest'] != canonical_hash(policy()) or _time(row['expires_at']) <= now()):
        raise CustodyUnavailable('Proxy change final authority changed')


class ProxyLifecycle:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, current: Any, workspace: str, asset: str) -> dict:
        view = await ProxyMigration(self.db)._snapshot(current, workspace, asset)
        row = view['inventory'] or {}
        view['previous_review'] = _stable(await current.outreach_proxy_lifecycle_reviews.find_one({
            'workspace_id': workspace, '_id': row.get('proxy_lifecycle_review_id'), 'proxy_id': asset})
            if row.get('proxy_lifecycle_review_id') else None)
        return view

    @staticmethod
    def _blockers(view: dict, workspace: str, operation: str) -> list[str]:
        reasons = [reason for reason in ProxyMigration._blockers(view, workspace) if reason not in {
            'original_strict_fernet_required', 'disabled_flags_and_scoped_destination_required', 'asset_unavailable_or_unowned'}]
        row = view['inventory'] or {}
        try:
            expiry = _time(row.get('expires_at'))
        except (TypeError, ValueError):
            expiry = None
        if (row.get('provider') != 'webshare_plan' or row.get('status') != 'available'
                or row.get('workspace_id') != workspace or row.get('last_workspace_id') != workspace or not expiry
                or operation == 'rotate' and expiry <= now()):
            reasons.append('original_managed_asset_unavailable')
        value = row.get('password_enc')
        if (not isinstance(value, str) or not 1 <= len(value) <= 16384
                or value.startswith(PREFIX) != (custody_mode() == 'kms_v1')
                or not value.startswith((PREFIX, 'gAAAAA')) or row.get('custody_workspace_id') != workspace
                or not isinstance(row.get('credential_generation'), str) or not 1 <= len(row['credential_generation']) <= 256):
            reasons.append('original_storage_scope_unproven')
        if not flags_off() or custody_mode() not in ('legacy_fernet', 'kms_v1'):
            reasons.append('disabled_flags_and_known_custody_required')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, asset: str, operation: str) -> dict:
        _reference(workspace); _reference(asset)
        if operation not in OPERATIONS:
            raise CustodyUnavailable('A supported proxy review operation is required')
        view = await self._view(self.db, workspace, asset)
        return {'workspace_id': workspace, 'proxy_id': asset, 'operation': operation,
            'digest': canonical_hash([operation, view]), 'blockers': self._blockers(view, workspace, operation),
            'activation_allowed': False}

    async def _saved(self, current: Any, receipt: dict, request_digest: str, workspace: str, asset: str) -> dict:
        if receipt.get('request_digest') != request_digest:
            raise CustodyUnavailable('A different provider change review is already saved')
        view = await self._view(_authority(current, receipt['_id']), workspace, asset)
        return {'status': 'completed', 'review_id': receipt['_id'], 'operation': receipt['operation'],
            'current_matches': _current(view) == receipt['after_digest'] and view['lifecycle_history_valid']
                and view['restore_reuse_allowed'],
            'configuration_matches': view['policy_digest'] == receipt['target_policy_digest'], 'activation_allowed': False}

    async def apply(self, workspace: str, asset: str, operation: str, operator: str, evidence_digest: str,
                    provider_reference: str, expected_digest: str, *, workers_drained: bool = False,
                    expires_at: Any = None, password_supplier: Callable[[], str] | None = None) -> dict:
        _reference(workspace); _reference(asset); _reference(operator); _reference(provider_reference)
        if (workers_drained is not True or not flags_off() or operation not in OPERATIONS
                or custody_mode() not in ('legacy_fernet', 'kms_v1')
                or any(not isinstance(value, str) or not HEX.fullmatch(value) for value in (evidence_digest, expected_digest))
                or operation == 'renew' and password_supplier is not None
                or operation == 'rotate' and (expires_at is not None or not callable(password_supplier))):
            raise CustodyUnavailable('Exact disabled-gate provider evidence and all-writer/cache drain are required')
        target = _target(expires_at, eligible=False) if operation == 'renew' else None
        request_digest = canonical_hash([workspace, asset, operation, operator, evidence_digest,
            provider_reference, expected_digest, target])
        key = canonical_hash(['proxy-lifecycle-v1', workspace, asset, operation, provider_reference])
        scope = {'workspace_id': workspace, '_id': key}
        receipt = await self.db.outreach_proxy_lifecycle_reviews.find_one(scope)
        if receipt:
            return await self._saved(self.db, receipt, request_digest, workspace, asset)
        if target is not None:
            _target(target)
        async def verify(current: Any) -> dict:
            view = await self._view(_authority(current, key), workspace, asset)
            if (canonical_hash([operation, view]) != expected_digest or self._blockers(view, workspace, operation)
                    or target is not None and target <= _time(view['inventory']['expires_at'])):
                raise CustodyUnavailable('Original drained proxy change inspection changed')
            return view
        async def preflight(current: Any) -> dict:
            saved = await current.outreach_proxy_lifecycle_reviews.find_one(scope)
            if saved:
                return {'completed': await self._saved(current, saved, request_digest, workspace, asset)}
            return {'view': await verify(current)}
        inspected = await suppression.mutate_suppression(self.db, workspace, preflight)
        if 'completed' in inspected:
            return inspected['completed']
        view = inspected['view']; original = view['inventory']; row = deepcopy(original)
        if target is not None:
            row['expires_at'] = target
        else:
            password = _password(password_supplier())
            row.update(await seal_proxy_password(password, row, workspace, generation=uuid.uuid4().hex))
            del password
        if not flags_off() or view['policy_digest'] != canonical_hash(policy()):
            raise CustodyUnavailable('Proxy change custody policy changed')
        row.update(root_import_basis_digest=original.get('root_import_basis_digest', original['import_basis_digest']),
            proxy_lifecycle_revision=original.get('proxy_lifecycle_revision', 0) + 1, proxy_lifecycle_review_id=key)
        row['import_basis_digest'] = _basis(row)
        fields = ('expires_at', 'credential_generation', 'custody_workspace_id', 'password_enc', 'import_basis_digest',
            'root_import_basis_digest', 'proxy_lifecycle_revision', 'proxy_lifecycle_review_id')
        async def install(current: Any) -> dict:
            saved = await current.outreach_proxy_lifecycle_reviews.find_one(scope)
            if saved:
                return await self._saved(current, saved, request_digest, workspace, asset)
            fresh = await verify(current); authority = _authority(current, key)
            result = await authority.outreach_proxy_inventory.update_one({'_id': asset, 'workspace_id': workspace,
                'password_enc': original['password_enc'], 'import_basis_digest': original['import_basis_digest']},
                {'$set': {field: row[field] for field in fields}})
            if result.matched_count != 1:
                raise CustodyUnavailable('Original proxy resource changed')
            if operation == 'rotate':
                for account in fresh['accounts']:
                    updates = {name: {**account[name], **{field: row[field] for field in
                        ('credential_generation', 'custody_workspace_id', 'password_enc')}}
                        for name in ('proxy', 'proxy_config') if account.get(name)}
                    result = await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': account['id'],
                        **{name: account.get(name) if name in account else {'$exists': False}
                           for name in ('proxy', 'proxy_config')}}, {'$set': updates})
                    if result.matched_count != 1:
                        raise CustodyUnavailable('Original sender proxy copy changed')
            after = await self._view(authority, workspace, asset)
            journal = {**scope, 'proxy_id': asset, 'operation': operation, 'status': 'completed',
                'request_digest': request_digest, 'revision': row['proxy_lifecycle_revision'],
                'root_import_basis_digest': row['root_import_basis_digest'], 'after_basis_digest': material(row),
                'previous_review_digest': canonical_hash(view['previous_review']) if view['previous_review'] else None,
                'before_digest': expected_digest, 'after_digest': _current(after), 'target_policy_digest': view['policy_digest'],
                'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                'provider_reference_digest': canonical_hash(provider_reference),
                'generation_digest': canonical_hash(row['credential_generation']),
                'before_expires_at': original['expires_at'], 'after_expires_at': row['expires_at'],
                'at': _time(now()), 'provenance': 'operator_recorded_provider_change',
                'workers_drained': True, 'activation_allowed': False}
            await current.outreach_proxy_lifecycle_reviews.insert_one(journal)
            if not await valid_history(authority, row, workspace):
                raise CustodyUnavailable('Proxy change final authority changed')
            result = await self._saved(current, journal, request_digest, workspace, asset)
            _final(view, row)
            return result
        return await suppression.mutate_suppression(self.db, workspace, install)
