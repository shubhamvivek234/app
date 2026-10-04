"""Actual snapshot/majority provider custody, refresh and migration boundaries."""
import asyncio
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid
import httpx
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from outreach.core import suppression, mailbox_connection as connection
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.provider_credential_migration import ProviderCredentialMigration
from outreach.core.provider_custody import prepare_mailbox_access, prepare_finder_key, open_mailbox_refresh
from outreach.core.dispatch_authority import AuthorityCollection
from tests.test_outreach_provider_migration import provider_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_mailbox_custody_integration import mailbox_db
pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Disposable local Mongo is opt-in')]

async def copy_mongo(source):
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27028',tz_aware=True,serverSelectionTimeoutMS=2000)
    db=client['test_unravler_provider_custody_'+uuid.uuid4().hex]
    for name,collection in source.collections.items():
        if collection.docs:await db[name].insert_many(collection.docs)
    return client,db

@pytest_asyncio.fixture
async def real_provider(provider_db):
    client,db=await copy_mongo(provider_db)
    try: yield db
    finally: await client.drop_database(db.name);client.close()

@pytest.mark.parametrize('kind',['mailbox','finder'])
async def test_conversion_and_actual_ttl_free_indexes(real_provider,monkeypatch,kind):
    db=real_provider; service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None
    view=await service.inspect('w',kind,sender)
    assert (await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True))['current_matches']
    if kind=='mailbox':
        row=await db.outreach_mailboxes.find_one({})
        assert (await prepare_mailbox_access(row,'w','a')).value=='old-access'
        assert row['connection_job_id']=='job' and row['history_id']=='cursor' and row['status']=='reauth_required'
    else: assert (await prepare_finder_key(await db.outreach_hunter_credentials.find_one({}),'w')).value=='private-hunter-key'
    from db.indexes import create_all_indexes
    monkeypatch.setenv('DB_NAME',db.name);await create_all_indexes(db.client)
    indexes=await db.outreach_credential_migrations.index_information()
    assert any(item['key']==[('workspace_id',1),('kind',1),('at',-1)] for item in indexes.values())
    assert not any('expireAfterSeconds' in item for item in indexes.values())

@pytest.mark.parametrize('kind',['mailbox','finder'])
async def test_receipt_failure_rolls_back_credentials(real_provider,monkeypatch,kind):
    from outreach.core.suppression import SuppressionCollection
    db=real_provider;service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None
    view=await service.inspect('w',kind,sender);insert=SuppressionCollection.insert_one
    async def fail(self,*args,**kwargs):
        if self.collection.name=='outreach_credential_migrations':raise RuntimeError('local interrupted receipt')
        return await insert(self,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'insert_one',fail)
    with pytest.raises(RuntimeError):await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True)
    collection=db.outreach_mailboxes if kind=='mailbox' else db.outreach_hunter_credentials
    assert (await collection.find_one({}))['access_token_enc' if kind=='mailbox' else 'api_key_enc'].startswith('gAAAA')
    assert not await db.outreach_credential_migrations.find_one({})

@pytest.mark.parametrize('kind',['mailbox','finder'])
@pytest.mark.parametrize('change',['mailbox','key','sender','permission','job','erasure','mode'])
async def test_replacement_during_key_work_denies_install(real_provider,monkeypatch,kind,change):
    from outreach.core import provider_credential_migration as module
    db=real_provider;service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None
    view=await service.inspect('w',kind,sender)
    name='seal_mailbox_tokens' if kind=='mailbox' else 'seal_finder_key';seal=getattr(module,name)
    async def changed(*args,**kwargs):
        result=await seal(*args,**kwargs)
        if change=='mailbox':await db.outreach_mailboxes.update_one({}, {'$set':{'history_id':'replacement'}})
        if change=='key':await db.outreach_hunter_credentials.update_one({}, {'$set':{'api_key_enc':'replacement'}})
        if change=='sender':await db.outreach_accounts.update_one({}, {'$set':{'status':'active'}})
        if change=='permission':await db.outreach_sender_execution.update_one({}, {'$set':{'permission.latched':False}})
        if change=='mode':monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
        if change in {'job','erasure'}:
            async def write(current):
                if change=='job':await current.outreach_mailbox_connection_jobs.insert_one({'workspace_id':'w','sender_account_id':'a','status':'queued'})
                else:await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'),{'$set':{'erasure_state':'requested'}})
            await suppression.mutate_suppression(db,'w',write)
        return result
    monkeypatch.setattr(module,name,changed)
    # A mailbox migration also captures all workspace mailbox authorities; a
    # separate finder-key change is outside mailbox scope and intentionally safe.
    if change=='key' and kind=='mailbox':
        assert (await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True))['current_matches']
    else:
        with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):
            await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True)
        assert not await db.outreach_credential_migrations.find_one({})

