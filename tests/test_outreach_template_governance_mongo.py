"""Actual Mongo review, guarded CRUD, HTTP and failure-ordering checks."""
from copy import deepcopy
import os
import asyncio

from bson import ObjectId
from fastapi import HTTPException
import pytest

from outreach.core.template_governance import deletion_precondition, template_review
from outreach.core.template_governance import authorize_delete, delete_template, scoped_review, create_template
from outreach.core.suppression import mutate_suppression
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from outreach.core import template_governance as governance
from outreach.core.authorization import canonical_hash
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance import record

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]


async def seed(db):
    row=record()
    await db.outreach_templates.insert_one(row)
    saved=await db.outreach_templates.find_one({'_id':row['_id']})
    review=template_review(saved,'workspace')
    return saved,deletion_precondition(saved,'workspace',review['revision'],review['review_digest'])


async def test_exact_review_can_target_only_its_native_template(replica_db):
    row,query=await seed(replica_db)
    other={**row,'_id':ObjectId(),'workspace_id':'other'}
    await replica_db.outreach_templates.insert_one(other)
    result=await replica_db.outreach_templates.delete_one(query)
    assert result.deleted_count==1
    assert await replica_db.outreach_templates.find_one({'_id':other['_id']})==other


@pytest.mark.parametrize('change',[{'name':'Changed'},{'future_metadata':'added'},{'template_revision':1}])
async def test_raw_record_drift_between_review_and_cas_denies(replica_db,change):
    row,query=await seed(replica_db)
    await replica_db.outreach_templates.update_one({'_id':row['_id']},{'$set':change})
    assert (await replica_db.outreach_templates.delete_one(query)).deleted_count==0
    assert await replica_db.outreach_templates.count_documents({})==1


async def test_recreated_public_identity_cannot_reuse_old_review(replica_db):
    row,query=await seed(replica_db)
    await replica_db.outreach_templates.delete_one({'_id':row['_id']})
    replacement={**row,'_id':ObjectId()}
    await replica_db.outreach_templates.insert_one(replacement)
    assert (await replica_db.outreach_templates.delete_one(query)).deleted_count==0
    assert await replica_db.outreach_templates.find_one({'_id':replacement['_id']})==replacement


async def test_operator_looking_nested_data_is_literal(replica_db):
    row=record();row['future_metadata']={'$ne':'literal'}
    await replica_db.outreach_templates.insert_one(row)
    saved=await replica_db.outreach_templates.find_one({'_id':row['_id']})
    review=template_review(saved,'workspace')
    query=deletion_precondition(saved,'workspace',0,review['review_digest'])
    assert (await replica_db.outreach_templates.delete_one(query)).deleted_count==1


async def seed_authority(db):
    await db.users.insert_one({'user_id':'actor','firebase_uid':'original-uid','status':'active'})
    await db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'actor','role':'admin'})


async def authorize(db,uid='original-uid'):
    async def operation(current):
        await authorize_delete(current,'actor',uid)
    return await mutate_suppression(db,'workspace',operation)


async def test_authority_fences_current_native_user_and_role_without_deleting(replica_db):
    await seed_authority(replica_db)
    row=record();await replica_db.outreach_templates.insert_one(row)
    await authorize(replica_db)
    assert (await replica_db.users.find_one({}))['template_authority_revision']==1
    assert (await replica_db.workspace_members.find_one({}))['template_authority_revision']==1
    assert await replica_db.outreach_templates.count_documents({})==1


