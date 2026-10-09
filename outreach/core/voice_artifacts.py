"""Encrypted prepared recordings only; loading can never synthesize audio."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from typing import TYPE_CHECKING
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.paid_access import _utc
from outreach.core.voice_artifact_custody import (
    MAX_AUDIO_BYTES, PreparedArtifact, PreparedClip, open_audio, seal_audio, validate_record,
)
from outreach.core.voice_policy import validate_audio
if TYPE_CHECKING:
    from outreach.core.suppression import SuppressionDatabase
    from outreach.core.dispatch_authority import AuthorityDatabase


class VoiceArtifacts:
    def __init__(self, db: AsyncIOMotorDatabase | SuppressionDatabase | AuthorityDatabase) -> None:
        self.db = db

    def _outside_transaction(self) -> None:
        from outreach.core.suppression import SuppressionDatabase
        from outreach.core.dispatch_authority import AuthorityDatabase
        if session_custody.custody_mode() == 'kms_v1' and isinstance(self.db, (SuppressionDatabase, AuthorityDatabase)):
            raise CustodyUnavailable('Voice key access requires an independent preparation step')

    async def prepare(self, binding: dict, audio: bytes, *, generation_id: str | None = None,
                      now: datetime | None = None) -> PreparedArtifact:
        """Seal outside Mongo; final installation uses the captured owner transaction."""
        self._outside_transaction()
        metadata = validate_audio(audio)
        now = _utc(now or datetime.now(timezone.utc))
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        doc = {'_id': canonical_hash(binding), 'workspace_id': binding['workspace_id'], 'status': 'prepared',
               'audio_digest': hashlib.sha256(audio).hexdigest(), 'byte_count': len(audio), **metadata,
               'binding_digest': canonical_hash(binding), 'generation_id': generation_id or str(uuid.uuid4()),
               'expires_at': now + timedelta(days=1), 'prepared_at': now}
        return await seal_audio(audio, doc)

    async def install(self, prepared: PreparedArtifact, *, now: datetime | None = None) -> dict:
        """Database only. Caller must fence job/authority before installing."""
        if not isinstance(prepared, PreparedArtifact) or not prepared.matches(now=now):
            raise CustodyUnavailable('Prepared voice clip changed before installation')
        doc = deepcopy(prepared.document)
        scope = {'_id': doc['_id'], 'workspace_id': doc['workspace_id']}
        await self.db.outreach_voice_artifacts.replace_one(scope, doc, upsert=True)
        if not prepared.matches(now=now):
            # An authority callback rolls this write back. Direct callers must
            # also run in a stopped, owned scope; they grant no execution permit.
            raise CustodyUnavailable('Prepared voice clip changed during installation')
        return doc

    async def store(self, binding: dict, audio: bytes, *, generation_id: str | None = None,
                    now: datetime | None = None) -> dict:
        """Compatibility helper for independent callers; scoped transactions use install."""
        prepared = await self.prepare(binding, audio, generation_id=generation_id, now=now)
        return await self.install(prepared, now=now)

    async def metadata(self, workspace_id: str, artifact_id: str, *, now: datetime | None = None) -> dict:
        doc = await self.db.outreach_voice_artifacts.find_one(
            {'_id': artifact_id, 'workspace_id': workspace_id, 'status': 'prepared'})
        validate_record(doc, workspace_id, artifact_id, now=now)
        return doc

    async def prepare_load(self, workspace_id: str, artifact_id: str, *, now: datetime | None = None) -> PreparedClip:
        self._outside_transaction()
        doc = await self.metadata(workspace_id, artifact_id, now=now)
        clip = await open_audio(deepcopy(doc), now=now)
        # Key work yields: never return audio from a replaced, expired or erased row.
        current = await self.db.outreach_voice_artifacts.find_one(
            {'_id': artifact_id, 'workspace_id': workspace_id, 'status': 'prepared'})
        if not clip.matches(current, now=now):
            raise CustodyUnavailable('Prepared voice clip changed during opening')
        return clip

    async def load(self, workspace_id: str, artifact_id: str, *, now: datetime | None = None) -> bytes:
        return (await self.prepare_load(workspace_id, artifact_id, now=now)).audio
