"""Actual drained review transactions, acknowledgement loss and receipt races."""
import asyncio
from datetime import timedelta
import os
import uuid
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from db.indexes import ensure_voice_studio_indexes
from outreach.core.authorization import canonical_hash
from outreach.core import suppression
from outreach.core.voice_studio import VoiceStudio, now
from outreach.core.voice_studio_review import VoiceStudioReview
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.sender_execution import SenderExecution
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_voice_studio_review import EVIDENCE

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned loopback replica set is opt-in')]


@pytest_asyncio.fixture
async def review_db(studio_db):
    # Production-default naive UTC decoding is intentional.
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=2000)
    db = client['test_unravler_studio_review_' + uuid.uuid4().hex]
    for name, source in studio_db.collections.items():
        if source.docs: await db[name].insert_many(source.docs)
    await ensure_voice_studio_indexes(db)
    try: yield db
    finally:
        await client.drop_database(db.name)
        client.close()


async def ready(db, monkeypatch, operation='clone', received=False):
    service = VoiceStudio(db)
    job = await service.queue('w', 'actor', 'clone', 'clone-review', name='Voice',
        audio=generate_mock_voice_wav(duration_s=20), consent=True)
    if operation != 'clone':
        await service.run('w', job['_id'], provider=AsyncMock(return_value={'voice_id': 'remote'}))
        job = await service.queue('w', 'actor', operation, 'request-review', voice_id=job['voice_id'], script='Hi')
    async def provider(request):
        if not received: raise TimeoutError('dummy local outcome')
        monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED', 'false')
        return {'voice_id': 'remote'} if operation == 'clone' else {'deleted': True} if operation == 'delete' else {'audio': generate_mock_voice_wav()}
    await service.run('w', job['_id'], provider=provider)
    await db.outreach_voice_studio_jobs.update_one({'_id': job['_id']}, {'$set': {'lease_until': now()-timedelta(seconds=1)}})
    await db.outreach_accounts.insert_one({'_id': 'a', 'id': 'a', 'workspace_id': 'w', 'status': 'active'})
    await db.outreach_campaigns.insert_one({'_id': 'c', 'id': 'c', 'workspace_id': 'w', 'status': 'active', 'authorization_revision': 3})
    await db.outreach_sender_execution.insert_one({**SenderExecution.scope('w','a'), 'status': 'in_flight',
        'owner_token': 'original', 'physical_request_token': 'held-token', 'permission': {'latched': False}})
    await db.outreach_execution_permissions.insert_one({**ExecutionPermission.scope('w','a'), 'latched': False})
    for flag in ['OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED']:
        monkeypatch.setenv(flag,'false')
    return await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})


async def resolve(db, job, decision='stop_local'):
    service=VoiceStudioReview(db); view=await service.inspect('w',job['_id'])
    return await service.resolve('w',job['_id'],decision,'operator',EVIDENCE,
        expected_digest=view['review_digest'],workers_drained=True)


@pytest.mark.parametrize('operation', ['clone','preview','delete'])
async def test_real_received_projection_never_activates_or_opens_keys(review_db,monkeypatch,operation):
    db=review_db; job=await ready(db,monkeypatch,operation,received=True)
    from outreach.core import voice_studio, session_custody
    monkeypatch.setattr(voice_studio,'prepare_key',AsyncMock(side_effect=AssertionError('No key')))
    monkeypatch.setattr(session_custody,'configured_custody',lambda: (_ for _ in ()).throw(AssertionError('No KMS')))
    result=await resolve(db,job,'use_receipt')
    assert result['status']=='review_completed'
    saved=await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})
    assert saved['receipt']==job['receipt'] and saved['owner']==job['owner']
    assert not saved.get('result_enc') and not saved.get('input_enc')
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4
    execution=await db.outreach_sender_execution.find_one(SenderExecution.scope('w','a'))
    assert execution['permission']['latched'] and execution['physical_request_token']=='held-token'
    profile=await db.outreach_voices.find_one({'id':job['voice_id']})
    if operation=='delete': assert profile is None
    else: assert profile['studio_review_required'] and profile['status']!='active'


