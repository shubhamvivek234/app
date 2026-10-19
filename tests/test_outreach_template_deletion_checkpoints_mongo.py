"""Native deletion continuity, rollback, resurrection holds and erasure."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os

from bson import BSON, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_revision_checkpoints as checkpoints
from outreach.core import template_deletions as deletions
from outreach.core import template_governance as governance
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, remove
from tests.test_outreach_template_graphs_mongo import seed as seed_older, edit as graph_edit
from tests.test_outreach_template_metadata_mongo import edit as metadata_edit
from tests.test_outreach_template_saves_mongo import post
from tests.test_outreach_template_deletions_mongo import save, status
from tests.test_outreach_template_deletions import content

pytestmark = [pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1',reason='Owned native Mongo opt-in')]


async def rows(db):
    return await db.outreach_template_revisions.find({}).to_list(30)


async def seed(db,basis='created'):
    await seed_authority(db)
    if basis == 'older': return await seed_older(db)
    response = await post(db); assert response.status_code == 200,response.text
    return await db.outreach_templates.find_one({})


async def delete(db,row,mode):
    return await remove(db,row) if mode == 'legacy' else await save(db,content(row))


@pytest.mark.parametrize('mode',['legacy','recoverable'])
@pytest.mark.parametrize('basis',['older','created'])
async def test_both_deletion_paths_atomically_link_terminal_to_last_native_revision(replica_db,mode,basis):
    original = await seed(replica_db,basis); recorded = deepcopy(await rows(replica_db))
    result = await delete(replica_db,original,mode)
    assert result['status'] == 'deleted' and await replica_db.outreach_templates.count_documents({}) == 0
    final = await rows(replica_db); assert len(final) == 2
    terminal = next(r for r in final if r['event'] == 'deleted'); parent = next(r for r in final if r['event'] != 'deleted')
    assert parent['event'] == ('observed' if basis == 'older' else 'created')
    assert terminal['revision'] == terminal['predecessor_revision'] == parent['revision']
    assert terminal['predecessor_review_digest'] == parent['review_digest'] == result['review_digest']
    assert terminal['identity_digest'] == parent['identity_digest'] == result['identity_digest']
    assert parent['_id'] != terminal['_id'] and all(len(r) == 12 for r in final)
    if recorded: assert BSON.encode(parent) == BSON.encode(recorded[0])
    assert set(await replica_db.outreach_template_revisions.index_information()) == {'_id_'}


@pytest.mark.parametrize('mode,fault',[(m,f) for m in ['legacy','recoverable'] for f in
    ['baseline_insert','baseline_readback','terminal_insert','terminal_readback']]+[('recoverable','receipt_insert'),('recoverable','receipt_readback')])
async def test_failure_after_delete_preserves_template_history_receipt_and_counters(replica_db,monkeypatch,mode,fault):
    original = await seed(replica_db,'older'); recorded = deepcopy(await rows(replica_db))
    authority = await replica_db.users.find_one({}); insert = SuppressionCollection.insert_one; find = SuppressionCollection.find_one
    async def broken_insert(self,document,*args,**kwargs):
        result = await insert(self,document,*args,**kwargs)
        if (self.collection.name == 'outreach_template_revisions' and
                (fault == 'baseline_insert' and document['event'] == 'observed' or fault == 'terminal_insert' and document['event'] == 'deleted')
                or self.collection.name == 'outreach_template_deletions' and fault == 'receipt_insert'):
            raise HTTPException(409,'Owned post-insert fault')
        return result
    async def broken_find(self,*args,**kwargs):
        result = await find(self,*args,**kwargs)
        if result and (self.collection.name == 'outreach_template_revisions' and
                (fault == 'baseline_readback' and result['event'] == 'observed' or fault == 'terminal_readback' and result['event'] == 'deleted')
                or self.collection.name == 'outreach_template_deletions' and fault == 'receipt_readback'):
            return {**result,'recorded_by':'corrupted-readback'}
        return result
    monkeypatch.setattr(SuppressionCollection,'insert_one',broken_insert); monkeypatch.setattr(SuppressionCollection,'find_one',broken_find)
    with pytest.raises(HTTPException): await delete(replica_db,original,mode)
    assert BSON.encode(await replica_db.outreach_templates.find_one({})) == BSON.encode(original)
    assert await rows(replica_db) == recorded and await replica_db.users.find_one({}) == authority
    assert await replica_db.outreach_template_deletions.count_documents({}) == 0


@pytest.mark.parametrize('mutation',['metadata','graph','deletion'])
@pytest.mark.parametrize('newer',[False,True])
async def test_same_native_restoration_stays_held_even_with_a_newer_revision(replica_db,mutation,newer):
    original = await seed(replica_db); await remove(replica_db,original)
    restored = {**original,'template_revision':2} if newer else original
    await replica_db.outreach_templates.insert_one(restored)
    recorded = deepcopy(await rows(replica_db)); authority = await replica_db.users.find_one({})
    action = metadata_edit if mutation == 'metadata' else graph_edit if mutation == 'graph' else remove
    with pytest.raises(HTTPException) as caught: await action(replica_db,restored)
    assert caught.value.status_code == 409
    assert await replica_db.outreach_templates.find_one({}) == restored and await rows(replica_db) == recorded
    assert await replica_db.users.find_one({}) == authority


@pytest.mark.parametrize('mode',['legacy','recoverable'])
async def test_final_javascript_safe_revision_deletes_without_overflow(replica_db,mode):
    original = await seed(replica_db,'older'); original['template_revision'] = Int64(governance.MAX_REVISION)
    await replica_db.outreach_templates.replace_one({'_id':original['_id']},original)
    result = await delete(replica_db,original,mode); assert result['revision'] == governance.MAX_REVISION
    final = await rows(replica_db); assert len(final) == 2
    assert all(r['revision'] == governance.MAX_REVISION for r in final)
    assert next(r for r in final if r['event'] == 'deleted')['predecessor_revision'] == governance.MAX_REVISION


@pytest.mark.parametrize('fault',['current_digest','parent_missing','parent_hash','future','capacity'])
async def test_unproven_or_exhausted_history_holds_delete_without_repair(replica_db,monkeypatch,fault):
    original = await seed(replica_db)
    if fault in {'parent_missing','parent_hash'}:
        await graph_edit(replica_db,original); original = await replica_db.outreach_templates.find_one({})
        if fault == 'parent_missing': await replica_db.outreach_template_revisions.delete_one({'event':'created'})
        else: await replica_db.outreach_template_revisions.update_one({'event':'graph'},{'$set':{'predecessor_review_digest':'a'*64}})
    elif fault == 'current_digest': await replica_db.outreach_template_revisions.update_one({},{'$set':{'review_digest':'a'*64}})
    elif fault == 'future':
        future = checkpoints.checkpoint_for({**original,'template_revision':3},'actor',datetime(2026,10,19,tzinfo=timezone.utc))
        future['template_id'] = 'tpl_custom_fffffffffe'; await replica_db.outreach_template_revisions.insert_one(future)
    else: monkeypatch.setattr(checkpoints,'MAX_CHECKPOINTS',1)
    recorded = deepcopy(await rows(replica_db)); authority = await replica_db.users.find_one({})
    with pytest.raises(HTTPException): await remove(replica_db,original)
    assert await replica_db.outreach_templates.find_one({}) == original and await rows(replica_db) == recorded
    assert await replica_db.users.find_one({}) == authority


async def test_unknown_committed_deletion_is_recovered_without_replaying_restored_original(replica_db,monkeypatch):
    original = await seed(replica_db); raw = content(original); commit = deletions.mutate_suppression
    async def lost(*args,**kwargs):
        await commit(*args,**kwargs); raise SuppressionUnavailable('Owned lost commit acknowledgement')
    monkeypatch.setattr(deletions,'mutate_suppression',lost)
    with pytest.raises(HTTPException) as caught: await save(replica_db,raw)
    assert caught.value.status_code == 503
    recorded = deepcopy(await rows(replica_db)); assert len(recorded) == 2
    await replica_db.outreach_templates.insert_one(original)
    monkeypatch.setattr(deletions,'mutate_suppression',commit)
    assert await status(replica_db,raw) == await save(replica_db,raw)
    assert await rows(replica_db) == recorded and await replica_db.outreach_templates.find_one({}) == original


@pytest.mark.parametrize('fault',['missing','corrupt'])
async def test_historical_receipt_does_not_backfill_or_repair_checkpoint_history(replica_db,fault):
    original = await seed(replica_db); raw = content(original); receipt = await save(replica_db,raw)
    if fault == 'missing': await replica_db.outreach_template_revisions.delete_many({})
    else: await replica_db.outreach_template_revisions.update_one({'event':'deleted'},{'$set':{'review_digest':'bad'}})
    recorded = deepcopy(await rows(replica_db))
    assert await save(replica_db,raw) == receipt == await status(replica_db,raw)
    assert await rows(replica_db) == recorded and await replica_db.outreach_templates.count_documents({}) == 0


async def test_graph_and_deletion_compete_for_one_original_successor(replica_db):
    original = await seed(replica_db)
    results = await asyncio.gather(graph_edit(replica_db,original),remove(replica_db,original),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in results) == 1
    recorded = await rows(replica_db); assert len(recorded) == 2
    deleted = any(r['event'] == 'deleted' for r in recorded)
    assert await replica_db.outreach_templates.count_documents({}) == (not deleted)
    assert sum(r['event'] in {'graph','deleted'} for r in recorded) == 1


async def test_duplicate_recoverable_deletions_commit_one_terminal(replica_db):
    original = await seed(replica_db); raw = content(original)
    a,b = await asyncio.gather(save(replica_db,raw),save(replica_db,raw)); assert a == b
    assert len(await rows(replica_db)) == 2
    assert await replica_db.outreach_template_revisions.count_documents({'event':'deleted'}) == 1
    assert await replica_db.outreach_template_deletions.count_documents({}) == 1


@pytest.mark.parametrize('ordinary_delete_held',[False,True])
async def test_guarded_workspace_erasure_purges_terminal_or_capacity_held_history(replica_db,monkeypatch,ordinary_delete_held):
    from outreach.core.erasure import OutreachErasure
    original = await seed(replica_db)
    if ordinary_delete_held:
        monkeypatch.setattr(checkpoints,'MAX_CHECKPOINTS',1)
        with pytest.raises(HTTPException): await remove(replica_db,original)
    else: await save(replica_db,content(original))
    assert len(await rows(replica_db)) == (1 if ordinary_delete_held else 2)
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service = OutreachErasure(replica_db); await service.request('workspace','actor'); inspected = await service.inspect('workspace')
    await service.finish('workspace','operator','Owned fixture writers drained.',workers_drained=True,expected_digest=inspected['review_digest'])
    for name in ['outreach_templates','outreach_template_revisions','outreach_template_deletions']:
        assert await replica_db[name].count_documents({}) == 0


@pytest.mark.parametrize('mode',['legacy','recoverable'])
async def test_standalone_denies_before_any_partial_deletion_history(real_db,mode):
    original = await seed(real_db,'older')
    with pytest.raises(HTTPException) as caught: await delete(real_db,original,mode)
    assert caught.value.status_code == 503
    assert await real_db.outreach_templates.find_one({}) == original and await rows(real_db) == []


async def test_missing_original_never_invents_a_deletion_checkpoint(replica_db):
    original = await seed(replica_db,'older'); await replica_db.outreach_templates.delete_many({})
    with pytest.raises(HTTPException) as caught: await remove(replica_db,original)
    assert caught.value.status_code == 404 and await rows(replica_db) == []


@pytest.mark.parametrize('mutation',['metadata','graph','deletion'])
@pytest.mark.parametrize('fault',['identifier','result_digest'])
async def test_malformed_stored_terminal_holds_restored_native_without_repair(replica_db,mutation,fault):
    original = await seed(replica_db); await remove(replica_db,original)
    terminal = await replica_db.outreach_template_revisions.find_one({'event':'deleted'})
    if fault == 'identifier':
        await replica_db.outreach_template_revisions.delete_one({'_id':terminal['_id']})
        await replica_db.outreach_template_revisions.insert_one({**terminal,'_id':'a'*64})
    else: await replica_db.outreach_template_revisions.update_one({'_id':terminal['_id']},{'$set':{'review_digest':'b'*64}})
    await replica_db.outreach_templates.insert_one(original)
    recorded = deepcopy(await rows(replica_db)); authority = await replica_db.users.find_one({})
    action = metadata_edit if mutation == 'metadata' else graph_edit if mutation == 'graph' else remove
    with pytest.raises(HTTPException) as caught: await action(replica_db,original)
    assert caught.value.status_code == 409
    assert await replica_db.outreach_templates.find_one({}) == original and await rows(replica_db) == recorded
    assert await replica_db.users.find_one({}) == authority


async def test_metadata_and_deletion_compete_for_one_original_successor(replica_db):
    original = await seed(replica_db)
    result = await asyncio.gather(metadata_edit(replica_db,original),remove(replica_db,original),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in result) == 1
    recorded = await rows(replica_db); assert len(recorded) == 2
    deleted = any(r['event'] == 'deleted' for r in recorded)
    assert await replica_db.outreach_templates.count_documents({}) == (not deleted)
    assert sum(r['event'] in {'metadata','deleted'} for r in recorded) == 1


async def test_deletion_succeeds_at_exact_checkpoint_capacity(replica_db,monkeypatch):
    original = await seed(replica_db); monkeypatch.setattr(checkpoints,'MAX_CHECKPOINTS',2)
    result = await remove(replica_db,original); assert result['status'] == 'deleted'
    recorded = await rows(replica_db); assert len(recorded) == 2
    assert {r['event'] for r in recorded} == {'created','deleted'}
