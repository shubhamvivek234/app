"""Cancellation CAS and public integration payload contracts, without providers."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from pymongo.errors import AutoReconnect

from outreach.api import billing, integrations
from tests.outreach_memory import Database

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}


def active_term():
    return {'workspace_id': 'workspace', 'status': 'active', 'seats': 1,
            'paid_through': datetime.now(timezone.utc) + timedelta(days=10),
            'payment_source': 'manual_verified_invoice', 'last_invoice_id': 'original'}


@pytest.mark.parametrize('change', [
    {'paid_through': datetime.now(timezone.utc) + timedelta(days=30)},
    {'last_invoice_id': 'replacement'}, {'is_revoked': True}, {'seats': 2},
])
async def test_cancellation_lost_current_term_write_is_conflict(change):
    db = Database(outreach_entitlements=[active_term()])
    collection = db.outreach_entitlements
    update = collection.update_one

    async def race(query, patch, **kwargs):
        collection.docs[0].update(change)
        return await update(query, patch, **kwargs)

    collection.update_one = race
    with pytest.raises(HTTPException) as exc:
        await billing.cancel_subscription(current_user=USER, db=db)
    assert exc.value.status_code == 409
    assert not collection.docs[0].get('cancel_at_period_end')


async def test_confirmed_cancellation_retries_preserve_original_request_time():
    db = Database(outreach_entitlements=[active_term()])
    first = await billing.cancel_subscription(current_user=USER, db=db)
    requested = db.outreach_entitlements.docs[0]['cancellation_requested_at']
    second = await billing.cancel_subscription(current_user=USER, db=db)
    assert first == second
    assert db.outreach_entitlements.docs[0]['cancellation_requested_at'] == requested


async def test_lost_cancellation_acknowledgement_does_not_claim_success_and_retry_is_safe():
    db = Database(outreach_entitlements=[active_term()])
    update = db.outreach_entitlements.update_one

    async def lose_ack(*args, **kwargs):
        await update(*args, **kwargs)
        raise AutoReconnect('synthetic lost acknowledgement')

    db.outreach_entitlements.update_one = lose_ack
    with pytest.raises(HTTPException) as exc:
        await billing.cancel_subscription(current_user=USER, db=db)
    assert exc.value.status_code == 503
    saved = db.outreach_entitlements.docs[0]['cancellation_requested_at']
    db.outreach_entitlements.update_one = update
    assert (await billing.cancel_subscription(current_user=USER, db=db))['status'] == 'cancellation_scheduled'
    assert db.outreach_entitlements.docs[0]['cancellation_requested_at'] == saved


@pytest.mark.parametrize('route,collection,private', [
    (integrations.list_webhooks, 'outreach_webhooks', {'secret_enc': 'private-envelope', 'unexpected_secret': 'private-unknown'}),
    (integrations.list_api_keys, 'outreach_api_keys', {'key_hash': 'private-hash', 'unexpected_secret': 'private-unknown'}),
])
async def test_integration_lists_serialize_native_ids_without_private_storage_fields(route, collection, private, monkeypatch):
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_PILOT_WORKSPACES', 'workspace')
    row = {'_id': ObjectId(), 'id': 'public-id', 'workspace_id': 'workspace',
           'name': 'Current', 'target_url': 'https://example.invalid/webhook',
           'events': ['lead.replied'], 'status': 'active', 'scopes': ['leads:write'],
           'key_prefix': 'visible-prefix', 'revoked_at': None, 'created_at': datetime.now(timezone.utc), **private}
    db = Database(**{collection: [row, {**row, 'workspace_id': 'foreign', 'id': 'foreign'}]})
    result = await route(current_user=USER, db=db)
    encoded = jsonable_encoder(result)
    assert len(encoded) == 1 and encoded[0]['id'] == 'public-id'
    assert not any(key in encoded[0] for key in ('_id', *private.keys()))
    assert 'private' not in str(encoded)