@pytest.mark.parametrize('kind',['mailbox','finder'])
@pytest.mark.parametrize('authority',['outreach_accounts','outreach_sender_execution','outreach_mailboxes'])
async def test_existing_authority_edit_after_read_denies_before_kms(real_provider,monkeypatch,kind,authority):
    db=real_provider;service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None
    view=await service.inspect('w',kind,sender);seen,release=asyncio.Event(),asyncio.Event();fence=AuthorityCollection.fence;paused=False
    async def pause(self,document,query):
        nonlocal paused
        if self.name==authority and not paused:paused=True;seen.set();await release.wait()
        await fence(self,document,query)
    monkeypatch.setattr(AuthorityCollection,'fence',pause)
    seal=AsyncMock(side_effect=AssertionError('No KMS'))
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_mailbox_tokens',seal)
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_finder_key',seal)
    task=asyncio.create_task(service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True))
    try:await asyncio.wait_for(seen.wait(),5);await db[authority].update_one({}, {'$set':{'operator_revision':'replacement'}})
    finally:release.set()
    with pytest.raises(CustodyUnavailable):await task
    seal.assert_not_awaited()

@pytest.mark.parametrize('kind',['mailbox','finder'])
async def test_lost_commit_ack_replays_metadata_only(real_provider,monkeypatch,kind):
    db=real_provider;service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None;mutate=suppression.mutate_suppression
    view=await service.inspect('w',kind,sender)
    async def lost(*args):
        result=await mutate(*args)
        if args[-1].__name__=='apply':raise TimeoutError('local lost response')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(TimeoutError):await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True)
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_mailbox_tokens',AsyncMock(side_effect=AssertionError('No replay')))
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_finder_key',AsyncMock(side_effect=AssertionError('No replay')))
    assert (await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True))['current_matches']
    assert await db.outreach_credential_migrations.count_documents({})==1

@pytest.mark.parametrize('lost_install_ack',[False,True])
async def test_refresh_bson_precision_and_committed_ack_loss(scoped,monkeypatch,lost_install_ack):
    from tests.test_outreach_mailbox_custody_integration import configured_app
    from outreach.core.oauth_app_custody import app_identity_digest
    source=await mailbox_db(monkeypatch,expired=True)
    config = await configured_app(monkeypatch)
    source.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    client,db=await copy_mongo(source)
    http=AsyncMock();http.post.return_value=httpx.Response(200,json={'access_token':'new-access','refresh_token':'new-refresh'})
    context=AsyncMock();context.__aenter__.return_value=http
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:context)
    class Clock:
        @staticmethod
        def now(_):return datetime.now(timezone.utc).replace(microsecond=123456)
    monkeypatch.setattr(connection,'datetime',Clock)
    mutate=suppression.mutate_suppression
    async def lost(*args):
        result=await mutate(*args)
        if args[-1].__name__=='install':raise TimeoutError('local lost install acknowledgement')
        return result
    if lost_install_ack:monkeypatch.setattr(suppression,'mutate_suppression',lost)
    try:
        row=await db.outreach_mailboxes.find_one({})
        if lost_install_ack:
            with pytest.raises(connection.MailboxUnavailable):await connection.get_mailbox_access_token(db,row)
            monkeypatch.setattr(suppression,'mutate_suppression',mutate)
        else:assert (await connection.get_mailbox_access_token(db,row)).secret.value=='new-access'
        saved=await db.outreach_mailboxes.find_one({})
        assert saved['token_expires_at'].microsecond==123000
        assert not saved.get('refresh_state') and not saved.get('refresh_lease_nonce')
        assert await open_mailbox_refresh(saved,'w','a')=='new-refresh'
        assert (await connection.get_mailbox_access_token(db,saved)).secret.value=='new-access'
        http.post.assert_awaited_once()
    finally:await client.drop_database(db.name);client.close()

