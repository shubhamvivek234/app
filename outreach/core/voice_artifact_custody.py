"""Bounded campaign WAV custody; crypto precedes database-only authority work."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CredentialContext, CustodyUnavailable, _bytes, _pairs, canonical
from outreach.core.oauth_app_custody import KMS_SETTINGS
from outreach.core.paid_access import _utc
from outreach.core.voice_policy import MAX_PCM_BYTES, validate_audio
from utils.encryption import decrypt_strict, encrypt

PREFIX = 'va1:'
MAX_AUDIO_BYTES = MAX_PCM_BYTES + 44
MAX_ENVELOPE_CHARS = 2700000
MAX_LEGACY_ENVELOPE_CHARS = 3500000
LIFETIME = timedelta(days=1)
FIELDS = ('_id', 'workspace_id', 'binding_digest', 'generation_id', 'audio_digest',
          'byte_count', 'media_type', 'duration_ms', 'sample_rate', 'prepared_at', 'expires_at')


def policy() -> tuple[str, ...]:
    """Capture configured custody authority without AWS access."""
    return (session_custody.custody_mode(), os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip(),
            *(os.getenv(name, '').strip() for name in KMS_SETTINGS))


def policy_digest() -> str:
    return canonical_hash(policy())


def _identity(doc: dict) -> dict:
    value = {name: doc[name] for name in FIELDS}
    for name in ('prepared_at', 'expires_at'):
        instant = _utc(value[name])
        if not instant:
            raise ValueError('Recording time is unavailable')
        value[name] = instant.isoformat(timespec='milliseconds')
    return value


def record_digest(doc: dict) -> str:
    return canonical_hash({**_identity(doc), 'status': doc['status'], 'audio_enc': doc['audio_enc']})


def _validate_record(doc: dict, workspace: str, artifact_id: str, *, mode: str, now: datetime | None = None) -> None:
    """Metadata/format check only; it does not prove ciphertext can be opened."""
    try:
        now = _utc(now or datetime.now(timezone.utc))
        if (not isinstance(doc, dict) or doc.get('workspace_id') != workspace or doc.get('_id') != artifact_id
                or doc.get('status') != 'prepared' or not isinstance(artifact_id, str)
                or not re.fullmatch(r'[a-f0-9]{64}', artifact_id) or doc.get('binding_digest') != artifact_id):
            raise ValueError('Recording identity')
        for name in ('workspace_id', 'generation_id'):
            value = doc.get(name)
            if (not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip()
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError('Recording scope')
        if not isinstance(doc.get('audio_digest'), str) or not re.fullmatch(r'[a-f0-9]{64}', doc['audio_digest']):
            raise ValueError('Recording digest')
        if (type(doc.get('byte_count')) is not int or not 44 < doc['byte_count'] <= MAX_AUDIO_BYTES
                or type(doc.get('duration_ms')) is not int or not 0 < doc['duration_ms'] <= 60000
                or type(doc.get('sample_rate')) is not int or doc['sample_rate'] != 16000
                or doc.get('media_type') != 'audio/wav'):
            raise ValueError('Recording bounds')
        prepared, expiry = _utc(doc.get('prepared_at')), _utc(doc.get('expires_at'))
        if not prepared or not expiry or not prepared <= now < expiry or expiry - prepared > LIFETIME:
            raise ValueError('Recording expired')
        value = doc.get('audio_enc')
        if mode == 'kms_v1' and (prepared.microsecond % 1000 or expiry.microsecond % 1000):
            raise ValueError('Recording time precision')
        maximum = MAX_ENVELOPE_CHARS if mode == 'kms_v1' else MAX_LEGACY_ENVELOPE_CHARS
        if not isinstance(value, str) or not 0 < len(value) <= maximum:
            raise ValueError('Recording storage')
        if (mode == 'kms_v1') != value.startswith(PREFIX):
            raise ValueError('Recording custody mode')
        _identity(doc)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CustodyUnavailable('Prepared voice clip is unavailable; prepare and review it again') from None


def validate_record(doc: dict, workspace: str, artifact_id: str, *, now: datetime | None = None) -> None:
    """Normal consumers always require the configured custody format."""
    _validate_record(doc, workspace, artifact_id, mode=session_custody.custody_mode(), now=now)


def _context(doc: dict) -> CredentialContext:
    return session_custody.context(doc['workspace_id'], doc['_id'], doc['generation_id'], 'voice_artifact_key')


def _audio_matches(audio: bytes, doc: dict) -> bool:
    try:
        return (hashlib.sha256(audio).hexdigest() == doc['audio_digest'] and len(audio) == doc['byte_count']
                and all(doc.get(name) == value for name, value in validate_audio(audio).items()))
    except (ValueError, KeyError, TypeError):
        return False


@dataclass(frozen=True)
class PreparedArtifact:
    """Ciphertext prepared once outside a transaction; mutable data is hash-fenced."""
    document: dict = field(repr=False)
    captured_policy: tuple[str, ...] = field(repr=False)
    digest: str = field(repr=False)

    def matches(self, *, now: datetime | None = None) -> bool:
        try:
            validate_record(self.document, self.document['workspace_id'], self.document['_id'], now=now)
            return (self.captured_policy == policy()
                    and hmac.compare_digest(self.digest, record_digest(self.document)))
        except (ValueError, KeyError, TypeError):
            return False


@dataclass(frozen=True)
class PreparedClip:
    """Operation-local proof. Never put it in jobs, broker payloads or logs."""
    document: dict = field(repr=False)
    audio: bytes = field(repr=False)
    captured_policy: tuple[str, ...] = field(repr=False)
    digest: str = field(repr=False)

    def matches(self, current: dict, *, now: datetime | None = None) -> bool:
        try:
            validate_record(current, self.document['workspace_id'], self.document['_id'], now=now)
            return (self.captured_policy == policy() and _audio_matches(self.audio, self.document)
                    and hmac.compare_digest(self.digest, record_digest(self.document))
                    and hmac.compare_digest(self.digest, record_digest(current)))
        except (ValueError, KeyError, TypeError):
            return False


async def seal_audio(audio: bytes, document: dict) -> PreparedArtifact:
    """Wrap a fresh recording key; authenticate scope, generation, metadata and time."""
    key = bytearray()
    try:
        captured = policy()
        if not _audio_matches(audio, document):
            raise ValueError('Recording data')
        if captured[0] == 'legacy_fernet':
            value = encrypt(base64.b64encode(audio).decode())
        else:
            context = _context(document)
            key.extend(os.urandom(32))
            wrapped = await session_custody.configured_custody().seal(base64.b64encode(key).decode(), context)
            if captured != policy():
                raise ValueError('Recording policy changed')
            nonce = os.urandom(12)
            encrypted = AESGCM(bytes(key)).encrypt(nonce, audio, canonical(_identity(document)))
            value = PREFIX + canonical({'key': wrapped, 'nonce': base64.b64encode(nonce).decode(),
                                        'body': base64.b64encode(encrypted).decode()}).decode()
        document = {**document, 'audio_enc': value}
        result = PreparedArtifact(document, captured, record_digest(document))
        if not result.matches(now=document['prepared_at']):
            raise ValueError('Recording policy changed')
        return result
    except Exception:
        raise CustodyUnavailable('Prepared voice clip sealing is unavailable') from None
    finally:
        key[:] = bytes(len(key))


async def open_audio(document: dict, *, now: datetime | None = None) -> PreparedClip:
    """One strict bounded open; recheck mode/config after key access."""
    key = bytearray()
    try:
        captured = policy()
        validate_record(document, document['workspace_id'], document['_id'], now=now)
        value = document['audio_enc']
        if captured[0] == 'legacy_fernet':
            audio = _bytes(decrypt_strict(value), MAX_AUDIO_BYTES)
        else:
            data = json.loads(value[len(PREFIX):], object_pairs_hook=_pairs)
            if not isinstance(data, dict) or set(data) != {'key', 'nonce', 'body'}:
                raise ValueError('Recording envelope')
            nonce = _bytes(data['nonce'], 12, exact=12)
            encrypted = _bytes(data['body'], MAX_AUDIO_BYTES + 16)
            if not isinstance(data['key'], str) or not data['key'].startswith('uc1:') or len(data['key']) > 60000:
                raise ValueError('Recording key envelope')
            context = _context(document)
            key.extend(_bytes(await session_custody.configured_custody().open(data['key'], context), 32, exact=32))
            if captured != policy():
                raise ValueError('Recording policy changed')
            audio = AESGCM(bytes(key)).decrypt(nonce, encrypted, canonical(_identity(document)))
        result = PreparedClip(document, audio, captured, record_digest(document))
        if not result.matches(document, now=now):
            raise ValueError('Recording data changed')
        return result
    except Exception:
        raise CustodyUnavailable('Prepared voice clip opening is unavailable') from None
    finally:
        key[:] = bytes(len(key))
