"""Real transactions, default BSON and exact receipt recovery for proxy conversion."""
import asyncio
from contextvars import ContextVar
from copy import deepcopy
import os
import uuid
from unittest.mock import AsyncMock

from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import pytest_asyncio

from outreach.core import proxy_migration as migration, suppression
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityCollection
from outreach.core.erasure import OutreachErasure
from outreach.core.webshare_provisioning import import_webshare_proxy, managed_webshare_valid
from outreach.core.sender_execution import SenderExecution
from tests.test_outreach_webshare_migration import scoped, ASSET, EVIDENCE, convert

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


@pytest_asyncio.fixture
async def real_webshare(scoped,monkeypatch):
    from datetime import datetime, timedelta, timezone
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_INTEGRATIONS_ENABLED',
                 'OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag,'false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27028',serverSelectionTimeoutMS=2000)
    db=client['test_webshare_migration_'+uuid.uuid4().hex]
    try:
        await import_webshare_proxy(db,proxy_url='http://operator:private-password@191.116.125.248:12323',
            country_code='IN',plan_id='plan',resource_id='resource',provider_order_id='order',
            workspace_id='w',expires_at=datetime.now(timezone.utc)+timedelta(days=30),
            verified_by='operator',evidence_digest='a'*64,dedicated_isp_confirmed=True)
        row=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
        proxy={key:row[key] for key in ('provider','host','port','username','password_enc',
            'country_code','credential_generation','custody_workspace_id')}|{'proxy_id':ASSET}
        await db.outreach_proxy_leases.insert_one({'_id':ASSET,'workspace_id':'w','sender_id':'a',
            'provider':'webshare_plan','country_code':'IN','reservation_job_id':'original'})
        await db.outreach_accounts.insert_one({'workspace_id':'w','id':'a','status':'paused',
            'proxy':deepcopy(proxy),'proxy_config':deepcopy(proxy),'credential_generation':'cookie-original'})
        await db.outreach_sender_execution.insert_one({**SenderExecution.scope('w','a'),'status':'idle',
            'permission':{'latched':True}})
        await db.workspaces.insert_one({'workspace_id':'w','owner_id':'human'})
        monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
        yield db
    finally:
        await client.drop_database(db.name);client.close()


async def test_default_bson_atomic_conversion_indexes_and_no_transaction_key_work(real_webshare,scoped,monkeypatch):
    db=real_webshare; before=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert before['expires_at'].tzinfo is None
    inside=ContextVar('webshare_migration_inside',default=False)
    mutate=suppression.mutate_suppression;seal=scoped.seal
    async def guarded(db,workspace,operation):
        async def run(current):
            token=inside.set(True)
            try:return await operation(current)
            finally:inside.reset(token)
        return await mutate(db,workspace,run)
    async def key(*args,**kwargs):
        assert not inside.get();return await seal(*args,**kwargs)
    monkeypatch.setattr(suppression,'mutate_suppression',guarded);monkeypatch.setattr(scoped,'seal',key)
    result=await convert(db)
    after=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    assert result['current_matches'] and await managed_webshare_valid(db,after,'w')
    assert before['import_basis_digest']==after['import_basis_digest'] and before['expires_at']==after['expires_at']
    from db.indexes import create_all_indexes
    await db.outreach_credential_migrations.create_index('at',expireAfterSeconds=60,name='unsafe_old_ttl')
    monkeypatch.setenv('DB_NAME',db.name);await create_all_indexes(db.client)
    assert all('expireAfterSeconds' not in row for row in (await db.outreach_credential_migrations.index_information()).values())
    assert all('expireAfterSeconds' not in row for row in (await db.account_proxy_ip_guards.index_information()).values())
    assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['credential_generation']=='cookie-original'


@pytest.mark.parametrize('target',['outreach_accounts','outreach_credential_migrations'])
async def test_projection_failure_rolls_back_inventory_and_both_aliases(real_webshare,monkeypatch,target):
    db=real_webshare;before=await db.outreach_proxy_inventory.find_one({'_id':ASSET})
    from outreach.core.suppression import SuppressionCollection
    update,insert=SuppressionCollection.update_one,SuppressionCollection.insert_one
    async def fail_update(self,*args,**kwargs):
        if self.collection.name==target:raise RuntimeError('Owned projection failure')
        return await update(self,*args,**kwargs)
    async def fail_insert(self,*args,**kwargs):
        if self.collection.name==target:raise RuntimeError('Owned receipt failure')
        return await insert(self,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',fail_update)
    monkeypatch.setattr(SuppressionCollection,'insert_one',fail_insert)
    with pytest.raises(RuntimeError):await convert(db)
    assert (await db.outreach_proxy_inventory.find_one({'_id':ASSET}))['password_enc']==before['password_enc']
    account=await db.outreach_accounts.find_one({'workspace_id':'w'})
    assert account['proxy']['password_enc']==account['proxy_config']['password_enc']==before['password_enc']
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})