async def test_concurrent_duplicate_review_is_one_atomic_stop(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    service=VoiceStudioReview(db);view=await service.inspect('w',job['_id'])
    results=await asyncio.gather(*(service.resolve('w',job['_id'],'stop_local','operator',EVIDENCE,
        expected_digest=view['review_digest'],workers_drained=True) for _ in range(5)))
    assert all(result==results[0] for result in results)
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4
    assert (await db.outreach_voices.find_one({}))['studio_review_required']
    assert await db.outreach_voice_studio_jobs.count_documents({'status':'review_stopped'})==1


async def test_lost_commit_ack_reuses_saved_review_without_repeated_stop(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    service=VoiceStudioReview(db);view=await service.inspect('w',job['_id'])
    original=suppression.mutate_suppression; injected=False
    async def lost(database,workspace,callback):
        nonlocal injected
        value=await original(database,workspace,callback)
        if not injected and value.get('status')=='review_stopped':
            injected=True
            raise RuntimeError('Lost local acknowledgement')
        return value
    monkeypatch.setattr(suppression,'mutate_suppression',lost)
    with pytest.raises(RuntimeError):
        await service.resolve('w',job['_id'],'stop_local','operator',EVIDENCE,expected_digest=view['review_digest'],workers_drained=True)
    result=await service.resolve('w',job['_id'],'stop_local','operator',EVIDENCE,expected_digest=view['review_digest'],workers_drained=True)
    assert result['status']=='review_stopped'
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4


async def test_transaction_abort_rolls_back_stop_profile_and_review_together(review_db,monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorCollection
    db=review_db;job=await ready(db,monkeypatch)
    original=AsyncIOMotorCollection.update_one
    async def fail(collection,query,update,*args,**kw):
        if collection.name=='outreach_voice_studio_jobs' and update.get('$set',{}).get('review'):
            raise ValueError('Abort final local review write')
        return await original(collection,query,update,*args,**kw)
    monkeypatch.setattr(AsyncIOMotorCollection,'update_one',fail)
    with pytest.raises(ValueError): await resolve(db,job)
    assert (await db.outreach_accounts.find_one({'_id':'a'}))['status']=='active'
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==3
    assert (await db.outreach_voices.find_one({}))['studio_job_id']==job['_id']
    assert not (await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})).get('review')
    monkeypatch.setattr(AsyncIOMotorCollection,'update_one',original)
    assert (await resolve(db,job))['status']=='review_stopped'


async def test_receipt_committed_first_invalidates_old_unknown_inspection(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    service=VoiceStudioReview(db);view=await service.inspect('w',job['_id'])
    async def receipt(current):
        await current.outreach_voice_studio_jobs.update_one({'workspace_id':'w','_id':job['_id'],'owner':job['owner'],'status':'held_outcome'},
            {'$set':{'status':'received','receipt':{'voice_id':'remote','requires_verification':False,'received_at':now()}}})
    await suppression.mutate_suppression(db,'w',receipt)
    with pytest.raises(ValueError):
        await service.resolve('w',job['_id'],'stop_local','operator',EVIDENCE,expected_digest=view['review_digest'],workers_drained=True)
    assert (await resolve(db,job,'use_receipt'))['status']=='review_completed'


async def test_review_committed_first_fences_late_original_worker_receipt(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    await resolve(db,job)
    async def late(current):
        return await current.outreach_voice_studio_jobs.update_one({'workspace_id':'w','_id':job['_id'],'owner':job['owner'],
            'status':{'$in':['possible','held_outcome']}},{'$set':{'status':'received','receipt':{'voice_id':'remote','requires_verification':False,'received_at':now()}}})
    assert (await suppression.mutate_suppression(db,'w',late)).matched_count==0
    saved=await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})
    assert saved['status']=='review_stopped' and not saved.get('receipt')


async def test_erasure_retains_unknown_review_without_operator_narrative(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    await resolve(db,job)
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
    erasure=OutreachErasure(db);await erasure.request('w','actor')
    view=await erasure.inspect('w')
    await erasure.finish('w','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    hold=await db.outreach_erasure_holds.find_one({'source_collection':'outreach_voice_studio_jobs','record_id_hash':canonical_hash(job['_id'])})
    assert hold['kind']=='unresolved_submission' and hold['original_outcome']=='unknown'
    assert hold['review_provenance']=='operator_local_stop' and EVIDENCE not in str(hold)
    assert not await db.outreach_voice_studio_jobs.find_one({'_id':job['_id']})


async def test_closed_workspace_review_never_recreates_authority_or_activates(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch,received=True)
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
    await OutreachErasure(db).request('w','actor')
    async def remove(current):
        await current.outreach_sender_execution.delete_one(SenderExecution.scope('w','a'))
        await current.outreach_execution_permissions.delete_one(ExecutionPermission.scope('w','a'))
    from outreach.core.erasure import _control
    await _control(db,'w',remove)
    with pytest.raises(ValueError): await resolve(db,job,'use_receipt')
    assert (await resolve(db,job))['status']=='review_stopped'
    assert await db.outreach_execution_permissions.count_documents({})==0
    assert await db.outreach_sender_execution.count_documents({})==0
    assert not (await db.outreach_voices.find_one({})).get('elevenlabs_voice_id')


async def test_replacement_profile_is_never_relabelled_or_unlocked(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    await db.outreach_voices.update_one({'id':job['voice_id']},{'$set':{'studio_job_id':'replacement','elevenlabs_voice_id':'new-remote'}})
    with pytest.raises(ValueError): await resolve(db,job)
    profile=await db.outreach_voices.find_one({})
    assert profile['studio_job_id']=='replacement' and profile['elevenlabs_voice_id']=='new-remote'


async def test_configuration_change_inside_transaction_aborts_all_repairs(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    service=VoiceStudioReview(db);original=service._stop_authority
    async def changed(*args):
        await original(*args)
        monkeypatch.setenv('ELEVENLABS_API_KEY','replacement')
    monkeypatch.setattr(service,'_stop_authority',changed)
    view=await service.inspect('w',job['_id'])
    with pytest.raises(ValueError):
        await service.resolve('w',job['_id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['status']=='active'
    assert (await db.outreach_voices.find_one({}))['studio_job_id']==job['_id']


async def test_review_preserves_other_workspaces_and_does_not_add_ttl(review_db,monkeypatch):
    db=review_db;job=await ready(db,monkeypatch)
    await db.outreach_accounts.insert_one({'_id':'other-a','workspace_id':'other','id':'a','status':'active'})
    await db.outreach_campaigns.insert_one({'_id':'other-c','workspace_id':'other','id':'c','status':'active'})
    await resolve(db,job)
    assert (await db.outreach_accounts.find_one({'_id':'other-a'}))['status']=='active'
    assert (await db.outreach_campaigns.find_one({'_id':'other-c'}))['status']=='active'
    assert not any('expireAfterSeconds' in index for index in (await db.outreach_voice_studio_jobs.index_information()).values())


async def test_actual_standalone_denies_review_without_partial_repairs(review_db,monkeypatch,tmp_path):
    import socket
    import subprocess
    from pymongo.errors import PyMongoError
    db=review_db;job=await ready(db,monkeypatch)
    with socket.socket() as connection:
        assert connection.connect_ex(('127.0.0.1',27029)) != 0, 'Preserve any existing service on27029'
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port','27029',
        '--bind_ip','127.0.0.1','--logpath',str(root/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true',serverSelectionTimeoutMS=500)
    target=client['test_unravler_review_sa_'+uuid.uuid4().hex]
    try:
        for _ in range(40):
            try:
                await client.admin.command('ping');break
            except PyMongoError: await asyncio.sleep(.1)
        else: raise AssertionError('Owned standalone failed to start')
        for name in await db.list_collection_names():
            rows=await db[name].find({}).to_list(length=200)
            if rows: await target[name].insert_many(rows)
        await ensure_voice_studio_indexes(target)
        with pytest.raises(suppression.SuppressionUnavailable): await resolve(target,job)
        assert not (await target.outreach_voice_studio_jobs.find_one({'_id':job['_id']})).get('review')
        assert (await target.outreach_voices.find_one({}))['studio_job_id']==job['_id']
        assert (await target.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==3
        assert (await target.outreach_accounts.find_one({'_id':'a'}))['status']=='active'
    finally:
        try:
            await client.drop_database(target.name)
        finally:
            client.close()
            process.terminate();process.wait(timeout=10)
