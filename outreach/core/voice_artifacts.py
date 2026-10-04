"""Encrypted prepared recordings only; loading can never synthesize audio."""
from __future__ import annotations
import base64
import hashlib
import uuid
from typing import TYPE_CHECKING
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta, timezone

from outreach.core.authorization import canonical_hash
from outreach.core.crypto import encrypt_secret
from utils.encryption import decrypt_strict
from outreach.core.paid_access import _utc
from outreach.core.voice_policy import validate_audio
if TYPE_CHECKING:
    from outreach.core.suppression import SuppressionDatabase
    from outreach.core.dispatch_authority import AuthorityDatabase

MAX_AUDIO_BYTES = 4 * 1024 * 1024


class VoiceArtifacts:
    def __init__(self, db: AsyncIOMotorDatabase | SuppressionDatabase | AuthorityDatabase) -> None:
        self.db = db

    async def store(self, binding: dict, audio: bytes, *, generation_id: str | None = None, now: datetime | None = None) -> dict:
        """Called in the preparation owner's final transaction, never with a factory."""
        metadata = validate_audio(audio)
        now = now or datetime.now(timezone.utc)
        scope = {"_id": canonical_hash(binding), "workspace_id": binding["workspace_id"]}
        doc = {**scope, "status": "prepared", "audio_enc": encrypt_secret(base64.b64encode(audio).decode()),
            "audio_digest": hashlib.sha256(audio).hexdigest(), "byte_count": len(audio), **metadata,
            "binding_digest": canonical_hash(binding), "generation_id": generation_id or str(uuid.uuid4()),
            "expires_at": now + timedelta(days=1), "prepared_at": now}
        await self.db.outreach_voice_artifacts.replace_one(scope, doc, upsert=True)
        return doc

    async def load(self, workspace_id: str, artifact_id: str, *, now: datetime | None = None) -> bytes:
        now = now or datetime.now(timezone.utc)
        doc = await self.db.outreach_voice_artifacts.find_one({"_id": artifact_id, "workspace_id": workspace_id, "status": "prepared"})
        if not doc or not _utc(doc.get("expires_at")) or _utc(doc["expires_at"]) <= now:
            raise ValueError("Voice preview expired; prepare and review it again")
        try:
            audio = base64.b64decode(decrypt_strict(doc["audio_enc"]), validate=True)
            if not 0 < len(audio) <= MAX_AUDIO_BYTES or hashlib.sha256(audio).hexdigest() != doc["audio_digest"]:
                raise ValueError("Prepared voice clip changed")
            validate_audio(audio)
        except (KeyError, ValueError) as exc:
            raise ValueError("Prepared voice clip is unavailable; prepare and review it again") from exc
        return audio
