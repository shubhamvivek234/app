"""Owned Mongo tests for explicit, unexposed metadata snapshot capture."""
import asyncio
from copy import deepcopy
import os

from bson import BSON, Code
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from utils import encryption
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority,remove
from tests.test_outreach_template_saves_mongo import post
from tests.test_outreach_template_metadata_mongo import edit

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1',reason='Owned native Mongo opt-in')]


@pytest.fixture(autouse=True)
def owned_key(monkeypatch):monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))


async def seed(db):
    from outreach.core import template_metadata_snapshots as snapshots,template_history_storage as storage
    await seed_authority(db);assert (await post(db)).status_code==200
    await storage.ensure_history_index(db);await snapshots.prepare_storage(db)
    return await db.outreach_templates.find_one({})


async def capture(db,row,**override):
    from outreach.core import template_metadata_snapshots as snapshots
    from outreach.core.template_governance import template_review
    review=template_review(row,'workspace')
    return await snapshots.capture_snapshot(db,'workspace','actor','original-uid',row['id'],
        revision=review['revision'],review_digest=review['review_digest'],identity_digest=review['identity_digest'],
        scope_digest=snapshots.snapshot_scope('workspace','actor','original-uid'),**override)


async def test_snapshot_collection_is_in_actual_erasure_contract(replica_db):
    from outreach.core.erasure import DATA_COLLECTIONS
    assert 'outreach_template_metadata_snapshots' in DATA_COLLECTIONS


async def test_capture_is_immutable_encrypted_current_proof_only_and_does_not_edit_source(replica_db):
    row=await seed(replica_db);before=await replica_db.outreach_template_revisions.find({}).to_list(10)
    first=await capture(replica_db,row);saved=await replica_db.outreach_template_metadata_snapshots.find_one({})
    second=await capture(replica_db,row)
    assert first==second and saved==await replica_db.outreach_template_metadata_snapshots.find_one({})
    assert b'Private' not in BSON.encode(saved) and 'ciphertext' not in first and 'name' not in first
    assert await replica_db.outreach_templates.find_one({})==row
    assert await replica_db.outreach_template_revisions.find({}).to_list(10)==before
    await edit(replica_db,row)
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert await replica_db.outreach_template_metadata_snapshots.find_one({})==saved


@pytest.mark.parametrize('fault',['viewer','uid','duplicate_uid','code_role','stopped','checkpoint_missing',
    'terminal','index','wrong_key','count','bytes','corrupt'])
async def test_invalid_authority_history_storage_and_key_hold_without_snapshot_or_counter_write(replica_db,monkeypatch,fault):
    from outreach.core import template_metadata_snapshots as snapshots,template_history_storage as storage
    row=await seed(replica_db)
    if fault in {'wrong_key','corrupt'}:await capture(replica_db,row)
    if fault=='viewer':await replica_db.workspace_members.update_one({}, {'$set':{'role':'viewer'}})
    elif fault=='uid':await replica_db.users.update_one({}, {'$set':{'firebase_uid':'different'}})
    elif fault=='duplicate_uid':await replica_db.users.insert_one({'user_id':'other','firebase_uid':'original-uid'})
    elif fault=='code_role':await replica_db.workspace_members.update_one({}, {'$set':{'role':Code('admin')}})
    elif fault=='stopped':await replica_db.users.update_one({}, {'$set':{'status':'deletion_pending'}})
    elif fault=='checkpoint_missing':await replica_db.outreach_template_revisions.delete_many({})
    elif fault=='terminal':await remove(replica_db,row);await replica_db.outreach_templates.insert_one(row)
    elif fault=='index':await replica_db.outreach_template_metadata_snapshots.drop_index(storage.INDEX_NAME)
    elif fault=='wrong_key':monkeypatch.setattr(encryption,'_fernet',Fernet(Fernet.generate_key()))
    elif fault=='count':monkeypatch.setattr(snapshots,'MAX_SNAPSHOTS',0)
    elif fault=='bytes':monkeypatch.setattr(snapshots,'MAX_TOTAL_BYTES',1)
    elif fault=='corrupt':await replica_db.outreach_template_metadata_snapshots.update_one({}, {'$set':{'ciphertext':'plaintext'}})
    before=await replica_db.outreach_template_metadata_snapshots.find({}).to_list(10)
    users=await replica_db.users.find({}).to_list(5);members=await replica_db.workspace_members.find({}).to_list(5)
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert await replica_db.outreach_template_metadata_snapshots.find({}).to_list(10)==before
    assert await replica_db.users.find({}).to_list(5)==users and await replica_db.workspace_members.find({}).to_list(5)==members


