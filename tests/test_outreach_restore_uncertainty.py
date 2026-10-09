"""Restored operation metadata never clears uncertainty or authorizes another call."""
from copy import deepcopy
import json

import pytest
import pytest_asyncio

from outreach.core.restore_inventory import RestoreInventory
from tests.test_outreach_restore_epoch import restored_db, prepare

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]

# These are persisted worker states, not response-only API labels.
CASES = [
    ('outreach_mailbox_connection_jobs', 'oauth_job', {
        'pending': 'pending_review', 'queued': 'pending_review', 'running': 'unresolved',
        'review_required': 'unresolved', 'connected': 'recorded_result_review',
        'failed': 'stopped_review', 'review_stopped': 'stopped_review'}),
    ('outreach_mailbox_sync_jobs', 'mailbox_sync_job', {
        'queued': 'pending_review', 'running': 'unresolved', 'completed': 'recorded_result_review',
        'failed': 'stopped_review', 'stopped': 'stopped_review'}),
    ('outreach_mailbox_sync_reads', 'mailbox_sync_read', {
        'possible': 'unresolved', 'read_interrupted': 'unresolved', 'received': 'recorded_result_review'}),
    ('outreach_voice_preparation_jobs', 'voice_preparation', {
        'queued': 'pending_review', 'claimed': 'preparing_review', 'generating': 'unresolved',
        'held_outcome': 'unresolved', 'prepared': 'recorded_result_review',
        'blocked': 'stopped_review', 'superseded': 'stopped_review', 'cancelled': 'stopped_review'}),
    ('outreach_voice_studio_jobs', 'voice_studio', {
        'queued': 'pending_review', 'preparing': 'preparing_review', 'possible': 'unresolved',
        'held_outcome': 'unresolved', 'received': 'recorded_result_review',
        'held_received': 'recorded_result_review', 'completed': 'recorded_result_review',
        'review_completed': 'recorded_result_review', 'cancelled': 'stopped_review',
        'stopped': 'stopped_review', 'review_stopped': 'stopped_review'}),
    ('outreach_voice_vendor_reads', 'voice_vendor_read', {
        'preparing': 'preparing_review', 'possible': 'unresolved', 'read_interrupted': 'unresolved',
        'received': 'recorded_result_review', 'released': 'recorded_result_review', 'stopped': 'stopped_review'}),
    ('outreach_webhook_deliveries', 'integration_delivery', {
        'pending': 'pending_review', 'retry': 'pending_review', 'preparing': 'preparing_review',
        'possible': 'unresolved', 'review_required': 'unresolved', 'received': 'recorded_result_review',
        'held_received': 'recorded_result_review', 'delivered': 'recorded_result_review',
        'review_completed': 'recorded_result_review', 'failed': 'stopped_review', 'cancelled': 'stopped_review'}),
]


@pytest_asyncio.fixture
async def inventory_db(restored_db):
    await prepare(restored_db)
    return restored_db


async def inspect(db):
    return await RestoreInventory(db).inspect('w', workers_drained=True)


@pytest.mark.parametrize('collection,prefix,states', CASES)
async def test_each_worker_state_is_conservative_metadata_review(inventory_db, collection, prefix, states):
    rows = [{'_id': str(index), 'workspace_id': 'w', 'status': state,
             'owner': 'private-owner', 'receipt': {'token': 'secret'}, 'history': ['retained']}
            for index, state in enumerate(states)]
    getattr(inventory_db, collection).docs = rows
    before = deepcopy(rows)
    result = await inspect(inventory_db)
    for category in set(states.values()):
        assert result['findings'][prefix + '_' + category] == list(states.values()).count(category)
    assert getattr(inventory_db, collection).docs == before
    assert not result['activation_allowed'] and not result['completeness_verified']
    assert not result['provider_ownership_verified']
    assert 'secret' not in json.dumps(result) and 'private-owner' not in json.dumps(result)


