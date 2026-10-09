"""Production adapters with local MockTransport and bounded DNS/write fences."""
import asyncio
import json
import logging
import socket
import time
from unittest.mock import AsyncMock
import httpx
import pytest
from outreach.core.integration_delivery import IntegrationDelivery
from outreach.core.safe_transport import PinnedAsyncNetworkBackend, FencedAsyncNetworkStream, SSRFSecurityError, validate_webhook_url
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped
from utils.log_scrub import LogScrubFilter

pytestmark = pytest.mark.asyncio

class Bytes(httpx.AsyncByteStream):
    def __init__(self, value): self.value = value
    async def __aiter__(self): yield self.value

@pytest.mark.parametrize('kind', ['webhook', 'slack', 'hubspot'])
async def test_actual_adapter_one_request_correct_auth_and_minimal_receipt(integration_db, monkeypatch, kind):
    db = integration_db; job = await queue(db, kind); calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, stream=Bytes(b'{"id":"456","private":"not-retained"}'))
    monkeypatch.setattr('outreach.core.safe_transport.create_safe_client', lambda **kwargs:
        httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    result = await IntegrationDelivery(db).run('w', job['id'])
    assert result['status'] == 'delivered' and len(calls) == 1
    request = calls[0]
    if kind == 'webhook':
        from outreach.core.webhook_signer import verify_signature
        assert verify_signature(request.content, 'private-signing-secret', request.headers['x-unravler-signature'],
                                request.headers['x-unravler-timestamp'])
    elif kind == 'hubspot': assert request.headers['authorization'] == 'Bearer private-crm-token'
    else: assert 'blocks' in json.loads(request.content)
    row = await db.outreach_webhook_deliveries.find_one({'workspace_id': 'w'})
    assert set(row['receipt']) <= {'status_code', 'received_at', 'external_id'}
    assert 'not-retained' not in str(row)

@pytest.mark.parametrize('problem', ['conflict', 'oversized', 'encoded', 'bad_id'])
async def test_crm_conflict_or_unproven_receipt_cannot_trigger_second_mutation(integration_db, monkeypatch, problem):
    db = integration_db; job = await queue(db, 'hubspot'); calls = []
    def transport(request):
        calls.append(request)
        value = b'x' * 65537 if problem == 'oversized' else b'{"id":"non-numeric"}' if problem == 'bad_id' else b'{"id":"456"}'
        return httpx.Response(409 if problem == 'conflict' else 200, stream=Bytes(value),
            headers={'content-encoding': 'gzip'} if problem == 'encoded' else {})
    monkeypatch.setattr('outreach.core.safe_transport.create_safe_client', lambda **kwargs:
        httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    result = await IntegrationDelivery(db).run('w', job['id'])
    assert result['status'] == 'review_required'
    await IntegrationDelivery(db).run('w', job['id'])
    assert len(calls) == 1
    assert await db.outreach_external_mappings.count_documents({}) == 0

async def test_slack_http500_never_retries_notification(integration_db):
    job = await IntegrationDelivery(integration_db).queue('w', 'slack', 'slack', 'internal-event', {})
    provider = AsyncMock(return_value={'status_code': 500})
    assert (await IntegrationDelivery(integration_db).run('w', job['id'], provider=provider))['status'] == 'review_required'
    await IntegrationDelivery(integration_db).run('w', job['id'], provider=provider)
    assert provider.await_count == 1

async def test_slow_dns_yields_and_expires_without_connection(monkeypatch):
    backend = PinnedAsyncNetworkBackend()
    def slow(*args, **kwargs):
        time.sleep(.04)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', slow)
    connect = AsyncMock(); monkeypatch.setattr(backend._anyio_backend, 'connect_tcp', connect)
    with pytest.raises(TimeoutError): await backend.connect_tcp('example.com', 443, timeout=.005)
    connect.assert_not_awaited()

async def test_expiry_after_dns_prevents_connect(monkeypatch):
    permission = {'active': True}; backend = PinnedAsyncNetworkBackend(preflight=lambda: permission['active'])
    def resolve(*args, **kwargs):
        permission['active'] = False
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    connect = AsyncMock(); monkeypatch.setattr(backend._anyio_backend, 'connect_tcp', connect)
    with pytest.raises(SSRFSecurityError, match='expired'): await backend.connect_tcp('example.com', 443)
    connect.assert_not_awaited()

async def test_stream_rechecks_after_tls_and_before_body_write():
    permission = {'active': True}; stream = AsyncMock(); tls = AsyncMock()
    stream.start_tls.return_value = tls
    wrapped = await FencedAsyncNetworkStream(stream, lambda: permission['active']).start_tls(None)
    permission['active'] = False
    with pytest.raises(SSRFSecurityError): await wrapped.write(b'private-body')
    tls.write.assert_not_awaited(); tls.aclose.assert_awaited_once()

@pytest.mark.parametrize('host', ['hooks.slack.com', 'hooks.gov-slack.com'])
async def test_slack_url_redacted_from_httpx_strings_objects_and_nested_fields(host):
    url = f'https://{host}/services/T1/B2/private-short-token'
    record = logging.LogRecord('httpx', 20, __file__, 1, 'HTTP %s %s', (httpx.URL(url), {'value': url}), None)
    LogScrubFilter().filter(record)
    assert 'private-short-token' not in record.getMessage() and '[REDACTED]' in record.getMessage()

async def test_literal_private_ip_rejected_before_dns():
    with pytest.raises(SSRFSecurityError): validate_webhook_url('https://192.168.1.1/hook')

async def test_denied_tls_start_closes_socket_before_handshake():
    stream = AsyncMock()
    with pytest.raises(SSRFSecurityError):
        await FencedAsyncNetworkStream(stream, lambda: False).start_tls(None)
    stream.start_tls.assert_not_awaited(); stream.aclose.assert_awaited_once()
