"""Warm-up and contact/cohort edits share the admission transaction guard."""
import asyncio
import os
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from outreach.api import campaigns, engage
from outreach.core.lead_importer import LeadImporter
from outreach.core.suppression import SuppressionCollection
from outreach.core.activation import claim_activation
from datetime import datetime, timedelta, timezone
from tests.outreach_native import replica_server, replica_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}

async def setup(db, monkeypatch):
    monkeypatch.setattr(campaigns, 'conditional_auto_launch_enabled', lambda: True)
    await db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': 'workspace', 'status': 'draft', 'sender_account_ids': ['sender'], 'leads_count': 1})
    await db.outreach_engage_lists.insert_one({'id': 'list', 'workspace_id': 'workspace', 'campaign_id': None})
    await db.outreach_leads.insert_one({'id': 'original', 'campaign_id': 'campaign', 'workspace_id': 'workspace', 'execution_state': 'queued'})
    await db.outreach_sequences.insert_one({'id': 'sequence', 'campaign_id': 'campaign', 'workspace_id': 'workspace', 'nodes': [{'id': 'root'}]})

async def arm(db):
    return await campaigns.arm_warmup_campaign('campaign', campaigns.ArmWarmupRequest(engage_list_id='list', warmup_hours=24), current_user=USER, db=db)

@pytest.mark.parametrize('mutation', ['add', 'remove', 'settings', 'delete_list'])
async def test_armed_list_rejects_all_cohort_mutations(replica_db, monkeypatch, mutation):
    await setup(replica_db, monkeypatch)
    await replica_db.outreach_engage_contacts.insert_one({'id': 'contact', 'list_id': 'list', 'workspace_id': 'workspace'})
    await arm(replica_db)
    with pytest.raises(HTTPException) as failure:
        if mutation == 'add': await engage.add_contacts_to_list('list', engage.AddContactsRequest(profile_urls=['https://linkedin.com/in/new']), current_user=USER, db=replica_db)
        if mutation == 'remove': await engage.delete_engage_contact('list', 'contact', current_user=USER, db=replica_db)
        if mutation == 'settings': await engage.update_engage_list_settings('list', engage.EngageListSettingsRequest(campaign_id=None), current_user=USER, db=replica_db)
        if mutation == 'delete_list': await engage.delete_engage_list('list', current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_engage_lists.count_documents({}) == 1
    assert await replica_db.outreach_engage_contacts.count_documents({}) == 1

async def test_arm_does_not_include_unreviewed_staged_contacts(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    await replica_db.outreach_leads.insert_one({'id': 'staged', 'workspace_id': 'workspace', 'campaign_id': 'campaign', 'execution_state': 'staged'})
    await arm(replica_db)
    assert (await replica_db.outreach_campaigns.find_one({}))['auto_launch_lead_ids'] == ['original']

async def test_arm_failure_rolls_back_campaign_and_list(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == 'outreach_engage_lists': raise OperationFailure('Synthetic list link failure')
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail)
    with pytest.raises(HTTPException) as failure: await arm(replica_db)
    assert failure.value.status_code == 503
    assert (await replica_db.outreach_campaigns.find_one({}))['status'] == 'draft'
    assert (await replica_db.outreach_engage_lists.find_one({}))['campaign_id'] is None

async def test_import_and_arm_have_one_ordered_cohort(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    results = await asyncio.gather(arm(replica_db), LeadImporter.ingest_leads(
        [{'linkedin_url': 'https://linkedin.com/in/new', 'first_name': 'New'}], 'campaign', 'workspace', replica_db), return_exceptions=True)
    assert not isinstance(results[0], Exception)
    current = await replica_db.outreach_campaigns.find_one({})
    rows = await replica_db.outreach_leads.find({'execution_state': 'queued'}).to_list(None)
    assert current['auto_launch_lead_ids'] == sorted(row['id'] for row in rows)
    if isinstance(results[1], Exception): assert isinstance(results[1], HTTPException) and results[1].status_code == 409
    else: assert results[1]['imported_count'] == 1

@pytest.mark.parametrize('mutation', ['settings', 'remove', 'delete_list', 'add'])
async def test_manual_launch_claim_blocks_list_mutations(replica_db, monkeypatch, mutation):
    await setup(replica_db, monkeypatch)
    await replica_db.outreach_engage_lists.update_one({}, {'$set': {'campaign_id': 'campaign'}})
    await replica_db.outreach_engage_contacts.insert_one({'id': 'contact', 'list_id': 'list', 'workspace_id': 'workspace'})
    assert await claim_activation(replica_db, await replica_db.outreach_campaigns.find_one({}))
    with pytest.raises(HTTPException) as failure:
        if mutation == 'settings': await engage.update_engage_list_settings('list', engage.EngageListSettingsRequest(), current_user=USER, db=replica_db)
        if mutation == 'remove': await engage.delete_engage_contact('list', 'contact', current_user=USER, db=replica_db)
        if mutation == 'delete_list': await engage.delete_engage_list('list', current_user=USER, db=replica_db)
        if mutation == 'add': await engage.add_contacts_to_list('list', engage.AddContactsRequest(profile_urls=['https://linkedin.com/in/new']), current_user=USER, db=replica_db)
    assert failure.value.status_code == 409

async def test_list_link_invalidates_previously_captured_launch(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch)
    captured = await replica_db.outreach_campaigns.find_one({})
    await engage.update_engage_list_settings('list', engage.EngageListSettingsRequest(campaign_id='campaign'), current_user=USER, db=replica_db)
    assert await claim_activation(replica_db, captured) is None

async def test_paid_sender_readiness_stays_outside_scoped_contact_transaction(replica_db, monkeypatch):
    from outreach.core import paid_access
    from celery_workers.celery_app import celery_app
    from unittest.mock import Mock
    await setup(replica_db, monkeypatch)
    monkeypatch.setattr(paid_access, 'live_actions_enabled', lambda: True)
    future = datetime.now(timezone.utc) + timedelta(days=10)
    await replica_db.outreach_entitlements.insert_one({'workspace_id': 'workspace', 'status': 'active', 'seats': 1,
        'payment_source': 'manual_verified_invoice', 'paid_through': future})
    await replica_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'workspace', 'status': 'active',
        'country_code': 'US', 'proxy': {'proxy_id': 'proxy', 'host': '192.0.2.1'}})
    await replica_db.outreach_proxy_leases.insert_one({'_id': 'proxy', 'workspace_id': 'workspace', 'sender_id': 'sender'})
    await replica_db.outreach_proxy_inventory.insert_one({'_id': 'proxy', 'last_workspace_id': 'workspace',
        'host': '192.0.2.1', 'status': 'available', 'provider': 'iproyal_static', 'country_code': 'US', 'expires_at': future})
    publish = Mock(); monkeypatch.setattr(celery_app, 'send_task', publish)
    result = await engage.add_contacts_to_list('list', engage.AddContactsRequest(sender_account_id='sender',
        profile_urls=['https://linkedin.com/in/new']), current_user=USER, db=replica_db)
    assert result['added_count'] == 1 and result['enrichment_status'] == 'queued'
    publish.assert_called_once()
    assert publish.call_args.kwargs['args'][:3] == ['list', 'workspace', 'sender']
    assert len(publish.call_args.kwargs['args'][3]) == 32