@pytest.mark.parametrize('case',['wrong_uid','user_stopped','uid_replaced','viewer','member_stopped','duplicate_user','duplicate_uid','duplicate_array_uid','duplicate_member','erased_identity'])
async def test_authority_rejects_changed_or_ambiguous_access_and_rolls_back(replica_db,case):
    await seed_authority(replica_db)
    uid='original-uid'
    if case=='wrong_uid':uid='other-uid'
    elif case=='user_stopped':await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    elif case=='uid_replaced':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'replacement'}})
    elif case=='viewer':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
    elif case=='member_stopped':await replica_db.workspace_members.update_one({}, {'$set':{'status':'inactive'}})
    elif case=='duplicate_user':await replica_db.users.insert_one({'user_id':'actor','firebase_uid':uid})
    elif case=='duplicate_uid':await replica_db.users.insert_one({'user_id':'other-actor','firebase_uid':uid})
    elif case=='duplicate_array_uid':await replica_db.users.insert_one({'user_id':'other-actor','firebase_uid':[uid]})
    elif case=='duplicate_member':await replica_db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'actor','role':'admin'})
    else:await replica_db.account_erasure_tombstones.insert_one({'_id':canonical_hash(['firebase_identity',uid])})
    with pytest.raises(HTTPException) as caught:await authorize(replica_db,uid)
    assert caught.value.status_code==403
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def test_owned_workspace_without_membership_requires_current_owner(replica_db):
    await seed_authority(replica_db);await replica_db.workspace_members.delete_many({})
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    await authorize(replica_db)
    await replica_db.workspaces.update_one({}, {'$set':{'owner_id':'replacement'}})
    with pytest.raises(HTTPException):await authorize(replica_db)


async def test_duplicate_workspace_with_different_owner_denies_owner_fallback(replica_db):
    await seed_authority(replica_db);await replica_db.workspace_members.delete_many({})
    await replica_db.workspaces.insert_many([{'workspace_id':'workspace','owner_id':'actor'},
        {'workspace_id':'workspace','owner_id':'other'}])
    with pytest.raises(HTTPException) as caught:await authorize(replica_db)
    assert caught.value.status_code==403
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def remove(db,row=None,**changes):
    row=row or await db.outreach_templates.find_one({})
    review=scoped_review(row,'workspace','actor','original-uid')
    payload={key:review[key] for key in ('revision','review_digest','identity_digest','scope_digest')}
    payload.update(changes)
    return await delete_template(db,'workspace','actor',row['id'],authenticated_uid='original-uid',**payload)


async def test_guarded_delete_preserves_frozen_campaign_and_execution_records(replica_db):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    for name in ['outreach_campaigns','outreach_sequence_versions','outreach_tasks','outreach_leads']:
        await replica_db[name].insert_one({'workspace_id':'workspace','id':'retained','template_copy':deepcopy(row)})
    before={name:await replica_db[name].find({}).to_list(10) for name in ['outreach_campaigns','outreach_sequence_versions','outreach_tasks','outreach_leads']}
    result=await remove(replica_db,row)
    assert result['status']=='deleted' and result['identity_digest']==template_review(row,'workspace')['identity_digest']
    assert await replica_db.outreach_templates.count_documents({})==0
    for name,rows in before.items():
        assert await replica_db[name].find({}).to_list(10)==rows


@pytest.mark.parametrize('change',['native','content','revision','duplicate','custom_marker','workspace_array','public_array'])
async def test_delete_rechecks_original_native_review_and_rolls_back_authority(replica_db,change):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    if change=='native':
        await replica_db.outreach_templates.delete_one({})
        await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
    elif change=='duplicate':await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
    else:
        edits={'content':{'name':'changed'},'revision':{'template_revision':1},'custom_marker':{'is_custom':False},
            'workspace_array':{'workspace_id':['workspace','other']},'public_array':{'id':[row['id'],'other']}}
        await replica_db.outreach_templates.update_one({}, {'$set':edits[change]})
    before=await replica_db.outreach_templates.find({}).to_list(10)
    with pytest.raises(HTTPException) as caught:await remove(replica_db,row)
    assert caught.value.status_code in {404,409}
    assert await replica_db.outreach_templates.find({}).to_list(10)==before
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def test_repeated_delete_is_not_confirmation_or_replay(replica_db):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    await remove(replica_db,row)
    with pytest.raises(HTTPException) as caught:await remove(replica_db,row)
    assert caught.value.status_code==404
    assert (await replica_db.users.find_one({}))['template_authority_revision']==1


