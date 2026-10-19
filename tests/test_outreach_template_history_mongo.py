"""Guarded digest-history HTTP, indexed storage, pagination and authority."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os

from bson import BSON, Code, ObjectId
from fastapi import HTTPException
import pytest

from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, api_client, remove
from tests.test_outreach_template_saves_mongo import post
from tests.test_outreach_template_metadata_mongo import edit
from outreach.core.template_governance import template_review
from outreach.core.template_revision_checkpoints import checkpoint_for

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned native Mongo opt-in')]


async def seed(db,prepare=True):
    await seed_authority(db);result=await post(db);assert result.status_code==200,result.text
    row=await db.outreach_templates.find_one({});identity=template_review(row,'workspace')['identity_digest']
    if prepare:
        from outreach.core.template_history_storage import ensure_history_index
        await ensure_history_index(db)
    return row,identity


async def get(db,row,identity,**query):
    async with await api_client(db) as api:
        return await api.get('/sequences/templates/'+row['id']+'/revision-checkpoints',
            params={'identity_digest':identity,**query})


async def test_missing_index_has_no_history_fallback(replica_db):
    row,identity=await seed(replica_db,False)
    result=await get(replica_db,row,identity);assert result.status_code==503,result.text


async def test_http_pages_digest_history_after_deletion_without_content_or_replay(replica_db):
    row,identity=await seed(replica_db);await edit(replica_db,row)
    current=await replica_db.outreach_templates.find_one({});await remove(replica_db,current)
    before=await replica_db.outreach_template_revisions.find({}).to_list(10)
    first=await get(replica_db,row,identity,page_size='2');assert first.status_code==200,first.text
    assert first.headers['cache-control']=='no-store'
    assert [x['event'] for x in first.json()['items']]==['created','metadata']
    second=await get(replica_db,row,identity,page_size='2',cursor=first.json()['next_cursor'])
    assert second.status_code==200 and [x['event'] for x in second.json()['items']]==['deleted']
    assert second.json()['next_cursor'] is None and not second.json()['content_available'] and not second.json()['restore_available']
    assert await replica_db.outreach_template_revisions.find({}).to_list(10)==before
    assert await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('role',['owner','admin','editor','viewer','client'])
async def test_current_workspace_readers_can_read_but_receive_no_execution_permission(replica_db,role):
    row,identity=await seed(replica_db)
    await replica_db.workspace_members.update_one({}, {'$set':{'role':role}})
    result=await get(replica_db,row,identity);assert result.status_code==200,result.text
    assert not result.json()['execution_authorized'] and not result.json()['capture_complete']


@pytest.mark.parametrize('fault',['uid','duplicate_uid','stopped','role','code_role','code_status','erased','closed'])
async def test_changed_or_malformed_authority_denies_before_disclosure(replica_db,fault):
    from outreach.core.erasure import stop_identity,OutreachErasure
    row,identity=await seed(replica_db)
    if fault=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'different'}})
    elif fault=='duplicate_uid':await replica_db.users.insert_one({'user_id':'other','firebase_uid':'original-uid'})
    elif fault=='stopped':await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    elif fault=='role':await replica_db.workspace_members.update_one({}, {'$set':{'role':'unknown'}})
    elif fault=='code_role':await replica_db.workspace_members.update_one({}, {'$set':{'role':Code('admin')}})
    elif fault=='code_status':await replica_db.users.update_one({}, {'$set':{'status':Code('active')}})
    elif fault=='erased':await stop_identity(replica_db,'original-uid')
    else:
        await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
        await OutreachErasure(replica_db).request('workspace','actor')
    result=await get(replica_db,row,identity);assert result.status_code in {403,409,503},result.text
    assert 'items' not in result.json()


@pytest.mark.parametrize('query',[{'page_size':'0'},{'page_size':'26'},{'page_size':'01'},{'page_size':'true'},
    {'page_size':'1.0'},{'cursor':''},{'unknown':'value'},{'identity_digest':'bad'}])
async def test_http_query_contract_rejects_coercion_unknown_fields_and_bad_cursor(replica_db,query):
    row,identity=await seed(replica_db)
    result=await get(replica_db,row,identity,**query);assert result.status_code==422,result.text


async def test_duplicate_query_keys_are_rejected(replica_db):
    row,identity=await seed(replica_db)
    async with await api_client(replica_db) as api:
        result=await api.get('/sequences/templates/'+row['id']+'/revision-checkpoints',
            params=[('identity_digest',identity),('page_size','1'),('page_size','2')])
    assert result.status_code==422


async def test_append_between_pages_holds_original_cursor(replica_db):
    row,identity=await seed(replica_db);await edit(replica_db,row)
    first=await get(replica_db,row,identity,page_size='1');assert first.status_code==200
    await edit(replica_db,await replica_db.outreach_templates.find_one({}),name='Later')
    result=await get(replica_db,row,identity,page_size='1',cursor=first.json()['next_cursor'])
    assert result.status_code==409


async def test_old_native_history_does_not_silently_follow_public_id_replacement(replica_db):
    row,identity=await seed(replica_db);await remove(replica_db,row)
    replacement={**row,'_id':ObjectId()};await replica_db.outreach_templates.insert_one(replacement)
    await edit(replica_db,replacement)
    result=await get(replica_db,row,identity);assert result.status_code==200
    assert [x['event'] for x in result.json()['items']]==['created','deleted']
    foreign=await get(replica_db,row,'a'*64);assert foreign.status_code==404


@pytest.mark.parametrize('fault',['orphan_terminal','changed_parent','unknown_field','oversized_actor','oversized_id'])
async def test_full_history_validation_holds_bad_data_before_paging(replica_db,fault):
    row,identity=await seed(replica_db);await edit(replica_db,row)
    if fault=='orphan_terminal':
        await remove(replica_db,await replica_db.outreach_templates.find_one({}))
        await replica_db.outreach_template_revisions.delete_one({'event':'metadata'})
    elif fault=='changed_parent':await replica_db.outreach_template_revisions.update_one({'event':'metadata'},{'$set':{'predecessor_review_digest':'a'*64}})
    elif fault=='unknown_field':await replica_db.outreach_template_revisions.update_one({}, {'$set':{'secret':'do not project this away'}})
    elif fault=='oversized_actor':await replica_db.outreach_template_revisions.update_one({}, {'$set':{'recorded_by':'x'*100_000}})
    else:
        original=await replica_db.outreach_template_revisions.find_one({});await replica_db.outreach_template_revisions.delete_one({'_id':original['_id']})
        await replica_db.outreach_template_revisions.insert_one({**original,'_id':'z'*100_000})
    result=await get(replica_db,row,identity,page_size='1');assert result.status_code==409,result.text
    assert 'items' not in result.json() and 'do not project' not in result.text


async def test_storage_installation_is_explicit_idempotent_and_never_ttl_or_repair(replica_db):
    from outreach.core import template_history_storage as storage
    row,identity=await seed(replica_db,False);before=await replica_db.outreach_template_revisions.find({}).to_list(5)
    await storage.ensure_history_index(replica_db);await storage.ensure_history_index(replica_db)
    indexes=await replica_db.outreach_template_revisions.index_information()
    assert set(indexes)=={'_id_',storage.INDEX_NAME} and indexes[storage.INDEX_NAME]['key']==storage.INDEX_KEYS
    assert await replica_db.outreach_template_revisions.find({}).to_list(5)==before
    await replica_db.outreach_template_revisions.create_index('recorded_at',expireAfterSeconds=99999999,name='legacy_ttl')
    with pytest.raises(HTTPException):await storage.ensure_history_index(replica_db)
    assert 'legacy_ttl' in await replica_db.outreach_template_revisions.index_information()
    assert (await get(replica_db,row,identity)).status_code==503


async def test_unknown_read_commit_returns_no_payload_and_retry_only_reads(replica_db,monkeypatch):
    from outreach.core import template_history as history
    from outreach.core.suppression import SuppressionUnavailable
    row,identity=await seed(replica_db);before=await replica_db.outreach_template_revisions.find({}).to_list(5);commit=history.mutate_suppression
    async def lost(*args,**kwargs):
        await commit(*args,**kwargs);raise SuppressionUnavailable('Owned lost acknowledgement')
    monkeypatch.setattr(history,'mutate_suppression',lost)
    result=await get(replica_db,row,identity);assert result.status_code==503 and 'items' not in result.json()
    monkeypatch.setattr(history,'mutate_suppression',commit)
    assert (await get(replica_db,row,identity)).status_code==200
    assert await replica_db.outreach_template_revisions.find({}).to_list(5)==before


async def test_standalone_cannot_disclose_transactional_history(real_db):
    from outreach.core import template_history_storage as storage,template_history as history
    from tests.test_outreach_template_revision_checkpoints import record
    await seed_authority(real_db);row=record(1);entry=checkpoint_for(row,'actor',datetime(2026,10,19,tzinfo=timezone.utc))
    await real_db.outreach_template_revisions.insert_one(entry);await storage.ensure_history_index(real_db)
    with pytest.raises(HTTPException) as caught:
        await history.read_history(real_db,'workspace','actor','original-uid',row['id'],entry['identity_digest'])
    assert caught.value.status_code==503


async def test_server_projection_bounds_oversized_native_id_and_explain_uses_index(replica_db):
    from outreach.core import template_history_storage as storage
    row,identity=await seed(replica_db)
    explain=await replica_db.command('explain',{'aggregate':'outreach_template_revisions',
        'pipeline':storage.history_pipeline('workspace',identity,1001),'cursor':{},
        'hint':storage.INDEX_NAME,'collation':{'locale':'simple'}},verbosity='executionStats')
    def values(value,key):
        if isinstance(value,dict):
            return ([value[key]] if key in value else [])+[x for v in value.values() for x in values(v,key)]
        return [x for v in value for x in values(v,key)] if isinstance(value,list) else []
    assert storage.INDEX_NAME in values(explain,'indexName')
    assert values(explain,'totalDocsExamined') and max(values(explain,'totalDocsExamined'))==1
    original=await replica_db.outreach_template_revisions.find_one({})
    await replica_db.outreach_template_revisions.delete_one({'_id':original['_id']})
    await replica_db.outreach_template_revisions.insert_one({**original,'_id':'x'*100_000})
    projected=await replica_db.outreach_template_revisions.aggregate(storage.history_pipeline('workspace',identity,1001),
        hint=storage.INDEX_NAME,collation={'locale':'simple'}).to_list(1001)
    assert len(projected)==1 and set(projected[0])=={'row','bytes'}
    assert projected[0]['row'] is None and projected[0]['bytes']>100_000 and len(BSON.encode(projected[0]))<100


@pytest.mark.parametrize('owner',[False,True])
async def test_all_strict_access_observations_share_owning_session(replica_db,monkeypatch,owner):
    from motor.motor_asyncio import AsyncIOMotorCollection
    from outreach.core import template_access as access
    row,identity=await seed(replica_db);sessions=[];original=access.inspect_access;active=False
    if owner:
        await replica_db.workspace_members.delete_many({})
        await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    find,one=AsyncIOMotorCollection.find,AsyncIOMotorCollection.find_one
    observed=[]
    def capture_find(collection,*args,**kwargs):
        if active and collection.database.name==replica_db.name and collection.name in {'users','workspace_members','workspaces'}:
            observed.append((collection.name,kwargs.get('session')))
        return find(collection,*args,**kwargs)
    async def capture_one(collection,*args,**kwargs):
        if active and collection.database.name==replica_db.name and collection.name in {'account_erasure_tombstones','outreach_suppression_guards'}:
            observed.append((collection.name,kwargs.get('session')))
        return await one(collection,*args,**kwargs)
    async def capture_access(*args,**kwargs):
        nonlocal active
        sessions.append(kwargs['session'])
        active=True
        try:return await original(*args,**kwargs)
        finally:active=False
    monkeypatch.setattr(access,'inspect_access',capture_access)
    monkeypatch.setattr(AsyncIOMotorCollection,'find',capture_find)
    monkeypatch.setattr(AsyncIOMotorCollection,'find_one',capture_one)
    result=await get(replica_db,row,identity);assert result.status_code==200,result.text
    assert sessions and {'users','workspace_members','account_erasure_tombstones','outreach_suppression_guards'}<=set(x[0] for x in observed)
    assert all(session is sessions[-1] for _,session in observed)
    if owner:assert 'workspaces' in {x[0] for x in observed}


@pytest.mark.parametrize('fault',['count','bytes','index_drift','timeout'])
async def test_storage_limits_and_failure_never_disclose_partial_history(replica_db,monkeypatch,fault):
    from outreach.core import template_history as history,template_history_storage as storage
    from pymongo.errors import ExecutionTimeout
    row,identity=await seed(replica_db);await edit(replica_db,row)
    if fault=='count':monkeypatch.setattr(history,'MAX_CHECKPOINTS',1)
    elif fault=='bytes':monkeypatch.setattr(history,'MAX_HISTORY_BYTES',1)
    else:
        load=history._load_rows
        async def changed(*args):
            rows=await load(*args)
            if fault=='timeout':raise ExecutionTimeout('private internal query')
            await replica_db.outreach_template_revisions.drop_index(storage.INDEX_NAME)
            return rows
        monkeypatch.setattr(history,'_load_rows',changed)
    result=await get(replica_db,row,identity,page_size='1')
    assert result.status_code in {409,503} and 'items' not in result.json() and 'private internal' not in result.text


async def test_shared_guard_orders_read_before_later_edit_and_invalidates_next_page(replica_db,monkeypatch):
    from outreach.core import template_history as history
    row,identity=await seed(replica_db);await edit(replica_db,row)
    entered,released=asyncio.Event(),asyncio.Event();load=history._load_rows
    async def pause(*args):
        rows=await load(*args);entered.set();await released.wait();return rows
    monkeypatch.setattr(history,'_load_rows',pause)
    reading=asyncio.create_task(get(replica_db,row,identity,page_size='1'))
    await asyncio.wait_for(entered.wait(),5)
    editing=asyncio.create_task(edit(replica_db,await replica_db.outreach_templates.find_one({}),name='Later'))
    try:
        await asyncio.sleep(0.05);assert not editing.done()
    finally:released.set()
    first,result=await asyncio.gather(reading,editing)
    assert first.status_code==200 and result['status']=='updated' and result['new_revision']==3
    assert (await replica_db.outreach_templates.find_one({}))['name']=='Later'
    monkeypatch.setattr(history,'_load_rows',load)
    assert (await get(replica_db,row,identity,page_size='1',cursor=first.json()['next_cursor'])).status_code==409


async def test_index_preparation_never_replaces_conflicting_named_index(replica_db):
    from outreach.core import template_history_storage as storage
    await seed(replica_db,False)
    await replica_db.outreach_template_revisions.create_index('workspace_id',name=storage.INDEX_NAME)
    before=await replica_db.outreach_template_revisions.index_information()
    with pytest.raises(HTTPException):await storage.ensure_history_index(replica_db)
    assert await replica_db.outreach_template_revisions.index_information()==before


async def test_removed_history_invalidates_cursor_without_repair_or_domain_write(replica_db):
    row,identity=await seed(replica_db);await edit(replica_db,row)
    first=await get(replica_db,row,identity,page_size='1');assert first.status_code==200
    await replica_db.outreach_template_revisions.delete_many({})
    current=await replica_db.outreach_templates.find_one({})
    assert (await get(replica_db,row,identity,page_size='1',cursor=first.json()['next_cursor'])).status_code==409
    assert (await get(replica_db,row,identity)).status_code==404
    assert await replica_db.outreach_templates.find_one({})==current
    assert await replica_db.outreach_template_revisions.count_documents({})==0
