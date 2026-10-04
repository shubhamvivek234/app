"""Application OAuth custody with exact per-operation configuration capture.

The application is a separate scope from a customer's mailbox. Configuration
inspection is synchronous; only workers or the private sealer open key custody.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import os
from typing import TYPE_CHECKING

from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CredentialContext, CustodyUnavailable, PREFIX

if TYPE_CHECKING:
    from outreach.core.mailbox_connection import ProviderConfig

KMS_SETTINGS = ("OUTREACH_KMS_KEY_ARN", "OUTREACH_KMS_ROLE_ARN", "OUTREACH_KMS_ROLE_ID",
                "OUTREACH_KMS_REGION", "OUTREACH_KMS_CREDENTIAL_PROVIDER")


def _policy() -> tuple[str, ...]:
    mode = session_custody.custody_mode()
    return (mode, os.getenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", "").strip(),
            *(os.getenv(name, "").strip() for name in KMS_SETTINGS))


def app_context(provider: str, client_id: str, generation: str) -> CredentialContext:
    """Use a reserved app scope, independent of tenant/sender token custody."""
    if (provider not in {"gmail", "microsoft"} or not isinstance(client_id, str)
            or not 1 <= len(client_id) <= 1024 or client_id != client_id.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in client_id)):
        raise CustodyUnavailable("OAuth application context is unavailable")
    return session_custody.context("outreach-oauth-application", canonical_hash([provider, client_id]),
                                   generation, "oauth_app_secret")


def validate_app_storage(config: ProviderConfig) -> None:
    """Inspect format without opening a secret or contacting the key service."""
    secret = getattr(config, "client_secret", None)
    if not isinstance(secret, str) or not secret or len(secret.encode()) > 60000:
        raise CustodyUnavailable("OAuth application secret storage is unavailable")
    if session_custody.custody_mode() == "kms_v1":
        if not secret.startswith(PREFIX):
            raise CustodyUnavailable("Scoped OAuth application secret is required")
        app_context(config.provider, config.client_id, getattr(config, "app_generation", ""))
    elif secret.startswith(PREFIX):
        raise CustodyUnavailable("Scoped OAuth application secrets cannot use legacy custody")


def app_identity_digest(config: ProviderConfig) -> str:
    """Secret rotation preserves identity; app or tenant replacement does not."""
    return canonical_hash([config.provider, getattr(config, "client_id", ""), getattr(config, "token_url", "")])


def app_configuration_digest(config: ProviderConfig) -> str:
    """Private proof of exact source/configuration and deployment policy."""
    return canonical_hash({"fields": {name: getattr(config, name, "") for name in (
        "provider", "client_id", "client_secret", "app_generation", "redirect_uri",
        "authorization_url", "token_url", "scopes")}, "policy": _policy()})


def app_configuration_matches(config: ProviderConfig, digest: str) -> bool:
    from outreach.core.mailbox_connection import _provider_config
    try:
        return (hmac.compare_digest(app_configuration_digest(config), digest)
                and hmac.compare_digest(app_configuration_digest(_provider_config(config.provider)), digest))
    except (ValueError, TypeError, AttributeError):
        return False
    except Exception:
        # Invalid replacement configuration is also a denial. Never expose its
        # details through physical-call errors or fall back to captured material.
        return False


@dataclass(frozen=True)
class PreparedAppSecret:
    value: str = field(repr=False)
    config: ProviderConfig = field(repr=False)
    digest: str
    _value_digest: str = field(repr=False)

    def matches(self) -> bool:
        return (isinstance(self.value, str) and canonical_hash(self.value) == self._value_digest
                and app_configuration_matches(self.config, self.digest))


async def seal_app_secret(secret: str, provider: str, client_id: str, generation: str) -> str:
    """Private local preparation; no provider mutation or execution grant."""
    if session_custody.custody_mode() != "kms_v1":
        raise CustodyUnavailable("Scoped custody is required to seal an OAuth app secret")
    policy = _policy()
    envelope = await session_custody.configured_custody().seal(secret, app_context(provider, client_id, generation))
    if _policy() != policy:
        raise CustodyUnavailable("OAuth application custody changed during sealing")
    return envelope


async def prepare_app_secret(config: ProviderConfig, *, job: dict | None = None, mailbox: dict | None = None) -> PreparedAppSecret:
    """Open outside transactions, then revalidate the captured app/configuration."""
    validate_app_storage(config)
    digest = app_configuration_digest(config)
    if job is not None:
        proof = job.get("app_config_digest")
        if ((proof and proof != digest) or job.get("provider") != config.provider
                or session_custody.custody_mode() == "kms_v1" and not proof):
            raise CustodyUnavailable("Mailbox authorization application changed or is unproven")
    if mailbox is not None:
        proof = mailbox.get("oauth_app_identity_digest")
        if ((proof and proof != app_identity_digest(config)) or mailbox.get("provider") != config.provider
                or session_custody.custody_mode() == "kms_v1" and not proof):
            raise CustodyUnavailable("Mailbox refresh application changed or is unproven")
    value = (await session_custody.configured_custody().open(config.client_secret,
                app_context(config.provider, config.client_id, config.app_generation))
             if session_custody.custody_mode() == "kms_v1" else config.client_secret)
    result = PreparedAppSecret(value, config, digest, canonical_hash(value))
    if not result.matches():
        raise CustodyUnavailable("OAuth application changed during secret opening")
    return result
