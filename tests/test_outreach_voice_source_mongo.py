"""Real snapshot/majority source transactions, strict journals and denial."""
import asyncio
from copy import deepcopy
import os
import socket
import subprocess
import uuid
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient,AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError,PyMongoError
from db.indexes import ensure_voice_studio_indexes
from outreach.core import suppression,voice_key_custody
from outreach.core.voice_studio import VoiceStudio
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_source_review import VoiceSourceReview,PreviousKey
from outreach.core.sender_execution import SenderExecution
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.erasure import OutreachErasure
from tests.test_outreach_voice_studio_review_mongo import review_db
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_source_review import KEY,EVIDENCE

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned loopback replica set is opt-in')]


async def ready(db,monkeypatch,kind='legacy_fernet'):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE',kind)
    monkeypatch.delenv('OUTREACH_ELEVENLABS_API_KEY_ENC',raising=False)
    monkeypatch.delenv('OUTREACH_ELEVENLABS_KEY_GENERATION',raising=False)
    monkeypatch.setenv('ELEVENLABS_API_KEY',KEY if kind=='legacy_fernet' else '')
    if kind=='kms_v1':
        monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC',await voice_key_custody.seal_key(KEY,'g1'))
        monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION','g1')
    prior=voice_key_custody.capture_configuration()
    monkeypatch.setenv('OUTREACH_VOICE_STUDIO_ENABLED','true')
    service=VoiceStudio(db)
    job=await service.queue('w','actor','clone','original',name='Original',audio=generate_mock_voice_wav(duration_s=20),consent=True)
    await service.run('w',job['_id'],provider=AsyncMock(return_value={'voice_id':'original-remote','requires_verification':False}))
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
    monkeypatch.setenv('ELEVENLABS_API_KEY','')
    monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC',await voice_key_custody.seal_key(KEY,'g2'))
    monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION','g2')
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED','OUTREACH_VOICE_STUDIO_ENABLED','OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag,'false')
    await db.outreach_accounts.insert_one({'_id':'a','id':'a','workspace_id':'w','status':'active'})
    await db.outreach_campaigns.insert_one({'_id':'c','id':'c','workspace_id':'w','status':'active','authorization_revision':3})
    await db.outreach_sender_execution.insert_one({**SenderExecution.scope('w','a'),'status':'in_flight',
        'physical_request_token':'held','owner_token':'original-owner','permission':{'latched':False}})
    await db.outreach_execution_permissions.insert_one({**ExecutionPermission.scope('w','a'),'latched':False})
    return await db.outreach_voices.find_one({'workspace_id':'w','id':job['voice_id']}),prior


async def migrate(db,profile,prior,digest=None,previous=None):
    service=VoiceSourceReview(db)
    digest=digest or (await service.inspect('w',profile['id']))['review_digest']
    return await service.migrate('w',profile['id'],'operator',EVIDENCE,digest,workers_drained=True,
        previous_key=previous or PreviousKey(prior.storage,prior.policy[0],prior.generation))


@pytest.mark.parametrize('kind',['legacy_fernet','kms_v1'])
async def test_real_source_journal_and_stop_commit_together_without_open_in_callbacks(review_db,scoped,monkeypatch,kind):
    db=review_db;profile,prior=await ready(db,monkeypatch,kind)
    before=await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w'})
    callback=False;opened=scoped.open;original=suppression.mutate_suppression
    async def control(database,workspace,operation):
        async def wrapped(current):
            nonlocal callback
            callback=True
            try:return await operation(current)
            finally:callback=False
        return await original(database,workspace,wrapped)
    async def open_key(*args):
        assert not callback,'Key opening must not occur in retryable callbacks'
        return await opened(*args)
    monkeypatch.setattr(suppression,'mutate_suppression',control)
    monkeypatch.setattr(scoped,'open',open_key)
    result=await migrate(db,profile,prior)
    assert result['current_matches'] and not result['activation_allowed']
    after=await db.outreach_voices.find_one({'workspace_id':'w','id':profile['id']})
    assert after['studio_review_required'] and after['revision']==profile['revision']+1
    assert after['consent']==profile['consent'] and after['status']=='review_required'
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4
    execution=await db.outreach_sender_execution.find_one(SenderExecution.scope('w','a'))
    assert execution['physical_request_token']=='held' and execution['permission']['latched']
    saved=await db.outreach_voice_studio_jobs.find_one({'workspace_id':'w'})
    for field in ('receipt','owner','possible_at','provider_source_digest'):
        assert saved[field]==before[field]


