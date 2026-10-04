"""Production credential paths with fake key and provider services."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from unittest.mock import AsyncMock
import httpx
import pytest
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped
from outreach.core.provider_custody import seal_mailbox_tokens, MailboxAccess, open_mailbox_refresh
from outreach.core import mailbox_connection as connection
from outreach.core.oauth_app_custody import seal_app_secret, app_configuration_digest, app_identity_digest

async def configured_app(monkeypatch, provider='gmail'):
    encrypted = await seal_app_secret('private-app-secret', provider, 'local', 'app-generation')
    config = connection.ProviderConfig(provider, 'local', encrypted, 'https://local.invalid/callback',
        'https://accounts.google.com/authorize', 'https://local.invalid/token', (), 'app-generation')
    monkeypatch.setattr(connection, '_provider_config', lambda _: config)
    return config

async def mailbox_db(monkeypatch, *, provider='gmail', expired=False):
    monkeypatch.setenv('OUTREACH_MAILBOX_CONNECTION_ENABLED', 'true')
    row={'workspace_id':'w','sender_account_id':'a','provider':provider,'provider_user_id':'u','email':'sender@example.com',
        'connection_job_id':'job','status':'active','sync_status':'healthy','last_sync_at':datetime.now(timezone.utc),
        'token_expires_at':datetime.now(timezone.utc)+timedelta(seconds=-1 if expired else 3600)}
    row.update(await seal_mailbox_tokens({'access_token':'old-access','refresh_token':'private-refresh'},row,'w','a'))
    monkeypatch.setattr(connection,'_paid_sender',AsyncMock(return_value=True))
    return Database(outreach_mailboxes=[row])

@pytest.mark.asyncio
async def test_ready_token_is_prepared_and_does_not_use_http(scoped,monkeypatch):
    db=await mailbox_db(monkeypatch)
    client=AsyncMock(side_effect=AssertionError('No refresh'))
    monkeypatch.setattr(connection.httpx,'AsyncClient',client)
    token=await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))
    assert isinstance(token,MailboxAccess) and token.secret.value=='old-access'
    client.assert_not_called()

@pytest.mark.asyncio
@pytest.mark.parametrize('provider,rotated',[('gmail',True),('microsoft',False)])
async def test_rotated_or_retained_refresh_token_reseals_without_changing_connection_identity(scoped,monkeypatch,provider,rotated):
    from types import SimpleNamespace
    db=await mailbox_db(monkeypatch,provider=provider,expired=True); old=deepcopy(db.outreach_mailboxes.docs[0])
    config = await configured_app(monkeypatch, provider)
    db.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    response={'access_token':'new-access','expires_in':3600,**({'refresh_token':'new-refresh'} if rotated else {})}
    client=AsyncMock();client.post.return_value=httpx.Response(200,json=response)
    ctx=AsyncMock();ctx.__aenter__.return_value=client
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:ctx)
    token=await connection.get_mailbox_access_token(db,old)
    current=db.outreach_mailboxes.docs[0]
    assert token.secret.value=='new-access' and token.secret.matches(current,'w','a')
    assert current['connection_job_id']=='job' and current['custody_generation']==old['custody_generation']
    assert await open_mailbox_refresh(current,'w','a')==('new-refresh' if rotated else 'private-refresh')
    assert not current.get('refresh_lease_nonce') and not current.get('refresh_state')

@pytest.mark.asyncio
async def test_refresh_timeout_holds_outcome_and_never_retries_provider(scoped,monkeypatch):
    from types import SimpleNamespace
    db=await mailbox_db(monkeypatch,expired=True)
    config = await configured_app(monkeypatch)
    db.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    client=AsyncMock();client.post.side_effect=httpx.ReadTimeout('local timeout')
    ctx=AsyncMock();ctx.__aenter__.return_value=client
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:ctx)
    with pytest.raises(connection.MailboxUnavailable): await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))
    current=db.outreach_mailboxes.docs[0]; assert current['refresh_state']=='unknown'
    current['refresh_lease_until']=datetime.now(timezone.utc)-timedelta(days=1)
    with pytest.raises(connection.MailboxUnavailable): await connection.get_mailbox_access_token(db,deepcopy(current))
    client.post.assert_awaited_once()
    assert 'local timeout' not in str(current)

@pytest.mark.asyncio
async def test_replacement_during_access_open_cannot_escape_as_current_token(scoped,monkeypatch):
    db=await mailbox_db(monkeypatch); opening=scoped.open
    async def replace(*args):
        db.outreach_mailboxes.docs[0]['connection_job_id']='replacement'
        return await opening(*args)
    monkeypatch.setattr(scoped,'open',replace)
    with pytest.raises(connection.MailboxUnavailable): await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))

@pytest.mark.asyncio
async def test_oauth_start_pkce_and_callback_code_have_job_scoped_custody(scoped,monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import urlparse,parse_qs
    from outreach.core.provider_custody import open_oauth_secret
    db=await mailbox_db(monkeypatch)
    monkeypatch.setattr(connection,'is_mailbox_pilot_allowed',lambda _:True)
    monkeypatch.setattr(connection,'get_active_entitlement',AsyncMock(return_value={'seats':1}))
    await configured_app(monkeypatch)
    monkeypatch.setattr(connection,'_expire_abandoned_connection_jobs',AsyncMock())
    result=await connection.start_mailbox_connection(db,'w','user','a','gmail')
    state=db.outreach_mailbox_oauth_states.docs[0]; job=db.outreach_mailbox_connection_jobs.docs[0]
    assert state['code_verifier_enc'].startswith('uc1:')
    verifier=await open_oauth_secret(state['code_verifier_enc'],job,'w','a','oauth_pkce')
    query=parse_qs(urlparse(result['authorization_url']).query)
    assert connection._pkce_challenge(verifier)==query['code_challenge'][0]
    monkeypatch.setattr(connection,'enqueue_connection_job',lambda *_:None)
    await connection.consume_oauth_callback(db,'gmail',query['state'][0],'private-code',browser_binding_nonce=result['browser_binding_nonce'])
    assert job['id']==db.outreach_mailbox_connection_jobs.docs[0]['id']
    queued=db.outreach_mailbox_connection_jobs.docs[0]
    assert queued['status']=='queued' and queued['authorization_code_enc'].startswith('uc1:')
    assert await open_oauth_secret(queued['authorization_code_enc'],queued,'w','a','oauth_code')=='private-code'
    assert not db.outreach_mailbox_oauth_states.docs

@pytest.mark.asyncio
async def test_connection_installs_scoped_tokens_with_guarded_exact_job_and_identity(scoped,monkeypatch):
    from types import SimpleNamespace
    db=await mailbox_db(monkeypatch);db.outreach_mailboxes.docs.clear()
    job={'id':'new-job','workspace_id':'w','sender_account_id':'a','provider':'gmail','status':'queued',
        'authorization_expires_at':datetime.now(timezone.utc)+timedelta(minutes=10)}
    db.outreach_mailbox_connection_jobs.docs.append(job)
    config = await configured_app(monkeypatch)
    job['app_config_digest'] = app_configuration_digest(config)
    monkeypatch.setattr(connection,'_token_exchange',AsyncMock(return_value={'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600,'scope':'send read'}))
    monkeypatch.setattr(connection,'_mailbox_identity',AsyncMock(return_value={'email':'sender@example.com','provider_user_id':'u','history_id':'cursor'}))
    monkeypatch.setattr('outreach.core.mailbox_sync.bootstrap_mailbox_sync',AsyncMock(return_value={'status':'healthy'}))
    assert (await connection.complete_connection_job(db,'w','new-job'))['status']=='connected'
    installed=db.outreach_mailboxes.docs[0]
    assert installed['access_token_enc'].startswith('uc1:') and installed['refresh_token_enc'].startswith('uc1:')
    assert installed['custody_generation'] and installed['connection_job_id']=='new-job'

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['pilot','shutdown','expired','cipher','status','environment'])
async def test_prepared_sync_read_refuses_current_authorization_changes(scoped,monkeypatch,change):
    from outreach.core import mailbox_sync
    from outreach.core.credential_custody import CustodyUnavailable
    db=await mailbox_db(monkeypatch)
    token=await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))
    row=db.outreach_mailboxes.docs[0]
    if change=='pilot':monkeypatch.setenv('OUTREACH_MAILBOX_CONNECTION_ENABLED','false')
    if change=='shutdown':monkeypatch.setattr(connection,'is_shutting_down',lambda:True)
    if change=='expired':row['token_expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    if change=='cipher':row['access_token_enc']='replacement'
    if change=='status':row['status']='disconnected'
    if change=='environment':monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','other-environment')
    client=AsyncMock();context=AsyncMock();context.__aenter__.return_value=client
    monkeypatch.setattr(mailbox_sync.httpx,'AsyncClient',lambda **_:context)
    with pytest.raises(CustodyUnavailable):await mailbox_sync._provider_get(mailbox_sync.GMAIL_BASE+'/history',token)
    client.get.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['cancel','malformed','rejected','key_unavailable','pilot_after_open','lease_after_commit'])
async def test_refresh_terminal_or_uncertain_states_never_erase_replacement_auth(scoped,monkeypatch,failure):
    import asyncio
    from types import SimpleNamespace
    from outreach.core import mailbox_refresh
    db=await mailbox_db(monkeypatch,expired=True)
    config = await configured_app(monkeypatch)
    db.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    client=AsyncMock();client.post.return_value=httpx.Response(200,json={'access_token':'new'})
    if failure=='cancel':client.post.side_effect=asyncio.CancelledError
    if failure=='malformed':client.post.return_value=httpx.Response(200,json={'access_token':None})
    if failure=='rejected':client.post.return_value=httpx.Response(401)
    if failure=='key_unavailable':monkeypatch.setattr(mailbox_refresh,'seal_mailbox_tokens',AsyncMock(side_effect=ValueError('local key unavailable')))
    if failure=='pilot_after_open':
        opening=mailbox_refresh.open_mailbox_refresh
        async def revoke(*args):
            value=await opening(*args);monkeypatch.setenv('OUTREACH_MAILBOX_CONNECTION_ENABLED','false');return value
        monkeypatch.setattr(mailbox_refresh,'open_mailbox_refresh',revoke)
    context=AsyncMock();context.__aenter__.return_value=client
    if failure=='lease_after_commit':
        async def delayed_enter():
            class Later:
                @staticmethod
                def now(_):return datetime.now(timezone.utc)+timedelta(seconds=60)
            monkeypatch.setattr(connection,'datetime',Later);return client
        context.__aenter__.side_effect=delayed_enter
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:context)
    with pytest.raises(asyncio.CancelledError if failure=='cancel' else connection.MailboxUnavailable):
        await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))
    row=db.outreach_mailboxes.docs[0]
    if failure=='rejected':
        assert row['refresh_state']=='rejected' and not row.get('access_token_enc') and not row.get('refresh_lease_nonce')
    else:
        assert row['refresh_state'] in {'possible','unknown'} and row.get('refresh_lease_nonce')
        assert row['access_token_enc'].startswith('uc1:')
    if failure in {'pilot_after_open','lease_after_commit'}:client.post.assert_not_awaited()
    else:client.post.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('source',['email_send','email_find'])
async def test_real_provider_adapter_uses_opened_secret_and_exact_scope_without_replay(scoped,monkeypatch,source):
    from tests.test_outreach_provider_boundary import ready
    from tests.test_outreach_mailboxes import _send_fixture
    from outreach.core.provider_custody import seal_finder_key
    from outreach.core.email_finder import find_lead_email
    from outreach.core.provider_boundary import provider_generation
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.request_guard import request_parent
    db,_,binding=await ready(monkeypatch,source=source)
    monkeypatch.setenv('OUTREACH_MAILBOX_CONNECTION_ENABLED','true')
    monkeypatch.setattr(connection,'_paid_sender',AsyncMock(return_value=True))
    if source=='email_send':
        row=db.outreach_mailboxes.docs[0];row['token_expires_at']=datetime.now(timezone.utc)+timedelta(hours=1)
        row.update(await seal_mailbox_tokens({'access_token':'private-access','refresh_token':'private-refresh'},row,'w','a'))
        monkeypatch.setattr('outreach.core.mailbox_delivery.get_ready_mailbox',AsyncMock(return_value=row))
    else:
        db.outreach_hunter_credentials.docs[0].update(await seal_finder_key('private-finder','w'))
        await ExecutionPermission(db).grant('w','a',provider_generation(db.outreach_accounts.docs[0],db.outreach_hunter_credentials.docs[0],source),[source],'operator',clear_latch=True)
    client=AsyncMock();client.post.return_value=httpx.Response(200,json={'id':'message','threadId':'thread'})
    client.get.return_value=httpx.Response(200,json={'data':{'email':'lead@example.com','source_type':'found','verification':{'status':'valid'}}})
    context=AsyncMock();context.__aenter__.return_value=client
    monkeypatch.setattr(httpx,'AsyncClient',lambda **_:context)
    async def invoke():
        if source=='email_send':return await _send_fixture(db,binding)
        with request_parent('owner',AsyncMock(return_value=None)):
            return await find_lead_email(db,workspace_id='w',sender_account_id='a',lead_id='l',operation_id='l:n')
    assert (await invoke())['status']==('accepted' if source=='email_send' else 'found')
    monkeypatch.setattr(scoped,'open',AsyncMock(side_effect=AssertionError('No reopen for committed outcome')))
    assert (await invoke())['status']==('accepted' if source=='email_send' else 'found')
    if source=='email_send':
        client.post.assert_awaited_once();assert client.post.await_args.kwargs['headers']['Authorization']=='Bearer private-access'
    else:
        client.get.assert_awaited_once();assert client.get.await_args.kwargs['params']['api_key']=='private-finder'
    assert 'private-access' not in str(db.outreach_physical_requests.docs) and 'private-finder' not in str(db.outreach_physical_requests.docs)

@pytest.mark.asyncio
@pytest.mark.parametrize('mode_change',['mode','environment'])
@pytest.mark.parametrize('operation',['refresh','oauth'])
async def test_custody_configuration_change_after_authorization_prevents_control_http(scoped,monkeypatch,mode_change,operation):
    from outreach.core.provider_custody import seal_oauth_secret
    from types import SimpleNamespace
    db=await mailbox_db(monkeypatch,expired=True)
    config = await configured_app(monkeypatch)
    db.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    http=AsyncMock();context=AsyncMock()
    async def changed_enter():
        monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE' if mode_change=='mode' else 'OUTREACH_CUSTODY_ENVIRONMENT_ID',
            'legacy_fernet' if mode_change=='mode' else 'replacement-environment')
        return http
    context.__aenter__.side_effect=changed_enter
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:context)
    job={'id':'job','workspace_id':'w','sender_account_id':'a','provider':'gmail','authorization_expires_at':datetime.now(timezone.utc)+timedelta(minutes=10)}
    job['app_config_digest'] = app_configuration_digest(config)
    job['authorization_code_enc']=await seal_oauth_secret('private-code',job,'w','a','oauth_code')
    job['code_verifier_enc']=await seal_oauth_secret('private-pkce',job,'w','a','oauth_pkce')
    with pytest.raises(connection.MailboxUnavailable):
        if operation=='refresh':await connection.get_mailbox_access_token(db,deepcopy(db.outreach_mailboxes.docs[0]))
        else:await connection._token_exchange(config,job,preflight=AsyncMock())
    http.post.assert_not_awaited()
