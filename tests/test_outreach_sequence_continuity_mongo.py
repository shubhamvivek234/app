"""Actual launch must not turn retained progress into a new sequence consent."""
from datetime import datetime, timedelta, timezone
import os

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.api import campaigns
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_campaign_readiness_mongo import seed, preflight, USER
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


async def progressed(db, version=1):
    await seed(db)
    await db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    await db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': 'sender', 'current_node_id': 'root',
        'execution_state': 'waiting_delay', 'sequence_version': version,
        'last_action_taken': 'visit_profile', 'last_action_at': datetime.now(timezone.utc),
        'next_action_due_at': datetime.now(timezone.utc) + timedelta(hours=8)}})


@pytest.mark.parametrize('kind', ['type', 'delay', 'content', 'branch'])
async def test_same_step_id_in_new_version_cannot_rebind_progress(replica_db, kind):
    await progressed(replica_db)
    node = {'id': 'root', 'type': 'visit_profile', 'config': {}}
    nodes, edges = [node], []
    if kind == 'type': node['type'] = 'like_last_post'
    if kind == 'delay': node['delay_hours'] = 36
    if kind == 'content': node.update(type='send_message', config={'body': 'A different message'})
    if kind == 'branch':
        nodes.append({'id': 'next', 'type': 'visit_profile', 'config': {}})
        edges.append({'source': 'root', 'target': 'next'})
    await replica_db.outreach_sequences.update_one({}, {'$set': {'nodes': nodes, 'edges': edges}})
    before = await replica_db.outreach_leads.find_one({})
    report = await preflight(replica_db)
    assert not report['can_launch']
    assert not next(item for item in report['checklist'] if item['id'] == 'lead_versions')['passed']
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find_one({}) == before
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


@pytest.mark.parametrize('version', [None, 0, -1, True, 2.0, '2', [], [2], Code('2')])
async def test_progress_without_exact_integer_version_holds(replica_db, version):
    await progressed(replica_db, version)
    before = await replica_db.outreach_leads.find_one({})
    assert not (await preflight(replica_db))['can_launch']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_leads.find_one({}) == before


async def test_progress_with_missing_version_requires_review(replica_db):
    await progressed(replica_db)
    await replica_db.outreach_leads.update_one({}, {'$unset': {'sequence_version': ''}})
    assert not (await preflight(replica_db))['can_launch']


@pytest.mark.parametrize('version', [2, Int64(2)])
async def test_same_version_resume_retains_original_sender_step_wait_and_due(replica_db, version):
    await progressed(replica_db, version)
    wait = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=1)
    await replica_db.outreach_leads.update_one({}, {'$set': {'waiting_for_reply_at': wait}})
    before = await replica_db.outreach_leads.find_one({})
    assert (await preflight(replica_db))['can_launch']
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    after = await replica_db.outreach_leads.find_one({})
    for key in ('assigned_account_id', 'current_node_id', 'execution_state', 'next_action_due_at',
                'waiting_for_reply_at', 'last_action_at', 'last_action_taken', 'sequence_version'):
        assert after[key] == before[key]


@pytest.mark.parametrize('state', ['staged', 'replied', 'finished', 'bounced', 'failed'])
async def test_terminal_and_staged_history_is_not_rebound_by_new_launch(replica_db, state):
    await seed(replica_db)
    historical = {'id': 'historical', 'workspace_id': 'workspace', 'campaign_id': 'campaign',
        'execution_state': state, 'assigned_account_id': 'old-sender', 'current_node_id': 'old-node',
        'sequence_version': 1, 'authorized_revision': 0, 'last_action_taken': 'send_message'}
    await replica_db.outreach_leads.insert_one(historical)
    before = await replica_db.outreach_leads.find_one({'id': 'historical'})
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    assert await replica_db.outreach_leads.find_one({'id': 'historical'}) == before


