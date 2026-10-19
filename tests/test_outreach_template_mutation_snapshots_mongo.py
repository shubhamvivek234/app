"""Atomic template/snapshot/receipt behavior against owned Mongo servers."""
import asyncio
import json
import os

from bson import BSON, Int64
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from outreach.core import template_graph_snapshots as graphs, template_metadata_snapshots as metadata
from outreach.core import template_history_storage as storage
from outreach.core import template_mutation_snapshots as snapshots
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from utils import encryption
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, remove
from tests.test_outreach_template_lifecycle_checkpoints_mongo import create
from tests.test_outreach_template_saves_mongo import post, inspect as save_status
from tests.test_outreach_template_metadata_mongo import edit as edit_metadata
from tests.test_outreach_template_graphs_mongo import edit as edit_graph
from tests.test_outreach_template_metadata_updates_mongo import save as save_metadata, status as metadata_status
from tests.test_outreach_template_graph_updates_mongo import save as save_graph, status as graph_status
from tests.test_outreach_template_deletions_mongo import save as save_deletion, status as deletion_status
from tests.test_outreach_template_metadata_updates import content as metadata_content
from tests.test_outreach_template_graph_updates import content as graph_content
from tests.test_outreach_template_deletions import content as deletion_content

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]
COLLECTIONS = ('users', 'workspace_members', 'outreach_templates', 'outreach_template_revisions',
    metadata.COLLECTION, graphs.COLLECTION, 'outreach_template_saves',
    'outreach_template_metadata_updates', 'outreach_template_graph_updates', 'outreach_template_deletions')


@pytest.fixture(autouse=True)
def owned_key_and_disabled_setting(monkeypatch):
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    monkeypatch.delenv(snapshots.SETTING, raising=False)


async def setup(db, monkeypatch, enabled=True):
    await seed_authority(db)
    # Ordinary HTTP auth hydration is outside the template transaction. Start
    # with the same resolved identity a real authenticated request supplies.
    await db.users.update_one({'user_id': 'actor'}, {'$set': {
        'default_workspace_id': 'workspace', 'workspace_ids': ['workspace']}})
    await storage.ensure_history_index(db)
    await metadata.prepare_storage(db)
    await graphs.prepare_storage(db)
    if enabled:
        monkeypatch.setenv(snapshots.SETTING, 'true')


async def state(db):
    return {name: [BSON.encode(row) for row in await db[name].find({}).sort('_id', 1).to_list(100)]
        for name in COLLECTIONS}


async def perform(db, row, operation, mode='recoverable'):
    if operation == 'created':
        result = await create(db, mode)
        if result.status_code != 200:
            raise HTTPException(result.status_code, result.text)
        return result.json()
    if operation == 'metadata':
        return await (save_metadata(db, metadata_content(row)) if mode == 'recoverable' else edit_metadata(db, row))
    if operation == 'graph':
        return await (save_graph(db, graph_content(row)) if mode == 'recoverable' else edit_graph(db, row))
    return await (save_deletion(db, deletion_content(row)) if mode == 'recoverable' else remove(db, row))


async def verify_pair(db, source):
    checkpoints = await db.outreach_template_revisions.find({'event': {'$ne': 'deleted'}}).to_list(100)
    checkpoint = next(row for row in checkpoints if row['revision'] == source['template_revision'])
    saved = []
    for codec in (metadata, graphs):
        row = await db[codec.COLLECTION].find_one({'_id': codec._id(checkpoint)})
        assert row is not None
        saved.append(row)
        content = codec.open_snapshot(row, checkpoint)
        expected = {key: source[key] for key in (('name', 'description') if codec is metadata else ('nodes', 'edges', 'tree'))}
        assert snapshots.canonical_json(content) == snapshots.canonical_json(expected)
    return saved


@pytest.mark.parametrize('mode', ['legacy', 'recoverable'])
async def test_creation_captures_both_kinds_in_original_transaction(replica_db, monkeypatch, mode):
    await setup(replica_db, monkeypatch)
    result = await perform(replica_db, None, 'created', mode)
    source = await replica_db.outreach_templates.find_one({})
    saved = await verify_pair(replica_db, source)
    assert source['template_revision'] == 1
    assert all(row['recorded_by'] == 'actor' for row in saved)
    assert not {'ciphertext', 'content_available', 'capture_complete', 'restore_available'} & result.keys()


