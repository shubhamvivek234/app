"""Native cancellation races and actual JSON serialization, with synthetic identities."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from outreach.api import billing, integrations
from tests.test_outreach_authorized_context import app_for, client_for
from tests.test_outreach_lead_workspace_scope import USER, WORKSPACE
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


@pytest.mark.parametrize('collection,path,private', [
    ('outreach_webhooks', '/integrations/webhooks', {'secret_enc': 'private-envelope'}),
    ('outreach_api_keys', '/integrations/api-keys', {'key_hash': 'private-hash'}),
])
async def test_native_settings_lists_return_json_and_only_public_fields(real_db, monkeypatch, collection, path, private):
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_PILOT_WORKSPACES', WORKSPACE)
    row = {'id': 'public-id', 'workspace_id': WORKSPACE, 'name': 'Current',
           'created_at': datetime.now(timezone.utc), 'revoked_at': None,
           'unexpected_secret': 'private-unknown', **private}
    await real_db[collection].insert_one(row)
    await real_db[collection].insert_many([
        {**{key: value for key, value in row.items() if key != '_id'}, 'workspace_id': 'foreign', 'id': 'foreign'},
        {**{key: value for key, value in row.items() if key != '_id'}, 'workspace_id': [WORKSPACE, 'foreign'], 'id': 'array'},
    ])
    assert '_id' in row
    async with client_for(app_for(real_db, integrations.router)) as client:
        result = await client.get(path)
    assert result.status_code == 200
    assert len(result.json()) == 1 and result.json()[0]['id'] == 'public-id'
    assert 'private' not in result.text and '_id' not in result.json()[0]
    stored = await real_db[collection].find_one({'id': 'public-id'})
    assert stored['unexpected_secret'] == 'private-unknown' and '_id' in stored


@pytest.mark.parametrize('change', ['renewal', 'invoice', 'revocation'])
async def test_native_concurrent_term_change_cannot_acknowledge_cancellation(real_db, change):
    term = {'workspace_id': WORKSPACE, 'status': 'active', 'seats': 1,
            'payment_source': 'manual_verified_invoice', 'last_invoice_id': 'original',
            'paid_through': datetime.now(timezone.utc) + timedelta(days=10)}
    await real_db.outreach_entitlements.insert_one(term)
    actual = real_db.outreach_entitlements

    class RacingCollection:
        async def find_one(self, *args, **kwargs): return await actual.find_one(*args, **kwargs)
        async def update_one(self, query, patch):
            changes = {'renewal': {'paid_through': datetime.now(timezone.utc) + timedelta(days=30)},
                       'invoice': {'last_invoice_id': 'replacement'}, 'revocation': {'is_revoked': True}}
            await actual.update_one({'workspace_id': WORKSPACE}, {'$set': changes[change]})
            return await actual.update_one(query, patch)

    class RacingDatabase:
        outreach_entitlements = RacingCollection()

    with pytest.raises(HTTPException) as exc:
        await billing.cancel_subscription(current_user=USER, db=RacingDatabase())
    assert exc.value.status_code == 409
    assert not (await actual.find_one({'workspace_id': WORKSPACE})).get('cancel_at_period_end')


async def test_native_bson_term_and_idempotent_cancellation(real_db):
    await real_db.outreach_entitlements.insert_one({'workspace_id': WORKSPACE, 'status': 'active',
        'seats': 1, 'payment_source': 'manual_verified_invoice', 'last_invoice_id': 'original',
        'paid_through': datetime.now(timezone.utc) + timedelta(days=10)})
    first = await billing.cancel_subscription(current_user=USER, db=real_db)
    stored = await real_db.outreach_entitlements.find_one({'workspace_id': WORKSPACE})
    second = await billing.cancel_subscription(current_user=USER, db=real_db)
    assert first == second
    assert (await real_db.outreach_entitlements.find_one({'workspace_id': WORKSPACE}))['cancellation_requested_at'] == stored['cancellation_requested_at']


@pytest.mark.parametrize('body,status', [('Original', 202), ('Changed', 409)])
async def test_native_reply_reference_reads_original_without_a_new_queue(real_db, body, status):
    from tests.test_outreach_reply_request_recovery import original, REQUEST, CONTEXT
    from outreach.api import inbox
    from outreach.api.inbox import _reply_request_job_id
    row = original()
    row.update(workspace_id=WORKSPACE, actor_id=USER['user_id'], _id=_reply_request_job_id(WORKSPACE, USER['user_id'], REQUEST))
    await real_db.outreach_manual_actions.insert_one(row)
    async with client_for(app_for(real_db, inbox.router)) as client:
        response = await client.post('/inbox/thread/reply', json={'body': body, 'request_id': str(REQUEST), 'context': CONTEXT})
        recovered = await client.get(f'/inbox/requests/{REQUEST}')
    assert response.status_code == status
    assert recovered.status_code == 200 and recovered.json()['result']['message']['body'] == 'Original'
    assert await real_db.outreach_manual_actions.count_documents({}) == 1
    assert await real_db.outreach_inbox_jobs.count_documents({}) == 0


@pytest.mark.parametrize('changed', ['actor', 'workspace'])
async def test_native_reply_reference_cannot_read_another_identity(real_db, changed):
    from tests.test_outreach_reply_request_recovery import original, REQUEST
    from outreach.api.inbox import get_reply_request
    row = original()
    await real_db.outreach_manual_actions.insert_one(row)
    other = {'user_id': 'other' if changed == 'actor' else 'actor',
             'default_workspace_id': 'foreign' if changed == 'workspace' else 'workspace'}
    with pytest.raises(HTTPException) as exc:
        await get_reply_request(REQUEST, current_user=other, db=real_db)
    assert exc.value.status_code == 404


async def test_native_recipient_replacement_between_read_and_slot_denies(real_db, monkeypatch):
    from outreach.core.manual_actions import ManualActions
    from tests.test_outreach_reply_request_recovery import CONTEXT
    await real_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': WORKSPACE})
    await real_db.outreach_inbox_threads.insert_one({'id': 'thread', 'workspace_id': WORKSPACE, **CONTEXT})
    binding = ManualActions.binding
    async def replace(self, *args):
        result = await binding(self, *args)
        await real_db.outreach_inbox_threads.update_one({'id': 'thread'}, {'$set': {'conversation_urn': 'replacement'}})
        return result
    monkeypatch.setattr(ManualActions, 'binding', replace)
    with pytest.raises(ValueError, match='conversation changed'):
        await ManualActions(real_db).queue('new', WORKSPACE, 'sender', 'thread', 'inbox_reply', 'reply',
            {'body': 'Original'}, USER['user_id'], expected_target=CONTEXT)
    assert await real_db.outreach_manual_actions.count_documents({}) == 0
    assert 'manual_action_id' not in await real_db.outreach_inbox_threads.find_one({'id': 'thread'})
