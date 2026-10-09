"""Real snapshot inventory of intact operation metadata without domain mutation."""
from copy import deepcopy
import json
import os

import pytest

from outreach.core import restore_inventory as inventory, restore_uncertainty as uncertainty
from tests.test_outreach_restore_epoch import restored_db, prepare
from tests.test_outreach_restore_epoch_mongo import real_restore
from tests.test_outreach_restore_uncertainty import CASES

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned local Mongo is opt-in')]


async def inspect(db):
    return await inventory.RestoreInventory(db).inspect('w', workers_drained=True)


@pytest.mark.parametrize('collection,prefix,states', CASES)
async def test_native_each_operation_family_preserves_evidence_and_projects_only_metadata(
        real_restore, collection, prefix, states):
    db = real_restore
    await prepare(db)
    target = getattr(db, collection)
    rows = [{'_id': str(index), 'workspace_id': 'w', 'status': status,
        'owner': 'private-owner', 'receipt': {'token': 'private-secret'}, 'history': ['retained'],
        'authorization_code_enc': 'private-secret', 'input_enc': 'private-secret',
        'result_enc': 'private-secret', 'response_enc': 'private-secret', 'payload': {'recipient': 'private'},
        'connection_owner': 'original', 'physical_request_token': 'original', 'attempt': 4}
        for index, status in enumerate(states)]
    rows.append({'_id': 'foreign', 'workspace_id': 'other', 'status': 'possible', 'secret': 'foreign'})
    await target.insert_many(rows)
    await db.outreach_voice_studio_budgets.insert_one({'_id': 'budget', 'workspace_id': 'w', 'used': 3})
    before = await target.find({}).sort('_id', 1).to_list(length=100)
    physical = await db.outreach_physical_requests.find_one({})
    budget = await db.outreach_voice_studio_budgets.find_one({})
    result = await inspect(db)
    assert result['counts'][collection] == len(states)
    for category in set(states.values()):
        assert result['findings'][prefix + '_' + category] == list(states.values()).count(category)
    assert await target.find({}).sort('_id', 1).to_list(length=100) == before
    assert await db.outreach_physical_requests.find_one({}) == physical
    assert await db.outreach_voice_studio_budgets.find_one({}) == budget
    assert not result['activation_allowed'] and not result['completeness_verified']
    assert not result['provider_ownership_verified']
    assert 'private' not in json.dumps(result) and 'foreign' not in json.dumps(result)
    # Credentials, bodies, owners, raw receipts and history are outside the digest.
    await target.update_one({'_id': '0'}, {'$set': {'receipt.token': 'replacement', 'owner': 'replacement',
        'input_enc': 'replacement', 'response_enc': 'replacement'}})
    assert (await inspect(db))['digest'] == result['digest']
    await target.update_one({'_id': '0'}, {'$set': {'status': 'unrecognized-result'}})
    changed = await inspect(db)
    assert changed['digest'] != result['digest']
    assert changed['findings'][prefix + '_state_unproven'] == 1


@pytest.mark.parametrize('collection', list(uncertainty.FIELDS))
async def test_native_added_collection_capacity_denies_without_partial_report(real_restore, collection):
    db = real_restore
    await prepare(db)
    target = getattr(db, collection)
    await target.delete_many({})
    await target.insert_many([{'_id': str(i), 'workspace_id': 'w', 'status': 'possible',
        'receipt': {'token': 'retained'}} for i in range(101)])
    before = await target.find({}).sort('_id', 1).to_list(length=101)
    sender = await db.outreach_sender_execution.find_one({})
    with pytest.raises(ValueError, match='bounded review capacity'):
        await inspect(db)
    assert await target.find({}).sort('_id', 1).to_list(length=101) == before
    assert await db.outreach_sender_execution.find_one({}) == sender