@pytest.mark.parametrize('fault',['insert','readback'])
async def test_insert_or_readback_failure_rolls_back_capture_and_authority(replica_db,monkeypatch,fault):
    from outreach.core.suppression import SuppressionCollection
    row=await seed(replica_db);insert=SuppressionCollection.insert_one;find=SuppressionCollection.find_one
    async def broken_insert(self,*args,**kwargs):
        result=await insert(self,*args,**kwargs)
        if self.collection.name=='outreach_template_metadata_snapshots' and fault=='insert':raise ValueError('private error')
        return result
    async def broken_find(self,*args,**kwargs):
        result=await find(self,*args,**kwargs)
        return {**result,'ciphertext':'bad'} if result and self.collection.name=='outreach_template_metadata_snapshots' and fault=='readback' else result
    monkeypatch.setattr(SuppressionCollection,'insert_one',broken_insert);monkeypatch.setattr(SuppressionCollection,'find_one',broken_find)
    before=await replica_db.users.find_one({})
    with pytest.raises(HTTPException) as caught:await capture(replica_db,row)
    assert 'private error' not in str(caught.value.detail)
    assert await replica_db.outreach_template_metadata_snapshots.count_documents({})==0 and await replica_db.users.find_one({})==before


async def test_actual_erasure_purges_snapshots_even_after_template_deletion(replica_db):
    from outreach.core.erasure import OutreachErasure
    row=await seed(replica_db);await capture(replica_db,row);await remove(replica_db,row)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service=OutreachErasure(replica_db);await service.request('workspace','actor');inspection=await service.inspect('workspace')
    await service.finish('workspace','operator','Owned drained fixture',workers_drained=True,expected_digest=inspection['review_digest'])
    assert await replica_db.outreach_template_metadata_snapshots.count_documents({})==0
    with pytest.raises(HTTPException):await capture(replica_db,row)


async def test_standalone_cannot_capture(real_db):
    from outreach.core import template_metadata_snapshots as snapshots
    with pytest.raises(HTTPException) as caught:
        await snapshots.capture_snapshot(real_db,'workspace','actor','uid','tpl_custom_012345abcd',revision=1,
            review_digest='a'*64,identity_digest='b'*64,scope_digest=snapshots.snapshot_scope('workspace','actor','uid'))
    assert caught.value.status_code==503


async def test_missing_key_holds_without_plaintext_fallback(replica_db,monkeypatch):
    row=await seed(replica_db);monkeypatch.setattr(encryption,'_fernet',None);monkeypatch.delenv('ENCRYPTION_KEY',raising=False)
    with pytest.raises(HTTPException) as caught:await capture(replica_db,row)
    assert caught.value.status_code==503 and await replica_db.outreach_template_metadata_snapshots.count_documents({})==0


async def test_current_other_editor_repeat_preserves_original_ciphertext_and_attribution(replica_db):
    from outreach.core import template_metadata_snapshots as snapshots
    from outreach.core.template_governance import template_review
    row=await seed(replica_db);first=await capture(replica_db,row)
    saved=await replica_db.outreach_template_metadata_snapshots.find_one({})
    await replica_db.users.insert_one({'user_id':'editor','firebase_uid':'editor-uid','status':'active'})
    await replica_db.workspace_members.insert_one({'workspace_id':'workspace','user_id':'editor','role':'editor'})
    review=template_review(row,'workspace')
    again=await snapshots.capture_snapshot(replica_db,'workspace','editor','editor-uid',row['id'],
        revision=review['revision'],identity_digest=review['identity_digest'],review_digest=review['review_digest'],
        scope_digest=snapshots.snapshot_scope('workspace','editor','editor-uid'))
    assert again==first and saved==await replica_db.outreach_template_metadata_snapshots.find_one({})


