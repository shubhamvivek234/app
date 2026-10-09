"""Owned real Mongo checks for physical exclusion, reservation and installation."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import os
import uuid
from unittest.mock import AsyncMock

from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import pytest_asyncio
from pymongo.errors import DuplicateKeyError

from outreach.core import suppression, proxy_custody
from outreach.core.connection_repair import ConnectionRepair
from outreach.core.managed_proxy import reserve_sender_proxy, import_iproyal_proxy
from outreach.core.paid_access import sender_is_ready, record_verified_payment
from outreach.core.webshare_provisioning import import_webshare_proxy, managed_webshare_valid
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_dispatch_authority import ready_db, dispatch
from db.indexes import ensure_managed_proxy_indexes, remove_other_evidence_ttls

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


@pytest_asyncio.fixture
async def managed_db(monkeypatch):
    from cryptography.fernet import Fernet
    from utils import encryption
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_managed_webshare_' + uuid.uuid4().hex]
    try:
        await db.workspaces.insert_many([{'workspace_id':'w','owner_id':'human'}, {'workspace_id':'other','owner_id':'other-human'}])
        await ensure_managed_proxy_indexes(db)
        yield db
    finally:
        await client.drop_database(db.name); client.close()


def args(**changes):
    result = dict(proxy_url='http://operator:private@191.116.125.248:12323', country_code='IN',
        plan_id='plan', resource_id='resource', provider_order_id='order', workspace_id='w',
        expires_at=datetime.now(timezone.utc)+timedelta(days=30), verified_by='operator',
        evidence_digest='a'*64, dedicated_isp_confirmed=True)
    result.update(changes); return result


async def asset(db):
    result = await import_webshare_proxy(db, **args())
    return await db.outreach_proxy_inventory.find_one({'_id':result['proxy_id']})


async def test_import_bson_identity_concurrent_retry_and_keys_outside_transaction(managed_db, scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    inside = ContextVar('managed_webshare_transaction', default=False)
    original = suppression.mutate_suppression
    async def transact(db, workspace, callback):
        async def run(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await original(db, workspace, run)
    monkeypatch.setattr(suppression,'mutate_suppression',transact)
    original_seal = scoped.seal
    async def seal(*args):
        assert not inside.get()
        return await original_seal(*args)
    monkeypatch.setattr(scoped,'seal',seal)
    request = args(); results = await asyncio.gather(*(import_webshare_proxy(managed_db, **request) for _ in range(3)))
    assert sum(result['status']=='imported' for result in results) == 1
    assert await managed_db.outreach_proxy_inventory.count_documents({}) == 1
    row = await managed_db.outreach_proxy_inventory.find_one({'workspace_id':'w'})
    assert row['password_enc'].startswith('uc1:') and await managed_webshare_valid(managed_db,row,'w')
    assert row['expires_at'].tzinfo is None  # Actual default BSON codec.
    prepared = await proxy_custody.prepare_proxy(row,'w')
    assert prepared.matches(row,'w')


async def test_concurrent_cross_provider_and_customer_imports_have_one_winner(managed_db):
    request = args()
    results = await asyncio.gather(import_webshare_proxy(managed_db, **request), import_iproyal_proxy(managed_db,
        request['proxy_url'].replace(':12323',':23456'), 'IN', 'royal', 'other', request['expires_at']), return_exceptions=True)
    assert sum(isinstance(result,dict) for result in results) == 1
    assert await managed_db.outreach_proxy_inventory.count_documents({}) == 1
    assert await managed_db.account_proxy_ip_guards.count_documents({}) == 1


async def test_reservation_same_sender_concurrent_different_sender_and_country(managed_db):
    row = await asset(managed_db)
    proxies = await asyncio.gather(*(reserve_sender_proxy(managed_db,'w','sender','IN',reservation_job_id='job') for _ in range(3)))
    assert {proxy.proxy_id for proxy in proxies} == {row['_id']}
    assert await managed_db.outreach_proxy_leases.count_documents({}) == 1
    for sender,country in [('other-sender','IN'),('sender','US')]:
        with pytest.raises(Exception): await reserve_sender_proxy(managed_db,'w',sender,country)
    assert (await managed_db.outreach_proxy_leases.find_one({'workspace_id':'w'}))['reservation_job_id']=='job'


async def test_multiple_paid_senders_skip_occupied_asset_and_keep_unique_leases(managed_db):
    first=await asset(managed_db)
    second=await import_webshare_proxy(managed_db,**args(proxy_url='http://u:p@8.8.8.8:80',resource_id='second'))
    one=await reserve_sender_proxy(managed_db,'w','one','IN')
    two=await reserve_sender_proxy(managed_db,'w','two','IN')
    assert {one.proxy_id,two.proxy_id}=={first['_id'],second['proxy_id']}
    assert await managed_db.outreach_proxy_leases.count_documents({'workspace_id':'w'})==2


async def test_lost_insert_ack_retry_keeps_original_and_opens_no_keys(managed_db, monkeypatch):
    original = suppression.mutate_suppression; calls = 0
    async def lost(db, workspace, callback):
        nonlocal calls
        result = await original(db,workspace,callback); calls += 1
        if calls == 2: raise TimeoutError('ack lost')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    request = args()
    with pytest.raises(TimeoutError): await import_webshare_proxy(managed_db, **request)
    saved = await managed_db.outreach_proxy_inventory.find_one({'workspace_id':'w'})
    monkeypatch.setattr(suppression,'mutate_suppression',original)
    seal = AsyncMock(side_effect=AssertionError('no keys'))
    monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password',seal)
    assert (await import_webshare_proxy(managed_db, **request))['status']=='already_imported'
    assert await managed_db.outreach_proxy_inventory.find_one({'workspace_id':'w'}) == saved


async def test_closed_tenant_denies_before_sealing_and_original_claim_survives_purge(managed_db,monkeypatch):
    row = await asset(managed_db)
    await managed_db.outreach_proxy_inventory.delete_one({'_id':row['_id']})
    with pytest.raises(ValueError): await import_webshare_proxy(managed_db, **args(workspace_id='other'))
    await managed_db.outreach_suppression_guards.update_one(suppression.guard_scope('w'), {'$set': {'erasure_state':'stopped'}})
    seal = AsyncMock(side_effect=AssertionError('no keys')); monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password',seal)
    with pytest.raises(suppression.SuppressionUnavailable): await import_webshare_proxy(managed_db, **args(proxy_url='http://u:p@8.8.8.8:80'))
    seal.assert_not_awaited()


async def test_strict_sender_index_denies_duplicate_legacy_leases_and_retention_precedes_failure(managed_db):
    await managed_db.outreach_proxy_leases.drop_indexes()
    await managed_db.outreach_proxy_leases.insert_many([{'_id':str(n),'workspace_id':'w','sender_id':'same'} for n in range(2)])
    await managed_db.account_proxy_ip_guards.create_index('never_used',expireAfterSeconds=99999999)
    await remove_other_evidence_ttls(managed_db)
    with pytest.raises(DuplicateKeyError): await ensure_managed_proxy_indexes(managed_db)
    assert all('expireAfterSeconds' not in index for index in (await managed_db.account_proxy_ip_guards.index_information()).values())


async def active_account(db):
    row = await asset(db); proxy = await reserve_sender_proxy(db,'w','sender','IN')
    now = datetime.now(timezone.utc)
    await db.outreach_entitlements.insert_one({'workspace_id':'w','status':'active','seats':1,
        'paid_through':now+timedelta(days=20),'payment_source':'manual_verified_invoice'})
    await db.outreach_sender_slots.insert_one({'workspace_id':'w','sender_id':'sender'})
    return row, {'workspace_id':'w','id':'sender','status':'active','country_code':'IN','proxy':proxy.model_dump()}


async def test_sender_readiness_requires_exact_transport_manual_basis_and_claim(managed_db):
    row, account = await active_account(managed_db)
    assert await sender_is_ready(managed_db,'w',account)
    account['proxy']['username']='replacement'
    assert not await sender_is_ready(managed_db,'w',account)
    await managed_db.outreach_proxy_inventory.update_one({'_id':row['_id']},{'$unset':{'managed_webshare_version':''}})
    assert not await sender_is_ready(managed_db,'w',{**account,'proxy':{**account['proxy'],'username':row['username']}})


async def test_payment_capacity_excludes_unproven_and_counts_exact_webshare(managed_db):
    row = await asset(managed_db); term = datetime.now(timezone.utc)+timedelta(days=20)
    await managed_db.outreach_access_requests.insert_one({'workspace_id':'w','country_code':'IN','seats':1})
    await managed_db.outreach_proxy_inventory.update_one({'_id':row['_id']},{'$unset':{'managed_webshare_version':''}})
    with pytest.raises(ValueError,match='Import enough'): await record_verified_payment(managed_db,'w','invoice','op',1,term)
    await managed_db.outreach_proxy_inventory.update_one({'_id':row['_id']},{'$set':{'managed_webshare_version':1}})
    assert (await record_verified_payment(managed_db,'w','invoice','op',1,term))['status']=='active'


async def test_installation_checks_final_lease_and_inventory_under_guard(managed_db):
    row, account = await active_account(managed_db); now=datetime.now(timezone.utc)
    job={'id':'job','workspace_id':'w','sender_id':'sender','proxy_id':row['_id'],'country_code':'IN',
        'status':'finalizing','verification_owner_token':'owner','credential_generation':'new',
        'custody_expires_at':now+timedelta(minutes=10)}
    await managed_db.outreach_connection_jobs.insert_one(job)
    await managed_db.outreach_accounts.insert_one({**account,'credential_generation':'base','connection_finalization':{
        'job_id':'job','owner_token':'owner','generation':'new','state':'prepared','base_generation':'base',
        'custody_expires_at':job['custody_expires_at']}})
    prepared=await proxy_custody.prepare_proxy(row,'w')
    await managed_db.outreach_proxy_leases.update_one({'_id':row['_id']},{'$set':{'sender_id':'other'}})
    assert not await ConnectionRepair(managed_db).install(job,'owner','new',account,prepared_proxy=prepared)
    await managed_db.outreach_proxy_leases.update_one({'_id':row['_id']},{'$set':{'sender_id':'sender'}})
    assert await ConnectionRepair(managed_db).install(job,'owner','new',account,prepared_proxy=prepared)
    saved=await managed_db.outreach_accounts.find_one({'workspace_id':'w'})
    assert saved['connection_finalization']['state']=='installed' and saved['credential_generation']=='new'


async def test_pending_verification_final_guard_denies_missing_import_proof(managed_db):
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    from outreach.core.execution_permission import ExecutionPermission
    row, account = await active_account(managed_db); now=datetime.now(timezone.utc)
    job={'id':'job','workspace_id':'w','sender_id':'sender','proxy_id':row['_id'],'country_code':'IN',
        'status':'running','custody_expires_at':now+timedelta(minutes=10)}
    await managed_db.outreach_connection_jobs.insert_one(job)
    await managed_db.outreach_sender_execution.insert_one({**ExecutionPermission.scope('w','sender'),'permission':{
        'credential_generation':'pending:job','sources':['verify'],'latched':False,
        'issued_at':now-timedelta(seconds=1),'expires_at':now+timedelta(seconds=20)}})
    prepared=await proxy_custody.prepare_proxy(row,'w')
    envelope=RequestEnvelope(managed_db,'w','sender','pending:job','verify',prepared.url,
        connection_job_id='job',prepared_proxy=prepared)
    assert await envelope._validate(now,None) == {}
    await managed_db.outreach_proxy_inventory.update_one({'_id':row['_id']},{'$unset':{'import_basis_digest':''}})
    with pytest.raises(RequestDenied,match='proxy_changed'): await envelope._validate(now,None)


async def test_insert_failure_keeps_exclusion_without_inventing_inventory(managed_db,monkeypatch):
    original = suppression.SuppressionCollection.insert_one
    async def fail(self,document,**kwargs):
        if self.collection.name=='outreach_proxy_inventory': raise RuntimeError('insert outage')
        return await original(self,document,**kwargs)
    request=args(); monkeypatch.setattr(suppression.SuppressionCollection,'insert_one',fail)
    with pytest.raises(RuntimeError): await import_webshare_proxy(managed_db,**request)
    assert await managed_db.outreach_proxy_inventory.count_documents({})==0
    assert await managed_db.account_proxy_ip_guards.count_documents({})==1
    monkeypatch.setattr(suppression.SuppressionCollection,'insert_one',original)
    assert (await import_webshare_proxy(managed_db,**request))['status']=='imported'


async def test_expired_lease_only_retires_when_replacement_commits(managed_db):
    row=await asset(managed_db); expiry=row['expires_at'].replace(tzinfo=timezone.utc)
    await reserve_sender_proxy(managed_db,'w','sender','IN')
    with pytest.raises(Exception): await reserve_sender_proxy(managed_db,'w','sender','IN',now=expiry+timedelta(seconds=1))
    assert await managed_db.outreach_proxy_lease_history.count_documents({})==0
    assert await managed_db.outreach_proxy_leases.count_documents({})==1
    new=await import_webshare_proxy(managed_db,**args(proxy_url='http://u:p@8.8.8.8:80',
        resource_id='replacement',expires_at=expiry+timedelta(days=30)))
    assert (await reserve_sender_proxy(managed_db,'w','sender','IN',now=expiry+timedelta(seconds=1))).proxy_id==new['proxy_id']
    assert await managed_db.outreach_proxy_lease_history.count_documents({})==1
    assert await managed_db.account_proxy_ip_guards.count_documents({})==2


async def test_actual_standalone_denies_import_before_key_work(monkeypatch,tmp_path):
    import socket
    import subprocess
    from pymongo.errors import PyMongoError
    with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',27029))!=0
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port','27029','--bind_ip','127.0.0.1',
        '--logpath',str(tmp_path/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true',serverSelectionTimeoutMS=500)
    db=client['test_webshare_standalone_'+uuid.uuid4().hex]
    try:
        for _ in range(40):
            try: await client.admin.command('ping'); break
            except PyMongoError: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone failed to start')
        seal=AsyncMock(side_effect=AssertionError('no KMS'))
        monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password',seal)
        with pytest.raises(suppression.SuppressionUnavailable): await import_webshare_proxy(db,**args())
        seal.assert_not_awaited()
        assert await db.outreach_proxy_inventory.count_documents({})==0
        assert await db.account_proxy_ip_guards.count_documents({})==0
    finally:
        await client.drop_database(db.name);client.close()
        process.terminate();process.wait(timeout=10)


async def test_proxy_policy_rotation_after_dispatch_commit_is_proven_non_call(ready_db,monkeypatch):
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    db,job=ready_db
    original=RequestEnvelope._authorize_dispatch
    async def commit_then_rotate(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement-after-commit')
        return result
    monkeypatch.setattr(RequestEnvelope,'_authorize_dispatch',commit_then_rotate)
    factory=AsyncMock(side_effect=AssertionError('HTTP cannot begin'))
    with pytest.raises(RequestDenied,match='proxy_changed'): await dispatch(db,job,factory)
    factory.assert_not_awaited()
    evidence=await db.outreach_physical_requests.find_one({'workspace_id':'w'})
    assert evidence['status']=='not_submitted'
    execution=await db.outreach_sender_execution.find_one({'workspace_id':'w','sender_id':'a'})
    assert 'physical_request_token' not in execution
