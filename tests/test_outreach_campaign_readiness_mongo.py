"""Read-only readiness and frozen-state launch parity on owned MongoDB."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from outreach.api import campaigns
from outreach.core import session_custody
from outreach.models import WorkingSchedule
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_sender_resume_mongo import local_custody, seed as seed_sender  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}


async def seed(db):
    await seed_sender(db)
    await db.outreach_accounts.update_one({}, {'$set': {'status': 'active', 'stop_reason': None}})
    await db.outreach_campaigns.update_one({}, {'$set': {
        'status': 'draft', 'authorization_revision': 0, 'sender_account_ids': ['sender'],
        'schedule': WorkingSchedule().model_dump()}})
    await db.outreach_sequences.insert_one({'workspace_id': 'workspace', 'campaign_id': 'campaign',
        'nodes': [{'id': 'root', 'type': 'visit_profile', 'config': {}}], 'edges': []})
    await db.outreach_leads.insert_one({'id': 'lead', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'linkedin_url': 'https://linkedin.com/in/synthetic', 'execution_state': 'queued'})


async def preflight(db):
    return await campaigns.get_campaign_preflight('campaign', current_user=USER, db=db)


@pytest.mark.parametrize('fault', ['disabled', 'cookie', 'proxy_term', 'lease', 'intent',
    'manual', 'physical', 'provider', 'revision', 'active', 'pending_edit', 'restore', 'latched'])
async def test_preflight_and_launch_share_current_blockers(replica_db, monkeypatch, fault):
    await seed(replica_db)
    if fault == 'disabled': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    elif fault == 'cookie': await replica_db.outreach_accounts.update_one({}, {'$unset': {'session_cookie_enc': ''}})
    elif fault == 'proxy_term': await replica_db.outreach_proxy_inventory.update_one({}, {'$set': {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
    elif fault == 'lease': await replica_db.outreach_proxy_leases.delete_many({})
    elif fault == 'revision': await replica_db.outreach_campaigns.update_one({}, {'$set': {'authorization_revision': 'unproven'}})
    elif fault == 'active': await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'active'}})
    elif fault == 'pending_edit': await replica_db.outreach_campaigns.update_one({}, {'$set': {'sequence_edit_pending': True}})
    elif fault == 'restore': monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'true')
    elif fault == 'latched':
        from outreach.core.execution_permission import ExecutionPermission
        await replica_db.outreach_sender_execution.insert_one({**ExecutionPermission.scope('workspace', 'sender'),
            'status': 'idle', 'permission': {'latched': True}})
    else:
        collection, row = {
            'intent': ('outreach_intents', {'sender_id': 'sender', 'status': 'unknown_outcome'}),
            'manual': ('outreach_manual_actions', {'account_id': 'sender', 'status': 'projection_pending'}),
            'physical': ('outreach_physical_requests', {'sender_id': 'sender', 'status': 'unknown_outcome'}),
            'provider': ('outreach_email_operations', {'sender_id': 'sender', 'status': 'uncertain'}),
        }[fault]
        await getattr(replica_db, collection).insert_one({'workspace_id': 'workspace', 'campaign_id': 'campaign', **row})
    opening = AsyncMock(side_effect=AssertionError('Readiness must not open keys'))
    monkeypatch.setattr(session_custody, 'account_session', opening)
    report = await preflight(replica_db)
    assert report['can_launch'] is False
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.detail == report['blockers'][0]
    opening.assert_not_awaited()
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == ('active' if fault == 'active' else 'draft')


async def test_healthy_stored_launch_state_does_not_claim_execution_or_health_proof(replica_db, monkeypatch):
    await seed(replica_db)
    opening = AsyncMock(side_effect=AssertionError('Readiness must not open keys'))
    monkeypatch.setattr(session_custody, 'account_session', opening)
    report = await preflight(replica_db)
    assert report['can_launch'] is True
    assert report['execution_ready'] is False
    assert report['execution_checks']
    assert 'verified proxies' not in str(report)
    opening.assert_not_awaited()


async def test_preflight_is_read_only_including_unknown_execution_state(replica_db):
    await seed(replica_db)
    async def snapshot():
        return {name: await replica_db[name].find({}).to_list(length=100)
                for name in await replica_db.list_collection_names()}
    before = await snapshot()
    await preflight(replica_db)
    assert await snapshot() == before


async def test_missing_saved_sequence_blocks_launch_without_inventing_default(replica_db):
    await seed(replica_db)
    await replica_db.outreach_sequences.delete_many({})
    report = await preflight(replica_db)
    assert not report['can_launch']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'draft'


async def test_valid_activation_allocates_without_granting_execution(replica_db):
    await seed(replica_db)
    result = await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert result['status'] == 'launched'
    campaign = await replica_db.outreach_campaigns.find_one({})
    lead = await replica_db.outreach_leads.find_one({})
    assert campaign['status'] == 'active' and campaign['authorization_revision'] == 1
    assert lead['assigned_account_id'] == 'sender' and lead['authorized_revision'] == 1
    assert await replica_db.outreach_sender_execution.count_documents({}) == 0
    assert await replica_db.outreach_execution_permissions.count_documents({}) == 0
    assert await replica_db.outreach_physical_requests.count_documents({}) == 0


@pytest.mark.parametrize('collection,change', [
    ('outreach_campaigns', {'launch_claim_token': 'retained-owner'}),
    ('outreach_campaigns', {'launch_claim_expires_at': 'unproven'}),
    ('outreach_campaigns', {'pause_reasons': ['unproven_stop']}),
    ('outreach_campaigns', {'authorization_revision': True}),
    ('outreach_accounts', {'cooldown_until': datetime.now(timezone.utc) + timedelta(hours=1)}),
    ('outreach_accounts', {'cooldown_until': 'unproven'}),
    ('outreach_accounts', {'stop_reason': 'rate_limited_429'}),
    ('outreach_accounts', {'connection_finalization': {'state': 'installing'}}),
    ('outreach_accounts', {'session_cookie_enc': 'plaintext'}),
    ('outreach_accounts', {'session_cookie_enc': 'gAAAAA-corrupt'}),
    ('outreach_accounts', {'jsession_id': ''}),
    ('outreach_accounts', {'proxy': {'host': '8.8.4.4'}}),
    ('outreach_proxy_inventory', {'username': 'replacement'}),
    ('outreach_proxy_leases', {'country_code': 'GB'}),
    ('outreach_proxy_leases', {'provider': 'replacement'}),
    ('outreach_sender_slots', {'workspace_id': ['workspace', 'foreign']}),
])
async def test_malformed_or_retained_current_state_blocks_both_paths(replica_db, collection, change):
    await seed(replica_db)
    await getattr(replica_db, collection).update_one({}, {'$set': change})
    report = await preflight(replica_db)
    assert report['can_launch'] is False
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.detail == report['blockers'][0]
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


@pytest.mark.parametrize('change', ['proxy', 'hold', 'campaign', 'paid', 'credentials', 'policy'])
async def test_changes_during_key_preparation_deny_activation(replica_db, monkeypatch, change):
    await seed(replica_db)
    original = session_custody.account_session
    async def changed(account):
        material = await original(account)
        if change == 'proxy': await replica_db.outreach_proxy_inventory.update_one({}, {'$set': {'username': 'replacement'}})
        elif change == 'hold': await replica_db.outreach_intents.insert_one({'workspace_id': 'workspace', 'sender_id': 'sender', 'status': 'unknown_outcome'})
        elif change == 'campaign': await replica_db.outreach_campaigns.update_one({}, {'$set': {'authorization_revision': 8}})
        elif change == 'paid': await replica_db.outreach_entitlements.update_one({}, {'$set': {'status': 'expired'}})
        elif change == 'policy': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
        else: await replica_db.outreach_accounts.update_one({}, {'$set': {'credential_generation': 'replacement'}})
        return material
    monkeypatch.setattr(session_custody, 'account_session', changed)
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'draft'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


async def test_prospective_parameters_match_launch_without_mutation(replica_db):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'sender_account_ids': []}})
    assert not (await preflight(replica_db))['can_launch']
    request = campaigns.LaunchCampaignRequest(sender_account_ids=['sender'], daily_limits={'connection_invites': 4})
    report = await campaigns.preview_campaign_preflight('campaign', request, current_user=USER, db=replica_db)
    assert report['can_launch'] is True
    assert (await replica_db.outreach_campaigns.find_one({}))['sender_account_ids'] == []
    result = await campaigns._launch_campaign_impl('campaign', request, USER, replica_db)
    assert result['status'] == 'launched'
    assert (await replica_db.outreach_campaigns.find_one({}))['limits']['connection_invites'] == 4


@pytest.mark.parametrize('shape', ['foreign', 'array', 'duplicate'])
async def test_sender_scope_and_identity_cannot_be_inferred(replica_db, shape):
    await seed(replica_db)
    sender = await replica_db.outreach_accounts.find_one({}); sender.pop('_id')
    if shape == 'duplicate':
        await replica_db.outreach_accounts.insert_one(sender)
    else:
        await replica_db.outreach_accounts.update_one({}, {'$set': {'workspace_id': 'foreign' if shape == 'foreign' else ['workspace', 'foreign']}})
    assert not (await preflight(replica_db))['can_launch']


async def test_foreign_unresolved_work_is_not_used_as_current_workspace_hold(replica_db):
    await seed(replica_db)
    for workspace in ['foreign', ['workspace', 'foreign']]:
        await replica_db.outreach_intents.insert_one({'workspace_id': workspace, 'campaign_id': 'campaign', 'sender_id': 'sender', 'status': 'unknown_outcome'})
    assert (await preflight(replica_db))['can_launch']


@pytest.mark.parametrize('mode', ['manual_future', 'automatic_future', 'automatic_elapsed', 'wrong_claim'])
async def test_manual_future_warmup_and_claimed_automatic_admission(replica_db, mode):
    await seed(replica_db)
    now = datetime.now(timezone.utc)
    elapsed = mode == 'automatic_elapsed'
    await replica_db.outreach_engage_lists.insert_one({'id': 'list', 'workspace_id': 'workspace', 'campaign_id': 'campaign', 'warmup_hours': 24})
    await replica_db.outreach_engage_contacts.insert_one({'id': 'contact', 'list_id': 'list', 'workspace_id': 'workspace', 'profile_url': 'https://linkedin.com/in/synthetic'})
    await replica_db.outreach_engage_posts.insert_one({'workspace_id': 'workspace', 'list_id': 'list', 'contact_id': 'contact', 'status': 'liked', 'liked_at': now - timedelta(hours=25 if elapsed else 1)})
    auto = mode != 'manual_future'
    if auto:
        await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'warming_up', 'auto_launch_enabled': True, 'auto_launch_claim_id': 'claim', 'auto_launch_list_id': 'list'}})
    from outreach.core.campaign_readiness import assess
    campaign = await replica_db.outreach_campaigns.find_one({})
    claim = ('wrong' if mode == 'wrong_claim' else 'claim') if auto else None
    report = (await assess(replica_db, 'workspace', campaign, campaigns._evaluate_warmup, auto_claim=claim)).report
    assert report['can_launch'] is (mode in {'manual_future', 'automatic_elapsed'})
    if report['can_launch']:
        result = await campaigns._launch_campaign_impl('campaign', None, USER, replica_db, auto_launch_claim_id=claim)
        assert result['status'] == 'launched'
        assert bool(result['warmup_until'])
    else:
        with pytest.raises(HTTPException) as failure:
            await campaigns._launch_campaign_impl('campaign', None, USER, replica_db, auto_launch_claim_id=claim)
        assert failure.value.detail == report['blockers'][0]


async def test_warmup_capacity_overflow_is_unknown_and_read_only(replica_db):
    await seed(replica_db)
    await replica_db.outreach_engage_lists.insert_many([{'id': f'list-{i}', 'workspace_id': 'workspace', 'campaign_id': 'campaign'} for i in range(101)])
    report = await preflight(replica_db)
    assert not report['can_launch'] and report['checklist'][0]['id'] == 'verification'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


async def test_read_failure_never_reports_clear_or_leaks_database_detail(replica_db, monkeypatch):
    await seed(replica_db)
    from outreach.core import campaign_readiness
    monkeypatch.setattr(campaign_readiness, 'load_sequence', AsyncMock(side_effect=RuntimeError('mongodb://synthetic-private-detail')))
    report = await preflight(replica_db)
    assert not report['can_launch'] and 'synthetic-private-detail' not in str(report)
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 503 and failure.value.detail == report['blockers'][0]


@pytest.mark.parametrize('status', ['dispatching', 'uncertain'])
async def test_actual_finder_operation_family_blocks_launch(replica_db, status):
    await seed(replica_db)
    await replica_db.outreach_email_discoveries.insert_one({'workspace_id': 'workspace', 'sender_account_id': 'sender', 'source': 'email_find', 'status': status})
    report = await preflight(replica_db)
    assert not report['can_launch']
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.detail == report['blockers'][0]


async def test_saved_intent_receipt_requires_projection_repair(replica_db):
    await seed(replica_db)
    await replica_db.outreach_intents.insert_one({'workspace_id': 'workspace', 'sender_id': 'sender', 'status': 'executed'})
    assert not (await preflight(replica_db))['can_launch']
    await replica_db.outreach_intents.update_one({}, {'$set': {'projection_reconciled': True}})
    assert (await preflight(replica_db))['can_launch']


async def test_scoped_metadata_preflight_never_unwraps_keys(replica_db, monkeypatch):
    from tests.test_outreach_credential_custody import LocalKeys, ARN
    from outreach.core.credential_custody import CredentialCustody
    from outreach.core.proxy_custody import _context, proxy_record
    await seed(replica_db)
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'synthetic-environment')
    keys = LocalKeys(); custody = CredentialCustody(ARN, keys)
    monkeypatch.setattr(session_custody, 'configured_custody', lambda: custody)
    account = await replica_db.outreach_accounts.find_one({})
    proxy = proxy_record(account['proxy']); proxy.update(credential_generation='proxy-original', custody_workspace_id='workspace')
    proxy['password_enc'] = await custody.seal('synthetic-password', _context(proxy, 'workspace'))
    cookie = await custody.seal('synthetic-session', session_custody.context('workspace', 'sender', 'original', 'session_li_at'))
    js = await custody.seal('ajax:synthetic', session_custody.context('workspace', 'sender', 'original', 'session_jsession'))
    await replica_db.outreach_accounts.update_one({}, {'$set': {'proxy': proxy, 'session_cookie_enc': cookie, 'jsession_id': js}})
    await replica_db.outreach_proxy_inventory.update_one({}, {'$set': proxy})
    keys.calls.clear()
    report = await preflight(replica_db)
    assert report['can_launch'] is True and report['execution_ready'] is False
    assert keys.calls == []
    # Wrong context is known locally and cannot be advertised as eligible.
    await replica_db.outreach_accounts.update_one({}, {'$set': {'credential_generation': 'replacement'}})
    assert not (await preflight(replica_db))['can_launch']
    assert keys.calls == []


@pytest.mark.parametrize('fault', ['cycle', 'orphan', 'unresolved_ai', 'empty_email'])
async def test_known_sequence_failures_report_sequence_blocker(replica_db, fault):
    await seed(replica_db)
    nodes = [{'id': 'a', 'type': 'visit_profile', 'config': {}}]
    edges = []
    if fault in {'cycle', 'orphan'}:
        nodes.append({'id': 'b', 'type': 'visit_profile', 'config': {}})
        if fault == 'cycle': edges = [{'source': 'a', 'target': 'b'}, {'source': 'b', 'target': 'a'}]
    elif fault == 'empty_email': nodes = [{'id': 'a', 'type': 'send_email', 'config': {'subject': '', 'body': ''}}]
    else: nodes = [{'id': 'a', 'type': 'send_message', 'config': {'message': '✨ [Saved prompt]'}}]
    await replica_db.outreach_sequences.update_one({}, {'$set': {'nodes': nodes, 'edges': edges}})
    report = await preflight(replica_db)
    assert not report['can_launch']
    assert next(c for c in report['checklist'] if c['id'] == 'sequence')['passed'] is False
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 400 and failure.value.detail == report['blockers'][0]


@pytest.mark.parametrize('fault', [None, 'stale', 'unknown_refresh', 'array_scope', 'missing', 'pilot', 'disabled'])
async def test_email_only_launch_uses_its_own_capability_and_mailbox_gates(replica_db, monkeypatch, fault):
    await seed(replica_db)
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    monkeypatch.setenv('OUTREACH_EMAIL_SEND_ENABLED', 'true' if fault != 'disabled' else 'false')
    monkeypatch.setenv('OUTREACH_EMAIL_SYNC_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_MAILBOX_PILOT_WORKSPACES', 'workspace' if fault != 'pilot' else 'foreign')
    await replica_db.outreach_sequences.update_one({}, {'$set': {'nodes': [{'id': 'email', 'type': 'send_email', 'config': {'subject': 'Synthetic', 'body': 'Synthetic'}}]}})
    # LinkedIn cookie/proxy are not email transport prerequisites.
    await replica_db.outreach_accounts.update_one({}, {'$unset': {'session_cookie_enc': '', 'proxy': ''}})
    if fault != 'missing':
        await replica_db.outreach_mailboxes.insert_one({'workspace_id': ['workspace', 'foreign'] if fault == 'array_scope' else 'workspace',
            'sender_account_id': 'sender', 'status': 'active', 'sync_status': 'healthy',
            'access_token_enc': 'synthetic-encrypted-access', 'refresh_token_enc': 'synthetic-encrypted-refresh',
            'refresh_state': 'unknown' if fault == 'unknown_refresh' else 'idle',
            'last_sync_at': datetime.now(timezone.utc) - timedelta(minutes=11 if fault == 'stale' else 1)})
    report = await preflight(replica_db)
    assert report['can_launch'] is (fault is None)
    if fault is None:
        assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
        assert await replica_db.outreach_physical_requests.count_documents({}) == 0
    else:
        with pytest.raises(HTTPException) as failure:
            await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
        assert failure.value.detail == report['blockers'][0]


@pytest.mark.parametrize('change', [
    {'assigned_account_id': 'removed-sender'},
    {'assigned_account_id': ['sender']},
    {'current_node_id': 'removed-step'},
    {'current_node_id': ''},
    {'current_node_id': ['root']},
    {'current_node_id': None, 'last_action_taken': 'connection_request'},
    {'current_node_id': None, 'waiting_for_connection_at': datetime.now(timezone.utc)},
])
async def test_resume_holds_incompatible_lead_progress_without_reassignment_or_restart(replica_db, change):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await replica_db.outreach_leads.update_one({}, {'$set': change})
    before = await replica_db.outreach_leads.find_one({})
    report = await preflight(replica_db)
    assert not report['can_launch']
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.detail == report['blockers'][0]
    assert await replica_db.outreach_leads.find_one({}) == before
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


@pytest.mark.parametrize('state', ['staged', 'replied', 'finished', 'bounced', 'failed'])
async def test_terminal_or_staged_progress_does_not_block_other_launchable_leads(replica_db, state):
    await seed(replica_db)
    await replica_db.outreach_leads.insert_one({'id': 'historical', 'workspace_id': 'workspace',
        'campaign_id': 'campaign', 'execution_state': state, 'assigned_account_id': 'removed',
        'current_node_id': 'removed', 'last_action_taken': 'send_message'})
    assert (await preflight(replica_db))['can_launch'] is True


async def test_resume_preserves_valid_sender_step_and_due_time(replica_db):
    await seed(replica_db)
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=5)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await replica_db.outreach_leads.update_one({}, {'$set': {'assigned_account_id': 'sender',
        'current_node_id': 'root', 'execution_state': 'waiting_delay', 'next_action_due_at': due,
        'sequence_version': 1}})
    assert (await preflight(replica_db))['can_launch'] is True
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['assigned_account_id'] == 'sender' and lead['current_node_id'] == 'root'
    assert lead['execution_state'] == 'waiting_delay' and lead['next_action_due_at'] == due


@pytest.mark.parametrize('missing_field', [False, True])
@pytest.mark.parametrize('marker,value', [
    ('last_action_at', datetime.now(timezone.utc)),
    ('last_action_taken', 'connection_request'),
    ('waiting_for_connection_at', datetime.now(timezone.utc)),
    ('waiting_for_reply_at', datetime.now(timezone.utc)),
    ('last_action_taken', [None, 'connection_request']),
])
async def test_missing_sender_with_prior_progress_requires_review(replica_db, missing_field, marker, value):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': None, 'current_node_id': 'root', marker: value}})
    if missing_field:
        await replica_db.outreach_leads.update_one({}, {'$unset': {'assigned_account_id': ''}})
    before = await replica_db.outreach_leads.find_one({})
    report = await preflight(replica_db)
    assert not report['can_launch']
    assert next(item for item in report['checklist'] if item['id'] == 'lead_senders')['passed'] is False
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find_one({}) == before
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


@pytest.mark.parametrize('missing_field', [False, True])
@pytest.mark.parametrize('state', ['waiting_delay', 'waiting_trigger', 'paused', ['queued']])
async def test_unassigned_nonfresh_state_holds_even_without_optional_action_markers(replica_db, missing_field, state):
    await seed(replica_db)
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=5)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': None, 'current_node_id': None,
        'execution_state': state, 'next_action_due_at': due}})
    if missing_field:
        await replica_db.outreach_leads.update_one({}, {'$unset': {'assigned_account_id': ''}})
    before = await replica_db.outreach_leads.find_one({})
    report = await preflight(replica_db)
    assert not report['can_launch']
    assert next(item for item in report['checklist'] if item['id'] == 'lead_senders')['passed'] is False
    with pytest.raises(HTTPException) as failure:
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.find_one({}) == before


@pytest.mark.parametrize('missing_field', [False, True])
async def test_unacted_unassigned_root_still_receives_first_sender(replica_db, missing_field):
    await seed(replica_db)
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=5)
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': None, 'current_node_id': 'root', 'next_action_due_at': due}})
    if missing_field:
        await replica_db.outreach_leads.update_one({}, {'$unset': {'assigned_account_id': ''}})
    assert (await preflight(replica_db))['can_launch'] is True
    assert (await campaigns._launch_campaign_impl('campaign', None, USER, replica_db))['status'] == 'launched'
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['assigned_account_id'] == 'sender' and lead['current_node_id'] == 'root'
    assert lead['next_action_due_at'] == due


@pytest.mark.parametrize('state,replied', [
    ('staged', False), ('replied', False), ('finished', False),
    ('bounced', False), ('failed', False), ('queued', True),
])
async def test_no_outstanding_prospects_cannot_activate_an_idle_campaign(replica_db, state, replied):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {'status': 'paused'}})
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'execution_state': state, 'has_replied': replied, 'assigned_account_id': 'sender',
        'current_node_id': 'root'}})
    # Neither another tenant nor another campaign supplies an actionable lead.
    await replica_db.outreach_leads.insert_many([
        {'id': 'foreign', 'workspace_id': 'foreign', 'campaign_id': 'campaign', 'execution_state': 'queued'},
        {'id': 'other-campaign', 'workspace_id': 'workspace', 'campaign_id': 'other', 'execution_state': 'queued'},
    ])
    before = await replica_db.outreach_leads.find({}).sort('id', 1).to_list(length=10)
    report = await preflight(replica_db)
    assert report['can_launch'] is False
    assert not next(item for item in report['checklist'] if item['id'] == 'actionable_leads')['passed']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)
    assert await replica_db.outreach_leads.find({}).sort('id', 1).to_list(length=10) == before
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'paused'
    assert await replica_db.outreach_sequence_versions.count_documents({}) == 0


async def test_unassigned_nonroot_without_optional_markers_requires_review(replica_db):
    await seed(replica_db)
    await replica_db.outreach_sequences.update_one({}, {'$set': {
        'nodes': [{'id': 'root', 'type': 'visit_profile', 'config': {}},
                  {'id': 'later', 'type': 'visit_profile', 'config': {}}],
        'edges': [{'source': 'root', 'target': 'later'}]}})
    await replica_db.outreach_leads.update_one({}, {'$set': {
        'assigned_account_id': None, 'current_node_id': 'later'}})
    report = await preflight(replica_db)
    assert report['can_launch'] is False
    assert not next(item for item in report['checklist'] if item['id'] == 'lead_senders')['passed']
    with pytest.raises(HTTPException):
        await campaigns._launch_campaign_impl('campaign', None, USER, replica_db)


@pytest.mark.parametrize('change', [
    {'status': 'active'}, {'status': 'warming_up'}, {'status': 'completed'},
    {'authorization_revision': 1}, {'lead_admission_revision': 1},
    {'launch_claim_token': 'preparing', 'launch_claim_expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)},
])
async def test_auto_draft_compare_and_set_cannot_overwrite_a_concurrent_campaign_change(replica_db, change):
    await seed(replica_db)
    original = replica_db.outreach_campaigns.update_one
    changed = False

    async def interleave(query, update, *args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            await original({'id': 'campaign'}, {'$set': change})
        return await original(query, update, *args, **kwargs)

    # Motor returns a fresh collection wrapper on each attribute lookup. Keep
    # this one injected boundary so the interleaving really reaches MongoDB.
    observed_db = SimpleNamespace(outreach_campaigns=SimpleNamespace(
        find_one=replica_db.outreach_campaigns.find_one, update_one=interleave))
    request = campaigns.AutoDraftRequest(campaign_id='campaign', name='Stale edit',
        sender_account_ids=[], limits={'messages': 100})
    with pytest.raises(HTTPException) as failure:
        await campaigns.auto_draft_campaign(request, USER, observed_db)
    assert changed
    assert failure.value.status_code == 409
    stored = await replica_db.outreach_campaigns.find_one({})
    assert stored.get('name') != 'Stale edit' and stored['sender_account_ids'] == ['sender']
    assert stored.get('limits') != {'messages': 100}
    assert all(stored[key] == value for key, value in change.items() if not isinstance(value, datetime))


@pytest.mark.parametrize('change', [
    {'status': 'completed'}, {'authorization_revision': True}, {'authorization_revision': 'unproven'},
    {'launch_claim_token': 'preparing'},
    {'launch_claim_expires_at': 'unproven'},
    {'launch_claim_token': 'preparing', 'launch_claim_expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)},
])
async def test_auto_draft_requires_current_editable_authority(replica_db, change):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': change})
    before = await replica_db.outreach_campaigns.find_one({})
    with pytest.raises(HTTPException) as failure:
        await campaigns.auto_draft_campaign(campaigns.AutoDraftRequest(campaign_id='campaign', name='Denied'), USER, replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_campaigns.find_one({}) == before


@pytest.mark.parametrize('revision', [None, 3])
async def test_auto_draft_success_advances_authorization_revision(replica_db, revision):
    await seed(replica_db)
    if revision is None:
        await replica_db.outreach_campaigns.update_one({}, {'$unset': {'authorization_revision': ''}})
    else:
        await replica_db.outreach_campaigns.update_one({}, {'$set': {'authorization_revision': revision}})
    saved = await campaigns.auto_draft_campaign(campaigns.AutoDraftRequest(campaign_id='campaign', name='Current'), USER, replica_db)
    assert saved['name'] == 'Current' and saved['authorization_revision'] == (revision or 0) + 1


async def test_auto_draft_cannot_adopt_a_replacement_native_campaign(replica_db):
    await seed(replica_db)
    collection = replica_db.outreach_campaigns
    original = await collection.find_one({})

    async def replace_before_update(query, update):
        replacement = {**original, '_id': 'replacement', 'name': 'Replacement'}
        await collection.delete_one({'_id': original['_id']})
        await collection.insert_one(replacement)
        return await collection.update_one(query, update)

    observed = SimpleNamespace(outreach_campaigns=SimpleNamespace(
        find_one=collection.find_one, update_one=replace_before_update))
    with pytest.raises(HTTPException) as failure:
        await campaigns.auto_draft_campaign(campaigns.AutoDraftRequest(campaign_id='campaign', name='Stale'), USER, observed)
    assert failure.value.status_code == 409
    stored = await collection.find_one({})
    assert stored['_id'] == 'replacement' and stored['name'] == 'Replacement'
    assert stored['authorization_revision'] == 0


async def test_concurrent_draft_saves_publish_only_one_observed_revision(replica_db):
    await seed(replica_db)
    collection = replica_db.outreach_campaigns
    both_read = asyncio.Event()
    reads = 0

    async def observe(query):
        nonlocal reads
        doc = await collection.find_one(query)
        reads += 1
        if reads <= 2:
            if reads == 2:
                both_read.set()
            await asyncio.wait_for(both_read.wait(), timeout=3)
        return doc

    observed = SimpleNamespace(outreach_campaigns=SimpleNamespace(
        find_one=observe, update_one=collection.update_one))
    results = await asyncio.gather(*(campaigns.auto_draft_campaign(
        campaigns.AutoDraftRequest(campaign_id='campaign', name=name), USER, observed)
        for name in ['First', 'Second']), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    errors = [result for result in results if isinstance(result, HTTPException)]
    assert len(errors) == 1 and errors[0].status_code == 409
    assert (await collection.find_one({}))['authorization_revision'] == 1


async def test_expired_observed_launch_claim_allows_an_edit_without_releasing_new_ownership(replica_db):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {'$set': {
        'launch_claim_token': 'expired', 'launch_claim_expires_at': datetime.now(timezone.utc) - timedelta(minutes=1)}})
    saved = await campaigns.auto_draft_campaign(campaigns.AutoDraftRequest(campaign_id='campaign', name='Current'), USER, replica_db)
    assert saved['name'] == 'Current' and saved['authorization_revision'] == 1
    assert saved['launch_claim_token'] == 'expired'
