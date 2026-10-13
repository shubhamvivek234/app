"""Email evidence reporting over owned native Mongo; no provider transport."""
from datetime import datetime, timedelta, timezone
import csv
import io
import os

import pytest

from outreach.api import analytics
from outreach.core import email_reporting
from tests.outreach_native import replica_server, replica_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}


async def seed(db):
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    await db.outreach_campaigns.insert_many([
        {'id': name, 'workspace_id': 'workspace'} for name in ('campaign', 'other')])
    await db.outreach_accounts.insert_many([
        {'id': name, 'workspace_id': 'workspace', 'status': 'active'} for name in ('sender', 'other-sender')])
    op = {'_id': 'email:workspace:logical', 'workspace_id': 'workspace',
          'campaign_id': 'campaign', 'sender_account_id': 'sender', 'lead_id': 'lead',
          'source': 'email_send', 'logical_operation_id': 'logical', 'provider': 'gmail',
          'provider_message_id': 'synthetic-provider-message',
          'credential_generation': 'mailbox-generation', 'status': 'accepted',
          'accepted_at': now, 'created_at': now - timedelta(seconds=1), 'updated_at': now}
    await db.outreach_email_operations.insert_one(op)
    return op


async def report(db, **kwargs):
    return await analytics.get_outreach_analytics(campaign_id='campaign', timeframe='7d',
        current_user=USER, db=db, **kwargs)


def bounce(op, key='event', **overrides):
    return {'_id': key, 'workspace_id': op['workspace_id'],
            'sender_account_id': op['sender_account_id'], 'operation_id': op['_id'],
            'kind': 'bounce', 'attribution': 'message_reference',
            'received_at': op['accepted_at'] + timedelta(seconds=1),
            'created_at': datetime.now(timezone.utc), **overrides}


async def test_provider_acceptance_is_counted_without_inventing_delivery(replica_db):
    await seed(replica_db)
    email = (await report(replica_db))['kpis']['email']
    assert email['sent'] == email['provider_accepted'] == 1
    assert email['delivered'] is None and email['deliverability_rate'] is None
    assert email['delivery_unknown'] == 1 and email['bounced'] == 0
    assert email['submitted'] is None


async def test_completed_task_without_operation_is_unverified_not_delivered(replica_db):
    await seed(replica_db)
    await replica_db.outreach_email_operations.delete_many({})
    await replica_db.outreach_tasks.insert_one({'id': 'legacy', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'account_id': 'sender', 'task_type': 'send_email',
        'status': 'completed', 'updated_at': datetime.now(timezone.utc)})
    email = (await report(replica_db))['kpis']['email']
    assert email['sent'] == 0 and email['delivered'] is None
    assert email['unverified_task_records'] == 1


async def test_bounce_joins_original_operation_and_filters_campaign_and_sender(replica_db):
    op = await seed(replica_db)
    foreign = {**op, '_id': 'email:workspace:foreign', 'logical_operation_id': 'foreign',
        'campaign_id': 'other', 'sender_account_id': 'other-sender'}
    await replica_db.outreach_email_operations.insert_one(foreign)
    await replica_db.outreach_email_inbound_events.insert_one(bounce(foreign))
    email = (await report(replica_db, sender_account_id='sender'))['kpis']['email']
    assert email['sent'] == 1 and email['bounced'] == 0 and email['delivery_unknown'] == 1


async def test_duplicate_bounces_count_once_at_original_received_time(replica_db):
    op = await seed(replica_db)
    event = bounce(op, received_at=op['accepted_at'] + timedelta(seconds=2))
    await replica_db.outreach_email_inbound_events.insert_many([event, bounce(op, 'earlier'),
        bounce(op, 'duplicate', received_at=event['received_at'])])
    result = await report(replica_db)
    email = result['kpis']['email']
    assert email['provider_accepted'] == 1 and email['bounced'] == 1
    assert email['delivery_unknown'] == 0 and email['delivered'] is None
    assert sum(day['email_bounced'] for day in result['daily_chart']) == 1


