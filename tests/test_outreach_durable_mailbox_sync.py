"""Reference-only sync, conservative reads and recoverable cursor installation."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import httpx
import pytest

from tests.test_outreach_mailbox_job_lifecycle import lifecycle
from utils.encryption import encrypt
from tests.test_outreach_session_custody import scoped


@pytest.fixture
def sync_db(lifecycle, monkeypatch):
    from outreach.core import mailbox_sync
    monkeypatch.setenv('OUTREACH_EMAIL_SYNC_ENABLED', 'true')
    monkeypatch.setattr(mailbox_sync, '_paid_sender', AsyncMock(return_value=True))
    lifecycle.outreach_mailboxes.docs.append({'workspace_id': 'w', 'sender_account_id': 'a', 'status': 'active',
        'provider': 'gmail', 'provider_user_id': 'sender@example.com', 'email': 'sender@example.com',
        'connection_job_id': 'installed', 'custody_generation': 'generation', 'history_id': '100', 'sync_status': 'healthy',
        'access_token_enc': encrypt('access'), 'refresh_token_enc': encrypt('refresh'),
        'token_expires_at': datetime.now(timezone.utc) + timedelta(hours=1)})
    return lifecycle


def http_reads(monkeypatch, *, fail=None):
    from outreach.core import mailbox_sync
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={'historyId': '101'})
    if fail: client.get.side_effect = fail
    class Streaming:
        async def __aenter__(self):
            response = await client.get(*self.args, **self.kwargs)
            return (httpx.Response(response.status_code, headers=response.headers, stream=httpx.ByteStream(response.content))
                if response.is_stream_consumed else response)
        async def __aexit__(self, *_): pass
    def stream(method, *args, **kwargs):
        assert method == 'GET'
        instance = Streaming(); instance.args = args; instance.kwargs = kwargs
        return instance
    client.stream = stream
    context = AsyncMock(); context.__aenter__.return_value = client
    monkeypatch.setattr(mailbox_sync.httpx, 'AsyncClient', lambda **_: context)
    return client


@pytest.mark.asyncio
async def test_job_and_read_are_durable_before_http_and_cursor_commit(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    async def get(*args, **kwargs):
        job = sync_db.outreach_mailbox_sync_jobs.docs[0]
        assert job['status'] == 'running' and job['owner']
        assert sync_db.outreach_mailbox_sync_reads.docs[0]['status'] == 'possible'
        assert sync_db.outreach_mailbox_read_budgets.docs[0]['used'] == 1
        assert sync_db.outreach_mailboxes.docs[0]['history_id'] == '100'
        return httpx.Response(200, json={'historyId': '101'})
    client.get.side_effect = get
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    assert await jobs.execute_job(sync_db, 'w', job['_id']) == {'status': 'healthy', 'replies': 0, 'bounces': 0}
    assert sync_db.outreach_mailboxes.docs[0]['history_id'] == '101'
    assert sync_db.outreach_mailbox_sync_jobs.docs[0]['status'] == 'completed'
    assert sync_db.outreach_mailbox_sync_reads.docs[0]['status'] == 'received'
    assert await jobs.execute_job(sync_db, 'w', job['_id']) == {'status': 'already_claimed'}
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_broker_loss_keeps_reference_job_due(sync_db):
    from outreach.core import mailbox_sync_jobs as jobs
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    calls = []
    def failed(job_id, workspace):
        calls.append((job_id, workspace)); raise RuntimeError('broker down')
    assert await jobs.publish_due(sync_db, failed) == {'published': 0, 'failed': 1}
    assert calls == [(job['_id'], 'w')]
    assert sync_db.outreach_mailbox_sync_jobs.docs[0]['status'] == 'queued'
    assert sync_db.outreach_mailbox_sync_jobs.docs[0]['next_publish_at'] > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_received_read_recovers_without_http_after_local_cursor_failure(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    finalize = jobs.finish_job
    monkeypatch.setattr(jobs, 'finish_job', AsyncMock(side_effect=RuntimeError('database down')))
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    assert sync_db.outreach_mailboxes.docs[0]['history_id'] == '100'
    monkeypatch.setattr(jobs, 'finish_job', finalize)
    sync_db.outreach_mailbox_sync_jobs.docs[0]['next_publish_at'] = datetime.now(timezone.utc)
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'healthy'
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_read_recovery_spends_new_budget_without_resetting_evidence(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch, fail=asyncio.CancelledError())
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    with pytest.raises(asyncio.CancelledError): await jobs.execute_job(sync_db, 'w', job['_id'])
    sync_db.outreach_mailbox_sync_jobs.docs[0]['lease_until'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await jobs.recover_due(sync_db))['recovered'] == 1
    client.get.side_effect = None
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'healthy'
    reads = sync_db.outreach_mailbox_sync_reads.docs
    assert len(reads) == 2 and reads[0]['status'] == 'read_interrupted' and reads[1]['status'] == 'received'
    assert sync_db.outreach_mailbox_read_budgets.docs[0]['used'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['generation', 'cursor', 'disabled'])
async def test_async_transport_fences_replacement_or_disabled_control(sync_db, monkeypatch, change):
    from outreach.core import mailbox_sync, mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    original = jobs.SyncReadAccess.authorize
    async def changed(self):
        if change == 'generation': sync_db.outreach_mailboxes.docs[0]['custody_generation'] = 'replacement'
        if change == 'cursor': sync_db.outreach_mailboxes.docs[0]['history_id'] = 'replacement'
        if change == 'disabled': monkeypatch.setenv('OUTREACH_EMAIL_SYNC_ENABLED', 'false')
        return await original(self)
    monkeypatch.setattr(jobs.SyncReadAccess, 'authorize', changed)
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    client.get.assert_not_awaited()
    assert sync_db.outreach_mailboxes.docs[0]['history_id'] != '101'


@pytest.mark.asyncio
async def test_scoped_response_cache_uses_bound_wrapped_data_key(sync_db, scoped, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    from outreach.core.provider_custody import seal_mailbox_tokens
    row = sync_db.outreach_mailboxes.docs[0]
    row.update(await seal_mailbox_tokens({'access_token': 'access', 'refresh_token': 'refresh'}, row, 'w', 'a', generation='generation'))
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    finalize = jobs.finish_job
    monkeypatch.setattr(jobs, 'finish_job', AsyncMock(side_effect=RuntimeError('local down')))
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    read = sync_db.outreach_mailbox_sync_reads.docs[0]
    assert 'mailbox_sync_key' in read['response_enc'] and 'historyId' not in read['response_enc']
    saved_cipher = read['response_enc']
    monkeypatch.setattr(jobs, 'finish_job', finalize)
    from outreach.core import mailbox_sync
    monkeypatch.setattr(mailbox_sync, 'get_mailbox_access_token', AsyncMock(side_effect=AssertionError('No refresh for cached reads')))
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'healthy'
    client.get.assert_awaited_once()
    assert not read.get('response_enc')
    with pytest.raises(Exception): await jobs._crypt({**job, 'basis': 'replacement'}, read['_id'], saved_cipher, opening=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', ['daily', 'job', 'response', 'cache', 'encoded_response'])
async def test_physical_and_storage_limits_keep_old_cursor(sync_db, monkeypatch, limit):
    from outreach.core import mailbox_sync_jobs as jobs
    from outreach.core.authorization import canonical_hash
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    if limit == 'daily':
        key = canonical_hash(['mailbox-read', 'w', 'a', jobs.now().date().isoformat()])
        sync_db.outreach_mailbox_read_budgets.docs.append({'_id': key, 'workspace_id': 'w', 'used': jobs.DAILY_READ_LIMIT})
    if limit == 'job': sync_db.outreach_mailbox_sync_jobs.docs[0]['physical_reads'] = jobs.MAX_JOB_READS
    if limit == 'response': client.get.return_value = httpx.Response(200, content=b'x' * (jobs.MAX_RESPONSE_BYTES + 1))
    if limit == 'cache': sync_db.outreach_mailbox_sync_jobs.docs[0]['cache_bytes'] = jobs.MAX_CACHE_BYTES
    if limit == 'encoded_response': client.get.return_value = httpx.Response(200, headers={'Content-Encoding': 'gzip'},
        stream=httpx.ByteStream(b'encoded-body-must-not-be-decoded'))
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    assert sync_db.outreach_mailboxes.docs[0]['history_id'] == '100'
    assert not any(r['status'] == 'received' for r in sync_db.outreach_mailbox_sync_reads.docs)
    if limit in {'daily', 'job'}: client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_expiry_after_permit_denies_transport_and_keeps_allowance(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    authorize = jobs.SyncReadAccess.authorize
    async def expire(self):
        deadlines = await authorize(self)
        return [*deadlines, jobs.now() - timedelta(seconds=1)]
    monkeypatch.setattr(jobs.SyncReadAccess, 'authorize', expire)
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    client.get.assert_not_awaited()
    assert sync_db.outreach_mailbox_read_budgets.docs[0]['used'] == 1


@pytest.mark.asyncio
async def test_incomplete_pages_keep_cursor_and_saved_pages_without_fabricated_health(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    client.get.return_value = httpx.Response(200, json={'historyId': '101', 'nextPageToken': 'more'})
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    assert sync_db.outreach_mailboxes.docs[0]['history_id'] == '100'
    assert client.get.await_count == 20
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    assert client.get.await_count == 20


@pytest.mark.asyncio
async def test_original_graph_baseline_filter_does_not_move_during_recovery(sync_db, monkeypatch):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    sync_db.outreach_mailboxes.docs[0].update(provider='microsoft', delta_url=None)
    first = 'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=next'
    final = 'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=final'
    client.get.side_effect = [httpx.Response(200, json={'value': [], '@odata.nextLink': first}), httpx.ReadTimeout('loopback')]
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    original_filter = client.get.await_args_list[0].kwargs['params']['$filter']
    assert str(job['coverage_started_at'].date()) in original_filter
    client.get.side_effect = None
    client.get.return_value = httpx.Response(200, json={'value': [], '@odata.deltaLink': final})
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'healthy'
    assert client.get.await_count == 3  # first page cache; only missing page retried
    assert sync_db.outreach_mailboxes.docs[0]['delta_url'] == final


@pytest.mark.asyncio
async def test_inbound_dedup_preserves_same_account_reconnect_and_allows_other_account(sync_db, monkeypatch):
    from outreach.core.mailbox_sync import _apply_inbound
    from copy import deepcopy
    mailbox = sync_db.outreach_mailboxes.docs[0]
    received = datetime.now(timezone.utc)
    sync_db.outreach_email_operations.docs.append({'_id': 'op', 'workspace_id': 'w', 'sender_account_id': 'a',
        'status': 'accepted', 'accepted_at': received - timedelta(minutes=1), 'recipient': 'lead@example.com', 'lead_id': 'lead'})
    message = {'id': 'same-id', 'from': 'lead@example.com'}
    assert (await _apply_inbound(sync_db, mailbox, 'same-id', 'lead@example.com', received, message, kind='reply'))['status'] == 'possible_reply'
    reconnect = {**deepcopy(mailbox), 'connection_job_id': 'reconnect'}
    assert (await _apply_inbound(sync_db, reconnect, 'same-id', 'lead@example.com', received, message, kind='reply'))['status'] == 'duplicate'
    other = {**deepcopy(mailbox), 'email': 'other@example.com', 'provider_user_id': 'other-user'}
    assert (await _apply_inbound(sync_db, other, 'same-id', 'lead@example.com', received, message, kind='reply'))['status'] == 'possible_reply'
    assert len(sync_db.outreach_email_inbound_events.docs) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['gmail', 'microsoft'])
async def test_malformed_inbound_metadata_never_advances_complete_cursor(sync_db, monkeypatch, provider):
    from outreach.core import mailbox_sync_jobs as jobs
    client = http_reads(monkeypatch)
    if provider == 'gmail':
        client.get.side_effect = [httpx.Response(200, json={'historyId': '101', 'history': [
            {'messagesAdded': [{'message': {'id': 'broken'}}]}]}), httpx.Response(200, json={
                'id': 'broken', 'internalDate': 'not-a-date', 'payload': {'headers': [{'name': 'From', 'value': 'lead@example.com'}]}})]
    else:
        url = 'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=100'
        sync_db.outreach_mailboxes.docs[0].update(provider='microsoft', delta_url=url)
        client.get.return_value = httpx.Response(200, json={'value': [{'id': 'broken'}], '@odata.deltaLink': url + 'new'})
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    assert sync_db.outreach_mailboxes.docs[0]['sync_status'] == 'stale'
    assert sync_db.outreach_mailbox_sync_jobs.docs[0]['projected'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['owner', 'disable_after_permit'])
async def test_refresh_mutation_revalidates_sync_owner_after_async_secret_open(sync_db, monkeypatch, change):
    from outreach.core import mailbox_refresh as refresh, mailbox_sync_jobs as jobs, mailbox_connection as connection
    client = http_reads(monkeypatch)
    sync_db.outreach_mailboxes.docs[0]['token_expires_at'] = jobs.now() - timedelta(seconds=1)
    opened = refresh.open_mailbox_refresh
    async def opening(*args):
        value = await opened(*args)
        if change == 'owner': sync_db.outreach_mailbox_sync_jobs.docs[0]['owner'] = 'replacement'
        return value
    monkeypatch.setattr(refresh, 'open_mailbox_refresh', opening)
    if change == 'disable_after_permit':
        from outreach.core import suppression
        mutate = suppression.mutate_suppression
        async def disabled(*args):
            result = await mutate(*args)
            if args[-1].__name__ == 'authorize': monkeypatch.setenv('OUTREACH_EMAIL_SYNC_ENABLED', 'false')
            return result
        monkeypatch.setattr(suppression, 'mutate_suppression', disabled)
    job = await jobs.ensure_job(sync_db, 'w', 'a')
    assert (await jobs.execute_job(sync_db, 'w', job['_id']))['status'] == 'stale'
    client.post.assert_not_awaited(); client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_cli_review_is_sanitized_and_drain_phrase_is_exact(lifecycle, monkeypatch, capsys):
    from argparse import Namespace
    import json
    from outreach.ops.pilot import _run_db
    from tests.test_outreach_oauth_hold_review import seed_review
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false'); seed_review(lifecycle)
    await _run_db(Namespace(command='inspect-oauth-hold', workspace='w', job='job'), lifecycle)
    view = json.loads(capsys.readouterr().out)
    assert 'private-' not in str(view)
    args = Namespace(command='stop-oauth-hold', workspace='w', job='job', operator='operator',
        evidence='All OAuth and sender writers were drained before local stop.', review_digest=view['review_digest'], workers_drained='wrong')
    with pytest.raises(ValueError): await _run_db(args, lifecycle)
    args.workers_drained = 'I_PAUSED_AND_DRAINED_ALL_MAILBOX_AND_SENDER_WRITERS'
    await _run_db(args, lifecycle)
    assert json.loads(capsys.readouterr().out)['status'] == 'review_stopped'


@pytest.mark.asyncio
@pytest.mark.parametrize('original', ['same', 'other', 'ambiguous'])
async def test_legacy_inbound_collision_requires_proven_mailbox_identity(sync_db, original):
    from outreach.core.mailbox_sync import _apply_inbound, MailboxUnavailable
    mailbox = sync_db.outreach_mailboxes.docs[0]; received = datetime.now(timezone.utc)
    old = {'_id': 'old', 'workspace_id': 'w', 'sender_account_id': 'a', 'provider': 'gmail', 'sender_email': mailbox['email']}
    if original == 'other': old.update(provider='microsoft', sender_email='other@example.com')
    if original == 'ambiguous': old.pop('sender_email')
    sync_db.outreach_email_operations.docs.append(old)
    sync_db.outreach_email_operations.docs.append({'_id': 'current', 'workspace_id': 'w', 'sender_account_id': 'a',
        'status': 'accepted', 'accepted_at': received - timedelta(minutes=1), 'recipient': 'lead@example.com', 'lead_id': 'lead'})
    sync_db.outreach_email_inbound_events.docs.append({'workspace_id': 'w', 'sender_account_id': 'a',
        'provider_message_id': 'reused', 'operation_id': 'old'})
    call = _apply_inbound(sync_db, mailbox, 'reused', 'lead@example.com', received, {'id': 'reused'}, kind='reply')
    if original == 'ambiguous':
        with pytest.raises(MailboxUnavailable): await call
    else:
        assert (await call)['status'] == ('duplicate' if original == 'same' else 'possible_reply')
