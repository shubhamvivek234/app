"""Authorization revocation, immutable receipts and commit-loss recovery."""
from datetime import timedelta
from unittest.mock import AsyncMock
import pytest
from outreach.core import integration_custody as custody, suppression
from outreach.core.integration_delivery import IntegrationDelivery, identity, now, receipt_digest
from tests.test_outreach_integration_delivery import integration_db, queue
from tests.test_outreach_session_custody import scoped

pytestmark = pytest.mark.asyncio

async def test_same_request_recovers_original_reference_even_after_rotation(integration_db):
    db = integration_db; first = await queue(db)
    await db.outreach_webhooks.update_one({'workspace_id': 'w'}, {'$set': {'credential_generation': 'replacement'}})
    second = await queue(db)
    assert first['id'] == second['id'] and not second['newly_queued']
    assert await db.outreach_webhook_deliveries.count_documents({}) == 1

async def test_identity_reuse_for_different_payload_denies(integration_db):
    await queue(integration_db)
    with pytest.raises(ValueError, match='reused'):
        await IntegrationDelivery(integration_db).queue('w', 'webhook', 'hook', 'event', {'changed': True}, actor='actor')

async def test_crm_pending_or_unknown_lead_slot_cannot_be_replaced(integration_db):
    db = integration_db; job = await queue(db, 'hubspot')
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': {'status': 'review_required'}})
    with pytest.raises(ValueError, match='owns'):
        await IntegrationDelivery(db).queue('w', 'hubspot', 'hubspot', 'second', {}, actor='actor', lead_id='lead')

@pytest.mark.parametrize('mutation', ['disconnect', 'lead', 'mapping', 'flag', 'policy'])
async def test_final_authority_denies_changed_basis(integration_db, scoped, monkeypatch, mutation):
    db = integration_db; job = await queue(db, 'hubspot'); opening = scoped.open
    async def change(*args):
        result = await opening(*args)
        if mutation == 'disconnect': await custody.disconnect(db, 'w', 'hubspot', 'hubspot', authority={"actor": "actor"})
        elif mutation == 'lead': await db.outreach_leads.update_one({'workspace_id': 'w'}, {'$set': {'email': 'changed@example.com'}})
        elif mutation == 'mapping': await db.outreach_external_mappings.insert_one({'workspace_id': 'w', 'provider': 'hubspot',
            'external_account_id': '123', 'object_type': 'contact', 'internal_id': 'lead', 'external_id': '321'})
        elif mutation == 'flag': monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED', 'false')
        else: monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', 'changed')
        return result
    monkeypatch.setattr(scoped, 'open', change)
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'cancelled'
    provider.assert_not_awaited()
    assert (await db.outreach_webhook_deliveries.find_one({'id': job['id']}))['attempt'] == 0

@pytest.mark.parametrize('stamp', [None, 'invalid', 123])
async def test_invalid_request_expiry_never_calls(integration_db, stamp):
    db = integration_db; job = await queue(db)
    job['request_expires_at'] = stamp; job['immutable_digest'] = identity(job)
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': job})
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'cancelled'
    provider.assert_not_awaited()

async def test_expired_preparing_is_stopped_without_key_open(integration_db, scoped, monkeypatch):
    db = integration_db; job = await queue(db)
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': {
        'status': 'preparing', 'lease_id': 'old', 'leased_until': now() - timedelta(seconds=1)}})
    opened = AsyncMock(wraps=scoped.open); monkeypatch.setattr(scoped, 'open', opened)
    assert (await IntegrationDelivery(db).run('w', job['id']))['status'] == 'cancelled'
    opened.assert_not_awaited()

async def test_received_source_replacement_preserves_evidence_no_replay(integration_db):
    db = integration_db; job = await queue(db)
    async def provider(request):
        await db.outreach_webhooks.update_one({'workspace_id': 'w'}, {'$set': {'credential_generation': 'new'}})
        return {'status_code': 202}
    called = AsyncMock(side_effect=provider)
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=called))['status'] == 'held_received'
    await IntegrationDelivery(db).run('w', job['id'], provider=called)
    assert called.await_count == 1
    assert (await db.outreach_webhook_deliveries.find_one({'id': job['id']}))['receipt']['status_code'] == 202

