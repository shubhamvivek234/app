"""Private drained migration of one managed proxy asset and its exact sender copies."""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timezone
import re
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.paid_access import _utc, live_actions_enabled
from outreach.core.proxy_custody import policy, proxy_digest, seal_proxy_password
from outreach.core.proxy_identity import require_ip_binding, restore_ip_allowed
from outreach.core.sender_execution import SenderExecution
from outreach.core.session_custody import custody_mode
from utils.encryption import decrypt_strict

HEX = re.compile(r'[a-f0-9]{64}\Z')


def _stable(value: Any, *, timestamps: bool = True) -> Any:
    """Hash the same UTC millisecond representation before/after BSON storage."""
    if isinstance(value, dict):
        return {key: _stable(item, timestamps=timestamps) for key, item in value.items() if key != 'dispatch_fence_revision'}
    if isinstance(value, list):
        return [_stable(item, timestamps=timestamps) for item in value]
    if timestamps and isinstance(value, datetime):
        return _utc(value).replace(microsecond=value.microsecond // 1000 * 1000)
    return value


def flags_off() -> bool:
    from outreach.core.integrations_pilot import integrations_enabled
    from outreach.core.voice_policy import preparation_enabled
    from outreach.core.voice_studio import enabled
    return not (live_actions_enabled() or integrations_enabled() or preparation_enabled() or enabled())


def _reference(value: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise CustodyUnavailable('A bounded private record reference is required')


def _authority(current: Any, key: str) -> Any:
    return (AuthorityDatabase(current.database, current.session, key)
        if isinstance(current, suppression.SuppressionDatabase) else current)


def _material(snapshot: dict, *, version: int = 2) -> str:
    result = {'inventory': proxy_digest(snapshot['inventory'] or {}),
        'accounts': [{name: row.get(name) for name in ('id', 'proxy', 'proxy_config')}
            for row in snapshot['accounts']]}
    if version >= 2:
        row = snapshot['inventory'] or {}
        from outreach.core.webshare_provisioning import BASIS_FIELDS
        fields = BASIS_FIELDS if row.get('provider') == 'webshare_plan' else (
            'workspace_id', 'last_workspace_id', 'expires_at', 'provider_order_id')
        result.update({'asset_basis': {key: row.get(key) for key in (*fields, 'import_basis_digest', 'status')},
            'ip_binding': snapshot['ip_binding'],
            'lease': snapshot['lease']})
    return canonical_hash(_stable(result, timestamps=version >= 2))


class ProxyMigration:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, asset: str, *, timestamps: bool = True) -> dict:
        inventory = await current.outreach_proxy_inventory.find_one({'_id': asset})
        lease = await current.outreach_proxy_leases.find_one({'_id': asset})
        accounts = await current.outreach_accounts.find({'workspace_id': workspace, '$or': [
            {'proxy.proxy_id': asset}, {'proxy_config.proxy_id': asset}]}).sort('_id', 1).limit(2).to_list(length=2)
        senders = sorted({row.get('id') for row in accounts if isinstance(row.get('id'), str) and row['id']}
            | ({lease['sender_id']} if lease and isinstance(lease.get('sender_id'), str) and lease['sender_id'] else set()))
        execution = [await current.outreach_sender_execution.find_one(SenderExecution.scope(workspace, sender)) for sender in senders]
        jobs = await current.outreach_connection_jobs.find_one({'workspace_id': workspace, '$and': [
            {'$or': [{'proxy_id': asset}, {'sender_id': {'$in': senders}}]},
            {'$or': [{'status': {'$in': ['queued', 'running', 'finalizing', 'repairing']}}, {'needs_operator_repair': True}]}]})
        locks = await current.outreach_connection_locks.find_one({'workspace_id': workspace, '$or': [
            {'_id': {'$in': senders}}, {'storage_proof.proxy_id': asset}]})
        physical = await current.outreach_physical_requests.find_one({'workspace_id': workspace, 'sender_id': {'$in': senders},
            'status': {'$in': ['preparing', 'in_flight', 'unknown_outcome']}})
        campaigns = await current.outreach_campaigns.find_one({'workspace_id': workspace, '$or': [{'sender_account_ids': sender} for sender in senders] or [{'sender_account_ids': {'$in': []}}],
            'status': {'$in': ['active', 'warming_up']}})
        ip_binding = None
        if inventory and inventory.get('provider') == 'webshare_plan':
            try:
                ip_binding = await require_ip_binding(current, inventory, workspace)
            except (ValueError, TypeError, KeyError):
                ip_binding = False
        from outreach.core.proxy_lifecycle_proof import valid_history
        history_valid = await valid_history(current, inventory, workspace) if inventory else True
        restore_allowed = await restore_ip_allowed(current, inventory.get('host')) if inventory else True
        return _stable({'inventory': inventory, 'lease': lease, 'accounts': accounts,
            'execution': execution, 'jobs': jobs, 'locks': locks, 'physical': physical, 'campaigns': campaigns,
            'ip_binding': ip_binding, 'lifecycle_history_valid': history_valid, 'restore_reuse_allowed': restore_allowed,
            'workspace_open': await erasure.workspace_is_open(current, workspace),
            'policy_digest': canonical_hash(policy()), 'flags_off': flags_off()}, timestamps=timestamps)

    @staticmethod
    def _blockers(snapshot: dict, workspace: str) -> list[str]:
        inventory, lease, accounts = snapshot['inventory'] or {}, snapshot['lease'], snapshot['accounts']
        blockers = []
        try:
            expiry = _utc(inventory.get('expires_at'))
        except (AttributeError, TypeError, ValueError):
            expiry = None
        if (not inventory or inventory.get('provider') not in ('iproyal_static', 'webshare_plan') or inventory.get('status') != 'available'
                or inventory.get('last_workspace_id') != workspace or inventory.get('workspace_id', workspace) != workspace
                or not expiry or expiry <= datetime.now(timezone.utc)):
            blockers.append('asset_unavailable_or_unowned')
        if not snapshot['workspace_open']:
            blockers.append('workspace_closed')
        if not snapshot['lifecycle_history_valid']:
            blockers.append('proxy_lifecycle_history_unproven')
        if snapshot.get('restore_reuse_allowed') is not True:
            blockers.append('proxy_restore_reconciliation_required')
        if not snapshot['flags_off'] or custody_mode() != 'kms_v1':
            blockers.append('disabled_flags_and_scoped_destination_required')
        value = inventory.get('password_enc')
        if (not isinstance(value, str) or not 1 <= len(value) <= 16384 or value.startswith(PREFIX)
                or inventory.get('custody_workspace_id') not in (None, workspace)):
            blockers.append('original_strict_fernet_required')
        if inventory.get('provider') == 'webshare_plan':
            from outreach.core.webshare_provisioning import webshare_basis_valid
            if not webshare_basis_valid(inventory, workspace) or snapshot['ip_binding'] is not True:
                blockers.append('original_webshare_assignment_unproven')
            if lease and any(lease.get(key) != inventory.get(key) for key in ('provider', 'country_code')):
                blockers.append('lease_scope_ambiguous')
        if lease and (lease.get('workspace_id') != workspace or not lease.get('sender_id')):
            blockers.append('lease_scope_ambiguous')
        if len(accounts) > 1 or (accounts and (not lease or lease.get('sender_id') != accounts[0].get('id'))) or (lease and not accounts):
            blockers.append('sender_binding_ambiguous')
        for account in accounts:
            finalization = account.get('connection_finalization') or {}
            if (not isinstance(account.get('id'), str) or not account['id'] or account.get('is_deleted')
                    or account.get('status') not in ('paused', 'reauth_required', 'disconnected')
                    or not isinstance(finalization, dict) or finalization.get('state') in ('prepared', 'installed')):
                blockers.append('sender_not_stopped')
            for name in ('proxy', 'proxy_config'):
                try:
                    matches = not account.get(name) or proxy_digest(account[name]) == proxy_digest(inventory)
                except (CustodyUnavailable, TypeError, ValueError):
                    matches = False
                if not matches:
                    blockers.append('embedded_asset_changed')
        for execution in snapshot['execution']:
            permission = (execution or {}).get('permission') or {}
            if (not execution or execution.get('status') != 'idle' or execution.get('owner_token')
                    or execution.get('physical_request_token') or not isinstance(permission, dict) or permission.get('latched') is not True):
                blockers.append('execution_not_stopped')
        blockers.extend(name + '_unfinished' for name in ('jobs', 'locks', 'physical', 'campaigns') if snapshot[name])
        return sorted(set(blockers))

    async def inspect(self, workspace: str, asset: str) -> dict[str, Any]:
        _reference(workspace); _reference(asset)
        snapshot = await self._snapshot(self.db, workspace, asset)
        return {'workspace_id': workspace, 'proxy_id': asset, 'digest': canonical_hash(snapshot),
            'sender_ids': [row.get('id') for row in snapshot['accounts'] if isinstance(row.get('id'), str)],
            'blockers': self._blockers(snapshot, workspace), 'activation_allowed': False}

    async def _receipt(self, current: Any, receipt: dict, workspace: str, asset: str,
                       operator: str, evidence: str | None) -> dict:
        if (receipt.get('operator_digest', canonical_hash(receipt.get('operator'))) != canonical_hash(operator.strip())
                or receipt.get('evidence_digest') != evidence):
            raise CustodyUnavailable('A different proxy migration review is already saved')
        version = receipt.get('material_version', 1)
        snapshot = await self._snapshot(_authority(current, receipt['_id']), workspace, asset, timestamps=version >= 2)
        return {'status': 'completed', 'migration_id': receipt['_id'],
            'current_matches': _material(snapshot, version=version) == receipt['after_digest']
                and snapshot['restore_reuse_allowed'],
            'configuration_matches': receipt.get('target_policy_digest') == canonical_hash(policy()),
            'activation_allowed': False}

    async def migrate(self, workspace: str, asset: str, operator: str, expected_digest: str, *, workers_drained: bool = False,
                      evidence_digest: str | None = None) -> dict[str, Any]:
        _reference(workspace); _reference(asset)
        if (workers_drained is not True or not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in operator)
                or not isinstance(expected_digest, str) or not HEX.fullmatch(expected_digest)
                or evidence_digest is not None and (not isinstance(evidence_digest, str) or not HEX.fullmatch(evidence_digest))
                or not flags_off() or custody_mode() != 'kms_v1'):
            raise CustodyUnavailable('Stopped execution and identified drained proxy migration are required')
        key = canonical_hash(['proxy-migration-v1', workspace, asset, expected_digest])
        scope = {'_id': key, 'workspace_id': workspace}
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await self._receipt(self.db, receipt, workspace, asset, operator, evidence_digest)
        async def verify(current):
            snapshot = await self._snapshot(_authority(current, key), workspace, asset)
            if (canonical_hash(snapshot) != expected_digest or self._blockers(snapshot, workspace)
                    or snapshot['inventory'].get('provider') == 'webshare_plan' and evidence_digest is None):
                raise CustodyUnavailable('Drained proxy inspection changed')
            return snapshot
        async def preflight(current):
            # Exact concurrent completion wins before original-source checks or key work.
            saved = await current.outreach_credential_migrations.find_one(scope)
            if saved:
                return {'completed': await self._receipt(current, saved, workspace, asset, operator, evidence_digest)}
            return {'snapshot': await verify(current)}
        inspected = await suppression.mutate_suppression(self.db, workspace, preflight)
        if 'completed' in inspected: return inspected['completed']
        snapshot = inspected['snapshot']
        inventory = snapshot['inventory']
        try:
            password = decrypt_strict(inventory.get('password_enc') or '')
        except (ValueError, OSError, TypeError):
            raise CustodyUnavailable('Legacy proxy requires separate credential provenance review') from None
        # Key-service calls are outside both database-only transactions. Retries
        # reuse this ciphertext; installed cookie generation and leases do not change.
        encrypted = await seal_proxy_password(password, inventory, workspace, generation=inventory.get('credential_generation'))
        del password
        if snapshot['policy_digest'] != canonical_hash(policy()) or not flags_off():
            raise CustodyUnavailable('Proxy migration custody policy changed')
        async def apply(current):
            fenced = _authority(current, key)
            saved = await current.outreach_credential_migrations.find_one(scope)
            if saved:
                return await self._receipt(current, saved, workspace, asset, operator, evidence_digest)
            fresh = await self._snapshot(fenced, workspace, asset)
            if (canonical_hash(fresh) != expected_digest or self._blockers(fresh, workspace)
                    or not flags_off() or snapshot['policy_digest'] != canonical_hash(policy())):
                raise CustodyUnavailable('Drained proxy inspection changed')
            changed = await fenced.outreach_proxy_inventory.update_one({'_id': asset, 'last_workspace_id': workspace,
                'workspace_id': inventory.get('workspace_id') if 'workspace_id' in inventory else {'$exists': False},
                'password_enc': inventory['password_enc']}, {'$set': {**encrypted, 'workspace_id': workspace}})
            if changed.matched_count != 1: raise CustodyUnavailable('Proxy owner changed')
            for account in fresh['accounts']:
                updates = {name: {**account[name], **encrypted} for name in ('proxy', 'proxy_config') if account.get(name)}
                changed = await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': account['id'],
                    **{name: account.get(name) if name in account else {'$exists': False} for name in ('proxy', 'proxy_config')}}, {'$set': updates})
                if changed.matched_count != 1: raise CustodyUnavailable('Embedded proxy owner changed')
            after = await self._snapshot(fenced, workspace, asset)
            receipt = {**scope, 'kind': 'proxy', 'proxy_id': asset, 'status': 'completed', 'material_version': 2,
                'sender_ids': [row['id'] for row in fresh['accounts']], 'operator_digest': canonical_hash(operator.strip()),
                'evidence_digest': evidence_digest, 'workers_drained': True, 'activation_allowed': False,
                'provenance': 'strict_fernet_storage_conversion', 'provider': inventory['provider'],
                'before_digest': expected_digest, 'after_digest': _material(after), 'at': datetime.now(timezone.utc),
                'target_policy_digest': snapshot['policy_digest'], 'generation_digest': canonical_hash(encrypted['credential_generation']),
                'original_basis_digest': inventory.get('import_basis_digest')}
            await current.outreach_credential_migrations.insert_one(receipt)
            if (not flags_off() or snapshot['policy_digest'] != canonical_hash(policy())
                    or _utc(inventory['expires_at']) <= datetime.now(timezone.utc)):
                raise CustodyUnavailable('Proxy migration custody policy changed')
            return await self._receipt(current, receipt, workspace, asset, operator, evidence_digest)
        return await suppression.mutate_suppression(self.db, workspace, apply)
