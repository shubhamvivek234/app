"""Recoverable template creation using owned replica/standalone databases."""
import asyncio
from copy import deepcopy
import json
import os

from fastapi import HTTPException
from bson import Code
import pytest

from outreach.core import template_saves as saves
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from outreach.core.template_governance import delete_template, scoped_review
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, api_client
from tests.test_outreach_template_saves import REQUEST

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]

NODE={'id':'root','type':'visit_profile','delay_hours':0,'config':{}}
CONTENT=json.dumps({'name':'Saved','nodes':[NODE],'edges':[],'tree':[NODE]})


def body(content=CONTENT):
    return {'contract_version':1,'workspace_id':'workspace','scope_digest':saves.save_context('workspace','actor','original-uid')['scope_digest'],
        'request_id':REQUEST,'input_digest':saves.input_digest(content),'content_json':content}


async def post(db, content=CONTENT):
    async with await api_client(db) as api:
        return await api.post('/sequences/template-saves',json=body(content))


async def inspect(db):
    async with await api_client(db) as api:
        return await api.get('/sequences/template-saves/'+REQUEST,params={
            'scope_digest':body()['scope_digest'],'workspace_id':'workspace'})


async def test_original_retries_and_status_share_one_historical_receipt(replica_db):
    await seed_authority(replica_db)
    first,second=await post(replica_db),await post(replica_db)
    status=await inspect(replica_db)
    assert first.status_code==second.status_code==status.status_code==200,first.text
    assert first.json()==second.json()==status.json()
    assert await replica_db.outreach_templates.count_documents({})==1
    assert await replica_db.outreach_template_saves.count_documents({})==1
    receipt=await replica_db.outreach_template_saves.find_one({})
    assert not {'nodes','tree','compiled_dag','name','content_json','firebase_uid'} & receipt.keys()


async def test_same_reference_with_changed_content_conflicts_without_duplicate(replica_db):
    await seed_authority(replica_db);assert (await post(replica_db)).status_code==200
    result=await post(replica_db,CONTENT.replace('Saved','Changed'))
    assert result.status_code==409 and await replica_db.outreach_templates.count_documents({})==1


async def test_simultaneous_duplicate_requests_commit_one_template(replica_db):
    await seed_authority(replica_db)
    results=await asyncio.gather(post(replica_db),post(replica_db))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert results[0].json()==results[1].json()
    assert await replica_db.outreach_templates.count_documents({})==1


async def test_receipt_survives_deletion_without_recreating_template(replica_db):
    await seed_authority(replica_db);first=await post(replica_db)
    row=await replica_db.outreach_templates.find_one({})
    review=scoped_review(row,'workspace','actor','original-uid')
    await delete_template(replica_db,'workspace','actor',row['id'],review['revision'],review['review_digest'],review['identity_digest'],
        authenticated_uid='original-uid',scope_digest=review['scope_digest'])
    again,status=await post(replica_db),await inspect(replica_db)
    assert again.json()==status.json()==first.json()
    assert await replica_db.outreach_templates.count_documents({})==0


async def test_completed_receipt_does_not_recompile_on_original_replay(replica_db,monkeypatch):
    await seed_authority(replica_db);first=await post(replica_db)
    def unavailable(*args):raise AssertionError('Completed original request must not compile again')
    monkeypatch.setattr('outreach.api.sequences._authoring_graph',unavailable)
    assert (await post(replica_db)).json()==first.json()


async def test_missing_status_remains_unconfirmed_and_writes_no_save(replica_db):
    await seed_authority(replica_db)
    result=await inspect(replica_db)
    assert result.status_code==404 and await replica_db.outreach_template_saves.count_documents({})==0
    assert await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('change',[{'contract_version':True},{'input_digest':'bad'}, {'request_id':REQUEST.upper()},
    {'scope_digest':'d'*64},{'workspace_id':'other'},{'extra':True},{'content_json':'not json'}])
async def test_strict_http_contract_denies_without_template(replica_db,change):
    await seed_authority(replica_db);payload={**body(),**change}
    async with await api_client(replica_db) as api:
        result=await api.post('/sequences/template-saves',json=payload)
    assert result.status_code in {400,403,409,422},result.text
    assert await replica_db.outreach_templates.count_documents({})==0