@pytest.mark.parametrize('stage', ['possible', 'projection'])
async def test_lost_commit_ack_does_not_replay_or_overwrite_success(integration_db, monkeypatch, stage):
    db = integration_db; job = await queue(db); original = suppression.mutate_suppression; fired = False
    async def lost(database, workspace, operation):
        nonlocal fired
        result = await original(database, workspace, operation)
        saved = await db.outreach_webhook_deliveries.find_one({'id': job['id']})
        if not fired and saved['status'] == ('possible' if stage == 'possible' else 'delivered'):
            fired = True
            raise suppression.SuppressionUnavailable('unknown commit ack')
        return result
    monkeypatch.setattr(suppression, 'mutate_suppression', lost)
    provider = AsyncMock(return_value={'status_code': 200})
    result = await IntegrationDelivery(db).run('w', job['id'], provider=provider)
    assert result['status'] == ('possible' if stage == 'possible' else 'delivered')
    await IntegrationDelivery(db).run('w', job['id'], provider=provider)
    assert provider.await_count == (0 if stage == 'possible' else 1)

async def test_explicit_server_rejection_retries_preserving_each_attempt_receipt(integration_db):
    db = integration_db
    job = await IntegrationDelivery(db).queue('w', 'webhook', 'hook', 'system-event', {})
    provider = AsyncMock(side_effect=[{'status_code': 503}, {'status_code': 200}])
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'retry'
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': {'next_attempt_at': now()}})
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'delivered'
    row = await db.outreach_webhook_deliveries.find_one({'id': job['id']})
    assert [entry['receipt']['status_code'] for entry in row['attempt_receipts']] == [503, 200]
    assert row['attempt_receipts'][0]['owner'] != row['attempt_receipts'][1]['owner']
    assert provider.await_count == 2

async def test_late_receipt_is_preserved_but_held(integration_db, monkeypatch):
    from outreach.core import integration_delivery as delivery
    db = integration_db; job = await queue(db); stamp = now()
    async def provider(request):
        monkeypatch.setattr(delivery, 'now', lambda: stamp + timedelta(seconds=70))
        return {'status_code': 200}
    result = await IntegrationDelivery(db).run('w', job['id'], provider=provider)
    assert result['status'] == 'held_received'
    assert (await db.outreach_webhook_deliveries.find_one({'id': job['id']}))['receipt']

async def test_cross_workspace_status_and_execution_cannot_read_job(integration_db):
    job = await queue(integration_db); service = IntegrationDelivery(integration_db)
    assert (await service._result(service.scope('other', job['id'])))['status'] == 'unavailable'
    with pytest.raises(ValueError, match='unavailable'): await service.run('other', job['id'])

async def test_api_test_queues_with_stable_header_without_http(integration_db):
    from outreach.api.integrations import test_webhook_ping
    user = {'default_workspace_id': 'w', 'user_id': 'actor'}
    result = await test_webhook_ping('hook', user, integration_db, 'request-identity-123')
    retry = await test_webhook_ping('hook', user, integration_db, 'request-identity-123')
    assert result == retry and result['status'] == 'queued'
    assert await integration_db.outreach_webhook_deliveries.count_documents({}) == 1

@pytest.mark.parametrize('authority', ['member', 'api_key'])
async def test_revocation_during_config_sealing_denies_install(integration_db, scoped, monkeypatch, authority):
    from fastapi import HTTPException
    from outreach.api.integrations import _save_integration
    db = integration_db; previous = await db.outreach_webhooks.find_one({'workspace_id': 'w'})
    row = {key: value for key, value in previous.items() if key != '_id'}
    await db.outreach_api_keys.insert_one({'workspace_id': 'w', 'id': 'key', 'key_hash': 'hash', 'scopes': ['leads:read']})
    original = scoped.seal
    async def revoke(*args):
        value = await original(*args)
        if authority == 'member': await db.workspace_members.update_one({'workspace_id': 'w'}, {'$set': {'role': 'viewer'}})
        else: await db.outreach_api_keys.update_one({'workspace_id': 'w'}, {'$set': {'revoked_at': now()}})
        return value
    monkeypatch.setattr(scoped, 'seal', revoke)
    with pytest.raises(HTTPException) as error:
        await _save_integration(db, 'w', 'webhook', row, 'replacement', previous,
            **({'actor': 'actor'} if authority == 'member' else {'api_key': {'key_id': 'key', 'key_hash': 'hash'}}))
    assert error.value.status_code == 409
    assert (await db.outreach_webhooks.find_one({'workspace_id': 'w'}))['credential_generation'] == previous['credential_generation']

