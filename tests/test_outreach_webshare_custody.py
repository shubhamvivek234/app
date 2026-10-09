"""Webshare application-key scope and rotation tests; fake KMS only."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped


async def installed(monkeypatch, generation='g1'):
    from outreach.core import webshare_key_custody as custody
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER', 'webshare')
    monkeypatch.delenv('WEBSHARE_API_KEY', raising=False)
    envelope = await custody.seal_key('private-webshare-key', generation)
    monkeypatch.setenv('OUTREACH_WEBSHARE_API_KEY_ENC', envelope)
    monkeypatch.setenv('OUTREACH_WEBSHARE_KEY_GENERATION', generation)
    return custody


@pytest.mark.asyncio
async def test_metadata_never_opens_and_prepared_material_is_private(scoped, monkeypatch):
    custody = await installed(monkeypatch)
    opened = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', opened)
    config = custody.capture_configuration()
    assert custody.configuration_state() == 'live'
    assert custody.configuration_digest() == config.digest
    opened.assert_not_awaited()
    key = await custody.prepare_key(expected_digest=config.digest)
    assert key.value == 'private-webshare-key' and key.matches()
    assert 'private-webshare-key' not in repr(key)
    assert 'uc1:' not in repr(config)
    assert not replace(key, value='replacement').matches()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['generation', 'environment', 'purpose', 'provider', 'plaintext', 'downgrade', 'missing', 'proof', 'override'])
async def test_wrong_storage_or_scope_denies_without_fallback(scoped, monkeypatch, change):
    custody = await installed(monkeypatch)
    proof = custody.configuration_digest()
    if change == 'generation': monkeypatch.setenv('OUTREACH_WEBSHARE_KEY_GENERATION', 'g2')
    if change == 'environment': monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'other')
    if change == 'purpose':
        from outreach.core import session_custody
        envelope = await scoped.seal('private-webshare-key', session_custody.context('outreach-proxy-provider', 'webshare', 'g1', 'proxy_password'))
        monkeypatch.setenv('OUTREACH_WEBSHARE_API_KEY_ENC', envelope)
    if change == 'provider': monkeypatch.setenv('OUTREACH_PROXY_PROVIDER', 'iproyal')
    if change == 'plaintext': monkeypatch.setenv('WEBSHARE_API_KEY', 'fallback-private-key')
    if change == 'downgrade': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    if change == 'missing': monkeypatch.delenv('OUTREACH_WEBSHARE_KEY_GENERATION')
    with pytest.raises(CustodyUnavailable):
        await custody.prepare_key(expected_digest='wrong' if change == 'proof' else proof,
            override='another-key' if change == 'override' else None)


@pytest.mark.asyncio
@pytest.mark.parametrize('setting', ['OUTREACH_WEBSHARE_API_KEY_ENC', 'OUTREACH_WEBSHARE_KEY_GENERATION', 'OUTREACH_KMS_ROLE_ID', 'OUTREACH_KMS_KEY_ARN', 'OUTREACH_PROXY_PROVIDER'])
async def test_changed_configuration_during_open_denies(scoped, monkeypatch, setting):
    custody = await installed(monkeypatch)
    original = scoped.open
    async def change(*args):
        result = await original(*args)
        monkeypatch.setenv(setting, 'replacement')
        return result
    monkeypatch.setattr(scoped, 'open', change)
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()


@pytest.mark.asyncio
async def test_legacy_key_compatibility_and_mock_metadata_have_no_kms(monkeypatch):
    from outreach.core import session_custody, webshare_key_custody as custody
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER', 'webshare')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.delenv('OUTREACH_WEBSHARE_API_KEY_ENC', raising=False)
    monkeypatch.delenv('OUTREACH_WEBSHARE_KEY_GENERATION', raising=False)
    monkeypatch.setattr(session_custody, 'configured_custody', lambda: pytest.fail('No KMS'))
    monkeypatch.setenv('WEBSHARE_API_KEY', 'mock')
    assert custody.configuration_state() == 'mock'
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()
    monkeypatch.setenv('WEBSHARE_API_KEY', 'legacy-private-key')
    key = await custody.prepare_key()
    assert key.matches()
    monkeypatch.setenv('WEBSHARE_API_KEY', 'replacement')
    assert not key.matches()
    override = await custody.prepare_key(override='explicit-legacy-key')
    assert override.value == 'explicit-legacy-key' and override.matches()


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['', 'mock', 'test', 'two\nlines', 'uc1:bad', 'é', 'x' * 1025])
async def test_invalid_keys_deny(monkeypatch, value):
    from outreach.core import webshare_key_custody as custody
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('OUTREACH_PROXY_PROVIDER', 'webshare')
    monkeypatch.setenv('WEBSHARE_API_KEY', value)
    with pytest.raises(CustodyUnavailable): await custody.prepare_key()


@pytest.mark.asyncio
async def test_sealing_late_policy_change_denies(scoped, monkeypatch):
    from outreach.core import webshare_key_custody as custody
    original = scoped.seal
    async def change(*args):
        result = await original(*args)
        monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'replacement')
        return result
    monkeypatch.setattr(scoped, 'seal', change)
    with pytest.raises(CustodyUnavailable): await custody.seal_key('private-webshare-key', 'g')


@pytest.mark.asyncio
async def test_health_inspection_does_not_open_or_claim_mock_for_invalid_scoped_config(scoped, monkeypatch):
    from outreach.api.router import outreach_health
    await installed(monkeypatch)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('Metadata only')))
    assert (await outreach_health())['proxy_provider_mode'] == 'live'
    monkeypatch.delenv('OUTREACH_WEBSHARE_KEY_GENERATION')
    assert (await outreach_health())['proxy_provider_mode'] == 'unavailable'


@pytest.mark.parametrize('value', ['abc', 'private-webshare-key'])
def test_token_header_and_key_configuration_are_redacted(value):
    from utils.log_scrub import LogScrubFilter
    for key in ('WEBSHARE_API_KEY', 'OUTREACH_WEBSHARE_API_KEY_ENC', 'Authorization'):
        data = {'headers': {key: 'Token ' + value if key == 'Authorization' else value}}
        assert value not in str(LogScrubFilter._scrub_value(data))
        assert value not in LogScrubFilter._scrub(str(data))
    assert value not in LogScrubFilter._scrub('Authorization: Token ' + value)


def test_named_webshare_log_arguments_are_scrubbed():
    import io
    import logging
    from utils.log_scrub import attach_scrub_filter
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    attach_scrub_filter(handler)
    logger = logging.Logger('webshare-local-key-test')
    logger.addHandler(handler)
    logger.warning('key=%(WEBSHARE_API_KEY)s', {'WEBSHARE_API_KEY': 'private-webshare-key'})
    assert 'private-webshare-key' not in output.getvalue()
    assert '[REDACTED]' in output.getvalue()
