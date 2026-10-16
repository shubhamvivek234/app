"""Current email policy, suppression ordering and original branch receipts."""
import os
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pymongo.results import UpdateResult

from outreach.core.dispatch_authority import AuthorityCollection
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.email_finder import suppress_email
from outreach.tasks.sequence_dispatch import prepare_due, execute_job
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server  # noqa: F401
from tests.test_outreach_field_conditions_mongo import seed as seed_field
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]
WS = 'workspace'


async def seed(db, monkeypatch, **fields):
    await seed_field(db, monkeypatch)
    await db.outreach_sequence_jobs.delete_many({})
    sequence = await db.outreach_sequence_versions.find_one({})
    sequence['nodes'][0].update(type='if_email_available', config={})
    from outreach.core.dag_compiler import DAGCompiler
    compiled = DAGCompiler.validate_and_compile(sequence['nodes'], sequence['edges'])
    await db.outreach_sequence_versions.update_one({}, {'$set': {
        'nodes': sequence['nodes'], 'compiled_dag': compiled}})
    await db.outreach_leads.update_one({}, {'$set': {'email': 'person@example.test', **fields}})
    assert (await prepare_due(db))['prepared'] == 1
    return await db.outreach_sequence_jobs.find_one({})


@pytest.mark.parametrize('fields,met', [({}, True), ({'email': ''}, False),
    ({'email': 'bad'}, False), ({'email_verification_status': 'unknown'}, False),
    ({'email_verification_status': 'invalid'}, False), ({'email_opted_out': True}, False)])
async def test_atomic_policy_and_delay_without_transport(replica_db, monkeypatch, fields, met):
    from outreach.tasks import sequence_executor
    opener = AsyncMock(side_effect=AssertionError('condition must not open credentials'))
    monkeypatch.setattr(sequence_executor, 'account_session', opener)
    monkeypatch.setattr(sequence_executor, 'prepare_proxy', opener)
    job = await seed(replica_db, monkeypatch, **fields)
    before = datetime.now(timezone.utc)
    result = await execute_job(replica_db, WS, job['_id'])
    assert result == {'status': 'branch_advanced', 'condition_met': met}, result
    lead = await replica_db.outreach_leads.find_one({})
    saved = await replica_db.outreach_sequence_jobs.find_one({})
    receipt = saved['condition_decision']
    assert lead['current_node_id'] == ('yes' if met else 'no')
    assert saved['status'] == 'completed' and receipt['kind'] == 'if_email_available'
    assert receipt['policy_version'] == 1 and receipt['next_action_due_at'] == lead['next_action_due_at']
    if met:
        assert lead['next_action_due_at'] >= before + timedelta(hours=12)
    assert 'person@example.test' not in str(receipt)
    for name in ('outreach_intents', 'outreach_physical_requests', 'outreach_request_budgets'):
        assert await replica_db[name].count_documents({}) == 0
    opener.assert_not_awaited()


@pytest.mark.parametrize('fields', [ {'email_verification_status': []},
    {'email_verification_status': 'typo'}, {'email_opted_out': 'false'}, {'email': []}])
async def test_malformed_policy_holds_durably(replica_db, monkeypatch, fields):
    job = await seed(replica_db, monkeypatch, **fields)
    assert (await execute_job(replica_db, WS, job['_id']))['status'] == 'condition_review_required'
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['current_node_id'] == 'check' and lead['execution_state'] == 'waiting_trigger'
    assert lead['next_action_due_at'] is None
    assert (await execute_job(replica_db, WS, job['_id']))['recovered'] is True
    assert (await prepare_due(replica_db))['prepared'] == 0


async def test_suppression_committed_before_decision_takes_no(replica_db, monkeypatch):
    job = await seed(replica_db, monkeypatch)
    await suppress_email(replica_db, workspace_id=WS, email='PERSON@example.test', reason='test')
    assert (await execute_job(replica_db, WS, job['_id'])) == {'status': 'branch_advanced', 'condition_met': False}
    receipt = (await replica_db.outreach_sequence_jobs.find_one({}))['condition_decision']
    assert receipt['reason'] == 'email_suppressed'