async def test_cap_allows_exact_existing_capture_but_never_evicts_for_new_revision(replica_db,monkeypatch):
    from outreach.core import template_metadata_snapshots as snapshots
    row=await seed(replica_db);monkeypatch.setattr(snapshots,'MAX_SNAPSHOTS',1)
    first=await capture(replica_db,row);saved=await replica_db.outreach_template_metadata_snapshots.find_one({})
    assert await capture(replica_db,row)==first
    await edit(replica_db,row)
    with pytest.raises(HTTPException):await capture(replica_db,await replica_db.outreach_templates.find_one({}))
    assert saved==await replica_db.outreach_template_metadata_snapshots.find_one({})


async def test_unknown_commit_is_current_proof_only_idempotent_not_automatic_replay(replica_db,monkeypatch):
    from outreach.core import template_metadata_snapshots as snapshots
    from outreach.core.suppression import SuppressionUnavailable
    row=await seed(replica_db);commit=snapshots.mutate_suppression
    async def lost(*args,**kwargs):
        await commit(*args,**kwargs);raise SuppressionUnavailable('Owned lost acknowledgement')
    monkeypatch.setattr(snapshots,'mutate_suppression',lost)
    with pytest.raises(HTTPException) as caught:await capture(replica_db,row)
    assert caught.value.status_code==503
    saved=await replica_db.outreach_template_metadata_snapshots.find_one({});assert saved
    monkeypatch.setattr(snapshots,'mutate_suppression',commit)
    assert (await capture(replica_db,row))['snapshot_id']==saved['_id']
    assert saved==await replica_db.outreach_template_metadata_snapshots.find_one({})


async def test_oversized_snapshot_native_id_is_projected_to_small_sentinel(replica_db):
    from outreach.core import template_metadata_snapshots as snapshots
    from outreach.core.suppression import mutate_suppression
    row=await seed(replica_db);await capture(replica_db,row)
    original=await replica_db.outreach_template_metadata_snapshots.find_one({})
    await replica_db.outreach_template_metadata_snapshots.delete_one({'_id':original['_id']})
    await replica_db.outreach_template_metadata_snapshots.insert_one({**original,'_id':'z'*100_000})
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert (await replica_db.outreach_template_metadata_snapshots.find_one({}))['_id']=='z'*100_000


async def test_guard_orders_capture_before_edit_without_advancing_source_revision(replica_db,monkeypatch):
    from outreach.core import template_metadata_snapshots as snapshots
    row=await seed(replica_db);entered,released=asyncio.Event(),asyncio.Event();load=snapshots._retained
    async def pause(*args):
        result=await load(*args);entered.set();await released.wait();return result
    monkeypatch.setattr(snapshots,'_retained',pause)
    capturing=asyncio.create_task(capture(replica_db,row));await asyncio.wait_for(entered.wait(),5)
    editing=asyncio.create_task(edit(replica_db,row))
    try:await asyncio.sleep(0.05);assert not editing.done()
    finally:released.set()
    receipt,changed=await asyncio.gather(capturing,editing)
    assert receipt['revision']==1 and changed['new_revision']==2
    assert (await replica_db.outreach_template_metadata_snapshots.find_one({}))['revision']==1


async def test_final_revision_capture_does_not_increment_or_apply_edit_prohibition(replica_db):
    from datetime import datetime,timezone
    from bson import Int64
    from outreach.core.template_revision_checkpoints import checkpoint_for
    row=await seed(replica_db);row['template_revision']=Int64(2**53-1)
    await replica_db.outreach_templates.replace_one({'_id':row['_id']},row)
    await replica_db.outreach_template_revisions.insert_one(checkpoint_for(row,'actor',datetime(2026,10,19,tzinfo=timezone.utc)))
    assert (await capture(replica_db,row))['revision']==2**53-1
    assert await replica_db.outreach_templates.find_one({})==row


async def test_index_drift_rolls_back_new_snapshot_and_authority(replica_db,monkeypatch):
    from outreach.core import template_metadata_snapshots as snapshots,template_history_storage as storage
    row=await seed(replica_db);load=snapshots._retained;before=await replica_db.users.find_one({})
    async def drift(*args):
        result=await load(*args);await replica_db.outreach_template_metadata_snapshots.drop_index(storage.INDEX_NAME);return result
    monkeypatch.setattr(snapshots,'_retained',drift)
    with pytest.raises(HTTPException):await capture(replica_db,row)
    assert await replica_db.outreach_template_metadata_snapshots.count_documents({})==0
    assert await replica_db.users.find_one({})==before
