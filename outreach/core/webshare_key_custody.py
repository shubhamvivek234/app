"""Application-scoped Webshare keys; metadata capture never opens a key.

Prepared material belongs to one bounded inventory operation. Key possession
does not prove ownership of a provider account, proxy or subscription.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from dataclasses import dataclass, field
import hmac
import os

from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CredentialContext, CustodyUnavailable, PREFIX
from outreach.core.oauth_app_custody import KMS_SETTINGS

MAX_KEY_BYTES = 1024


def _policy() -> tuple[str, ...]:
    return (
        session_custody.custody_mode(),
        os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip(),
        *(os.getenv(name, '').strip() for name in KMS_SETTINGS),
        os.getenv('OUTREACH_PROXY_PROVIDER', 'webshare').strip().lower(),
    )


def key_context(generation: str) -> CredentialContext:
    return session_custody.context(
        'outreach-proxy-provider', 'webshare', generation, 'proxy_provider_key',
    )


def _validate_key(value: str) -> None:
    if (
        not isinstance(value, str) or not 1 <= len(value.encode()) <= MAX_KEY_BYTES
        or value.lower() in {'mock', 'test'} or value.startswith(PREFIX)
        or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
    ):
        raise CustodyUnavailable('Webshare provider key is unavailable')


@dataclass(frozen=True)
class KeyConfiguration:
    storage: str = field(repr=False)
    generation: str
    policy: tuple[str, ...]
    override: str | None = field(default=None, repr=False)

    @property
    def digest(self) -> str:
        return canonical_hash([self.storage, self.generation, self.policy, self.override is not None])


def capture_configuration(override: str | None = None) -> KeyConfiguration:
    policy = _policy()
    if policy[-1] != 'webshare':
        raise CustodyUnavailable('Webshare provider configuration changed')
    legacy = os.getenv('WEBSHARE_API_KEY', 'mock').strip()
    envelope = os.getenv('OUTREACH_WEBSHARE_API_KEY_ENC', '').strip()
    generation = os.getenv('OUTREACH_WEBSHARE_KEY_GENERATION', '').strip()
    if policy[0] == 'kms_v1':
        if (
            override is not None or legacy.lower() not in {'', 'mock', 'test'}
            or not envelope.startswith(PREFIX) or len(envelope.encode()) > 60000
        ):
            raise CustodyUnavailable('Scoped Webshare provider key storage is required')
        key_context(generation)
        return KeyConfiguration(envelope, generation, policy)
    if envelope or generation:
        raise CustodyUnavailable('Scoped Webshare keys cannot use legacy custody')
    value = legacy if override is None else override
    _validate_key(value)
    return KeyConfiguration(value, '', policy, override)


def configuration_digest(override: str | None = None) -> str:
    return capture_configuration(override).digest


def configuration_state(override: str | None = None) -> str:
    """Storage/configuration metadata only; never a vendor or KMS health proof."""
    try:
        if (
            session_custody.custody_mode() == 'legacy_fernet'
            and os.getenv('OUTREACH_PROXY_PROVIDER', 'webshare').strip().lower() == 'webshare'
            and not os.getenv('OUTREACH_WEBSHARE_API_KEY_ENC', '').strip()
            and not os.getenv('OUTREACH_WEBSHARE_KEY_GENERATION', '').strip()
            and (os.getenv('WEBSHARE_API_KEY', 'mock') if override is None else override).strip().lower()
            in {'', 'mock', 'test'}
        ):
            return 'mock'
        capture_configuration(override)
        return 'live'
    except (ValueError, TypeError, AttributeError):
        return 'unavailable'


@dataclass(frozen=True)
class PreparedKey:
    value: str = field(repr=False)
    config: KeyConfiguration = field(repr=False)
    value_digest: str = field(repr=False)

    def matches(self) -> bool:
        try:
            _validate_key(self.value)
            return (
                hmac.compare_digest(canonical_hash(self.value), self.value_digest)
                and hmac.compare_digest(self.config.digest, configuration_digest(self.config.override))
            )
        except (ValueError, TypeError, AttributeError):
            return False


async def prepare_key(*, expected_digest: str | None = None, override: str | None = None) -> PreparedKey:
    """Open outside Mongo, then recheck complete captured configuration."""
    config = capture_configuration(override)
    if expected_digest is not None and expected_digest != config.digest:
        raise CustodyUnavailable('Webshare provider configuration changed')
    value = (
        await session_custody.configured_custody().open(config.storage, key_context(config.generation))
        if config.policy[0] == 'kms_v1' else config.storage
    )
    key = PreparedKey(value, config, canonical_hash(value))
    if not key.matches():
        raise CustodyUnavailable('Webshare provider changed during key opening')
    return key


async def seal_key(value: str, generation: str) -> str:
    """Private offline preparation; installs no configuration or permission."""
    _validate_key(value)
    policy = _policy()
    if policy[0] != 'kms_v1':
        raise CustodyUnavailable('Scoped custody is required to seal a Webshare key')
    envelope = await session_custody.configured_custody().seal(value, key_context(generation))
    if _policy() != policy:
        raise CustodyUnavailable('Webshare custody changed during sealing')
    return envelope
