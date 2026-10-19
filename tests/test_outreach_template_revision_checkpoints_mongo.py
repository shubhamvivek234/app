"""Actual guarded metadata revisions, immutable records, rollback and erasure."""
import asyncio
from copy import deepcopy
import os

from bson import BSON, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core import template_metadata_updates as updates
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed, seed_authority
from tests.test_outreach_template_metadata_mongo import edit
from tests.test_outreach_template_metadata_updates_mongo import save, status
from tests.test_outreach_template_metadata_updates import content

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]


async def rows(db):
    return await db.outreach_template_revisions.find({}).sort('revision', 1).to_list(20)


async def test_legacy_and_recoverable_metadata_share_atomic_minimal_checkpoints(replica_db):
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    first = await edit(replica_db, original)
    initial = await rows(replica_db)
    assert [r['event'] for r in initial] == ['observed', 'metadata']
    assert [r['revision'] for r in initial] == [0, 1]
    assert initial[1]['predecessor_review_digest'] == initial[0]['review_digest']
    assert initial[1]['review_digest'] == first['new_review_digest']
    current = await replica_db.outreach_templates.find_one({})
    raw = content(current, name='Later');receipt = await save(replica_db, raw)
    recorded = await rows(replica_db)
    assert [r['revision'] for r in recorded] == [0, 1, 2]
    assert [BSON.encode(r) for r in recorded[:2]] == [BSON.encode(r) for r in initial]
    assert await save(replica_db, raw) == receipt == await status(replica_db, raw)
    assert await rows(replica_db) == recorded
    assert all(not {'name', 'description', 'nodes', 'edges', 'tree', 'firebase_uid', 'content_json'} & set(r) for r in recorded)
    indexes = await replica_db.outreach_template_revisions.index_information()
    assert set(indexes) == {'_id_'}


async def test_replacement_native_identity_cannot_inherit_previous_revision_entries(replica_db):
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    await edit(replica_db, original);first = await rows(replica_db)
    await replica_db.outreach_templates.delete_many({})
    replacement = {**original, '_id': ObjectId()}
    await replica_db.outreach_templates.insert_one(replacement);await edit(replica_db, replacement)
    assert await replica_db.outreach_template_revisions.count_documents({}) == 4
    assert await replica_db.outreach_template_revisions.count_documents({'identity_digest': first[0]['identity_digest']}) == 2


async def test_restored_prior_revision_is_held_when_same_native_has_a_future_checkpoint(replica_db):
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    await edit(replica_db, original);recorded = await rows(replica_db)
    await replica_db.outreach_templates.replace_one({'_id': original['_id']}, original)
    with pytest.raises(HTTPException): await edit(replica_db, original, name='Attempt replay')
    assert await replica_db.outreach_templates.find_one({}) == original and await rows(replica_db) == recorded


async def test_uncheckpointed_revision_is_observed_without_inventing_missing_history(replica_db):
    from tests.test_outreach_template_graphs_mongo import seed as graph_seed
    await seed_authority(replica_db);original = await graph_seed(replica_db)
    await edit(replica_db, original)
    # Simulate a genuinely older/raw writer: current guarded graph edits now participate.
    await replica_db.outreach_templates.update_one({'_id': original['_id']},
        {'$set': {'template_revision': 2, 'graph_updated_by': 'older-raw-writer'}})
    current = await replica_db.outreach_templates.find_one({});assert current['template_revision'] == 2
    await edit(replica_db, current, name='After graph')
    recorded = await rows(replica_db)
    assert [r['revision'] for r in recorded] == [0, 1, 2, 3]
    assert recorded[2]['event'] == 'observed' and recorded[2]['predecessor_revision'] is None


@pytest.mark.parametrize('change', [{'extra': 'never repair'}, {'revision': True}, {'review_digest': 'a'*64}])
async def test_existing_checkpoint_corruption_blocks_without_rewriting_it(replica_db, change):
    await seed_authority(replica_db);original, _ = await seed(replica_db);await edit(replica_db, original)
    current = await replica_db.outreach_templates.find_one({})
    await replica_db.outreach_template_revisions.update_one({'revision': 1}, {'$set': change})
    corrupted = await rows(replica_db)
    with pytest.raises(HTTPException): await edit(replica_db, current, name='Blocked')
    assert await replica_db.outreach_templates.find_one({}) == current and await rows(replica_db) == corrupted