@pytest.mark.parametrize('mode', ['legacy', 'recoverable'])
@pytest.mark.parametrize('operation', ['metadata', 'graph', 'deleted'])
async def test_mutation_retains_exact_pre_and_post_revision_pairs(replica_db, monkeypatch, mode, operation):
    await setup(replica_db, monkeypatch, enabled=False)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    monkeypatch.setenv(snapshots.SETTING, 'true')
    await perform(replica_db, original, operation, mode)
    await verify_pair(replica_db, original)
    if operation == 'deleted':
        assert await replica_db.outreach_templates.count_documents({}) == 0
        assert await replica_db[graphs.COLLECTION].count_documents({}) == 1
        assert await replica_db.outreach_template_revisions.count_documents({'event': 'deleted'}) == 1
    else:
        current = await replica_db.outreach_templates.find_one({})
        await verify_pair(replica_db, current)
        assert current['template_revision'] == 2
        assert await replica_db[graphs.COLLECTION].count_documents({}) == 2


async def test_disabled_rollout_preserves_creation_without_indexes_or_key(replica_db, monkeypatch):
    await seed_authority(replica_db)
    monkeypatch.setattr(encryption, '_fernet', None)
    monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    await perform(replica_db, None, 'created')
    assert await replica_db[graphs.COLLECTION].count_documents({}) == 0
    assert await replica_db[metadata.COLLECTION].count_documents({}) == 0
    assert storage.INDEX_NAME not in await replica_db.outreach_template_revisions.index_information()


@pytest.mark.parametrize('operation', ['created', 'metadata', 'graph', 'deleted'])
@pytest.mark.parametrize('fault', ['graph_insert', 'graph_readback', 'metadata_insert', 'receipt_insert'])
async def test_late_failure_rolls_back_mutation_both_snapshot_kinds_receipt_and_authority(
    replica_db, monkeypatch, operation, fault):
    await setup(replica_db, monkeypatch)
    original = None
    if operation != 'created':
        await perform(replica_db, None, 'created')
        original = await replica_db.outreach_templates.find_one({})
        # Force pre-image insertion too, proving no partial baseline is retained.
        await replica_db[graphs.COLLECTION].delete_many({})
        await replica_db[metadata.COLLECTION].delete_many({})
    before = await state(replica_db)
    insert, find = SuppressionCollection.insert_one, SuppressionCollection.find_one
    async def broken_insert(self, *args, **kwargs):
        result = await insert(self, *args, **kwargs)
        if ((fault == 'graph_insert' and self.collection.name == graphs.COLLECTION)
                or (fault == 'metadata_insert' and self.collection.name == metadata.COLLECTION)
                or (fault == 'receipt_insert' and self.collection.name in {
                    'outreach_template_saves', 'outreach_template_metadata_updates',
                    'outreach_template_graph_updates', 'outreach_template_deletions'})):
            raise HTTPException(409, 'Synthetic post-insert rollback')
        return result
    async def broken_find(self, *args, **kwargs):
        result = await find(self, *args, **kwargs)
        if fault == 'graph_readback' and self.collection.name == graphs.COLLECTION and result:
            return {**result, 'ciphertext': 'invalid'}
        return result
    monkeypatch.setattr(SuppressionCollection, 'insert_one', broken_insert)
    monkeypatch.setattr(SuppressionCollection, 'find_one', broken_find)
    with pytest.raises(HTTPException):
        await perform(replica_db, original, operation)
    assert await state(replica_db) == before


@pytest.mark.parametrize('fault', ['history_index', 'metadata_index', 'graph_index', 'missing_key',
    'graph_capacity', 'metadata_capacity', 'combined_bytes', 'unknown_config', 'missing_description'])
