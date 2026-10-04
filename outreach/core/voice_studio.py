"""Durable consent-bound Studio work. Possible provider calls never replay."""
from __future__ import annotations

import asyncio
import os
import logging
import re
import uuid
from typing import Awaitable, Callable
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta, timezone

from outreach.core import suppression, session_custody
from outreach.core.voice_key_custody import source_digest, prepare_key
from outreach.core.authorization import canonical_hash
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.paid_access import get_active_entitlement, _utc
from outreach.core.voice_policy import validate_audio
from outreach.core.voice_studio_custody import seal_blob, open_blob
from utils.roles import has_permission

LEASE = timedelta(minutes=2)
CONSENT_VERSION = 1
ACTIVE = ['queued', 'preparing', 'possible', 'received', 'held_outcome', 'held_received']
LIMITS = {'clone': 5, 'preview': 20, 'delete': 10}
logger = logging.getLogger(__name__)


def now() -> datetime:
    # Match BSON millisecond precision so frozen profile identities survive reads.
    value = datetime.now(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def enabled() -> bool:
    return os.getenv('OUTREACH_VOICE_STUDIO_ENABLED', 'false').strip().lower() in {'true', '1'}


def configuration() -> str:
    if not enabled():
        raise ValueError('Voice Studio is disabled')
    return canonical_hash([source_digest(), session_custody.custody_mode(),
        *[os.getenv(name, '').strip() for name in ('OUTREACH_CUSTODY_ENVIRONMENT_ID',
        'OUTREACH_KMS_KEY_ARN', 'OUTREACH_KMS_ROLE_ARN', 'OUTREACH_KMS_ROLE_ID',
        'OUTREACH_KMS_REGION', 'OUTREACH_KMS_CREDENTIAL_PROVIDER')]])


def consent_current(profile: dict) -> bool:
    consent = profile.get('consent') or {}
    asserted = consent.get('asserted_at')
    expiry = _utc(asserted) if isinstance(asserted, (datetime, str)) else None
    if expiry:
        expiry = expiry.replace(microsecond=expiry.microsecond // 1000 * 1000)
    return bool(type(consent.get('version')) is int and consent['version'] == CONSENT_VERSION
        and isinstance(consent.get('actor'), str) and consent['actor'].strip()
        and expiry and expiry <= now() and consent.get('assertion_digest'))


def require_profile(profile: dict | None) -> dict:
    if not profile or profile.get('studio_review_required') or profile.get('status') != 'active' or not consent_current(profile):
        raise ValueError('Voice profile needs active recorded consent')
    if profile.get('provider_source_digest') != source_digest():
        raise ValueError('Voice profile provider source needs operator review')
    return profile


def profile_identity(profile: dict) -> str:
    values = {key: profile.get(key) for key in ('id', 'elevenlabs_voice_id',
        'revision', 'status', 'consent', 'provider_source_digest')}
    consent = dict(values['consent'] or {})
    asserted = consent.get('asserted_at')
    stamp = _utc(asserted) if isinstance(asserted, (datetime, str)) else None
    if stamp:
        consent['asserted_at'] = stamp.replace(microsecond=stamp.microsecond // 1000 * 1000)
    values['consent'] = consent
    return canonical_hash(values)


def public_job(job: dict) -> dict:
    return {key: job[key] for key in ('_id', 'voice_id', 'operation', 'status', 'created_at',
        'updated_at', 'error_code', 'result_expires_at') if key in job}


class VoiceStudio:
    def __init__(self, db: AsyncIOMotorDatabase | suppression.SuppressionDatabase) -> None:
        self.db = db

    @staticmethod
    def scope(workspace: str, job_id: str) -> dict[str, str]:
        return {'workspace_id': workspace, '_id': job_id}

    async def _control(self, workspace, callback):
        try:
            return await suppression.mutate_suppression(self.db, workspace, callback)
        except suppression.SuppressionUnavailable:
            from outreach.core.erasure import _control
            return await _control(self.db, workspace, callback)

    async def _access(self, current, workspace, actor, operation):
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError('An identified workspace member is required')
        if isinstance(current, suppression.SuppressionDatabase):
            members = current.database.workspace_members
            options = {'session': current.session}
        else:
            members, options = current.workspace_members, {}
        member = await members.find_one({'workspace_id': workspace, 'user_id': actor}, **options)
        if not member or not has_permission(member.get('role'), 'voice:manage'):
            raise ValueError('Voice management permission is required')
        # Membership is an authority too; concurrent revocation must conflict.
        changed = await members.update_one({'workspace_id': workspace, 'user_id': actor,
            'role': member['role']}, {'$inc': {'voice_authority_revision': 1}}, **options)
        if changed.matched_count != 1:
            raise ValueError('Workspace permission changed')
        fenced = (AuthorityDatabase(current.database, current.session, 'voice_studio')
            if isinstance(current, suppression.SuppressionDatabase) else current)
        expiry = now() + timedelta(minutes=15)
        if operation != 'delete':
            entitlement = await get_active_entitlement(fenced, workspace)
            if not entitlement:
                raise ValueError('Voice Studio requires an active paid workspace')
            expiry = min(expiry, _utc(entitlement['paid_through']))
        return expiry

    @staticmethod
    def _authorities(current):
        return (AuthorityDatabase(current.database, current.session, 'voice_studio')
            if isinstance(current, suppression.SuppressionDatabase) else current)

    async def _validate(self, current, job):
        if configuration() != job['configuration_digest']:
            raise ValueError('Voice configuration changed')
        expiry = await self._access(current, job['workspace_id'], job['actor'], job['operation'])
        if now() >= _utc(job['authorization_expires_at']):
            raise ValueError('Voice request expired')
        profile = await self._authorities(current).outreach_voices.find_one({'workspace_id': job['workspace_id'], 'id': job['voice_id']})
        if not profile or profile.get('studio_job_id') != job['_id'] or profile_identity(profile) != job['profile_identity']:
            raise ValueError('Voice profile changed')
        return min(expiry, _utc(job['authorization_expires_at']))

    async def queue(self, workspace: str, actor: str, operation: str, request_id: str, *, name: str = '', audio: bytes | None = None,
                    consent: bool = False, voice_id: str | None = None, script: str = '') -> dict:
        if operation not in LIMITS or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
            raise ValueError('A stable request ID and supported operation are required')
        if operation == 'clone':
            if consent is not True or not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
                raise ValueError('A voice name and explicit speaker consent are required')
            if validate_audio(audio)['duration_ms'] < 20000:
                raise ValueError('Record 20–60 seconds of mono PCM WAV audio')
            raw = audio
        elif operation == 'preview':
            if not isinstance(script, str) or not 1 <= len(script.strip()) <= 1000 or '{{' in script or '}}' in script:
                raise ValueError('Preview needs 1–1000 finished script characters')
            raw = script.encode()
        else:
            raw = None
        stamp = configuration()
        frozen_source = source_digest()
        job_id = canonical_hash(['voice_studio', workspace, actor, operation, request_id])
        payload = canonical_hash([operation, name.strip(), canonical_hash(audio) if audio else None,
            consent, voice_id, script])
        scope = self.scope(workspace, job_id)
        async def preflight(current):
            await self._access(current, workspace, actor, operation)
            old = await current.outreach_voice_studio_jobs.find_one(scope)
            if old and old['payload_digest'] != payload:
                raise ValueError('Request ID belongs to different content')
            return old
        old = await suppression.mutate_suppression(self.db, workspace, preflight)
        if old:
            return old
        created = now()
        job = {**scope, 'operation': operation, 'actor': actor, 'payload_digest': payload,
            'configuration_digest': stamp, 'provider_source_digest': frozen_source,
            'voice_id': voice_id or canonical_hash(['voice_profile', job_id]), 'status': 'queued',
            'created_at': created, 'updated_at': created, 'next_publish_at': created,
            'next_recovery_at': created + timedelta(minutes=15), 'mutation': operation != 'preview',
            'chars': len(script), 'name': name.strip()}
        if operation == 'clone':
            job['consent'] = {'actor': actor, 'version': CONSENT_VERSION, 'asserted_at': created,
                'assertion_digest': canonical_hash(['speaker_owns_or_authorized', actor, payload, CONSENT_VERSION])}
        if raw:
            job['input_enc'] = await seal_blob(raw, job, 'input')
        async def save(current):
            expiry = await self._access(current, workspace, actor, operation)
            if configuration() != stamp or source_digest() != frozen_source:
                raise ValueError('Voice configuration changed')
            old = await current.outreach_voice_studio_jobs.find_one(scope)
            if old:
                if old['payload_digest'] != payload:
                    raise ValueError('Request ID belongs to different content')
                return old
            job['authorization_expires_at'] = min(expiry, created + timedelta(minutes=15))
            if operation == 'clone':
                if await current.outreach_voices.count_documents({'workspace_id': workspace}) >= 5:
                    raise ValueError('Voice profile limit reached (5)')
                profile = {'_id': job['voice_id'], 'id': job['voice_id'], 'workspace_id': workspace,
                    'name': job['name'], 'status': 'creating', 'revision': 1, 'studio_job_id': job_id,
                    'consent': job['consent'], 'provider_source_digest': job['provider_source_digest'],
                    'created_at': created, 'updated_at': created, 'assigned_account_ids': []}
                await current.outreach_voices.insert_one(profile)
            else:
                profile = await current.outreach_voices.find_one({'workspace_id': workspace, 'id': voice_id})
                if profile and profile.get('studio_review_required'):
                    raise ValueError('Voice profile requires drained operator review')
                if operation == 'delete':
                    if not profile or profile.get('status') not in {'active', 'consent_revoked', 'needs_vendor_verification'} or profile.get('provider_source_digest') != source_digest():
                        raise ValueError('Voice cleanup needs a proven provider source')
                    job['prior_status'] = profile['status']
                else:
                    require_profile(profile)
                if profile.get('studio_job_id'):
                    raise ValueError('Voice profile has unfinished Studio work')
                if operation == 'delete' and await current.outreach_voice_preparation_jobs.find_one({
                        'workspace_id': workspace, 'binding.content.voice_id': profile['elevenlabs_voice_id'],
                        'status': {'$in': ['claimed', 'generating']}}):
                    raise ValueError('Wait for active campaign voice preparation before deleting')
                change = {'$set': {'studio_job_id': job_id}}
                if operation == 'delete':
                    change['$set']['status'] = 'deleting'
                    change['$inc'] = {'revision': 1}
                result = await current.outreach_voices.update_one({'workspace_id': workspace, 'id': voice_id,
                    'revision': profile['revision'], 'studio_job_id': {'$exists': False}}, change)
                if result.matched_count != 1:
                    raise ValueError('Voice profile owner changed')
                profile = await current.outreach_voices.find_one({'workspace_id': workspace, 'id': voice_id})
                job['provider_voice_id'] = profile['elevenlabs_voice_id']
            job['profile_identity'] = profile_identity(profile)
            await current.outreach_voice_studio_jobs.insert_one(job)
            return await current.outreach_voice_studio_jobs.find_one(scope)
        try:
            return await suppression.mutate_suppression(self.db, workspace, save)
        except Exception:
            # Lost commit acknowledgement: same identity/content may be read back,
            # never manufacture a replacement request or provider call.
            old = await self.db.outreach_voice_studio_jobs.find_one(scope)
            if old and old.get('payload_digest') == payload:
                return old
            raise

    async def _stop(self, current, job, status):
        scope = self.scope(job['workspace_id'], job['_id'])
        changed = await current.outreach_voice_studio_jobs.update_one({**scope, 'status': job['status'],
            'owner': job.get('owner')}, {'$set': {'status': status, 'updated_at': now()}, '$unset': {'input_enc': ''}})
        if changed.matched_count != 1:
            return
        profile_scope = {'workspace_id': job['workspace_id'], 'id': job['voice_id'], 'studio_job_id': job['_id']}
        profile = await current.outreach_voices.find_one(profile_scope)
        if not profile:
            return
        if profile.get('provider_source_digest') != job['provider_source_digest'] or profile.get('elevenlabs_voice_id') != job.get('provider_voice_id'):
            await current.outreach_voice_studio_jobs.update_one(scope, {'$set': {'error_code': 'profile_cleanup_needs_review'}})
            return
        profile_scope['revision'] = profile.get('revision')
        if job['operation'] == 'clone':
            await current.outreach_voices.delete_one(profile_scope)
        else:
            change = {'$unset': {'studio_job_id': ''}}
            if job['operation'] == 'delete':
                profile = await current.outreach_voices.find_one(profile_scope)
                from outreach.core.erasure import workspace_is_open
                restored = ('stopped' if not await workspace_is_open(current, job['workspace_id']) else
                    'consent_revoked' if profile and profile.get('status') == 'consent_revoked' else job.get('prior_status', 'active'))
                change.update({'$set': {'status': restored}, '$inc': {'revision': 1}})
            await current.outreach_voices.update_one(profile_scope, change)

    async def cancel(self, workspace: str, job_id: str, actor: str) -> dict:
        async def apply(current):
            await self._access(current, workspace, actor, 'delete')
            job = await current.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))
            if not job or job['status'] not in {'queued', 'preparing'}:
                raise ValueError('Only proven unsubmitted work can be cancelled')
            await self._stop(current, job, 'cancelled')
        await suppression.mutate_suppression(self.db, workspace, apply)
        return await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))

    async def recover(self, workspace: str, job_id: str) -> dict | None:
        async def apply(current):
            job = await current.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))
            if not job:
                return
            if job['status'] in {'received', 'held_received'}:
                # Receipts are retained even when projection authority is gone.
                return
            expired = _utc(job.get('lease_until') or job['authorization_expires_at']) <= now()
            if job['status'] == 'possible' and expired:
                await current.outreach_voice_studio_jobs.update_one({**self.scope(workspace, job_id),
                    'owner': job['owner'], 'status': 'possible'}, {'$set': {'status': 'held_outcome',
                    'error_code': 'provider_outcome_needs_review', 'updated_at': now()}, '$unset': {'input_enc': ''}})
            elif job['status'] in {'queued', 'preparing'} and expired:
                await self._stop(current, job, 'stopped')
        await self._control(workspace, apply)
        job = await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))
        if job and job['status'] == 'received':
            await self._finish(workspace, job_id, job['owner'])
        return job

    async def _hold(self, workspace, job_id, owner):
        async def apply(current):
            await current.outreach_voice_studio_jobs.update_one({**self.scope(workspace, job_id),
                'owner': owner, 'status': 'possible'}, {'$set': {'status': 'held_outcome',
                'error_code': 'provider_outcome_needs_review', 'updated_at': now()}, '$unset': {'input_enc': ''}})
        await self._control(workspace, apply)
        return {'status': 'held_outcome'}

    async def _finish(self, workspace, job_id, owner):
        async def apply(current):
            scope = {**self.scope(workspace, job_id), 'status': 'received', 'owner': owner}
            job = await current.outreach_voice_studio_jobs.find_one(scope)
            if not job:
                return
            try:
                from outreach.core.erasure import workspace_is_open
                if not await workspace_is_open(current, workspace):
                    raise ValueError('Workspace stopped')
                await self._validate(current, job)
            except ValueError:
                await current.outreach_voice_studio_jobs.update_one(scope, {'$set': {'status': 'held_received',
                    'error_code': 'received_result_needs_review'}, '$unset': {'input_enc': '', 'result_enc': ''}})
                return
            ps = {'workspace_id': workspace, 'id': job['voice_id'], 'studio_job_id': job_id}
            if job['operation'] == 'delete':
                await current.outreach_voices.delete_one(ps)
            else:
                change = {'$unset': {'studio_job_id': ''}}
                if job['operation'] == 'clone':
                    change.update({'$set': {'status': 'needs_vendor_verification' if job['receipt'].get('requires_verification') else 'active', 'elevenlabs_voice_id': job['receipt']['voice_id'],
                        'updated_at': now()}, '$inc': {'revision': 1}})
                await current.outreach_voices.update_one(ps, change)
            await current.outreach_voice_studio_jobs.update_one(scope, {'$set': {'status': 'completed',
                'updated_at': now()}, '$unset': {'input_enc': ''}})
        await self._control(workspace, apply)
        return await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))

    async def run(self, workspace: str, job_id: str, *, provider: Callable[[dict], Awaitable[dict]] | None = None) -> dict:
        await self.recover(workspace, job_id)
        owner = uuid.uuid4().hex
        async def claim(current):
            scope = self.scope(workspace, job_id)
            job = await current.outreach_voice_studio_jobs.find_one({**scope, 'status': 'queued'})
            if not job:
                return None
            try:
                await self._validate(current, job)
            except ValueError:
                await self._stop(current, job, 'stopped')
                return None
            await current.outreach_voice_studio_jobs.update_one({**scope, 'status': 'queued'}, {'$set': {
                'status': 'preparing', 'owner': owner, 'lease_until': now() + LEASE,
                'next_recovery_at': now() + LEASE}})
            return await current.outreach_voice_studio_jobs.find_one(scope)
        job = await suppression.mutate_suppression(self.db, workspace, claim)
        if not job:
            return await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id)) or {'status': 'missing'}
        try:
            raw = await open_blob(job['input_enc'], job, 'input') if job.get('input_enc') else None
            credential = await prepare_key(expected_source=job['provider_source_digest'])
            async def begin(current):
                own = await current.outreach_voice_studio_jobs.find_one({**self.scope(workspace, job_id),
                    'owner': owner, 'status': 'preparing', 'lease_until': {'$gt': now()}})
                if not own:
                    raise ValueError('Voice owner changed')
                if not credential.matches():
                    raise ValueError('Voice provider configuration changed')
                deadline = min(await self._validate(current, own), _utc(own['lease_until']))
                day = now().date().isoformat()
                budget = {'_id': canonical_hash([workspace, job['operation'], day]), 'workspace_id': workspace}
                await current.outreach_voice_studio_budgets.update_one(budget, {'$setOnInsert': {
                    'day': day, 'operation': job['operation'], 'calls': 0, 'chars': 0}}, upsert=True)
                reserved = await current.outreach_voice_studio_budgets.update_one({**budget,
                    'calls': {'$lt': LIMITS[job['operation']]}, 'chars': {'$lte': 20000 - job['chars']}},
                    {'$inc': {'calls': 1, 'chars': job['chars']}})
                if reserved.modified_count != 1:
                    raise ValueError('Daily Studio budget exhausted')
                await current.outreach_voice_studio_jobs.update_one({**self.scope(workspace, job_id),
                    'owner': owner, 'status': 'preparing'}, {'$set': {'status': 'possible', 'possible_at': now()}})
                return deadline
            deadline = await suppression.mutate_suppression(self.db, workspace, begin)
        except Exception:
            async def stop(current):
                own = await current.outreach_voice_studio_jobs.find_one({**self.scope(workspace, job_id), 'owner': owner, 'status': 'preparing'})
                if own:
                    await self._stop(current, own, 'stopped')
            await self._control(workspace, stop)
            return await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))
        # Synchronous final configuration/deadline check and bounded adapter entry.
        def allowed():
            try:
                return now() < deadline and configuration() == job['configuration_digest'] and credential.matches()
            except ValueError:
                return False
        try:
            if not allowed():
                # Still held: marker committed, including possible lost commit ack.
                return await self._hold(workspace, job_id, owner)
            if provider is None:
                from outreach.core.voice_studio_provider import studio_call
                provider = studio_call
            async with asyncio.timeout(min(30, max(0, (deadline - now()).total_seconds()))):
                result = await provider({'operation': job['operation'], 'voice_id': job.get('provider_voice_id'),
                    'name': job['name'], 'input': raw, 'credential': credential, 'allowed': allowed})
            receipt = {'received_at': now()}
            result_enc = None
            if job['operation'] == 'clone':
                remote = result.get('voice_id')
                if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', remote) or remote.startswith('voice_mock_'):
                    raise ValueError('Invalid receipt')
                receipt['voice_id'] = remote
                receipt['requires_verification'] = result.get('requires_verification', False) is not False
            elif job['operation'] == 'delete':
                if result.get('deleted') is not True:
                    raise ValueError('Unconfirmed deletion')
                receipt['deleted'] = True
            else:
                validate_audio(result.get('audio'))
                receipt['audio_digest'] = canonical_hash(result['audio'])
                try:
                    result_enc = await seal_blob(result['audio'], job, 'result')
                except Exception:
                    # Preserve known paid response evidence even if content custody
                    # fails. No playback, profile unlock or replacement TTS call.
                    receipt['content_unavailable'] = True
            async def save_receipt(current):
                changes = {'receipt': receipt, 'status': 'held_received' if receipt.get('content_unavailable') else 'received', 'updated_at': now(), 'next_recovery_at': now()}
                if receipt.get('content_unavailable'):
                    changes['error_code'] = 'received_audio_storage_unavailable'
                if result_enc:
                    changes.update({'result_enc': result_enc, 'result_expires_at': now() + timedelta(hours=24)})
                await current.outreach_voice_studio_jobs.update_one({**self.scope(workspace, job_id), 'owner': owner,
                    'status': {'$in': ['possible', 'held_outcome']}}, {'$set': changes, '$unset': {'input_enc': ''}})
            await self._control(workspace, save_receipt)
        except asyncio.CancelledError:
            await self._hold(workspace, job_id, owner)
            raise
        except Exception:
            # A lost receipt acknowledgement can still be repaired without HTTP.
            saved = await self.db.outreach_voice_studio_jobs.find_one(self.scope(workspace, job_id))
            if not saved or saved.get('status') not in {'received', 'held_received'} or saved.get('owner') != owner:
                return await self._hold(workspace, job_id, owner)
        return await self._finish(workspace, job_id, owner)

    async def preview(self, workspace: str, job_id: str, actor: str) -> bytes:
        async def capture(current):
            await self._access(current, workspace, actor, 'preview')
            job = await current.outreach_voice_studio_jobs.find_one({**self.scope(workspace, job_id),
                'status': 'completed', 'operation': 'preview', 'result_expires_at': {'$gt': now()}})
            if not job:
                raise ValueError('Saved preview is unavailable')
            profile = require_profile(await self._authorities(current).outreach_voices.find_one({'workspace_id': workspace, 'id': job['voice_id']}))
            if profile_identity(profile) != job['profile_identity'] or configuration() != job['configuration_digest']:
                raise ValueError('Saved preview context changed')
            return job
        job = await suppression.mutate_suppression(self.db, workspace, capture)
        audio = await open_blob(job['result_enc'], job, 'result')
        validate_audio(audio)
        if canonical_hash(audio) != job['receipt']['audio_digest']:
            raise ValueError('Saved preview receipt changed')
        fresh = await suppression.mutate_suppression(self.db, workspace, capture)
        if any(fresh.get(k) != job.get(k) for k in ('result_enc', 'receipt', 'result_expires_at', 'profile_identity')):
            raise ValueError('Saved preview changed')
        return audio