async def test_actual_standalone_denies_both_migrations_and_finder_key_write_before_kms(provider_db,monkeypatch,tmp_path):
    import shutil,socket,subprocess
    from pymongo.errors import PyMongoError
    from fastapi import HTTPException
    from outreach.api.mailboxes import put_hunter_key,HunterKeyRequest
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    storage=tmp_path/'standalone';storage.mkdir()
    process=subprocess.Popen([shutil.which('mongod'),'--bind_ip','127.0.0.1','--port',str(port),'--dbpath',str(storage),'--logpath',str(storage/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient(f'mongodb://127.0.0.1:{port}',tz_aware=True,serverSelectionTimeoutMS=200)
    try:
        async with asyncio.timeout(10):
            while True:
                assert process.poll() is None
                try:await client.admin.command('ping');break
                except PyMongoError:await asyncio.sleep(.1)
        db=client['test_provider_standalone']
        for name,collection in provider_db.collections.items():
            if collection.docs:await db[name].insert_many(collection.docs)
        seal=AsyncMock(side_effect=AssertionError('No KMS calls'))
        monkeypatch.setattr('outreach.core.provider_credential_migration.seal_mailbox_tokens',seal)
        monkeypatch.setattr('outreach.core.provider_credential_migration.seal_finder_key',seal)
        for kind in ('mailbox','finder'):
            service=ProviderCredentialMigration(db);sender='a' if kind=='mailbox' else None;view=await service.inspect('w',kind,sender)
            with pytest.raises(suppression.SuppressionUnavailable):await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True)
        monkeypatch.setattr('outreach.core.provider_custody.seal_finder_key',seal);monkeypatch.setenv('OUTREACH_HUNTER_ENABLED','true')
        with pytest.raises(HTTPException) as exc:await put_hunter_key(HunterKeyRequest(api_key='dummy-local-key'),{'default_workspace_id':'w'},db)
        assert exc.value.status_code==503;seal.assert_not_awaited()
        await client.drop_database(db.name)
    finally:client.close();process.terminate();await asyncio.to_thread(process.wait,10)

@pytest.mark.parametrize('source',['email_send','email_find'])
@pytest.mark.parametrize('replace_cipher',[False,True,'mode_commit','environment_commit'])
async def test_final_physical_authorization_fences_current_provider_material_without_key_calls(scoped,monkeypatch,source,replace_cipher):
    from tests.test_outreach_provider_boundary import ready
    from outreach.core.provider_custody import seal_mailbox_tokens,seal_finder_key
    from outreach.core.provider_boundary import ProviderEnvelope,provider_generation
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.request_guard import RequestDenied,request_parent
    memory,_,binding=await ready(monkeypatch,source=source)
    if source=='email_send':
        resource=memory.outreach_mailboxes.docs[0];resource['token_expires_at']=datetime.now(timezone.utc)+timedelta(hours=1)
        resource.update(await seal_mailbox_tokens({'access_token':'private-access','refresh_token':'private-refresh'},resource,'w','a'))
        prepared=await prepare_mailbox_access(resource,'w','a')
    else:
        resource=memory.outreach_hunter_credentials.docs[0];resource.update(await seal_finder_key('private-finder','w'))
        prepared=await prepare_finder_key(resource,'w')
    client,db=await copy_mongo(memory)
    try:
        monkeypatch.setattr('outreach.core.provider_boundary.get_ready_mailbox',lambda current,*args:current.outreach_mailboxes.find_one({'workspace_id':'w','sender_account_id':'a'}))
        account=await db.outreach_accounts.find_one({'id':'a'})
        await ExecutionPermission(db).grant('w','a',provider_generation(account,resource,source),[source],'operator',clear_latch=True)
        envelope=ProviderEnvelope(db,'w','a',account,source,resource,operation_id='l:n',lead_id='l')
        if source=='email_send':envelope.bind_mailbox(prepared)
        else:envelope.finder_handle='person';envelope.bind_finder(prepared)
        monkeypatch.setattr(scoped,'open',AsyncMock(side_effect=AssertionError('No key work in transaction')))
        factory=AsyncMock(return_value=httpx.Response(200,json={'id':'message','data':{'email':None}}))
        if replace_cipher in {'mode_commit','environment_commit'}:
            from outreach.core.dispatch_authority import DispatchAuthority
            authorize=DispatchAuthority.authorize
            async def changed_after_commit(self,*args,**kwargs):
                result=await authorize(self,*args,**kwargs)
                monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE' if replace_cipher=='mode_commit' else 'OUTREACH_CUSTODY_ENVIRONMENT_ID',
                    'legacy_fernet' if replace_cipher=='mode_commit' else 'replacement-environment')
                return result
            monkeypatch.setattr(DispatchAuthority,'authorize',changed_after_commit)
            with request_parent('owner',AsyncMock(return_value=None),approval_binding=binding,transaction_validator=AsyncMock(return_value=None)):
                with pytest.raises(RequestDenied):await envelope.call('POST' if source=='email_send' else 'GET',envelope.endpoint,factory,action='email' if source=='email_send' else 'finder')
            factory.assert_not_awaited()
        elif replace_cipher:
            fence=AuthorityCollection.fence;seen,release=asyncio.Event(),asyncio.Event();paused=False
            collection='outreach_mailboxes' if source=='email_send' else 'outreach_hunter_credentials'
            async def pause(self,document,query):
                nonlocal paused
                if self.name==collection and not paused:paused=True;seen.set();await release.wait()
                await fence(self,document,query)
            monkeypatch.setattr(AuthorityCollection,'fence',pause)
            with request_parent('owner',AsyncMock(return_value=None),approval_binding=binding,transaction_validator=AsyncMock(return_value=None)):
                task=asyncio.create_task(envelope.call('POST' if source=='email_send' else 'GET',envelope.endpoint,factory,action='email' if source=='email_send' else 'finder'))
                try:await asyncio.wait_for(seen.wait(),5);await db[collection].update_one({}, {'$set':{'access_token_enc' if source=='email_send' else 'api_key_enc':'replacement'}})
                finally:release.set()
                with pytest.raises(RequestDenied):await task
            factory.assert_not_awaited()
        else:
            with request_parent('owner',AsyncMock(return_value=None),approval_binding=binding,transaction_validator=AsyncMock(return_value=None)):
                await envelope.call('POST' if source=='email_send' else 'GET',envelope.endpoint,factory,action='email' if source=='email_send' else 'finder')
            factory.assert_awaited_once()
            assert (await db.outreach_physical_requests.find_one({})).get('dispatch_authorization')
    finally:await client.drop_database(db.name);client.close()

@pytest.mark.parametrize('state',['possible','unknown'])
async def test_erasure_retains_minimal_refresh_uncertainty_without_secrets(real_provider,state):
    from outreach.core.erasure import OutreachErasure
    db=real_provider
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'user'})
    await db.outreach_mailboxes.update_one({}, {'$set':{'refresh_state':state,'refresh_lease_nonce':'nonce','status':'active'}})
    service=OutreachErasure(db);await service.request('w','user')
    assert not (await db.outreach_mailboxes.find_one({})).get('refresh_token_enc')
    view=await service.inspect('w')
    await service.finish('w','operator','All actual workspace writers and caches stopped for drained review.',workers_drained=True,expected_digest=view['review_digest'])
    hold=await db.outreach_erasure_holds.find_one({'source_collection':'outreach_mailboxes'})
    assert hold['operation_kind']=='oauth_refresh' and hold['outcome_state']==state and hold['kind']=='unresolved_submission'
    assert 'old-access' not in str(hold) and 'sender@example' not in str(hold) and 'nonce' not in str(hold)
    assert not await db.outreach_mailboxes.find_one({})
    assert not any('expireAfterSeconds' in item for item in (await db.outreach_erasure_holds.index_information()).values())