async def test_human_assertion_never_becomes_provider_acceptance(replica_db):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {
        'acceptance_source': 'human_assertion', 'resolution': {'source': 'human_assertion'}}})
    email = (await report(replica_db))['kpis']['email']
    assert email['provider_accepted'] == 0 and email['human_reported'] == 1


async def test_reporting_repairs_do_not_move_old_acceptance_into_period(replica_db):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {
        'accepted_at': datetime.now(timezone.utc) - timedelta(days=20),
        'created_at': datetime.now(timezone.utc) - timedelta(days=21),
        'updated_at': datetime.now(timezone.utc), 'completed_at': datetime.now(timezone.utc)}})
    await replica_db.outreach_tasks.insert_one({'id': 'logical', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'account_id': 'sender', 'task_type': 'send_email',
        'status': 'completed', 'updated_at': datetime.now(timezone.utc)})
    email = (await report(replica_db))['kpis']['email']
    assert email['provider_accepted'] == 0 and email['unverified_task_records'] == 0


async def test_csv_email_evidence_matches_read_only_report(replica_db):
    await seed(replica_db)
    async def snapshot():
        return {name: await replica_db[name].find({}).to_list(length=100)
                for name in await replica_db.list_collection_names()}
    before = await snapshot()
    response = await analytics.export_outreach_analytics(campaign_id='campaign', timeframe='7d',
        current_user=USER, db=replica_db)
    content = ''.join([chunk.decode() if isinstance(chunk, bytes) else chunk async for chunk in response.body_iterator])
    rows = list(csv.DictReader(io.StringIO(content)))
    assert sum(int(row['email_provider_accepted']) for row in rows) == 1
    assert all(row['email_delivery_status'] == 'unavailable' for row in rows)
    assert all(row['email_delivered'] == '' for row in rows)
    assert await snapshot() == before


@pytest.mark.parametrize('changes', [
    {'accepted_at': None}, {'accepted_at': '2026-10-13T00:00:00Z'},
    {'accepted_at': datetime.now(timezone.utc) + timedelta(days=1)},
    {'created_at': None}, {'created_at': datetime.now(timezone.utc) + timedelta(days=1)},
    {'logical_operation_id': 'replacement'}, {'source': 'unproven'},
    {'provider': ['gmail']}, {'credential_generation': None},
    {'acceptance_source': 'unproven'}, {'resolution': {'source': 'unproven'}},
    {'provider_message_id': None}, {'provider_message_id': ' '}, {'status': 'unproven'},
])
async def test_unproven_operations_stay_partial_without_invented_acceptance(replica_db, changes):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': changes})
    email = (await report(replica_db))['kpis']['email']
    assert email['provider_accepted'] == 0 and email['unverified_operations'] == 1
    assert email['evidence_status'] == 'partial' and email['delivered'] is None


@pytest.mark.parametrize('changes', [
    {'acceptance_source': 'human_assertion'}, {'resolution': {'source': 'human_assertion'}},
])
async def test_each_human_provenance_field_independently_excludes_provider_count(replica_db, changes):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': changes})
    email = (await report(replica_db))['kpis']['email']
    assert email['human_reported'] == 1 and email['sent'] == 0


async def test_graph_acceptance_does_not_require_nonexistent_message_id(replica_db):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {'provider': 'microsoft', 'provider_message_id': None}})
    email = (await report(replica_db))['kpis']['email']
    assert email['provider_accepted'] == 1 and email['delivered'] is None


async def test_old_human_assertion_does_not_move_to_current_period(replica_db):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {
        'accepted_at': datetime.now(timezone.utc) - timedelta(days=20), 'acceptance_source': 'human_assertion'}})
    email = (await report(replica_db))['kpis']['email']
    assert email['human_reported'] == email['provider_accepted'] == 0


