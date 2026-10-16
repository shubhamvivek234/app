"""Real Mongo atomic admission/membership/receipt and cancellation ordering."""
import asyncio
import os
import uuid
import pytest
from fastapi import FastAPI, HTTPException
import httpx
from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.lead_lists import router, ImportPreview
from outreach.core import lead_list_imports as imports, lead_lists as lists
from outreach.core.suppression import SuppressionCollection
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_lead_lists_mongo import seed, create

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


async def setup(db):
    await seed(db, 0)
    row = await create(db)
    p = ImportPreview(source_type='csv', raw_text='linkedin_url,first_name,email\nhttps://www.linkedin.com/in/one,One,one@example.invalid', quantity=10).model_dump()
    p.update(request_id=str(uuid.uuid4()), request_scope=imports.request_scope('w','actor'), campaign_id='campaign', revision=row['revision'], review_digest=row['review_digest'])
    return row, p


async def run(db, row, p):
    return await imports.import_contacts(db, 'w', 'actor', row['id'], p)


async def test_atomic_contacts_membership_and_reference_only_receipt(replica_db):
    row,p = await setup(replica_db)
    done = await run(replica_db,row,p)
    result = done['result']; assert done['status'] == 'completed' and result['imported_count'] == 1
    assert result['membership_added_count'] == 1 and result['list_revision'] == 2
    lead = await replica_db.outreach_leads.find_one({})
    assert not lead.get('authorized_revision') and lead['assigned_account_id'] is None
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 1
    stored = await replica_db.outreach_lead_list_imports.find_one({})
    assert 'example.invalid' not in str(stored) and 'linkedin.com' not in str(stored)
    assert 'raw_text' not in str(stored) and 'One' not in str(stored)
    assert not result['collection_verified']
    assert (await run(replica_db,row,p)) == done
    assert await replica_db.outreach_leads.count_documents({}) == 1


async def test_invalid_duplicate_and_original_email_policy_rows_retained(replica_db):
    row,p = await setup(replica_db)
    p['raw_text'] += '\nhttps://www.linkedin.com/in/one,Duplicate,dup@example.invalid\nbad,Invalid,x@example.invalid\nhttps://www.linkedin.com/in/two,Two,blocked@example.invalid'
    await replica_db.outreach_email_suppressions.insert_one({'workspace_id':'w','email':'blocked@example.invalid'})
    p['name_overrides'] = {'4':'Changed'}
    done = (await run(replica_db,row,p))['result']
    assert (done['imported_count'],done['duplicates_count'],done['skipped_count']) == (1,1,2)
    assert [item.get('rejection_code') for item in done['row_results']] == [None,'duplicate_batch','invalid_url','email_suppressed']
    assert [item['row_number'] for item in done['row_results']] == [1,2,3,4]


@pytest.mark.parametrize('phase', ['begin','finish'])
async def test_lost_ack_recovers_original_without_replay(replica_db,monkeypatch,phase):
    row,p=await setup(replica_db); original=lists.commit; dropped=False
    async def lost(db,ws,operation):
        nonlocal dropped
        result=await original(db,ws,operation)
        if operation.__name__ == phase and not dropped:
            dropped=True; raise HTTPException(503,'Lost acknowledgement')
        return result
    monkeypatch.setattr(lists,'commit',lost)
    with pytest.raises(HTTPException): await run(replica_db,row,p)
    status=await imports.inspect_import(replica_db,'w','actor',p['request_id'],p['request_scope'])
    assert status['status'] == ('pending' if phase=='begin' else 'completed')
    done=await run(replica_db,row,p)
    assert done['status']=='completed' and await replica_db.outreach_leads.count_documents({})==1
    if phase=='finish': assert done==status


async def pending(db,row,p,monkeypatch):
    original=lists.commit
    async def stop(db,ws,operation):
        if operation.__name__=='finish': raise HTTPException(503,'Interrupted before finish')
        return await original(db,ws,operation)
    monkeypatch.setattr(lists,'commit',stop)
    with pytest.raises(HTTPException): await run(db,row,p)
    monkeypatch.setattr(lists,'commit',original)