async def test_concurrent_identical_source_review_stops_once(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    digest=(await VoiceSourceReview(db).inspect('w',profile['id']))['review_digest']
    results=await asyncio.gather(*(migrate(db,profile,prior,digest) for _ in range(4)))
    assert all(result==results[0] for result in results)
    assert await db.outreach_voice_source_migrations.count_documents({})==1
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4


async def test_lost_ack_reuses_journal_without_secret_read(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    digest=(await VoiceSourceReview(db).inspect('w',profile['id']))['review_digest']
    original=suppression.mutate_suppression;lost=False
    async def control(*args):
        nonlocal lost
        result=await original(*args)
        if result.get('status')=='completed' and not lost:
            lost=True;raise RuntimeError('Lost acknowledgement')
        return result
    monkeypatch.setattr(suppression,'mutate_suppression',control)
    with pytest.raises(RuntimeError):await migrate(db,profile,prior,digest)
    assert (await migrate(db,profile,prior,digest,lambda:pytest.fail('No secret reread')))['current_matches']
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['authorization_revision']==4


async def test_failed_journal_insert_rolls_back_profile_and_authority(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    insert=AsyncIOMotorCollection.insert_one
    async def failing(collection,*args,**kwargs):
        if collection.name=='outreach_voice_source_migrations':raise ValueError('Abort journal')
        return await insert(collection,*args,**kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection,'insert_one',failing)
    with pytest.raises(ValueError):await migrate(db,profile,prior)
    assert (await db.outreach_voices.find_one({'id':profile['id']}))['provider_source_digest']==prior.source
    assert (await db.outreach_campaigns.find_one({'_id':'c'}))['status']=='active'
    assert (await db.outreach_accounts.find_one({'_id':'a'}))['status']=='active'
    assert await db.outreach_voice_source_migrations.count_documents({})==0


async def test_replacement_profile_during_key_open_is_not_relabelled(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    opening=scoped.open
    async def replaced(*args):
        value=await opening(*args)
        await db.outreach_voices.update_one({'id':profile['id']},{'$set':{'elevenlabs_voice_id':'replacement'}})
        return value
    monkeypatch.setattr(scoped,'open',replaced)
    with pytest.raises(ValueError):await migrate(db,profile,prior)
    after=await db.outreach_voices.find_one({'id':profile['id']})
    assert after['provider_source_digest']==prior.source and after['elevenlabs_voice_id']=='replacement'


async def test_new_matching_authority_during_open_invalidates_inspection(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    opening=scoped.open
    async def inserted(*args):
        value=await opening(*args)
        await db.outreach_accounts.insert_one({'_id':'new','id':'new','workspace_id':'w','status':'active'})
        return value
    monkeypatch.setattr(scoped,'open',inserted)
    with pytest.raises(ValueError):await migrate(db,profile,prior)
    assert (await db.outreach_voices.find_one({'id':profile['id']}))['provider_source_digest']==prior.source


async def test_closed_erasure_denies_source_install_and_authority_creation(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
    await OutreachErasure(db).request('w','actor')
    opening=AsyncMock(side_effect=AssertionError('No KMS for closed tenant'))
    monkeypatch.setattr(scoped,'open',opening)
    with pytest.raises((ValueError,suppression.SuppressionUnavailable)):await migrate(db,profile,prior)
    opening.assert_not_awaited()
    assert await db.outreach_voice_source_migrations.count_documents({})==0
    assert (await db.outreach_voices.find_one({'id':profile['id']}))['provider_source_digest']==prior.source


async def test_multiple_rotations_preserve_root_with_default_naive_utc(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch,kind='kms_v1')
    await migrate(db,profile,prior)
    prior=voice_key_custody.capture_configuration()
    monkeypatch.setenv('OUTREACH_ELEVENLABS_API_KEY_ENC',await voice_key_custody.seal_key(KEY,'g3'))
    monkeypatch.setenv('OUTREACH_ELEVENLABS_KEY_GENERATION','g3')
    profile=await db.outreach_voices.find_one({'id':profile['id']})
    assert profile['created_at'].tzinfo is None
    await migrate(db,profile,prior)
    receipts=await db.outreach_voice_source_migrations.find({}).to_list(length=3)
    assert len(receipts)==2 and receipts[0]['root_clone_digest']==receipts[1]['root_clone_digest']


async def test_actual_journal_indexes_are_unique_and_ttl_free(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    await db.outreach_voice_source_migrations.create_index('at',expireAfterSeconds=1,name='old_destructive_ttl')
    await ensure_voice_studio_indexes(db)
    await migrate(db,profile,prior)
    indexes=await db.outreach_voice_source_migrations.index_information()
    assert indexes['voice_source_review_v1']['unique'] and not any('expireAfterSeconds' in row for row in indexes.values())
    receipt=await db.outreach_voice_source_migrations.find_one({})
    receipt['_id']='duplicate-journal'
    with pytest.raises(DuplicateKeyError):await db.outreach_voice_source_migrations.insert_one(receipt)


async def test_erasure_archives_continuity_and_purges_private_journal(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    await migrate(db,profile,prior)
    await db.workspaces.insert_one({'workspace_id':'w','owner_id':'actor'})
    service=OutreachErasure(db);await service.request('w','actor')
    view=await service.inspect('w')
    await service.finish('w','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert await db.outreach_voice_source_migrations.count_documents({'workspace_id':'w'})==0
    hold=await db.outreach_erasure_holds.find_one({'workspace_id':'w','kind':'voice_source_continuity'})
    assert hold['provenance']=='same_key_continuity' and not hold['activation_allowed']
    assert KEY not in str(hold) and EVIDENCE not in str(hold) and 'original-remote' not in str(hold)


async def test_other_workspace_and_replacement_retry_never_change(review_db,scoped,monkeypatch):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    await db.outreach_accounts.insert_one({'_id':'other-a','id':'a','workspace_id':'other','status':'active'})
    digest=(await VoiceSourceReview(db).inspect('w',profile['id']))['review_digest']
    await migrate(db,profile,prior,digest)
    await db.outreach_voices.update_one({'id':profile['id']},{'$set':{'elevenlabs_voice_id':'replacement'}})
    result=await migrate(db,profile,prior,digest,lambda:pytest.fail('No reread'))
    assert not result['current_matches']
    assert (await db.outreach_voices.find_one({'id':profile['id']}))['elevenlabs_voice_id']=='replacement'
    assert (await db.outreach_accounts.find_one({'workspace_id':'other'}))['status']=='active'


async def test_actual_standalone_continuity_denies_without_partial_changes(review_db,scoped,monkeypatch,tmp_path):
    db=review_db;profile,prior=await ready(db,monkeypatch)
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',27029))!=0,'Preserve existing service'
    root=tmp_path/'standalone';root.mkdir()
    process=subprocess.Popen(['/opt/homebrew/bin/mongod','--dbpath',str(root),'--port','27029','--bind_ip','127.0.0.1',
        '--logpath',str(root/'mongo.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=AsyncIOMotorClient('mongodb://127.0.0.1:27029/?directConnection=true',serverSelectionTimeoutMS=500)
    target=client['test_unravler_source_sa_'+uuid.uuid4().hex]
    try:
        for _ in range(40):
            try:await client.admin.command('ping');break
            except PyMongoError:await asyncio.sleep(.1)
        else:raise AssertionError('Owned standalone failed to start')
        for name in await db.list_collection_names():
            rows=await db[name].find({}).to_list(length=200)
            if rows:await target[name].insert_many(rows)
        await ensure_voice_studio_indexes(target)
        opening=AsyncMock(side_effect=AssertionError('No key opening'))
        monkeypatch.setattr(scoped,'open',opening)
        with pytest.raises(suppression.SuppressionUnavailable):await migrate(target,profile,prior)
        opening.assert_not_awaited()
        assert (await target.outreach_voices.find_one({'id':profile['id']}))['provider_source_digest']==prior.source
        assert (await target.outreach_campaigns.find_one({'_id':'c'}))['status']=='active'
        assert await target.outreach_voice_source_migrations.count_documents({})==0
    finally:
        try:await client.drop_database(target.name)
        finally:
            client.close();process.terminate();process.wait(timeout=10)
