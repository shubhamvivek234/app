"""Deletion phase failures/retries and restore generations over owned Mongo."""
import os
import uuid

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from outreach.core import campaign_deletion as lifecycle
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


async def seed(db, count=1):
    await db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': 'workspace',
        'name': 'Campaign', 'status': 'active', 'authorization_revision': 7, 'leads_count': count})
    for i in range(count):
        await db.outreach_leads.insert_one({'id': str(i), 'workspace_id': 'workspace',
            'campaign_id': 'campaign', 'pipeline_stage': 'replied', 'has_replied': True,
            'enrollment_id': 'original-' + str(i)})
    await db.outreach_tasks.insert_many([
        {'id': 'queued', 'workspace_id': 'workspace', 'campaign_id': 'campaign', 'status': 'queued'},
        {'id': 'uncertain', 'workspace_id': 'workspace', 'campaign_id': 'campaign', 'status': 'uncertain', 'physical_token': 'held'},
        {'id': 'foreign', 'workspace_id': 'foreign', 'campaign_id': 'campaign', 'status': 'queued'}])
    await db.outreach_sequences.insert_one({'id': 'sequence', 'workspace_id': 'workspace', 'campaign_id': 'campaign'})
    return str(uuid.uuid4())


@pytest.mark.parametrize('collection', ['outreach_tasks', 'outreach_leads', 'outreach_sequences', 'outreach_campaign_deletions'])
async def test_failed_phase_stays_stopped_and_same_request_finishes(replica_db, monkeypatch, collection):
    request = await seed(replica_db)
    # Stop is already durable; the selected cleanup transaction fails.
    await lifecycle._start(replica_db, 'workspace', 'campaign', request)
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == collection:
            raise OperationFailure('injected phase fault')
        return await original(self, query, update, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(SuppressionCollection, 'update_one', fail)
        with pytest.raises(SuppressionUnavailable):
            await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    parent = await replica_db.outreach_campaigns.find_one({})
    assert parent['is_deleted'] is True and parent['status'] == 'paused'
    assert parent['authorization_revision'] == 8
    assert (await lifecycle.delete(replica_db, 'workspace', 'campaign', request))['status'] == 'deleted'
    assert (await lifecycle.delete(replica_db, 'workspace', 'campaign', request))['status'] == 'deleted'
    assert (await replica_db.outreach_campaigns.find_one({}))['authorization_revision'] == 8


async def test_restore_keeps_tasks_stopped_preserves_replies_and_foreign_workspace(replica_db):
    request = await seed(replica_db)
    await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    result = await lifecycle.restore(replica_db, 'workspace', 'campaign', request)
    assert result['status'] == 'restored'
    parent = await replica_db.outreach_campaigns.find_one({})
    assert parent['status'] == 'paused' and parent['auto_launch_enabled'] is False
    assert 'restore_review' in parent['pause_reasons'] and parent['leads_count'] == 1
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['campaign_id'] == 'campaign' and lead['pipeline_stage'] == 'replied'
    assert lead['has_replied'] is True and lead['enrollment_id'] == 'original-0'
    assert (await replica_db.outreach_tasks.find_one({'id': 'queued'}))['status'] == 'cancelled'
    assert (await replica_db.outreach_tasks.find_one({'id': 'uncertain'}))['physical_token'] == 'held'
    assert (await replica_db.outreach_tasks.find_one({'id': 'foreign'}))['status'] == 'queued'


async def test_old_delete_and_restore_requests_cannot_touch_new_generation(replica_db):
    first = await seed(replica_db)
    await lifecycle.delete(replica_db, 'workspace', 'campaign', first)
    await lifecycle.restore(replica_db, 'workspace', 'campaign', first)
    assert (await lifecycle.delete(replica_db, 'workspace', 'campaign', first))['status'] == 'restored'
    assert (await replica_db.outreach_campaigns.find_one({}))['is_deleted'] is False
    second = str(uuid.uuid4())
    await lifecycle.delete(replica_db, 'workspace', 'campaign', second)
    with pytest.raises(HTTPException) as failure:
        await lifecycle.restore(replica_db, 'workspace', 'campaign', first)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_campaigns.find_one({}))['deletion_request_id'] == second


async def test_replacement_parent_cannot_receive_old_cleanup(replica_db):
    request = await seed(replica_db)
    await lifecycle._start(replica_db, 'workspace', 'campaign', request)
    old = await replica_db.outreach_campaigns.find_one({})
    await replica_db.outreach_campaigns.delete_one({'_id': old['_id']})
    old.pop('_id')
    await replica_db.outreach_campaigns.insert_one(old)
    with pytest.raises(HTTPException) as failure:
        await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_tasks.find_one({'id': 'queued'}))['status'] == 'queued'


