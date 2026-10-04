"""Private drained local stop; an unknown grant is never declared revoked."""
from datetime import datetime, timezone
from typing import Any

from outreach.core import suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_migration import _stable
from outreach.core.mailbox_jobs import ACTIVE_JOB_STATES, JOB_SECRETS, _fenced
from outreach.core.manual_resolution import require_review
from outreach.core.paid_access import _utc, live_actions_enabled
from outreach.core.sender_execution import SenderExecution
from outreach.core.execution_permission import ExecutionPermission


class OAuthHoldReview:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, db: Any, workspace: str, job_id: str) -> dict:
        job = await db.outreach_mailbox_connection_jobs.find_one({'workspace_id': workspace, 'id': job_id})
        if not job: raise ValueError('OAuth reference is unavailable')
        sender = job['sender_account_id']
        scope = {'workspace_id': workspace, 'sender_account_id': sender}
        snapshot = {'job': _stable(job),
            'mailbox': _stable(await db.outreach_mailboxes.find_one(scope)),
            'account': _stable(await db.outreach_accounts.find_one({'workspace_id': workspace, 'id': sender})),
            'execution': _stable(await db.outreach_sender_execution.find_one(SenderExecution.scope(workspace, sender))),
            'permission': _stable(await db.outreach_execution_permissions.find_one(ExecutionPermission.scope(workspace, sender)))}
        for name, collection, query in (
            ('jobs', 'outreach_mailbox_connection_jobs', {**scope, 'status': {'$in': list(ACTIVE_JOB_STATES)}}),
            ('states', 'outreach_mailbox_oauth_states', scope),
            ('sync_jobs', 'outreach_mailbox_sync_jobs', {**scope, 'status': {'$in': ['queued', 'running']}}),
            ('campaigns', 'outreach_campaigns', {'workspace_id': workspace, 'sender_account_ids': sender,
                'status': {'$in': ['active', 'warming_up']}})):
            snapshot[name] = [_stable(row) for row in await getattr(db, collection).find(query).sort('_id', 1).limit(101).to_list(length=101)]
        return snapshot

    @staticmethod
    def _blockers(snapshot: dict) -> list[str]:
        job = snapshot['job']; reasons = []
        if job.get('status') not in {'review_required', 'running'}: reasons.append('not_awaiting_review')
        if job.get('exchange_state') == 'installed': reasons.append('installed_receipt_requires_separate_review')
        lease = _utc(job.get('lease_until'))
        if lease and lease > datetime.now(timezone.utc): reasons.append('worker_lease_live')
        for name in ('jobs', 'states', 'sync_jobs', 'campaigns'):
            if len(snapshot[name]) > 100: reasons.append(name + '_capacity_exceeded')
        if any(row.get('id') != job['id'] for row in snapshot['jobs']): reasons.append('other_connection_active')
        return reasons

    async def inspect(self, workspace: str, job_id: str) -> dict:
        snapshot = await self._snapshot(self.db, workspace, job_id)
        job = snapshot['job']
        return {'workspace_id': workspace, 'job_id': job_id, 'sender_id': job['sender_account_id'],
            'status': job['status'], 'exchange_state': job.get('exchange_state', 'unmarked'),
            'review_digest': canonical_hash(snapshot), 'blockers': self._blockers(snapshot),
            'mailbox_will_be_scrubbed': snapshot['mailbox'] is not None,
            'campaigns_to_pause': len(snapshot['campaigns']), 'provider_revocation_verified': False}

    async def stop(self, workspace: str, job_id: str, operator: str, evidence: str, *,
                   expected_digest: str, workers_drained: bool = False) -> dict:
        require_review(operator, evidence, workers_drained)
        if not expected_digest or live_actions_enabled(): raise ValueError('Exact drained inspection and disabled live actions are required')
        scope = {'workspace_id': workspace, 'id': job_id}
        def saved_result(row):
            review = row.get('review') or {}
            if (row.get('status') != 'review_stopped' or review.get('review_digest') != expected_digest
                    or review.get('operator') != operator.strip() or review.get('evidence') != evidence.strip()):
                raise ValueError('A different OAuth review is already saved')
            return {'status': 'review_stopped', 'job_id': job_id, 'provider_revocation_verified': False}
        saved = await self.db.outreach_mailbox_connection_jobs.find_one(scope)
        if saved and saved.get('review'): return saved_result(saved)
        async def apply(current):
            fresh = await current.outreach_mailbox_connection_jobs.find_one(scope)
            if fresh and fresh.get('review'): return saved_result(fresh)
            snapshot = await self._snapshot(_fenced(current, expected_digest), workspace, job_id)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot) or live_actions_enabled():
                raise ValueError('OAuth review changed; inspect after draining again')
            sender = snapshot['job']['sender_account_id']; now = datetime.now(timezone.utc)
            await current.outreach_sender_execution.update_one(SenderExecution.scope(workspace, sender), {'$set': {
                'permission.latched': True, 'permission.expires_at': now, 'permission.stop_reason': 'oauth_hold_review',
                'permission.stopped_by': operator.strip()}, '$inc': {'permission_revision': 1},
                '$setOnInsert': {'status': 'idle'}}, upsert=True)
            await current.outreach_execution_permissions.update_one(ExecutionPermission.scope(workspace, sender), {'$set': {
                'latched': True, 'expires_at': now, 'stop_reason': 'oauth_hold_review', 'stopped_by': operator.strip()}}, upsert=True)
            await current.outreach_accounts.update_one({'workspace_id': workspace, 'id': sender}, {'$set': {'status': 'paused', 'updated_at': now}})
            for campaign in snapshot['campaigns']:
                await current.outreach_campaigns.update_one({'workspace_id': workspace, 'id': campaign['id']}, {'$set': {
                    'status': 'paused', 'auto_launch_enabled': False, 'updated_at': now}, '$inc': {'authorization_revision': 1}})
            await current.outreach_mailboxes.update_one({'workspace_id': workspace, 'sender_account_id': sender}, {'$set': {
                'status': 'disconnected', 'sync_status': 'stale', 'last_sync_at': None, 'updated_at': now},
                '$unset': {'access_token_enc': '', 'refresh_token_enc': '', 'sync_lease_id': '', 'sync_lease_until': ''}})
            for state in snapshot['states']:
                await current.outreach_mailbox_oauth_states.delete_one({'workspace_id': workspace, '_id': state['_id']})
            await current.outreach_mailbox_sync_jobs.update_many({'workspace_id': workspace, 'sender_account_id': sender,
                'status': {'$in': ['queued', 'running']}}, {'$set': {'status': 'stopped', 'updated_at': now}})
            # The same transaction stops authority BEFORE closing the unique
            # review slot. Original owner/exchange evidence remains immutable.
            changed = await current.outreach_mailbox_connection_jobs.update_one({**scope, 'status': snapshot['job']['status']}, {
                '$set': {'status': 'review_stopped', 'updated_at': now, 'review': {'operator': operator.strip(),
                    'evidence': evidence.strip(), 'review_digest': expected_digest, 'workers_drained': True,
                    'at': now, 'provenance': 'operator_local_stop', 'provider_revocation_verified': False}},
                '$unset': {**JOB_SECRETS, 'expires_at': ''}})
            if changed.matched_count != 1: raise ValueError('OAuth review owner changed')
            return saved_result(await current.outreach_mailbox_connection_jobs.find_one(scope))
        return await suppression.mutate_suppression(self.db, workspace, apply)
