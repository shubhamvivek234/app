"""Owned native metadata edits, current authority, rollback and HTTP contracts."""
import asyncio
from copy import deepcopy
import os

from bson import BSON, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core import template_metadata as metadata
from outreach.core import template_governance as governance
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed, seed_authority, api_client, remove

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]


def payload(row, **changes):
    review = metadata.metadata_review(row, 'workspace', 'actor', 'original-uid')
    return {**{key: review[key] for key in ('contract_version', 'workspace_id', 'revision',
        'review_digest', 'identity_digest', 'scope_digest')}, 'name': 'Renamed', 'description': '', **changes}


async def edit(db, row, **changes):
    body = payload(row, **changes)
    body.pop('contract_version'); body.pop('workspace_id')
    return await metadata.update_metadata(db, 'workspace', 'actor', row['id'],
        authenticated_uid='original-uid', **body)


async def test_edit_updates_only_metadata_revision_and_current_audit(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    row['future_metadata'] = {'$ne': 'literal'}
    await replica_db.outreach_templates.replace_one({'_id': row['_id']}, row)
    for collection in ['outreach_campaigns', 'outreach_sequence_versions', 'outreach_tasks', 'outreach_leads']:
        await replica_db[collection].insert_one({'workspace_id': 'workspace', 'copy': deepcopy(row)})
    before = {name: await replica_db[name].find({}).to_list(5) for name in
        ['outreach_campaigns', 'outreach_sequence_versions', 'outreach_tasks', 'outreach_leads']}
    receipt = await edit(replica_db, row)
    saved = await replica_db.outreach_templates.find_one({'_id': row['_id']})
    assert receipt == {**payload(row), 'status': 'updated', 'template_id': row['id'],
        'new_revision': 1, 'new_review_digest': metadata.metadata_review(saved, 'workspace', 'actor', 'original-uid')['review_digest']}
    assert saved['name'] == 'Renamed' and saved['description'] == '' and saved['template_revision'] == 1
    assert saved['metadata_updated_by'] == 'actor' and saved['metadata_updated_at'].microsecond % 1000 == 0
    excluded = {'name', 'description', 'template_revision', 'metadata_updated_by', 'metadata_updated_at'}
    assert BSON.encode({k:v for k,v in saved.items() if k not in excluded}) == BSON.encode({k:v for k,v in row.items() if k not in excluded})
    for name, original in before.items(): assert await replica_db[name].find({}).to_list(5) == original
    assert (await replica_db.users.find_one({}))['template_authority_revision'] == 1


@pytest.mark.parametrize('change', ['content', 'native', 'revision', 'duplicate', 'creator', 'graph'])
async def test_stale_review_never_overwrites_changed_or_replaced_template(replica_db, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    if change == 'native':
        await replica_db.outreach_templates.delete_one({})
        await replica_db.outreach_templates.insert_one({**row, '_id': ObjectId()})
    elif change == 'duplicate': await replica_db.outreach_templates.insert_one({**row, '_id': ObjectId()})
    else:
        patch = {'content': {'name': 'Other edit'}, 'revision': {'template_revision': 2},
            'creator': {'user_id': 'other'}, 'graph': {'nodes': []}}[change]
        await replica_db.outreach_templates.update_one({}, {'$set': patch})
    before = await replica_db.outreach_templates.find({}).to_list(5)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 409
    assert await replica_db.outreach_templates.find({}).to_list(5) == before
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


@pytest.mark.parametrize('case', ['viewer', 'uid', 'duplicate_uid', 'member_stop', 'user_stop', 'owner'])
async def test_current_update_authority_is_required(replica_db, case):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    if case == 'viewer': await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
    elif case == 'member_stop': await replica_db.workspace_members.update_one({}, {'$set': {'status': 'inactive'}})
    elif case == 'uid': await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'changed'}})
    elif case == 'user_stop': await replica_db.users.update_one({}, {'$set': {'status': 'deletion_pending'}})
    elif case == 'duplicate_uid': await replica_db.users.insert_one({'user_id': 'other', 'firebase_uid': ['original-uid']})
    else:
        await replica_db.workspace_members.delete_many({})
        await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'other'})
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 403
    assert await replica_db.outreach_templates.find_one({}) == row