async def test_guarded_create_assigns_revision_and_retains_native_identity_on_collision(replica_db):
    await seed_authority(replica_db);row=record();row.pop('_id');row['user_id']='actor'
    saved=await create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid')
    assert saved['template_revision']==1 and '_id' not in saved
    before=await replica_db.outreach_templates.find_one({})
    with pytest.raises(HTTPException) as caught:await create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid')
    assert caught.value.status_code==409
    assert await replica_db.outreach_templates.find_one({})==before


async def api_client(db):
    import httpx
    from fastapi import FastAPI
    from api.deps import get_current_user
    from db.mongo import get_db
    from outreach.api.sequences import router
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':'actor','firebase_uid':'original-uid','default_workspace_id':'workspace'}
    app.dependency_overrides[get_db]=lambda:db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')


def delete_payload(review):
    return {key:review[key] for key in ['contract_version','workspace_id','revision','review_digest','identity_digest','scope_digest']}


async def test_actual_api_gallery_supplies_native_review_and_delete_receipt(replica_db):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    async with await api_client(replica_db) as api:
        listed=await api.get('/sequences/templates');assert listed.status_code==200
        saved=next(item for item in listed.json() if item['id']==row['id'])
        assert '_id' not in saved
        review=saved['deletion_review']
        assert review['reviewable'] and not review['deletion_authorized'] and not review['execution_authorized']
        result=await api.request('DELETE','/sequences/templates/'+row['id']+'/reviewed',json=delete_payload(review))
        assert result.status_code==200,result.text
        assert result.json()=={**delete_payload(review),'status':'deleted','template_id':row['id']}
    assert await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('change',[{'revision':True},{'revision':1.0},{'revision':'0'},{'review_digest':'bad'},
    {'scope_digest':None},{'identity_digest':[]},{'workspace_id':[]},{'contract_version':True},{'unknown':'field'}])
async def test_actual_delete_http_contract_rejects_coercion_and_unknown_fields(replica_db,change):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    body=delete_payload(scoped_review(row,'workspace','actor','original-uid'));body.update(change)
    async with await api_client(replica_db) as api:
        result=await api.request('DELETE','/sequences/templates/'+row['id']+'/reviewed',json=body)
    assert result.status_code==422,result.text
    assert await replica_db.outreach_templates.count_documents({})==1


async def test_old_unreviewed_delete_is_denied(replica_db):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    async with await api_client(replica_db) as api:
        result=await api.delete('/sequences/templates/'+row['id'])
    assert result.status_code==422 and await replica_db.outreach_templates.count_documents({})==1


@pytest.mark.parametrize('change',[{'workspace_id':'other'},{'scope_digest':'a'*64},{'identity_digest':'b'*64},{'review_digest':'c'*64}])
async def test_cross_scope_or_stale_api_review_cannot_delete(replica_db,change):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    body=delete_payload(scoped_review(row,'workspace','actor','original-uid'));body.update(change)
    async with await api_client(replica_db) as api:
        result=await api.request('DELETE','/sequences/templates/'+row['id']+'/reviewed',json=body)
    assert result.status_code in {403,409}
    assert await replica_db.outreach_templates.count_documents({})==1


async def test_actual_create_api_uses_guarded_revisioned_insertion(replica_db):
    await seed_authority(replica_db)
    node={'id':'root','type':'visit_profile','delay_hours':0,'config':{}}
    async with await api_client(replica_db) as api:
        result=await api.post('/sequences/templates',json={'name':'Saved','nodes':[node],'edges':[],'tree':[node]})
        assert result.status_code==200,result.text
        identifier=result.json()['template']['id']
        listed=await api.get('/sequences/templates')
        entry=next(item for item in listed.json() if item['id']==identifier)
        removed=await api.request('DELETE','/sequences/templates/'+identifier+'/reviewed',json=delete_payload(entry['deletion_review']))
        assert removed.status_code==200,removed.text
    assert result.status_code==200,result.text
    assert result.json()['template']['template_revision']==1
    assert (await replica_db.users.find_one({}))['template_authority_revision']==2
    assert await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('change',['role','uid','user_stop','owner'])
