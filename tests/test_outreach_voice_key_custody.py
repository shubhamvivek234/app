"""Voice provider key custody uses local fake KMS; never vendor/AWS calls."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped


async def installed(monkeypatch, generation='g1'):
    from outreach.core import voice_key_custody as custody
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    envelope = await custody.seal_key('private-voice-key', generation)
    monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC', envelope)
    monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', generation)
    return custody


@pytest.mark.asyncio
async def test_scoped_key_metadata_never_opens_and_prepared_repr_is_private(scoped, monkeypatch):
    custody = await installed(monkeypatch)
    config = custody.capture_configuration()
    assert custody.source_digest() != canonical_hash(['elevenlabs', 'private-voice-key'])
    opened = scoped.open
    spy = AsyncMock(wraps=opened)
    monkeypatch.setattr(scoped, 'open', spy)
    custody.source_digest(); custody.configuration_digest()
    spy.assert_not_awaited()
    key = await custody.prepare_key(expected_digest=custody.configuration_digest(), expected_source=custody.source_digest())
    assert key.value == 'private-voice-key' and key.matches()
    assert 'private-voice-key' not in repr(key) and 'uc1:' not in repr(config)
    assert not replace(key, value='replacement').matches()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['generation', 'environment', 'purpose', 'plaintext', 'downgrade', 'missing', 'proof'])
async def test_wrong_scope_or_storage_denies_without_fallback(scoped, monkeypatch, change):
    custody = await installed(monkeypatch)
    proof = custody.configuration_digest()
    if change == 'generation': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'g2')
    if change == 'environment': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'other')
    if change == 'purpose':
        from outreach.core import session_custody
        envelope = await scoped.seal('private-voice-key', session_custody.context('outreach-voice-provider', 'elevenlabs', 'g1', 'voice_studio_key'))
        monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC', envelope)
    if change == 'plaintext': monkeypatch.setenv('ELEVENLABS_API_KEY', 'private-fallback')
    if change == 'downgrade': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    if change == 'missing': monkeypatch.delenv('OUTREACH_ELEVENLABS_KEY_GENERATION')
    with pytest.raises(CustodyUnavailable):
        await custody.prepare_key(expected_digest='wrong' if change == 'proof' else proof)


@pytest.mark.asyncio
@pytest.mark.parametrize('setting', ['OUTREACH_ELEVENLABS_API_KEY_ENC', 'OUTREACH_KMS_ROLE_ID', 'OUTREACH_KMS_KEY_ARN'])
async def test_rotation_during_key_open_denies(scoped, monkeypatch, setting):
    custody = await installed(monkeypatch)
    original = scoped.open
    async def rotated(*args):
        value = await original(*args)
        monkeypatch.setenv(setting, 'replacement')
        return value
    monkeypatch.setattr(scoped, 'open', rotated)
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()


@pytest.mark.asyncio
async def test_legacy_digest_stays_compatible_and_has_no_kms(monkeypatch):
    from outreach.core import voice_key_custody as custody, session_custody
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'legacy-key')
    monkeypatch.setattr(session_custody, 'configured_custody', lambda: pytest.fail('No KMS'))
    assert custody.source_digest() == canonical_hash(['elevenlabs', 'legacy-key'])
    key = await custody.prepare_key()
    assert key.matches()
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'replacement')
    assert not key.matches()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ['', 'mock', 'test', 'two\nlines', 'uc1:bad', 'x' * 1025])
async def test_invalid_legacy_key_is_rejected(monkeypatch, key):
    from outreach.core import voice_key_custody as custody
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('ELEVENLABS_API_KEY', key)
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()


@pytest.mark.asyncio
async def test_sealing_policy_rotation_denies(scoped, monkeypatch):
    from outreach.core import voice_key_custody as custody
    original = scoped.seal
    async def rotated(*args):
        envelope = await original(*args)
        monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'replacement')
        return envelope
    monkeypatch.setattr(scoped, 'seal', rotated)
    with pytest.raises(CustodyUnavailable): await custody.seal_key('private', 'g')


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['generation', 'environment', 'purpose'])
async def test_envelope_context_itself_rejects_even_without_job_proof(scoped, monkeypatch, change):
    custody = await installed(monkeypatch)
    if change == 'generation': monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION', 'other')
    if change == 'environment': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'other')
    if change == 'purpose':
        from outreach.core import session_custody
        envelope = await scoped.seal('private-voice-key', session_custody.context('outreach-voice-provider', 'elevenlabs', 'g1', 'voice_studio_key'))
        monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC', envelope)
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()


@pytest.mark.parametrize('value', ['abc', 'private-voice-key'])
def test_provider_header_and_environment_keys_are_redacted(value):
    from utils.log_scrub import LogScrubFilter
    for field in ['xi-api-key', 'ELEVENLABS_API_KEY', 'OUTREACH_ELEVENLABS_API_KEY_ENC']:
        assert value not in str(LogScrubFilter._scrub_value({'headers': {field: value}}))
    assert value not in LogScrubFilter._scrub(str({'xi-api-key': value}))


def test_named_log_arguments_are_redacted_at_emitted_handler():
    import io
    import logging
    from utils.log_scrub import attach_scrub_filter
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    attach_scrub_filter(handler)
    logger = logging.Logger('voice-key-local-test')
    logger.addHandler(handler)
    logger.warning('provider key=%(xi-api-key)s', {'xi-api-key': 'named-private-key'})
    assert 'named-private-key' not in output.getvalue()
    assert '[REDACTED]' in output.getvalue()