@pytest.mark.parametrize('collection',['outreach_templates','outreach_template_saves'])
async def test_failure_after_each_actual_insert_rolls_back_both_records(replica_db,monkeypatch,collection):
    await seed_authority(replica_db);original=SuppressionCollection.insert_one
    async def fail(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        if self.collection.name==collection:raise HTTPException(409,'Synthetic post-insert failure')
        return result
    monkeypatch.setattr(SuppressionCollection,'insert_one',fail)
    assert (await post(replica_db)).status_code==409
    assert await replica_db.outreach_templates.count_documents({})==0
    assert await replica_db.outreach_template_saves.count_documents({})==0
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def test_committed_ack_loss_is_recovered_only_by_explicit_status(replica_db,monkeypatch):
    await seed_authority(replica_db);original=saves.mutate_suppression;calls=0
    async def lose(*args):
        nonlocal calls
        calls+=1;await original(*args);raise SuppressionUnavailable('Synthetic committed acknowledgement loss')
    monkeypatch.setattr(saves,'mutate_suppression',lose)
    result=await post(replica_db)
    assert result.status_code==503 and calls==1
    assert await replica_db.outreach_templates.count_documents({})==1
    monkeypatch.setattr(saves,'mutate_suppression',original)
    assert (await inspect(replica_db)).status_code==200


@pytest.mark.parametrize('change',['role','uid','user_stop','duplicate_uid'])
async def test_status_and_replay_recheck_current_original_authority(replica_db,change):
    await seed_authority(replica_db);assert (await post(replica_db)).status_code==200
    if change=='role':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
    elif change=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'replacement'}})
    elif change=='user_stop':await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    else:await replica_db.users.insert_one({'user_id':'other','firebase_uid':'original-uid'})
    assert (await inspect(replica_db)).status_code==403
    assert (await post(replica_db)).status_code==403
    assert await replica_db.outreach_templates.count_documents({})==1


async def test_actual_erasure_purges_save_receipt_and_denies_new_request(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db);assert (await post(replica_db)).status_code==200
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service=OutreachErasure(replica_db);await service.request('workspace','actor')
    assert (await post(replica_db)).status_code==409  # Existing HTTP erasure admission denies before the consumer.
    inspection=await service.inspect('workspace')
    result=await service.finish('workspace','operator','Owned fixture writers drained.',workers_drained=True,expected_digest=inspection['review_digest'])
    assert result['status']=='erased'
    assert await replica_db.outreach_template_saves.count_documents({})==0
    assert await replica_db.outreach_templates.count_documents({})==0


async def test_actual_standalone_cannot_claim_creation_or_status(real_db):
    await seed_authority(real_db)
    assert (await post(real_db)).status_code==503
    assert (await inspect(real_db)).status_code==503
    assert await real_db.outreach_templates.count_documents({})==0


async def test_receipt_hashes_the_actual_bson_stored_template(replica_db):
    from outreach.core.template_governance import template_review
    await seed_authority(replica_db);result=await post(replica_db)
    row=await replica_db.outreach_templates.find_one({})
    reviewed=template_review(row,'workspace')
    assert result.json()['template_identity_digest']==reviewed['identity_digest']
    assert result.json()['template_review_digest']==reviewed['review_digest']
    assert row['created_at'].microsecond%1000==0


async def test_simultaneous_conflicting_input_selects_only_one_original(replica_db):
    await seed_authority(replica_db)
    results=await asyncio.gather(post(replica_db),post(replica_db,CONTENT.replace('Saved','Changed')))
    assert sorted(r.status_code for r in results)==[200,409]
    winner=next(r for r in results if r.status_code==200)
    assert (await inspect(replica_db)).json()==winner.json()
    assert await replica_db.outreach_templates.count_documents({})==1


@pytest.mark.parametrize('change',[{'template_revision':True},{'input_digest':['a'*64]},
    {'created_at':'today'},{'status':'pending'},{'future_field':'unsupported'}])