@pytest.mark.parametrize('before_begin', [True,False])
async def test_cancellation_orders_before_any_later_commit(replica_db,monkeypatch,before_begin):
    row,p=await setup(replica_db)
    if not before_begin: await pending(replica_db,row,p,monkeypatch)
    stopped=await imports.cancel_import(replica_db,'w','actor',p['request_id'],p['request_scope'])
    assert stopped['status']=='cancelled' and stopped['result'] is None
    assert (await run(replica_db,row,p))['status']=='cancelled'
    assert await replica_db.outreach_leads.count_documents({})==0
    assert await replica_db.outreach_lead_list_members.count_documents({})==0


async def test_cancel_after_completion_reports_saved_contacts(replica_db):
    row,p=await setup(replica_db); done=await run(replica_db,row,p)
    assert await imports.cancel_import(replica_db,'w','actor',p['request_id'],p['request_scope']) == done
    assert await replica_db.outreach_leads.count_documents({})==1


async def test_cancel_racing_finish_cannot_split_contacts_membership_and_receipt(replica_db,monkeypatch):
    row,p=await setup(replica_db); entered=asyncio.Event(); release=asyncio.Event(); original=lists.commit
    async def hold(db,ws,operation):
        if operation.__name__=='finish': entered.set(); await release.wait()
        return await original(db,ws,operation)
    monkeypatch.setattr(lists,'commit',hold)
    task=asyncio.create_task(run(replica_db,row,p)); await asyncio.wait_for(entered.wait(),5)
    cancelled=await imports.cancel_import(replica_db,'w','actor',p['request_id'],p['request_scope'])
    release.set(); assert (await task)==cancelled
    assert await replica_db.outreach_leads.count_documents({})==0


@pytest.mark.parametrize('change', ['revision','active','native_list','native_parent','parser','authorization'])
async def test_pending_request_denies_changed_original_context(replica_db,monkeypatch,change):
    row,p=await setup(replica_db); await pending(replica_db,row,p,monkeypatch)
    if change=='revision': await lists.edit_list(replica_db,'w',row['id'],1,name='Renamed')
    elif change=='active': await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':'active'}})
    elif change=='authorization': await replica_db.outreach_campaigns.update_one({}, {'$inc':{'authorization_revision':1}})
    elif change=='parser': monkeypatch.setattr(imports,'CONTRACT_VERSION',2)
    else:
        collection=replica_db.outreach_lead_lists if change=='native_list' else replica_db.outreach_campaigns
        stored=await collection.find_one({}); await collection.delete_one({'_id':stored.pop('_id')}); await collection.insert_one(stored)
    with pytest.raises(HTTPException): await run(replica_db,row,p)
    assert await replica_db.outreach_leads.count_documents({})==0
    assert (await imports.inspect_import(replica_db,'w','actor',p['request_id'],p['request_scope']))['status']=='pending'