async def test_crm_whitespace_cannot_overwrite_remote_properties(integration_db):
    db = integration_db
    await db.outreach_leads.update_one({'workspace_id': 'w', 'id': 'lead'}, {'$set': {'first_name': '   ', 'company_name': ''}})
    job = await queue(db, 'hubspot')
    async def provider(request):
        assert 'firstname' not in request['basis']['properties'] and 'company' not in request['basis']['properties']
        return {'status_code': 200, 'external_id': '123'}
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'delivered'

@pytest.mark.parametrize('code', [408, 409, 500])
async def test_ambiguous_crm_http_receipt_keeps_the_lead_slot(integration_db, code):
    db = integration_db; job = await queue(db, 'hubspot')
    provider = AsyncMock(return_value={'status_code': code})
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=provider))['status'] == 'review_required'
    with pytest.raises(ValueError, match='owns'):
        await IntegrationDelivery(db).queue('w', 'hubspot', 'hubspot', 'new-attempt', {}, actor='actor', lead_id='lead')
    await IntegrationDelivery(db).run('w', job['id'], provider=provider)
    assert provider.await_count == 1

async def test_deferred_hubspot_auto_sync_cannot_be_enabled(integration_db):
    from fastapi import HTTPException
    from outreach.api.integrations import HubSpotConfigRequest, update_hubspot_config
    with pytest.raises(HTTPException) as error:
        await update_hubspot_config(HubSpotConfigRequest(access_token='token', portal_id='123', auto_sync_on_reply=True),
            {'default_workspace_id': 'w', 'user_id': 'actor'}, integration_db)
    assert error.value.status_code == 409

async def test_old_hubspot_setting_cannot_claim_automatic_sync_available(integration_db):
    from outreach.api.integrations import get_hubspot_config
    await integration_db.outreach_integrations.update_one({'workspace_id': 'w', 'provider': 'hubspot'},
        {'$set': {'metadata.auto_sync_on_reply': True}})
    result = await get_hubspot_config({'default_workspace_id': 'w', 'user_id': 'actor'}, integration_db)
    assert result['auto_sync_on_reply'] is False and result['auto_sync_available'] is False

async def test_api_webhook_configuration_never_resolves_dns(integration_db, monkeypatch):
    import socket
    from outreach.api.integrations import create_webhook, CreateWebhookRequest
    def deny_dns(*args, **kwargs): raise AssertionError('No customer DNS in the API event loop')
    monkeypatch.setattr(socket, 'getaddrinfo', deny_dns)
    result = await create_webhook(CreateWebhookRequest(target_url='https://customer.example/hook'),
        {'default_workspace_id': 'w', 'user_id': 'actor'}, integration_db)
    assert result['id'] and result['secret'].startswith('whsec_')

@pytest.mark.parametrize('missing', [True, False])
async def test_unknown_or_inactive_actor_cannot_queue(integration_db, missing):
    db = integration_db
    if missing:
        await db.users.delete_one({'user_id': 'actor'})
    else:
        await db.users.update_one({'user_id': 'actor'}, {'$set': {'status': 'deletion_pending'}})
    with pytest.raises(ValueError, match='actor'):
        await queue(db, 'slack')
    assert await db.outreach_webhook_deliveries.count_documents({}) == 0

async def test_webhook_retry_unknown_outcome_retains_prior_receipt_as_unresolved(integration_db):
    from outreach.core.erasure import OutreachErasure
    db = integration_db
    job = await IntegrationDelivery(db).queue('w', 'webhook', 'hook', 'internal-event', {})
    result = await IntegrationDelivery(db).run('w', job['id'], provider=AsyncMock(return_value={'status_code': 500}))
    assert result['status'] == 'retry'
    await db.outreach_webhook_deliveries.update_one({'id': job['id']}, {'$set': {'next_attempt_at': now()}})
    assert (await IntegrationDelivery(db).run('w', job['id'], provider=AsyncMock(side_effect=TimeoutError())))['status'] == 'review_required'
    row = await db.outreach_webhook_deliveries.find_one({'id': job['id']})
    assert row['receipt']['status_code'] == 500 and row['attempt'] == 2
    await OutreachErasure(db)._archive(db, 'outreach_webhook_deliveries', 'w', row)
    hold = await db.outreach_erasure_holds.find_one({'workspace_id': 'w'})
    assert hold['kind'] == 'unresolved_submission' and hold['outcome_state'] == 'review_required'
    assert hold['receipt_digest'] == row['receipt_digest'] and not hold['activation_allowed']