@pytest.mark.parametrize('changes', [
    {'workspace_id': 'foreign'}, {'workspace_id': ['workspace', 'foreign']},
    {'campaign_id': 'other'}, {'campaign_id': ['campaign', 'other']},
    {'sender_account_id': 'other-sender'}, {'sender_account_id': ['sender', 'other-sender']},
])
async def test_strict_selected_scope_excludes_foreign_and_array_operations(replica_db, changes):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': changes})
    email = (await report(replica_db, sender_account_id='sender'))['kpis']['email']
    assert email['provider_accepted'] == 0 and email['unverified_operations'] == 0


@pytest.mark.parametrize('changes', [
    {'workspace_id': 'foreign'}, {'workspace_id': ['workspace', 'foreign']},
    {'sender_account_id': 'other-sender'}, {'sender_account_id': ['sender']},
    {'operation_id': 'email:workspace:unrelated'}, {'operation_id': ['email:workspace:logical']},
    {'kind': 'reply'},
])
async def test_bounce_must_bind_exact_scalar_original_operation_and_sender(replica_db, changes):
    op = await seed(replica_db)
    await replica_db.outreach_email_inbound_events.insert_one(bounce(op, **changes))
    email = (await report(replica_db))['kpis']['email']
    assert email['bounced'] == email['possible_bounced'] == 0 and email['delivery_unknown'] == 1


@pytest.mark.parametrize('attribution', ['provider_thread', 'sender_address_and_time', None, 'unproven'])
async def test_thread_or_address_correlation_is_only_possible(replica_db, attribution):
    op = await seed(replica_db)
    second = {**op, '_id': 'email:workspace:followup', 'logical_operation_id': 'followup'}
    await replica_db.outreach_email_operations.insert_one(second)
    await replica_db.outreach_email_inbound_events.insert_one(bounce(second, attribution=attribution))
    email = (await report(replica_db))['kpis']['email']
    assert email['provider_accepted'] == 2 and email['bounced'] == 0
    assert email['possible_bounced'] == 1 and email['delivery_unknown'] == 2


async def test_reference_bucket_dominates_possible_without_double_counting(replica_db):
    op = await seed(replica_db)
    await replica_db.outreach_email_inbound_events.insert_many([
        bounce(op), bounce(op, 'possible', attribution='provider_thread')])
    email = (await report(replica_db))['kpis']['email']
    assert email['bounced'] == 1 and email['possible_bounced'] == 0


@pytest.mark.parametrize('when', ['before', 'future', 'malformed', 'missing'])
async def test_unproven_bounce_time_is_not_replaced_with_projection_time(replica_db, when):
    op = await seed(replica_db)
    value = {'before': op['accepted_at'] - timedelta(seconds=1),
        'future': datetime.now(timezone.utc) + timedelta(days=1), 'malformed': 'unproven', 'missing': None}[when]
    await replica_db.outreach_email_inbound_events.insert_one(bounce(op, received_at=value))
    email = (await report(replica_db))['kpis']['email']
    assert email['bounced'] == 0 and email['unverified_bounce_events'] == 1
    assert email['evidence_status'] == 'partial'


@pytest.mark.parametrize('state,expected', [('dispatching', 1), ('uncertain', 1),
    ('failed', 0), ('not_submitted', 0), ('not_sent_stopped', 0)])
async def test_operation_state_does_not_fabricate_submission_or_delivery(replica_db, state, expected):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {'status': state}})
    email = (await report(replica_db))['kpis']['email']
    assert email['pending_or_unknown_operations'] == expected and email['sent'] == 0
    assert email['submitted'] is None and email['delivered'] is None


async def test_current_task_projection_does_not_duplicate_original_acceptance(replica_db):
    await seed(replica_db)
    await replica_db.outreach_tasks.insert_one({'id': 'logical', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'account_id': 'sender', 'task_type': 'send_email',
        'status': 'accepted', 'updated_at': datetime.now(timezone.utc)})
    email = (await report(replica_db))['kpis']['email']
    assert email['sent'] == 1 and email['unverified_task_records'] == 0


