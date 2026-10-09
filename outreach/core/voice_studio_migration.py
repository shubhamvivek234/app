"""Private stopped conversion of completed Studio preview result custody.

Original receipts/configuration/expiry remain. No replay, adoption or activation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, _bytes, _pairs
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.integration_control import flags_off, stable
from outreach.core.paid_access import _utc
from outreach.core.proxy_migration import HEX, _reference
from outreach.core.session_custody import custody_mode
from outreach.core.voice_artifact_custody import policy
from outreach.core.voice_policy import validate_audio
from outreach.core.voice_studio_custody import MAX_BLOB, scope as blob_scope, seal_blob
from outreach.core.voice_studio_review import LIMIT, REMOTE, VoiceStudioReview, authority_snapshot
from utils.encryption import decrypt_strict

JOB_FIELDS = {'_id', 'workspace_id', 'operation', 'actor', 'payload_digest', 'configuration_digest',
    'provider_source_digest', 'voice_id', 'status', 'created_at', 'updated_at', 'next_publish_at',
    'next_recovery_at', 'mutation', 'chars', 'name', 'authorization_expires_at', 'provider_voice_id',
    'profile_identity', 'owner', 'lease_until', 'possible_at', 'receipt', 'result_enc', 'result_expires_at'}
LIFETIME = timedelta(hours=24)
# Only a bounded original result-installation interval is accepted; never added
# to or substituted for the retained expiry during conversion.
INSTALL_LAG = timedelta(seconds=60)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _source(job: Any, profile: Any, workspace: str, job_id: str) -> bool:
    try:
        if not isinstance(job, dict) or not set(job).issubset(JOB_FIELDS): return False
        if (job.get('_id') != job_id or job.get('workspace_id') != workspace
                or job.get('status') != 'completed' or job.get('operation') != 'preview'
                or job.get('mutation') is not False or type(job.get('chars')) is not int
                or not 1 <= job['chars'] <= 1000): return False
        for field in ('actor', 'owner', 'voice_id'): _reference(job[field])
        for field in ('_id', 'payload_digest', 'configuration_digest', 'profile_identity', 'provider_source_digest'):
            if not isinstance(job.get(field), str) or not HEX.fullmatch(job[field]): return False
        value = job.get('result_enc')
        if not isinstance(value, str) or not value.startswith('gAAAAA') or len(value) > 4000000: return False
        if not isinstance(job.get('name'), str) or len(job['name']) > 100: return False
        receipt = job.get('receipt')
        if (not isinstance(receipt, dict) or set(receipt) != {'received_at', 'audio_digest'}
                or not isinstance(receipt['audio_digest'], str) or not HEX.fullmatch(receipt['audio_digest'])): return False
        dates = [job[field] for field in ('created_at', 'possible_at', 'updated_at',
            'authorization_expires_at', 'lease_until', 'result_expires_at')] + [receipt['received_at']]
        if any(not isinstance(value, datetime) or value.microsecond % 1000 for value in dates): return False
        created, possible, updated, authorization, lease, expiry, received = map(_utc, dates)
        if (not created <= possible <= received <= updated <= now() or lease > now()
                or not possible <= min(authorization, lease) or expiry <= now()
                or not received < expiry <= received + LIFETIME + INSTALL_LAG): return False
        remote = job.get('provider_voice_id')
        return bool(isinstance(remote, str) and REMOTE.fullmatch(remote) and not remote.startswith('voice_mock_')
            and isinstance(profile, dict) and profile.get('workspace_id') == workspace
            and profile.get('id') == job['voice_id'] and profile.get('elevenlabs_voice_id') == remote
            and profile.get('provider_source_digest') == job['provider_source_digest']
            and not profile.get('studio_job_id'))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


async def open_legacy_result(job: dict) -> bytes:
    """Explicit original-purpose Fernet opening; normal consumers gain no fallback."""
    try:
        value = job['result_enc']
        if not isinstance(value, str) or not value.startswith('gAAAAA') or len(value) > 4000000:
            raise ValueError('Original format')
        envelope = json.loads(decrypt_strict(value), object_pairs_hook=_pairs)
        if set(envelope) != {'scope', 'value'} or envelope['scope'] != blob_scope(job, 'result'):
            raise ValueError('Original result scope')
        audio = _bytes(envelope['value'], MAX_BLOB)
        validate_audio(audio)
        if canonical_hash(audio) != job['receipt']['audio_digest']: raise ValueError('Original receipt')
        return audio
    except Exception:
        raise CustodyUnavailable('Original received Studio preview is unavailable') from None


def _final(view: dict) -> None:
    if (not flags_off() or custody_mode() != 'kms_v1' or canonical_hash(policy()) != view['policy_digest']
            or _utc(view['job']['result_expires_at']) <= now()):
        raise CustodyUnavailable('Studio conversion authority changed')


def _fenced(current: Any, key: str) -> Any:
    return (AuthorityDatabase(current.database, current.session, key)
        if isinstance(current, suppression.SuppressionDatabase) else current)


class VoiceStudioMigration:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, job_id: str) -> dict:
        job = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
        profile = await current.outreach_voices.find_one({'workspace_id': workspace, 'id': (job or {}).get('voice_id')})
        existing = await current.outreach_credential_migrations.find_one({'workspace_id': workspace,
            'kind': 'voice_studio_result', 'job_id': job_id})
        return stable({'job': job, 'profile': profile, 'existing_conversion': bool(existing),
            'workspace_open': await erasure.workspace_is_open(current, workspace), 'flags_off': flags_off(),
            'policy_digest': canonical_hash(policy()), **await authority_snapshot(current, workspace)})

    @staticmethod
    def _blockers(view: dict, workspace: str, job_id: str) -> list[str]:
        reasons = []
        if not _source(view['job'], view['profile'], workspace, job_id): reasons.append('original_completed_preview_unproven')
        if not view['workspace_open']: reasons.append('workspace_closed')
        if not view['flags_off'] or custody_mode() != 'kms_v1': reasons.append('disabled_flags_scoped_destination_required')
        if view['existing_conversion']: reasons.append('original_preview_conversion_already_saved')
        for name in ('studio_jobs', 'preparations', 'accounts', 'campaigns', 'executions', 'permissions'):
            if len(view[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
        ids = [row.get('id') for row in view['accounts']]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            reasons.append('sender_identity_unproven')
        for row in view['studio_jobs']:
            lease = _utc(row.get('lease_until')) if isinstance(row.get('lease_until'), (datetime, str)) else None
            if row.get('status') in {'queued', 'preparing', 'possible', 'received'} or lease and lease > now():
                reasons.append('studio_writer_pending')
        if any(row.get('status') in {'claimed', 'generating'} for row in view['preparations']):
            reasons.append('campaign_preparation_not_recovered')
        for row in view['executions']:
            lease = _utc(row.get('expires_at')) if isinstance(row.get('expires_at'), (datetime, str)) else None
            if ((row.get('status') != 'idle' or row.get('owner_token') or row.get('physical_request_token'))
                    and (not lease or lease > now())): reasons.append('sender_worker_live_or_unproven')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, job_id: str) -> dict:
        _reference(workspace)
        if not isinstance(job_id, str) or not HEX.fullmatch(job_id):
            raise CustodyUnavailable('An exact original Studio reference is required')
        view = await self._snapshot(self.db, workspace, job_id)
        return {'workspace_id': workspace, 'job_id': job_id, 'digest': canonical_hash(view),
            'blockers': self._blockers(view, workspace, job_id), 'senders_to_pause': len(view['accounts']),
            'campaigns_to_pause': len(view['campaigns']), 'activation_allowed': False}

    async def _saved(self, current: Any, receipt: dict, request: str, workspace: str, job_id: str) -> dict:
        if receipt.get('status') != 'completed' or receipt.get('request_digest') != request:
            raise CustodyUnavailable('A different Studio conversion review is already saved')
        job = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
        return {'status': 'completed', 'migration_id': receipt['_id'],
            'current_matches': canonical_hash(stable(job)) == receipt['after_digest'],
            'configuration_matches': canonical_hash(policy()) == receipt['target_policy_digest'], 'activation_allowed': False}

    async def migrate(self, workspace: str, job_id: str, operator: str, evidence_digest: str,
                      expected_digest: str, *, workers_drained: bool = False) -> dict:
        for value in (workspace, operator): _reference(value)
        if (workers_drained is not True or not flags_off() or custody_mode() != 'kms_v1'
                or any(not isinstance(value, str) or not HEX.fullmatch(value)
                       for value in (job_id, evidence_digest, expected_digest))):
            raise CustodyUnavailable('Exact disabled-gate review and all-writer/cache drain are required')
        key = canonical_hash(['voice-studio-result-migration-v1', workspace, job_id, expected_digest])
        scope = {'workspace_id': workspace, '_id': key}
        request = canonical_hash([workspace, job_id, operator, evidence_digest, expected_digest])
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await self._saved(self.db, receipt, request, workspace, job_id)

        async def verify(current: Any, digest: str) -> dict:
            view = await self._snapshot(_fenced(current, key), workspace, job_id)
            if canonical_hash(view) != digest or self._blockers(view, workspace, job_id):
                raise CustodyUnavailable('Original Studio inspection changed')
            return view

        async def stop(current: Any) -> dict:
            receipt = await current.outreach_credential_migrations.find_one(scope)
            if receipt: return {'completed': await self._saved(current, receipt, request, workspace, job_id)}
            view = await verify(current, expected_digest)
            await VoiceStudioReview(self.db)._stop_authority(current, view, operator, now(),
                reason='voice_studio_result_storage_migration')
            after = await self._snapshot(_fenced(current, key), workspace, job_id)
            if after['job'] != view['job'] or after['profile'] != view['profile'] or self._blockers(after, workspace, job_id):
                raise CustodyUnavailable('Original Studio result changed during stop')
            _final(after)
            return {'view': after}

        inspected = await suppression.mutate_suppression(self.db, workspace, stop)
        if 'completed' in inspected: return inspected['completed']
        view = inspected['view']; original = view['job']
        _final(view)
        audio = await open_legacy_result(original)
        _final(view)
        sealing_job = deepcopy(original)
        sealed = await seal_blob(audio, sealing_job, 'result')
        del audio
        _final(view)
        if (sealing_job != original or not isinstance(sealed, str) or not sealed.startswith('vs1:')
                or len(sealed) > 4000000): raise CustodyUnavailable('Studio conversion changed')
        target = {**original, 'result_enc': sealed}

        async def install(current: Any) -> dict:
            receipt = await current.outreach_credential_migrations.find_one(scope)
            if receipt: return await self._saved(current, receipt, request, workspace, job_id)
            await verify(current, canonical_hash(view))
            changed = await current.outreach_voice_studio_jobs.update_one({'workspace_id': workspace, **original},
                {'$set': {'result_enc': sealed}})
            if changed.matched_count != 1: raise CustodyUnavailable('Original Studio result owner changed')
            row = await current.outreach_voice_studio_jobs.find_one({'workspace_id': workspace, '_id': job_id})
            if stable(row) != target: raise CustodyUnavailable('Original Studio result installation changed')
            receipt = {**scope, 'kind': 'voice_studio_result', 'job_id': job_id, 'status': 'completed',
                'request_digest': request, 'before_digest': expected_digest, 'after_digest': canonical_hash(target),
                'original_job_digest': canonical_hash(original), 'audio_digest': original['receipt']['audio_digest'],
                'generation_digest': canonical_hash([original['owner'], original['payload_digest'], original['receipt']]),
                'received_at': original['receipt']['received_at'], 'expires_at': original['result_expires_at'],
                'target_policy_digest': view['policy_digest'], 'operator_digest': canonical_hash(operator),
                'evidence_digest': evidence_digest, 'at': now(), 'workers_drained': True,
                'activation_allowed': False, 'provenance': 'strict_fernet_studio_result_conversion'}
            await current.outreach_credential_migrations.insert_one(receipt)
            result = await self._saved(current, receipt, request, workspace, job_id)
            _final(view)
            return result

        return await suppression.mutate_suppression(self.db, workspace, install)
