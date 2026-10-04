"""Private database-only Studio review; never resend, adopt or activate.

The drain is an operator assertion. Snapshot/majority ordering covers current
participating writers, not cached credentials or an already authorized call.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core.credential_migration import _stable
from outreach.core import erasure
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.paid_access import _utc, live_actions_enabled
from outreach.core.sender_execution import SenderExecution
from outreach.core.voice_key_custody import capture_configuration
from outreach.core.voice_policy import preparation_enabled
from outreach.core.voice_studio import ACTIVE, VoiceStudio, enabled, now

LIMIT = 100
DECISIONS = {'stop_local', 'use_receipt'}
REVIEWABLE = {'preparing', 'possible', 'held_outcome', 'received', 'held_received'}
HEX = re.compile(r'[a-f0-9]{64}\Z')
REMOTE = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def flags_off() -> bool:
    return not (live_actions_enabled() or enabled() or preparation_enabled())


def timestamp(value: Any) -> datetime | None:
    return _utc(value) if isinstance(value, (datetime, str)) else None


def key_metadata(job: dict) -> dict:
    try:
        config = capture_configuration()
        return {'digest': config.digest, 'source_matches': config.source == job.get('provider_source_digest')}
    except ValueError:
        return {'digest': None, 'source_matches': False}


def receipt_valid(job: dict) -> bool:
    receipt = job.get('receipt')
    if not isinstance(receipt, dict):
        return False
    stamp = timestamp(receipt.get('received_at'))
    possible = timestamp(job.get('possible_at'))
    if not stamp or not possible or not possible <= stamp <= now() or not job.get('owner'):
        return False
    if job.get('operation') == 'clone':
        remote = receipt.get('voice_id')
        return bool(isinstance(remote, str) and REMOTE.fullmatch(remote) and not remote.startswith('voice_mock_')
                    and type(receipt.get('requires_verification')) is bool)
    if job.get('operation') == 'delete':
        remote = job.get('provider_voice_id')
        return receipt.get('deleted') is True and isinstance(remote, str) and bool(REMOTE.fullmatch(remote))
    digest = receipt.get('audio_digest')
    return job.get('operation') == 'preview' and isinstance(digest, str) and bool(HEX.fullmatch(digest))


def outcome(job: dict) -> str:
    if receipt_valid(job):
        return 'received'
    return 'not_called' if job.get('status') == 'preparing' and not job.get('possible_at') and not job.get('receipt') else 'unknown'


async def authority_snapshot(db: Any, workspace: str) -> dict:
    """Bound workspace rows used by private stopped Studio control operations."""
    snapshot = {}
    for name, collection, query in (
        ('studio_jobs', 'outreach_voice_studio_jobs', {'status': {'$in': ACTIVE}}),
        ('preparations', 'outreach_voice_preparation_jobs', {'status': {'$in': ['queued', 'claimed', 'generating']}}),
        ('accounts', 'outreach_accounts', {}),
        ('campaigns', 'outreach_campaigns', {'status': {'$in': ['active', 'warming_up']}}),
        ('executions', 'outreach_sender_execution', {}),
        ('permissions', 'outreach_execution_permissions', {})):
        snapshot[name] = [_stable(row) for row in await getattr(db, collection).find({
            'workspace_id': workspace, **query}).sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1)]
    return snapshot


class VoiceStudioReview:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, db: Any, workspace: str, job_id: str) -> dict:
        job = _stable(await db.outreach_voice_studio_jobs.find_one(VoiceStudio.scope(workspace, job_id)))
        if not job:
            raise ValueError('Studio reference is unavailable')
        snapshot = {'job': job, 'profile': _stable(await db.outreach_voices.find_one({
            'workspace_id': workspace, 'id': job['voice_id']})), 'workspace_open': await erasure.workspace_is_open(db, workspace),
            'key': key_metadata(job), 'flags_off': flags_off()}
        snapshot.update(await authority_snapshot(db, workspace))
        return snapshot

    @staticmethod
    def _blockers(snapshot: dict) -> list[str]:
        job, profile = snapshot['job'], snapshot['profile']
        reasons = []
        if job.get('status') not in REVIEWABLE: reasons.append('not_awaiting_review')
        if (job.get('operation') not in {'clone', 'preview', 'delete'} or not isinstance(job.get('owner'), str)
                or not job['owner'].strip() or any(not isinstance(job.get(key), str) or not HEX.fullmatch(job[key])
                    for key in ('payload_digest', 'provider_source_digest', 'profile_identity', 'configuration_digest'))):
            reasons.append('original_binding_unproven')
        lease = timestamp(job.get('lease_until'))
        if not lease or lease > now(): reasons.append('worker_lease_live_or_unproven')
        if job.get('receipt') and not receipt_valid(job): reasons.append('unusable_saved_receipt')
        if profile and (profile.get('studio_job_id') != job['_id']
                or profile.get('provider_source_digest') != job.get('provider_source_digest')
                or profile.get('elevenlabs_voice_id') != job.get('provider_voice_id')):
            reasons.append('profile_owner_or_resource_changed')
        if not snapshot['flags_off']: reasons.append('provider_flags_enabled')
        for name in ('studio_jobs', 'preparations', 'accounts', 'campaigns', 'executions', 'permissions'):
            if len(snapshot[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
        if any(row['_id'] != job['_id'] and (row.get('status') in {'queued', 'preparing', 'possible', 'received'}
                or (timestamp(row.get('lease_until')) and timestamp(row['lease_until']) > now())) for row in snapshot['studio_jobs']):
            reasons.append('other_studio_writer_pending')
        if any(row.get('status') in {'claimed', 'generating'} for row in snapshot['preparations']):
            reasons.append('campaign_preparation_not_recovered')
        if any(row.get('status') != 'idle' and timestamp(row.get('expires_at')) and timestamp(row['expires_at']) > now()
               for row in snapshot['executions']): reasons.append('sender_worker_lease_live')
        if any(not isinstance(row.get('id'), str) or not row['id'] for row in snapshot['accounts']):
            reasons.append('sender_identity_unproven')
        return reasons

    async def inspect(self, workspace: str, job_id: str) -> dict:
        snapshot = await self._snapshot(self.db, workspace, job_id)
        job = snapshot['job']; blockers = self._blockers(snapshot)
        decisions = [] if blockers else ['stop_local']
        if (not blockers and receipt_valid(job) and (job['operation'] == 'delete'
                or snapshot['workspace_open'] and snapshot['profile'])): decisions.append('use_receipt')
        return {'workspace_id': workspace, 'job_id': job_id, 'voice_id': job['voice_id'], 'operation': job['operation'],
            'status': job['status'], 'outcome_at_review': outcome(job), 'review_digest': canonical_hash(snapshot),
            'blockers': blockers, 'allowed_decisions': decisions, 'original_source_is_current': snapshot['key']['source_matches'],
            'profile_present': snapshot['profile'] is not None, 'campaigns_to_pause': len(snapshot['campaigns']),
            'senders_to_pause': len(snapshot['accounts']), 'queued_preparations_to_cancel':
                sum(row.get('status') == 'queued' for row in snapshot['preparations']), 'activation_allowed': False}

    @staticmethod
    def _saved(row: dict, decision: str, operator: str, evidence: str, digest: str) -> dict:
        review = row.get('review') or {}
        if (row.get('status') not in {'review_stopped', 'review_completed'} or review.get('decision') != decision
                or review.get('operator') != operator or review.get('evidence') != evidence
                or review.get('review_digest') != digest):
            raise ValueError('A different Studio review is already saved')
        return {'status': row['status'], 'job_id': row['_id'], 'outcome_at_review': review['outcome_at_review'],
            'activation_allowed': False}

    async def _stop_authority(self, current: Any, snapshot: dict, operator: str, stamp: Any,
                              reason: str = 'voice_studio_review') -> None:
        workspace = snapshot['job']['workspace_id']
        for row in snapshot['accounts']:
            await current.outreach_accounts.update_one({'workspace_id': workspace, '_id': row['_id']}, {'$set': {
                'status': 'paused' if snapshot['workspace_open'] else 'disconnected', 'updated_at': stamp}})
        for row in snapshot['campaigns']:
            await current.outreach_campaigns.update_one({'workspace_id': workspace, '_id': row['_id']}, {'$set': {
                'status': 'paused', 'auto_launch_enabled': False, 'updated_at': stamp}, '$inc': {'authorization_revision': 1}})
        # Keep physical tokens/leases/owners. A Studio review cannot resolve an
        # unrelated delivery or prove an external resource was withdrawn.
        senders = {row['id'] for row in snapshot['accounts']}
        for kind, collection, scope_fn, rows in (
            ('execution', current.outreach_sender_execution, SenderExecution.scope, snapshot['executions']),
            ('permission', current.outreach_execution_permissions, ExecutionPermission.scope, snapshot['permissions'])):
            changes = {'latched': True, 'expires_at': stamp, 'stop_reason': reason, 'stopped_by': operator}
            update = ({'$set': {'permission.' + k: v for k, v in changes.items()}, '$inc': {'permission_revision': 1}}
                      if kind == 'execution' else {'$set': changes})
            for row in rows:
                await collection.update_one({'workspace_id': workspace, '_id': row['_id']}, update)
            if snapshot['workspace_open']:
                existing = {row.get('sender_id') for row in rows}
                for sender in senders - existing:
                    addition = {**update, '$setOnInsert': {'status': 'idle'}} if kind == 'execution' else update
                    await collection.update_one(scope_fn(workspace, sender), addition, upsert=True)
        for row in snapshot['preparations']:
            await current.outreach_voice_preparation_jobs.update_one({'workspace_id': workspace, '_id': row['_id'],
                'status': 'queued'}, {'$set': {'status': 'cancelled', 'error_code': 'operator_studio_review',
                    'updated_at': stamp}, '$unset': {'binding': ''}})

    async def resolve(self, workspace: str, job_id: str, decision: str, operator: str, evidence: str, *,
                      workers_drained: bool = False, expected_digest: str) -> dict:
        if (workers_drained is not True or decision not in DECISIONS or not flags_off()
                or not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 256
                or any(ord(c) < 32 or ord(c) == 127 for c in operator)
                or not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 2000
                or not isinstance(expected_digest, str) or not HEX.fullmatch(expected_digest)):
            raise ValueError('Disabled flags, exact inspection and identified all-writer drain evidence are required')
        operator, evidence = operator.strip(), evidence.strip()
        scope = VoiceStudio.scope(workspace, job_id)
        async def apply(current):
            row = await current.outreach_voice_studio_jobs.find_one(scope)
            if row and row.get('review'): return self._saved(row, decision, operator, evidence, expected_digest)
            fenced = VoiceStudio._authorities(current)
            snapshot = await self._snapshot(fenced, workspace, job_id)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot):
                raise ValueError('Studio inspection changed; drain and inspect again')
            job, profile = snapshot['job'], snapshot['profile']
            if decision == 'use_receipt' and (not receipt_valid(job)
                    or job['operation'] != 'delete' and (not snapshot['workspace_open'] or not profile)):
                raise ValueError('An original received outcome and unchanged local resource are required')
            stamp = now()
            await self._stop_authority(current, snapshot, operator, stamp)
            if profile:
                profile_scope = {'workspace_id': workspace, '_id': profile['_id'], 'studio_job_id': job_id,
                    'revision': profile.get('revision'), 'provider_source_digest': job['provider_source_digest']}
                remove = ((outcome(job) == 'not_called' and job['operation'] == 'clone')
                          or decision == 'use_receipt' and job['operation'] == 'delete')
                if remove:
                    changed = await current.outreach_voices.delete_one(profile_scope)
                    matched = changed.deleted_count
                else:
                    changes = {'studio_review_required': True, 'status': 'consent_revoked' if profile.get('status') == 'consent_revoked'
                        else 'review_required', 'updated_at': stamp}
                    if decision == 'use_receipt' and job['operation'] == 'clone':
                        changes['elevenlabs_voice_id'] = job['receipt']['voice_id']
                        if job['receipt']['requires_verification'] and profile.get('status') != 'consent_revoked':
                            changes['status'] = 'needs_vendor_verification'
                    changed = await current.outreach_voices.update_one(profile_scope, {'$set': changes,
                        '$unset': {'studio_job_id': ''}, '$inc': {'revision': 1}})
                    matched = changed.matched_count
                if matched != 1: raise ValueError('Original Studio profile owner changed')
            if not flags_off() or key_metadata(job) != snapshot['key']:
                raise ValueError('Studio deployment configuration changed during review')
            status = 'review_completed' if decision == 'use_receipt' else 'review_stopped'
            changed = await current.outreach_voice_studio_jobs.update_one({**scope, 'status': job['status'], 'owner': job['owner'],
                'review': {'$exists': False}}, {'$set': {'status': status, 'updated_at': stamp, 'review': {
                    'decision': decision, 'operator': operator, 'evidence': evidence, 'workers_drained': True,
                    'review_digest': expected_digest, 'at': stamp, 'original_status': job['status'],
                    'outcome_at_review': outcome(job), 'receipt_digest': canonical_hash(job['receipt']) if job.get('receipt') else None,
                    'provenance': 'saved_provider_receipt' if decision == 'use_receipt' else 'operator_local_stop',
                    'activation_allowed': False}}, '$unset': {'input_enc': '', 'result_enc': ''}})
            if changed.matched_count != 1: raise ValueError('Studio review owner changed')
            return self._saved(await current.outreach_voice_studio_jobs.find_one(scope), decision, operator, evidence, expected_digest)
        return await VoiceStudio(self.db)._control(workspace, apply)
