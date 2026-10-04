"""Drained stop-only closure for proven pre-installation connection storage orphans.

An absent job alone proves nothing. Protocol-one locks capture the base account
and exact resource ownership before the attempted insert. Older ambiguous locks
and any verification/installation evidence remain held for separate review.
"""
from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core import suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.credential_migration import _stable
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.manual_resolution import require_review
from outreach.core.paid_access import live_actions_enabled
from outreach.core.sender_execution import SenderExecution


def storage_account_digest(account: dict[str, Any] | None) -> str:
    if account is None: return canonical_hash(None)
    return canonical_hash({name: account.get(name) for name in ('id', 'workspace_id', 'is_deleted', 'credential_generation',
        'session_cookie_enc', 'encrypted_session_cookie', 'li_at_enc', 'jsession_id', 'jsession_id_enc', 'li_a_enc',
        'proxy', 'proxy_config', 'connection_finalization', 'linkedin_urn', 'country_code')})


class ConnectionStorageRepair:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def _snapshot(self, current, workspace, job_id):
        lock = await current.outreach_connection_locks.find_one({'workspace_id': workspace, 'job_id': job_id})
        if not lock: raise CustodyUnavailable('Storage owner reference is unavailable')
        sender = lock['_id']
        proof = lock.get('storage_proof') or {}
        job = await current.outreach_connection_jobs.find_one({'workspace_id': workspace, 'id': job_id})
        account = await current.outreach_accounts.find_one({'workspace_id': workspace, 'id': sender})
        execution = await current.outreach_sender_execution.find_one(SenderExecution.scope(workspace, sender))
        slot = await current.outreach_sender_slots.find_one({'workspace_id': workspace, 'sender_id': sender})
        lease = await current.outreach_proxy_leases.find_one({'_id': proof.get('proxy_id'), 'workspace_id': workspace, 'sender_id': sender})
        physical = await current.outreach_physical_requests.find_one({'workspace_id': workspace, 'sender_id': sender, '$or': [
            {'credential_generation': 'pending:' + job_id}, {'status': {'$in': ['preparing', 'in_flight', 'unknown_outcome']}}]})
        # Also fence every active campaign that this stop will pause. A bounded
        # pilot limit refuses extra rows instead of silently leaving work active.
        campaigns = await current.outreach_campaigns.find({'workspace_id': workspace, 'sender_account_ids': sender,
            'status': {'$in': ['active', 'warming_up']}}).sort('_id', 1).limit(101).to_list(length=101)
        return {'lock': _stable(lock), 'job': _stable(job), 'account': _stable(account), 'execution': _stable(execution),
            'slot': _stable(slot), 'lease': _stable(lease), 'physical': _stable(physical), 'campaigns': [_stable(row) for row in campaigns]}

    @staticmethod
    def _blockers(snapshot):
        lock = snapshot['lock']; proof = lock.get('storage_proof') or {}; account = snapshot['account']; execution = snapshot['execution'] or {}
        reasons = []
        if (lock.get('installation_protocol') != 2 or lock.get('storage_protocol') != 1
                or not isinstance(proof.get('base_account_digest'), str) or not proof.get('proxy_id')
                or type(proof.get('created_slot')) is not bool or type(proof.get('new_proxy_reservation')) is not bool):
            reasons.append('storage_provenance_unavailable')
        if snapshot['job']: reasons.append('job_present_requires_existing_job_review')
        if storage_account_digest(account) != proof.get('base_account_digest'): reasons.append('base_account_changed')
        if account and (account.get('is_deleted') or (account.get('connection_finalization') or {}).get('state') in {'prepared', 'installed'}
                or (account.get('connection_finalization') or {}).get('job_id') == lock['job_id']):
            reasons.append('installation_ambiguous')
        if execution and (execution.get('status') != 'idle' or execution.get('owner_token') or execution.get('physical_request_token')):
            reasons.append('execution_unfinished')
        if snapshot['physical']: reasons.append('verification_or_submission_evidence_present')
        for name, owned in (('slot', 'created_slot'), ('lease', 'new_proxy_reservation')):
            resource = snapshot[name]
            if proof.get(owned) and (not resource or resource.get('reservation_job_id') != lock['job_id']):
                reasons.append(name + '_owner_changed')
        if len(snapshot['campaigns']) > 100: reasons.append('campaign_capacity_exceeded')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, job_id: str) -> dict[str, Any]:
        snapshot = await self._snapshot(self.db, workspace, job_id)
        return {'workspace_id': workspace, 'job_id': job_id, 'sender_id': snapshot['lock']['_id'],
            'digest': canonical_hash(snapshot), 'blockers': self._blockers(snapshot),
            'account_present': snapshot['account'] is not None,
            'release_slot': (snapshot['lock'].get('storage_proof') or {}).get('created_slot') is True,
            'release_proxy_reservation': (snapshot['lock'].get('storage_proof') or {}).get('new_proxy_reservation') is True}

    async def resolve(self, workspace: str, job_id: str, operator: str, evidence: str, expected_digest: str, *, workers_drained: bool = False) -> dict[str, Any]:
        require_review(operator, evidence, workers_drained)
        if not expected_digest or live_actions_enabled():
            raise CustodyUnavailable('Disabled live actions and exact drained storage inspection are required')
        scope = {'workspace_id': workspace, 'id': job_id}
        key = canonical_hash(['storage-closure-v1', workspace, job_id])
        def result(row):
            if row.get('status') != 'storage_stopped' or (row.get('storage_closure') or {}).get('review_digest') != expected_digest:
                raise CustodyUnavailable('A different job or storage review is already saved')
            return {'status': 'storage_stopped', 'job_id': job_id, 'sender_id': row['sender_id'], 'repair_cleanup_complete': True}
        saved = await self.db.outreach_connection_jobs.find_one(scope)
        if saved and saved.get('storage_closure'): return result(saved)
        async def apply(current):
            fenced = (AuthorityDatabase(current.database, current.session, key)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            saved = await current.outreach_connection_jobs.find_one(scope)
            if saved and saved.get('storage_closure'): return result(saved)
            snapshot = await self._snapshot(fenced, workspace, job_id)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot) or live_actions_enabled():
                raise CustodyUnavailable('Drained storage inspection changed')
            lock = snapshot['lock']; proof = lock['storage_proof']; sender = lock['_id']; now = datetime.now(timezone.utc)
            # Stop authority before resource cleanup in the SAME transaction.
            # A missing execution row is created already latched, never granted.
            execution_scope = SenderExecution.scope(workspace, sender)
            await current.outreach_sender_execution.update_one(execution_scope, {'$set': {
                'permission.latched': True, 'permission.expires_at': now,
                'permission.stop_reason': 'connection_storage_repair', 'permission.stopped_by': operator.strip()},
                '$setOnInsert': {'status': 'idle'}, '$inc': {'permission_revision': 1},
                '$push': {'permission_history': {'event': 'revoke', 'operator': operator.strip(), 'reason': 'connection_storage_repair', 'at': now}}}, upsert=True)
            await current.outreach_execution_permissions.update_one(ExecutionPermission.scope(workspace, sender), {'$set': {
                'latched': True, 'expires_at': now, 'stop_reason': 'connection_storage_repair', 'stopped_by': operator.strip()}}, upsert=True)
            if snapshot['account']:
                changed = await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': sender}, {'$set': {'status': 'paused', 'updated_at': now}})
                if changed.matched_count != 1: raise CustodyUnavailable('Sender changed during storage review')
            for campaign in snapshot['campaigns']:
                changed = await current.outreach_campaigns.update_one({'workspace_id': workspace, '_id': campaign['_id'], 'status': campaign['status']}, {'$set': {'status': 'paused', 'updated_at': now}})
                if changed.matched_count != 1: raise CustodyUnavailable('Campaign changed during storage review')
            # No created_at: the ordinary pending-job TTL must not expire this
            # reference-only closure and let a late insertion recreate the job.
            closure = {**scope, '_id': key, 'sender_id': sender, 'proxy_id': proof['proxy_id'], 'status': 'storage_stopped',
                'repair_cleanup_complete': True, 'installation_protocol': 2, 'storage_closure': {
                    'operator': operator.strip(), 'evidence': evidence.strip(), 'workers_drained': True,
                    'review_digest': expected_digest, 'at': now, 'provenance': 'operator_inspection'}}
            await current.outreach_connection_jobs.insert_one(closure)
            for name, owned, collection in (('slot', 'created_slot', 'outreach_sender_slots'), ('lease', 'new_proxy_reservation', 'outreach_proxy_leases')):
                if proof[owned]:
                    resource = snapshot[name]
                    deleted = await getattr(current, collection).delete_one({'workspace_id': workspace, '_id': resource['_id'],
                        'sender_id': sender, 'reservation_job_id': job_id})
                    if deleted.deleted_count != 1: raise CustodyUnavailable('Reservation owner changed')
            deleted = await current.outreach_connection_locks.delete_one({'workspace_id': workspace, '_id': sender,
                'job_id': job_id, 'storage_proof': proof, 'storage_protocol': 1})
            if deleted.deleted_count != 1: raise CustodyUnavailable('Storage lock changed')
            return result(closure)
        return await suppression.mutate_suppression(self.db, workspace, apply)