async def test_late_receipt_failure_rolls_back_admission_members_and_list(replica_db,monkeypatch):
    row,p=await setup(replica_db); original=SuppressionCollection.update_one
    async def fail(self,query,update,*args,**kwargs):
        if self.collection.name=='outreach_lead_list_imports' and update.get('$set',{}).get('status')=='completed':
            raise RuntimeError('late failure')
        return await original(self,query,update,*args,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',fail)
    with pytest.raises(RuntimeError): await run(replica_db,row,p)
    assert await replica_db.outreach_leads.count_documents({})==0
    assert await replica_db.outreach_lead_list_members.count_documents({})==0
    assert (await replica_db.outreach_lead_lists.find_one({}))['revision']==1
    assert (await replica_db.outreach_lead_list_imports.find_one({}))['status']=='pending'


async def test_receipt_survives_parent_deletion_without_reparse(replica_db,monkeypatch):
    row,p=await setup(replica_db); done=await run(replica_db,row,p)
    await replica_db.outreach_campaigns.delete_many({}); await replica_db.outreach_leads.delete_many({})
    monkeypatch.setattr(imports,'parsed_source',lambda _: (_ for _ in ()).throw(AssertionError('must not reparse')))
    assert await run(replica_db,row,p)==done
    assert await imports.inspect_import(replica_db,'w','actor',p['request_id'],p['request_scope'])==done


@pytest.mark.parametrize('mutation',[{'result.imported_count':True},{'result.lead_ids':['bad','bad']},{'result.private_email':'secret'}, {'request_scope':[]},{'contract_version':True}])
async def test_corrupt_receipt_cannot_be_reported_as_success(replica_db,mutation):
    row,p=await setup(replica_db); await run(replica_db,row,p)
    await replica_db.outreach_lead_list_imports.update_one({}, {'$set':mutation})
    with pytest.raises(HTTPException) as failure: await imports.inspect_import(replica_db,'w','actor',p['request_id'],p['request_scope'])
    assert failure.value.status_code==503


async def test_scope_actor_and_missing_status_never_clear_unknown_request(replica_db):
    row,p=await setup(replica_db)
    with pytest.raises(HTTPException) as missing: await imports.inspect_import(replica_db,'w','actor',p['request_id'],p['request_scope'])
    assert missing.value.status_code==404
    with pytest.raises(HTTPException) as wrong: await imports.cancel_import(replica_db,'foreign','actor',p['request_id'],p['request_scope'])
    assert wrong.value.status_code==403
    assert await replica_db.outreach_lead_list_imports.count_documents({})==0


async def test_http_preview_import_and_recovery_permissions(replica_db):
    row,p=await setup(replica_db)
    await replica_db.workspace_members.insert_one({'workspace_id':'w','user_id':'actor','role':'admin'})
    app=FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':'actor','default_workspace_id':'w'}
    app.dependency_overrides[get_db]=lambda:replica_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.get('/lead-lists/import-context')).json()['request_scope']==p['request_scope']
        preview={key:value for key,value in p.items() if key not in {'request_id','request_scope','campaign_id','revision','review_digest'}}
        assert (await client.post(f"/lead-lists/{row['id']}/import-preview",json=preview)).status_code==200
        done=await client.post(f"/lead-lists/{row['id']}/import",json=p); assert done.status_code==200,done.text
        assert (await client.get(f"/lead-lists/imports/{p['request_id']}?request_scope={p['request_scope']}")).json()==done.json()
        await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
        assert (await client.post(f"/lead-lists/{row['id']}/import",json=p)).status_code==403


async def test_controls_erased_by_actual_guarded_workspace_batch(replica_db):
    row,p=await setup(replica_db); await run(replica_db,row,p)
    await replica_db.outreach_lead_list_imports.insert_one({'workspace_id':'foreign','actor_id':'other','request_id':'foreign'})
    from outreach.core.erasure import OutreachErasure,_control,DATA_COLLECTIONS
    assert 'outreach_lead_list_imports' in DATA_COLLECTIONS
    async def erase(current): return await OutreachErasure(replica_db)._erase_batch(current,'w','outreach_lead_list_imports')
    assert await _control(replica_db,'w',erase)
    assert await replica_db.outreach_lead_list_imports.count_documents({'workspace_id':'w'})==0
    assert await replica_db.outreach_lead_list_imports.count_documents({'workspace_id':'foreign'})==1


async def test_standalone_cannot_create_pending_control(real_db):
    await seed(real_db,0)
    p=ImportPreview(source_type='pasted_urls',raw_text='https://linkedin.com/in/one',quantity=1).model_dump()
    p.update(request_id=str(uuid.uuid4()),request_scope=imports.request_scope('w','actor'),campaign_id='campaign',revision=1,review_digest='a'*64)
    with pytest.raises(HTTPException) as failure: await run(real_db,{'id':'list_'+'a'*64},p)
    assert failure.value.status_code==503
    assert await real_db.outreach_lead_list_imports.count_documents({})==0


