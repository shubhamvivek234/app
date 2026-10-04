"""Credential envelopes cannot cross tenant, sender, generation or purpose."""
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from outreach.core.credential_custody import CredentialContext, CredentialCustody, CustodyUnavailable

ARN = "arn:aws:kms:eu-north-1:123456789012:key/11111111-2222-3333-4444-555555555555"


class LocalKeys:
    def __init__(self):
        self.calls = []
        self.keys = {}

    async def generate(self, context):
        import os
        key, wrapped = os.urandom(32), os.urandom(64)
        self.keys[wrapped] = (key, context)
        self.calls.append(("generate", context))
        return key, wrapped

    async def unwrap(self, wrapped, context):
        self.calls.append(("unwrap", context))
        key, original = self.keys[wrapped]
        if original != context:
            raise ValueError("incorrect KMS context")
        return key


def scope(**kwargs):
    return replace(CredentialContext("workspace", "sender", "generation", "session_li_at", "test-environment"), **kwargs)


@pytest.mark.asyncio
async def test_unique_envelopes_exact_context_and_no_plaintext_key_cache():
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    one = await custody.seal("private-session", scope())
    two = await custody.seal("private-session", scope())
    assert one != two and "private-session" not in one
    assert await custody.open(one, scope()) == "private-session"
    assert await custody.open(one, scope()) == "private-session"
    assert [call[0] for call in keys.calls] == ["generate", "generate", "unwrap", "unwrap"]
    assert not any("workspace" == value for value in keys.calls[0][1].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["workspace_id", "sender_id", "generation", "purpose", "environment_id"])
async def test_context_swap_denies_before_key_service(field):
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    value = await custody.seal("private-session", scope())
    changed = "session_jsession" if field == "purpose" else "different"
    with pytest.raises(CustodyUnavailable):
        await custody.open(value, scope(**{field: changed}))
    assert len(keys.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["version", "algorithm", "key_arn", "context", "nonce", "ciphertext", "wrapped_key", "unknown"])
async def test_tampered_envelope_never_returns_secret(field):
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    value = json.loads((await custody.seal("private-session", scope()))[4:])
    value[field] = 99 if field == "version" else "tampered"
    with pytest.raises(CustodyUnavailable):
        await custody.open("uc1:" + json.dumps(value), scope())


@pytest.mark.asyncio
async def test_key_service_failure_malformed_key_and_legacy_values_deny():
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    for text in ("plaintext", "mock_session", "gAAAAAcipher", "uc1:{", "uc1:" + "x" * 100000):
        with pytest.raises(CustodyUnavailable):
            await custody.open(text, scope())
    keys.generate = AsyncMock(return_value=(bytes(16), b"wrapped"))
    with pytest.raises(CustodyUnavailable):
        await custody.seal("secret", scope())
    keys.generate = AsyncMock(side_effect=RuntimeError("secret-provider-error"))
    with pytest.raises(CustodyUnavailable) as error:
        await custody.seal("secret", scope())
    assert "secret-provider-error" not in str(error.value)


@pytest.mark.parametrize("field,value", [("workspace_id", ""), ("sender_id", " leading"), ("generation", "x" * 300), ("purpose", "proxy"), ("environment_id", "bad\nvalue")])
def test_context_requires_bounded_server_owned_identity(field, value):
    with pytest.raises(CustodyUnavailable):
        scope(**{field: value}).kms_context()


@pytest.mark.asyncio
async def test_invalid_key_and_plaintext_size_are_rejected_before_provider():
    keys = LocalKeys()
    with pytest.raises(CustodyUnavailable):
        CredentialCustody("alias/rotating", keys)
    for secret in ("", "x" * 32769, 1):
        with pytest.raises(CustodyUnavailable):
            await CredentialCustody(ARN, keys).seal(secret, scope())
    assert not keys.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['ciphertext', 'nonce', 'wrapped_key'])
async def test_validly_encoded_ciphertext_nonce_or_wrapped_key_tampering_denies(field):
    import base64
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    doc = json.loads((await custody.seal('private-session', scope()))[4:])
    data = bytearray(base64.b64decode(doc[field]))
    data[0] ^= 1
    doc[field] = base64.b64encode(data).decode()
    with pytest.raises(CustodyUnavailable):
        await custody.open('uc1:' + json.dumps(doc), scope())


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['duplicate', 'boolean_version'])
async def test_strict_json_rejects_ambiguous_or_coerced_versions_before_kms(invalid):
    keys = LocalKeys()
    custody = CredentialCustody(ARN, keys)
    envelope = await custody.seal('private-session', scope())
    if invalid == 'duplicate':
        envelope = envelope.replace('{', '{"version":1,', 1)
    else:
        envelope = envelope.replace('"version":1', '"version":true')
    with pytest.raises(CustodyUnavailable): await custody.open(envelope, scope())
    assert len(keys.calls) == 1


def test_unhashable_context_purpose_and_noncanonical_key_fail_sanitized():
    with pytest.raises(CustodyUnavailable): scope(purpose=[]).kms_context()
    with pytest.raises(CustodyUnavailable): CredentialCustody(ARN[:-36] + '-' * 36, LocalKeys())
