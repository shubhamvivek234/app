"""Owned Mongo graph snapshots, shared capture fences and actual erasure."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone
import json
import os

from bson import BSON,Int64,Code
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from utils import encryption
from tests.outreach_native import replica_server,replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server,real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority,remove
from tests.test_outreach_template_saves_mongo import post
from tests.test_outreach_template_graphs_mongo import edit

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned native Mongo opt-in')]


@pytest.fixture(autouse=True)
def owned_key(monkeypatch):monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))


async def seed(db,secret=False):
    from outreach.core import template_graph_snapshots as snapshots,template_history_storage as storage
    await seed_authority(db)
    node={'id':'root','type':'visit_profile','config':{'api_key':'private-secret'} if secret else {'dwell_mode':'realistic','skip_if_visited':False}}
    assert (await post(db,content=json.dumps({'name':'Saved','nodes':[node],'edges':[],'tree':[node]}))).status_code==200
    await storage.ensure_history_index(db);await snapshots.prepare_storage(db)
    return await db.outreach_templates.find_one({})


async def capture(db,row):
    from outreach.core import template_graph_snapshots as snapshots
    from outreach.core.template_governance import template_review
    proof=template_review(row,'workspace')
    return await snapshots.capture_snapshot(db,'workspace','actor','original-uid',row['id'],revision=proof['revision'],
        review_digest=proof['review_digest'],identity_digest=proof['identity_digest'],scope_digest=snapshots.snapshot_scope('workspace','actor','original-uid'))


async def test_graph_collection_is_in_actual_erasure_contract(replica_db):
    from outreach.core.erasure import DATA_COLLECTIONS
    assert 'outreach_template_graph_snapshots' in DATA_COLLECTIONS


async def test_capture_round_trip_repeat_and_source_checkpoint_immutability(replica_db):
    from outreach.core import template_graph_snapshots as snapshots,template_metadata_snapshots as metadata
    row=await seed(replica_db);before=await replica_db.outreach_template_revisions.find({}).to_list(10)
    first=await capture(replica_db,row);saved=await replica_db.outreach_template_graph_snapshots.find_one({})
    assert await capture(replica_db,row)==first and saved==await replica_db.outreach_template_graph_snapshots.find_one({})
    assert snapshots.open_snapshot(saved,before[0])=={k:row[k] for k in ('nodes','edges','tree')}
    assert b'realistic' not in BSON.encode(saved) and not {'nodes','graph','ciphertext'} & first.keys()
    assert await replica_db.outreach_templates.find_one({})==row and await replica_db.outreach_template_revisions.find({}).to_list(10)==before
    assert await replica_db.outreach_template_metadata_snapshots.count_documents({})==0


@pytest.mark.parametrize('fault',['viewer','uid','duplicate_uid','code_role','stopped','missing_checkpoint','terminal',
    'index','missing_key','wrong_key','count','bytes','corrupt','unknown_config'])
async def test_authority_history_storage_crypto_and_field_holds_are_atomic(replica_db,monkeypatch,fault):
    from outreach.core import template_graph_snapshots as snapshots,template_history_storage as storage
    row=await seed(replica_db,secret=fault=='unknown_config')
    if fault in {'wrong_key','corrupt'}:await capture(replica_db,row)
    if fault=='viewer':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
    elif fault=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'different'}})
    elif fault=='duplicate_uid':await replica_db.users.insert_one({'user_id':'other','firebase_uid':'original-uid'})
    elif fault=='code_role':await replica_db.workspace_members.update_one({}, {'$set':{'role':Code('admin')}})
    elif fault=='stopped':await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    elif fault=='missing_checkpoint':await replica_db.outreach_template_revisions.delete_many({})
    elif fault=='terminal':await remove(replica_db,row);await replica_db.outreach_templates.insert_one(row)
    elif fault=='index':await replica_db.outreach_template_graph_snapshots.drop_index(storage.INDEX_NAME)
    elif fault=='missing_key':monkeypatch.setattr(encryption,'_fernet',None);monkeypatch.delenv('ENCRYPTION_KEY',raising=False)
    elif fault=='wrong_key':monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))
    elif fault=='count':monkeypatch.setattr(snapshots,'MAX_SNAPSHOTS',0)
    elif fault=='bytes':monkeypatch.setattr(snapshots,'MAX_TOTAL_BYTES',1)
    elif fault=='corrupt':await replica_db.outreach_template_graph_snapshots.update_one({}, {'$set':{'ciphertext':'plaintext'}})
    before=await replica_db.outreach_template_graph_snapshots.find({}).to_list(10)
    users=await replica_db.users.find({}).to_list(5);members=await replica_db.workspace_members.find({}).to_list(5)
    with pytest.raises(HTTPException) as caught:await capture(replica_db,row)
    assert 'private-secret' not in str(caught.value.detail)
    assert await replica_db.outreach_template_graph_snapshots.find({}).to_list(10)==before
    assert await replica_db.users.find({}).to_list(5)==users and await replica_db.workspace_members.find({}).to_list(5)==members


@pytest.mark.parametrize('fault',['insert','readback','index_drift'])
async def test_insert_readback_and_index_drift_roll_back_capture_and_counters(replica_db,monkeypatch,fault):
    from outreach.core import template_graph_snapshots as snapshots,template_history_storage as storage
    from outreach.core.suppression import SuppressionCollection
    row=await seed(replica_db);before=await replica_db.users.find_one({});insert=SuppressionCollection.insert_one;find=SuppressionCollection.find_one;load=snapshots._retained
    async def broken_insert(self,*args,**kwargs):
        value=await insert(self,*args,**kwargs)
        if self.collection.name=='outreach_template_graph_snapshots' and fault=='insert':raise ValueError('private data')
        return value
    async def broken_find(self,*args,**kwargs):
        value=await find(self,*args,**kwargs)
        return {**value,'ciphertext':'bad'} if value and self.collection.name=='outreach_template_graph_snapshots' and fault=='readback' else value
    async def drift(*args):
        value=await load(*args)
        if fault=='index_drift':await replica_db.outreach_template_graph_snapshots.drop_index(storage.INDEX_NAME)
        return value
    monkeypatch.setattr(SuppressionCollection,'insert_one',broken_insert);monkeypatch.setattr(SuppressionCollection,'find_one',broken_find);monkeypatch.setattr(snapshots,'_retained',drift)
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert await replica_db.outreach_template_graph_snapshots.count_documents({})==0 and await replica_db.users.find_one({})==before


async def test_cap_retains_original_and_stale_proof_cannot_recover_after_graph_edit(replica_db,monkeypatch):
    from outreach.core import template_graph_snapshots as snapshots
    row=await seed(replica_db);monkeypatch.setattr(snapshots,'MAX_SNAPSHOTS',1);first=await capture(replica_db,row)
    saved=await replica_db.outreach_template_graph_snapshots.find_one({});assert await capture(replica_db,row)==first
    await edit(replica_db,row)
    for source in [row,await replica_db.outreach_templates.find_one({})]:
        with pytest.raises(HTTPException):await capture(replica_db,source)
    assert saved==await replica_db.outreach_template_graph_snapshots.find_one({})


async def test_unknown_acknowledgement_current_proof_repeat_preserves_ciphertext(replica_db,monkeypatch):
    from outreach.core import template_graph_snapshots as snapshots
    from outreach.core.suppression import SuppressionUnavailable
    row=await seed(replica_db);commit=snapshots.mutate_suppression
    async def lost(*args,**kwargs):await commit(*args,**kwargs);raise SuppressionUnavailable('Owned lost acknowledgement')
    monkeypatch.setattr(snapshots,'mutate_suppression',lost)
    with pytest.raises(HTTPException) as caught:await capture(replica_db,row)
    assert caught.value.status_code==503;saved=await replica_db.outreach_template_graph_snapshots.find_one({});assert saved
    monkeypatch.setattr(snapshots,'mutate_suppression',commit)
    assert (await capture(replica_db,row))['snapshot_id']==saved['_id'] and saved==await replica_db.outreach_template_graph_snapshots.find_one({})


async def test_canonical_graph_comparison_rejects_equal_numeric_aliases(replica_db):
    from outreach.core import template_graph_snapshots as snapshots
    row=await seed(replica_db);await capture(replica_db,row);saved=await replica_db.outreach_template_graph_snapshots.find_one({})
    payload=json.loads(encryption.decrypt_strict(saved['ciphertext']))
    # The capture source has false here. A token's number0 is not that boolean.
    payload['graph']['nodes'][0]['config']['skip_if_visited']=0
    saved['ciphertext']=encryption.encrypt(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    await replica_db.outreach_template_graph_snapshots.replace_one({'_id':saved['_id']},saved)
    with pytest.raises(HTTPException):await capture(replica_db,row)


async def test_canonical_comparison_holds_valid_number_float_alias_after_decryption(replica_db):
    from outreach.core import template_graph_snapshots as snapshots,template_history_storage as storage
    await seed_authority(replica_db)
    node={'id':'root','type':'has_data_in_column','config':{'condition_contract_version':1,
        'field':'custom_variables.score','operator':'equals','value_type':'number','value':1}}
    assert (await post(replica_db,content=json.dumps({'name':'Saved','nodes':[node],'edges':[],'tree':[node]}))).status_code==200
    await storage.ensure_history_index(replica_db);await snapshots.prepare_storage(replica_db)
    row=await replica_db.outreach_templates.find_one({});await capture(replica_db,row)
    saved=await replica_db.outreach_template_graph_snapshots.find_one({});payload=json.loads(encryption.decrypt_strict(saved['ciphertext']))
    payload['graph']['nodes'][0]['config']['value']=1.0;payload['graph']['tree'][0]['config']['value']=1.0
    saved['ciphertext']=encryption.encrypt(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    checkpoint=await replica_db.outreach_template_revisions.find_one({})
    assert snapshots.open_snapshot(saved,checkpoint)['nodes'][0]['config']['value']==1.0
    await replica_db.outreach_template_graph_snapshots.replace_one({'_id':saved['_id']},saved)
    before=await replica_db.users.find_one({})
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert await replica_db.users.find_one({})==before


async def test_actual_erasure_purges_graph_and_metadata_snapshots_after_deletion(replica_db):
    from outreach.core import template_metadata_snapshots as metadata
    from outreach.core.template_governance import template_review
    from outreach.core.erasure import OutreachErasure
    row=await seed(replica_db);await capture(replica_db,row);await metadata.prepare_storage(replica_db);proof=template_review(row,'workspace')
    await metadata.capture_snapshot(replica_db,'workspace','actor','original-uid',row['id'],revision=proof['revision'],
        review_digest=proof['review_digest'],identity_digest=proof['identity_digest'],scope_digest=metadata.snapshot_scope('workspace','actor','original-uid'))
    await remove(replica_db,row);await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service=OutreachErasure(replica_db);await service.request('workspace','actor');review=await service.inspect('workspace')
    await service.finish('workspace','operator','Owned fixture drained',workers_drained=True,expected_digest=review['review_digest'])
    for name in ['outreach_template_graph_snapshots','outreach_template_metadata_snapshots']:assert await replica_db[name].count_documents({})==0
    with pytest.raises(HTTPException):await capture(replica_db,row)


async def test_capture_commits_before_later_edit_without_advancing_revision(replica_db,monkeypatch):
    from outreach.core import template_graph_snapshots as snapshots
    row=await seed(replica_db);entered,released=asyncio.Event(),asyncio.Event();load=snapshots._retained
    async def pause(*args):value=await load(*args);entered.set();await released.wait();return value
    monkeypatch.setattr(snapshots,'_retained',pause);capturing=asyncio.create_task(capture(replica_db,row));await asyncio.wait_for(entered.wait(),5)
    editing=asyncio.create_task(edit(replica_db,row))
    try:await asyncio.sleep(.05);assert not editing.done()
    finally:released.set()
    captured,changed=await asyncio.gather(capturing,editing);assert captured['revision']==1 and changed['new_revision']==2


async def test_final_revision_and_oversized_native_id_are_safe(replica_db):
    from outreach.core.template_revision_checkpoints import checkpoint_for
    from outreach.core import template_graph_snapshots as snapshots
    row=await seed(replica_db);row['template_revision']=Int64(2**53-1)
    await replica_db.outreach_templates.replace_one({'_id':row['_id']},row)
    await replica_db.outreach_template_revisions.insert_one(checkpoint_for(row,'actor',datetime(2026,10,19,tzinfo=timezone.utc)))
    assert (await capture(replica_db,row))['revision']==2**53-1
    saved=await replica_db.outreach_template_graph_snapshots.find_one({});await replica_db.outreach_template_graph_snapshots.delete_one({'_id':saved['_id']})
    await replica_db.outreach_template_graph_snapshots.insert_one({**saved,'_id':'z'*(snapshots.MAX_ROW_BYTES+1)})
    with pytest.raises(HTTPException):await capture(replica_db,row)


async def test_standalone_cannot_capture(real_db):
    from outreach.core import template_graph_snapshots as snapshots
    with pytest.raises(HTTPException) as caught:
        await snapshots.capture_snapshot(real_db,'workspace','actor','uid','tpl_custom_012345abcd',revision=1,
            review_digest='a'*64,identity_digest='b'*64,scope_digest=snapshots.snapshot_scope('workspace','actor','uid'))
    assert caught.value.status_code==503
