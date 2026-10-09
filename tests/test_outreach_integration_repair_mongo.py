"""Disposable real replica-set repair/migration rollback and custody boundaries."""
import asyncio
from contextvars import ContextVar
from datetime import timedelta
import os
from unittest.mock import AsyncMock
import pytest
from pymongo.errors import OperationFailure
from outreach.core import integration_control as ctl, integration_custody as custody, suppression, erasure
from outreach.core.integration_review import IntegrationReview
from outreach.core.integration_migration import IntegrationMigration
from outreach.core.integration_delivery import IntegrationDelivery, now
from db.indexes import ensure_integration_indexes
from tests.test_outreach_integration_mongo import real_db
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_integration_review import held, EVIDENCE
from tests.test_outreach_integration_migration import legacy

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned loopback replica set is opt-in')]

@pytest.mark.parametrize('decision',['stop_local','use_receipt'])
async def test_concurrent_review_commits_one_original_journal(real_db,monkeypatch,decision):
    db=real_db;job=await held(db,monkeypatch,received=decision=='use_receipt');service=IntegrationReview(db)
    view=await service.inspect('w',job['id'])
    results=await asyncio.gather(*(service.resolve('w',job['id'],decision,'operator',EVIDENCE,
        workers_drained=True,expected_digest=view['review_digest']) for _ in range(2)))
    assert results[0]==results[1]
    assert await db.outreach_integration_reviews.count_documents({'workspace_id':'w'})==1
    assert (await db.outreach_campaigns.find_one({'id':'campaign'}))['authorization_revision']==4
    saved=await db.outreach_webhook_deliveries.find_one({'id':job['id']})
    assert saved['receipt']==job['receipt'] if decision=='use_receipt' else saved['active_slot']==job['active_slot']

@pytest.mark.parametrize('fault',['journal','late_flag','ack_loss'])
async def test_review_rollback_and_commit_acknowledgement_loss(real_db,monkeypatch,fault):
    db=real_db;job=await held(db,monkeypatch,received=True);service=IntegrationReview(db)
    view=await service.inspect('w',job['id']);original=ctl.control
    if fault=='journal':
        insert=suppression.SuppressionCollection.insert_one
        async def failed(current,*args,**kwargs):
            if current.collection.name=='outreach_integration_reviews':raise ValueError('Local injected journal failure')
            return await insert(current,*args,**kwargs)
        monkeypatch.setattr(suppression.SuppressionCollection,'insert_one',failed)
    elif fault=='late_flag':
        stop=ctl.stop
        async def changed(*args,**kwargs):await stop(*args,**kwargs);monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
        monkeypatch.setattr(ctl,'stop',changed)
    else:
        async def lost(*args):await original(*args);raise suppression.SuppressionUnavailable('Unknown commit acknowledgement')
        monkeypatch.setattr(ctl,'control',lost)
    with pytest.raises((ValueError,suppression.SuppressionUnavailable)):
        await service.resolve('w',job['id'],'use_receipt','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    if fault=='ack_loss':
        monkeypatch.setattr(ctl,'control',original)
        assert (await service.resolve('w',job['id'],'use_receipt','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest']))['status']=='review_completed'
        assert (await db.outreach_campaigns.find_one({'id':'campaign'}))['authorization_revision']==4
    else:
        assert (await db.outreach_campaigns.find_one({'id':'campaign'}))['status']=='active'
        assert (await db.outreach_integrations.find_one({'provider':'hubspot'}))['status']=='connected'
        assert await db.outreach_integration_controls.count_documents({})==0
        assert await db.outreach_external_mappings.count_documents({})==0
        assert await db.outreach_integration_reviews.count_documents({})==0

@pytest.mark.parametrize('kind',['webhook','slack','hubspot'])
async def test_migration_key_work_outside_mongo_and_concurrent_idempotent_install(real_db,monkeypatch,scoped,kind):
    db=real_db;raw=await legacy(db,monkeypatch,kind);resource='hook' if kind=='webhook' else kind
    service=IntegrationMigration(db);view=await service.inspect('w',kind,resource)
    inside=ContextVar('integration_migration_txn',default=False);original=ctl.control
    async def guarded(database,workspace,callback):
        async def marked(current):
            token=inside.set(True)
            try:return await callback(current)
            finally:inside.reset(token)
        return await original(database,workspace,marked)
    monkeypatch.setattr(ctl,'control',guarded);seal=scoped.seal
    async def sealing(*args):assert not inside.get();return await seal(*args)
    monkeypatch.setattr(scoped,'seal',sealing)
    results=await asyncio.gather(*(service.migrate('w',kind,resource,'operator',EVIDENCE,view['review_digest'],workers_drained=True) for _ in range(2)))
    assert results[0]==results[1]
    assert await db.outreach_credential_migrations.count_documents({'kind':'integration'})==1
    after=await custody.collection(db,kind).find_one(custody.resource_scope('w',kind,resource))
    assert (await custody.prepare(after,'w',kind)).value==raw and after['integration_review_required']