async def test_redelivery_after_suppression_keeps_original_delay_without_reactivation(replica_db, monkeypatch):
    job = await seed(replica_db, monkeypatch)
    assert (await execute_job(replica_db, WS, job['_id']))['condition_met'] is True
    before = await replica_db.outreach_leads.find_one({})
    await suppress_email(replica_db, workspace_id=WS, email='person@example.test', reason='test')
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await ExecutionPermission(replica_db).revoke(WS, 'sender', 'tester', 'stop')
    assert (await execute_job(replica_db, WS, job['_id'])) == {
        'status': 'branch_advanced', 'condition_met': True, 'recovered': True}
    after = await replica_db.outreach_leads.find_one({})
    assert after['next_action_due_at'] == before['next_action_due_at']
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'


@pytest.mark.parametrize('field,value', [('email', ''), ('email_verification_status', 'unknown'), ('email_opted_out', True)])
async def test_lead_policy_conflict_retries_current_values(replica_db, monkeypatch, field, value):
    job = await seed(replica_db, monkeypatch)
    original = AuthorityCollection.fence
    changed = False
    async def interleave(self, document, query):
        nonlocal changed
        if self.name == 'outreach_leads' and not changed:
            changed = True
            await replica_db.outreach_leads.update_one({}, {'$set': {field: value}})
        return await original(self, document, query)
    monkeypatch.setattr(AuthorityCollection, 'fence', interleave)
    assert (await execute_job(replica_db, WS, job['_id'])) == {'status': 'branch_advanced', 'condition_met': False}
    assert changed


@pytest.mark.parametrize('fault', ['cas', 'expiry'])
async def test_last_write_failure_rolls_back_branch_and_receipt(replica_db, monkeypatch, fault):
    job = await seed(replica_db, monkeypatch)
    original = AuthorityCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.name == 'outreach_sequence_jobs' and 'condition_decision' in update.get('$set', {}):
            if fault == 'cas':
                return UpdateResult({'n': 0, 'nModified': 0}, True)
            result = await original(self, query, update, **kwargs)
            self.database.deadlines.append(datetime.now(timezone.utc) - timedelta(seconds=1))
            return result
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(AuthorityCollection, 'update_one', fail)
    assert (await execute_job(replica_db, WS, job['_id']))['status'] == 'condition_authority_unavailable'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id'] == 'check'
    assert 'condition_decision' not in await replica_db.outreach_sequence_jobs.find_one({})


@pytest.mark.parametrize('fault', ['lead', 'campaign', 'sender', 'sequence', 'unstamped', 'bool_marker', 'legacy', 'copied'])
async def test_unbound_jobs_and_replacement_parents_deny(replica_db, monkeypatch, fault):
    job = await seed(replica_db, monkeypatch)
    if fault == 'unstamped':
        await replica_db.outreach_sequence_jobs.update_one({}, {'$unset': {'stamp.email_condition_contract_version': '', 'stamp.condition_native_ids': ''}})
    elif fault == 'bool_marker':
        await replica_db.outreach_sequence_jobs.update_one({}, {'$set': {'stamp.email_condition_contract_version': True}})
    elif fault == 'legacy':
        await replica_db.outreach_sequence_jobs.update_one({}, {'$set': {'stamp.enrollment_id': 'legacy:lead'}})
    elif fault == 'copied':
        await replica_db.outreach_sequence_jobs.delete_many({})
        job['_id'] = 'copy'; await replica_db.outreach_sequence_jobs.insert_one(job)
    else:
        name = {'lead': 'outreach_leads', 'campaign': 'outreach_campaigns',
            'sender': 'outreach_accounts', 'sequence': 'outreach_sequence_versions'}[fault]
        row = await replica_db[name].find_one({}); old = row.pop('_id')
        await replica_db[name].delete_one({'_id': old})
        if fault == 'sequence':
            row['_id'] = 'replacement'
            await replica_db.outreach_campaigns.update_one({}, {'$set': {'sequence_version_id': 'replacement'}})
        await replica_db[name].insert_one(row)
    assert (await execute_job(replica_db, WS, job['_id']))['status'] == 'stale_job'
    assert (await replica_db.outreach_leads.find_one({}))['current_node_id'] == 'check'