async def test_native_disconnected_refresh_and_stopped_oauth_substates_remain_unresolved(real_restore):
    db = real_restore
    await prepare(db)
    await db.outreach_mailbox_connection_jobs.insert_one({'_id': 'oauth', 'workspace_id': 'w',
        'status': 'review_stopped', 'exchange_state': 'unknown', 'authorization_code_enc': 'retained'})
    await db.outreach_mailbox_oauth_states.insert_many([
        {'_id': 'browser', 'workspace_id': 'w', 'code_verifier_enc': 'retained'},
        {'_id': 'foreign-browser', 'workspace_id': 'other', 'code_verifier_enc': 'private'}])
    await db.outreach_mailboxes.insert_many([
        {'_id': 'normal', 'workspace_id': 'w', 'status': 'active', 'refresh_token_enc': 'retained'},
        {'_id': 'null', 'workspace_id': 'w', 'status': 'disconnected', 'refresh_state': None}])
    before = await db.outreach_mailboxes.find({}).sort('_id', 1).to_list(length=100)
    result = await inspect(db)
    assert result['findings']['oauth_exchange_unresolved'] == 1
    assert result['findings']['oauth_job_stopped_review'] == 1
    # The restored fixture's original unknown refresh survives prepare unchanged.
    assert result['findings']['mailbox_refresh_unresolved'] == 1
    assert result['findings']['mailbox_refresh_unmarked_review'] == 1
    assert result['findings']['mailbox_refresh_state_unproven'] == 1
    assert result['findings']['oauth_browser_state_review'] == 1
    assert result['counts']['outreach_mailbox_oauth_states'] == 1
    assert await db.outreach_mailboxes.find({}).sort('_id', 1).to_list(length=100) == before


async def test_native_voice_substates_are_digest_bound_and_keep_original_unknown(real_restore):
    db = real_restore
    await prepare(db)
    await db.outreach_voice_studio_jobs.insert_one({'_id': 'studio', 'workspace_id': 'w',
        'status': 'review_stopped', 'review': {'outcome_at_review': 'unknown', 'evidence': 'private'}})
    await db.outreach_voice_preparation_jobs.insert_one({'_id': 'preparation', 'workspace_id': 'w',
        'status': 'superseded', 'generation_result': 'received_discarded'})
    first = await inspect(db)
    assert first['findings']['voice_studio_original_outcome_unresolved'] == 1
    assert first['findings']['voice_generation_recorded_result_review'] == 1
    await db.outreach_voice_studio_jobs.update_one({'_id': 'studio'}, {'$set': {'review.evidence': 'replacement'}})
    assert (await inspect(db))['digest'] == first['digest']
    await db.outreach_voice_studio_jobs.update_one({'_id': 'studio'}, {'$set': {'review.outcome_at_review': 'received'}})
    assert (await inspect(db))['digest'] != first['digest']


async def test_native_new_families_share_one_snapshot_despite_later_inserts(real_restore, monkeypatch):
    db = real_restore
    await prepare(db)
    baseline = await inspect(db)
    original = inventory.raw_database
    triggered = False

    class Cursor:
        def __init__(self, cursor): self.cursor = cursor
        def sort(self, *args): self.cursor = self.cursor.sort(*args); return self
        def limit(self, *args): self.cursor = self.cursor.limit(*args); return self
        async def to_list(self, **kwargs):
            nonlocal triggered
            rows = await self.cursor.to_list(**kwargs)
            if not triggered:
                triggered = True
                for name in uncertainty.FIELDS:
                    await getattr(db, name).insert_one({'_id': 'concurrent', 'workspace_id': 'w', 'status': 'possible'})
            return rows

    class Collection:
        def find(self, *args, **kwargs): return Cursor(db.outreach_entitlements.find(*args, **kwargs))

    class Database:
        def __getattr__(self, name):
            return Collection() if name == 'outreach_entitlements' else getattr(db, name)

    def wrapped(current):
        raw, options = original(current)
        assert options.get('session') is not None
        return Database(), options

    monkeypatch.setattr(inventory, 'raw_database', wrapped)
    result = await inspect(db)
    assert triggered and result['digest'] == baseline['digest']
    monkeypatch.setattr(inventory, 'raw_database', original)
    fresh = await inspect(db)
    for name in uncertainty.FIELDS:
        assert fresh['counts'][name] == baseline['counts'][name] + 1


async def test_native_combined_metadata_bound_denies_without_mutation(real_restore):
    db = real_restore
    await prepare(db)
    await db.outreach_voice_vendor_reads.insert_one({'_id': 'vendor', 'workspace_id': 'w', 'status': 'x' * 33000})
    await db.outreach_webhook_deliveries.insert_one({'_id': 'delivery', 'workspace_id': 'w', 'status': 'x' * 33000})
    before = deepcopy(await db.outreach_voice_vendor_reads.find_one({}))
    with pytest.raises(ValueError, match='metadata exceeds'):
        await inspect(db)
    assert await db.outreach_voice_vendor_reads.find_one({}) == before