async def test_malformed_stored_receipt_holds_without_replacing_it(replica_db,change):
    await seed_authority(replica_db);assert (await post(replica_db)).status_code==200
    await replica_db.outreach_template_saves.update_one({}, {'$set':change})
    before=await replica_db.outreach_template_saves.find_one({})
    assert (await inspect(replica_db)).status_code==503
    assert (await post(replica_db)).status_code==503
    assert await replica_db.outreach_template_saves.find_one({})==before
    assert await replica_db.outreach_templates.count_documents({})==1


@pytest.mark.parametrize('operation',['save','status'])
@pytest.mark.parametrize('change',['role','uid','user_stop'])
async def test_authority_changed_after_snapshot_retries_to_denial(replica_db,monkeypatch,operation,change):
    await seed_authority(replica_db)
    if operation=='status':assert (await post(replica_db)).status_code==200
    original=saves.authorize_create;changed=False
    async def interleave(current,actor,uid):
        nonlocal changed
        await current.database.users.find_one({'user_id':actor},session=current.session)
        if not changed:
            changed=True
            if change=='role':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
            elif change=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'replacement'}})
            else:
                from outreach.core.erasure import stop_identity
                await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
                await stop_identity(replica_db,'original-uid')
        await original(current,actor,uid)
    monkeypatch.setattr(saves,'authorize_create',interleave)
    result=await (post(replica_db) if operation=='save' else inspect(replica_db))
    assert changed and result.status_code==403,result.text
    assert await replica_db.outreach_templates.count_documents({})==(1 if operation=='status' else 0)


async def test_creation_commit_orders_before_competing_guarded_erasure(replica_db,monkeypatch):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    ready,release=asyncio.Event(),asyncio.Event();original=saves.authorize_create
    async def hold(current,actor,uid):
        await original(current,actor,uid);ready.set();await release.wait()
    monkeypatch.setattr(saves,'authorize_create',hold)
    creating=asyncio.create_task(post(replica_db));await asyncio.wait_for(ready.wait(),5)
    erasing=asyncio.create_task(OutreachErasure(replica_db).request('workspace','actor'))
    await asyncio.sleep(0.05);assert not erasing.done();release.set()
    result,stop=await asyncio.gather(creating,erasing)
    assert result.status_code==200 and stop['status']=='awaiting_drain'
    assert await replica_db.outreach_templates.count_documents({})==1
    assert await replica_db.outreach_template_saves.count_documents({})==1


async def test_new_save_url_cannot_invoke_older_unrecoverable_handler():
    import httpx
    from fastapi import FastAPI
    app=FastAPI();calls=[]
    @app.post('/sequences/templates')
    async def older_handler():calls.append(True);return {'status':'success'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as api:
        result=await api.post('/sequences/template-saves',json=body())
    assert result.status_code==404 and not calls


@pytest.mark.parametrize('field',['template_id','input_digest','template_identity_digest','template_review_digest','status'])
async def test_actual_bson_code_receipt_fields_hold(replica_db,field):
    await seed_authority(replica_db);assert (await post(replica_db)).status_code==200
    row=await replica_db.outreach_template_saves.find_one({})
    await replica_db.outreach_template_saves.update_one({}, {'$set':{field:Code(row[field])}})
    assert (await inspect(replica_db)).status_code==503
    assert (await post(replica_db)).status_code==503


@pytest.mark.parametrize('collection',['outreach_templates','outreach_template_saves'])
async def test_valid_but_changed_insert_readback_cannot_confirm(replica_db,monkeypatch,collection):
    await seed_authority(replica_db);original=SuppressionCollection.find_one
    async def changed(self,*args,**kwargs):
        row=await original(self,*args,**kwargs)
        if row is not None and self.collection.name==collection:
            row=deepcopy(row)
            row['name' if collection=='outreach_templates' else 'template_review_digest']='Changed' if collection=='outreach_templates' else 'd'*64
        return row
    monkeypatch.setattr(SuppressionCollection,'find_one',changed)
    assert (await post(replica_db)).status_code==503
    assert await replica_db.outreach_templates.count_documents({})==0
    assert await replica_db.outreach_template_saves.count_documents({})==0