async def test_access_changed_after_snapshot_conflicts_and_retries_to_denial(replica_db,monkeypatch,change):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    if change=='owner':
        await replica_db.workspace_members.delete_many({})
        await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    original=governance.authorize_delete;changed=False
    async def interleave(current,actor,uid):
        nonlocal changed
        await current.database.users.find_one({'user_id':actor},session=current.session)
        if not changed:
            changed=True
            if change=='role':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
            elif change=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'replacement'}})
            elif change=='owner':await replica_db.workspaces.update_one({}, {'$set':{'owner_id':'replacement'}})
            else:
                from outreach.core.erasure import stop_identity
                await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
                await stop_identity(replica_db,'original-uid')
        await original(current,actor,uid)
    monkeypatch.setattr(governance,'authorize_delete',interleave)
    with pytest.raises(HTTPException) as caught:await remove(replica_db,row)
    assert changed and caught.value.status_code==403
    assert await replica_db.outreach_templates.find_one({})==row
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


@pytest.mark.parametrize('change',['content','native'])
async def test_raw_template_changed_after_transaction_read_is_not_deleted(replica_db,monkeypatch,change):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    original=governance.unique_resource;changed=False
    async def interleave(collection,workspace,identifier):
        nonlocal changed
        saved=await original(collection,workspace,identifier)
        if not changed:
            changed=True
            if change=='content':await replica_db.outreach_templates.update_one({}, {'$set':{'name':'changed after read'}})
            else:
                await replica_db.outreach_templates.delete_one({})
                await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
        return saved
    monkeypatch.setattr(governance,'unique_resource',interleave)
    with pytest.raises(HTTPException) as caught:await remove(replica_db,row)
    assert changed and caught.value.status_code==409
    assert await replica_db.outreach_templates.count_documents({})==1


