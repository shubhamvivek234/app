"""Versioned AES-GCM custody; independent caller context is required to open."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "uc1:"
MAX_SECRET_BYTES = 32768
KEY_ARN = re.compile(r"arn:aws:kms:([a-z0-9-]+):([0-9]{12}):key/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\Z")
PURPOSES = frozenset({"voice_provider_key", "voice_studio_key", "oauth_app_secret", "mailbox_sync_key", "mailbox_access_token", "mailbox_refresh_token", "oauth_code", "oauth_pkce", "finder_key", "proxy_password", "session_li_at", "session_jsession", "session_li_a",
    "pending_li_at", "pending_jsession", "pending_li_a"})


class CustodyUnavailable(ValueError):
    """Sanitized fail-closed custody error, without secret/provider details."""


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


@dataclass(frozen=True)
class CredentialContext:
    workspace_id: str
    sender_id: str
    generation: str
    purpose: str
    environment_id: str

    def kms_context(self) -> dict[str, str]:
        values = [self.workspace_id, self.sender_id, self.generation, self.environment_id]
        if (any(not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in value) for value in values)
                or not isinstance(self.purpose, str) or self.purpose not in PURPOSES):
            raise CustodyUnavailable("Credential context is unavailable")
        # CloudTrail encryption context is not secret. Persist opaque hashes,
        # not tenant/user IDs, cookie values or raw ambiguous concatenations.
        return {"app": "unravler-outreach", "format": "uc1", "purpose": self.purpose,
            "environment": hashlib.sha256(self.environment_id.encode()).hexdigest(),
            "scope": hashlib.sha256(canonical({"workspace": self.workspace_id,
                "sender": self.sender_id, "generation": self.generation})).hexdigest()}


class KeyProvider(Protocol):
    async def generate(self, context: dict[str, str]) -> tuple[bytes, bytes]: ...
    async def unwrap(self, wrapped: bytes, context: dict[str, str]) -> bytes: ...


def _bytes(encoded: str, maximum: int, *, exact: int | None = None) -> bytes:
    if not isinstance(encoded, str) or len(encoded) > 4 * ((maximum + 2) // 3):
        raise ValueError("Invalid encoding")
    value = base64.b64decode(encoded, validate=True)
    if not 0 < len(value) <= maximum or exact is not None and len(value) != exact:
        raise ValueError("Invalid length")
    return value


def _pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate envelope field")
        result[key] = value
    return result


class CredentialCustody:
    """No DEK cache; each operation holds key material only in its own scope.

    Python/SDK/crypto copies cannot be guaranteed zeroized. Mutable local key
    copies are scrubbed on exit; caller session strings still need process drain.
    """
    def __init__(self, key_arn: str, provider: KeyProvider) -> None:
        if not isinstance(key_arn, str) or not KEY_ARN.fullmatch(key_arn):
            raise CustodyUnavailable("A pinned KMS key ARN is required")
        self.key_arn = key_arn
        self.provider = provider

    def _header(self, context: CredentialContext) -> dict:
        return {"version": 1, "algorithm": "AES-256-GCM", "key_arn": self.key_arn,
            "context": context.kms_context()}

    async def seal(self, secret: str, context: CredentialContext) -> str:
        key = bytearray()
        try:
            if not isinstance(secret, str) or not 0 < len(secret.encode()) <= MAX_SECRET_BYTES:
                raise ValueError("Secret size")
            header = self._header(context)
            plain, wrapped = await self.provider.generate(header["context"])
            if not isinstance(plain, bytes) or len(plain) != 32 or not isinstance(wrapped, bytes) or not 0 < len(wrapped) <= 6144:
                raise ValueError("Key response")
            key.extend(plain)
            del plain
            nonce = os.urandom(12)
            ciphertext = AESGCM(bytes(key)).encrypt(nonce, secret.encode(), canonical(header))
            doc = {**header, "wrapped_key": base64.b64encode(wrapped).decode(),
                "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode()}
            return PREFIX + canonical(doc).decode()
        except Exception:
            raise CustodyUnavailable("Credential sealing is unavailable") from None
        finally:
            key[:] = bytes(len(key))

    async def open(self, envelope: str, context: CredentialContext) -> str:
        key = bytearray()
        try:
            if not isinstance(envelope, str) or not envelope.startswith(PREFIX) or len(envelope) > 60000:
                raise ValueError("Envelope format")
            doc = json.loads(envelope[len(PREFIX):], object_pairs_hook=_pairs)
            header = self._header(context)
            if (not isinstance(doc, dict) or set(doc) != set(header) | {"wrapped_key", "nonce", "ciphertext"}
                    or type(doc["version"]) is not int or any(doc.get(field) != value for field, value in header.items())):
                raise ValueError("Envelope binding")
            nonce = _bytes(doc["nonce"], 12, exact=12)
            ciphertext = _bytes(doc["ciphertext"], MAX_SECRET_BYTES + 16)
            wrapped = _bytes(doc["wrapped_key"], 6144)
            plain = await self.provider.unwrap(wrapped, header["context"])
            if not isinstance(plain, bytes) or len(plain) != 32:
                raise ValueError("Key response")
            key.extend(plain)
            del plain
            secret = AESGCM(bytes(key)).decrypt(nonce, ciphertext, canonical(header)).decode()
            if not secret:
                raise ValueError("Empty secret")
            return secret
        except Exception:
            raise CustodyUnavailable("Credential opening is unavailable") from None
        finally:
            key[:] = bytes(len(key))
