"""Actual creation/graph entry points, atomic lineage and failure boundaries."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os

from bson import BSON
from fastapi import HTTPException
import pytest

from outreach.core import template_revision_checkpoints as checkpoints
from outreach.core import template_governance as governance
from outreach.core import template_saves as saves
from outreach.core import template_graph_updates as graph_updates
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable, mutate_suppression
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, api_client, remove
from tests.test_outreach_template_saves_mongo import post, inspect, CONTENT
from tests.test_outreach_template_graphs_mongo import edit as graph_edit
from tests.test_outreach_template_graph_updates_mongo import save as graph_save, status as graph_status
from tests.test_outreach_template_graph_updates import content as graph_content
from tests.test_outreach_template_metadata_mongo import edit as metadata_edit

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]


async def create(db, mode):
    if mode == 'recoverable':
        response = await post(db)
    else:
        async with await api_client(db) as api:
            response = await api.post('/sequences/templates', json=json.loads(CONTENT))
    return response


async def edit_graph(db, row, mode):
    return await graph_save(db, graph_content(row)) if mode == 'recoverable' else await graph_edit(db, row)


async def rows(db):
    return await db.outreach_template_revisions.find({}).sort('revision', 1).to_list(30)


@pytest.mark.parametrize('creation_mode', ['legacy', 'recoverable'])
@pytest.mark.parametrize('graph_mode', ['legacy', 'recoverable'])
async def test_creation_graph_metadata_share_one_preserved_native_lineage(replica_db, creation_mode, graph_mode):
    await seed_authority(replica_db)
    response = await create(replica_db, creation_mode); assert response.status_code == 200, response.text
    first = await rows(replica_db); assert len(first) == 1 and first[0]['event'] == 'created'
    current = await replica_db.outreach_templates.find_one({})
    receipt = await edit_graph(replica_db, current, graph_mode)
    second = await rows(replica_db); assert [r['event'] for r in second] == ['created', 'graph']
    assert BSON.encode(second[0]) == BSON.encode(first[0])
    assert second[-1]['review_digest'] == receipt['new_review_digest']
    current = await replica_db.outreach_templates.find_one({}); await metadata_edit(replica_db, current)
    final = await rows(replica_db)
    assert [r['revision'] for r in final] == [1, 2, 3]
    assert [r['event'] for r in final] == ['created', 'graph', 'metadata']
    assert [BSON.encode(r) for r in final[:2]] == [BSON.encode(r) for r in second]
    for parent, child in zip(final, final[1:]):
        assert child['predecessor_revision'] == parent['revision']
        assert child['predecessor_review_digest'] == parent['review_digest']
    assert all(len(r) == 12 and not {'name', 'description', 'nodes', 'tree', 'firebase_uid'} & r.keys() for r in final)
    assert set(await replica_db.outreach_template_revisions.index_information()) == {'_id_'}


@pytest.mark.parametrize('later', ['corrupt_checkpoint', 'missing_checkpoint', 'delete'])
async def test_original_creation_receipt_does_not_backfill_or_inspect_history(replica_db, later):
    await seed_authority(replica_db); first = await post(replica_db); assert first.status_code == 200
    if later == 'corrupt_checkpoint':
        await replica_db.outreach_template_revisions.update_one({}, {'$set': {'event': 'broken'}})
    elif later == 'missing_checkpoint': await replica_db.outreach_template_revisions.delete_many({})
    else: await remove(replica_db, await replica_db.outreach_templates.find_one({}))
    before = deepcopy(await rows(replica_db))
    assert (await post(replica_db)).json() == (await inspect(replica_db)).json() == first.json()
    assert await rows(replica_db) == before
    assert await replica_db.outreach_templates.count_documents({}) == (later != 'delete')


@pytest.mark.parametrize('mode,fault', [(m,f) for m in ['legacy','recoverable'] for f in ['insert','readback']]
    + [('recoverable','receipt')])
async def test_creation_failure_rolls_back_template_checkpoint_receipt_and_counters(replica_db, monkeypatch, mode, fault):
    await seed_authority(replica_db); insert = SuppressionCollection.insert_one; find = SuppressionCollection.find_one
    async def broken_insert(self, *args, **kwargs):
        result = await insert(self, *args, **kwargs)
        if self.collection.name == ('outreach_template_revisions' if fault == 'insert' else 'outreach_template_saves' if fault == 'receipt' else ''):
            raise HTTPException(409, 'Owned after-insert failure')
        return result
    async def broken_find(self, *args, **kwargs):
        result = await find(self, *args, **kwargs)
        return {**result, 'recorded_by': 'wrong'} if fault == 'readback' and self.collection.name == 'outreach_template_revisions' and result else result
    monkeypatch.setattr(SuppressionCollection, 'insert_one', broken_insert)
    monkeypatch.setattr(SuppressionCollection, 'find_one', broken_find)
    result = await create(replica_db, mode); assert result.status_code == 409, result.text
    for name in ['outreach_templates', 'outreach_template_revisions', 'outreach_template_saves']:
        assert await replica_db[name].count_documents({}) == 0
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


@pytest.mark.parametrize('mode,fault', [(m,f) for m in ['legacy','recoverable'] for f in ['insert','readback']]
    + [('recoverable','receipt')])
async def test_graph_failure_preserves_original_and_checkpoint_bytes(replica_db, monkeypatch, mode, fault):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    original = await replica_db.outreach_templates.find_one({}); recorded = await rows(replica_db)
    authority = await replica_db.users.find_one({}); insert = SuppressionCollection.insert_one; find = SuppressionCollection.find_one
    async def broken_insert(self, document, *args, **kwargs):
        result = await insert(self, document, *args, **kwargs)
        if self.collection.name == 'outreach_template_revisions' and document['event'] == 'graph' and fault == 'insert' or self.collection.name == 'outreach_template_graph_updates' and fault == 'receipt':
            raise HTTPException(409, 'Owned graph insertion fault')
        return result
    async def broken_find(self, *args, **kwargs):
        result = await find(self, *args, **kwargs)
        if fault == 'readback' and self.collection.name == 'outreach_template_revisions' and result and result['event'] == 'graph':
            return {**result, 'review_digest': '0'*64}
        return result
    monkeypatch.setattr(SuppressionCollection, 'insert_one', broken_insert); monkeypatch.setattr(SuppressionCollection, 'find_one', broken_find)
    with pytest.raises(HTTPException): await edit_graph(replica_db, original, mode)
    assert await replica_db.outreach_templates.find_one({}) == original and await rows(replica_db) == recorded
    assert await replica_db.users.find_one({}) == authority
    assert await replica_db.outreach_template_graph_updates.count_documents({}) == 0


@pytest.mark.parametrize('fault', ['parent_missing','parent_hash','future','capacity'])
async def test_graph_holds_bad_retained_lineage_without_repair(replica_db, monkeypatch, fault):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({}); await graph_edit(replica_db, row)
    row = await replica_db.outreach_templates.find_one({})
    if fault == 'parent_missing': await replica_db.outreach_template_revisions.delete_one({'event':'created'})
    elif fault == 'parent_hash': await replica_db.outreach_template_revisions.update_one({'event':'graph'}, {'$set':{'predecessor_review_digest':'a'*64}})
    elif fault == 'future':
        future = checkpoints.checkpoint_for({**row,'template_revision':3},'actor',datetime(2026,10,19,tzinfo=timezone.utc))
        future['template_id'] = 'tpl_custom_fffffffffe'; await replica_db.outreach_template_revisions.insert_one(future)
    else: monkeypatch.setattr(checkpoints,'MAX_CHECKPOINTS',2)
    recorded = deepcopy(await rows(replica_db))
    with pytest.raises(HTTPException): await graph_edit(replica_db, row)
    assert await replica_db.outreach_templates.find_one({}) == row and await rows(replica_db) == recorded


async def test_graph_and_metadata_competitors_publish_only_one_successor(replica_db):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({})
    result = await asyncio.gather(graph_edit(replica_db,row),metadata_edit(replica_db,row),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in result) == 1
    recorded = await rows(replica_db); assert [r['revision'] for r in recorded] == [1,2]
    assert recorded[1]['predecessor_review_digest'] == recorded[0]['review_digest']


@pytest.mark.parametrize('mode',['creation','graph'])
async def test_unknown_commit_status_does_not_reappend_checkpoints(replica_db, monkeypatch, mode):
    await seed_authority(replica_db)
    if mode == 'graph':
        assert (await post(replica_db)).status_code == 200
        row = await replica_db.outreach_templates.find_one({}); raw = graph_content(row)
    service = saves if mode == 'creation' else graph_updates; commit = service.mutate_suppression
    async def lost(*args,**kwargs):
        await commit(*args,**kwargs); raise SuppressionUnavailable('Owned commit acknowledgement loss')
    monkeypatch.setattr(service,'mutate_suppression',lost)
    if mode == 'creation': assert (await post(replica_db)).status_code == 503
    else:
        with pytest.raises(HTTPException): await graph_save(replica_db,raw)
    before = deepcopy(await rows(replica_db)); assert len(before) == (1 if mode == 'creation' else 2)
    monkeypatch.setattr(service,'mutate_suppression',commit)
    if mode == 'creation': assert (await inspect(replica_db)).status_code == 200
    else: assert (await graph_status(replica_db,raw))['new_revision'] == 2
    assert await rows(replica_db) == before


@pytest.mark.parametrize('change',[{}, {'template_id':'tpl_custom_fffffffffe'}, {'revision':'1'}])
async def test_creation_admission_rejects_any_existing_native_identity_history(replica_db, change):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({}); before = await rows(replica_db)
    if change: await replica_db.outreach_template_revisions.update_one({}, {'$set':change})
    existing = deepcopy(await rows(replica_db)); authority = await replica_db.users.find_one({})
    async def attempt(current):
        await governance.authorize_create(current,'actor','original-uid')
        await checkpoints.append_creation_checkpoint(current,row,'actor',datetime(2026,10,19,tzinfo=timezone.utc))
    with pytest.raises(HTTPException): await mutate_suppression(replica_db,'workspace',attempt)
    assert await rows(replica_db) == existing and await replica_db.users.find_one({}) == authority
    assert len(before) == 1


@pytest.mark.parametrize('mode',['legacy','recoverable'])
async def test_standalone_creation_has_no_partial_history_or_template(real_db,mode):
    await seed_authority(real_db)
    result = await create(real_db,mode); assert result.status_code == 503
    for name in ['outreach_templates','outreach_template_revisions','outreach_template_saves']:
        assert await real_db[name].count_documents({}) == 0


@pytest.mark.parametrize('mode',['legacy','recoverable'])
async def test_creation_requires_exact_template_readback_before_any_checkpoint(replica_db,monkeypatch,mode):
    await seed_authority(replica_db); find = SuppressionCollection.find_one
    async def drift(self,*args,**kwargs):
        row = await find(self,*args,**kwargs)
        return {**row,'description':'changed during readback'} if self.collection.name == 'outreach_templates' and row else row
    monkeypatch.setattr(SuppressionCollection,'find_one',drift)
    result = await create(replica_db,mode); assert result.status_code == (409 if mode == 'legacy' else 503)
    for name in ['outreach_templates','outreach_template_revisions','outreach_template_saves']:
        assert await replica_db[name].count_documents({}) == 0


@pytest.mark.parametrize('mode',['legacy','recoverable'])
async def test_creation_obeys_checkpoint_capacity_before_committing(replica_db,monkeypatch,mode):
    await seed_authority(replica_db); monkeypatch.setattr(checkpoints,'MAX_CHECKPOINTS',0)
    result = await create(replica_db,mode); assert result.status_code == 409
    assert await replica_db.outreach_templates.count_documents({}) == 0 and await rows(replica_db) == []


@pytest.mark.parametrize('change',['missing','corrupt'])
async def test_historical_graph_result_precedes_current_checkpoint_inspection(replica_db,change):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({}); raw = graph_content(row)
    receipt = await graph_save(replica_db,raw)
    if change == 'missing': await replica_db.outreach_template_revisions.delete_many({})
    else: await replica_db.outreach_template_revisions.update_one({'event':'graph'},{'$set':{'predecessor_review_digest':'bad'}})
    recorded = deepcopy(await rows(replica_db)); current = await replica_db.outreach_templates.find_one({})
    assert await graph_save(replica_db,raw) == receipt == await graph_status(replica_db,raw)
    assert await rows(replica_db) == recorded and await replica_db.outreach_templates.find_one({}) == current


async def test_reused_public_id_creation_starts_distinct_native_history(replica_db):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    old = await replica_db.outreach_templates.find_one({}); await graph_edit(replica_db,old)
    recorded = deepcopy(await rows(replica_db)); await remove(replica_db,await replica_db.outreach_templates.find_one({}))
    doc = {k:v for k,v in old.items() if k not in {'_id','template_revision'}}
    await governance.create_template(replica_db,'workspace','actor',doc,authenticated_uid='original-uid')
    current = await replica_db.outreach_templates.find_one({}); assert current['_id'] != old['_id'] and current['id'] == old['id']
    all_rows = await rows(replica_db); assert len(all_rows) == 4
    assert await replica_db.outreach_template_revisions.count_documents({'identity_digest':recorded[0]['identity_digest']}) == 3
    assert sum(r['event'] == 'deleted' for r in all_rows) == 1
    new = [r for r in all_rows if r['identity_digest'] != recorded[0]['identity_digest']]
    assert len(new) == 1 and new[0]['event'] == 'created' and new[0]['predecessor_revision'] is None


async def test_duplicate_creation_requests_commit_one_creation_checkpoint(replica_db):
    await seed_authority(replica_db); results = await asyncio.gather(post(replica_db),post(replica_db))
    assert all(r.status_code == 200 for r in results) and results[0].json() == results[1].json()
    recorded = await rows(replica_db); assert len(recorded) == 1 and recorded[0]['event'] == 'created'
    assert await replica_db.outreach_templates.count_documents({}) == await replica_db.outreach_template_saves.count_documents({}) == 1


async def test_guarded_graph_of_older_template_records_observed_not_created(replica_db):
    from tests.test_outreach_template_graphs_mongo import seed
    await seed_authority(replica_db); original = await seed(replica_db); await graph_edit(replica_db,original)
    recorded = await rows(replica_db)
    assert [r['event'] for r in recorded] == ['observed','graph'] and [r['revision'] for r in recorded] == [0,1]
    assert recorded[1]['predecessor_review_digest'] == recorded[0]['review_digest']


async def test_actual_erasure_purges_creation_and_graph_even_after_template_deleted(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({}); await graph_edit(replica_db,row)
    await remove(replica_db,await replica_db.outreach_templates.find_one({})); assert len(await rows(replica_db)) == 3
    assert sum(r['event'] == 'deleted' for r in await rows(replica_db)) == 1
    await replica_db.workspaces.insert_one({'workspace_id':'workspace','owner_id':'actor'})
    service = OutreachErasure(replica_db); await service.request('workspace','actor'); inspected = await service.inspect('workspace')
    await service.finish('workspace','operator','Owned fixture writers drained.',workers_drained=True,expected_digest=inspected['review_digest'])
    for name in ['outreach_templates','outreach_template_revisions','outreach_template_saves','outreach_template_graph_updates']:
        assert await replica_db[name].count_documents({}) == 0


@pytest.mark.parametrize('kind',['metadata','graph'])
async def test_earlier_revision_contradicting_creation_holds_all_writes(replica_db,kind):
    await seed_authority(replica_db); assert (await post(replica_db)).status_code == 200
    row = await replica_db.outreach_templates.find_one({})
    contradiction = checkpoints.checkpoint_for({**row,'template_revision':0},'actor',datetime(2026,10,19,tzinfo=timezone.utc))
    await replica_db.outreach_template_revisions.insert_one(contradiction)
    recorded = deepcopy(await rows(replica_db)); authority = await replica_db.users.find_one({})
    with pytest.raises(HTTPException) as caught:
        await (metadata_edit(replica_db,row) if kind == 'metadata' else graph_edit(replica_db,row))
    assert caught.value.status_code == 409
    assert await replica_db.outreach_templates.find_one({}) == row and await rows(replica_db) == recorded
    assert await replica_db.users.find_one({}) == authority