@pytest.mark.parametrize('operation',['refresh','read','oauth'])
async def test_paid_term_expiry_during_commit_denies_control_transport(scoped,monkeypatch,operation):
    from outreach.core.provider_custody import seal_oauth_secret
    from tests.test_outreach_mailbox_custody_integration import configured_app
    from outreach.core.oauth_app_custody import app_configuration_digest, app_identity_digest
    source=await mailbox_db(monkeypatch,expired=operation=='refresh')
    config = await configured_app(monkeypatch)
    source.outreach_mailboxes.docs[0]['oauth_app_identity_digest'] = app_identity_digest(config)
    client,db=await copy_mongo(source)
    from outreach.core.paid_access import get_active_entitlement
    # Restore production paid authorization: snapshot fences must remember the
    # paid term, which the other focused custody fixtures deliberately stub.
    async def actual_paid(current,workspace,sender):
        return bool(await get_active_entitlement(current,workspace))
    monkeypatch.setattr(connection,'_paid_sender',actual_paid)
    await db.outreach_entitlements.insert_one({'workspace_id':'w','status':'active','seats':1,'payment_source':'manual_verified_invoice',
        'paid_through':datetime.now(timezone.utc)+timedelta(hours=1)})
    http=AsyncMock();context=AsyncMock();context.__aenter__.return_value=http
    monkeypatch.setattr(connection.httpx,'AsyncClient',lambda **_:context)
    mutate=suppression.mutate_suppression
    async def expired_after_commit(*args):
        result=await mutate(*args)
        if args[-1].__name__ in {'authorize','check'}:
            class Later:
                @staticmethod
                def now(_):return datetime.now(timezone.utc)+timedelta(hours=2)
            monkeypatch.setattr(connection,'datetime',Later)
        return result
    try:
        if operation=='oauth':
            job={'id':'job','workspace_id':'w','sender_account_id':'a','provider':'gmail','status':'queued',
                'authorization_expires_at':datetime.now(timezone.utc)+timedelta(hours=3)}
            job['app_config_digest'] = app_configuration_digest(config)
            job['authorization_code_enc']=await seal_oauth_secret('code',job,'w','a','oauth_code')
            job['code_verifier_enc']=await seal_oauth_secret('pkce',job,'w','a','oauth_pkce')
            await db.outreach_mailbox_connection_jobs.insert_one(job)
            monkeypatch.setattr(suppression,'mutate_suppression',expired_after_commit)
            assert (await connection.complete_connection_job(db,'w','job'))['status']=='review_required'
            assert (await db.outreach_mailbox_connection_jobs.find_one({'workspace_id':'w','id':'job'}))['exchange_state']=='unknown'
        else:
            token=None
            if operation=='read':token=await connection.get_mailbox_access_token(db,await db.outreach_mailboxes.find_one({}))
            monkeypatch.setattr(suppression,'mutate_suppression',expired_after_commit)
            with pytest.raises(connection.MailboxUnavailable if operation=='refresh' else CustodyUnavailable):
                if operation=='refresh':await connection.get_mailbox_access_token(db,await db.outreach_mailboxes.find_one({}))
                else:await token.authorize()
        http.post.assert_not_awaited();http.get.assert_not_awaited()
    finally:await client.drop_database(db.name);client.close()