async def test_capture_prerequisites_and_legacy_content_hold_edit_atomically(replica_db, monkeypatch, fault):
    await setup(replica_db, monkeypatch, enabled=False)
    await perform(replica_db, None, 'created')
    if fault == 'unknown_config':
        await replica_db.outreach_templates.update_one({}, {'$set': {'nodes.0.config.credential': 'private-secret'}})
    if fault == 'missing_description':
        await replica_db.outreach_templates.update_one({}, {'$unset': {'description': ''}})
    original = await replica_db.outreach_templates.find_one({})
    if fault.endswith('_index'):
        target = {'history_index': 'outreach_template_revisions', 'metadata_index': metadata.COLLECTION,
            'graph_index': graphs.COLLECTION}[fault]
        await replica_db[target].drop_index(storage.INDEX_NAME)
    elif fault == 'missing_key':
        monkeypatch.setattr(encryption, '_fernet', None); monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    elif fault == 'graph_capacity': monkeypatch.setattr(graphs, 'MAX_SNAPSHOTS', 1)
    elif fault == 'metadata_capacity': monkeypatch.setattr(metadata, 'MAX_SNAPSHOTS', 1)
    elif fault == 'combined_bytes': monkeypatch.setattr(snapshots, 'MAX_BATCH_BYTES', 1)
    monkeypatch.setenv(snapshots.SETTING, 'true')
    before = await state(replica_db)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, original, 'metadata')
    assert 'private-secret' not in str(caught.value.detail)
    assert await state(replica_db) == before


@pytest.mark.parametrize('operation', ['created', 'metadata', 'graph', 'deleted'])
async def test_original_historical_receipt_precedes_new_snapshot_prerequisites(replica_db, monkeypatch, operation):
    await seed_authority(replica_db)
    original = None
    if operation != 'created':
        await perform(replica_db, None, 'created')
        original = await replica_db.outreach_templates.find_one({})
    first = await perform(replica_db, original, operation)
    if operation != 'deleted':
        await remove(replica_db, await replica_db.outreach_templates.find_one({}))
    before = await state(replica_db)
    monkeypatch.setenv(snapshots.SETTING, 'invalid')
    monkeypatch.setattr(encryption, '_fernet', None); monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    assert await perform(replica_db, original, operation) == first
    status = {'created': save_status, 'metadata': metadata_status, 'graph': graph_status, 'deleted': deletion_status}[operation]
    if operation == 'created':
        assert (await status(replica_db)).json() == first
    else:
        raw = {'metadata': metadata_content, 'graph': graph_content, 'deleted': deletion_content}[operation](original)
        assert await status(replica_db, raw) == first
    after = await state(replica_db)
    for name in COLLECTIONS[2:]:
        assert after[name] == before[name]
    for name in COLLECTIONS[:2]:
        previous = BSON(before[name][0]).decode()
        current = BSON(after[name][0]).decode()
        assert current.pop('template_authority_revision') == previous.pop('template_authority_revision') + 2
        assert current == previous


async def test_lost_creation_ack_recovers_original_pair_without_reencrypting(replica_db, monkeypatch):
    from outreach.core import template_saves as saves
    await setup(replica_db, monkeypatch)
    commit = saves.mutate_suppression
    async def lost(*args, **kwargs):
        await commit(*args, **kwargs)
        raise SuppressionUnavailable('Synthetic lost acknowledgement')
    monkeypatch.setattr(saves, 'mutate_suppression', lost)
    assert (await post(replica_db)).status_code == 503
    before = await state(replica_db)
    monkeypatch.setattr(saves, 'mutate_suppression', commit)
    assert (await post(replica_db)).status_code == 200
    # Successful receipt reads advance authority, but never touch retained content.
    after = await state(replica_db)
    for name in COLLECTIONS[2:]:
        assert after[name] == before[name]


