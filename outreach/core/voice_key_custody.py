"""ElevenLabs application-key custody; metadata inspection never decrypts.

Source identity is conservative: an encrypted-envelope change needs explicit
profile review. Neither key possession nor an operator label proves vendor account
identity. Plaintext material exists only in one worker operation, outside Mongo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import os

from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CredentialContext, CustodyUnavailable, PREFIX
from outreach.core.oauth_app_custody import KMS_SETTINGS

MAX_KEY_BYTES = 1024


def _policy() -> tuple[str, ...]:
    return (session_custody.custody_mode(), os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip(),
            *(os.getenv(name, '').strip() for name in KMS_SETTINGS))


def key_context(generation: str) -> CredentialContext:
    return session_custody.context('outreach-voice-provider', 'elevenlabs', generation, 'voice_provider_key')


def _validate_key(value: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value.encode()) <= MAX_KEY_BYTES
            or value.lower() in {'mock', 'test'} or value.startswith(PREFIX)
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)):
        raise CustodyUnavailable('Voice provider key is unavailable')


@dataclass(frozen=True)
class KeyConfiguration:
    storage: str = field(repr=False)
    generation: str
    policy: tuple[str, ...]

    @property
    def source(self) -> str:
        # Preserve deployed legacy fingerprints and content/dedup identities.
        return (canonical_hash(['elevenlabs', self.storage]) if self.policy[0] == 'legacy_fernet'
                else canonical_hash(['elevenlabs-scoped-v1', self.storage, self.generation, self.policy[1]]))

    @property
    def digest(self) -> str:
        return canonical_hash([self.storage, self.generation, self.policy])


def capture_configuration() -> KeyConfiguration:
    policy = _policy()
    legacy = os.getenv('ELEVENLABS_API_KEY', '').strip()
    envelope = os.getenv('OUTREACH_ELEVENLABS_API_KEY_ENC', '').strip()
    generation = os.getenv('OUTREACH_ELEVENLABS_KEY_GENERATION', '').strip()
    if policy[0] == 'kms_v1':
        if (legacy.lower() not in {'', 'mock', 'test'} or not envelope.startswith(PREFIX)
                or len(envelope.encode()) > 60000):
            raise CustodyUnavailable('Scoped voice provider key storage is required')
        key_context(generation)
        return KeyConfiguration(envelope, generation, policy)
    if envelope or generation:
        raise CustodyUnavailable('Scoped voice provider keys cannot use legacy custody')
    _validate_key(legacy)
    return KeyConfiguration(legacy, '', policy)


def source_digest() -> str:
    return capture_configuration().source


def configuration_digest() -> str:
    return capture_configuration().digest


@dataclass(frozen=True)
class PreparedKey:
    value: str = field(repr=False)
    config: KeyConfiguration = field(repr=False)
    value_digest: str = field(repr=False)

    def matches(self) -> bool:
        try:
            _validate_key(self.value)
            return (hmac.compare_digest(canonical_hash(self.value), self.value_digest)
                    and hmac.compare_digest(self.config.digest, configuration_digest()))
        except (ValueError, TypeError, AttributeError):
            return False


async def prepare_key(*, expected_digest: str | None = None, expected_source: str | None = None) -> PreparedKey:
    """Open before physical authorization and recheck exact source after awaits."""
    config = capture_configuration()
    if ((expected_digest is not None and expected_digest != config.digest)
            or (expected_source is not None and expected_source != config.source)):
        raise CustodyUnavailable('Voice provider configuration changed')
    value = (await session_custody.configured_custody().open(config.storage, key_context(config.generation))
             if config.policy[0] == 'kms_v1' else config.storage)
    result = PreparedKey(value, config, canonical_hash(value))
    if not result.matches():
        raise CustodyUnavailable('Voice provider changed during key opening')
    return result


async def seal_key(value: str, generation: str) -> str:
    """Private offline preparation; does not install configuration or grant work."""
    _validate_key(value)
    policy = _policy()
    if policy[0] != 'kms_v1':
        raise CustodyUnavailable('Scoped custody is required to seal a voice provider key')
    envelope = await session_custody.configured_custody().seal(value, key_context(generation))
    if _policy() != policy:
        raise CustodyUnavailable('Voice provider custody changed during sealing')
    return envelope
