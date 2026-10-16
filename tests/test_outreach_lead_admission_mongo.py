"""Current campaign admission, atomic counts/events and intake convergence on Mongo."""
import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from outreach.api import integrations, leads as lead_api
from outreach.core.lead_importer import LeadImporter
from outreach.core.suppression import SuppressionCollection, guard_scope
from outreach.core.activation import claim_activation, activation_lead_filter
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
WS = 'workspace'
USER = {'user_id': 'actor', 'default_workspace_id': WS}
ROW = {'linkedin_url': 'https://linkedin.com/in/person', 'first_name': 'Person', 'email': 'person@example.test'}

@pytest.fixture(autouse=True)
def isolated_integration_permission(monkeypatch):
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_PILOT_WORKSPACES', WS)


async def campaign(db, status='active'):
    doc = {'id': 'campaign', 'workspace_id': WS, 'status': status, 'leads_count': 0,
           'sender_account_ids': ['sender'], 'authorization_revision': 4, 'sequence_version_id': 'version'}
    await db.outreach_campaigns.insert_one(doc)
    await db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': WS, 'status': 'active'})
    await db.outreach_sequence_versions.insert_one({'_id': 'version', 'campaign_id': 'campaign', 'workspace_id': WS,
        'version': 3, 'compiled_dag': {'root_node_ids': ['root'], 'nodes': {'root': {
            'id':'root','type':'visit_profile','delay_hours':0,'config':{},'branches':{},'next_default':None}}}})
    return doc


async def ingest(db, **kwargs):
    return await LeadImporter.ingest_leads([dict(ROW)], 'campaign', WS, db, **kwargs)


async def test_active_import_has_current_bindings_count_and_event(replica_db):
    await campaign(replica_db)
    result = await ingest(replica_db)
    assert result['imported_count'] == 1
    lead = await replica_db.outreach_leads.find_one({'workspace_id': WS})
    assert lead['assigned_account_id'] == 'sender' and lead['current_node_id'] == 'root'
    assert lead['authorized_revision'] == 4 and lead['sequence_version'] == 3 and lead['enrollment_id']
    assert (await replica_db.outreach_campaigns.find_one({'id': 'campaign'}))['leads_count'] == 1
    assert await replica_db.outreach_event_outbox.count_documents({'workspace_id': WS}) == 1


@pytest.mark.parametrize('status', ['warming_up', 'completed', 'archived'])
async def test_stale_snapshot_cannot_admit_after_current_state_changes(replica_db, status):
    old = await campaign(replica_db)
    await replica_db.outreach_campaigns.update_one({'id': 'campaign'}, {'$set': {'status': status}})
    with pytest.raises(HTTPException) as failure:
        await ingest(replica_db, campaign=old)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.count_documents({}) == 0


@pytest.mark.parametrize('change', ['deleted', 'missing_sender', 'missing_root', 'missing_revision', 'engage'])
async def test_unproven_active_binding_does_not_create_unbound_work(replica_db, change):
    await campaign(replica_db)
    if change == 'deleted': await replica_db.outreach_campaigns.update_one({'id': 'campaign'}, {'$set': {'is_deleted': True}})
    if change == 'missing_sender': await replica_db.outreach_accounts.delete_many({})
    if change == 'missing_root': await replica_db.outreach_sequence_versions.update_one({}, {'$set': {'compiled_dag.root_node_ids': []}})
    if change == 'missing_revision': await replica_db.outreach_campaigns.update_one({}, {'$unset': {'authorization_revision': ''}})
    if change == 'engage': await replica_db.outreach_campaigns.update_one({}, {'$set': {'engage_list_id': 'list'}})
    with pytest.raises(HTTPException): await ingest(replica_db)
    assert await replica_db.outreach_leads.count_documents({}) == 0