async def publish_studio_jobs(db: AsyncIOMotorDatabase, publisher: Callable[[str, str], Awaitable[None]], *, limit: int = 50) -> int:
    service = VoiceStudio(db)
    due = await db.outreach_voice_studio_jobs.find({'status': {'$in': ACTIVE},
        'next_recovery_at': {'$lte': now()}}).sort('next_recovery_at', 1).limit(limit).to_list(length=limit)
    for job in due:
        async def reserve(current):
            return await current.outreach_voice_studio_jobs.update_one(service.scope(job['workspace_id'], job['_id']),
                {'$set': {'next_recovery_at': now() + timedelta(minutes=5)}})
        try:
            await service._control(job['workspace_id'], reserve)
            await service.recover(job['workspace_id'], job['_id'])
        except suppression.SuppressionUnavailable:
            continue
    # Clear content only, never remove job identity/evidence/unknown slot.
    expired = await db.outreach_voice_studio_jobs.find({'result_expires_at': {'$lte': now()},
        'result_enc': {'$exists': True}}).limit(limit).to_list(length=limit)
    for job in expired:
        async def scrub(current):
            await current.outreach_voice_studio_jobs.update_one({**service.scope(job['workspace_id'], job['_id']),
                'result_enc': job['result_enc'], 'result_expires_at': job['result_expires_at']}, {'$unset': {'result_enc': ''}})
        await service._control(job['workspace_id'], scrub)
    if not enabled():
        return 0
    jobs = await db.outreach_voice_studio_jobs.find({'status': 'queued', 'next_publish_at': {'$lte': now()}}).sort('next_publish_at', 1).limit(limit).to_list(length=limit)
    count = 0
    for job in jobs:
        async def reserve(current):
            return await current.outreach_voice_studio_jobs.update_one({**service.scope(job['workspace_id'], job['_id']),
                'status': 'queued', 'next_publish_at': {'$lte': now()}}, {'$set': {'next_publish_at': now() + timedelta(seconds=60)}})
        try:
            result = await suppression.mutate_suppression(db, job['workspace_id'], reserve)
            if result.modified_count:
                await publisher(job['_id'], job['workspace_id'])
                count += 1
        except Exception:
            logger.warning("Studio publication deferred; durable job retained")
            continue
    return count