@pytest.mark.parametrize('fault', ['reply', 'dnc', 'paid', 'permission', 'epoch', 'campaign', 'disabled'])
async def test_current_stops_do_not_choose_branch(replica_db, monkeypatch, fault):
    job = await seed(replica_db, monkeypatch)
    if fault in ('reply', 'dnc'):
        await replica_db.outreach_leads.update_one({}, {'$set': {'has_replied' if fault == 'reply' else 'do_not_contact': True}})
    elif fault == 'paid':
        await replica_db.outreach_entitlements.update_one({}, {'$set': {'status': 'expired'}})
    elif fault == 'permission':
        await ExecutionPermission(replica_db).revoke(WS, 'sender', 'tester', 'stop')
    elif fault == 'epoch':
        monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'true')
    elif fault == 'campaign':
        await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    else:
        monkeypatch.setenv('OUTREACH_HUNTER_ENABLED', 'false')
    result = await execute_job(replica_db, WS, job['_id'])
    assert result['status'] != 'branch_advanced'
    assert 'condition_decision' not in await replica_db.outreach_sequence_jobs.find_one({})


@pytest.mark.parametrize('fault', ['kind', 'policy_version', 'two_markers'])
async def test_corrupt_receipt_cannot_be_recovered(replica_db, monkeypatch, fault):
    job = await seed(replica_db, monkeypatch)
    assert (await execute_job(replica_db, WS, job['_id']))['status'] == 'branch_advanced'
    change = {'kind': {'condition_decision.kind': 'has_data_in_column'},
        'policy_version': {'condition_decision.policy_version': True},
        'two_markers': {'stamp.field_condition_contract_version': 1}}[fault]
    await replica_db.outreach_sequence_jobs.update_one({}, {'$set': change})
    assert (await execute_job(replica_db, WS, job['_id'])) == {'status': 'already_claimed'}


async def test_guard_orders_new_suppression_after_in_progress_decision(replica_db, monkeypatch):
    from outreach.core import email_conditions
    job = await seed(replica_db, monkeypatch)
    read, release = asyncio.Event(), asyncio.Event()
    original = email_conditions.evaluate
    async def paused(*args):
        result = await original(*args)
        read.set()
        await release.wait()
        return result
    monkeypatch.setattr(email_conditions, 'evaluate', paused)
    worker = asyncio.create_task(execute_job(replica_db, WS, job['_id']))
    suppression = None
    try:
        await asyncio.wait_for(read.wait(), 5)
        suppression = asyncio.create_task(suppress_email(replica_db, workspace_id=WS,
            email='person@example.test', reason='test'))
        await asyncio.sleep(0.05)
        assert not suppression.done()
        release.set()
        assert (await asyncio.wait_for(worker, 5))['condition_met'] is True
        assert await asyncio.wait_for(suppression, 5) is True
        saved = await replica_db.outreach_sequence_jobs.find_one({})
        assert saved['condition_decision']['reason'] == 'policy_available'
        assert await original(replica_db, WS, await replica_db.outreach_leads.find_one({})) == {
            'condition_met': False, 'reason': 'email_suppressed'}
    finally:
        release.set()
        for task in (worker, suppression):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (worker, suppression) if task is not None), return_exceptions=True)


