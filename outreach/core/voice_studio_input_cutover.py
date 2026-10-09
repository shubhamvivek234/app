"""Private database-only cutover of proven unsubmitted Studio inputs.

No ciphertext opening, provider call, replay, refund or activation occurs.
Proof concerns the participating job protocol; drain remains an assertion.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.integration_control import flags_off, reference, stable
from outreach.core.paid_access import _utc
from outreach.core.proxy_migration import HEX
from outreach.core.voice_artifact_custody import policy
from outreach.core.voice_studio import consent_current, now, profile_identity
from outreach.core.voice_studio_review import LIMIT, REMOTE, VoiceStudioReview, authority_snapshot

JOB_FIELDS = {'_id', 'workspace_id', 'operation', 'actor', 'payload_digest', 'configuration_digest',
    'provider_source_digest', 'voice_id', 'status', 'created_at', 'updated_at', 'next_publish_at',
    'next_recovery_at', 'mutation', 'chars', 'name', 'authorization_expires_at', 'provider_voice_id',
    'profile_identity', 'owner', 'lease_until', 'input_enc', 'consent'}
PLACEHOLDER_FIELDS = {'_id', 'id', 'workspace_id', 'name', 'status', 'revision', 'studio_job_id',
    'consent', 'provider_source_digest', 'created_at', 'updated_at', 'assigned_account_ids'}


def unsubmitted(job: Any) -> bool:
    """Recognize bounded original metadata, without asserting decryptability."""
    try:
        if not isinstance(job, dict) or not set(job).issubset(JOB_FIELDS): return False
        if job.get('status') not in {'queued', 'preparing'} or job.get('operation') not in {'clone', 'preview'}: return False
        for field in ('workspace_id', 'actor', 'voice_id'): reference(job[field])
        for field in ('_id', 'payload_digest', 'configuration_digest', 'profile_identity', 'provider_source_digest'):
            if not isinstance(job.get(field), str) or not HEX.fullmatch(job[field]): return False
        value = job.get('input_enc')
        if not isinstance(value, str) or not value.startswith(('gAAAAA', 'vs1:')) or len(value) > 4000000: return False
        dates = [job[field] for field in ('created_at', 'updated_at', 'next_publish_at',
            'next_recovery_at', 'authorization_expires_at')]
        if any(not isinstance(value, datetime) or value.microsecond % 1000 for value in dates): return False
        created, updated, _, _, deadline = map(_utc, dates)
        if not created <= updated <= now() or not created < deadline <= created + timedelta(minutes=15): return False
        if job['status'] == 'queued':
            if 'owner' in job or 'lease_until' in job: return False
        else:
            reference(job['owner'])
            lease = job.get('lease_until')
            if not isinstance(lease, datetime) or lease.microsecond % 1000: return False
            if not created < _utc(lease) <= min(now(), deadline + timedelta(minutes=2)): return False
        if not isinstance(job.get('name'), str) or len(job['name']) > 100 or type(job.get('chars')) is not int: return False
        if job['operation'] == 'clone':
            consent = job.get('consent')
            return bool(job.get('mutation') is True and job['chars'] == 0 and job['name'].strip()
                and 'provider_voice_id' not in job and job['voice_id'] == canonical_hash(['voice_profile', job['_id']])
                and isinstance(consent, dict) and set(consent) == {'actor', 'version', 'asserted_at', 'assertion_digest'}
                and consent['actor'] == job['actor'] and type(consent['version']) is int and consent['version'] == 1
                and consent['asserted_at'] == job['created_at']
                and consent['assertion_digest'] == canonical_hash(['speaker_owns_or_authorized', job['actor'], job['payload_digest'], 1]))
        remote = job.get('provider_voice_id')
        return bool(job.get('mutation') is False and 1 <= job['chars'] <= 1000 and 'consent' not in job
            and isinstance(remote, str) and REMOTE.fullmatch(remote) and not remote.startswith('voice_mock_'))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def original_profile(job: dict, profile: Any) -> bool:
    if (not isinstance(profile, dict) or profile.get('workspace_id') != job['workspace_id']
            or profile.get('id') != job['voice_id'] or profile.get('studio_job_id') != job['_id']
            or profile.get('provider_source_digest') != job['provider_source_digest']
            or profile_identity(profile) != job['profile_identity']): return False
    if job['operation'] == 'clone':
        return bool(set(profile).issubset(PLACEHOLDER_FIELDS) and profile.get('_id') == job['voice_id']
            and profile.get('status') == 'creating' and type(profile.get('revision')) is int and profile['revision'] == 1
            and profile.get('consent') == job['consent'] and profile.get('name') == job['name']
            and profile.get('created_at') == job['created_at'] and profile.get('updated_at') == job['created_at']
            and profile.get('assigned_account_ids') == [])
    return bool(profile.get('elevenlabs_voice_id') == job['provider_voice_id'] and profile.get('status') == 'active'
        and consent_current(profile) and not profile.get('studio_review_required')
        and type(profile.get('revision')) is int and profile['revision'] >= 1)


def final(view: dict) -> None:
    if not flags_off() or canonical_hash(policy()) != view['policy_digest']:
        raise CustodyUnavailable('Studio input cutover configuration changed')


class VoiceStudioInputCutover:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, job_id: str) -> dict:
        job = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
        profile = await current.outreach_voices.find_one({'workspace_id': workspace, 'id': (job or {}).get('voice_id')})
        existing = await current.outreach_credential_migrations.find_one({'workspace_id': workspace,
            'kind': 'voice_studio_input_stop', 'job_id': job_id})
        return stable({'job': job, 'profile': profile, 'existing_stop': bool(existing),
            'workspace_open': await erasure.workspace_is_open(current, workspace), 'flags_off': flags_off(),
            'policy_digest': canonical_hash(policy()), **await authority_snapshot(current, workspace)})

    @staticmethod
    def _blockers(view: dict, workspace: str, job_id: str) -> list[str]:
        reasons = []
        job = view['job']
        proven = unsubmitted(job) and job['workspace_id'] == workspace and job['_id'] == job_id
        if not proven: reasons.append('original_unsubmitted_job_unproven')
        elif not original_profile(job, view['profile']): reasons.append('original_profile_owner_unproven')
        if not view['workspace_open']: reasons.append('workspace_closed')
        if not view['flags_off']: reasons.append('disabled_flags_required')
        if view['existing_stop']: reasons.append('original_input_stop_already_saved')
        for name in ('studio_jobs', 'preparations', 'accounts', 'campaigns', 'executions', 'permissions'):
            if len(view[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
        ids = [row.get('id') for row in view['accounts']]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            reasons.append('sender_identity_unproven')
        for row in view['studio_jobs']:
            if row.get('_id') == job_id: continue
            if row.get('status') == 'queued' and unsubmitted(row): continue
            lease = _utc(row.get('lease_until')) if isinstance(row.get('lease_until'), datetime) else None
            if row.get('status') in {'queued', 'preparing', 'possible', 'received'} or not lease or lease > now():
                reasons.append('other_studio_writer_live_or_unproven')
        if any(row.get('status') in {'claimed', 'generating'} for row in view['preparations']):
            reasons.append('campaign_preparation_not_recovered')
        for row in view['executions']:
            lease = _utc(row.get('expires_at')) if isinstance(row.get('expires_at'), datetime) else None
            if ((row.get('status') != 'idle' or row.get('owner_token') or row.get('physical_request_token'))
                    and (not lease or lease > now())): reasons.append('sender_worker_live_or_unproven')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, job_id: str) -> dict:
        reference(workspace)
        if not isinstance(job_id, str) or not HEX.fullmatch(job_id):
            raise CustodyUnavailable('An exact original Studio reference is required')
        view = await self._snapshot(self.db, workspace, job_id)
        return {'workspace_id': workspace, 'job_id': job_id, 'digest': canonical_hash(view),
            'blockers': self._blockers(view, workspace, job_id), 'senders_to_pause': len(view['accounts']),
            'campaigns_to_pause': len(view['campaigns']), 'activation_allowed': False}

    async def _saved(self, current: Any, receipt: dict, request: str, workspace: str, job_id: str) -> dict:
        if receipt.get('status') != 'completed' or receipt.get('request_digest') != request:
            raise CustodyUnavailable('A different Studio input review is already saved')
        job = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
        return {'status': 'review_stopped', 'job_id': job_id,
            'current_matches': canonical_hash(stable(job)) == receipt['after_digest'], 'activation_allowed': False}

    async def stop(self, workspace: str, job_id: str, operator: str, evidence_digest: str,
                   expected_digest: str, *, workers_drained: bool = False) -> dict:
        for value in (workspace, operator): reference(value)
        if (workers_drained is not True or not flags_off() or any(not isinstance(value, str) or not HEX.fullmatch(value)
                for value in (job_id, evidence_digest, expected_digest))):
            raise CustodyUnavailable('Exact disabled-gate review and all-writer/cache drain are required')
        key = canonical_hash(['voice-studio-input-stop-v1', workspace, job_id, expected_digest])
        scope = {'workspace_id': workspace, '_id': key}
        request = canonical_hash([workspace, job_id, operator, evidence_digest, expected_digest])
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await self._saved(self.db, receipt, request, workspace, job_id)

        async def apply(current: Any) -> dict:
            receipt = await current.outreach_credential_migrations.find_one(scope)
            if receipt: return await self._saved(current, receipt, request, workspace, job_id)
            fenced = (AuthorityDatabase(current.database, current.session, key)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            view = await self._snapshot(fenced, workspace, job_id)
            if canonical_hash(view) != expected_digest or self._blockers(view, workspace, job_id):
                raise CustodyUnavailable('Original Studio input inspection changed')
            job, profile = view['job'], view['profile']; stamp = now()
            await VoiceStudioReview(self.db)._stop_authority(current, view, operator, stamp,
                reason='voice_studio_input_cutover')
            if job['operation'] == 'clone':
                changed = await current.outreach_voices.delete_one({'workspace_id': workspace, **profile})
                matched = changed.deleted_count
            else:
                changed = await current.outreach_voices.update_one({'workspace_id': workspace, **profile},
                    {'$set': {'studio_review_required': True, 'updated_at': stamp},
                     '$inc': {'revision': 1}, '$unset': {'studio_job_id': ''}})
                matched = changed.matched_count
            if matched != 1: raise CustodyUnavailable('Original Studio input profile changed')
            changed = await current.outreach_voice_studio_jobs.update_one({'workspace_id': workspace, **job},
                {'$set': {'status': 'review_stopped', 'updated_at': stamp}, '$unset': {'input_enc': ''}})
            if changed.matched_count != 1: raise CustodyUnavailable('Original Studio input owner changed')
            target = {k: v for k, v in {**job, 'status': 'review_stopped', 'updated_at': stamp}.items() if k != 'input_enc'}
            row = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
            if stable(row) != target: raise CustodyUnavailable('Original Studio input closure changed')
            receipt = {**scope, 'kind': 'voice_studio_input_stop', 'job_id': job_id, 'status': 'completed',
                'request_digest': request, 'before_digest': expected_digest, 'after_digest': canonical_hash(target),
                'original_job_digest': canonical_hash(job), 'original_profile_digest': canonical_hash(profile),
                'original_status': job['status'], 'operation': job['operation'],
                'owner_digest': canonical_hash(job.get('owner')), 'input_digest': canonical_hash(job['input_enc']),
                'consent_digest': canonical_hash(profile.get('consent')), 'policy_digest': view['policy_digest'],
                'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                'at': stamp, 'workers_drained': True, 'activation_allowed': False,
                'provenance': 'unsubmitted_studio_input_stop'}
            await current.outreach_credential_migrations.insert_one(receipt)
            result = await self._saved(current, receipt, request, workspace, job_id)
            final(view)
            return result

        return await suppression.mutate_suppression(self.db, workspace, apply)