@pytest.mark.parametrize('fault', ['baseline_insert', 'result_insert', 'baseline_readback', 'result_readback', 'receipt_insert'])
async def test_checkpoint_template_receipt_and_authority_roll_back_together(replica_db, monkeypatch, fault):
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    insert = SuppressionCollection.insert_one;find = SuppressionCollection.find_one
    async def broken_insert(self, document, *args, **kwargs):
        if (self.collection.name == 'outreach_template_revisions'
                and (fault == 'baseline_insert' and document['event'] == 'observed'
                    or fault == 'result_insert' and document['event'] == 'metadata')
                or self.collection.name == 'outreach_template_metadata_updates' and fault == 'receipt_insert'):
            raise SuppressionUnavailable('Owned insertion fault')
        return await insert(self, document, *args, **kwargs)
    async def broken_find(self, *args, **kwargs):
        result = await find(self, *args, **kwargs)
        if self.collection.name == 'outreach_template_revisions' and result is not None:
            if fault == 'baseline_readback' and result['event'] == 'observed' or fault == 'result_readback' and result['event'] == 'metadata':
                return {**result, 'recorded_by': 'another-actor'}
        return result
    monkeypatch.setattr(SuppressionCollection, 'insert_one', broken_insert)
    monkeypatch.setattr(SuppressionCollection, 'find_one', broken_find)
    with pytest.raises(HTTPException): await save(replica_db, content(original))
    assert await replica_db.outreach_templates.find_one({}) == original
    assert await replica_db.outreach_template_revisions.count_documents({}) == 0
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 0
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_concurrent_metadata_originals_have_one_revision_lineage(replica_db):
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    results = await asyncio.gather(edit(replica_db, original, name='First'), edit(replica_db, original, name='Second'), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert [r['revision'] for r in await rows(replica_db)] == [0, 1]


async def test_actual_erasure_purges_checkpoints_even_after_template_deletion(replica_db):
    from outreach.core.erasure import OutreachErasure
    from tests.test_outreach_template_governance_mongo import remove
    await seed_authority(replica_db);original, _ = await seed(replica_db);await edit(replica_db, original)
    await remove(replica_db, await replica_db.outreach_templates.find_one({}))
    assert len(await rows(replica_db)) == 3
    assert sum(r['event'] == 'deleted' for r in await rows(replica_db)) == 1
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    service = OutreachErasure(replica_db);await service.request('workspace', 'actor');inspected = await service.inspect('workspace')
    await service.finish('workspace', 'operator', 'Owned fixture writers drained.', workers_drained=True, expected_digest=inspected['review_digest'])
    assert await replica_db.outreach_template_revisions.count_documents({}) == 0


async def test_lost_commit_acknowledgement_recovers_receipt_without_appending_again(replica_db, monkeypatch):
    await seed_authority(replica_db);original, _ = await seed(replica_db);raw = content(original)
    commit = updates.mutate_suppression
    async def lost(*args, **kwargs):
        await commit(*args, **kwargs);raise SuppressionUnavailable('Owned lost acknowledgement')
    monkeypatch.setattr(updates, 'mutate_suppression', lost)
    with pytest.raises(HTTPException): await save(replica_db, raw)
    recorded = deepcopy(await rows(replica_db));assert len(recorded) == 2
    monkeypatch.setattr(updates, 'mutate_suppression', commit)
    assert (await status(replica_db, raw))['new_revision'] == 1 and await rows(replica_db) == recorded


@pytest.mark.parametrize('fault', ['changed', 'missing'])
async def test_declared_parent_must_exist_and_match_before_extending_lineage(replica_db, fault):
    await seed_authority(replica_db);original, _ = await seed(replica_db);await edit(replica_db, original)
    current = await replica_db.outreach_templates.find_one({})
    if fault == 'changed':
        await replica_db.outreach_template_revisions.update_one({'revision': 1}, {'$set': {'predecessor_review_digest': 'a'*64}})
    else: await replica_db.outreach_template_revisions.delete_one({'revision': 0})
    recorded = await rows(replica_db)
    with pytest.raises(HTTPException): await edit(replica_db, current, name='Must hold')
    assert await replica_db.outreach_templates.find_one({}) == current and await rows(replica_db) == recorded


@pytest.mark.parametrize('fault', ['template_id', 'revision'])
async def test_contradictory_future_record_cannot_escape_native_identity_inspection(replica_db, fault):
    from datetime import datetime, timezone
    from outreach.core.template_revision_checkpoints import checkpoint_for
    await seed_authority(replica_db);original, _ = await seed(replica_db)
    future = checkpoint_for({**original, 'template_revision': 4}, 'actor', datetime(2026, 10, 19, tzinfo=timezone.utc))
    if fault == 'template_id': future['template_id'] = 'tpl_custom_fffffffffe'
    else: future['revision'] = '4'
    await replica_db.outreach_template_revisions.insert_one(future)
    with pytest.raises(HTTPException): await edit(replica_db, original)
    assert await replica_db.outreach_templates.find_one({}) == original
    assert await replica_db.outreach_template_revisions.count_documents({}) == 1


async def test_identity_checkpoint_capacity_holds_without_eviction_or_partial_edit(replica_db, monkeypatch):
    from outreach.core import template_revision_checkpoints as checkpoints
    await seed_authority(replica_db);original, _ = await seed(replica_db);await edit(replica_db, original)
    current = await replica_db.outreach_templates.find_one({});recorded = await rows(replica_db)
    monkeypatch.setattr(checkpoints, 'MAX_CHECKPOINTS', 2)
    with pytest.raises(HTTPException): await edit(replica_db, current)
    assert await replica_db.outreach_templates.find_one({}) == current and await rows(replica_db) == recorded