@pytest.mark.parametrize('channel', ['linkedin', 'restored', 'dnc'])
async def test_current_cross_record_stops_block_email_decision(replica_db, monkeypatch, channel):
    job = await seed(replica_db, monkeypatch)
    if channel == 'linkedin':
        await replica_db.outreach_inbox_threads.insert_one({'workspace_id': WS, 'account_id': 'sender',
            'lead_profile_url': 'https://www.linkedin.com/in/synthetic', 'has_lead_reply': True})
    elif channel == 'restored':
        await replica_db.outreach_reply_stops.insert_one({'workspace_id': WS, 'sender_id': 'sender',
            'field': 'normalized_url', 'value': 'https://www.linkedin.com/in/synthetic'})
    else:
        await replica_db.outreach_do_not_contact.insert_one({'workspace_id': WS, 'email': 'person@example.test'})
    assert (await execute_job(replica_db, WS, job['_id']))['status'] == 'lead_suppressed'
    assert 'condition_decision' not in await replica_db.outreach_sequence_jobs.find_one({})


async def test_one_sided_missing_successor_finishes_atomically(replica_db, monkeypatch):
    job = await seed(replica_db, monkeypatch)
    await replica_db.outreach_sequence_jobs.delete_many({})
    from outreach.core.dag_compiler import DAGCompiler
    sequence = await replica_db.outreach_sequence_versions.find_one({})
    nodes = sequence['nodes'][:1] + sequence['nodes'][2:]
    edges = [sequence['edges'][1]]
    compiled = DAGCompiler.validate_and_compile(nodes, edges)
    await replica_db.outreach_sequence_versions.update_one({}, {'$set': {'nodes': nodes, 'edges': edges, 'compiled_dag': compiled}})
    assert (await prepare_due(replica_db))['prepared'] == 1
    job = await replica_db.outreach_sequence_jobs.find_one({})
    assert (await execute_job(replica_db, WS, job['_id']))['condition_met'] is True
    lead = await replica_db.outreach_leads.find_one({})
    receipt = (await replica_db.outreach_sequence_jobs.find_one({}))['condition_decision']
    assert lead['execution_state'] == 'finished' and lead['next_action_due_at'] is None
    assert receipt['next_node_id'] is None


async def test_standalone_database_cannot_commit_policy_decision(replica_db, mongo_server, monkeypatch):
    import uuid
    from motor.motor_asyncio import AsyncIOMotorClient
    job = await seed(replica_db, monkeypatch)
    client = AsyncIOMotorClient(mongo_server, tz_aware=True, serverSelectionTimeoutMS=2000)
    db = client['test_lead_scope_' + uuid.uuid4().hex]
    try:
        for name in await replica_db.list_collection_names():
            rows = await replica_db[name].find({}).to_list(length=100)
            if rows:
                await db[name].insert_many(rows)
        result = await execute_job(db, WS, job['_id'])
        assert result['status'] == 'condition_authority_unavailable', result
        assert (await db.outreach_leads.find_one({}))['current_node_id'] == 'check'
        assert 'condition_decision' not in await db.outreach_sequence_jobs.find_one({})
    finally:
        await client.drop_database(db.name)
        client.close()


async def test_committed_decision_with_lost_ack_recovers_without_advancing_again(replica_db, monkeypatch):
    from outreach.core import sequence_conditions
    from outreach.core.suppression import SuppressionUnavailable
    job = await seed(replica_db, monkeypatch)
    original = sequence_conditions.mutate_suppression
    async def lost_ack(*args, **kwargs):
        await original(*args, **kwargs)
        raise SuppressionUnavailable('synthetic acknowledgement loss after commit')
    monkeypatch.setattr(sequence_conditions, 'mutate_suppression', lost_ack)
    first = await execute_job(replica_db, WS, job['_id'])
    assert first['status'] == 'condition_authority_unavailable'
    lead = await replica_db.outreach_leads.find_one({})
    saved = await replica_db.outreach_sequence_jobs.find_one({})
    assert saved['status'] == 'completed' and lead['current_node_id'] == 'yes'
    assert (await execute_job(replica_db, WS, job['_id'])) == {
        'status': 'branch_advanced', 'condition_met': True, 'recovered': True}
    assert (await replica_db.outreach_leads.find_one({}))['next_action_due_at'] == lead['next_action_due_at']
