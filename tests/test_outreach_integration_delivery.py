"""Reference-only integration work with original-owner receipt recovery."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import integration_custody as custody
from outreach.core.integration_delivery import IntegrationDelivery, now, receipt_digest
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_integration_custody import resource


@pytest_asyncio.fixture
async def integration_db(scoped, monkeypatch):
    monkeypatch.setenv("OUTREACH_INTEGRATIONS_ENABLED", "true")
    monkeypatch.delenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", raising=False)
    db = Database(users=[{"user_id": "actor", "status": "active", "firebase_uid": "fixture-uid"}],
        workspace_members=[{"workspace_id": "w", "user_id": "actor", "role": "owner"}])
    for kind, value in [("webhook", "private-signing-secret"),
            ("slack", "https://hooks.slack.com/services/T1/B2/private-token"), ("hubspot", "private-crm-token")]:
        row = resource(kind); row['_id'] = 'integration-fixture-' + kind
        row.update(await custody.seal(value, row, "w", kind))
        await custody.collection(db, kind).insert_one(row)
    await db.outreach_leads.insert_one({"workspace_id": "w", "id": "lead", "email": "person@example.com", "first_name": "A"})
    return db


async def queue(db, kind="webhook", **kwargs):
    return await IntegrationDelivery(db).queue("w", kind, "hook" if kind == "webhook" else kind,
        "event", {"type": "system.ping", "data": {}}, actor="actor", lead_id="lead" if kind == "hubspot" else None, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["webhook", "slack", "hubspot"])
async def test_only_references_are_persisted_and_duplicate_workers_send_once(integration_db, kind):
    db = integration_db; job = await queue(db, kind)
    assert "_enc" not in str(job) and "private-" not in str(job)
    provider = AsyncMock(return_value={"status_code": 200, "external_id": "123"})
    await asyncio.gather(*(IntegrationDelivery(db).run("w", job["id"], provider=provider) for _ in range(4)))
    assert provider.await_count == 1
    saved = await db.outreach_webhook_deliveries.find_one({"id": job["id"]})
    assert saved["status"] == "delivered" and saved["receipt"]["status_code"] == 200


@pytest.mark.asyncio
async def test_rotation_during_open_cancels_without_http(integration_db, scoped, monkeypatch):
    db = integration_db; job = await queue(db); original = scoped.open
    async def rotate(*args):
        value = await original(*args)
        await db.outreach_webhooks.update_one({"workspace_id": "w", "id": "hook"}, {"$set": {"credential_generation": "replacement"}})
        return value
    monkeypatch.setattr(scoped, "open", rotate)
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run("w", job["id"], provider=provider))["status"] == "cancelled"
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_possible_is_held_and_never_reopens_key_or_replays(integration_db, scoped, monkeypatch):
    db = integration_db; job = await queue(db, "hubspot")
    await db.outreach_webhook_deliveries.update_one({"id": job["id"]}, {"$set": {
        "status": "possible", "lease_id": "old-owner", "leased_until": now() - timedelta(seconds=1)}})
    opening = AsyncMock(wraps=scoped.open); monkeypatch.setattr(scoped, "open", opening)
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run("w", job["id"], provider=provider))["status"] == "review_required"
    opening.assert_not_awaited(); provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_receipt_repairs_projection_without_call(integration_db, scoped, monkeypatch):
    db = integration_db; job = await queue(db, "hubspot")
    receipt = {"status_code": 200, "external_id": "123", "received_at": now()}
    await db.outreach_webhook_deliveries.update_one({"id": job["id"]}, {"$set": {
        "status": "received", "lease_id": "original", "receipt": receipt, "receipt_digest": receipt_digest(receipt),
        "possible_at": now() - timedelta(seconds=1), "authorization_expires_at": now() + timedelta(seconds=60)}})
    opening = AsyncMock(wraps=scoped.open); monkeypatch.setattr(scoped, "open", opening)
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run("w", job["id"], provider=provider))["status"] == "delivered"
    assert (await db.outreach_external_mappings.find_one({"workspace_id": "w"}))["external_id"] == "123"
    opening.assert_not_awaited(); provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_permissions_revoked_after_queue_denies(integration_db):
    db = integration_db; job = await queue(db)
    await db.workspace_members.update_one({"workspace_id": "w", "user_id": "actor"}, {"$set": {"role": "viewer"}})
    provider = AsyncMock()
    assert (await IntegrationDelivery(db).run("w", job["id"], provider=provider))["status"] == "cancelled"
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_provider_failure_keeps_original_submission(integration_db):
    db = integration_db; job = await queue(db)
    provider = AsyncMock(side_effect=TimeoutError("private-credential-in-error"))
    result = await IntegrationDelivery(db).run("w", job["id"], provider=provider)
    assert result["status"] == "review_required" and "private-credential" not in str(result)
    await IntegrationDelivery(db).run("w", job["id"], provider=provider)
    assert provider.await_count == 1