async def test_exact_migration_receipt_committed_before_guard_skips_old_source_and_keys(real_db,monkeypatch,scoped):
    """Deterministically close the outside-read / guarded-inspection race."""
    from motor.motor_asyncio import AsyncIOMotorCollection
    db=real_db; await legacy(db,monkeypatch,'webhook')
    await db.outreach_campaigns.insert_one({'workspace_id':'w','id':'campaign','status':'active','authorization_revision':3})
    service=IntegrationMigration(db); view=await service.inspect('w','webhook','hook')
    original=AsyncIOMotorCollection.find_one; triggered=False; committed=None
    seal=AsyncMock(wraps=scoped.seal); monkeypatch.setattr(scoped,'seal',seal)
    async def other_commits(self,query,*args,**kwargs):
        nonlocal triggered,committed
        if self.name=='outreach_credential_migrations' and not kwargs.get('session') and not triggered:
            triggered=True
            prior=await original(self,query,*args,**kwargs)
            assert prior is None
            committed=await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)
            return prior
        return await original(self,query,*args,**kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection,'find_one',other_commits)
    assert await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)==committed
    seal.assert_awaited_once()
    assert await db.outreach_credential_migrations.count_documents({'kind':'integration'})==1
    assert (await db.outreach_campaigns.find_one({'id':'campaign'}))['authorization_revision']==4


@pytest.mark.parametrize('fault',['journal','late_flag','replacement','ack_loss'])
async def test_migration_rollback_replacement_and_metadata_retry(real_db,monkeypatch,scoped,fault):
    db=real_db;await legacy(db,monkeypatch);service=IntegrationMigration(db);view=await service.inspect('w','webhook','hook')
    before=await db.outreach_webhooks.find_one({'id':'hook'});original=ctl.control
    if fault=='journal':
        insert=suppression.SuppressionCollection.insert_one
        async def failed(current,*args,**kwargs):
            if current.collection.name=='outreach_credential_migrations':raise ValueError('Injected local failure')
            return await insert(current,*args,**kwargs)
        monkeypatch.setattr(suppression.SuppressionCollection,'insert_one',failed)
    elif fault in {'late_flag','replacement'}:
        seal=scoped.seal
        async def changed(*args):
            value=await seal(*args)
            if fault=='late_flag':monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
            else:await db.outreach_webhooks.update_one({'id':'hook'},{'$set':{'credential_generation':'replacement'}})
            return value
        monkeypatch.setattr(scoped,'seal',changed)
    else:
        calls=[0]
        async def lost(*args):
            calls[0]+=1;value=await original(*args)
            if calls[0]==2:raise suppression.SuppressionUnavailable('Unknown commit acknowledgement')
            return value
        monkeypatch.setattr(ctl,'control',lost)
    with pytest.raises((ValueError,suppression.SuppressionUnavailable)):
        await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)
    if fault=='ack_loss':
        monkeypatch.setattr(scoped,'seal',AsyncMock(side_effect=AssertionError('No key replay')))
        result=await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)
        assert result['current_matches']
    else:
        after=await db.outreach_webhooks.find_one({'id':'hook'})
        assert after['secret_enc']==before['secret_enc'] and after['status']=='active'
        assert await db.outreach_integration_controls.count_documents({})==0
        assert await db.outreach_credential_migrations.count_documents({})==0