@pytest.mark.parametrize('fault', ['old_version', 'missing_step', 'removed_step'])
async def test_late_progress_change_is_not_overwritten_during_binding(replica_db, monkeypatch, fault):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    collection_type = type(replica_db.outreach_leads)
    original = collection_type.update_many
    changed = []
    async def intervene(collection, query, update, **options):
        if (collection.database.name == replica_db.name and collection.name == 'outreach_leads'
                and 'sequence_version' in update.get('$set', {}) and not changed):
            changed.append(True)
            await collection.update_one({'id': 'lead'}, {'$set': {'sequence_version': 1 if fault == 'old_version' else 2,
                'assigned_account_id': 'sender', 'execution_state': 'waiting_delay',
                'current_node_id': 'root' if fault == 'old_version' else None if fault == 'missing_step' else 'removed',
                'last_action_taken': 'visit_profile'}})
        return await original(collection, query, update, **options)
    monkeypatch.setattr(collection_type, 'update_many', intervene)
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 409 and changed == [True]
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['sequence_version'] == (1 if fault == 'old_version' else 2)
    assert lead.get('authorized_revision') is None
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'draft'


async def test_unacted_queued_root_can_receive_its_first_current_version(replica_db):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['sequence_version'] == 2 and lead['current_node_id'] == 'root'


@pytest.mark.parametrize('metadata', [
    {'sequence_version': 1}, {'sequence_version': True}, {'sequence_version': [None]},
    {'sequence_version': '1'}, {'authorized_revision': 1}, {'authorized_revision': [None]},
    {'sequence_version': None, 'authorized_revision': 3}])
async def test_queued_root_with_previous_or_ambiguous_binding_is_not_initial(replica_db, metadata):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    await replica_db.outreach_leads.update_one({}, {'$set': {'current_node_id': 'root', **metadata}})
    before = await replica_db.outreach_leads.find_one({})
    assert not (await preflight(replica_db))['can_launch']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_leads.find_one({}) == before


@pytest.mark.parametrize('field', ['last_action_at', 'last_action_taken',
                                  'waiting_for_connection_at', 'waiting_for_reply_at'])
async def test_null_matching_array_cannot_certify_an_unacted_root(replica_db, field):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': 2}})
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': 'sender', 'current_node_id': 'root', field: [None]}})
    assert not (await preflight(replica_db))['can_launch']


@pytest.mark.parametrize('version', [True, 2.0, '2', [2], None])
async def test_malformed_sequence_version_cannot_authorize_even_a_new_root(replica_db, version):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {'version': version}})
    before = await replica_db.outreach_leads.find_one({})
    assert not (await preflight(replica_db))['can_launch']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_leads.find_one({}) == before


async def test_foreign_workspace_or_campaign_progress_cannot_block_current_launch(replica_db):
    await seed(replica_db)
    await replica_db.outreach_leads.insert_many([
        {'id': 'foreign-workspace', 'workspace_id': 'foreign', 'campaign_id': 'campaign',
         'execution_state': 'waiting_delay', 'sequence_version': 0},
        {'id': 'foreign-campaign', 'workspace_id': 'workspace', 'campaign_id': 'other',
         'execution_state': 'waiting_delay', 'sequence_version': 0}])
    before = await replica_db.outreach_leads.find({'id': {'$ne': 'lead'}}).to_list(10)
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    assert await replica_db.outreach_leads.find({'id': {'$ne': 'lead'}}).to_list(10) == before


@pytest.mark.parametrize('state', ['waiting_delay', 'waiting_trigger', 'paused', 'in_progress', ['waiting_delay']])
async def test_current_version_with_missing_waiting_step_cannot_restart_at_root(replica_db, state):
    await progressed(replica_db, 2)
    await replica_db.outreach_leads.update_one({}, {'$set': {'current_node_id': None,
        'last_action_at': None, 'last_action_taken': None, 'execution_state': state}})
    before = await replica_db.outreach_leads.find_one({})
    assert not (await preflight(replica_db))['can_launch']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_leads.find_one({}) == before
