"""Session consumers require independent job/account scope; no envelope fallback."""
from unittest.mock import AsyncMock

import pytest

from outreach.core import session_custody
from outreach.core.credential_custody import CredentialCustody, CustodyUnavailable
from outreach.core.crypto import decrypt_secret, encrypt_secret
from tests.test_outreach_credential_custody import ARN, LocalKeys


@pytest.fixture
def scoped(monkeypatch):
    from cryptography.fernet import Fernet
    from utils import encryption
    monkeypatch.setattr(encryption, "_fernet", Fernet(Fernet.generate_key()))
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
    monkeypatch.setenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", "test-environment")
    custody = CredentialCustody(ARN, LocalKeys())
    monkeypatch.setattr(session_custody, "configured_custody", lambda: custody)
    return custody


@pytest.mark.asyncio
async def test_pending_and_installed_scopes_are_distinct_and_all_cookies_rewrap(scoped):
    job = {"id": "job", "workspace_id": "w", "sender_id": "a"}
    material = {"li_at": "private-cookie", "jsession_id": "ajax:csrf", "li_a": "private-navigation"}
    job.update(await session_custody.seal_pending(material, "w", "a", "job"))
    assert await session_custody.pending_session(job) == material
    account = {"id": "a", "workspace_id": "w", "credential_generation": "g"}
    account.update(await session_custody.seal_installed(material, "w", "a", "g"))
    assert await session_custody.account_session(account) == material
    assert account["session_cookie_enc"] != job["li_at_enc"]
    for field, value in [("workspace_id", "other"), ("id", "other"), ("credential_generation", "other")]:
        with pytest.raises(CustodyUnavailable):
            await session_custody.account_session({**account, field: value})
    with pytest.raises(CustodyUnavailable):
        await session_custody.pending_session({**job, "id": "other"})
    with pytest.raises(CustodyUnavailable):
        decrypt_secret(account["session_cookie_enc"])


@pytest.mark.asyncio
async def test_kms_mode_never_opens_plaintext_mock_or_fernet(scoped):
    for value in ("plaintext", "mock_cookie", encrypt_secret("real-legacy-cookie")):
        with pytest.raises(CustodyUnavailable):
            await session_custody.account_session({"id": "a", "workspace_id": "w", "credential_generation": "g",
                "session_cookie_enc": value, "jsession_id": value})


@pytest.mark.asyncio
async def test_legacy_mode_has_no_kms_calls_and_cannot_downgrade_envelopes(scoped, monkeypatch):
    job = {"id": "job", "workspace_id": "w", "sender_id": "a"}
    material = {"li_at": "private-cookie", "jsession_id": "ajax:csrf", "li_a": ""}
    sealed = await session_custody.seal_pending(material, "w", "a", "job")
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    monkeypatch.setattr(session_custody, "configured_custody", lambda: (_ for _ in ()).throw(AssertionError("No KMS")))
    legacy = await session_custody.seal_pending(material, "w", "a", "job")
    assert await session_custody.pending_session({**job, **legacy}) == material
    with pytest.raises(CustodyUnavailable):
        await session_custody.pending_session({**job, **sealed})


@pytest.mark.asyncio
async def test_kms_configuration_and_missing_context_fail_before_provider(monkeypatch):
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "invalid")
    with pytest.raises(CustodyUnavailable):
        await session_custody.seal_pending({"li_at": "cookie", "jsession_id": "csrf"}, "w", "a", "job")
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
    monkeypatch.delenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", raising=False)
    with pytest.raises(CustodyUnavailable):
        await session_custody.seal_pending({"li_at": "cookie", "jsession_id": "csrf"}, "w", "a", "job")
