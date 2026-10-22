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


def test_linkedin_cookies_and_proxy_credentials_are_redacted():
    raw_msg = (
        "Cookie: li_at=AQEDAR_SECRET_COOKIE_12345; JSESSIONID=\"ajax:987654321\"; "
        "proxy=http://proxy_user:proxy_secret_pass@isp.proxy.example.com:8080"
    )
    record = logging.LogRecord('test', logging.WARNING, 'local', 1, raw_msg, (), None)
    LogScrubFilter().filter(record)
    rendered = record.getMessage()
    assert "AQEDAR_SECRET_COOKIE_12345" not in rendered
    assert "ajax:987654321" not in rendered
    assert "proxy_user:proxy_secret_pass" not in rendered
    assert "http://[REDACTED]@isp.proxy.example.com:8080" in rendered


def test_log_outreach_event_scrubs_sensitive_fields_and_records_error_type(caplog):
    from outreach.core.logging_utils import get_outreach_logger, log_outreach_event

    test_logger = get_outreach_logger("outreach.test_logger")
    with caplog.at_level(logging.WARNING, logger="outreach.test_logger"):
        log_outreach_event(
            test_logger,
            "warning",
            "outreach.test.event",
            error=RuntimeError("raw_secret_cookie_value"),
            workspace_id="ws-123",
            session_cookie_enc="ENCRYPTED_SECRET_VALUE",
            proxy_url="http://user1:secretpass2@proxy.internal:3128",
        )
    assert "outreach.test.event" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "raw_secret_cookie_value" not in caplog.text
    assert "ENCRYPTED_SECRET_VALUE" not in caplog.text
    assert "secretpass2" not in caplog.text