async def test_array_kind_is_unverified_not_a_scalar_bounce(replica_db):
    op = await seed(replica_db)
    await replica_db.outreach_email_inbound_events.insert_one(bounce(op, kind=['bounce', 'reply']))
    email = (await report(replica_db))['kpis']['email']
    assert email['bounced'] == 0 and email['delivery_unknown'] == 1
    assert email['unverified_bounce_events'] == 1 and email['evidence_status'] == 'partial'


@pytest.mark.parametrize('state', ['failed', 'not_submitted', 'uncertain', 'not_sent_stopped'])
async def test_completed_projection_cannot_be_explained_by_a_nonaccepted_operation(replica_db, state):
    await seed(replica_db)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {'status': state}})
    await replica_db.outreach_tasks.insert_one({'id': 'logical', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'account_id': 'sender', 'task_type': 'send_email',
        'status': 'completed', 'updated_at': datetime.now(timezone.utc)})
    email = (await report(replica_db))['kpis']['email']
    assert email['sent'] == 0 and email['unverified_task_records'] == 1
    assert email['evidence_status'] == 'partial'


@pytest.mark.parametrize('source', ['operations', 'events', 'tasks'])
async def test_capacity_overflow_invalidates_counts_instead_of_truncating(replica_db, monkeypatch, source):
    op = await seed(replica_db)
    if source == 'operations':
        monkeypatch.setattr(email_reporting, 'MAX_OPERATIONS', 1)
        await replica_db.outreach_email_operations.insert_one({**op, '_id': 'email:workspace:second', 'logical_operation_id': 'second'})
    elif source == 'events':
        monkeypatch.setattr(email_reporting, 'MAX_EVENTS', 1)
        await replica_db.outreach_email_inbound_events.insert_many([bounce(op), bounce(op, 'second')])
    else:
        monkeypatch.setattr(email_reporting, 'MAX_TASKS', 1)
        await replica_db.outreach_tasks.insert_many([{'workspace_id': 'workspace', 'campaign_id': 'campaign',
            'task_type': 'send_email', 'status': 'completed', 'updated_at': datetime.now(timezone.utc)} for _ in range(2)])
    email = (await report(replica_db))['kpis']['email']
    assert email['evidence_status'] == 'unavailable'
    assert all(email[key] is None for key in email_reporting.COUNTS)


async def test_source_failure_or_deadline_returns_sanitized_unavailable(replica_db, monkeypatch):
    await seed(replica_db)
    async def broken(*args, **kwargs):
        raise RuntimeError('synthetic-sensitive-source')
    monkeypatch.setattr(email_reporting, '_build', broken)
    result = await report(replica_db)
    assert result['kpis']['email']['evidence_status'] == 'unavailable'
    assert 'synthetic-sensitive-source' not in str(result)
    assert all(day['email_provider_accepted'] is None for day in result['daily_chart'])
    monkeypatch.setattr(email_reporting, 'READ_SECONDS', 0)
    assert (await report(replica_db))['kpis']['email']['provider_accepted'] is None


async def test_bson_naive_utc_and_inclusive_fixed_window_boundaries(replica_db, replica_server):
    from motor.motor_asyncio import AsyncIOMotorClient
    op = await seed(replica_db)
    start = datetime(2026, 10, 10, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    await replica_db.outreach_email_operations.update_one({}, {'$set': {'created_at': start, 'accepted_at': start}})
    await replica_db.outreach_email_inbound_events.insert_one(bounce(op, received_at=end))
    client = AsyncIOMotorClient(replica_server, tz_aware=False)
    try:
        result = await email_reporting.email_report(client[replica_db.name], workspace='workspace',
            campaign='campaign', sender='sender', start=start, as_of=end)
    finally:
        client.close()
    assert result['kpis']['provider_accepted'] == result['kpis']['bounced'] == 1
    assert result['daily']['2026-10-10']['email_provider_accepted'] == 1
    assert result['daily']['2026-10-12']['email_bounced'] == 1
