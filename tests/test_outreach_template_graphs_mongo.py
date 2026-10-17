"""Real template graph update races, strict HTTP and recovery boundaries."""
import asyncio
from copy import deepcopy
import json
import os

from bson import BSON, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core import template_graphs as graphs
from outreach.core import template_governance as governance
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, api_client, remove
from tests.test_outreach_template_metadata_mongo import edit as edit_metadata
from tests.test_outreach_template_graphs import original, GRAPH, NODE

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]
NEW_NODE = {**NODE, 'delay_hours': 24, 'title': 'Updated visit'}
NEW_GRAPH = {'nodes': [NEW_NODE], 'edges': [], 'tree': [NEW_NODE]}
CONTENT = json.dumps(NEW_GRAPH)


async def seed(db):
    row = original(); await db.outreach_templates.insert_one(row)
    return await db.outreach_templates.find_one({'_id': row['_id']})


def payload(row, **changes):
    review = graphs.graph_review(row, 'workspace', 'actor', 'original-uid')
    return {**{key: review[key] for key in ('contract_version', 'workspace_id', 'revision',
        'review_digest', 'identity_digest', 'scope_digest')}, 'graph_json': CONTENT,
        'input_digest': graphs.prepare_graph(CONTENT)['input_digest'], **changes}


async def edit(db, row, **changes):
    body = payload(row, **changes); body.pop('contract_version'); body.pop('workspace_id')
    return await graphs.update_graph(db, 'workspace', 'actor', row['id'], authenticated_uid='original-uid', **body)


async def test_graph_update_preserves_identity_metadata_unknowns_and_campaign_copies(replica_db):
    await seed_authority(replica_db); row = await seed(replica_db)
    row['unknown'] = {'$ne': 'literal'}; row['description'] = 'Preserve description'
    await replica_db.outreach_templates.replace_one({'_id': row['_id']}, row)
    for name in ('outreach_campaigns','outreach_sequence_versions','outreach_tasks','outreach_leads'):
        await replica_db[name].insert_one({'workspace_id':'workspace','copy':deepcopy(row)})
    before = {name:await replica_db[name].find({}).to_list(5) for name in
        ('outreach_campaigns','outreach_sequence_versions','outreach_tasks','outreach_leads')}
    receipt = await edit(replica_db, row); saved = await replica_db.outreach_templates.find_one({})
    assert receipt['new_revision'] == 1 and receipt['status'] == 'updated'
    assert receipt['input_digest'] == payload(row)['input_digest'] and 'graph_json' not in receipt
    assert saved['nodes'] == saved['tree'] == [NEW_NODE]
    assert saved['compiled_dag']['nodes']['root']['delay_hours'] == 24
    excluded = {'nodes','edges','tree','compiled_dag','compiler_contract_version','template_revision','graph_updated_at','graph_updated_by'}
    assert BSON.encode({k:v for k,v in saved.items() if k not in excluded}) == BSON.encode({k:v for k,v in row.items() if k not in excluded})
    assert saved['graph_updated_by'] == 'actor' and saved['graph_updated_at'].microsecond % 1000 == 0
    for name, values in before.items(): assert await replica_db[name].find({}).to_list(5) == values


@pytest.mark.parametrize('change',['content','native','revision','duplicate','creator','graph'])
async def test_stale_graph_review_cannot_overwrite_another_original(replica_db,change):
    await seed_authority(replica_db); row = await seed(replica_db)
    if change == 'native':
        await replica_db.outreach_templates.delete_one({}); await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
    elif change == 'duplicate': await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
    else: await replica_db.outreach_templates.update_one({}, {'$set': {
        'content':{'name':'Other'},'revision':{'template_revision':1},'creator':{'user_id':'other'},'graph':{'nodes':[]}}[change]})
    before = await replica_db.outreach_templates.find({}).to_list(5)
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code == 409 and await replica_db.outreach_templates.find({}).to_list(5) == before
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}}) == 0


@pytest.mark.parametrize('case',['viewer','uid','duplicate_uid','member_stop','user_stop'])
async def test_current_role_and_original_uid_are_required(replica_db,case):
    await seed_authority(replica_db); row=await seed(replica_db)
    if case == 'viewer': await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
    elif case == 'member_stop': await replica_db.workspace_members.update_one({}, {'$set':{'status':'inactive'}})
    elif case == 'uid': await replica_db.users.update_one({}, {'$set':{'firebase_uid':'changed'}})
    elif case == 'user_stop': await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    else: await replica_db.users.insert_one({'user_id':'other','firebase_uid':['original-uid']})
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code == 403 and await replica_db.outreach_templates.find_one({}) == row


