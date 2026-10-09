"""Private bounded vendor GET evidence and database-only review-hold release.

The operator asserts an all-writer/cache drain. Configuration is process-local;
actual IAM/egress/remote revocation are outside this protocol. No adoption of a
new key or unproven profile, voice generation, campaign resume or send grants.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
import uuid

from outreach.core import erasure, suppression, voice_key_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_migration import _stable
from outreach.core.voice_source_review import VoiceSourceReview, configuration_metadata, profile_digest, root_digest
from outreach.core.voice_studio import VoiceStudio, consent_current, now
from outreach.core.voice_studio_review import HEX, LIMIT, REMOTE, VoiceStudioReview, flags_off, timestamp

READ_ACTIVE = ['preparing', 'possible']
READ_LIMIT = 20
EVIDENCE_AGE = timedelta(minutes=15)
PERMISSION = timedelta(seconds=60)
FIELDS = ('voice_id', 'category', 'is_owner', 'permission_on_resource', 'is_legacy',
    'is_mixed', 'safety_control', 'requires_verification', 'is_verified')


def normalized(value: Any) -> Any:
    if isinstance(value, datetime): return timestamp(value).isoformat()
    if isinstance(value, dict): return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, list): return [normalized(item) for item in value]
    return value


def digest(value: Any) -> str:
    return canonical_hash(normalized(value))


def metadata_projection(value: Any) -> dict:
    """Retain only bounded facts; absent/ambiguous fields remain unknown."""
    if not isinstance(value, dict): raise ValueError('Vendor metadata is unavailable')
    remote = value.get('voice_id')
    if not isinstance(remote, str) or not REMOTE.fullmatch(remote) or remote.startswith('voice_mock_'):
        raise ValueError('Vendor voice reference is unavailable')
    verification = value.get('voice_verification')
    verification = verification if isinstance(verification, dict) else {}
    result = {'voice_id': remote}
    for key in ('category', 'permission_on_resource', 'safety_control'):
        item = value.get(key)
        result[key] = item if isinstance(item, str) and 1 <= len(item) <= 64 else None
    for key in ('is_owner', 'is_legacy', 'is_mixed'):
        result[key] = value.get(key) if type(value.get(key)) is bool else None
    for key in ('requires_verification', 'is_verified'):
        result[key] = verification.get(key) if type(verification.get(key)) is bool else None
    return result


def receipt_valid(job: dict) -> bool:
    receipt = job.get('receipt')
    if not isinstance(receipt, dict) or set(receipt) != {'metadata', 'received_at', 'schema_version'}:
        return False
    stamp, possible, deadline = (timestamp(receipt.get('received_at')), timestamp(job.get('possible_at')),
        timestamp(job.get('authorization_expires_at')))
    metadata = receipt.get('metadata')
    if (not isinstance(metadata, dict) or set(metadata) != set(FIELDS) or type(receipt.get('schema_version')) is not int
            or receipt['schema_version'] != 1
            or not stamp or not possible or not deadline or not possible <= stamp <= deadline or stamp > now()
            or not isinstance(job.get('owner'), str) or not job['owner'].strip()
            or digest(receipt) != job.get('receipt_digest')):
        return False
    nested = {key: metadata[key] for key in FIELDS if key not in {'requires_verification', 'is_verified'}}
    nested['voice_verification'] = {key: metadata[key] for key in ('requires_verification', 'is_verified')}
    try: return metadata_projection(nested) == metadata
    except ValueError: return False


def public_read(job: dict) -> dict:
    identity, status = job.get('_id'), job.get('status')
    return {'job_id': identity if isinstance(identity, str) and HEX.fullmatch(identity) else None,
        'status': status if isinstance(status, str) and status in {
            'preparing', 'possible', 'received', 'released', 'stopped', 'read_interrupted'} else 'review_required',
        'activation_allowed': False}


class VoiceVendorEvidence:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.source = VoiceSourceReview(db)

    async def _snapshot(self, current: Any, workspace: str, voice: str, job_id: str | None = None) -> dict:
        snapshot = await self.source._snapshot(current, workspace, voice)
        snapshot['reads'] = [_stable(row) for row in await current.outreach_voice_vendor_reads.find({
            'workspace_id': workspace, 'voice_id': voice}).sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1)]
        snapshot['selected_read'] = next((row for row in snapshot['reads'] if row['_id'] == job_id), None)
        return snapshot

    @staticmethod
    def _binding(snapshot: dict) -> str:
        return digest({key: value for key, value in snapshot.items() if key not in {'reads', 'selected_read'}})

    @staticmethod
    def _job_reference(job_id: str | None) -> None:
        if not isinstance(job_id, str) or not HEX.fullmatch(job_id):
            raise ValueError('An exact vendor read reference is required')

    @classmethod
    def _blockers(cls, snapshot: dict) -> list[str]:
        reasons = [reason for reason in VoiceSourceReview._blockers(snapshot) if reason != 'source_already_current']
        profile = snapshot['profile'] or {}
        if profile.get('provider_source_digest') != snapshot['configuration']['source']:
            reasons.append('source_not_current')
        try: consent = isinstance(profile.get('consent'), dict) and consent_current(profile)
        except (ValueError, TypeError): consent = False
        recorded = profile.get('consent') if isinstance(profile.get('consent'), dict) else {}
        if not consent or not isinstance(recorded.get('assertion_digest'), str) or not HEX.fullmatch(
                recorded.get('assertion_digest', '')):
            reasons.append('recorded_consent_unproven')
        if (not isinstance(profile.get('status'), str) or profile['status'] not in {'review_required', 'needs_vendor_verification'}
                and profile.get('studio_review_required') is not True): reasons.append('review_hold_required')
        if len(snapshot['reads']) > LIMIT: reasons.append('vendor_read_capacity_exceeded')
        if any(row.get('status') in READ_ACTIVE for row in snapshot['reads']): reasons.append('vendor_read_unfinished')
        return reasons

    @staticmethod
    def _release_current(job: dict) -> bool:
        config = configuration_metadata()
        return bool(flags_off() and receipt_valid(job)
            and timestamp(job['receipt']['received_at']) + EVIDENCE_AGE > now()
            and config['digest'] == job['configuration_digest'] and config['source'] == job['provider_source_digest'])

    @classmethod
    def _capture_blockers(cls, snapshot: dict) -> list[str]:
        # Reserve space for the new permanent record so its release can still
        # inspect the complete bounded lineage.
        return cls._blockers(snapshot) + (['vendor_read_capacity_exceeded'] if len(snapshot['reads']) >= LIMIT else [])

    @classmethod
    def _release_blockers(cls, snapshot: dict) -> list[str]:
        reasons = cls._blockers(snapshot)
        job = snapshot['selected_read'] or {}
        root = VoiceSourceReview._root(snapshot)
        if job.get('status') != 'received' or not receipt_valid(job):
            return reasons + ['vendor_receipt_unproven']
        receipt = job['receipt']; metadata = receipt['metadata']; profile = snapshot['profile'] or {}
        if (job.get('profile_digest') != profile_digest(profile)
                or job.get('provider_source_digest') != snapshot['configuration']['source']
                or job.get('configuration_digest') != snapshot['configuration']['digest']
                or not root or job.get('root_clone_digest') != root_digest(root)
                or metadata['voice_id'] != profile.get('elevenlabs_voice_id')):
            reasons.append('vendor_evidence_binding_changed')
        if timestamp(receipt['received_at']) + EVIDENCE_AGE <= now(): reasons.append('vendor_evidence_expired')
        # Local policy deliberately accepts only explicitly owned instant clones
        # with admin metadata. Unknown permission semantics remain held.
        if (metadata['category'] != 'cloned' or metadata['is_owner'] is not True
                or metadata['permission_on_resource'] != 'admin' or metadata['is_legacy'] is not False
                or metadata['is_mixed'] is not False or metadata['safety_control'] != 'NONE'):
            reasons.append('vendor_ownership_or_permissions_unproven')
        if (metadata['requires_verification'] is not False or type(metadata['is_verified']) is not bool
                or root and root['receipt']['requires_verification'] and metadata['is_verified'] is not True):
            reasons.append('vendor_verification_unproven')
        return reasons

    async def inspect(self, workspace: str, voice: str, job_id: str | None = None) -> dict:
        if job_id is not None: self._job_reference(job_id)
        snapshot = await self._snapshot(self.db, workspace, voice, job_id)
        blockers = self._release_blockers(snapshot) if job_id else self._capture_blockers(snapshot)
        return {'workspace_id': workspace, 'voice_id': voice, 'review_digest': digest(snapshot),
            'blockers': blockers, 'capture_available': not self._capture_blockers(snapshot),
            'release_available': bool(job_id and not blockers), 'activation_allowed': False,
            'reads': [public_read(row) for row in snapshot['reads']]}

    @staticmethod
    def _arguments(operator: str, evidence: str, expected: str, drained: bool) -> tuple[str, str]:
        if (drained is not True or not flags_off() or not isinstance(operator, str)
                or not 1 <= len(operator.strip()) <= 256 or any(ord(c) < 32 or ord(c) == 127 for c in operator)
                or not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 2000
                or not isinstance(expected, str) or not HEX.fullmatch(expected)):
            raise ValueError('Disabled flags, exact inspection and identified all-writer/cache drain are required')
        return canonical_hash(operator.strip()), canonical_hash(evidence.strip())

    async def capture(self, workspace: str, voice: str, operator: str, evidence: str, expected_digest: str, *,
                      workers_drained: bool = False, provider: Callable[[dict], Awaitable[dict]] | None = None) -> dict:
        self.source._scope(workspace, voice)
        actor, proof = self._arguments(operator, evidence, expected_digest, workers_drained)
        from outreach.core.restore_epoch import positive
        epoch = await positive(self.db, workspace)
        scope = {'workspace_id': workspace, '_id': canonical_hash(['voice-vendor-read-v1', workspace, voice, expected_digest])}
        owner = uuid.uuid4().hex

        async def prepare(current):
            saved = await current.outreach_voice_vendor_reads.find_one(scope)
            if saved:
                if saved.get('operator_digest') != actor or saved.get('evidence_digest') != proof:
                    raise ValueError('A different vendor read is already recorded')
                return {'saved': public_read(saved)}
            snapshot = await self._snapshot(VoiceStudio._authorities(current), workspace, voice)
            if digest(snapshot) != expected_digest or self._capture_blockers(snapshot):
                raise ValueError('Vendor read inspection changed; drain and inspect again')
            profile = snapshot['profile']; root = self.source._root(snapshot); stamp = now()
            job = {**scope, 'voice_id': voice, 'provider_voice_id': profile['elevenlabs_voice_id'],
                'status': 'preparing', 'mutation': False, 'owner': owner, 'operator_digest': actor,
                'evidence_digest': proof, 'inspection_digest': expected_digest, 'authority_digest': self._binding(snapshot),
                'profile_digest': profile_digest(profile), 'root_clone_digest': root_digest(root),
                'configuration_digest': snapshot['configuration']['digest'], 'provider_source_digest': profile['provider_source_digest'],
                'authorization_expires_at': stamp + PERMISSION, 'created_at': stamp}
            await current.outreach_voice_vendor_reads.insert_one(job)
            return {'job': job}
        checked = await suppression.mutate_suppression(self.db, workspace, prepare)
        if 'saved' in checked: return checked['saved']
        job = checked['job']
        try:
            credential = await voice_key_custody.prepare_key(expected_digest=job['configuration_digest'],
                expected_source=job['provider_source_digest'])
            def allowed():
                return epoch.live() and flags_off() and credential.matches() and now() < timestamp(job['authorization_expires_at'])
            async def authorize(current):
                await positive(current, workspace, captured=epoch.captured)
                record = await current.outreach_voice_vendor_reads.find_one(scope)
                snapshot = await self._snapshot(VoiceStudio._authorities(current), workspace, voice)
                others = {**snapshot, 'reads': [row for row in snapshot['reads'] if row['_id'] != job['_id']]}
                if (not record or record.get('owner') != owner or record.get('status') != 'preparing'
                        or self._binding(snapshot) != job['authority_digest'] or self._blockers(others) or not allowed()):
                    raise ValueError('Vendor read authority changed')
                stamp = now(); day = stamp.date().isoformat()
                budget = {'workspace_id': workspace, '_id': canonical_hash([workspace, 'vendor_metadata', day])}
                await current.outreach_voice_studio_budgets.update_one(budget, {'$setOnInsert': {
                    'operation': 'vendor_metadata', 'day': day, 'calls': 0}}, upsert=True)
                consumed = await current.outreach_voice_studio_budgets.update_one({**budget, 'calls': {'$lt': READ_LIMIT}},
                    {'$inc': {'calls': 1}})
                if consumed.matched_count != 1: raise ValueError('Vendor metadata daily budget reached')
                changed = await current.outreach_voice_vendor_reads.update_one({**scope, 'status': 'preparing', 'owner': owner},
                    {'$set': {'status': 'possible', 'possible_at': stamp, 'budget_day': day}})
                if changed.matched_count != 1 or not allowed(): raise ValueError('Vendor read owner changed')
            await suppression.mutate_suppression(self.db, workspace, authorize)
            if not allowed(): raise ValueError('Vendor read permission expired')
            if provider is None:
                from outreach.core.voice_vendor_provider import metadata_call
                provider = metadata_call
            async with asyncio.timeout(30):
                metadata = metadata_projection(await provider({'voice_id': job['provider_voice_id'],
                    'credential': credential, 'allowed': allowed}))
            receipt = {'metadata': metadata, 'schema_version': 1, 'received_at': now()}
            async def save(current):
                changed = await current.outreach_voice_vendor_reads.update_one({**scope, 'owner': owner, 'status': 'possible',
                    'receipt': {'$exists': False}}, {'$set': {'receipt': receipt, 'receipt_digest': digest(receipt), 'status': 'received'}})
                if changed.matched_count != 1: raise ValueError('Vendor receipt owner changed')
            await suppression.mutate_suppression(self.db, workspace, save)
        except Exception:
            # Only a proved pre-call state can stop. Possible reads retain their
            # marker/budget; received acknowledgement loss preserves the receipt.
            async def stop(current):
                await current.outreach_voice_vendor_reads.update_one({**scope, 'owner': owner, 'status': 'preparing'},
                    {'$set': {'status': 'stopped', 'error_code': 'vendor_read_not_authorized'}})
            try: await suppression.mutate_suppression(self.db, workspace, stop)
            except Exception: pass
        saved = await self.db.outreach_voice_vendor_reads.find_one(scope)
        if not saved: raise ValueError('Vendor read custody needs operator inspection')
        return public_read(saved)

    async def release(self, workspace: str, voice: str, job_id: str, operator: str, evidence: str, expected_digest: str, *,
                      workers_drained: bool = False) -> dict:
        self.source._scope(workspace, voice)
        self._job_reference(job_id)
        actor, proof = self._arguments(operator, evidence, expected_digest, workers_drained)
        async def apply(current):
            scope = {'workspace_id': workspace, '_id': job_id, 'voice_id': voice}
            job = await current.outreach_voice_vendor_reads.find_one(scope)
            if job and job.get('status') == 'released':
                release = job.get('release') or {}
                if any(release.get(key) != value for key, value in (
                        ('operator_digest', actor), ('evidence_digest', proof), ('review_digest', expected_digest))):
                    raise ValueError('A different hold release is already saved')
                profile = await current.outreach_voices.find_one(self.source._scope(workspace, voice))
                config = configuration_metadata()
                return {'status': 'released', 'job_id': job_id, 'activation_allowed': False,
                    'current_matches': profile_digest(profile) == release['after_digest']
                        and config['source'] == job['provider_source_digest']
                        and config['digest'] == job['configuration_digest']}
            from outreach.core.restore_epoch import positive
            epoch = await positive(current, workspace)
            snapshot = await self._snapshot(VoiceStudio._authorities(current), workspace, voice, job_id)
            if digest(snapshot) != expected_digest or self._release_blockers(snapshot):
                raise ValueError('Fresh vendor ownership, verification and unchanged recorded consent are required')
            profile = snapshot['profile']; stamp = now()
            await VoiceStudioReview(self.db)._stop_authority(current, snapshot, operator.strip(), stamp, 'voice_vendor_review')
            if not self._release_current(job): raise ValueError('Vendor evidence expired or configuration changed')
            changed = await current.outreach_voices.update_one({**self.source._scope(workspace, voice), '_id': profile['_id'],
                'revision': profile['revision'], 'elevenlabs_voice_id': profile['elevenlabs_voice_id'],
                'provider_source_digest': profile['provider_source_digest'], 'studio_job_id': {'$exists': False}}, {'$set': {
                    'status': 'active', 'studio_review_required': False, 'updated_at': stamp,
                    'vendor_evidence_id': job_id}, '$inc': {'revision': 1}})
            if changed.matched_count != 1: raise ValueError('Voice review owner changed')
            after = await current.outreach_voices.find_one(self.source._scope(workspace, voice))
            journal = {'operator_digest': actor, 'evidence_digest': proof, 'review_digest': expected_digest,
                'after_digest': profile_digest(after), 'at': stamp, 'receipt_digest': job['receipt_digest'],
                'provenance': 'saved_vendor_metadata', 'activation_allowed': False}
            changed = await current.outreach_voice_vendor_reads.update_one({**scope, 'owner': job['owner'],
                'status': 'received', 'receipt_digest': job['receipt_digest']}, {'$set': {'status': 'released', 'release': journal}})
            if changed.matched_count != 1 or not self._release_current(job): raise ValueError('Vendor receipt changed')
            epoch.assert_live()
            return {'status': 'released', 'job_id': job_id, 'current_matches': True, 'activation_allowed': False}
        return await suppression.mutate_suppression(self.db, workspace, apply)

    async def close_read(self, workspace: str, voice: str, job_id: str, operator: str, evidence: str, expected_digest: str, *,
                         workers_drained: bool = False) -> dict:
        self.source._scope(workspace, voice)
        self._job_reference(job_id)
        actor, proof = self._arguments(operator, evidence, expected_digest, workers_drained)
        async def apply(current):
            snapshot = await self._snapshot(VoiceStudio._authorities(current), workspace, voice, job_id)
            job = snapshot['selected_read'] or {}
            closure = job.get('closure') or {}
            if closure:
                if closure != {'operator_digest': actor, 'evidence_digest': proof, 'review_digest': expected_digest}:
                    raise ValueError('A different read closure is already saved')
                return public_read(job)
            deadline = timestamp(job.get('authorization_expires_at'))
            if (digest(snapshot) != expected_digest or job.get('status') not in READ_ACTIVE
                    or not deadline or deadline > now() or job.get('receipt') or not isinstance(job.get('owner'), str)):
                raise ValueError('An exact drained expired read without a receipt is required')
            status = 'read_interrupted' if job.get('possible_at') else 'stopped'
            changed = await current.outreach_voice_vendor_reads.update_one({'workspace_id': workspace, '_id': job_id,
                'voice_id': voice, 'owner': job['owner'], 'status': job['status'], 'receipt': {'$exists': False}}, {'$set': {
                    'status': status, 'closure': {'operator_digest': actor, 'evidence_digest': proof, 'review_digest': expected_digest}}})
            if changed.matched_count != 1 or not flags_off(): raise ValueError('Read closure owner changed')
            return {'job_id': job_id, 'status': status, 'activation_allowed': False}
        return await suppression.mutate_suppression(self.db, workspace, apply)
