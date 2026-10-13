from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.activation import claim_activation, release_activation, activation_lead_filter
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_two_launchers_cannot_prepare_same_revision():
    campaign = {"id": "c", "workspace_id": "w", "status": "paused", "authorization_revision": 1}
    db = Database(outreach_campaigns=[campaign])
    claim = await claim_activation(db, campaign)
    assert claim and claim["revision"] == 2
    assert await claim_activation(db, campaign) is None
    assert await claim_activation(db, {**campaign, "authorization_revision": 2}) is None
    assert not await release_activation(db, "other", "c", claim["token"])
    assert await release_activation(db, "w", "c", claim["token"])


@pytest.mark.asyncio
async def test_expired_launcher_cannot_overwrite_newer_lead_authorization():
    now = datetime.now(timezone.utc)
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "paused",
                                      "authorization_revision": 4, "launch_claim_expires_at": now - timedelta(seconds=1)}],
                  outreach_leads=[{"id": "l", "workspace_id": "w", "campaign_id": "c", "authorized_revision": 4}])
    campaign = await db.outreach_campaigns.find_one({"id": "c"})
    newer = await claim_activation(db, campaign)
    assert newer["revision"] == 5
    await db.outreach_leads.update_many(activation_lead_filter("w", "c", 5), {"$set": {"authorized_revision": 5}})
    await db.outreach_leads.update_many(activation_lead_filter("w", "c", 4), {"$set": {"authorized_revision": 4}})
    assert (await db.outreach_leads.find_one({"id": "l"}))["authorized_revision"] == 5


@pytest.mark.asyncio
async def test_pause_invalidates_launcher_and_other_workspace_cannot_claim():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "draft"}])
    campaign = await db.outreach_campaigns.find_one({"id": "c"})
    assert await claim_activation(db, {**campaign, "workspace_id": "other"}) is None
    claim = await claim_activation(db, campaign)
    await db.outreach_campaigns.update_one({"id": "c"}, {"$inc": {"authorization_revision": 1}, "$set": {"status": "paused"}})
    result = await db.outreach_campaigns.update_one(
        {"id": "c", "workspace_id": "w", "launch_claim_token": claim["token"], "authorization_revision": claim["revision"]},
        {"$set": {"status": "active"}},
    )
    assert result.matched_count == 0


@pytest.mark.asyncio
async def test_launch_binds_null_legacy_metadata_and_initializes_assigned_lead_node(monkeypatch):
    from outreach.api import campaigns
    from tests.campaign_readiness_fixtures import admission_database
    db = admission_database(monkeypatch)
    await db.outreach_leads.update_one({}, {'$set': {'assigned_account_id': 'a', 'authorized_revision': None, 'current_node_id': None}})
    result = await campaigns._launch_campaign_impl('c', None, {'user_id': 'u', 'default_workspace_id': 'w'}, db)
    assert result['status'] == 'launched'
    lead = await db.outreach_leads.find_one({})
    assert lead['authorized_revision'] == 1 and lead['current_node_id'] == 'n'