@pytest.mark.parametrize('other',['graph','metadata','delete'])
async def test_competing_original_updates_or_delete_have_one_winner(replica_db,other):
    await seed_authority(replica_db); row=await seed(replica_db)
    second = edit(replica_db,row) if other=='graph' else edit_metadata(replica_db,row) if other=='metadata' else remove(replica_db,row)
    results = await asyncio.gather(edit(replica_db,row),second,return_exceptions=True)
    assert sum(isinstance(result,dict) for result in results) == 1
    assert sum(isinstance(result,HTTPException) and result.status_code in {404,409} for result in results) == 1
    assert (await replica_db.users.find_one({}))['template_authority_revision'] == 1


@pytest.mark.parametrize('change',['role','uid','content','native'])
async def test_changes_after_snapshot_conflict_and_retry_to_denial(replica_db,monkeypatch,change):
    await seed_authority(replica_db); row=await seed(replica_db); changed=False
    target=governance if change in {'role','uid'} else graphs
    name='authorize_update' if change in {'role','uid'} else 'unique_resource'; original_call=getattr(target,name)
    async def interleave(*args):
        nonlocal changed
        if change in {'role','uid'}:
            current=args[0]; await current.database.users.find_one({'user_id':'actor'},session=current.session)
        else: result=await original_call(*args)
        if not changed:
            changed=True
            if change=='role': await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
            elif change=='uid': await replica_db.users.update_one({}, {'$set':{'firebase_uid':'changed'}})
            elif change=='content': await replica_db.outreach_templates.update_one({}, {'$set':{'name':'Newer'}})
            else:
                await replica_db.outreach_templates.delete_one({}); await replica_db.outreach_templates.insert_one({**row,'_id':ObjectId()})
        return await original_call(*args) if change in {'role','uid'} else result
    monkeypatch.setattr(target,name,interleave)
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert changed and caught.value.status_code == (403 if change in {'role','uid'} else 409)


async def test_ack_loss_is_unknown_and_original_retry_never_increments_again(replica_db,monkeypatch):
    await seed_authority(replica_db); row=await seed(replica_db); calls=0; original_call=graphs.mutate_suppression
    async def lose(*args):
        nonlocal calls
        calls+=1; await original_call(*args); raise SuppressionUnavailable('synthetic lost acknowledgement')
    monkeypatch.setattr(graphs,'mutate_suppression',lose)
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code == 503 and calls==1
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1
    monkeypatch.setattr(graphs,'mutate_suppression',original_call)
    with pytest.raises(HTTPException) as stale: await edit(replica_db,row)
    assert stale.value.status_code == 409


@pytest.mark.parametrize('fault',['after_write','readback'])
async def test_post_write_failures_roll_back_graph_and_authority(replica_db,monkeypatch,fault):
    await seed_authority(replica_db); row=await seed(replica_db)
    name='replace_one' if fault=='after_write' else 'find_one'; original_call=getattr(SuppressionCollection,name)
    async def corrupt(self,*args,**kwargs):
        result=await original_call(self,*args,**kwargs)
        if self.collection.name=='outreach_templates':
            if fault=='after_write': raise HTTPException(409,'synthetic post-write failure')
            return {**result,'nodes':[]} if result else result
        return result
    monkeypatch.setattr(SuppressionCollection,name,corrupt)
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code==409 and await replica_db.outreach_templates.find_one({})==row
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def test_real_standalone_denies_graph_updates(real_db):
    await seed_authority(real_db); row=await seed(real_db)
    with pytest.raises(HTTPException) as caught: await edit(real_db,row)
    assert caught.value.status_code==503 and await real_db.outreach_templates.find_one({})==row