@pytest.mark.parametrize('collection,prefix,states', CASES)
@pytest.mark.parametrize('state', [None, {}, [], True, 7, 'other-family-result'])
async def test_unrecognized_or_malformed_states_do_not_disappear(inventory_db, collection, prefix, states, state):
    getattr(inventory_db, collection).docs = [{'_id': 'private-id', 'workspace_id': 'w', 'status': state}]
    result = await inspect(inventory_db)
    assert result['findings'][prefix + '_state_unproven'] == 1


@pytest.mark.parametrize('state,category', [
    ('pending', 'pending_review'), ('preparing', 'preparing_review'), ('possible', 'unresolved'),
    ('unknown', 'unresolved'), ('installed', 'recorded_result_review'), ('rejected', 'recorded_result_review'),
    ('not_submitted', 'stopped_review'), (None, 'state_unproven'), ({}, 'state_unproven')])
async def test_oauth_exchange_is_reviewed_even_on_stopped_jobs(inventory_db, state, category):
    inventory_db.outreach_mailbox_connection_jobs.docs = [{'_id': 'oauth', 'workspace_id': 'w',
        'status': 'review_stopped', 'exchange_state': state, 'authorization_code_enc': 'secret'}]
    result = await inspect(inventory_db)
    assert result['findings']['oauth_exchange_' + category] == 1
    assert result['findings']['oauth_job_stopped_review'] == 1


@pytest.mark.parametrize('state,category', [
    ('preparing', 'preparing_review'), ('possible', 'unresolved'), ('unknown', 'unresolved'),
    ('rejected', 'recorded_result_review'), (None, 'state_unproven'), ([], 'state_unproven')])
async def test_disconnected_mailbox_keeps_refresh_uncertainty(inventory_db, state, category):
    inventory_db.outreach_mailboxes.docs = [{'_id': 'mailbox', 'workspace_id': 'w',
        'status': 'disconnected', 'refresh_state': state, 'refresh_token_enc': 'secret'}]
    result = await inspect(inventory_db)
    assert result['findings']['mailbox_refresh_' + category] == 1
    assert result['findings']['mailbox_stopped_review'] == 1


async def test_unmarked_refresh_and_browser_state_are_reviewed_without_secret_reads(inventory_db):
    inventory_db.outreach_mailboxes.docs = [{'_id': 'mailbox', 'workspace_id': 'w', 'status': 'active'}]
    inventory_db.outreach_mailbox_oauth_states.docs = [{'_id': 'browser', 'workspace_id': 'w',
        'code_verifier_enc': 'secret', 'expires_at': 'expired'}]
    result = await inspect(inventory_db)
    assert result['findings']['mailbox_refresh_unmarked_review'] == 1
    assert result['findings']['oauth_browser_state_review'] == 1


@pytest.mark.parametrize('outcome,category', [('unknown', 'unresolved'), ('received', 'recorded_result_review'),
    ('not_called', 'stopped_review'), (None, 'state_unproven'), ({}, 'state_unproven')])
async def test_studio_local_review_does_not_erase_original_unknown(inventory_db, outcome, category):
    inventory_db.outreach_voice_studio_jobs.docs = [{'_id': 'voice', 'workspace_id': 'w',
        'status': 'review_stopped', 'review': {'outcome_at_review': outcome, 'evidence': 'secret'}}]
    result = await inspect(inventory_db)
    assert result['findings']['voice_studio_original_outcome_' + category] == 1
    assert result['findings']['voice_studio_stopped_review'] == 1


async def test_discarded_voice_receipt_remains_a_separate_review(inventory_db):
    inventory_db.outreach_voice_preparation_jobs.docs = [{'_id': 'voice', 'workspace_id': 'w',
        'status': 'superseded', 'generation_result': 'received_discarded'}]
    result = await inspect(inventory_db)
    assert result['findings']['voice_generation_recorded_result_review'] == 1
    assert result['findings']['voice_preparation_stopped_review'] == 1
