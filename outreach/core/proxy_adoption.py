"""Stopped storage adoption of legacy Webshare with retained original evidence.

No missing purchase/owner facts, vendor requests or activation are supplied.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.proxy_custody import BINDING_FIELDS, policy, seal_proxy_password
from outreach.core.proxy_identity import identity, raw_options, require_ip_binding
from outreach.core.proxy_lifecycle_proof import ADOPTION_FIELDS, FIELDS, adoption_material, valid_history
from outreach.core.proxy_lifecycle import _password
from outreach.core.proxy_migration import HEX, ProxyMigration, _authority, _material, _reference, _stable, flags_off
from outreach.core.session_custody import custody_mode
from outreach.core.webshare_provisioning import BASIS_FIELDS, _basis, _time
from utils.encryption import decrypt_strict
from outreach.models import ProxyStatus

LEGACY_FIELDS = (set(BASIS_FIELDS) - {'request_digest', 'managed_webshare_version'}) | {
    'status', 'password_enc', 'created_at', 'provider_auto_renew_confirmed', 'dispatch_fence_revision'}
ALIAS_FIELDS = set(BINDING_FIELDS) | {'status', 'assigned_at', 'last_health_check'}


def _alias_shape(row: Any) -> bool:
    try:
        if not isinstance(row, dict) or not set(row).issubset(ALIAS_FIELDS):
            return False
        if 'status' in row and row['status'] not in {item.value for item in ProxyStatus}:
            return False
        for field in ('assigned_at', 'last_health_check'):
            if field in row:
                _time(row[field])
        return True
    except (TypeError, ValueError):
        return False


def _original(row: dict, workspace: str) -> bool:
    """Require retained purchase and transport facts, never caller replacements."""
    try:
        if not set(row).issubset(LEGACY_FIELDS):
            return False
        if any(not isinstance(row.get(field), datetime) for field in ('verified_at', 'expires_at')):
            return False
        if 'created_at' in row:
            _time(row['created_at'])
        if 'provider_auto_renew_confirmed' in row and type(row['provider_auto_renew_confirmed']) is not bool:
            return False
        for field in ('provider_plan_id', 'provider_resource_id', 'provider_order_id', 'verified_by', 'username'):
            _reference(row[field])
        if ':' in row['provider_plan_id'] or ':' in row['provider_resource_id']:
            return False
        identity(row['host'], workspace, row['_id'], row['provider'])
        return bool(row.get('provider') == 'webshare_plan' and row.get('status') == 'available'
            and row.get('workspace_id') == row.get('last_workspace_id') == workspace
            and row['_id'] == f"webshare:{row['provider_plan_id']}:{row['provider_resource_id']}"
            and type(row.get('port')) is int and 1 <= row['port'] <= 65535
            and re.fullmatch('[A-Z]{2}', row.get('country_code', ''))
            and row.get('dedicated_isp_confirmed') is True
            and isinstance(row.get('evidence_digest'), str) and HEX.fullmatch(row['evidence_digest'])
            and _time(row['verified_at']) <= datetime.now(timezone.utc) < _time(row['expires_at']))
    except (KeyError, TypeError, ValueError, CustodyUnavailable):
        return False


def _current(view: dict) -> str:
    return canonical_hash([_material(view), adoption_material(view['inventory'] or {})])


def _final(view: dict) -> None:
    """Pure last authority check after every awaited installation readback."""
    if (not flags_off() or custody_mode() != 'kms_v1' or view['policy_digest'] != canonical_hash(policy())
            or _time(view['inventory']['expires_at']) <= datetime.now(timezone.utc)):
        raise CustodyUnavailable('Legacy proxy final authority changed')


class ProxyAdoption:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, current: Any, workspace: str, asset: str) -> dict:
        view = await ProxyMigration(self.db)._snapshot(current, workspace, asset)
        row = view['inventory'] or {}
        raw, options = raw_options(current)
        try:
            proof = identity(row['host'], workspace, asset, row['provider'])
            claim = await raw.account_proxy_ip_guards.find_one({'_id': proof['_id']}, **options)
            claim_state = ('absent' if not claim else 'matching'
                if claim.get('binding_digest') == proof['binding_digest'] else 'conflict')
            inventory_collision = bool(await raw.outreach_proxy_inventory.count_documents(
                {'host': row['host'], '_id': {'$ne': asset}}, **options))
            count = await raw.outreach_accounts.count_documents({'$or': [
                {'proxy.host': row['host']}, {'proxy_config.host': row['host']},
                {'proxy.proxy_id': asset}, {'proxy_config.proxy_id': asset}]}, **options)
            account_collision = count != len(view['accounts'])
        except (KeyError, ValueError, TypeError):
            claim_state, inventory_collision, account_collision = 'invalid', True, True
        view.update(ip_claim_state=claim_state, inventory_collision=inventory_collision,
            account_collision=account_collision, adoption_exists=bool(await current.outreach_proxy_adoptions.find_one(
                {'workspace_id': workspace, 'proxy_id': asset})))
        return _stable(view)

    @staticmethod
    def _blockers(view: dict, workspace: str) -> list[str]:
        reasons = [reason for reason in ProxyMigration._blockers(view, workspace)
            if reason not in {'original_webshare_assignment_unproven'}]
        row = view['inventory'] or {}
        if not _original(row, workspace):
            reasons.append('retained_original_purchase_owner_term_required')
        if any(account.get(name) and not _alias_shape(account[name])
                for account in view['accounts'] for name in ('proxy', 'proxy_config')):
            reasons.append('original_embedded_proxy_shape_required')
        if any(field in row for field in ('managed_webshare_version', 'import_basis_digest', 'request_digest', *FIELDS, *ADOPTION_FIELDS)) or view['adoption_exists']:
            reasons.append('original_unmanaged_source_required')
        value = row.get('password_enc')
        if not isinstance(value, str) or not value.startswith('gAAAAA'):
            reasons.append('original_strict_fernet_required')
        generation = row.get('credential_generation')
        if generation not in (None, ''):
            try:
                _reference(generation)
            except CustodyUnavailable:
                reasons.append('original_generation_invalid')
        if view['ip_claim_state'] not in ('absent', 'matching') or view['inventory_collision'] or view['account_collision']:
            reasons.append('physical_assignment_ambiguous')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, asset: str) -> dict:
        _reference(workspace); _reference(asset)
        view = await self._view(self.db, workspace, asset)
        return {'workspace_id': workspace, 'proxy_id': asset, 'digest': canonical_hash(view),
            'blockers': self._blockers(view, workspace), 'activation_allowed': False}

    async def _saved(self, current: Any, receipt: dict, request: str, workspace: str, asset: str) -> dict:
        if receipt.get('status') != 'completed' or receipt.get('request_digest') != request:
            raise CustodyUnavailable('A different legacy proxy review is already saved')
        view = await self._view(_authority(current, receipt['_id']), workspace, asset)
        return {'status': 'completed', 'adoption_id': receipt['_id'],
            'current_matches': _current(view) == receipt['after_digest'] and view['lifecycle_history_valid']
                and view['restore_reuse_allowed']
                and not view['inventory_collision'] and not view['account_collision'],
            'configuration_matches': view['policy_digest'] == receipt['target_policy_digest'], 'activation_allowed': False}

    async def adopt(self, workspace: str, asset: str, operator: str, evidence_digest: str,
                    expected_digest: str, *, workers_drained: bool = False) -> dict:
        for value in (workspace, asset, operator):
            _reference(value)
        if (workers_drained is not True or not flags_off() or custody_mode() != 'kms_v1'
                or any(not isinstance(value, str) or not HEX.fullmatch(value) for value in (evidence_digest, expected_digest))):
            raise CustodyUnavailable('Exact disabled-gate evidence and all-writer/cache drain are required')
        key = canonical_hash(['legacy-proxy-adoption-v1', workspace, asset])
        scope = {'workspace_id': workspace, '_id': key}
        request = canonical_hash([workspace, asset, operator, evidence_digest, expected_digest])
        receipt = await self.db.outreach_proxy_adoptions.find_one(scope)
        if receipt:
            return await self._saved(self.db, receipt, request, workspace, asset)

        async def verify(current: Any, digest: str) -> dict:
            view = await self._view(_authority(current, key), workspace, asset)
            if canonical_hash(view) != digest or self._blockers(view, workspace):
                raise CustodyUnavailable('Original legacy proxy inspection changed')
            return view

        async def preflight(current: Any) -> dict:
            saved = await current.outreach_proxy_adoptions.find_one(scope)
            if saved:
                return {'completed': await self._saved(current, saved, request, workspace, asset)}
            view = await verify(current, expected_digest)
            if not await require_ip_binding(current, view['inventory'], workspace, claim=True):
                raise CustodyUnavailable('Original physical assignment changed')
            after = await self._view(_authority(current, key), workspace, asset)
            comparable = {**after, 'ip_binding': view['ip_binding'], 'ip_claim_state': view['ip_claim_state']}
            if canonical_hash(comparable) != expected_digest:
                raise CustodyUnavailable('Original proxy claim inspection changed')
            _final(after)
            return {'view': after}

        captured = await suppression.mutate_suppression(self.db, workspace, preflight)
        if 'completed' in captured:
            return captured['completed']
        view = captured['view']; original = view['inventory']; row = deepcopy(original)
        try:
            password = _password(decrypt_strict(original['password_enc']))
        except (TypeError, ValueError, OSError):
            raise CustodyUnavailable('Original legacy credentials are unproven') from None
        encrypted = await seal_proxy_password(password, original, workspace, generation=original.get('credential_generation'))
        del password
        _final(view)
        row.update(encrypted, managed_webshare_version=1, request_digest=request,
            proxy_adoption_id=key, proxy_adoption_source_digest=canonical_hash(original))
        row['import_basis_digest'] = _basis(row)
        fields = (*encrypted, 'managed_webshare_version', 'request_digest', 'proxy_adoption_id',
            'proxy_adoption_source_digest', 'import_basis_digest')

        async def install(current: Any) -> dict:
            saved = await current.outreach_proxy_adoptions.find_one(scope)
            if saved:
                return await self._saved(current, saved, request, workspace, asset)
            fresh = await verify(current, canonical_hash(view)); authority = _authority(current, key)
            changed = await authority.outreach_proxy_inventory.update_one({'workspace_id': workspace, '_id': asset,
                'last_workspace_id': workspace, 'password_enc': original['password_enc'],
                'managed_webshare_version': {'$exists': False}}, {'$set': {field: row[field] for field in fields}})
            if changed.matched_count != 1:
                raise CustodyUnavailable('Original legacy proxy owner changed')
            for account in fresh['accounts']:
                updates = {name: {**account[name], **encrypted} for name in ('proxy', 'proxy_config') if account.get(name)}
                changed = await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': account['id'],
                    **{name: account.get(name) if name in account else {'$exists': False}
                        for name in ('proxy', 'proxy_config')}}, {'$set': updates})
                if changed.matched_count != 1:
                    raise CustodyUnavailable('Original legacy sender copy changed')
            after = await self._view(authority, workspace, asset)
            receipt = {**scope, 'proxy_id': asset, 'status': 'completed', 'request_digest': request,
                'before_digest': expected_digest, 'after_digest': _current(after),
                'source_digest': row['proxy_adoption_source_digest'], 'adopted_basis_digest': row['import_basis_digest'],
                'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                'original_evidence_digest': original['evidence_digest'],
                'original_order_digest': canonical_hash(original['provider_order_id']),
                'original_operator_digest': canonical_hash(original['verified_by']),
                'original_verified_at': original['verified_at'], 'provider_term_expires_at': original['expires_at'],
                'target_policy_digest': view['policy_digest'], 'generation_digest': canonical_hash(encrypted['credential_generation']),
                'generation_created': not bool(original.get('credential_generation')),
                'at': _time(datetime.now(timezone.utc)), 'provenance': 'retained_legacy_evidence_storage_adoption',
                'workers_drained': True, 'activation_allowed': False}
            await current.outreach_proxy_adoptions.insert_one(receipt)
            if not await valid_history(authority, row, workspace):
                raise CustodyUnavailable('Original proxy adoption proof changed')
            result = await self._saved(current, receipt, request, workspace, asset)
            _final(view)
            return result

        return await suppression.mutate_suppression(self.db, workspace, install)