async def test_actual_erasure_stop_finish_and_missing_original_never_recreate(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db); row=await seed(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service=OutreachErasure(replica_db); await service.request('workspace','actor')
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code==503
    inspection=await service.inspect('workspace')
    await service.finish('workspace','operator','Owned fixture writers are drained.',workers_drained=True,expected_digest=inspection['review_digest'])
    with pytest.raises(HTTPException): await edit(replica_db,row)
    assert await replica_db.outreach_templates.count_documents({})==0


async def test_actual_http_catalog_review_and_explicit_graph_update(replica_db):
    await seed_authority(replica_db); row=await seed(replica_db)
    async with await api_client(replica_db) as api:
        catalog=await api.get('/sequences/templates'); selected=next(item for item in catalog.json() if item['id']==row['id'])
        assert selected['graph_review']['reviewable'] and '_id' not in selected
        result=await api.patch('/sequences/templates/'+row['id']+'/graph-reviewed',json=payload(row))
        assert result.status_code==200,result.text
        next_catalog=await api.get('/sequences/templates'); next_row=next(item for item in next_catalog.json() if item['id']==row['id'])
    assert next_row['graph_review']['revision']==1 and next_row['metadata_review']['revision']==1
    assert next_row['graph_review']['review_digest']==result.json()['new_review_digest']


@pytest.mark.parametrize('patch', [{'revision':True},{'revision':1.0},{'contract_version':True},
    {'graph_json':{}},{'graph_json':'bad'},{'input_digest':'a'*64},{'scope_digest':'a'*64},
    {'workspace_id':'other'},{'name':'Changed'},{'compiled_dag':{}},{'new_revision':1},
    {'graph_json':json.dumps({**NEW_GRAPH,'tree':[]})}])
async def test_http_rejects_strict_contract_scope_digest_and_invalid_graph(replica_db,patch):
    await seed_authority(replica_db); row=await seed(replica_db)
    async with await api_client(replica_db) as api:
        result=await api.patch('/sequences/templates/'+row['id']+'/graph-reviewed',json=payload(row,**patch))
    assert result.status_code in {403,422},result.text
    assert await replica_db.outreach_templates.find_one({})==row


async def test_original_creation_receipt_survives_graph_edit_and_never_recompiles(replica_db):
    from outreach.core import template_saves
    from tests.test_outreach_template_saves_mongo import post,inspect,CONTENT as ORIGINAL_CONTENT,body
    from tests.test_outreach_template_saves import REQUEST
    await seed_authority(replica_db); first=await post(replica_db); row=await replica_db.outreach_templates.find_one({})
    await edit(replica_db,row); saved=await replica_db.outreach_templates.find_one({})
    def forbidden(): raise AssertionError('Historical creation must never recompile')
    replay=await template_saves.save_template(replica_db,'workspace','actor','original-uid',REQUEST,
        body()['scope_digest'],ORIGINAL_CONTENT,body()['input_digest'],forbidden)
    assert replay==first.json()==(await inspect(replica_db)).json()
    assert saved['template_revision']==2 and replay['template_revision']==1
    assert await replica_db.outreach_templates.find_one({})==saved


@pytest.mark.parametrize('fault',['boolean_delay','wrong_id','missing_order','unsupported_marker','missing_compiled'])
async def test_malformed_original_compiler_holds_even_with_matching_raw_review(replica_db,fault):
    await seed_authority(replica_db); row=await seed(replica_db)
    row.update(graphs.compile_graph(deepcopy(GRAPH)))
    if fault=='boolean_delay': row['compiled_dag']['nodes']['root']['delay_hours']=False
    elif fault=='wrong_id': row['compiled_dag']['nodes']['root']['id']='replacement'
    elif fault=='missing_order': row['compiled_dag'].pop('execution_order')
    elif fault=='unsupported_marker': row['compiler_contract_version']=2
    else: row.pop('compiled_dag')
    await replica_db.outreach_templates.replace_one({'_id':row['_id']},row)
    raw=governance.template_review(row,'workspace')
    body={**{key:raw[key] for key in ('contract_version','revision','review_digest','identity_digest')},
        'workspace_id':'workspace','scope_digest':graphs.graph_scope('workspace','actor','original-uid'),
        'graph_json':CONTENT,'input_digest':graphs.prepare_graph(CONTENT)['input_digest']}
    async with await api_client(replica_db) as api:
        catalog=await api.get('/sequences/templates'); saved=next(item for item in catalog.json() if item['id']==row['id'])
        assert saved['graph_review']['reviewable'] is False
        result=await api.patch('/sequences/templates/'+row['id']+'/graph-reviewed',json=body)
    assert result.status_code==409 and await replica_db.outreach_templates.find_one({})==row
    assert await replica_db.users.count_documents({'template_authority_revision':{'$exists':True}})==0


async def test_update_cannot_exceed_final_revision_or_full_row_bound(replica_db,monkeypatch):
    await seed_authority(replica_db); row=await seed(replica_db)
    row['template_revision']=governance.MAX_REVISION-1
    await replica_db.outreach_templates.replace_one({'_id':row['_id']},row)
    receipt=await edit(replica_db,row); saved=await replica_db.outreach_templates.find_one({})
    assert receipt['new_revision']==governance.MAX_REVISION
    assert graphs.graph_review(saved,'workspace','actor','original-uid')['reviewable'] is False
    await replica_db.outreach_templates.replace_one({'_id':row['_id']},row)
    monkeypatch.setattr(governance,'MAX_RECORD_BYTES',len(BSON.encode(row))+10)
    with pytest.raises(HTTPException) as caught: await edit(replica_db,row)
    assert caught.value.status_code==422 and await replica_db.outreach_templates.find_one({})==row


async def test_only_current_update_permission_allows_editor_and_unique_owner(replica_db):
    await seed_authority(replica_db); row=await seed(replica_db)
    await replica_db.workspace_members.update_one({}, {'$set':{'role':'editor'}})
    await edit(replica_db,row)
    await replica_db.workspace_members.delete_many({})
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    current=await replica_db.outreach_templates.find_one({}); await edit(replica_db,current)
    assert (await replica_db.outreach_templates.find_one({}))['template_revision']==2
