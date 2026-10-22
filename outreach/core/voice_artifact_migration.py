"""Private stopped conversion of installed, received campaign recordings.

No paid generation, source adoption, expiry extension or activation is granted.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, _bytes
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.integration_control import flags_off, stable
from outreach.core.paid_access import _utc
from outreach.core.proxy_migration import HEX, _reference
from outreach.core.session_custody import custody_mode
from outreach.core.voice_artifact_custody import (
    FIELDS, MAX_AUDIO_BYTES, _audio_matches, _validate_record, policy, seal_audio,
)
from outreach.core.voice_studio_review import LIMIT, VoiceStudioReview, authority_snapshot
from utils.encryption import decrypt_strict

SOURCE_FIELDS = {*FIELDS, 'status', 'audio_enc'}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _source(artifact: Any, job: Any, workspace: str, asset: str) -> bool:
    try:
        if not isinstance(artifact, dict) or not set(artifact).issubset(SOURCE_FIELDS):
            return False
        _validate_record(artifact, workspace, asset, mode='legacy_fernet')
        if (not artifact['audio_enc'].startswith('gAAAAA')
                or any(not isinstance(artifact[field], datetime) or artifact[field].microsecond % 1000
                       for field in ('prepared_at', 'expires_at'))):
            return False
        _reference(job['owner'])
        return bool(job.get('workspace_id') == workspace and job.get('_id') == asset
            and job.get('status') == 'prepared' and job.get('generation_result') == 'received'
            and job.get('mutation') is True and job['owner'] == artifact['generation_id']
            and job.get('audio_digest') == artifact['audio_digest']
            and type(job.get('generation_count')) is int and job['generation_count'] >= 1
            and isinstance(job.get('generation_started_at'), datetime)
            and _utc(job['generation_started_at']) <= _utc(artifact['prepared_at']))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


async def open_legacy_audio(document: dict) -> bytes:
    """Explicit migration-only legacy open, called after committed authority stop."""
    try:
        _validate_record(document, document['workspace_id'], document['_id'], mode='legacy_fernet')
        if not document['audio_enc'].startswith('gAAAAA'):
            raise ValueError('Original format')
        audio = _bytes(decrypt_strict(document['audio_enc']), MAX_AUDIO_BYTES)
        if not _audio_matches(audio, document):
            raise ValueError('Original recording')
        return audio
    except Exception:
        raise CustodyUnavailable('Original received recording is unavailable') from None


def _material(view: dict) -> str:
    return canonical_hash(stable({'artifact': view['artifact'], 'job': view['job']}))


def _binding_proven(view: dict, workspace: str, asset: str) -> bool:
    """Retained full review reconstructs the original tenant/content identity."""
    artifact = view['artifact'] or {}
    for review in view['approvals']:
        try:
            binding = deepcopy(review['binding'])
            if (review['_id'] != canonical_hash(binding) or binding.get('workspace_id') != workspace
                    or binding.get('action') != 'voice_note'
                    or binding['context'].pop('voice_artifact_id') != asset
                    or binding['context'].pop('voice_artifact_generation') != artifact['generation_id']
                    or binding['content'].pop('audio_digest') != artifact['audio_digest']):
                continue
            if canonical_hash(binding) == asset: return True
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return False


def _final(view: dict) -> None:
    if (not flags_off() or custody_mode() != 'kms_v1' or view['policy_digest'] != canonical_hash(policy())
            or _utc(view['artifact']['expires_at']) <= now()):
        raise CustodyUnavailable('Recording migration authority changed')


def _fenced(current: Any, key: str) -> Any:
    return (AuthorityDatabase(current.database, current.session, key)
        if isinstance(current, suppression.SuppressionDatabase) else current)


class VoiceArtifactMigration:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, asset: str) -> dict:
        scope = {'workspace_id': workspace, '_id': asset}
        artifact = await current.outreach_voice_artifacts.find_one(scope)
        job = await current.outreach_voice_preparation_jobs.find_one(scope)
        approvals = await current.outreach_content_approvals.find({'workspace_id': workspace,
            'binding.context.voice_artifact_id': asset}).sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1)
        existing = await current.outreach_credential_migrations.find_one({'workspace_id': workspace,
            'kind': 'voice_artifact', 'artifact_id': asset,
            'generation_digest': canonical_hash((artifact or {}).get('generation_id'))})
        return stable({'artifact': artifact, 'job': job, 'approvals': approvals,
            'workspace_open': await erasure.workspace_is_open(current, workspace),
            'policy_digest': canonical_hash(policy()), 'flags_off': flags_off(),
            'existing_conversion': bool(existing), **await authority_snapshot(current, workspace)})

    @staticmethod
    def _blockers(view: dict, workspace: str, asset: str) -> list[str]:
        reasons = []
        if not _source(view['artifact'], view['job'], workspace, asset): reasons.append('original_received_recording_unproven')
        if not _binding_proven(view, workspace, asset): reasons.append('original_content_binding_unproven')
        if any(type(row.get('revision')) is not int or row['revision'] < 1
               or row.get('status') not in {'pending', 'approved', 'rejected', 'revoked'} for row in view['approvals']):
            reasons.append('original_approval_shape_unproven')
        if not view['workspace_open']: reasons.append('workspace_closed')
        if not view['flags_off'] or custody_mode() != 'kms_v1': reasons.append('disabled_flags_scoped_destination_required')
        if view['existing_conversion']: reasons.append('generation_conversion_already_saved')
        for name in ('approvals', 'studio_jobs', 'preparations', 'accounts', 'campaigns', 'executions', 'permissions'):
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
                    and (not lease or lease > now())):
                reasons.append('sender_worker_live_or_unproven')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, asset: str) -> dict:
        _reference(workspace)
        if not isinstance(asset, str) or not HEX.fullmatch(asset):
            raise CustodyUnavailable('An exact recording reference is required')
        view = await self._snapshot(self.db, workspace, asset)
        return {'workspace_id': workspace, 'artifact_id': asset, 'digest': canonical_hash(view),
            'blockers': self._blockers(view, workspace, asset), 'approvals_to_revoke': len(view['approvals']),
            'senders_to_pause': len(view['accounts']), 'campaigns_to_pause': len(view['campaigns']),
            'activation_allowed': False}

    async def _saved(self, current: Any, receipt: dict, request: str, workspace: str, asset: str) -> dict:
        if receipt.get('status') != 'completed' or receipt.get('request_digest') != request:
            raise CustodyUnavailable('A different recording migration review is already saved')
        artifact = await current.outreach_voice_artifacts.find_one({'workspace_id': workspace, '_id': asset})
        job = await current.outreach_voice_preparation_jobs.find_one({'workspace_id': workspace, '_id': asset})
        return {'status': 'completed', 'migration_id': receipt['_id'],
            'current_matches': _material({'artifact': artifact, 'job': job}) == receipt['after_digest'],
            'configuration_matches': canonical_hash(policy()) == receipt['target_policy_digest'], 'activation_allowed': False}

    async def migrate(self, workspace: str, asset: str, operator: str, evidence_digest: str,
                      expected_digest: str, *, workers_drained: bool = False) -> dict:
        for value in (workspace, operator): _reference(value)
        if (workers_drained is not True or not flags_off() or custody_mode() != 'kms_v1'
                or any(not isinstance(value, str) or not HEX.fullmatch(value)
                       for value in (asset, evidence_digest, expected_digest))):
            raise CustodyUnavailable('Exact disabled-gate review and all-writer/cache drain are required')
        key = canonical_hash(['voice-artifact-migration-v1', workspace, asset, expected_digest])
        scope = {'workspace_id': workspace, '_id': key}
        request = canonical_hash([workspace, asset, operator, evidence_digest, expected_digest])
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await self._saved(self.db, receipt, request, workspace, asset)

        async def verify(current: Any, digest: str) -> dict:
            view = await self._snapshot(_fenced(current, key), workspace, asset)
            if canonical_hash(view) != digest or self._blockers(view, workspace, asset):
                raise CustodyUnavailable('Original recording inspection changed')
            return view

        async def stop(current: Any) -> dict:
            receipt = await current.outreach_credential_migrations.find_one(scope)
            if receipt: return {'completed': await self._saved(current, receipt, request, workspace, asset)}
            view = await verify(current, expected_digest)
            stamp = now()
            await VoiceStudioReview(self.db)._stop_authority(current, view, operator, stamp,
                reason='voice_artifact_storage_migration')
            for row in view['approvals']:
                changed = await current.outreach_content_approvals.update_one({'workspace_id': workspace,
                    '_id': row['_id'], 'revision': row['revision']}, {'$set': {'status': 'pending' if row['status'] == 'approved' else row['status'],
                        'approved_at': None, 'expires_at': stamp, 'updated_at': stamp}, '$inc': {'revision': 1},
                    '$push': {'history': {'decision': 'custody_migration_revoke', 'operator_digest': canonical_hash(operator), 'at': stamp}}})
                if changed.matched_count != 1: raise CustodyUnavailable('Original recording review changed')
            after = await self._snapshot(_fenced(current, key), workspace, asset)
            if _material(after) != _material(view) or self._blockers(after, workspace, asset):
                raise CustodyUnavailable('Original recording changed during stop')
            _final(after)
            return {'view': after}

        inspected = await suppression.mutate_suppression(self.db, workspace, stop)
        if 'completed' in inspected: return inspected['completed']
        view = inspected['view']; original = view['artifact']
        _final(view)
        audio = await open_legacy_audio(original)
        _final(view)
        prepared = await seal_audio(audio, deepcopy(original))
        del audio
        _final(view)
        if not prepared.matches(): raise CustodyUnavailable('Recording conversion changed')

        async def install(current: Any) -> dict:
            saved = await current.outreach_credential_migrations.find_one(scope)
            if saved: return await self._saved(current, saved, request, workspace, asset)
            await verify(current, canonical_hash(view))
            changed = await current.outreach_voice_artifacts.update_one({'workspace_id': workspace, **original},
                {'$set': {'audio_enc': prepared.document['audio_enc']}})
            if changed.matched_count != 1: raise CustodyUnavailable('Original recording owner changed')
            row = await current.outreach_voice_artifacts.find_one({'workspace_id': workspace, '_id': asset})
            if not prepared.matches() or not _audio_matches_from_metadata(row, prepared.document):
                raise CustodyUnavailable('Original recording installation changed')
            job = await current.outreach_voice_preparation_jobs.find_one({'workspace_id': workspace, '_id': asset})
            receipt = {**scope, 'kind': 'voice_artifact', 'artifact_id': asset, 'status': 'completed',
                'request_digest': request, 'before_digest': expected_digest,
                'after_digest': _material({'artifact': row, 'job': job}),
                'original_record_digest': canonical_hash(original), 'original_job_digest': canonical_hash(view['job']),
                'audio_digest': original['audio_digest'], 'generation_digest': canonical_hash(original['generation_id']),
                'prepared_at': original['prepared_at'], 'expires_at': original['expires_at'],
                'target_policy_digest': view['policy_digest'], 'operator_digest': canonical_hash(operator),
                'evidence_digest': evidence_digest, 'at': now(), 'workers_drained': True,
                'activation_allowed': False, 'provenance': 'strict_fernet_voice_artifact_conversion'}
            await current.outreach_credential_migrations.insert_one(receipt)
            result = await self._saved(current, receipt, request, workspace, asset)
            _final(view)
            if not prepared.matches(): raise CustodyUnavailable('Recording conversion authority changed')
            return result

        return await suppression.mutate_suppression(self.db, workspace, install)


def _audio_matches_from_metadata(row: dict, prepared: dict) -> bool:
    """Database-only readback identity, ignoring authority fence counters."""
    return stable(row) == stable(prepared)
