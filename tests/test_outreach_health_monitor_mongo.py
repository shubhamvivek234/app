"""Actual snapshot/majority renewal, replacement protection and rollback."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import os
import shutil
import socket
import subprocess
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
import pytest
import pytest_asyncio

from outreach.core import health_monitor as health, suppression
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_health_monitor import healthy_db, EVIDENCE
from tests.test_outreach_dispatch_authority import ready_db, dispatch

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned local Mongo is opt-in')]


@pytest_asyncio.fixture
async def real_health(healthy_db):
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27028',serverSelectionTimeoutMS=2000)
    db=client['test_health_monitor_'+uuid.uuid4().hex]
    try:
        for name,collection in healthy_db.collections.items():
            if collection.docs:await db[name].insert_many(collection.docs)
        await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
        yield db
    finally:await client.drop_database(db.name);client.close()


async def arm(db):
    service=health.HealthMonitor(db);view=await service.inspect('w','sender')
    assert not view['blockers']
    return await service.arm('w','sender','operator',EVIDENCE,view['digest'],window_seconds=300)


async def test_native_bson_duplicate_tick_and_historical_arm(real_health):
    db=real_health;service=health.HealthMonitor(db);view=await service.inspect('w','sender')
    control=await arm(db)
    assert (await db.outreach_accounts.find_one({'workspace_id':'w'}))['execution_health']['observed_at'].tzinfo is None
    results=await asyncio.gather(service.tick('w',control['control_id']),service.tick('w',control['control_id']))
    assert sorted(row['status'] for row in results)==['not_due','renewed']
    state=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    assert state['permission_revision']==4 and await ExecutionPermission(db).allowed('w','sender','generation','sequence')
    await service.stop('w',control['control_id'],'operator',EVIDENCE)
    assert (await service.arm('w','sender','operator',EVIDENCE,view['digest'],window_seconds=300))['status']=='stopped'
    assert (await db.outreach_campaigns.find_one({'workspace_id':'w'}))['status']=='paused'


@pytest.mark.parametrize('target',['permission','projection','root','final'])
async def test_renewal_failure_rolls_back_all_authorities(real_health,monkeypatch,target):
    db=real_health;control=await arm(db); original=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    update=suppression.SuppressionCollection.update_one
    async def failed(self,*args,**kwargs):
        if self.collection.name=={'permission':'outreach_sender_execution','projection':'outreach_execution_permissions',
            'root':'outreach_health_controls'}.get(target) and '$set' in args[1]:raise RuntimeError('Owned failure')
        return await update(self,*args,**kwargs)
    monkeypatch.setattr(suppression.SuppressionCollection,'update_one',failed)
    if target=='final':monkeypatch.setattr(health.HealthMonitor,'_final',lambda *args:(_ for _ in ()).throw(ValueError('Owned deadline')))
    with pytest.raises((RuntimeError,ValueError)):await health.HealthMonitor(db).tick('w',control['control_id'])
    assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==original
    assert not await db.outreach_execution_permissions.find_one({'workspace_id':'w'})
    assert (await db.outreach_health_controls.find_one({'workspace_id':'w'}))['renewals']==0


@pytest.mark.parametrize('fault',['generation','revision','proxy','latched','unknown','closed'])
async def test_current_authority_changes_do_not_reopen(real_health,fault):
    db=real_health;control=await arm(db)
    if fault=='generation':await db.outreach_accounts.update_one({'workspace_id':'w'},{'$set':{'credential_generation':'replacement'}})
    if fault=='revision':await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$inc':{'permission_revision':1}})
    if fault=='proxy':await db.outreach_proxy_inventory.update_one({'workspace_id':'w'},{'$set':{'password_enc':'replacement'}})
    if fault=='latched':await db.outreach_sender_execution.update_one({'workspace_id':'w'},{'$set':{'permission.latched':True}})
    if fault=='unknown':await db.outreach_physical_requests.insert_one({'_id':'unknown','workspace_id':'w','sender_id':'sender','status':'unknown_outcome'})
    if fault=='closed':await db.outreach_suppression_guards.update_one(suppression.guard_scope('w'),{'$set':{'erasure_state':'closed'}},upsert=True)
    original=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
    if fault=='closed':
        with pytest.raises(Exception):await health.HealthMonitor(db).tick('w',control['control_id'])
        assert await db.outreach_sender_execution.find_one({'workspace_id':'w'})==original
    else:
        result=await health.HealthMonitor(db).tick('w',control['control_id'])
        assert result['status']==('obsolete' if fault in {'generation','revision'} else 'stopped')
        state=await db.outreach_sender_execution.find_one({'workspace_id':'w'})
        if fault in {'generation','revision'}:assert health.stable(state)==health.stable(original)
        else:assert state['permission']['latched']


async def test_flag_and_policy_proof_are_checked_after_authorization(real_health,monkeypatch):
    db=real_health;control=await arm(db);await health.HealthMonitor(db).tick('w',control['control_id'])
    async def check(current):
        authority=AuthorityDatabase(current.database,current.session,'health-dispatch-test')
        assert await ExecutionPermission(authority).allowed('w','sender','generation','sequence')
        return authority.checks
    checks=await suppression.mutate_suppression(db,'w',check)
    assert checks and all(callback(health.now()) for callback in checks)
    monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','false')
    assert not all(callback(health.now()) for callback in checks)
    monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','true');monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','replacement')
    assert not all(callback(health.now()) for callback in checks)


async def test_startup_removes_ttl_before_duplicate_active_failure(real_health):
    from db.indexes import remove_other_evidence_ttls,ensure_integration_indexes
    db=real_health;await arm(db)
    row=await db.outreach_health_controls.find_one({'workspace_id':'w'});row['_id']='duplicate'
    await db.outreach_health_controls.insert_one(row)
    await db.outreach_health_controls.create_index('expires_at',expireAfterSeconds=0,name='unsafe_ttl')
    await remove_other_evidence_ttls(db)
    with pytest.raises(OperationFailure):await ensure_integration_indexes(db)
    assert 'unsafe_ttl' not in await db.outreach_health_controls.index_information()
    await db.outreach_health_controls.delete_one({'_id':'duplicate'});await ensure_integration_indexes(db)
    indexes=await db.outreach_health_controls.index_information()
    assert indexes['health_sender_active_v1']['unique'] and all('expireAfterSeconds' not in index for index in indexes.values())


async def test_erasure_stops_control_and_retains_only_metadata(real_health):
    db=real_health;await arm(db);service=OutreachErasure(db)
    await service.request('w','actor')
    root=await db.outreach_health_controls.find_one({'workspace_id':'w'})
    assert root['status']=='stopped' and root['stop_reason']=='erasure_requested'
    async def archive(current):await service._archive(current,'outreach_health_controls','w',root)
    # Archive is part of erasure's allowed closed-workspace transaction.
    async with await db.client.start_session() as session:
        async with session.start_transaction():await archive(suppression.SuppressionDatabase(db,'w',session))
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'execution_health_control'})
    assert hold and hold['generation_digest'] and 'operator' not in hold and 'sender_id' not in hold
    assert 'private-user' not in str(hold) and not hold['activation_allowed']


async def test_standalone_cannot_arm(real_health,tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    path=tmp_path/'mongo';path.mkdir()
    with (tmp_path/'mongo.log').open('w') as log:
        process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(path),'--bind_ip','127.0.0.1','--port',str(port)],stdout=log,stderr=log)
        client=AsyncIOMotorClient('mongodb://127.0.0.1:'+str(port),serverSelectionTimeoutMS=1000)
        db=client['test_health_standalone_'+uuid.uuid4().hex]
        try:
            for attempt in range(20):
                try:await client.admin.command('ping');break
                except Exception:
                    if attempt==19:raise
                    await asyncio.sleep(.2)
            for name in await real_health.list_collection_names():
                rows=await real_health[name].find({}).to_list(length=200)
                if rows:await db[name].insert_many(rows)
            view=await health.HealthMonitor(db).inspect('w','sender')
            with pytest.raises(Exception):await health.HealthMonitor(db).arm('w','sender','operator',EVIDENCE,view['digest'])
            assert not await db.outreach_health_controls.find_one({})
        finally:
            await client.drop_database(db.name);client.close();process.terminate();process.wait(timeout=10);shutil.rmtree(path)


@pytest.mark.parametrize('change',['flag','policy'])
async def test_actual_factory_denied_after_health_policy_changes_at_commit(ready_db,monkeypatch,change):
    """Exercise the normal dispatch entry using a matching control authority."""
    import httpx
    from unittest.mock import AsyncMock
    from outreach.core.request_guard import RequestEnvelope,RequestDenied
    from outreach.core.authorization import canonical_hash
    db,job=ready_db;monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED','true')
    monkeypatch.setenv('OUTREACH_MOCK_AUTH','false')
    state=await db.outreach_sender_execution.find_one(ExecutionPermission.scope('w','a'))
    key='a'*64
    await db.outreach_health_controls.insert_one({'_id':key,'workspace_id':'w','sender_id':'a','status':'armed',
        'expires_at':health.now()+timedelta(seconds=60),'generation':state['permission']['credential_generation'],
        'sources':state['permission']['sources'],'expected_permission_revision':state['permission_revision'],
        'policy_digest':canonical_hash(health.policy())})
    await db.outreach_sender_execution.update_one(ExecutionPermission.scope('w','a'),{'$set':{'permission.health_control_id':key}})
    original=RequestEnvelope._authorize_dispatch
    async def authorize(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        monkeypatch.setenv('OUTREACH_HEALTH_MONITOR_ENABLED' if change=='flag' else 'OUTREACH_CUSTODY_ENVIRONMENT_ID',
            'false' if change=='flag' else 'changed-policy')
        return result
    monkeypatch.setattr(RequestEnvelope,'_authorize_dispatch',authorize)
    factory=AsyncMock(return_value=httpx.Response(201,json={}))
    with pytest.raises(RequestDenied):await dispatch(db,job,factory)
    factory.assert_not_awaited()
    row=await db.outreach_physical_requests.find_one({'workspace_id':'w'})
    assert row['status']=='not_submitted'