async def test_competing_edits_commit_one_complete_pair(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    results = await asyncio.gather(perform(replica_db, original, 'metadata'),
        perform(replica_db, original, 'graph'), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    for codec in (metadata, graphs):
        assert await replica_db[codec.COLLECTION].count_documents({}) == 2
    await verify_pair(replica_db, original)
    await verify_pair(replica_db, await replica_db.outreach_templates.find_one({}))


async def test_actual_erasure_purges_integrated_pairs_after_source_deletion(replica_db, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    await remove(replica_db, await replica_db.outreach_templates.find_one({}))
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    service = OutreachErasure(replica_db)
    await service.request('workspace', 'actor')
    review = await service.inspect('workspace')
    await service.finish('workspace', 'operator', 'Owned drained fixture', workers_drained=True,
        expected_digest=review['review_digest'])
    for codec in (metadata, graphs):
        assert await replica_db[codec.COLLECTION].count_documents({}) == 0
    assert (await post(replica_db)).status_code != 200


async def test_enabled_creation_denies_standalone_without_partial_pair(real_db, monkeypatch):
    await seed_authority(real_db)
    monkeypatch.setenv(snapshots.SETTING, 'true')
    assert (await post(real_db)).status_code == 503
    for name in COLLECTIONS[2:]:
        assert await real_db[name].count_documents({}) == 0


async def test_existing_pair_at_capacity_survives_deletion_byte_for_byte(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    before = await state(replica_db)
    monkeypatch.setattr(graphs, 'MAX_SNAPSHOTS', 1)
    monkeypatch.setattr(metadata, 'MAX_SNAPSHOTS', 1)
    with pytest.raises(HTTPException):
        await perform(replica_db, original, 'metadata')
    assert await state(replica_db) == before
    await perform(replica_db, original, 'deleted')
    after = await state(replica_db)
    for name in (metadata.COLLECTION, graphs.COLLECTION):
        assert after[name] == before[name]


@pytest.mark.parametrize('kind', ['metadata', 'graph'])
async def test_corrupt_retained_kind_holds_both_and_preserves_source(replica_db, monkeypatch, kind):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    codec = metadata if kind == 'metadata' else graphs
    await replica_db[codec.COLLECTION].update_one({}, {'$set': {'ciphertext': 'invalid'}})
    before = await state(replica_db)
    with pytest.raises(HTTPException):
        await perform(replica_db, original, 'metadata')
    assert await state(replica_db) == before


async def test_index_drift_after_both_inserts_rolls_back_creation(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    before = await state(replica_db)
    require_index = storage.require_history_index
    observations = 0
    async def drift(collection):
        nonlocal observations
        if collection.name == metadata.COLLECTION:
            observations += 1
            if observations == 2:
                # Inject the final observation, rather than blocking a real DDL
                # command behind our own transaction's collection write locks.
                raise HTTPException(503, 'Synthetic changed index observation')
        return await require_index(collection)
    monkeypatch.setattr(storage, 'require_history_index', drift)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, None, 'created')
    assert caught.value.status_code == 503
    assert observations == 2
    assert await state(replica_db) == before


async def test_final_js_safe_revision_can_capture_pre_delete_without_increment(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch, enabled=False)
    await perform(replica_db, None, 'created')
    # An owned legacy fixture with no recorded lineage: deletion may observe its
    # actual final revision, without inventing all the missing historical ones.
    await replica_db.outreach_template_revisions.delete_many({})
    await replica_db.outreach_templates.update_one({}, {'$set': {'template_revision': Int64(2**53 - 1)}})
    original = await replica_db.outreach_templates.find_one({})
    monkeypatch.setenv(snapshots.SETTING, 'true')
    await perform(replica_db, original, 'deleted')
    await verify_pair(replica_db, original)
    assert await replica_db.outreach_template_revisions.count_documents({}) == 2
    for codec in (metadata, graphs):
        assert (await replica_db[codec.COLLECTION].find_one({}))['revision'] == 2**53 - 1


async def test_competing_edit_and_deletion_never_leave_a_half_pair(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    results = await asyncio.gather(perform(replica_db, original, 'metadata'),
        perform(replica_db, original, 'deleted'), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code in {404, 409} for result in results) == 1
    current = await replica_db.outreach_templates.find_one({})
    expected = 2 if current else 1
    for codec in (metadata, graphs):
        assert await replica_db[codec.COLLECTION].count_documents({}) == expected
    assert await replica_db.outreach_template_revisions.count_documents({'event': 'deleted'}) == (current is None)


@pytest.mark.parametrize('operation', ['metadata', 'graph', 'deleted'])
async def test_lost_mutation_ack_recovers_without_new_capture(replica_db, monkeypatch, operation):
    from outreach.core import template_metadata_updates, template_graph_updates, template_deletions
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    module = {'metadata': template_metadata_updates, 'graph': template_graph_updates,
        'deleted': template_deletions}[operation]
    commit = module.mutate_suppression
    async def lost(*args, **kwargs):
        await commit(*args, **kwargs)
        raise SuppressionUnavailable('Synthetic lost acknowledgement')
    monkeypatch.setattr(module, 'mutate_suppression', lost)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, original, operation)
    assert caught.value.status_code == 503
    before = await state(replica_db)
    monkeypatch.setattr(module, 'mutate_suppression', commit)
    monkeypatch.setenv(snapshots.SETTING, 'invalid')
    await perform(replica_db, original, operation)
    after = await state(replica_db)
    for name in COLLECTIONS[2:]:
        assert after[name] == before[name]


@pytest.mark.parametrize('fault', ['invalid_setting', 'duplicate_uid', 'revoked_role'])
async def test_new_capture_rechecks_server_and_current_identity_admission(replica_db, monkeypatch, fault):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    if fault == 'invalid_setting': monkeypatch.setenv(snapshots.SETTING, 'invalid')
    elif fault == 'duplicate_uid': await replica_db.users.insert_one({'user_id': 'other', 'firebase_uid': 'original-uid'})
    else: await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
    before = await state(replica_db)
    with pytest.raises(HTTPException):
        await perform(replica_db, original, 'metadata')
    assert await state(replica_db) == before


@pytest.mark.parametrize('collection', ['outreach_template_revisions', metadata.COLLECTION, graphs.COLLECTION])
@pytest.mark.parametrize('fault', ['ttl', 'conflicting'])
async def test_actual_conflicting_or_ttl_index_holds_without_customer_ddl(replica_db, monkeypatch, collection, fault):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    if fault == 'ttl':
        await replica_db[collection].create_index('future_expiry', expireAfterSeconds=3600)
    else:
        await replica_db[collection].drop_index(storage.INDEX_NAME)
        await replica_db[collection].create_index('revision', name=storage.INDEX_NAME)
    indexes = await replica_db[collection].index_information()
    before = await state(replica_db)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, original, 'metadata')
    assert caught.value.status_code == 503
    assert await state(replica_db) == before
    assert await replica_db[collection].index_information() == indexes


@pytest.mark.parametrize('revision', [0, 2**53 - 2])
async def test_legacy_zero_and_edit_to_final_revision_capture_exact_pair(replica_db, monkeypatch, revision):
    await setup(replica_db, monkeypatch, enabled=False)
    await perform(replica_db, None, 'created')
    await replica_db.outreach_template_revisions.delete_many({})
    await replica_db.outreach_templates.update_one({}, {'$set': {'template_revision': Int64(revision)}})
    original = await replica_db.outreach_templates.find_one({})
    monkeypatch.setenv(snapshots.SETTING, 'true')
    result = await perform(replica_db, original, 'metadata')
    assert result['new_revision'] == revision + 1
    await verify_pair(replica_db, original)
    await verify_pair(replica_db, await replica_db.outreach_templates.find_one({}))


async def test_current_wrong_key_rolls_back_edit_without_reencryption(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    before = await state(replica_db)
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    with pytest.raises(HTTPException):
        await perform(replica_db, original, 'metadata')
    assert await state(replica_db) == before


@pytest.mark.parametrize('change', ['role', 'uid'])
async def test_revocation_between_guard_entry_and_authority_check_denies_capture(replica_db, monkeypatch, change):
    from outreach.core import template_governance as governance
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    authorize = governance.authorize_update
    revoked = None
    async def revoke(current, actor, uid):
        nonlocal revoked
        if change == 'role':
            await replica_db.workspace_members.update_one({}, {'$set': {'role': 'viewer'}})
        else:
            await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'replacement'}})
        revoked = await state(replica_db)
        await authorize(current, actor, uid)
    monkeypatch.setattr(governance, 'authorize_update', revoke)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, original, 'metadata')
    assert caught.value.status_code == 403 and revoked is not None
    assert await state(replica_db) == revoked