@pytest.mark.parametrize('action',['delete','create'])
async def test_failure_after_actual_write_rolls_back_resource_and_authority(replica_db,monkeypatch,action):
    await seed_authority(replica_db)
    before=await replica_db.users.find_one({})
    method='delete_one' if action=='delete' else 'insert_one'
    original=getattr(SuppressionCollection,method)
    async def fail(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        if self.collection.name=='outreach_templates':raise HTTPException(409,'synthetic post-write failure')
        return result
    monkeypatch.setattr(SuppressionCollection,method,fail)
    row=record()
    if action=='delete':await replica_db.outreach_templates.insert_one(row)
    else:row['user_id']='actor'
    with pytest.raises(HTTPException):
        if action=='delete':await remove(replica_db,row)
        else:await create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid')
    assert await replica_db.users.find_one({})==before
    assert await replica_db.outreach_templates.count_documents({})==(1 if action=='delete' else 0)


async def test_simultaneous_original_deletions_have_one_receipt_and_one_missing_hold(replica_db):
    await seed_authority(replica_db);row,_=await seed(replica_db)
    results=await asyncio.gather(remove(replica_db,row),remove(replica_db,row),return_exceptions=True)
    assert sum(isinstance(result,dict) and result['status']=='deleted' for result in results)==1
    assert sum(isinstance(result,HTTPException) and result.status_code==404 for result in results)==1
    assert (await replica_db.users.find_one({}))['template_authority_revision']==1


async def test_simultaneous_creation_collision_commits_only_one_native_template(replica_db):
    await seed_authority(replica_db);row=record();row['user_id']='actor'
    results=await asyncio.gather(*[create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid') for _ in range(2)],return_exceptions=True)
    assert sum(isinstance(result,dict) for result in results)==1
    assert sum(isinstance(result,HTTPException) and result.status_code==409 for result in results)==1
    assert await replica_db.outreach_templates.count_documents({})==1
    assert (await replica_db.users.find_one({}))['template_authority_revision']==1


@pytest.mark.parametrize('action',['delete','create'])
async def test_saved_commit_lost_ack_is_unconfirmed_and_never_automatically_replayed(replica_db,monkeypatch,action):
    await seed_authority(replica_db);row=record();calls=0
    if action=='delete':await replica_db.outreach_templates.insert_one(row)
    else:row['user_id']='actor'
    original=governance.mutate_suppression
    async def commit_then_lose(*args):
        nonlocal calls
        calls+=1
        await original(*args)
        raise SuppressionUnavailable('synthetic committed acknowledgement loss')
    monkeypatch.setattr(governance,'mutate_suppression',commit_then_lose)
    with pytest.raises(HTTPException) as caught:
        if action=='delete':await remove(replica_db,row)
        else:await create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid')
    assert caught.value.status_code==503 and calls==1
    assert await replica_db.outreach_templates.count_documents({})==(0 if action=='delete' else 1)
    assert (await replica_db.users.find_one({}))['template_authority_revision']==1
    monkeypatch.setattr(governance,'mutate_suppression',original)
    if action=='delete':
        with pytest.raises(HTTPException) as second:await remove(replica_db,row)
        assert second.value.status_code==404


@pytest.mark.parametrize('action',['delete','create'])
async def test_actual_erasure_stop_wins_before_template_mutation(replica_db,action):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db);row,_=await seed(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    await OutreachErasure(replica_db).request('workspace','actor')
    with pytest.raises(HTTPException) as caught:
        if action=='delete':await remove(replica_db,row)
        else:await create_template(replica_db,'workspace','actor',{**row,'id':'tpl_custom_aaaaaaaaaa','user_id':'actor'},authenticated_uid='original-uid')
    assert caught.value.status_code==503
    assert await replica_db.outreach_templates.find_one({})==row


async def test_delete_commit_precedes_competing_guarded_erasure(replica_db,monkeypatch):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db);row,_=await seed(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    ready,release=asyncio.Event(),asyncio.Event();original=governance.authorize_delete
    async def hold(current,actor,uid):
        await original(current,actor,uid);ready.set();await release.wait()
    monkeypatch.setattr(governance,'authorize_delete',hold)
    deleting=asyncio.create_task(remove(replica_db,row));await asyncio.wait_for(ready.wait(),5)
    erasing=asyncio.create_task(OutreachErasure(replica_db).request('workspace','actor'))
    await asyncio.sleep(0.05);assert not erasing.done();release.set()
    result,stop=await asyncio.gather(deleting,erasing)
    assert result['status']=='deleted' and stop['status']=='awaiting_drain'
    assert await replica_db.outreach_templates.count_documents({})==0


async def test_actual_erasure_finish_purges_remaining_templates_without_new_collection(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db);await seed(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service=OutreachErasure(replica_db);await service.request('workspace','actor')
    inspection=await service.inspect('workspace')
    result=await service.finish('workspace','operator','All owned fixture writers are drained.',workers_drained=True,expected_digest=inspection['review_digest'])
    assert result['status']=='erased' and await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('action',['delete','create'])
async def test_real_standalone_denies_without_template_mutation(real_db,action):
    await seed_authority(real_db);row,_=await seed(real_db)
    with pytest.raises(HTTPException) as caught:
        if action=='delete':await remove(real_db,row)
        else:await create_template(real_db,'workspace','actor',{**row,'id':'tpl_custom_aaaaaaaaaa','user_id':'actor'},authenticated_uid='original-uid')
    assert caught.value.status_code==503
    assert await real_db.outreach_templates.find_one({})==row


async def test_oversized_prepared_template_is_denied_before_authority_mutation(replica_db):
    await seed_authority(replica_db);row=record();row['user_id']='actor'
    row['metadata']='x'*(governance.MAX_RECORD_BYTES+1)
    with pytest.raises(HTTPException) as caught:await create_template(replica_db,'workspace','actor',row,authenticated_uid='original-uid')
    assert caught.value.status_code==422
    assert await replica_db.outreach_templates.count_documents({})==0
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0