@pytest.mark.parametrize('change',['basis','guard','lease','alias','policy','closed'])
async def test_change_while_sealing_denies_without_overwriting_replacement(real_webshare,monkeypatch,change):
    db=real_webshare;seal=migration.seal_proxy_password
    async def changed(*args,**kwargs):
        result=await seal(*args,**kwargs)
        if change=='basis':await db.outreach_proxy_inventory.update_one({'_id':ASSET},{'$set':{'provider_order_id':'replacement'}})
        if change=='guard':await db.account_proxy_ip_guards.update_one({}, {'$set':{'binding_digest':'replacement'}})
        if change=='lease':await db.outreach_proxy_leases.update_one({'_id':ASSET},{'$set':{'sender_id':'replacement'}})
        if change=='alias':await db.outreach_accounts.update_one({'workspace_id':'w'},{'$set':{'proxy_config.username':'replacement'}})
        if change=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
        if change=='closed':
            async def stop(current):
                await current.outreach_suppression_guards.update_one(suppression.guard_scope('w'),{'$set':{'erasure_state':'requested'}})
            await suppression.mutate_suppression(db,'w',stop)
        return result
    monkeypatch.setattr(migration,'seal_proxy_password',changed)
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):await convert(db)
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    assert (await db.outreach_proxy_inventory.find_one({'_id':ASSET}))['password_enc'].startswith('gAAAAA')


async def test_guarded_concurrent_completion_wins_before_stale_source_and_second_key_call(real_webshare,monkeypatch):
    db=real_webshare;view=await migration.ProxyMigration(db).inspect('w',ASSET)
    mutate=suppression.mutate_suppression;seal=migration.seal_proxy_password
    arrived,release=asyncio.Event(),asyncio.Event();paused=False;calls=0
    async def delayed(db,workspace,callback):
        nonlocal paused
        if not paused:
            paused=True;arrived.set();await release.wait()
        return await mutate(db,workspace,callback)
    async def counted(*args,**kwargs):
        nonlocal calls
        calls+=1;return await seal(*args,**kwargs)
    monkeypatch.setattr(suppression,'mutate_suppression',delayed);monkeypatch.setattr(migration,'seal_proxy_password',counted)
    late=asyncio.create_task(convert(db,view));await asyncio.wait_for(arrived.wait(),5)
    first=await convert(db,view);release.set()
    assert await asyncio.wait_for(late,5)==first and calls==1
    assert await db.outreach_credential_migrations.count_documents({'workspace_id':'w'})==1


async def test_lost_commit_ack_recovers_exact_metadata_without_secret_work(real_webshare,monkeypatch):
    db=real_webshare;view=await migration.ProxyMigration(db).inspect('w',ASSET);mutate=suppression.mutate_suppression
    count=0
    async def unknown(db,workspace,callback):
        nonlocal count
        count+=1;result=await mutate(db,workspace,callback)
        if count==2:raise RuntimeError('Owned lost commit acknowledgement')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',unknown)
    with pytest.raises(RuntimeError):await convert(db,view)
    monkeypatch.setattr(migration,'seal_proxy_password',AsyncMock(side_effect=AssertionError('No reseal')))
    monkeypatch.setattr(migration,'decrypt_strict',lambda *a:(_ for _ in ()).throw(AssertionError('No open')))
    assert (await convert(db,view))['current_matches']
    assert await db.outreach_credential_migrations.count_documents({'workspace_id':'w'})==1


async def test_authority_replacement_after_snapshot_read_denies_before_key_call(real_webshare,monkeypatch):
    db=real_webshare;view=await migration.ProxyMigration(db).inspect('w',ASSET)
    arrived,release=asyncio.Event(),asyncio.Event();fence=AuthorityCollection.fence;paused=False
    async def delayed(self,document,query):
        nonlocal paused
        if self.name=='outreach_proxy_leases' and not paused:
            paused=True;arrived.set();await release.wait()
        await fence(self,document,query)
    monkeypatch.setattr(AuthorityCollection,'fence',delayed)
    seal=AsyncMock(side_effect=AssertionError('No key call'));monkeypatch.setattr(migration,'seal_proxy_password',seal)
    work=asyncio.create_task(convert(db,view));await asyncio.wait_for(arrived.wait(),5)
    await db.outreach_proxy_leases.update_one({'_id':ASSET},{'$set':{'sender_id':'replacement'}})
    release.set()
    with pytest.raises(CustodyUnavailable):await asyncio.wait_for(work,5)
    seal.assert_not_awaited()


async def test_erasure_retains_only_migration_provenance_and_permanent_ip_claim(real_webshare,monkeypatch):
    db=real_webshare;await convert(db);receipt=await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    before=await db.account_proxy_ip_guards.find_one({})
    service=OutreachErasure(db);await service.request('w','human')
    inspected=await service.inspect('w')
    await service.finish('w','operator','All workspace API workers credential writers and caches were drained.',
        workers_drained=True,expected_digest=inspected['review_digest'])
    assert not await db.outreach_credential_migrations.find_one({'workspace_id':'w'})
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'proxy_custody_migration'})
    assert hold['before_digest']==receipt['before_digest'] and hold['after_digest']==receipt['after_digest']
    assert hold['operator_digest']==receipt['operator_digest'] and hold['evidence_digest']==EVIDENCE
    assert hold['activation_allowed'] is False
    for secret in ('private-password','gAAAAA','uc1:','191.116.125.248','cookie-original'):
        assert secret not in str(hold)
    assert await db.account_proxy_ip_guards.find_one({})==before
    seal=AsyncMock(side_effect=AssertionError('No key work'));monkeypatch.setattr(migration,'seal_proxy_password',seal)
    with pytest.raises((CustodyUnavailable,suppression.SuppressionUnavailable)):
        await convert(db,{'digest':receipt['before_digest']})
    seal.assert_not_awaited()
