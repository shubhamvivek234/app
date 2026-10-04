"""Actual HTTP adapter logging redacts a credential-bearing query URL."""
import io
import logging
from unittest.mock import MagicMock
import httpx
import pytest
from utils.log_scrub import LogScrubFilter

@pytest.mark.asyncio
async def test_real_hunter_adapter_query_key_does_not_reach_emitted_logs(monkeypatch):
    from outreach.core.email_finder import _hunter_found_request, HUNTER_FOUND_URL
    opened='dummy-short-key'
    output=io.StringIO();handler=logging.StreamHandler(output);handler.addFilter(LogScrubFilter())
    logger=logging.getLogger('httpx');old_level=logger.level;logger.setLevel(logging.INFO);logger.addHandler(handler)
    client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(404)))
    envelope=MagicMock(spec=['assert_finder','call'])
    async def call(method,url,factory,**kwargs):return await factory()
    envelope.call=call
    monkeypatch.setattr('outreach.core.email_finder.httpx.AsyncClient',lambda **_:client)
    try: await _hunter_found_request(HUNTER_FOUND_URL,{'api_key':opened,'linkedin_handle':'sample'},envelope=envelope)
    finally: logger.removeHandler(handler);logger.setLevel(old_level);handler.close()
    assert output.getvalue() and opened not in output.getvalue() and '[REDACTED]' in output.getvalue()

@pytest.mark.parametrize('key',['api_key','api%5Fkey','client_secret','access_token','refresh_token'])
@pytest.mark.parametrize('sep',['=','%3D'])
def test_encoded_query_secrets_and_url_arguments_are_redacted(key,sep):
    record=logging.LogRecord('test',logging.INFO,'local',1,'URL %s', (httpx.URL('https://local.invalid/?'+key+sep+'short%2Fvalue&safe=ok'),),None)
    LogScrubFilter().filter(record)
    assert 'short' not in record.getMessage() and 'safe=ok' in record.getMessage()
