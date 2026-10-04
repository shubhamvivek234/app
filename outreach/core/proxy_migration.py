"""Private drained migration of one managed proxy asset and its exact sender copies."""
from datetime import datetime, timezone
import os
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core import suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.credential_migration import _stable
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.paid_access import _utc, live_actions_enabled
from outreach.core.proxy_custody import proxy_digest, seal_proxy_password
from outreach.core.sender_execution import SenderExecution
from outreach.core.session_custody import custody_mode
from utils.encryption import decrypt_strict


def _authority(current, key):
    return (AuthorityDatabase(current.database, current.session, key)
        if isinstance(current, suppression.SuppressionDatabase) else current)


def _material(snapshot):
    return canonical_hash({'inventory': proxy_digest(snapshot['inventory'] or {}),
        'accounts': [{name: row.get(name) for name in ('id', 'proxy', 'proxy_config')}
            for row in snapshot['accounts']]})


class ProxyMigration:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def _snapshot(self, current, workspace, asset):
        inventory = await current.outreach_proxy_inventory.find_one({'_id': asset})
        lease = await current.outreach_proxy_leases.find_one({'_id': asset})
        accounts = await current.outreach_accounts.find({'workspace_id': workspace, '$or': [
            {'proxy.proxy_id': asset}, {'proxy_config.proxy_id': asset}]}).sort('_id', 1).limit(2).to_list(length=2)
        senders = sorted({row['id'] for row in accounts} | ({lease['sender_id']} if lease and lease.get('sender_id') else set()))
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
        return {'inventory': _stable(inventory), 'lease': _stable(lease), 'accounts': [_stable(row) for row in accounts],
            'execution': [_stable(row) for row in execution], 'jobs': _stable(jobs), 'locks': _stable(locks),
            'physical': _stable(physical), 'campaigns': _stable(campaigns)}

    @staticmethod
    def _blockers(snapshot, workspace):
        inventory, lease, accounts = snapshot['inventory'] or {}, snapshot['lease'], snapshot['accounts']
        blockers = []
        if (not inventory or inventory.get('provider') != 'iproyal_static' or inventory.get('status') != 'available'
                or inventory.get('last_workspace_id') != workspace or inventory.get('workspace_id', workspace) != workspace
                or not _utc(inventory.get('expires_at')) or _utc(inventory['expires_at']) <= datetime.now(timezone.utc)):
            blockers.append('asset_unavailable_or_unowned')
        if lease and (lease.get('workspace_id') != workspace or not lease.get('sender_id')):
            blockers.append('lease_scope_ambiguous')
        if len(accounts) > 1 or (accounts and (not lease or lease.get('sender_id') != accounts[0].get('id'))) or (lease and not accounts):
            blockers.append('sender_binding_ambiguous')
        for account in accounts:
            if (account.get('is_deleted') or account.get('status') not in {'paused', 'reauth_required', 'disconnected'}
                    or (account.get('connection_finalization') or {}).get('state') in {'prepared', 'installed'}):
                blockers.append('sender_not_stopped')
            for name in ('proxy', 'proxy_config'):
                if account.get(name) and proxy_digest(account[name]) != proxy_digest(inventory):
                    blockers.append('embedded_asset_changed')
        for execution in snapshot['execution']:
            if (not execution or execution.get('status') != 'idle' or execution.get('owner_token')
                    or execution.get('physical_request_token') or (execution.get('permission') or {}).get('latched') is not True):
                blockers.append('execution_not_stopped')
        blockers.extend(name + '_unfinished' for name in ('jobs', 'locks', 'physical', 'campaigns') if snapshot[name])
        return sorted(set(blockers))

    async def inspect(self, workspace: str, asset: str) -> dict[str, Any]:
        snapshot = await self._snapshot(self.db, workspace, asset)
        return {'workspace_id': workspace, 'proxy_id': asset, 'digest': canonical_hash(snapshot),
            'sender_ids': [row['id'] for row in snapshot['accounts']], 'blockers': self._blockers(snapshot, workspace)}

    async def _receipt(self, receipt, workspace, asset):
        current = await self._snapshot(self.db, workspace, asset)
        return {'status': 'completed', 'migration_id': receipt['_id'], 'current_matches': _material(current) == receipt['after_digest']}

    async def migrate(self, workspace: str, asset: str, operator: str, expected_digest: str, *, workers_drained: bool = False) -> dict[str, Any]:
        if (workers_drained is not True or not operator or not operator.strip() or not expected_digest
                or live_actions_enabled() or custody_mode() != 'kms_v1'):
            raise CustodyUnavailable('Stopped execution and identified drained proxy migration are required')
        key = canonical_hash(['proxy-migration-v1', workspace, asset, expected_digest])
        scope = {'_id': key, 'workspace_id': workspace}
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await self._receipt(receipt, workspace, asset)
        async def verify(current):
            snapshot = await self._snapshot(_authority(current, key), workspace, asset)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot, workspace):
                raise CustodyUnavailable('Drained proxy inspection changed')
            return snapshot
        snapshot = await suppression.mutate_suppression(self.db, workspace, verify)
        inventory = snapshot['inventory']
        try:
            password = decrypt_strict(inventory.get('password_enc') or '')
        except (ValueError, OSError):
            raise CustodyUnavailable('Legacy proxy requires separate credential provenance review') from None
        # Key-service calls are outside both database-only transactions. Retries
        # reuse this ciphertext; installed cookie generation and leases do not change.
        encrypted = await seal_proxy_password(password, inventory, workspace, generation=inventory.get('credential_generation'))
        del password
        async def apply(current):
            fenced = _authority(current, key)
            saved = await current.outreach_credential_migrations.find_one(scope)
            fresh = await self._snapshot(fenced, workspace, asset)
            if saved:
                return {'status': 'completed', 'migration_id': key, 'current_matches': _material(fresh) == saved['after_digest']}
            if (canonical_hash(fresh) != expected_digest or self._blockers(fresh, workspace)
                    or live_actions_enabled() or custody_mode() != 'kms_v1'):
                raise CustodyUnavailable('Drained proxy inspection changed')
            changed = await fenced.outreach_proxy_inventory.update_one({'_id': asset, 'last_workspace_id': workspace,
                'workspace_id': inventory.get('workspace_id') if 'workspace_id' in inventory else {'$exists': False},
                'password_enc': inventory['password_enc']}, {'$set': {**encrypted, 'workspace_id': workspace}})
            if changed.matched_count != 1: raise CustodyUnavailable('Proxy owner changed')
            after = {**fresh, 'inventory': {**inventory, **encrypted, 'workspace_id': workspace}, 'accounts': []}
            for account in fresh['accounts']:
                updates = {name: {**account[name], **encrypted} for name in ('proxy', 'proxy_config') if account.get(name)}
                changed = await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': account['id'],
                    **{name: account.get(name) if name in account else {'$exists': False} for name in ('proxy', 'proxy_config')}}, {'$set': updates})
                if changed.matched_count != 1: raise CustodyUnavailable('Embedded proxy owner changed')
                after['accounts'].append({**account, **updates})
            await current.outreach_credential_migrations.insert_one({**scope, 'kind': 'proxy', 'proxy_id': asset, 'status': 'completed',
                'sender_ids': [row['id'] for row in fresh['accounts']], 'operator': operator.strip(), 'workers_drained': True,
                'before_digest': expected_digest, 'after_digest': _material(after), 'at': datetime.now(timezone.utc),
                'target_environment_digest': canonical_hash(os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', ''))})
            return {'status': 'completed', 'migration_id': key, 'current_matches': True}
        return await suppression.mutate_suppression(self.db, workspace, apply)