async def test_legacy_backlog_blocks_migration_and_stop_scrubs_copies(real_db,monkeypatch):
    db=real_db;await legacy(db,monkeypatch)
    await db.outreach_webhook_deliveries.insert_one({'workspace_id':'w','id':'old','destination_id':'hook',
        'status':'review_required','secret_enc':'copied-secret','target_url':'https://private.example/path'})
    service=IntegrationMigration(db);view=await service.inspect('w','webhook','hook')
    assert 'original_delivery_outcome_unresolved' in view['blockers']
    repair=IntegrationReview(db);inspected=await repair.inspect('w','old')
    result=await repair.resolve('w','old','stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=inspected['review_digest'])
    assert result['outcome_at_review']=='unknown'
    row=await db.outreach_webhook_deliveries.find_one({'id':'old'});assert 'secret_enc' not in row and 'target_url' not in row
    with pytest.raises(ValueError):await service.migrate('w','webhook','hook','operator',EVIDENCE,(await service.inspect('w','webhook','hook'))['review_digest'],workers_drained=True)

async def test_resource_control_survives_actual_disconnect_and_restored_status(real_db,monkeypatch):
    db=real_db;job=await held(db,monkeypatch,'slack');service=IntegrationReview(db);view=await service.inspect('w',job['id'])
    await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    await custody.disconnect(db,'w','slack','slack',authority={'actor':'actor'})
    # Even a restored config row cannot erase the distinct persisted authority.
    from tests.test_outreach_integration_custody import resource
    row=resource('slack');row.update(await custody.seal('https://hooks.slack.com/services/T1/B2/private-token',row,'w','slack'))
    await db.outreach_integrations.insert_one(row);monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
    with pytest.raises(ValueError,match='held'):await IntegrationDelivery(db).queue('w','slack','slack','new',{},actor='actor')

async def test_closed_erasure_stop_keeps_minimal_evidence_and_creates_no_authority(real_db,monkeypatch):
    db=real_db;job=await held(db,monkeypatch)
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
    service=erasure.OutreachErasure(db);await service.request('w','actor')
    repair=IntegrationReview(db);view=await repair.inspect('w',job['id'])
    assert 'use_receipt' not in view['allowed_decisions']
    await repair.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert await db.outreach_integration_controls.count_documents({})==0
    inspected=await service.inspect('w');await service.finish('w','operator',EVIDENCE,workers_drained=True,expected_digest=inspected['review_digest'])
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','operation_kind':'integration_review'})
    assert hold and hold['kind']=='unresolved_submission' and not hold['activation_allowed']
    assert 'private-' not in str(hold) and 'person@example.com' not in str(hold)

async def test_review_journal_ttl_removed_before_strict_duplicate_failure(real_db):
    db=real_db;await db.outreach_integration_reviews.drop_indexes()
    await db.outreach_integration_reviews.insert_many([{'workspace_id':'w','id':'duplicate'} for _ in range(2)])
    for name in ['outreach_integration_reviews','outreach_integration_controls','outreach_credential_migrations']:
        await db[name].create_index('at',expireAfterSeconds=77777777)
    with pytest.raises(OperationFailure):await ensure_integration_indexes(db)
    for name in ['outreach_integration_reviews','outreach_integration_controls','outreach_credential_migrations']:
        assert all('expireAfterSeconds' not in item for item in (await db[name].index_information()).values())

async def test_actual_standalone_denies_review_before_any_stop(real_db,monkeypatch,tmp_path):
    import socket,subprocess,uuid
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import PyMongoError
    db=real_db;job=await held(db,monkeypatch)
    with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',27029))!=0
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port','27029','--bind_ip','127.0.0.1',
        '--logpath',str(root/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true',serverSelectionTimeoutMS=500)
    standalone=client['test_unravler_int_repair_'+uuid.uuid4().hex]
    try:
        for _ in range(40):
            try:await client.admin.command('ping');break
            except PyMongoError:await asyncio.sleep(.1)
        else:raise AssertionError('Owned standalone did not start')
        for name in await db.list_collection_names():
            rows=await db[name].find({}).to_list(length=200)
            if rows:await standalone[name].insert_many(rows)
        await ensure_integration_indexes(standalone)
        service=IntegrationReview(standalone);view=await service.inspect('w',job['id'])
        with pytest.raises(suppression.SuppressionUnavailable):
            await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
        assert (await standalone.outreach_campaigns.find_one({'id':'campaign'}))['status']=='active'
        assert await standalone.outreach_integration_controls.count_documents({})==0
        assert await standalone.outreach_integration_reviews.count_documents({})==0
    finally:
        try:
            await client.drop_database(standalone.name)
        finally:
            client.close();process.terminate();process.wait(timeout=10)