async def test_parent_replacement_between_snapshot_read_and_cleanup_aborts_batch(replica_db, monkeypatch):
    request = await seed(replica_db)
    await lifecycle._start(replica_db, 'workspace', 'campaign', request)
    original = SuppressionCollection.find_one
    replaced = False
    async def replace_after_read(self, query, *args, **kwargs):
        nonlocal replaced
        row = await original(self, query, *args, **kwargs)
        if self.collection.name == 'outreach_campaigns' and row and not replaced:
            replaced = True
            await replica_db.outreach_campaigns.delete_one({'_id': row['_id']})
            copy = dict(row); copy.pop('_id')
            await replica_db.outreach_campaigns.insert_one(copy)
        return row
    monkeypatch.setattr(SuppressionCollection, 'find_one', replace_after_read)
    with pytest.raises(HTTPException) as failure:
        await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_tasks.find_one({'id': 'queued'}))['status'] == 'queued'


async def test_pending_delete_and_restore_are_hidden_and_resumable(replica_db, monkeypatch):
    request = await seed(replica_db, count=401)
    monkeypatch.setattr(lifecycle, 'MAX_STEPS', 1)
    assert (await lifecycle.delete(replica_db, 'workspace', 'campaign', request))['status'] == 'deletion_pending'
    with pytest.raises(HTTPException) as failure:
        await lifecycle.restore(replica_db, 'workspace', 'campaign', request)
    assert failure.value.status_code == 409
    for _ in range(12):
        result = await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
        if result['status'] == 'deleted': break
    assert result['status'] == 'deleted'
    result = await lifecycle.restore(replica_db, 'workspace', 'campaign', request)
    assert result['status'] == 'restore_pending'
    assert (await replica_db.outreach_campaigns.find_one({}))['is_deleted'] is True
    for _ in range(12):
        result = await lifecycle.restore(replica_db, 'workspace', 'campaign', request)
        if result['status'] == 'restored': break
    assert result['status'] == 'restored'
    assert (await replica_db.outreach_campaigns.find_one({}))['leads_count'] == 401


async def test_restore_preserves_reassigned_and_changed_lead(replica_db):
    request = await seed(replica_db, count=2)
    await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    await replica_db.outreach_leads.update_one({'id': '0'}, {'$set': {'campaign_id': 'replacement', 'pipeline_stage': 'call_booked'}})
    await replica_db.outreach_leads.update_one({'id': '1'}, {'$set': {'pipeline_stage': 'call_booked'}})
    await lifecycle.restore(replica_db, 'workspace', 'campaign', request)
    assert (await replica_db.outreach_leads.find_one({'id': '0'}))['campaign_id'] == 'replacement'
    assert (await replica_db.outreach_leads.find_one({'id': '1'}))['campaign_id'] is None
    assert (await replica_db.outreach_campaigns.find_one({}))['leads_count'] == 0


async def test_stop_manifest_failure_rolls_back_parent(replica_db, monkeypatch):
    request = await seed(replica_db)
    original = SuppressionCollection.insert_one
    async def fail(self, document, **kwargs):
        if self.collection.name == 'outreach_campaign_deletions': raise OperationFailure('injected')
        return await original(self, document, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail)
    with pytest.raises(SuppressionUnavailable):
        await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    parent = await replica_db.outreach_campaigns.find_one({})
    assert parent['status'] == 'active' and parent.get('is_deleted') is not True


async def test_legacy_same_delete_retry_finishes_without_key(replica_db):
    await seed(replica_db)
    first = await lifecycle.delete(replica_db, 'workspace', 'campaign')
    assert await lifecycle.delete(replica_db, 'workspace', 'campaign') == first


@pytest.mark.parametrize('lost_after', [1, 4, 7])
async def test_lost_commit_response_resumes_without_repeating_parent_authorization_change(replica_db, monkeypatch, lost_after):
    request = await seed(replica_db)
    original = lifecycle.mutate_suppression
    calls = 0
    async def lose_response(db, workspace, callback):
        nonlocal calls
        result = await original(db, workspace, callback)
        calls += 1
        if calls == lost_after: raise SuppressionUnavailable('simulated lost acknowledgement after commit')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle, 'mutate_suppression', lose_response)
        with pytest.raises(SuppressionUnavailable): await lifecycle.delete(replica_db, 'workspace', 'campaign', request)
    assert (await lifecycle.delete(replica_db, 'workspace', 'campaign', request))['status'] == 'deleted'
    assert (await replica_db.outreach_campaigns.find_one({}))['authorization_revision'] == 8


async def test_standalone_denies_before_stopping_parent(real_db):
    request = await seed(real_db)
    with pytest.raises(SuppressionUnavailable):
        await lifecycle.delete(real_db, 'workspace', 'campaign', request)
    assert (await real_db.outreach_campaigns.find_one({'id': 'campaign', 'workspace_id': 'workspace'}))['status'] == 'active'
    assert await real_db.outreach_campaign_deletions.count_documents({}) == 0