async def test_snapshot_mutation_commits_before_competing_guarded_erasure_stop(replica_db, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    entered, release = asyncio.Event(), asyncio.Event()
    load = graphs._retained
    async def pause(*args):
        result = await load(*args)
        entered.set()
        await release.wait()
        return result
    monkeypatch.setattr(graphs, '_retained', pause)
    editing = asyncio.create_task(perform(replica_db, original, 'metadata'))
    erasing = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        erasing = asyncio.create_task(OutreachErasure(replica_db).request('workspace', 'actor'))
        await asyncio.sleep(0.05)
        assert not erasing.done()
    finally:
        release.set()
        tasks = [editing] + ([erasing] if erasing is not None else [])
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert len(results) == 2 and isinstance(results[0], dict) and isinstance(results[1], dict)
    assert results[1]['status'] == 'awaiting_drain'
    await verify_pair(replica_db, original)
    current = await replica_db.outreach_templates.find_one({})
    await verify_pair(replica_db, current)
    before = await state(replica_db)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, current, 'graph')
    assert caught.value.status_code == 503 and await state(replica_db) == before


async def test_combined_retained_plus_new_bson_exact_boundary(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    before = await state(replica_db)
    check_indexes = snapshots._indexes
    observations, measured = 0, {}
    async def measure_then_abort(current):
        nonlocal observations
        await check_indexes(current)
        observations += 1
        if observations == 2:
            for codec in (metadata, graphs):
                rows = await current[codec.COLLECTION].find({'workspace_id': 'workspace'}).to_list(10)
                assert len(rows) == 2
                measured[codec.COLLECTION] = sum(len(BSON.encode(row)) for row in rows)
            raise HTTPException(409, 'Owned byte-boundary measurement rollback')
    monkeypatch.setattr(snapshots, '_indexes', measure_then_abort)
    with pytest.raises(HTTPException, match='Owned byte-boundary'):
        await perform(replica_db, original, 'metadata')
    assert observations == 2 and await state(replica_db) == before
    monkeypatch.setattr(snapshots, '_indexes', check_indexes)
    total = sum(measured.values())
    assert all(size < total - 1 for size in measured.values())
    monkeypatch.setattr(snapshots, 'MAX_BATCH_BYTES', total - 1)
    with pytest.raises(HTTPException):
        await perform(replica_db, original, 'metadata')
    assert await state(replica_db) == before
    monkeypatch.setattr(snapshots, 'MAX_BATCH_BYTES', total)
    await perform(replica_db, original, 'metadata')
    for codec in (metadata, graphs):
        rows = await replica_db[codec.COLLECTION].find({}).to_list(10)
        assert sum(len(BSON.encode(row)) for row in rows) == measured[codec.COLLECTION]


@pytest.mark.parametrize('fault', ['orphan_revision', 'valid_ciphertext_content_drift', 'storage_error', 'live_readback_drift'])
async def test_retained_context_and_final_source_fences_rollback(replica_db, monkeypatch, fault):
    await setup(replica_db, monkeypatch)
    await perform(replica_db, None, 'created')
    original = await replica_db.outreach_templates.find_one({})
    if fault == 'orphan_revision':
        await replica_db[metadata.COLLECTION].update_one({}, {'$set': {'revision': 777}})
    elif fault == 'valid_ciphertext_content_drift':
        saved = await replica_db[metadata.COLLECTION].find_one({})
        payload = json.loads(encryption.decrypt_strict(saved['ciphertext']))
        payload['metadata']['name'] = 'Different valid metadata'
        token = encryption.encrypt(snapshots.canonical_json(payload))
        await replica_db[metadata.COLLECTION].update_one({}, {'$set': {'ciphertext': token}})
    elif fault == 'storage_error':
        async def unavailable(*args):
            raise ValueError('private-secret')
        monkeypatch.setattr(graphs, '_retained', unavailable)
    else:
        lookup = snapshots.unique_resource
        async def changed(*args):
            row = await lookup(*args)
            return {**row, 'unexpected_readback': True}
        monkeypatch.setattr(snapshots, 'unique_resource', changed)
    before = await state(replica_db)
    with pytest.raises(HTTPException) as caught:
        await perform(replica_db, original, 'metadata')
    assert 'private-secret' not in str(caught.value.detail)
    assert await state(replica_db) == before