async def test_concurrent_same_profile_has_one_lead_one_count_one_event(replica_db):
    await campaign(replica_db)
    results = await asyncio.gather(ingest(replica_db), ingest(replica_db))
    assert sum(result['imported_count'] for result in results) == 1
    assert await replica_db.outreach_leads.count_documents({}) == 1
    assert await replica_db.outreach_event_outbox.count_documents({}) == 1
    assert (await replica_db.outreach_campaigns.find_one({}))['leads_count'] == 1


async def test_event_write_failure_rolls_back_lead_and_campaign_count(replica_db, monkeypatch):
    await campaign(replica_db)
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == 'outreach_event_outbox': raise OperationFailure('Synthetic event write rejection')
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail)
    with pytest.raises(HTTPException) as failure: await ingest(replica_db)
    assert failure.value.status_code == 503
    assert await replica_db.outreach_leads.count_documents({}) == 0
    assert (await replica_db.outreach_campaigns.find_one({}))['leads_count'] == 0


async def test_email_suppression_is_mandatory_in_common_import(replica_db):
    await campaign(replica_db)
    await replica_db.outreach_email_suppressions.insert_one({'workspace_id': WS, 'email': ROW['email']})
    result = await ingest(replica_db, skip_do_not_contact=False, include_rejections=True)
    assert result['imported_count'] == 0 and result['rejections'][0]['rejection_code'] == 'email_suppressed'


async def test_erased_workspace_and_standalone_deny_without_partial_enrollment(replica_db, real_db):
    for db in (replica_db, real_db):
        await campaign(db)
    await replica_db.outreach_suppression_guards.insert_one({**guard_scope(WS), 'erasure_state': 'stopped'})
    for db in (replica_db, real_db):
        before = await db.outreach_leads.count_documents({})
        with pytest.raises(HTTPException) as failure: await ingest(db)
        assert failure.value.status_code == 503
        assert await db.outreach_leads.count_documents({}) == before


async def staged(db):
    await db.outreach_import_jobs.insert_one({'id': 'job', 'campaign_id': 'campaign', 'workspace_id': WS, 'status': 'completed'})
    await db.outreach_leads.insert_one({**ROW, 'id': 'staged', 'campaign_id': 'campaign', 'workspace_id': WS,
        'import_job_id': 'job', 'execution_state': 'staged', 'staged_at': 'original'})


async def test_search_promotion_preserves_identity_and_installs_binding_once(replica_db):
    await campaign(replica_db); await staged(replica_db)
    before = await replica_db.outreach_leads.find_one({'id': 'staged'})
    for _ in range(2):
        with pytest.raises(HTTPException) as failure:
            await lead_api.commit_staged_leads('job', None, current_user=USER, db=replica_db)
        assert failure.value.status_code == 409
    lead = await replica_db.outreach_leads.find_one({'id': 'staged'})
    assert lead == before and lead['execution_state'] == 'staged'
    assert await replica_db.outreach_leads.count_documents({}) == 1
    assert (await replica_db.outreach_campaigns.find_one({}))['leads_count'] == 0


async def test_search_promotion_during_warmup_preserves_staged_row(replica_db):
    await campaign(replica_db, 'warming_up'); await staged(replica_db)
    with pytest.raises(HTTPException) as failure:
        await lead_api.commit_staged_leads('job', None, current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_leads.find_one({}))['execution_state'] == 'staged'


@pytest.mark.parametrize('body', [{}, {'name_overrides': None}, {'selected_lead_ids': ['staged']}])
async def test_search_promotion_accepts_actual_unedited_review_payload(replica_db, body):
    await campaign(replica_db); await staged(replica_db)
    req = lead_api.CommitStagedLeadsRequest(**body)
    with pytest.raises(HTTPException) as failure:
        await lead_api.commit_staged_leads('job', req, current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_leads.find_one({'id': 'staged'}))['first_name'] == 'Person'


async def test_sheets_uses_common_binding_and_suppression(replica_db):
    await campaign(replica_db)
    req = integrations.SheetsImportRequest(campaign_id='campaign', rows=[dict(ROW)])
    result = await integrations.import_sheets_leads(req, current_user=USER, db=replica_db)
    assert result['enrolled_count'] == 1
    lead = await replica_db.outreach_leads.find_one({})
    assert lead['assigned_account_id'] == 'sender' and lead['enrollment_id'] and lead['sequence_version'] == 3


