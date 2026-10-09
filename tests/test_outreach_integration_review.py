"""Private integration repair preserves evidence and never invokes providers."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock
import pytest
from outreach.core import integration_custody as custody, integration_review as review, suppression
from outreach.core.integration_delivery import IntegrationDelivery, now, receipt_digest
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped

pytestmark = pytest.mark.asyncio
EVIDENCE = 'All API, scheduler, workers and cached credentials are drained for this local test.'

async def held(db, monkeypatch, kind='hubspot', received=False):
    job = await queue(db, kind)
    changes = {'status': 'held_received' if received else 'review_required', 'lease_id': 'original-owner',
        'leased_until': now()-timedelta(seconds=1), 'possible_at': now()-timedelta(seconds=4),
        'authorization_expires_at': now()-timedelta(seconds=2), 'attempt': 1}
    if received:
        receipt = {'status_code': 200, 'received_at': now()-timedelta(seconds=3)}
        if kind == 'hubspot': receipt['external_id'] = '123'
        changes.update(receipt=receipt, receipt_digest=receipt_digest(receipt))
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': changes})
    await db.outreach_accounts.insert_one({'_id':'sender-row', 'workspace_id':'w', 'id':'sender', 'status':'connected'})
    await db.outreach_campaigns.insert_one({'_id':'campaign-row', 'workspace_id':'w', 'id':'campaign', 'status':'active', 'authorization_revision':3})
    await db.outreach_sender_execution.insert_one({'_id':'execution-row', 'workspace_id':'w', 'sender_id':'sender', 'status':'in_flight',
        'owner_token':'unrelated-owner', 'physical_request_token':'unrelated-physical', 'permission':{'latched':False}})
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    return await db.outreach_webhook_deliveries.find_one({'id':job['id']})

async def resolve(service, job, decision='stop_local'):
    view = await service.inspect('w',job['id'])
    return await service.resolve('w',job['id'],decision,'operator',EVIDENCE,
        workers_drained=True,expected_digest=view['review_digest'])

async def test_unknown_stop_keeps_slot_evidence_and_tokens(integration_db,monkeypatch):
    db=integration_db; job=await held(db,monkeypatch)
    result=await resolve(review.IntegrationReview(db),job)
    assert result['outcome_at_review']=='unknown' and not result['activation_allowed']
    row=await db.outreach_webhook_deliveries.find_one({'id':job['id']})
    assert row['active_slot']==job['active_slot'] and row['status']=='review_required'
    assert row['possible_at']==job['possible_at'] and row['attempt']==1
    execution=db.outreach_sender_execution.docs[0]
    assert execution['physical_request_token']=='unrelated-physical' and execution['permission']['latched']
    assert db.outreach_campaigns.docs[0]['authorization_revision']==4
    view=await review.IntegrationReview(db).inspect('w',job['id'])
    assert 'private-' not in str(view) and 'person@example.com' not in str(view)
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
    with pytest.raises(ValueError): await IntegrationDelivery(db).queue('w','hubspot','hubspot','new-event',{},actor='actor',lead_id='lead')

@pytest.mark.parametrize('kind',['webhook','slack','hubspot'])
async def test_original_receipt_finishes_without_key_http_or_reactivation(integration_db,monkeypatch,kind):
    db=integration_db;job=await held(db,monkeypatch,kind,True)
    opening=AsyncMock(side_effect=AssertionError('No opening'));monkeypatch.setattr(custody,'prepare',opening)
    result=await resolve(review.IntegrationReview(db),job,'use_receipt')
    assert result['status']=='review_completed' and result['outcome_at_review']=='received'
    assert not result['activation_allowed']
    row=await db.outreach_webhook_deliveries.find_one({'id':job['id']})
    assert row['receipt']==job['receipt'] and row['active_slot'] is None
    if kind=='hubspot': assert db.outreach_external_mappings.docs[0]['external_id']=='123'
    assert db.outreach_campaigns.docs[0]['status']=='paused'
    provider=AsyncMock();await IntegrationDelivery(db).run('w',job['id'],provider=provider)
    provider.assert_not_awaited();opening.assert_not_awaited()

@pytest.mark.parametrize('change',['source','owner','receipt','lead','mapping','campaign','policy'])
async def test_stale_review_denies_without_stop(integration_db,monkeypatch,change):
    db=integration_db;job=await held(db,monkeypatch,received=True);service=review.IntegrationReview(db)
    view=await service.inspect('w',job['id'])
    if change=='source': await db.outreach_integrations.update_one({'provider':'hubspot'},{'$set':{'credential_generation':'replacement'}})
    elif change=='owner': await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'lease_id':'replacement'}})
    elif change=='receipt': await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'receipt.external_id':'456'}})
    elif change=='lead': await db.outreach_leads.update_one({'id':'lead'},{'$set':{'first_name':'replacement'}})
    elif change=='mapping': await db.outreach_external_mappings.insert_one({'workspace_id':'w','provider':'hubspot','internal_id':'lead','external_account_id':'123','object_type':'contact','external_id':'456'})
    elif change=='campaign': await db.outreach_campaigns.update_one({'id':'campaign'},{'$inc':{'authorization_revision':1}})
    else:monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','changed')
    with pytest.raises(ValueError): await service.resolve('w',job['id'],'use_receipt','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert db.outreach_campaigns.docs[0]['status']=='active'
    assert not db.outreach_integration_reviews.docs

@pytest.mark.parametrize('problem',['drain','live','studio','generation','integrations','lease','missing_lease','capacity','ambiguous'])
async def test_unsafe_review_denies(integration_db,monkeypatch,problem):
    db=integration_db;job=await held(db,monkeypatch,received=True)
    flags={'live':'OUTREACH_LIVE_ACTIONS_ENABLED','studio':'OUTREACH_VOICE_STUDIO_ENABLED','generation':'OUTREACH_VOICE_PREPARATION_ENABLED','integrations':'OUTREACH_INTEGRATIONS_ENABLED'}
    if problem in flags:monkeypatch.setenv(flags[problem],'true')
    if problem=='lease':await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'leased_until':now()+timedelta(seconds=60)}})
    if problem=='missing_lease':await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$unset':{'leased_until':''}})
    if problem=='capacity':db.outreach_accounts.docs.extend({'workspace_id':'w','id':str(i)} for i in range(101))
    if problem=='ambiguous':
        receipt={**job['receipt'],'status_code':409};await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'receipt':receipt,'receipt_digest':receipt_digest(receipt)}})
    service=review.IntegrationReview(db);view=await service.inspect('w',job['id'])
    with pytest.raises(ValueError):await service.resolve('w',job['id'],'use_receipt','operator',EVIDENCE,workers_drained=problem!='drain',expected_digest=view['review_digest'])

async def test_ack_loss_retry_uses_journal_without_second_stop(integration_db,monkeypatch):
    db=integration_db;job=await held(db,monkeypatch);service=review.IntegrationReview(db);view=await service.inspect('w',job['id'])
    first=await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])==first
    assert db.outreach_campaigns.docs[0]['authorization_revision']==4
    with pytest.raises(ValueError):await service.resolve('w',job['id'],'use_receipt','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])

async def test_legacy_missing_provider_type_is_stop_only_and_scrubs_copied_secret(integration_db,monkeypatch):
    db=integration_db;monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    await db.outreach_webhook_deliveries.insert_one({'_id':'legacy','id':'legacy','workspace_id':'w','destination_id':'hook',
        'status':'review_required','secret_enc':'copied-opaque-secret','target_url_enc':'copied-opaque-url'})
    service=review.IntegrationReview(db);view=await service.inspect('w','legacy')
    assert view['allowed_decisions']==['stop_local'] and view['outcome_at_review']=='unknown'
    assert 'copied-opaque' not in str(view)
    result=await service.resolve('w','legacy','stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    row=await db.outreach_webhook_deliveries.find_one({'id':'legacy'})
    assert result['outcome_at_review']=='unknown' and row['status']=='review_required' and 'secret_enc' not in row

async def test_permanent_resource_hold_survives_delete_and_reconnect(integration_db,monkeypatch):
    from tests.test_outreach_integration_custody import resource
    db=integration_db;job=await held(db,monkeypatch,'slack')
    await resolve(review.IntegrationReview(db),job)
    assert await custody.disconnect(db,'w','slack','slack',authority={'actor':'actor'})
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
    row=resource('slack');row.update(await custody.seal('https://hooks.slack.com/services/T1/B2/private-token',row,'w','slack'))
    with pytest.raises(ValueError,match='held'):
        await custody.save(db,'w','slack',row,previous=None,policy=custody.policy_digest(),authority={'actor':'actor'})
    assert db.outreach_integration_controls.docs[0]['latched']
    with pytest.raises(ValueError):await IntegrationDelivery(db).queue('w','slack','slack','new-event',{},actor='actor')

@pytest.mark.parametrize('state',['preparing','possible'])
async def test_previous_receipt_never_proves_current_attempt(integration_db,monkeypatch,state):
    db=integration_db;job=await held(db,monkeypatch,received=True)
    await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'status':state}})
    view=await review.IntegrationReview(db).inspect('w',job['id'])
    assert view['outcome_at_review']=='unknown' and 'use_receipt' not in view['allowed_decisions']

async def test_proven_preparing_noncall_releases_only_original_slot(integration_db,monkeypatch):
    db=integration_db;job=await held(db,monkeypatch)
    await db.outreach_webhook_deliveries.update_one({'id':job['id']},{'$set':{'status':'preparing','attempt':0},
        '$unset':{'possible_at':'','authorization_expires_at':''}})
    result=await resolve(review.IntegrationReview(db),job)
    row=await db.outreach_webhook_deliveries.find_one({'id':job['id']})
    assert result['outcome_at_review']=='not_called' and row['status']=='cancelled' and row['active_slot'] is None

async def test_projected_ambiguous_receipt_retains_proof_but_cannot_complete(integration_db,monkeypatch):
    db=integration_db;job=await queue(db,'hubspot')
    await IntegrationDelivery(db).run('w',job['id'],provider=AsyncMock(return_value={'status_code':409}))
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    service=review.IntegrationReview(db);view=await service.inspect('w',job['id'])
    assert view['outcome_at_review']=='received' and view['allowed_decisions']==['stop_local']
    result=await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    row=await db.outreach_webhook_deliveries.find_one({'id':job['id']})
    assert result['outcome_at_review']=='received' and row['active_slot'] and row['attempt_receipts']

async def test_other_destination_live_writer_blocks_private_review(integration_db,monkeypatch):
    db=integration_db;job=await held(db,monkeypatch)
    await db.outreach_webhook_deliveries.insert_one({'_id':'other-writer','id':'other-writer','workspace_id':'w',
        'destination_type':'slack','destination_id':'slack','status':'possible','lease_id':'other-owner',
        'leased_until':now()+timedelta(seconds=60)})
    service=review.IntegrationReview(db);view=await service.inspect('w',job['id'])
    assert 'other_integration_writer_live_or_unproven' in view['blockers']
    with pytest.raises(ValueError):await service.resolve('w',job['id'],'stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert db.outreach_campaigns.docs[0]['status']=='active'

async def test_deleted_legacy_source_with_original_plaintext_url_is_stop_only(integration_db,monkeypatch):
    db=integration_db;await db.outreach_webhooks.delete_one({'workspace_id':'w','id':'hook'})
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    await db.outreach_webhook_deliveries.insert_one({'_id':'legacy','id':'legacy','workspace_id':'w','destination_id':'hook',
        'status':'review_required','target_url':'https://original.example/hook','secret_enc':'copied-encrypted-signing-key'})
    service=review.IntegrationReview(db);view=await service.inspect('w','legacy')
    assert view['allowed_decisions']==['stop_local'] and 'original.example' not in str(view)
    result=await service.resolve('w','legacy','stop_local','operator',EVIDENCE,workers_drained=True,expected_digest=view['review_digest'])
    assert result['outcome_at_review']=='unknown'
    row=await db.outreach_webhook_deliveries.find_one({'id':'legacy'})
    assert 'target_url' not in row and 'secret_enc' not in row
    assert not db.outreach_webhooks.docs and db.outreach_integration_controls.docs[0]['latched']
    saved=await service.inspect('w','legacy')
    assert saved['review_saved'] and saved['review_status']=='review_stopped' and saved['allowed_decisions']==[]
