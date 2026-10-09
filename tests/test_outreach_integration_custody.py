"""Integration scope, captured configuration and rotation fail closed."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from outreach.core import integration_custody as custody
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped


def resource(kind="webhook", **changes):
    row = {"workspace_id": "w", "id": "hook", "status": "active",
           "target_url": "https://example.com/hook", "events": ["lead.replied"]}
    if kind != "webhook":
        row = {"workspace_id": "w", "provider": kind, "status": "connected",
               "metadata": {"portal_id": "123"} if kind == "hubspot" else {"channel_name": "#sales"}}
    return {**row, **changes}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,value", [("webhook", "private-signing-secret"),
    ("slack", "https://hooks.slack.com/services/T1/B2/private-token"), ("hubspot", "private-crm-token")])
async def test_seal_open_exact_prepare_and_no_secrets_in_repr(scoped, kind, value):
    row = resource(kind)
    row.update(await custody.seal(value, row, "w", kind))
    prepared = await custody.prepare(row, "w", kind)
    assert prepared.value == value and value not in repr(prepared)
    monkey = scoped.open
    scoped.open = AsyncMock(side_effect=AssertionError("No KMS in comparisons"))
    try:
        assert prepared.matches(row, "w", kind)
        assert not replace(prepared, value="changed").matches(row, "w", kind)
        assert not prepared.matches({**row, "credential_generation": "new"}, "w", kind)
    finally:
        scoped.open = monkey


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("workspace_id", "other"), ("id", "other"),
    ("credential_generation", "other"), ("target_url", "https://other.example/hook")])
async def test_webhook_context_swaps_deny(scoped, field, value):
    row = resource(); row.update(await custody.seal("private-secret", row, "w", "webhook"))
    with pytest.raises(CustodyUnavailable):
        await custody.prepare({**row, field: value}, "w", "webhook")


@pytest.mark.asyncio
async def test_provider_and_portal_swaps_deny(scoped):
    row = resource("hubspot"); row.update(await custody.seal("private-token", row, "w", "hubspot"))
    for changed in ({**row, "provider": "slack"}, {**row, "metadata": {"portal_id": "other"}}):
        with pytest.raises(CustodyUnavailable):
            await custody.prepare(changed, "w", "hubspot")


@pytest.mark.asyncio
async def test_custody_rotation_during_open_denies(scoped, monkeypatch):
    row = resource(); row.update(await custody.seal("private-secret", row, "w", "webhook"))
    original = scoped.open
    async def opened(*args):
        value = await original(*args)
        monkeypatch.setenv("OUTREACH_KMS_ROLE_ID", "replacement")
        return value
    monkeypatch.setattr(scoped, "open", opened)
    with pytest.raises(CustodyUnavailable): await custody.prepare(row, "w", "webhook")


@pytest.mark.asyncio
async def test_plaintext_legacy_and_downgrade_never_fall_back(scoped, monkeypatch):
    from utils.encryption import encrypt
    row = resource(); row.update(await custody.seal("secret", row, "w", "webhook"))
    for value in ("plaintext", encrypt("legacy"), ""):
        with pytest.raises(CustodyUnavailable):
            await custody.prepare({**row, "secret_enc": value}, "w", "webhook")
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    with pytest.raises(CustodyUnavailable): await custody.prepare(row, "w", "webhook")
    legacy = resource(); legacy.update(await custody.seal("legacy", legacy, "w", "webhook"))
    assert (await custody.prepare(legacy, "w", "webhook")).value == "legacy"


@pytest.mark.asyncio
async def test_snapshot_changes_during_open_cannot_change_prepared_scope(scoped, monkeypatch):
    row = resource(); row.update(await custody.seal("secret", row, "w", "webhook")); original = dict(row)
    opening = scoped.open
    async def mutate(*args):
        row["target_url"] = "https://replacement.example/"
        return await opening(*args)
    monkeypatch.setattr(scoped, "open", mutate)
    prepared = await custody.prepare(row, "w", "webhook")
    assert prepared.matches(original, "w", "webhook")
    assert not prepared.matches(row, "w", "webhook")