async def test_public_request_key_is_bound_to_payload_and_original_result(replica_db):
    await campaign(replica_db)
    auth = {'workspace_id': WS, 'key_id': 'key', 'key_hash': 'digest', 'scopes': ['leads:write']}
    await replica_db.outreach_api_keys.insert_one({'id': 'key', 'workspace_id': WS, 'key_hash': 'digest', 'scopes': ['leads:write']})
    req = integrations.PublicLeadEnrollRequest(campaign_id='campaign', **ROW)
    first = await integrations.public_enroll_lead(req, 'operation', auth=auth, db=replica_db)
    again = await integrations.public_enroll_lead(req, 'operation', auth=auth, db=replica_db)
    assert first == again and first['status'] == 'enrolled'
    req.first_name = 'Changed'
    with pytest.raises(HTTPException) as failure:
        await integrations.public_enroll_lead(req, 'operation', auth=auth, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.count_documents({}) == 1


async def test_public_revoked_key_is_rechecked_at_admission(replica_db):
    await campaign(replica_db)
    await replica_db.outreach_api_keys.insert_one({'id': 'key', 'workspace_id': WS, 'key_hash': 'digest', 'scopes': ['leads:write'], 'revoked_at': 'stopped'})
    with pytest.raises(HTTPException) as failure:
        await integrations.public_enroll_lead(integrations.PublicLeadEnrollRequest(campaign_id='campaign', **ROW), 'op',
            auth={'workspace_id': WS, 'key_id': 'key', 'key_hash': 'digest'}, db=replica_db)
    assert failure.value.status_code == 401
    assert await replica_db.outreach_leads.count_documents({}) == 0


async def test_new_intake_invalidates_previously_captured_launch_cohort(replica_db):
    captured = await campaign(replica_db, 'draft')
    assert (await ingest(replica_db))['imported_count'] == 1
    assert await claim_activation(replica_db, captured) is None
    assert not (await replica_db.outreach_campaigns.find_one({})).get('launch_claim_token')


@pytest.mark.parametrize('path', ['common', 'search', 'sheets', 'public'])
async def test_intake_after_launch_binding_pass_is_rejected(replica_db, path):
    captured = await campaign(replica_db, 'draft')
    claim = await claim_activation(replica_db, captured)
    assert claim
    await replica_db.outreach_leads.update_many(activation_lead_filter(WS, 'campaign', claim['revision']), {'$set': {'authorized_revision': claim['revision']}})
    await staged(replica_db)
    await replica_db.outreach_api_keys.insert_one({'id': 'key', 'workspace_id': WS, 'key_hash': 'digest', 'scopes': ['leads:write']})
    with pytest.raises(HTTPException) as failure:
        if path == 'common': await ingest(replica_db)
        if path == 'search': await lead_api.commit_staged_leads('job', None, current_user=USER, db=replica_db)
        if path == 'sheets': await integrations.import_sheets_leads(integrations.SheetsImportRequest(campaign_id='campaign', rows=[dict(ROW)]), current_user=USER, db=replica_db)
        if path == 'public': await integrations.public_enroll_lead(integrations.PublicLeadEnrollRequest(campaign_id='campaign', **ROW), 'operation', auth={'workspace_id': WS, 'key_id': 'key', 'key_hash': 'digest'}, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.count_documents({'execution_state': 'queued'}) == 0
    assert (await replica_db.outreach_leads.find_one({'id': 'staged'}))['execution_state'] == 'staged'


async def test_launch_binding_does_not_adopt_unreviewed_staged_rows(replica_db):
    await campaign(replica_db, 'draft'); await staged(replica_db)
    await replica_db.outreach_leads.update_many(activation_lead_filter(WS, 'campaign', 5), {'$set': {'authorized_revision': 5}})
    assert 'authorized_revision' not in await replica_db.outreach_leads.find_one({'id': 'staged'})