async def test_empty_reviewed_name_is_excluded_by_required_name_policy(replica_db):
    row,p=await setup(replica_db); p['name_overrides']={'1':''}
    result=(await run(replica_db,row,p))['result']
    assert result['imported_count']==0 and result['skipped_count']==1
    assert result['row_results']==[{'row_number':1,'status':'excluded','rejection_code':'missing_name'}]
    assert await replica_db.outreach_lead_list_members.count_documents({})==0


async def test_matching_history_overflow_denies_preview_and_commit_without_admission(replica_db):
    row,p=await setup(replica_db)
    await replica_db.outreach_do_not_contact.insert_many([{'workspace_id':'w','linkedin_url':'https://www.linkedin.com/in/one','reason':'held'} for _ in range(1001)])
    with pytest.raises(HTTPException) as preview: await imports.preview_import(replica_db,'w','actor',row['id'],p)
    assert preview.value.status_code==503
    with pytest.raises(HTTPException) as commit: await run(replica_db,row,p)
    assert commit.value.status_code==503
    assert await replica_db.outreach_leads.count_documents({})==0
    assert await replica_db.outreach_lead_list_members.count_documents({})==0
    assert (await replica_db.outreach_lead_list_imports.find_one({}))['status']=='pending'


@pytest.mark.parametrize('status',[[],{}])
async def test_malformed_campaign_state_is_controlled_denial(replica_db,status):
    row,p=await setup(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set':{'status':status}})
    with pytest.raises(HTTPException) as error: await run(replica_db,row,p)
    assert error.value.status_code==409
    assert await replica_db.outreach_lead_list_imports.count_documents({})==0


async def test_preview_includes_original_email_suppression_after_name_edit(replica_db):
    row,p=await setup(replica_db)
    await replica_db.outreach_email_suppressions.insert_one({'workspace_id':'w','email':'one@example.invalid'})
    p['name_overrides']={'1':'Edited'}
    preview=await imports.preview_import(replica_db,'w','actor',row['id'],p)
    assert preview['rows'][0]['rejection_code']=='email_suppressed'


@pytest.mark.parametrize('change',[{'campaign_id':'other'},{'list_id':'list_'+'f'*64},{'list_name':'Changed name'}])
async def test_pending_saved_target_substitution_cannot_complete(replica_db,monkeypatch,change):
    row,p=await setup(replica_db); await pending(replica_db,row,p,monkeypatch)
    await replica_db.outreach_lead_list_imports.update_one({}, {'$set':change})
    with pytest.raises(HTTPException): await run(replica_db,row,p)
    assert await replica_db.outreach_leads.count_documents({})==0


async def test_completed_receipt_survives_parser_contract_upgrade(replica_db,monkeypatch):
    row,p=await setup(replica_db); done=await run(replica_db,row,p)
    monkeypatch.setattr(imports,'CONTRACT_VERSION',2)
    assert await run(replica_db,row,p)==done


@pytest.mark.parametrize('column,value',[('member_urn','urn:li:fsd_profile:DIFFERENT'),('sales_lead_urn','urn:li:fs_salesProfile:DIFFERENT')])
async def test_public_url_with_unverified_transport_recipient_cannot_be_admitted(replica_db,column,value):
    row,p=await setup(replica_db)
    p['raw_text']=f'linkedin_url,first_name,{column}\nhttps://www.linkedin.com/in/reviewed,Reviewed,{value}'
    with pytest.raises(HTTPException) as preview: await imports.preview_import(replica_db,'w','actor',row['id'],p)
    assert preview.value.status_code==422
    with pytest.raises(HTTPException) as commit: await run(replica_db,row,p)
    assert commit.value.status_code==422
    assert await replica_db.outreach_leads.count_documents({})==0
    assert await replica_db.outreach_lead_list_imports.count_documents({})==0
