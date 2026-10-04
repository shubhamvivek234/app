"""Private same-key storage migration, without vendor identity or activation.

Old/new custody opens happen outside Mongo callbacks. Current configuration and
all-writer/cache drain are process-local/operator assertions. Different keys and
unproven legacy profiles require a separate vendor-evidence protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
from typing import Any, Callable

from outreach.core import erasure, session_custody, suppression, voice_key_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from outreach.core.credential_migration import _stable
from outreach.core.voice_studio import VoiceStudio, now, profile_identity
from outreach.core.voice_studio_review import (
    HEX, REMOTE, LIMIT, VoiceStudioReview, authority_snapshot, flags_off, receipt_valid, timestamp,
)


@dataclass(frozen=True)
class PreviousKey:
    """Transient original key or scoped envelope; never stored in a journal."""
    storage: str = field(repr=False)
    mode: str = 'legacy_fernet'
    generation: str = ''

    def configuration(self, policy: tuple[str, ...]) -> voice_key_custody.KeyConfiguration:
        if self.mode == 'legacy_fernet':
            voice_key_custody._validate_key(self.storage)
            if self.generation:
                raise CustodyUnavailable('Original key scope is unavailable')
        elif self.mode == 'kms_v1':
            if (not isinstance(self.storage, str) or not self.storage.startswith(PREFIX)
                    or len(self.storage.encode()) > 60000):
                raise CustodyUnavailable('Original key scope is unavailable')
            voice_key_custody.key_context(self.generation)
        else:
            raise CustodyUnavailable('Original key scope is unavailable')
        return voice_key_custody.KeyConfiguration(self.storage, self.generation, (self.mode, *policy[1:]))


def configuration_metadata() -> dict:
    try:
        config = voice_key_custody.capture_configuration()
        return {'digest': config.digest, 'source': config.source, 'scoped': config.policy[0] == 'kms_v1'}
    except ValueError:
        return {'digest': None, 'source': None, 'scoped': False}


def root_digest(job: dict) -> str:
    """Normalize original received timestamps across BSON UTC codec options."""
    receipt = job['receipt']
    return canonical_hash([job['_id'], job['workspace_id'], job['voice_id'], job['owner'],
        job['payload_digest'], job['provider_source_digest'], timestamp(job['possible_at']).isoformat(),
        receipt['voice_id'], receipt['requires_verification'], timestamp(receipt['received_at']).isoformat()])


def profile_digest(profile: dict | None) -> str | None:
    try:
        return canonical_hash([profile_identity(profile), bool(profile.get('studio_review_required'))]) if profile else None
    except (TypeError, ValueError):
        return None


class VoiceSourceReview:
    """Private metadata migration rooted in an original clone receipt."""

    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def _scope(workspace: str, voice: str) -> dict:
        if any(not isinstance(value, str) or not 1 <= len(value) <= 256 or value.strip() != value
               or any(ord(char) < 32 or ord(char) == 127 for char in value) for value in (workspace, voice)):
            raise ValueError('Workspace and voice references are required')
        return {'workspace_id': workspace, 'id': voice}

    async def _snapshot(self, current: Any, workspace: str, voice: str) -> dict:
        profile = _stable(await current.outreach_voices.find_one(self._scope(workspace, voice)))
        snapshot = {'profile': profile, 'job': {'workspace_id': workspace},
            'workspace_open': await erasure.workspace_is_open(current, workspace),
            'configuration': configuration_metadata(), 'flags_off': flags_off()}
        snapshot.update(await authority_snapshot(current, workspace))
        for name, collection in (('profile_jobs', 'outreach_voice_studio_jobs'),
                                 ('lineage', 'outreach_voice_source_migrations')):
            snapshot[name] = [_stable(row) for row in await getattr(current, collection).find({
                'workspace_id': workspace, 'voice_id': voice}).sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1)]
        return snapshot

    @staticmethod
    def _root(snapshot: dict) -> dict | None:
        profile = snapshot['profile'] or {}
        proofs = []
        for job in snapshot['profile_jobs']:
            if (job.get('operation') != 'clone' or job.get('voice_id') != profile.get('id')
                    or job.get('voice_id') != canonical_hash(['voice_profile', job['_id']])
                    or not isinstance(job.get('status'), str) or job['status'] not in {'completed', 'review_completed'}
                    or not isinstance(job.get('owner'), str) or not job['owner'].strip()
                    or not receipt_valid(job) or job['receipt']['voice_id'] != profile.get('elevenlabs_voice_id')
                    or any(not isinstance(job.get(key), str) or not HEX.fullmatch(job[key])
                           for key in ('payload_digest', 'provider_source_digest', 'profile_identity', 'configuration_digest'))):
                continue
            if job['status'] == 'review_completed':
                review = job.get('review') or {}
                if (review.get('provenance') != 'saved_provider_receipt' or review.get('decision') != 'use_receipt'
                        or review.get('outcome_at_review') != 'received'):
                    continue
            digest = root_digest(job)
            links = [row for row in snapshot['lineage'] if row.get('status') == 'completed'
                and row.get('provenance') == 'same_key_continuity' and row.get('activation_allowed') is False
                and row.get('after_source') == profile.get('provider_source_digest')
                and row.get('root_clone_digest') == digest and row.get('clone_source') == job['provider_source_digest']
                and row.get('remote_digest') == canonical_hash(profile.get('elevenlabs_voice_id'))
                and type(row.get('after_revision')) is int and type(profile.get('revision')) is int
                and row['after_revision'] <= profile['revision']]
            if job['provider_source_digest'] == profile.get('provider_source_digest') or len(links) == 1:
                proofs.append(job)
        return proofs[0] if len(proofs) == 1 else None

    @classmethod
    def _blockers(cls, snapshot: dict) -> list[str]:
        reasons = []
        profile = snapshot['profile'] or {}
        remote = profile.get('elevenlabs_voice_id')
        source = profile.get('provider_source_digest')
        if (not profile or not isinstance(profile.get('status'), str)
                or profile['status'] not in {'active', 'consent_revoked', 'needs_vendor_verification', 'review_required'}
                or not isinstance(profile.get('consent'), dict)
                or type(profile.get('revision')) is not int or profile['revision'] < 1
                or not isinstance(remote, str) or not REMOTE.fullmatch(remote) or remote.startswith('voice_mock_')
                or not isinstance(source, str) or not HEX.fullmatch(source)):
            reasons.append('profile_binding_unproven')
        if 'studio_job_id' in profile: reasons.append('profile_work_unfinished')
        if not snapshot['workspace_open']: reasons.append('workspace_closed')
        if not snapshot['flags_off']: reasons.append('provider_flags_enabled')
        if not snapshot['configuration']['scoped']: reasons.append('scoped_destination_required')
        if source and source == snapshot['configuration']['source']: reasons.append('source_already_current')
        if cls._root(snapshot) is None: reasons.append('original_clone_receipt_unproven')
        for name in ('studio_jobs', 'preparations', 'accounts', 'campaigns', 'executions', 'permissions', 'profile_jobs', 'lineage'):
            if len(snapshot[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
        if snapshot['studio_jobs']: reasons.append('studio_work_pending')
        if any(row.get('status') in {'claimed', 'generating'} for row in snapshot['preparations']):
            reasons.append('campaign_preparation_not_recovered')
        if any(row.get('status') != 'idle' and timestamp(row.get('expires_at')) and timestamp(row['expires_at']) > now()
               for row in snapshot['executions']): reasons.append('sender_worker_lease_live')
        if any(not isinstance(row.get('id'), str) or not row['id'] for row in snapshot['accounts']):
            reasons.append('sender_identity_unproven')
        if any((row.get('review') or {}).get('outcome_at_review') == 'unknown'
               or row.get('possible_at') and not receipt_valid(row)
               or row.get('operation') == 'delete' and receipt_valid(row) for row in snapshot['profile_jobs']):
            reasons.append('profile_provider_outcome_unresolved_or_deleted')
        return reasons

    async def inspect(self, workspace: str, voice: str) -> dict:
        snapshot = await self._snapshot(self.db, workspace, voice)
        reasons = self._blockers(snapshot)
        return {'workspace_id': workspace, 'voice_id': voice, 'review_digest': canonical_hash(snapshot),
            'blockers': reasons, 'migration_available': not reasons, 'activation_allowed': False,
            'original_clone_proven': self._root(snapshot) is not None,
            'source_is_current': bool(snapshot['profile'] and snapshot['profile'].get('provider_source_digest')
                == snapshot['configuration']['source']), 'senders_to_pause': len(snapshot['accounts']),
            'campaigns_to_pause': len(snapshot['campaigns'])}

    async def _saved(self, current: Any, receipt: dict, operator: str, evidence: str) -> dict:
        if (receipt.get('operator') != operator or receipt.get('evidence') != evidence
                or receipt.get('status') != 'completed' or receipt.get('provenance') != 'same_key_continuity'):
            raise ValueError('A different source review is already saved')
        profile = await current.outreach_voices.find_one(self._scope(receipt['workspace_id'], receipt['voice_id']))
        config = configuration_metadata()
        return {'status': 'completed', 'migration_id': receipt['_id'], 'activation_allowed': False,
            'current_matches': bool(profile_digest(profile) == receipt['after_digest']
                and config['digest'] == receipt['configuration_digest'] and config['source'] == receipt['after_source'])}

    async def migrate(self, workspace: str, voice: str, operator: str, evidence: str, expected_digest: str, *,
                      workers_drained: bool = False,
                      previous_key: PreviousKey | Callable[[], PreviousKey] | None = None) -> dict:
        """Prove identical plaintext keys outside transactions, then stop and bind."""
        self._scope(workspace, voice)
        if (workers_drained is not True or not flags_off() or session_custody.custody_mode() != 'kms_v1'
                or not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in operator)
                or not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 2000
                or not isinstance(expected_digest, str) or not HEX.fullmatch(expected_digest)):
            raise ValueError('Scoped custody, disabled flags, exact inspection and identified all-writer drain are required')
        operator, evidence = operator.strip(), evidence.strip()
        scope = {'workspace_id': workspace, '_id': canonical_hash(['voice-source-review-v1', workspace, voice, expected_digest])}

        async def verify(current):
            saved = await current.outreach_voice_source_migrations.find_one(scope)
            if saved: return {'saved': await self._saved(current, saved, operator, evidence)}
            snapshot = await self._snapshot(VoiceStudio._authorities(current), workspace, voice)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot):
                raise ValueError('Source inspection changed; drain and inspect again')
            return {'snapshot': snapshot}

        checked = await suppression.mutate_suppression(self.db, workspace, verify)
        if 'saved' in checked: return checked['saved']
        snapshot = checked['snapshot']
        try:
            previous = previous_key() if callable(previous_key) else previous_key
            if not isinstance(previous, PreviousKey): raise CustodyUnavailable('Original key material is required')
            config = voice_key_custody.capture_configuration()
            original = previous.configuration(config.policy)
            if (config.digest != snapshot['configuration']['digest']
                    or original.source != snapshot['profile']['provider_source_digest']):
                raise CustodyUnavailable('Original source continuity is unavailable')
            old_value = (await session_custody.configured_custody().open(original.storage,
                voice_key_custody.key_context(original.generation)) if previous.mode == 'kms_v1' else original.storage)
            voice_key_custody._validate_key(old_value)
            prepared = await voice_key_custody.prepare_key(expected_digest=config.digest)
            same = hmac.compare_digest(old_value, prepared.value)
            del old_value
            if not same or not prepared.matches() or not flags_off():
                raise CustodyUnavailable('Original source continuity is unavailable')
        except Exception:
            raise CustodyUnavailable('Original and destination key continuity could not be proven') from None

        async def install(current):
            saved = await current.outreach_voice_source_migrations.find_one(scope)
            if saved: return await self._saved(current, saved, operator, evidence)
            captured = await self._snapshot(VoiceStudio._authorities(current), workspace, voice)
            if (canonical_hash(captured) != expected_digest or self._blockers(captured)
                    or not prepared.matches() or not flags_off()):
                raise CustodyUnavailable('Source inspection changed before installation')
            stamp = now()
            await VoiceStudioReview(self.db)._stop_authority(current, captured, operator, stamp, 'voice_source_review')
            profile = captured['profile']
            root = self._root(captured)
            status = ('consent_revoked' if profile['status'] == 'consent_revoked' else 'needs_vendor_verification'
                if profile['status'] == 'needs_vendor_verification' or root['receipt']['requires_verification'] else 'review_required')
            changed = await current.outreach_voices.update_one({**self._scope(workspace, voice), '_id': profile['_id'],
                'revision': profile['revision'], 'provider_source_digest': profile['provider_source_digest'],
                'elevenlabs_voice_id': profile['elevenlabs_voice_id'], 'studio_job_id': {'$exists': False}}, {'$set': {
                    'provider_source_digest': prepared.config.source, 'studio_review_required': True,
                    'status': status, 'updated_at': stamp}, '$inc': {'revision': 1}})
            if changed.matched_count != 1: raise CustodyUnavailable('Original voice owner changed')
            after = await current.outreach_voices.find_one(self._scope(workspace, voice))
            if not prepared.matches() or not flags_off(): raise CustodyUnavailable('Voice deployment configuration changed')
            receipt = {**scope, 'voice_id': voice, 'status': 'completed', 'provenance': 'same_key_continuity',
                'operator': operator, 'evidence': evidence, 'workers_drained': True, 'review_digest': expected_digest,
                'before_source': profile['provider_source_digest'], 'after_source': prepared.config.source,
                'configuration_digest': prepared.config.digest, 'root_clone_digest': root_digest(root),
                'clone_source': root['provider_source_digest'], 'remote_digest': canonical_hash(profile['elevenlabs_voice_id']),
                'after_revision': after['revision'], 'after_digest': profile_digest(after), 'at': stamp, 'activation_allowed': False}
            await current.outreach_voice_source_migrations.insert_one(receipt)
            return await self._saved(current, receipt, operator, evidence)
        return await suppression.mutate_suppression(self.db, workspace, install)
