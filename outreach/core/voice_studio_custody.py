"""Bounded authenticated Studio content; key work stays outside transactions."""
import logging
logger = logging.getLogger(__name__)
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from outreach.core.authorization import canonical_hash
from outreach.core import session_custody
from outreach.core.credential_custody import CustodyUnavailable
from utils.encryption import encrypt, decrypt_strict

MAX_BLOB = 2000000


def scope(job: dict, kind: str) -> dict:
    if kind not in {'input', 'result'} or any(not isinstance(job.get(key), str) or not job[key] for key in ('workspace_id', '_id', 'payload_digest')):
        raise CustodyUnavailable('Voice Studio scope is unavailable')
    return {"workspace": job['workspace_id'], "job": job['_id'], "binding": job['payload_digest'], "kind": kind}


async def seal_blob(value: bytes, job: dict, kind: str) -> str:
    if not isinstance(value, bytes) or not 0 < len(value) <= MAX_BLOB:
        raise CustodyUnavailable('Voice Studio content is outside its bounds')
    binding = scope(job, kind)
    if session_custody.custody_mode() == 'legacy_fernet':
        return encrypt(json.dumps({'scope': binding, 'value': base64.b64encode(value).decode()}, separators=(',', ':')))
    key = os.urandom(32)
    context = session_custody.context(job['workspace_id'], 'voice-studio-' + kind, job['_id'], 'voice_studio_key')
    wrapped = await session_custody.configured_custody().seal(base64.b64encode(key).decode(), context)
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, value, canonical_hash(binding).encode())
    return 'vs1:' + json.dumps({'key': wrapped, 'nonce': base64.b64encode(nonce).decode(),
        'body': base64.b64encode(encrypted).decode()}, separators=(',', ':'))


async def open_blob(value: str, job: dict, kind: str) -> bytes:
    try:
        if not isinstance(value, str) or not 0 < len(value) <= 4000000:
            raise ValueError('Content bounds')
        binding = scope(job, kind)
        if session_custody.custody_mode() == 'legacy_fernet':
            if value.startswith('vs1:'): raise ValueError('No downgrade')
            data = json.loads(decrypt_strict(value))
            if data.get('scope') != binding: raise ValueError('Content scope')
            result = base64.b64decode(data['value'], validate=True)
        else:
            if not value.startswith('vs1:'): raise ValueError('Scoped content required')
            data = json.loads(value[4:])
            context = session_custody.context(job['workspace_id'], 'voice-studio-' + kind, job['_id'], 'voice_studio_key')
            key = base64.b64decode(await session_custody.configured_custody().open(data['key'], context), validate=True)
            result = AESGCM(key).decrypt(base64.b64decode(data['nonce'], validate=True),
                base64.b64decode(data['body'], validate=True), canonical_hash(binding).encode())
        if not 0 < len(result) <= MAX_BLOB: raise ValueError('Content bounds')
        return result
    except Exception:
        raise CustodyUnavailable('Voice Studio content is unavailable') from None
