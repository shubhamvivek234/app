"""Owned database recovery, atomicity, authority, and HTTP contracts."""
import asyncio
from copy import deepcopy
import json
import os

from bson import BSON, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core import template_metadata_updates as updates
from outreach.core import template_metadata as metadata
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed, seed_authority, api_client, remove
from tests.test_outreach_template_metadata_updates import content, REQUEST

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]


def body(raw):
    return {**{k:v for k,v in updates.update_context('workspace', 'actor', 'original-uid').items()
        if k != 'execution_authorized'}, 'request_id': REQUEST, 'input_digest': updates.input_digest(raw), 'content_json': raw}


async def save(db, raw, request=REQUEST):
    b = body(raw)
    return await updates.save_update(db, 'workspace', 'actor', 'original-uid', request,
        b['scope_digest'], raw, b['input_digest'])


async def status(db, raw):
    b = body(raw)
    return await updates.inspect_update(db, 'workspace', 'actor', 'original-uid', REQUEST,
        b['scope_digest'], b['input_digest'])


async def test_original_retry_status_and_reference_only_receipt(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    first = await save(replica_db, raw); saved = await replica_db.outreach_templates.find_one({})
    assert saved['name'] == 'Renamed ☕' and saved['template_revision'] == 1
    assert first['new_review_digest'] == metadata.metadata_review(saved, 'workspace', 'actor', 'original-uid')['review_digest']
    async def forbidden(*args, **kwargs): raise AssertionError('Historical operation cannot apply again')
    monkeypatch.setattr(metadata, '_replace_metadata', forbidden)
    monkeypatch.setattr(updates, 'prepare_update', lambda *args: (_ for _ in ()).throw(AssertionError('No revalidation')))
    assert await save(replica_db, raw) == first == await status(replica_db, raw)
    assert await replica_db.outreach_templates.find_one({}) == saved
    stored = await replica_db.outreach_template_metadata_updates.find_one({})
    assert not {'name', 'description', 'nodes', 'tree', 'content_json', 'firebase_uid'} & set(stored)
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 1
    assert (await replica_db.outreach_template_metadata_updates.index_information())['_id_']['key'] == [('_id', 1)]


@pytest.mark.parametrize('later', ['metadata', 'graph', 'delete', 'native_replacement'])
async def test_historical_receipt_survives_later_template_state(replica_db, later):
    await seed_authority(replica_db)
    if later == 'graph':
        from tests.test_outreach_template_graphs_mongo import seed as graph_seed
        row = await graph_seed(replica_db)
    else:
        row, _ = await seed(replica_db)
    raw = content(row)
    first = await save(replica_db, raw); current = await replica_db.outreach_templates.find_one({})
    if later == 'metadata':
        from tests.test_outreach_template_metadata_mongo import edit
        await edit(replica_db, current, name='Later')
    elif later == 'graph':
        from tests.test_outreach_template_graphs_mongo import edit
        await edit(replica_db, current)
    elif later == 'delete': await remove(replica_db, current)
    else:
        await replica_db.outreach_templates.delete_one({})
        await replica_db.outreach_templates.insert_one({**current, '_id': ObjectId(), 'name': 'Replacement'})
    before = await replica_db.outreach_templates.find({}).to_list(5)
    assert await status(replica_db, raw) == first == await save(replica_db, raw)
    assert await replica_db.outreach_templates.find({}).to_list(5) == before


async def test_concurrent_identical_requests_commit_one_increment(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    first, second = await asyncio.gather(save(replica_db, raw), save(replica_db, raw))
    assert first == second and (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 1


@pytest.mark.parametrize('same_reference', [True, False])
async def test_competing_originals_have_one_winner(replica_db, same_reference):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    results = await asyncio.gather(save(replica_db, content(row)), save(replica_db, content(row, name='Other'),
        REQUEST if same_reference else 'fedcba98-7654-3210-fedc-ba9876543210'), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 1


@pytest.mark.parametrize('phase', ['initial', 'status', 'retry'])
@pytest.mark.parametrize('change', ['role', 'uid', 'erased'])
async def test_every_path_rechecks_current_authority(replica_db, phase, change):
    from outreach.core.erasure import stop_identity
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    if phase != 'initial': await save(replica_db, raw)
    if change == 'role': await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
    elif change == 'uid': await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'replacement'}})
    else: await stop_identity(replica_db, 'original-uid')
    with pytest.raises(HTTPException) as caught:
        await (status(replica_db, raw) if phase == 'status' else save(replica_db, raw))
    assert caught.value.status_code == 403
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == (phase != 'initial')


@pytest.mark.parametrize('fault', ['insert', 'receipt_readback', 'template_readback'])
async def test_receipt_or_template_failure_rolls_back_both_and_authority(replica_db, monkeypatch, fault):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    if fault == 'insert':
        original = SuppressionCollection.insert_one
        async def broken(self, *args, **kwargs):
            if self.collection.name == 'outreach_template_metadata_updates': raise SuppressionUnavailable('Owned fault')
            return await original(self, *args, **kwargs)
        monkeypatch.setattr(SuppressionCollection, 'insert_one', broken)
    else:
        original = SuppressionCollection.find_one
        async def broken(self, *args, **kwargs):
            result = await original(self, *args, **kwargs)
            if result and self.collection.name == ('outreach_templates' if fault == 'template_readback' else 'outreach_template_metadata_updates'):
                return {**result, 'future_corruption': True}
            return result
        monkeypatch.setattr(SuppressionCollection, 'find_one', broken)
    with pytest.raises(HTTPException): await save(replica_db, raw)
    assert BSON.encode(await replica_db.outreach_templates.find_one({})) == BSON.encode(row)
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 0
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_commit_ack_loss_recovers_by_original_status_without_replay(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    original = updates.mutate_suppression
    async def lost(*args):
        await original(*args); raise SuppressionUnavailable('Owned lost acknowledgement')
    monkeypatch.setattr(updates, 'mutate_suppression', lost)
    with pytest.raises(HTTPException) as caught: await save(replica_db, raw)
    assert caught.value.status_code == 503
    monkeypatch.setattr(updates, 'mutate_suppression', original)
    assert (await status(replica_db, raw))['new_revision'] == 1
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1


async def test_actual_erasure_purges_receipt_and_blocks_recovery(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row); await save(replica_db, raw)
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    service = OutreachErasure(replica_db); await service.request('workspace', 'actor'); inspected = await service.inspect('workspace')
    await service.finish('workspace', 'operator', 'Owned fixture writers drained.', workers_drained=True, expected_digest=inspected['review_digest'])
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 0
    with pytest.raises(HTTPException): await status(replica_db, raw)


async def test_standalone_denies_without_template_or_receipt_changes(real_db):
    await seed_authority(real_db); row, _ = await seed(real_db)
    with pytest.raises(HTTPException) as caught: await save(real_db, content(row))
    assert caught.value.status_code == 503 and await real_db.outreach_templates.find_one({}) == row
    assert await real_db.outreach_template_metadata_updates.count_documents({}) == 0


async def test_http_context_submit_and_original_status_are_exact(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    async with await api_client(replica_db) as api:
        context = await api.get('/sequences/template-metadata-updates/context')
        assert context.status_code == 200 and context.json() == updates.update_context('workspace', 'actor', 'original-uid')
        first = await api.post('/sequences/template-metadata-updates', json=body(raw))
        assert first.status_code == 200, first.text
        result = await api.get('/sequences/template-metadata-updates/'+REQUEST,
            params={k:body(raw)[k] for k in ('workspace_id', 'scope_digest', 'input_digest')})
    assert result.status_code == 200 and result.json() == first.json()


@pytest.mark.parametrize('change', [{'contract_version': True}, {'workspace_id': 'other'}, {'scope_digest': 'a'*64},
    {'request_id': 'bad'}, {'input_digest': 'b'*64}, {'name': 'extra'}, {'content_json': 1}])
async def test_http_rejects_invalid_envelope_without_writes(replica_db, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    async with await api_client(replica_db) as api:
        result = await api.post('/sequences/template-metadata-updates', json={**body(content(row)), **change})
    assert result.status_code in {403, 422} and await replica_db.outreach_templates.find_one({}) == row
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 0


async def test_missing_original_status_is_held_not_negative_proof(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    with pytest.raises(HTTPException) as caught: await status(replica_db, content(row))
    assert caught.value.status_code == 404
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


@pytest.mark.parametrize('phase', ['initial', 'status', 'retry'])
@pytest.mark.parametrize('change', ['role', 'uid', 'user_stop'])
async def test_post_snapshot_authority_changes_retry_to_denial(replica_db, monkeypatch, phase, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    if phase != 'initial': await save(replica_db, raw)
    original = updates.governance.authorize_update; changed = False
    async def interleave(current, actor, uid):
        nonlocal changed
        await current.database.users.find_one({'user_id': actor}, session=current.session)
        if not changed:
            changed = True
            if change == 'role': await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
            elif change == 'uid': await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'replacement'}})
            else: await replica_db.users.update_one({}, {'$set': {'status': 'deletion_pending'}})
        await original(current, actor, uid)
    monkeypatch.setattr(updates.governance, 'authorize_update', interleave)
    with pytest.raises(HTTPException) as caught:
        await (status(replica_db, raw) if phase == 'status' else save(replica_db, raw))
    assert changed and caught.value.status_code == 403
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == (phase != 'initial')


@pytest.mark.parametrize('change', [{'review_scope_digest': 'a'*64}, {'new_revision': 3},
    {'template_id': ['tpl_custom_012345abcd']}, {'revision': True}])
async def test_persisted_receipt_corruption_holds_without_replacement(replica_db, change):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row); await save(replica_db, raw)
    await replica_db.outreach_template_metadata_updates.update_one({}, {'$set': change})
    before = await replica_db.outreach_template_metadata_updates.find_one({})
    for call in (status, save):
        with pytest.raises(HTTPException) as caught: await call(replica_db, raw)
        assert caught.value.status_code == 503
    assert await replica_db.outreach_template_metadata_updates.find_one({}) == before
    assert (await replica_db.outreach_templates.find_one({}))['template_revision'] == 1


async def test_valid_shape_changed_receipt_readback_rolls_back_actual_update(replica_db, monkeypatch):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    original = SuppressionCollection.find_one
    async def corrupt(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if result and self.collection.name == 'outreach_template_metadata_updates':
            return {**result, 'new_review_digest': 'e'*64}
        return result
    monkeypatch.setattr(SuppressionCollection, 'find_one', corrupt)
    with pytest.raises(HTTPException) as caught: await save(replica_db, raw)
    assert caught.value.status_code == 503
    assert await replica_db.outreach_templates.find_one({}) == row
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 0


@pytest.mark.parametrize('phase', ['initial', 'status'])
async def test_update_or_status_orders_before_guarded_erasure(replica_db, monkeypatch, phase):
    from outreach.core.erasure import OutreachErasure
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row)
    if phase == 'status': await save(replica_db, raw)
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    ready, release = asyncio.Event(), asyncio.Event(); original = updates.governance.authorize_update
    async def hold(current, actor, uid):
        await original(current, actor, uid); ready.set(); await release.wait()
    monkeypatch.setattr(updates.governance, 'authorize_update', hold)
    operation = asyncio.create_task(status(replica_db, raw) if phase == 'status' else save(replica_db, raw))
    await asyncio.wait_for(ready.wait(), 5)
    erasing = asyncio.create_task(OutreachErasure(replica_db).request('workspace', 'actor'))
    await asyncio.sleep(0.05); assert not erasing.done(); release.set()
    result, stopped = await asyncio.gather(operation, erasing)
    assert result['status'] == 'updated' and stopped['status'] == 'awaiting_drain'
    assert await replica_db.outreach_template_metadata_updates.count_documents({}) == 1


async def test_new_post_url_cannot_reach_retired_metadata_patch_handler():
    import httpx
    from fastapi import FastAPI
    app = FastAPI(); calls = []
    @app.patch('/sequences/templates/{template_id}/metadata-reviewed')
    async def old(template_id: str): calls.append(template_id); return {'status': 'updated'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as api:
        result = await api.post('/sequences/template-metadata-updates', json={})
    assert result.status_code == 404 and not calls


async def test_final_js_safe_revision_receipt_is_recoverable(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db)
    row['template_revision'] = 2**53-2
    await replica_db.outreach_templates.replace_one({'_id': row['_id']}, row)
    raw = content(row); first = await save(replica_db, raw)
    assert first['new_revision'] == 2**53-1 and await status(replica_db, raw) == first == await save(replica_db, raw)


async def test_status_wrong_input_scope_and_actor_never_disclose_receipt(replica_db):
    await seed_authority(replica_db); row, _ = await seed(replica_db); raw = content(row); await save(replica_db, raw)
    for scope, digest, expected in [(body(raw)['scope_digest'], 'a'*64, 409), ('a'*64, body(raw)['input_digest'], 403)]:
        with pytest.raises(HTTPException) as caught:
            await updates.inspect_update(replica_db, 'workspace', 'actor', 'original-uid', REQUEST, scope, digest)
        assert caught.value.status_code == expected
