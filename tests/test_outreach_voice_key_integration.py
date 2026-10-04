"""Worker custody is outside transactions and precedes possible-call budgets."""
from unittest.mock import AsyncMock
import httpx
import pytest
from outreach.core import voice_key_custody
from outreach.core.voice_studio import VoiceStudio
from outreach.core.voice_preparation import VoicePreparation
from outreach.core.voice_cloner import generate_mock_voice_wav
from tests.test_outreach_voice_studio import studio_db, clone
from tests.test_outreach_voice_preparation import voice_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_key_custody import installed
from tests.test_outreach_voice_studio_provider import Stream


async def campaign(db):
    db.outreach_voices.docs[0]['provider_source_digest'] = voice_key_custody.source_digest()
    return await VoicePreparation(db).queue('w', 'l', 'human')


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['studio', 'campaign'])
async def test_scoped_default_adapter_uses_opened_key_once(studio_db, voice_db, scoped, monkeypatch, path):
    await installed(monkeypatch)
    seen = []
    def handle(request):
        seen.append(request)
        body = b'{"voice_id":"remote","requires_verification":false}' if path == 'studio' else bytes(32000)
        return httpx.Response(200, headers={'content-type': 'application/json' if path == 'studio' else 'audio/pcm'}, stream=Stream(body))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    db = studio_db if path == 'studio' else voice_db
    service = VoiceStudio(db) if path == 'studio' else VoicePreparation(db)
    job = await clone(service) if path == 'studio' else await campaign(db)
    assert 'private-voice-key' not in str(job)
    assert (await service.run('w', job['_id']))['status'] == ('completed' if path == 'studio' else 'prepared')
    assert (await service.run('w', job['_id']))['status'] == ('completed' if path == 'studio' else 'prepared')
    assert len(seen) == 1 and seen[0].headers['xi-api-key'] == 'private-voice-key'


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['studio', 'campaign'])
@pytest.mark.parametrize('failure', ['kms', 'rotation', 'proof'])
async def test_open_failure_or_rotation_has_no_marker_budget_or_http(studio_db, voice_db, scoped, monkeypatch, path, failure):
    await installed(monkeypatch)
    db = studio_db if path == 'studio' else voice_db
    service = VoiceStudio(db) if path == 'studio' else VoicePreparation(db)
    job = await clone(service) if path == 'studio' else await campaign(db)
    if failure == 'proof':
        rows = db.outreach_voice_studio_jobs.docs if path == 'studio' else db.outreach_voice_preparation_jobs.docs
        rows[0]['configuration_digest' if path == 'studio' else 'provider_config_digest'] = 'wrong'
    original = scoped.open
    async def open_key(envelope, context):
        if context.purpose == 'voice_provider_key':
            if failure == 'kms': raise ValueError('private KMS failure')
            value = await original(envelope, context)
            if failure == 'rotation': monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'replacement')
            return value
        return await original(envelope, context)
    monkeypatch.setattr(scoped, 'open', open_key)
    provider = AsyncMock(return_value={'voice_id': 'remote'} if path == 'studio' else generate_mock_voice_wav())
    result = await service.run('w', job['_id'], **({'provider': provider} if path == 'studio' else {'generator': provider}))
    assert result['status'] in {'stopped', 'blocked'}
    provider.assert_not_awaited()
    assert not db.outreach_voice_studio_budgets.docs and not db.outreach_voice_preparation_budgets.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['studio', 'campaign'])
async def test_configuration_change_at_client_entry_holds_without_http(studio_db, voice_db, scoped, monkeypatch, path):
    await installed(monkeypatch)
    db = studio_db if path == 'studio' else voice_db
    service = VoiceStudio(db) if path == 'studio' else VoicePreparation(db)
    job = await clone(service) if path == 'studio' else await campaign(db)
    seen = []
    original = httpx.AsyncClient
    class RotatingClient(original):
        async def __aenter__(self):
            result = await super().__aenter__()
            monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'replacement')
            return result
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: RotatingClient(**kw, transport=httpx.MockTransport(lambda request: seen.append(request))))
    assert (await service.run('w', job['_id']))['status'] == 'held_outcome'
    assert not seen


@pytest.mark.asyncio
async def test_unproven_kms_campaign_job_denies_before_key_open(voice_db, scoped, monkeypatch):
    await installed(monkeypatch)
    job = await campaign(voice_db)
    voice_db.outreach_voice_preparation_jobs.docs[0].pop('provider_config_digest')
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    generator = AsyncMock()
    assert (await VoicePreparation(voice_db).run('w', job['_id'], generator=generator))['status'] == 'blocked'
    spy.assert_not_awaited(); generator.assert_not_awaited()