async def test_editor_and_unique_owner_can_rename_workspace_shared_templates(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    await replica_db.workspace_members.update_one({}, {'$set': {'role': 'editor'}})
    await edit(replica_db, row)
    await replica_db.workspace_members.delete_many({})
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    saved = await replica_db.outreach_templates.find_one({}); await edit(replica_db, saved, name='Owner edit')
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 2


async def test_competing_edits_and_stale_delete_have_one_winner(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    results = await asyncio.gather(edit(replica_db, row, name='One'), edit(replica_db, row, name='Two'), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    with pytest.raises(HTTPException) as caught: await remove(replica_db, row)
    assert caught.value.status_code == 409
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1


@pytest.mark.parametrize('change', ['role', 'uid', 'content', 'native'])
async def test_mutation_after_snapshot_retries_to_denial(replica_db, monkeypatch, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    changed = False
    original = governance.authorize_update if change in {'role', 'uid'} else metadata.unique_resource
    async def interleave(*args):
        nonlocal changed
        if change in {'role', 'uid'}:
            current = args[0]
            await current.database.users.find_one({'user_id': 'actor'}, session=current.session)
        else: result = await original(*args)
        if not changed:
            changed = True
            if change == 'role': await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
            elif change == 'uid': await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'changed'}})
            elif change == 'content': await replica_db.outreach_templates.update_one({}, {'$set': {'name': 'Newer'}})
            else:
                await replica_db.outreach_templates.delete_one({})
                await replica_db.outreach_templates.insert_one({**row, '_id': ObjectId()})
        return await original(*args) if change in {'role', 'uid'} else result
    monkeypatch.setattr(governance if change in {'role', 'uid'} else metadata,
        'authorize_update' if change in {'role', 'uid'} else 'unique_resource', interleave)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert changed and caught.value.status_code == (403 if change in {'role', 'uid'} else 409)
    assert (await replica_db.outreach_templates.find_one({})).get('template_revision', 0) == 0


async def test_failure_after_write_rolls_back_template_and_authority(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    original = SuppressionCollection.replace_one
    async def fail(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if self.collection.name == 'outreach_templates': raise HTTPException(409, 'synthetic failure')
        return result
    monkeypatch.setattr(SuppressionCollection, 'replace_one', fail)
    with pytest.raises(HTTPException): await edit(replica_db, row)
    assert await replica_db.outreach_templates.find_one({}) == row
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_committed_acknowledgement_loss_is_held_without_replay(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db); calls = 0
    original = metadata.mutate_suppression
    async def lose(*args):
        nonlocal calls
        calls += 1; await original(*args); raise SuppressionUnavailable('synthetic lost ack')
    monkeypatch.setattr(metadata, 'mutate_suppression', lose)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 503 and calls == 1
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1
    monkeypatch.setattr(metadata, 'mutate_suppression', original)
    with pytest.raises(HTTPException) as stale: await edit(replica_db, row)
    assert stale.value.status_code == 409


async def test_stopped_and_erased_workspace_cannot_be_recreated(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    service = OutreachErasure(replica_db); await service.request('workspace', 'actor')
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 503
    inspected = await service.inspect('workspace')
    await service.finish('workspace', 'operator', 'Owned fixture writers drained.', workers_drained=True, expected_digest=inspected['review_digest'])
    with pytest.raises(HTTPException): await edit(replica_db, row)
    assert await replica_db.outreach_templates.count_documents({}) == 0


async def test_real_standalone_denies_metadata_changes(real_db):
    await seed_authority(real_db); row, _ = await seed(real_db)
    with pytest.raises(HTTPException) as caught: await edit(real_db, row)
    assert caught.value.status_code == 503 and await real_db.outreach_templates.find_one({}) == row


async def test_actual_http_review_edit_and_fresh_review(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    async with await api_client(replica_db) as api:
        before = await api.get('/sequences/templates')
        listed = next(item for item in before.json() if item['id'] == row['id'])
        assert listed['metadata_review']['reviewable'] and '_id' not in listed
        result = await api.patch('/sequences/templates/'+row['id']+'/metadata-reviewed', json=payload(row))
        assert result.status_code == 200, result.text
        after = await api.get('/sequences/templates')
    fresh = next(item for item in after.json() if item['id'] == row['id'])
    assert fresh['name'] == 'Renamed' and fresh['metadata_review']['revision'] == 1
    assert fresh['deletion_review']['revision'] == 1
    assert fresh['metadata_review']['review_digest'] == result.json()['new_review_digest']


@pytest.mark.parametrize('change', [
    {'revision': True}, {'revision': 1.0}, {'contract_version': True}, {'name': None},
    {'name': 1}, {'description': None}, {'name': ''}, {'name': ' '*3}, {'name': 'x'*101},
    {'description': 'x'*1001}, {'nodes': []}, {'is_custom': True}, {'workspace_id': []},
    {'scope_digest': 'bad'}, {'review_digest': None}, {'new_revision': 1},
])
async def test_http_rejects_coercion_and_out_of_scope_fields(replica_db, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    async with await api_client(replica_db) as api:
        result = await api.patch('/sequences/templates/'+row['id']+'/metadata-reviewed', json=payload(row, **change))
    assert result.status_code == 422, result.text
    assert await replica_db.outreach_templates.find_one({}) == row


@pytest.mark.parametrize('change', [{'workspace_id': 'other'}, {'scope_digest': 'a'*64},
    {'identity_digest': 'b'*64}, {'review_digest': 'c'*64}])
async def test_http_rejects_foreign_or_stale_reviews(replica_db, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    async with await api_client(replica_db) as api:
        result = await api.patch('/sequences/templates/'+row['id']+'/metadata-reviewed', json=payload(row, **change))
    assert result.status_code in {403, 409}
    assert await replica_db.outreach_templates.find_one({}) == row


async def test_edit_preserves_original_creation_receipt_and_replay_never_recompiles(replica_db):
    from outreach.core import template_saves
    from tests.test_outreach_template_saves_mongo import post, inspect, CONTENT, body
    from tests.test_outreach_template_saves import REQUEST
    await seed_authority(replica_db)
    first = await post(replica_db); assert first.status_code == 200
    row = await replica_db.outreach_templates.find_one({}); await edit(replica_db, row)
    saved = await replica_db.outreach_templates.find_one({})
    def forbidden(): raise AssertionError('A historical request must never recompile')
    replay = await template_saves.save_template(replica_db, 'workspace', 'actor', 'original-uid',
        REQUEST, body()['scope_digest'], CONTENT, body()['input_digest'], forbidden)
    assert replay == first.json() == (await inspect(replica_db)).json()
    assert replay['template_revision'] == 1 and saved['template_revision'] == 2
    assert await replica_db.outreach_templates.find_one({}) == saved
    assert await replica_db.outreach_template_saves.count_documents({}) == 1


async def test_simultaneous_original_edit_and_delete_have_one_winner(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    results = await asyncio.gather(edit(replica_db, row), remove(replica_db, row), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code in {404, 409} for result in results) == 1
    winner = next(result for result in results if isinstance(result, dict))
    assert await replica_db.outreach_templates.count_documents({}) == (1 if winner['status'] == 'updated' else 0)
    assert (await replica_db.users.find_one({}))['template_authority_revision'] == 1


async def test_delete_and_edit_scope_proofs_are_not_interchangeable(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    deletion = governance.scoped_review(row, 'workspace', 'actor', 'original-uid')
    with pytest.raises(HTTPException) as update: await edit(replica_db, row, scope_digest=deletion['scope_digest'])
    with pytest.raises(HTTPException) as delete: await remove(replica_db, row, scope_digest=payload(row)['scope_digest'])
    assert update.value.status_code == delete.value.status_code == 403
    assert await replica_db.outreach_templates.find_one({}) == row


async def test_maximum_revision_can_be_written_once_and_then_holds(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    row['template_revision'] = governance.MAX_REVISION-1
    await replica_db.outreach_templates.replace_one({'_id': row['_id']}, row)
    receipt = await edit(replica_db, row)
    saved = await replica_db.outreach_templates.find_one({})
    assert receipt['new_revision'] == governance.MAX_REVISION
    assert saved['template_revision'] == governance.MAX_REVISION
    assert metadata.metadata_review(saved, 'workspace', 'actor', 'original-uid')['reviewable'] is False


async def test_post_write_bson_mismatch_rolls_back_before_receipt(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    original = SuppressionCollection.find_one
    async def corrupt(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if self.collection.name == 'outreach_templates' and result:
            return {**result, 'nodes': []}
        return result
    monkeypatch.setattr(SuppressionCollection, 'find_one', corrupt)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 409
    assert await replica_db.outreach_templates.find_one({}) == row
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_new_full_row_bound_denies_without_committing_authority(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    monkeypatch.setattr(governance, 'MAX_RECORD_BYTES', len(BSON.encode(row))+5)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 422
    assert await replica_db.outreach_templates.find_one({}) == row
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_deleted_original_returns_missing_without_recreation(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db); await remove(replica_db, row)
    with pytest.raises(HTTPException) as caught: await edit(replica_db, row)
    assert caught.value.status_code == 404
    assert await replica_db.outreach_templates.count_documents({}) == 0
